"""
Job Tracking & Market Trends API.

Two routers live here (both registered in ``app/api/v1/api.py``):

``router``         — /tracking : a user's personal job pipeline (state machine).
``trends_router``  — /trends   : aggregate market intelligence over ``jobs``.

The tracking write endpoint is idempotent — re-sending the status a job already
holds is a no-op (no duplicate audit event). See ``job_tracking_service`` for
the state-machine contract.
"""

from typing import Optional

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.connection import get_session
from app.models.job_tracking import TrackingStatus
from app.schemas.job_tracking import (
    JobTrackingListOut,
    JobTrackingOut,
    LabeledCountOut,
    MarketTrendsOut,
    PostingVolumePointOut,
    SalaryStatOut,
    TrackingHistoryOut,
    TrackJobRequest,
)
from app.services import market_trend_service as trends
from app.services.job_tracking_service import (
    JobNotFoundError,
    TrackingNotFoundError,
    generate_application_materials_task,
    get_tracking,
    get_tracking_history,
    list_tracked_jobs,
    should_generate_materials,
    track_job,
    _get_tracking_row,
)

logger = structlog.get_logger()

# ===========================================================================
# Job tracking — /tracking
# ===========================================================================

router = APIRouter()


@router.put("/jobs/{job_id}", response_model=JobTrackingOut)
async def set_job_status(
    job_id: int,
    body: TrackJobRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> JobTrackingOut:
    """Record or transition a job's status in the user's pipeline.

    Idempotent: re-sending the current status changes nothing and logs no event.
    On the first transition into SHORTLISTED, schedules background generation of
    CV-tailoring + cover-letter materials (runs after the response is sent).
    Returns the resulting tracking row.
    """
    # Capture the prior state so we can detect first entry into SHORTLISTED.
    prior = await _get_tracking_row(session, user_id=body.user_id, job_id=job_id)
    previous_status = prior.status if prior else None

    try:
        row = await track_job(
            session, user_id=body.user_id, job_id=job_id, status=body.status
        )
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    await session.commit()
    logger.info(
        "job_status_set",
        user_id=body.user_id,
        job_id=job_id,
        status=body.status.value,
    )

    # Generate application materials in the background *after* commit, so the LLM
    # calls never block this response.
    if should_generate_materials(
        previous_status=previous_status, new_status=body.status
    ):
        background_tasks.add_task(
            generate_application_materials_task, body.user_id, job_id
        )

    return JobTrackingOut.model_validate(row)


@router.get("/jobs/{job_id}", response_model=JobTrackingOut)
async def get_job_status(
    job_id: int,
    user_id: int = Query(description="The user whose pipeline to read."),
    session: AsyncSession = Depends(get_session),
) -> JobTrackingOut:
    """Return the current tracking state for a ``(user_id, job_id)`` pair."""
    try:
        row = await get_tracking(session, user_id=user_id, job_id=job_id)
    except TrackingNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} is not tracked by user {user_id}",
        )
    return JobTrackingOut.model_validate(row)


@router.get("", response_model=JobTrackingListOut)
async def list_tracking(
    user_id: int = Query(description="The user whose pipeline to list."),
    status: Optional[TrackingStatus] = Query(
        default=None, description="Optional filter by pipeline state."
    ),
    session: AsyncSession = Depends(get_session),
) -> JobTrackingListOut:
    """List a user's tracked jobs, newest-updated first, optionally filtered."""
    rows = await list_tracked_jobs(session, user_id=user_id, status=status)
    return JobTrackingListOut(
        items=[JobTrackingOut.model_validate(r) for r in rows],
        total=len(rows),
    )


@router.get("/jobs/{job_id}/history", response_model=TrackingHistoryOut)
async def get_job_history(
    job_id: int,
    user_id: int = Query(description="The user whose history to read."),
    session: AsyncSession = Depends(get_session),
) -> TrackingHistoryOut:
    """Return the append-only transition history for a pair (oldest first)."""
    try:
        events = await get_tracking_history(session, user_id=user_id, job_id=job_id)
    except TrackingNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} is not tracked by user {user_id}",
        )
    return TrackingHistoryOut(job_id=job_id, user_id=user_id, events=events)


