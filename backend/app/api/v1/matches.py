import logging
import openai
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, status, Depends
from app.schemas.matching import MatchRequest, JobMatchResponse, CandidateProfile
from app.services.job_matching_service import JobMatchingService
from app.services.match_service import MatchService, mark_job_match_reviewed
from app.schemas.match_analysis import JobMatchOut
from app.db.connection import get_session
from sqlmodel.ext.asyncio.session import AsyncSession
from app.models.jobs import JobTable, UserTable, JobMatchTable
from app.services.role_benchmark_service import run_benchmark_pipeline, save_benchmark
from app.services.readiness_score_service import run_readiness_pipeline, save_readiness_score
from app.schemas.readiness_score import ReadinessRequest, ReadinessResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/matches", tags=["Job Matching"])

def get_matching_service(session: AsyncSession = Depends(get_session)) -> JobMatchingService:
    return JobMatchingService(session=session)


class AnalyzeMatchRequest(BaseModel):
    user_id: int = Field(..., description="Real user id (users.id)")
    job_id: int = Field(..., description="Real job id (jobs.id)")

@router.post("/", response_model=JobMatchResponse, status_code=status.HTTP_200_OK)
async def match_candidate_to_job(request: MatchRequest, matching_service: JobMatchingService = Depends(get_matching_service)):
    """
    Evaluates a candidate's profile against a target job using a two-stage 
    vector pre-filtering and LLM re-ranking pipeline.
    """
    try:
        response = await matching_service.execute_match(request)
        return response
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Matching pipeline failed: {str(e)}"
        )


@router.post("/analyze", response_model=JobMatchOut, status_code=status.HTTP_200_OK)
async def analyze_match(
    request: AnalyzeMatchRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Run AI gap analysis for a real (user_id, job_id) pair and persist it to
    `job_matches` (upsert on the unique constraint). Returns the stored row.
    """
    try:
        row = await MatchService(session=session).analyze(
            request.user_id, request.job_id
        )
        return row
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Match analysis failed: {str(e)}",
        )


@router.patch("/{match_id}/review", response_model=JobMatchOut, status_code=status.HTTP_200_OK)
async def review_match(match_id: int, session: AsyncSession = Depends(get_session)):
    """Record that a human has reviewed this match's AI-generated content."""
    try:
        match = await mark_job_match_reviewed(session, match_id)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    return match


@router.post(
    "/{match_id}/deepen",
    response_model=ReadinessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Deepen an existing match into a full readiness assessment",
    description=(
        "Takes an existing job match, extracts a role benchmark from that job's "
        "real description, then scores the same user's readiness against it. "
        "Runs two separate LLM pipelines in sequence — noticeably slower and "
        "costlier than either /matches/analyze or /readiness/score alone.\n\n"
        "**⚠ AI-Generated Assessment — Use as decision support only.**"
    ),
)
async def deepen_match(
    match_id: int,
    session: AsyncSession = Depends(get_session),
) -> ReadinessResponse:
    # ------------------------------------------------------------------
    # 1. Load the match, its job, and its user
    # ------------------------------------------------------------------
    match: JobMatchTable | None = await session.get(JobMatchTable, match_id)
    if match is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job match with id={match_id!r} was not found.",
        )

    job: JobTable | None = await session.get(JobTable, match.job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with id={match.job_id!r} was not found.",
        )

    if len(job.description) < 50:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Job {job.id!r}'s description is too short ({len(job.description)} "
                "characters) to extract a reliable benchmark. Minimum 50 characters."
            ),
        )

    user: UserTable | None = await session.get(UserTable, match.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id={match.user_id!r} was not found.",
        )

    # ------------------------------------------------------------------
    # 2. Extract a role benchmark from this job's real description
    # ------------------------------------------------------------------
    try:
        benchmark_state = await run_benchmark_pipeline(raw_text=job.description)
    except ValueError as exc:
        logger.error("Benchmark extraction pipeline exhausted retries: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM extraction failed after maximum retries: {exc}",
        ) from exc
    except openai.RateLimitError as exc:
        logger.error("LLM rate limit hit during benchmark extraction: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The AI model rate limit has been reached. Please retry shortly.",
        ) from exc
    except openai.AuthenticationError as exc:
        logger.error("LLM authentication failed during benchmark extraction: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI model authentication failed. Check LITELLM_API_KEY.",
        ) from exc
    except openai.APIError as exc:
        logger.exception("LLM API error during benchmark extraction pipeline")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI model returned an error: {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error during benchmark extraction pipeline")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during benchmark extraction.",
        ) from exc

    try:
        new_benchmark = await save_benchmark(benchmark_state, session)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    # ------------------------------------------------------------------
    # 3. Score this user's readiness against the freshly extracted benchmark
    # ------------------------------------------------------------------
    candidate_profile = CandidateProfile.from_user(user)
    readiness_request = ReadinessRequest(benchmark_id=new_benchmark.id, user_id=match.user_id)

    try:
        final_state = await run_readiness_pipeline(
            request=readiness_request,
            benchmark=new_benchmark,
            candidate_profile=candidate_profile,
        )
    except ValueError as exc:
        logger.error("Readiness scoring pipeline exhausted retries: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM readiness scoring failed after maximum retries: {exc}",
        ) from exc
    except openai.RateLimitError as exc:
        logger.error("LLM rate limit hit during readiness scoring: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The AI model rate limit has been reached. Please retry shortly.",
        ) from exc
    except openai.AuthenticationError as exc:
        logger.error("LLM authentication failed during readiness scoring: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI model authentication failed. Check LITELLM_API_KEY.",
        ) from exc
    except openai.APIError as exc:
        logger.exception("LLM API error during readiness scoring pipeline")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI model returned an error: {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error during readiness scoring pipeline")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during readiness scoring.",
        ) from exc

    try:
        db_record = await save_readiness_score(
            state=final_state, session=session, job_match_id=match.id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    # ------------------------------------------------------------------
    # 4. Build and return the response
    # ------------------------------------------------------------------
    analysis = final_state["analysis"]
    return ReadinessResponse(
        id=db_record.id,
        benchmark_id=db_record.benchmark_id,
        user_id=db_record.user_id,
        job_match_id=db_record.job_match_id,
        created_at=db_record.created_at,
        reviewed_at=db_record.reviewed_at,
        overall_score=analysis.overall_score,
        sub_scores=analysis.sub_scores,
        critical_gaps=analysis.critical_gaps,
        nice_to_have_gaps=analysis.nice_to_have_gaps,
        strengths=analysis.strengths,
        explanation=analysis.explanation,
    )
