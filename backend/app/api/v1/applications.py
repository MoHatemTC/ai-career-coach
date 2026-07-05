from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.connection import get_session
from app.models.jobs import JobTable, UserTable
from app.schemas.application_ai import ApplicationRequest, ApplicationResponse
from app.schemas.matching import CandidateProfile
from app.services.application_ai_service import ApplicationAIService
from app.services.log_service import write_log
from app.services.match_service import upsert_job_match

router = APIRouter(prefix="/applications", tags=["Application AI"])


class GenerateMaterialsRequest(BaseModel):
    user_id: int = Field(..., description="Real user id (users.id)")
    job_id: int = Field(..., description="Real job id (jobs.id)")

    model_config = {"json_schema_extra": {"example": {"user_id": 1, "job_id": 1}}}


@router.post(
    "/",
    response_model=ApplicationResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate Application Materials",
    description=(
        "Generate (or regenerate) tailored CV suggestions and a cover-letter draft "
        "for a real (user, job) pair. The candidate profile and job description are "
        "loaded from the database — the caller only supplies user_id and job_id. "
        "Results are persisted to job_matches and can be read back via "
        "GET /tracking/jobs/{job_id}/application-materials."
    ),
)
async def generate_application_materials(
    request: GenerateMaterialsRequest,
    session: AsyncSession = Depends(get_session),
):
    """Two-stage pipeline: CV tailoring -> cover letter, persisted to job_matches."""
    user = await session.get(UserTable, request.user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User {request.user_id} not found")
    job = await session.get(JobTable, request.job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {request.job_id} not found")

    ai_request = ApplicationRequest(
        candidate_id=request.user_id,
        job_id=request.job_id,
        candidate_profile=CandidateProfile.from_user(user),
        job_description=job.description,
    )

    await write_log(
        session, stage="cover_letter", status="started",
        user_id=request.user_id, job_id=request.job_id,
    )
    try:
        result = await ApplicationAIService(session=session).generate_application_materials(
            ai_request
        )
    except ValueError as ve:
        await write_log(
            session, stage="error", status="failure", message=str(ve),
            user_id=request.user_id, job_id=request.job_id,
            metadata={"stage": "cover_letter"},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(ve)
        )
    except Exception as e:
        await write_log(
            session, stage="error", status="failure", message=str(e),
            user_id=request.user_id, job_id=request.job_id,
            metadata={"stage": "cover_letter"},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Application AI pipeline failed: {str(e)}",
        )

    # Persist via the canonical upsert (same format the SHORTLISTED task writes).
    await upsert_job_match(
        session,
        user_id=request.user_id,
        job_id=request.job_id,
        cv_tailoring_suggestion=(
            result.cv_tailoring.model_dump_json() if result.cv_tailoring else ""
        ),
        cover_letter_draft=(
            result.cover_letter.model_dump_json() if result.cover_letter else None
        ),
    )
    await write_log(
        session, stage="cover_letter", status="success",
        user_id=request.user_id, job_id=request.job_id,
    )
    await session.commit()
    return result
