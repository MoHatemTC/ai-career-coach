"""
SQLModel table classes for **notifications** (Sprint 4, Task 13).

Tracks notifications sent to users about job recommendations.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, UniqueConstraint
from sqlmodel import Field as SQLField, SQLModel

from app.models.helpers import _utcnow


class NotificationStatus(str, Enum):
    """The status of a notification."""
    SENT = "sent"          # user had an email on file, notification recorded
    SKIPPED = "skipped"    # user has no email on file — nothing to notify with


class NotificationTable(SQLModel, table=True):
    """
    Records a notification to a user about a specific job match.
    Enforces a unique constraint to prevent duplicate notifications.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_notifications_user_job"),
    )

    id: Optional[int] = SQLField(default=None, primary_key=True)
    user_id: int = SQLField(foreign_key="users.id", ondelete="CASCADE", index=True)
    job_id: int = SQLField(foreign_key="jobs.id", ondelete="CASCADE", index=True)
    match_score: int = SQLField(ge=0, le=100)
    status: NotificationStatus = SQLField(default=NotificationStatus.SENT)
    search_run_id: str = SQLField(index=True)
    created_at: datetime = SQLField(default_factory=_utcnow, sa_type=DateTime(timezone=True))
