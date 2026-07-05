"""
app/api/v1/readiness.py
========================
FastAPI router that exposes:

  POST /readiness/score
    - Accepts a ``ReadinessRequest`` (benchmark_id + user_id), loads the real
      user's profile, and runs the scoring pipeline against it.
    - Fetches the target ``RoleBenchmark`` from PostgreSQL.
    - Runs the LangGraph readiness scoring pipeline.
    - Persists the result in PostgreSQL via SQLModel.
    - Returns the scored ``ReadinessResponse`` to the caller.

.. important::
   Readiness scores produced by this endpoint are **AI-generated assessments**.
   They should be used as a decision-support tool, not as a sole basis for any
   hiring or career decision.  Scores may be inaccurate if the candidate profile
   or benchmark is incomplete.
"""

from __future__ import annotations

import logging
from typing import Annotated

import openai
from fastapi import APIRouter, Depends, HTTPException, Response, status
from prometheus_client import Histogram
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.connection import get_session
from app.models.jobs import UserTable
from app.models.readiness_score import ReadinessScore as ReadinessScoreModel
from app.models.role_benchmark import RoleBenchmark as RoleBenchmarkModel
from app.schemas.matching import CandidateProfile
from app.schemas.readiness_score import (
    ReadinessRequest,
    ReadinessResponse,
    SubScores,
)
from app.services.readiness_score_service import (
    mark_readiness_score_reviewed,
    run_readiness_pipeline,
    save_readiness_score,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

from app.core.metrics import get_or_create_metric

READINESS_SCORING_LATENCY = get_or_create_metric(
    Histogram,
    "readiness_scoring_latency_seconds",
    "End-to-end latency for the LLM readiness scoring pipeline",
)

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/readiness", tags=["readiness"])

# ---------------------------------------------------------------------------
# Database session dependency
# ---------------------------------------------------------------------------

SessionDep = Annotated[AsyncSession, Depends(get_session)]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/score",
    response_model=ReadinessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Score a candidate's readiness against a role benchmark (AI assessment)",
    description=(
        "Compare a structured candidate profile against a previously extracted "
        "role benchmark to generate a 0–100 readiness score, dimensional "
        "sub-scores, critical gaps, nice-to-have gaps, and an explanation.\n\n"
        "**⚠ AI-Generated Assessment — Use as decision support only.**\n\n"
        "Supply the ``benchmark_id`` returned by ``POST /benchmarks/analyze`` "
        "and the candidate's structured profile."
    ),
)
async def score_readiness(
    session: SessionDep,
    request: ReadinessRequest,
    response: Response,
) -> ReadinessResponse:
    """
    POST /readiness/score

    Scores a candidate's readiness against a persisted role benchmark using
    an LLM gap-analysis pipeline, persists the result, and returns it.

    Parameters
    ----------
    session:
        Injected SQLModel database session.
    request:
        :class:`~app.schemas.readiness_score.ReadinessRequest` — the
        ``benchmark_id`` and ``user_id`` of the real, stored user to evaluate.
    response:
        FastAPI ``Response`` object (used to set custom headers).

    Returns
    -------
    ReadinessResponse
        The scored and persisted readiness assessment.

    Raises
    ------
    404 Not Found
        If ``benchmark_id`` does not match any record in the database.
    422 Unprocessable Entity
        If the request body fails Pydantic validation.
    502 Bad Gateway
        If the LLM API returns an error or fails after all retries.
    503 Service Unavailable
        If the LLM rate limit is reached.
    500 Internal Server Error
        For unexpected errors during the pipeline or persistence.
    """
    # ------------------------------------------------------------------
    # 1. Load the benchmark from the database
    # ------------------------------------------------------------------
    benchmark: RoleBenchmarkModel | None = await session.get(
        RoleBenchmarkModel, request.benchmark_id
    )
    if benchmark is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"RoleBenchmark with id={request.benchmark_id!r} was not found. "
                "Create a benchmark first via POST /api/v1/benchmarks/analyze."
            ),
        )

    # ------------------------------------------------------------------
    # 2. Load the user and build the profile
    # ------------------------------------------------------------------
    user: UserTable | None = await session.get(UserTable, request.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id={request.user_id!r} was not found.",
        )
    candidate_profile = CandidateProfile.from_user(user)

    # ------------------------------------------------------------------
    # 3. Run the LangGraph scoring pipeline (latency observed via Prometheus)
    # ------------------------------------------------------------------
    try:
        with READINESS_SCORING_LATENCY.time():
            final_state = await run_readiness_pipeline(
                request=request,
                benchmark=benchmark,
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

    # ------------------------------------------------------------------
    # 4. Persist to PostgreSQL via the service layer
    # ------------------------------------------------------------------
    try:
        db_record: ReadinessScoreModel = await save_readiness_score(
            state=final_state,
            session=session,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    # ------------------------------------------------------------------
    # 5. Set observability header (Langfuse trace integration point)
    # ------------------------------------------------------------------
    response.headers["X-Readiness-Score-Id"] = str(db_record.id)

    # ------------------------------------------------------------------
    # 6. Build and return the API response
    # ------------------------------------------------------------------
    analysis = final_state["analysis"]

    return ReadinessResponse(
        id=db_record.id,
        benchmark_id=db_record.benchmark_id,
        user_id=db_record.user_id,
        created_at=db_record.created_at,
        reviewed_at=db_record.reviewed_at,
        overall_score=analysis.overall_score,
        sub_scores=analysis.sub_scores,
        critical_gaps=analysis.critical_gaps,
        nice_to_have_gaps=analysis.nice_to_have_gaps,
        strengths=analysis.strengths,
        explanation=analysis.explanation,
    )


@router.patch("/{readiness_score_id}/review", response_model=ReadinessResponse, status_code=status.HTTP_200_OK)
async def review_readiness_score(readiness_score_id: int, session: AsyncSession = Depends(get_session)):
    """Record that a human has reviewed this readiness assessment."""
    try:
        score = await mark_readiness_score_reviewed(session, readiness_score_id)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    return ReadinessResponse(
        id=score.id,
        benchmark_id=score.benchmark_id,
        user_id=score.user_id,
        created_at=score.created_at,
        reviewed_at=score.reviewed_at,
        overall_score=score.overall_score,
        sub_scores=SubScores(
            must_have_skills_score=score.must_have_skills_score,
            tools_score=score.tools_score,
            experience_score=score.experience_score,
            soft_skills_score=score.soft_skills_score,
        ),
        critical_gaps=score.critical_gaps,
        nice_to_have_gaps=score.nice_to_have_gaps,
        strengths=score.strengths,
        explanation=score.explanation,
    )