@router.get("/jobs/{job_id}/application-materials")
async def get_application_materials(
    job_id: int,
    user_id: int = Query(description="The user whose application materials to read."),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return the generated CV tailoring suggestions and cover letter for a job."""
    from app.models.jobs import JobMatchTable
    from sqlmodel import select
    import json
    
    stmt = select(JobMatchTable).where(
        JobMatchTable.user_id == user_id,
        JobMatchTable.job_id == job_id
    )
    match_row = (await session.exec(stmt)).first()
    
    if not match_row:
        raise HTTPException(
            status_code=404,
            detail=f"No application materials found for job {job_id} and user {user_id}",
        )
        
    def safe_loads(val: str) -> dict | None:
        if not val:
            return None
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            return None
            
    return {
        "job_id": job_id,
        "user_id": user_id,
        "cv_tailoring_suggestion": safe_loads(match_row.cv_tailoring_suggestion),
        "cover_letter_draft": safe_loads(match_row.cover_letter_draft),
        "reviewed_at": match_row.reviewed_at,
    }

# ===========================================================================
# Market trends — /trends
# ===========================================================================

trends_router = APIRouter()


@trends_router.get("/companies", response_model=list[LabeledCountOut])
async def top_companies(
    limit: int = Query(default=10, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> list[LabeledCountOut]:
    """Top hiring companies by posting count."""
    rows = await trends.top_companies(session, limit=limit)
    return [LabeledCountOut.model_validate(r) for r in rows]


@trends_router.get("/experience-levels", response_model=list[LabeledCountOut])
async def experience_levels(
    session: AsyncSession = Depends(get_session),
) -> list[LabeledCountOut]:
    """Distribution of postings across junior / mid / senior."""
    rows = await trends.experience_level_distribution(session)
    return [LabeledCountOut.model_validate(r) for r in rows]


@trends_router.get("/work-types", response_model=list[LabeledCountOut])
async def work_types(
    session: AsyncSession = Depends(get_session),
) -> list[LabeledCountOut]:
    """Remote / hybrid / on-site split, from the ``work_mode`` column."""
    rows = await trends.work_type_distribution(session)
    return [LabeledCountOut.model_validate(r) for r in rows]


@trends_router.get("/categories", response_model=list[LabeledCountOut])
async def categories(
    limit: int = Query(default=10, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> list[LabeledCountOut]:
    """Top job categories, from the ``work_roles`` column."""
    rows = await trends.top_categories(session, limit=limit)
    return [LabeledCountOut.model_validate(r) for r in rows]


@trends_router.get("/countries", response_model=list[LabeledCountOut])
async def countries(
    session: AsyncSession = Depends(get_session),
) -> list[LabeledCountOut]:
    """Posting counts per country code (EG / SA / QA / AE)."""
    rows = await trends.country_distribution(session)
    return [LabeledCountOut.model_validate(r) for r in rows]


@trends_router.get("/job-types", response_model=list[LabeledCountOut])
async def job_types(
    session: AsyncSession = Depends(get_session),
) -> list[LabeledCountOut]:
    """Employment-type split (full_time / part_time / ...)."""
    rows = await trends.job_type_distribution(session)
    return [LabeledCountOut.model_validate(r) for r in rows]


@trends_router.get("/posting-volume", response_model=list[PostingVolumePointOut])
async def posting_volume(
    session: AsyncSession = Depends(get_session),
) -> list[PostingVolumePointOut]:
    """Posting volume over time, bucketed by month."""
    rows = await trends.posting_volume(session)
    return [PostingVolumePointOut.model_validate(r) for r in rows]


@trends_router.get("/skills", response_model=list[LabeledCountOut])
async def top_skills(
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> list[LabeledCountOut]:
    """Top canonical skills in demand, from the normalized skills tables."""
    rows = await trends.top_skills(session, limit=limit)
    return [LabeledCountOut.model_validate(r) for r in rows]


@trends_router.get("/salaries", response_model=list[SalaryStatOut])
async def salaries(
    session: AsyncSession = Depends(get_session),
) -> list[SalaryStatOut]:
    """Salary min/avg/max per currency+period (visible salaries only)."""
    rows = await trends.salary_stats(session)
    return [SalaryStatOut.model_validate(r) for r in rows]


@trends_router.get("", response_model=MarketTrendsOut)
async def market_overview(
    session: AsyncSession = Depends(get_session),
) -> MarketTrendsOut:
    """Combined market-intelligence overview — all metrics in one call."""
    return MarketTrendsOut(
        top_companies=[LabeledCountOut.model_validate(r) for r in await trends.top_companies(session)],
        experience_levels=[LabeledCountOut.model_validate(r) for r in await trends.experience_level_distribution(session)],
        work_types=[LabeledCountOut.model_validate(r) for r in await trends.work_type_distribution(session)],
        top_categories=[LabeledCountOut.model_validate(r) for r in await trends.top_categories(session)],
        countries=[LabeledCountOut.model_validate(r) for r in await trends.country_distribution(session)],
        job_types=[LabeledCountOut.model_validate(r) for r in await trends.job_type_distribution(session)],
        posting_volume=[PostingVolumePointOut.model_validate(r) for r in await trends.posting_volume(session)],
        top_skills=[LabeledCountOut.model_validate(r) for r in await trends.top_skills(session)],
        salary_stats=[SalaryStatOut.model_validate(r) for r in await trends.salary_stats(session)],
    )
