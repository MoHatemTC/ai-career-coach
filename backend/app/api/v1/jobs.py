"""
Job Collection API — /api/v1/jobs

Endpoints:
    POST /jobs/collect   — run the collection pipeline for one or more sources
    GET  /jobs           — list stored jobs with optional filters
    GET  /jobs/sources   — list available (registered) job sources
"""

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select, func
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.connection import get_session
from app.models import JobTable
from app.schemas.jobs import (
    CollectRequest,
    CollectResponse,
    JobListResponse,
    JobOut,
    SourceResultOut,
    SourcesResponse,
)
from app.services.job_collection_service import (
    collect_from_sources,
    get_available_sources,
)

logger = structlog.get_logger()

router = APIRouter()


@router.post("/collect", response_model=CollectResponse)
async def collect_jobs(
    body: CollectRequest,
    session: AsyncSession = Depends(get_session),
) -> CollectResponse:
    """Trigger the job collection pipeline.

    Runs fetch → deduplicate → insert for every source listed in the
    request body.  Sources are processed sequentially; a failure in one
    does not block the others.
    """
    logger.info("job_collect_endpoint_called", sources=body.sources)

    available = get_available_sources()
    unknown = [s for s in body.sources if s not in available]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown source(s): {unknown}. Available: {available}",
        )

    batch = await collect_from_sources(body.sources, session)

    return CollectResponse(
        results=[SourceResultOut.from_result(r) for r in batch.results],
        total_inserted=batch.total_inserted,
        total_duplicates=batch.total_duplicates,
        total_errors=batch.total_errors,
    )


@router.get("", response_model=JobListResponse)
async def list_jobs(
    source: Optional[str] = Query(default=None, description="Filter by source name"),
    experience_level: Optional[str] = Query(
        default=None,
        description="Filter by experience level (junior | mid | senior)",
    ),
    limit: int = Query(default=50, ge=1, le=200, description="Max results"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    session: AsyncSession = Depends(get_session),
) -> JobListResponse:
    """Return stored jobs with optional filters and pagination."""
    stmt = select(JobTable)

    if source:
        stmt = stmt.where(JobTable.source == source)
    if experience_level:
        stmt = stmt.where(JobTable.experience_level == experience_level)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total: int = (await session.exec(count_stmt)).one()

    stmt = stmt.order_by(JobTable.posted_date.desc())  # type: ignore[union-attr]
    stmt = stmt.offset(offset).limit(limit)
    rows = (await session.exec(stmt)).all()

    logger.info(
        "job_list_endpoint_called",
        source=source,
        experience_level=experience_level,
        total=total,
        returned=len(rows),
    )

    return JobListResponse(
        jobs=[JobOut.from_row(r) for r in rows],
        total=total,
    )


@router.get("/sources", response_model=SourcesResponse)
def list_sources() -> SourcesResponse:
    """Return the list of registered job source names."""
    return SourcesResponse(sources=get_available_sources())
