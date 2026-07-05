"""
Pydantic request/response schemas for the Job Tracking & Market Trends API.

Kept separate from the SQLModel table classes in ``app/models/job_tracking.py``
so the API surface can evolve independently of the database layer — the same
split the job-collection feature uses (``app/schemas/jobs.py``).

All response schemas set ``ConfigDict(from_attributes=True)`` so they can be
built directly from ORM rows and from the service-layer dataclasses with
``.model_validate(obj)``.
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.job_tracking import TrackingStatus


# ---------------------------------------------------------------------------
# Job tracking — requests
# ---------------------------------------------------------------------------


class TrackJobRequest(BaseModel):
    """Body for recording/updating a job's status in a user's pipeline.

    This app has no auth layer yet (consistent with the existing job endpoints),
    so the acting user is supplied explicitly.
    """

    user_id: int = Field(description="The user whose pipeline is being updated.")
    status: TrackingStatus = Field(
        default=TrackingStatus.REVIEWED,
        description="Target pipeline state. Defaults to 'reviewed' (job opened).",
    )


# ---------------------------------------------------------------------------
# Job tracking — responses
# ---------------------------------------------------------------------------


class JobTrackingOut(BaseModel):
    """Current tracking state for one ``(user_id, job_id)`` pair."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    job_id: int
    status: TrackingStatus
    created_at: datetime
    updated_at: datetime


class JobTrackingListOut(BaseModel):
    """A user's tracked jobs."""

    items: list[JobTrackingOut]
    total: int


class TrackingEventOut(BaseModel):
    """One immutable transition from the append-only audit log."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    job_id: int
    from_status: Optional[TrackingStatus] = None
    to_status: TrackingStatus
    created_at: datetime


class TrackingHistoryOut(BaseModel):
    """The full transition history for one ``(user_id, job_id)`` pair."""

    job_id: int
    user_id: int
    events: list[TrackingEventOut]


# ---------------------------------------------------------------------------
# Market trends — responses
# ---------------------------------------------------------------------------


class LabeledCountOut(BaseModel):
    """A generic ``(label, count)`` bucket used by most trend metrics."""

    model_config = ConfigDict(from_attributes=True)

    label: str
    count: int


class PostingVolumePointOut(BaseModel):
    """A single point on the posting-volume-over-time series."""

    model_config = ConfigDict(from_attributes=True)

    period: date
    count: int


class SalaryStatOut(BaseModel):
    """Salary aggregates for one currency+period group (visible salaries only)."""

    model_config = ConfigDict(from_attributes=True)

    currency: str
    period: Optional[str] = None
    count: int
    min: float
    max: float
    avg: float


class MarketTrendsOut(BaseModel):
    """Combined market-intelligence overview returned by ``GET /trends``."""

    top_companies: list[LabeledCountOut]
    experience_levels: list[LabeledCountOut]
    work_types: list[LabeledCountOut]
    top_categories: list[LabeledCountOut]
    countries: list[LabeledCountOut]
    job_types: list[LabeledCountOut]
    posting_volume: list[PostingVolumePointOut]
    top_skills: list[LabeledCountOut]
    salary_stats: list[SalaryStatOut]
