"""
Audit log service.

Writes rows to the append-only ``logs`` table (see ``LogTable``). Every
pipeline stage — ``cv_parse``, ``profile_extract``, ``job_ingest``,
``matching``, ``cover_letter``, ``error`` — records a row here so the database
holds a durable, queryable audit trail alongside the console structlog stream.

Contract: like the rest of the pipeline, this only ``session.add()``s the row —
the caller owns the commit/rollback. The row is added to the *outer* transaction
(never a per-source SAVEPOINT) so the audit record survives even when the
job rows it describes are rolled back, matching the ERD's "logs survive" intent.
"""

from typing import Any, Optional

import structlog
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import LogTable

logger = structlog.get_logger()


async def write_log(
    session: AsyncSession,
    *,
    stage: str,
    status: str,
    message: Optional[str] = None,
    user_id: Optional[int] = None,
    job_id: Optional[int] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    """Add one audit row to the ``logs`` table within the caller's session.

    Args:
        session: Active async session — the caller commits or rolls back.
        stage: One of the allowed pipeline stages (e.g. ``"job_ingest"``).
        status: ``"started"`` | ``"success"`` | ``"failure"``.
        message: Optional human-readable description.
        user_id: Optional FK to ``users.id``.
        job_id: Optional FK to ``jobs.id``.
        metadata: Optional JSON blob (counts, latency, model name, etc.).
    """
    session.add(
        LogTable(
            stage=stage,
            status=status,
            message=message,
            user_id=user_id,
            job_id=job_id,
            log_metadata=metadata,
        )
    )
    logger.info(
        "audit_log_written",
        stage=stage,
        status=status,
        user_id=user_id,
        job_id=job_id,
    )
