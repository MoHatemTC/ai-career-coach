"""
Search Runs router (Sprint 4, Task 13).

Endpoints for manual triggering and inspection of the search automation layer.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
import structlog

from app.db.connection import get_session
from app.models.jobs import LogTable
from app.models.notification import NotificationTable
from app.services.job_collection_service import get_available_sources
from app.services.search_orchestration_service import run_search

logger = structlog.get_logger()
router = APIRouter()

# --- Schemas ---

class TriggerSearchRunRequest(BaseModel):
    user_ids: Optional[list[int]] = None
    sources: Optional[list[str]] = None
    notify: bool = True

class SearchRunResponse(BaseModel):
    run_id: str
    sources: list[str]
    jobs_fetched: int
    jobs_inserted: int
    jobs_duplicates: int
    users_processed: int
    notifications_sent: int
    notifications_skipped_duplicate: int
    notifications_skipped_no_email: int
    errors: list[str]

# --- Endpoints ---

@router.post("", response_model=SearchRunResponse)
async def trigger_search_run(
    request: TriggerSearchRunRequest,
    session: AsyncSession = Depends(get_session)
):
    """Trigger a manual search run."""
    # Validate sources if provided
    if request.sources:
        available = get_available_sources()
        for source in request.sources:
            if source not in available:
                raise HTTPException(status_code=400, detail=f"Invalid source: {source}")

    result = await run_search(
        session,
        source_names=request.sources,
        user_ids=request.user_ids,
        notify=request.notify,
    )
    
    return SearchRunResponse(
        run_id=result.run_id,
        sources=result.sources,
        jobs_fetched=result.jobs_fetched,
        jobs_inserted=result.jobs_inserted,
        jobs_duplicates=result.jobs_duplicates,
        users_processed=result.users_processed,
        notifications_sent=result.notifications_sent,
        notifications_skipped_duplicate=result.notifications_skipped_duplicate,
        notifications_skipped_no_email=result.notifications_skipped_no_email,
        errors=result.errors,
    )


@router.get("")
async def list_search_runs(
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session)
):
    """List recent search runs."""
    statement = (
        select(LogTable)
        .where(LogTable.stage == "search_run")
        .where(LogTable.status.in_(["success", "failure"]))
        .order_by(LogTable.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.exec(statement)
    logs = result.all()
    
    # Map log metadata into a summary
    return [
        {
            "run_id": log.log_metadata.get("run_id") if log.log_metadata else None,
            "status": log.status,
            "created_at": log.created_at,
            "summary": log.log_metadata
        }
        for log in logs
    ]


@router.get("/{run_id}")
async def get_search_run(run_id: str, session: AsyncSession = Depends(get_session)):
    """Fetch a specific search run from logs."""
    # Using JSONB containment query
    statement = (
        select(LogTable)
        .where(LogTable.stage == "search_run")
        .where(LogTable.log_metadata.contains({"run_id": run_id}))
    )
    result = await session.exec(statement)
    log = result.first()
    
    if not log:
        raise HTTPException(status_code=404, detail="Search run not found")
        
    return {
        "run_id": log.log_metadata.get("run_id") if log.log_metadata else run_id,
        "status": log.status,
        "message": log.message,
        "created_at": log.created_at,
        "metadata": log.log_metadata
    }


@router.get("/{run_id}/notifications", response_model=list[NotificationTable])
async def get_search_run_notifications(run_id: str, session: AsyncSession = Depends(get_session)):
    """List notifications generated during a specific run."""
    statement = select(NotificationTable).where(NotificationTable.search_run_id == run_id)
    result = await session.exec(statement)
    notifications = result.all()
    return notifications
