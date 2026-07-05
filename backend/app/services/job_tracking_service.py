"""
Job tracking service — the personal-pipeline state machine.

Responsibilities:
  1. Record/transition the current state of a ``(user_id, job_id)`` pair in the
     ``job_tracking`` table (one row per pair, upserted in place).
  2. Append one immutable row to ``job_tracking_events`` for every *real*
     transition — the audit trail of how a job moved through the pipeline.

State machine
-------------
The pipeline is **permissive and user-driven**: any state may transition to any
other state (a user can re-save, un-shortlist, re-open, etc.). The single
invariant is idempotency — receiving the *same* status the pair already holds is
a **no-op**: no row update and, crucially, no duplicate event is logged.

Contract
--------
Like the rest of the pipeline (see ``job_collection_service`` / ``log_service``),
these functions only ``add``/``flush`` within the caller's session — the caller
owns the final ``commit`` / ``rollback``.
"""

from typing import Optional

import structlog
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import JobTable, _utcnow
from app.models.job_tracking import (
    JobTrackingEventTable,
    JobTrackingTable,
    TrackingStatus,
)

logger = structlog.get_logger()


class JobNotFoundError(LookupError):
    """Raised when tracking is requested for a job id that does not exist."""


class TrackingNotFoundError(LookupError):
    """Raised when a ``(user_id, job_id)`` pair has no tracking row yet."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _job_exists(session: AsyncSession, job_id: int) -> bool:
    """True if a row with ``job_id`` exists in the ``jobs`` table."""
    found = (
        await session.exec(select(JobTable.id).where(JobTable.id == job_id))
    ).first()
    return found is not None


async def _get_tracking_row(
    session: AsyncSession, *, user_id: int, job_id: int
) -> Optional[JobTrackingTable]:
    """Return the tracking row for a pair, or ``None`` if untracked."""
    stmt = select(JobTrackingTable).where(
        JobTrackingTable.user_id == user_id,
        JobTrackingTable.job_id == job_id,
    )
    return (await session.exec(stmt)).first()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def track_job(
    session: AsyncSession,
    *,
    user_id: int,
    job_id: int,
    status: TrackingStatus = TrackingStatus.REVIEWED,
) -> JobTrackingTable:
    """Record or transition the status of a job in a user's pipeline.

    Behaviour:
        * Job must exist — otherwise ``JobNotFoundError`` is raised.
        * First contact (no existing row) → create the tracking row and write a
          ``from_status=None`` event.
        * Existing row, **same status** → no-op: the row is returned unchanged
          and **no event is logged** (silent duplicate handling).
        * Existing row, different status → update the row's status/``updated_at``
          and write an event recording ``from_status`` → ``to_status``.

    The row is ``flush``ed so its generated id is available, but not committed —
    the caller owns the transaction.

    Returns:
        The current (created or updated) ``JobTrackingTable`` row.
    """
    if not await _job_exists(session, job_id):
        raise JobNotFoundError(f"job {job_id} does not exist")

    row = await _get_tracking_row(session, user_id=user_id, job_id=job_id)

    # --- First contact: create the tracking row + opening event --------------
    if row is None:
        row = JobTrackingTable(user_id=user_id, job_id=job_id, status=status)
        session.add(row)
        session.add(
            JobTrackingEventTable(
                user_id=user_id,
                job_id=job_id,
                from_status=None,
                to_status=status,
            )
        )
        await session.flush()
        logger.info(
            "job_tracking_created",
            user_id=user_id,
            job_id=job_id,
            status=status.value,
        )
        return row

    # --- Duplicate transition: silently ignore -------------------------------
    if row.status == status:
        logger.info(
            "job_tracking_noop_duplicate",
            user_id=user_id,
            job_id=job_id,
            status=status.value,
        )
        return row

    # --- Real transition: update row + append event --------------------------
    previous = row.status
    row.status = status
    row.updated_at = _utcnow()
    session.add(row)
    session.add(
        JobTrackingEventTable(
            user_id=user_id,
            job_id=job_id,
            from_status=previous,
            to_status=status,
        )
    )
    await session.flush()
    logger.info(
        "job_tracking_transitioned",
        user_id=user_id,
        job_id=job_id,
        from_status=previous.value,
        to_status=status.value,
    )
    return row


async def get_tracking(
    session: AsyncSession, *, user_id: int, job_id: int
) -> JobTrackingTable:
    """Return the current tracking row for a pair.

    Raises:
        TrackingNotFoundError: if the pair has never been tracked.
    """
    row = await _get_tracking_row(session, user_id=user_id, job_id=job_id)
    if row is None:
        raise TrackingNotFoundError(
            f"job {job_id} is not tracked by user {user_id}"
        )
    return row


async def list_tracked_jobs(
    session: AsyncSession,
    *,
    user_id: int,
    status: Optional[TrackingStatus] = None,
) -> list[JobTrackingTable]:
    """List a user's tracked jobs, newest-updated first, optionally filtered."""
    stmt = select(JobTrackingTable).where(JobTrackingTable.user_id == user_id)
    if status is not None:
        stmt = stmt.where(JobTrackingTable.status == status)
    stmt = stmt.order_by(JobTrackingTable.updated_at.desc())  # type: ignore[union-attr]
    return list((await session.exec(stmt)).all())


