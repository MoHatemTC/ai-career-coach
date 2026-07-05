"""
Search Orchestration Service (Sprint 4, Task 13).

Orchestrates the full search pipeline:
1. Job Collection (fetch + dedup + insert)
2. For each user: Match + rank new jobs
3. For each good match: Record a notification
"""
from dataclasses import dataclass
from uuid import uuid4

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
import structlog

from app.core.config import get_settings
from app.models.jobs import JobTable, UserTable
from app.services.job_collection_service import collect_from_sources, get_available_sources
from app.services.job_recommendation_service import recommend_jobs_for_user
from app.services.log_service import write_log
from app.services.notification_service import notify_user_of_job
from app.models.notification import NotificationStatus

from prometheus_client import Counter
from app.core.metrics import get_or_create_metric

SEARCH_RUNS_TOTAL = get_or_create_metric(Counter, "search_runs_total", "Search runs", ["status"])

settings = get_settings()
logger = structlog.get_logger()


@dataclass(frozen=True)
class SearchRunResult:
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


async def run_search(
    session: AsyncSession,
    *,
    source_names: list[str] | None = None,
    user_ids: list[int] | None = None,
    notify: bool = True,
) -> SearchRunResult:
    """
    Run the entire automation-ready backend flow: collect jobs -> match to users -> notify.
    """
    run_id = uuid4().hex
    sources = source_names if source_names is not None else get_available_sources()
    
    await write_log(
        session,
        stage="search_run",
        status="started",
        message="search run started",
        metadata={"run_id": run_id, "sources": sources, "user_ids": user_ids}
    )

    # 1. Collect
    collection = await collect_from_sources(sources, session)
    jobs_fetched = sum(r.fetched for r in collection.results) if collection.results else 0
    jobs_inserted = collection.total_inserted
    jobs_duplicates = collection.total_duplicates

    # 2. Resolve users
    target_users: list[UserTable] = []
    if user_ids is not None:
        for uid in user_ids:
            user = await session.get(UserTable, uid)
            if user:
                target_users.append(user)
            else:
                logger.warning("search_run_user_not_found", user_id=uid, run_id=run_id)
    else:
        statement = select(UserTable).where(UserTable.email.is_not(None))
        result = await session.exec(statement)
        target_users = list(result.all())

    # 3. Match & Notify per user
    errors: list[str] = []
    notifications_sent = 0
    notifications_skipped_duplicate = 0
    notifications_skipped_no_email = 0

    for user in target_users:
        try:
            async with session.begin_nested():
                matches = await recommend_jobs_for_user(user.id, session)
                
                # Filter matches above threshold and limit by top N
                good = [m for m in matches if m.get("total_score", 0) >= settings.MATCH_SCORE_NOTIFICATION_THRESHOLD][:settings.TOP_N_JOBS_PER_USER]
                
                if not notify:
                    continue
                    
                for m in good:
                    job_id = m["job"]["id"]
                    job = await session.get(JobTable, job_id)
                    if not job:
                        logger.error("search_run_job_not_found", job_id=job_id, run_id=run_id)
                        continue

                    row = await notify_user_of_job(
                        session,
                        user=user,
                        job=job,
                        match_score=m.get("total_score", 0),
                        search_run_id=run_id
                    )
                    
                    if row is None:
                        notifications_skipped_duplicate += 1
                    elif row.status == NotificationStatus.SKIPPED:
                        notifications_skipped_no_email += 1
                    elif row.status == NotificationStatus.SENT:
                        notifications_sent += 1
                        
        except Exception as e:
            logger.exception("search_run_user_error", user_id=user.id, run_id=run_id, error=str(e))
            errors.append(f"user {user.id}: {e}")

    # 4. Finish
    result = SearchRunResult(
        run_id=run_id,
        sources=sources,
        jobs_fetched=jobs_fetched,
        jobs_inserted=jobs_inserted,
        jobs_duplicates=jobs_duplicates,
        users_processed=len(target_users),
        notifications_sent=notifications_sent,
        notifications_skipped_duplicate=notifications_skipped_duplicate,
        notifications_skipped_no_email=notifications_skipped_no_email,
        errors=errors,
    )
    
    metadata = {
        "run_id": run_id,
        "sources": sources,
        "jobs_fetched": jobs_fetched,
        "jobs_inserted": jobs_inserted,
        "jobs_duplicates": jobs_duplicates,
        "users_processed": len(target_users),
        "notifications_sent": notifications_sent,
        "notifications_skipped_duplicate": notifications_skipped_duplicate,
        "notifications_skipped_no_email": notifications_skipped_no_email,
        "errors": errors,
    }

    await write_log(
        session,
        stage="search_run",
        status="success" if not errors else "failure",
        message=f"search run complete: {len(target_users)} users processed",
        metadata=metadata
    )

    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    SEARCH_RUNS_TOTAL.labels(status="success" if not errors else "partial").inc()

    return result
