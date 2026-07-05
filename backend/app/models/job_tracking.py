"""
SQLModel table classes for **job tracking** (Sprint 3, Task 9).

Two tables live here, mirroring the conventions in ``app/models/jobs.py``
(JSONB list columns, ``_utcnow`` TIMESTAMPTZ defaults, CASCADE foreign keys):

``job_tracking``
    The *current* state of each ``(user_id, job_id)`` pair in a user's personal
    pipeline. Exactly one row per pair — enforced by a UNIQUE constraint, the
    same pattern ``job_matches`` uses.

``job_tracking_events``
    An *append-only* audit log: one row per real state transition, written every
    time the status actually changes. Rows are never updated or deleted by the
    application — the same immutable-event-log intent as ``LogTable``.

The six pipeline states are modelled by ``TrackingStatus``; ``reviewed`` is the
default entry state (the user opened the job).
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, UniqueConstraint
from sqlmodel import Field as SQLField, SQLModel

# Single source of truth for the UTC TIMESTAMPTZ default — reuse the helper the
# rest of the data layer already uses so the two never drift.
from app.models.helpers import _utcnow


class TrackingStatus(str, Enum):
    """The six states a job can occupy in a user's personal pipeline.

    Stored as a plain string column; the ``str`` mixin means the enum value
    serialises to its name (e.g. ``"saved"``) transparently for JSON and SQL.
    """

    REVIEWED = "reviewed"        # user opened the job — the default entry state
    SAVED = "saved"              # bookmarked for later
    SHORTLISTED = "shortlisted"  # seriously considering applying
    APPLIED = "applied"          # application submitted
    REJECTED = "rejected"        # rejected by company or dropped
    IGNORED = "ignored"          # user dismissed the job as irrelevant


class JobTrackingTable(SQLModel, table=True):
    """
    Maps to the ``job_tracking`` table — the current state per pair.

    One row per ``(user_id, job_id)`` pair, enforced by a UNIQUE constraint at
    the database level (defence in depth alongside the service-layer upsert).
    ``status`` is overwritten in place on each real transition; the history of
    how it got there lives in ``job_tracking_events``.
    """

    __tablename__ = "job_tracking"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_job_tracking_user_job"),
    )

    id: Optional[int] = SQLField(default=None, primary_key=True)
    user_id: int = SQLField(foreign_key="users.id", ondelete="CASCADE", index=True)
    job_id: int = SQLField(foreign_key="jobs.id", ondelete="CASCADE", index=True)

    # Current pipeline state. Stored as TEXT; validated by TrackingStatus in the
    # schema/service layers.
    status: TrackingStatus = SQLField(default=TrackingStatus.REVIEWED)

    created_at: datetime = SQLField(default_factory=_utcnow, sa_type=DateTime(timezone=True))
    updated_at: datetime = SQLField(default_factory=_utcnow, sa_type=DateTime(timezone=True))


class JobTrackingEventTable(SQLModel, table=True):
    """
    Maps to the ``job_tracking_events`` table — the append-only audit log.

    One row is written per *real* status transition. ``from_status`` is NULL for
    the first event (the job had no prior state). Rows are immutable: never
    updated, never deleted by the application.
    """

    __tablename__ = "job_tracking_events"

    id: Optional[int] = SQLField(default=None, primary_key=True)
    user_id: int = SQLField(foreign_key="users.id", ondelete="CASCADE", index=True)
    job_id: int = SQLField(foreign_key="jobs.id", ondelete="CASCADE", index=True)

    # NULL on the first transition (no prior state); otherwise the state we left.
    from_status: Optional[TrackingStatus] = SQLField(default=None)
    to_status: TrackingStatus = SQLField()

    # Append-only — set once on insert, never changed.
    created_at: datetime = SQLField(default_factory=_utcnow, sa_type=DateTime(timezone=True))
