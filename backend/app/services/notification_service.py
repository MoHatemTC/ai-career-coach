"""
Notification service (Sprint 4, Task 13).

Records notifications for users regarding matched jobs.
Currently, this does not send an actual email/SMS; instead, it records a SENT row
which acts as the notification and provides a durable audit trail.
"""
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
import structlog

from app.models.jobs import JobTable, UserTable
from app.models.notification import NotificationStatus, NotificationTable

logger = structlog.get_logger()

async def notify_user_of_job(
    session: AsyncSession,
    *,
    user: UserTable,
    job: JobTable,
    match_score: int,
    search_run_id: str,
) -> NotificationTable | None:
    """
    Records that `user` was told about `job`. Returns the created row,
    or None if this pair was already notified (duplicate — no-op).

    There is no email/SMS provider wired up yet: a SENT row *is* the
    notification for now (queryable via GET /search-runs/{id}/notifications).
    When a real channel is added later, the single place to plug it in
    is right after the SENT row is created below.
    """
    # 1. Query for existing notification
    statement = select(NotificationTable).where(
        NotificationTable.user_id == user.id,
        NotificationTable.job_id == job.id
    )
    existing = (await session.exec(statement)).first()
    if existing:
        return None

    # 2. Determine status based on user email
    status = NotificationStatus.SKIPPED if not user.email else NotificationStatus.SENT

    new_notification = NotificationTable(
        user_id=user.id,
        job_id=job.id,
        match_score=match_score,
        status=status,
        search_run_id=search_run_id,
    )

    # 3. Flush to DB and catch race conditions
    try:
        async with session.begin_nested():
            session.add(new_notification)
            await session.flush()
    except IntegrityError:
        # Race condition: another run inserted this notification at the same time
        logger.warning(
            "notification_duplicate_race",
            user_id=user.id,
            job_id=job.id,
            search_run_id=search_run_id
        )
        return None

    if status == NotificationStatus.SENT:
        # Plug real channel here later
        logger.info(
            "notification_recorded",
            user_id=user.id,
            job_id=job.id,
            score=match_score,
            search_run_id=search_run_id
        )

    return new_notification