async def get_tracking_history(
    session: AsyncSession, *, user_id: int, job_id: int
) -> list[JobTrackingEventTable]:
    """Return the append-only transition history for a pair, oldest first.

    Raises:
        TrackingNotFoundError: if the pair has never been tracked (so there is
        no history to return).
    """
    # Confirm the pair is tracked so callers can return a clean 404 rather than
    # an empty list that is ambiguous with "tracked but somehow no events".
    await get_tracking(session, user_id=user_id, job_id=job_id)

    stmt = (
        select(JobTrackingEventTable)
        .where(
            JobTrackingEventTable.user_id == user_id,
            JobTrackingEventTable.job_id == job_id,
        )
        .order_by(JobTrackingEventTable.created_at.asc(), JobTrackingEventTable.id.asc())  # type: ignore[union-attr]
    )
    return list((await session.exec(stmt)).all())


# ---------------------------------------------------------------------------
# Application materials — generated on entry to SHORTLISTED (see docs/features)
# ---------------------------------------------------------------------------
#
# Rationale: users apply *externally*, then log the outcome here. CV tailoring and
# a cover-letter draft are only useful *before* applying — so materials are
# generated when a job first enters SHORTLISTED ("seriously considering"), not at
# APPLIED (too late). Generation runs in a FastAPI BackgroundTask *after* the
# tracking commit, so the HTTP response is not blocked by LLM calls.


def should_generate_materials(
    *, previous_status: Optional[TrackingStatus], new_status: TrackingStatus
) -> bool:
    """True only on the *first* entry into SHORTLISTED.

    Re-entering SHORTLISTED from a later state does not re-trigger here; the task
    itself also skips if materials already exist, so regeneration never happens
    implicitly (use an explicit endpoint for that).
    """
    return (
        new_status == TrackingStatus.SHORTLISTED
        and previous_status != TrackingStatus.SHORTLISTED
    )


async def generate_application_materials_task(user_id: int, job_id: int) -> None:
    """Background task: generate CV tailoring + cover letter and persist them.

    Opens its own DB session (the request-scoped session is already closed by the
    time this runs), is idempotent (skips if materials already exist), and audits
    the ``cover_letter`` stage. Never raises — failures are logged.
    """
    # Lazy imports avoid a heavy/circular import chain at module load.
    from sqlmodel.ext.asyncio.session import AsyncSession as _AsyncSession

    from app.db.connection import engine
    from app.models.jobs import JobMatchTable, JobTable, UserTable
    from app.schemas.application_ai import ApplicationRequest
    from app.schemas.matching import CandidateProfile
    from app.services.application_ai_service import ApplicationAIService
    from app.services.log_service import write_log
    from app.services.match_service import upsert_job_match

    async with _AsyncSession(engine, expire_on_commit=False) as session:
        try:
            # Idempotency: skip if materials already exist for this pair.
            existing = (
                await session.exec(
                    select(JobMatchTable).where(
                        JobMatchTable.user_id == user_id,
                        JobMatchTable.job_id == job_id,
                    )
                )
            ).first()
            if existing and existing.cv_tailoring_suggestion:
                logger.info(
                    "application_materials_skip_exists",
                    user_id=user_id,
                    job_id=job_id,
                )
                return

            user = await session.get(UserTable, user_id)
            job = await session.get(JobTable, job_id)
            if not user or not job:
                return

            candidate_profile = CandidateProfile.from_user(user)
            req = ApplicationRequest(
                candidate_id=user_id,
                job_id=job_id,
                candidate_profile=candidate_profile,
                job_description=job.description,
            )

            await write_log(
                session,
                stage="cover_letter",
                status="started",
                user_id=user_id,
                job_id=job_id,
            )
            res = await ApplicationAIService(session=session).generate_application_materials(req)

            await upsert_job_match(
                session,
                user_id=user_id,
                job_id=job_id,
                cv_tailoring_suggestion=(
                    res.cv_tailoring.model_dump_json() if res.cv_tailoring else ""
                ),
                cover_letter_draft=(
                    res.cover_letter.model_dump_json() if res.cover_letter else None
                ),
            )
            await write_log(
                session,
                stage="cover_letter",
                status="success",
                user_id=user_id,
                job_id=job_id,
            )
            await session.commit()
            logger.info(
                "application_materials_generated", user_id=user_id, job_id=job_id
            )
        except Exception as e:  # noqa: BLE001 — background task must not crash
            logger.error(
                "application_materials_failed",
                user_id=user_id,
                job_id=job_id,
                error=str(e),
            )
            try:
                await write_log(
                    session,
                    stage="error",
                    status="failure",
                    message=str(e),
                    user_id=user_id,
                    job_id=job_id,
                    metadata={"stage": "cover_letter"},
                )
                await session.commit()
            except Exception:
                pass
