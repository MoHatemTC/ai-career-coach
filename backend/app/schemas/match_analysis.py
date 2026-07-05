"""LLM structured-output schema for the match service.

Maps 1:1 onto the columns of ``JobMatchTable`` (``app/models/jobs.py``) so the
service can persist the result directly via the canonical upsert.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class MatchAnalysis(BaseModel):
    """AI gap-analysis result for a (user, job) pair.

    WARNING: entirely AI-generated. Requires human review before use.
    """

    match_score: int = Field(..., ge=0, le=100, description="Overall fit, 0-100")
    match_explanation: str = Field(..., description="Why the candidate matches (or not)")
    missing_skills: list[str] = Field(
        default_factory=list, description="Required skills/tools the candidate lacks"
    )
    strengths: list[str] = Field(
        default_factory=list, description="Aspects of the candidate's profile that align well with this job"
    )
    cv_tailoring_suggestion: str = Field(
        default="", description="Actionable CV-tailoring advice for this job"
    )
    cover_letter_draft: str | None = Field(
        default=None, description="Cover letter draft, or null if not enough info"
    )


class JobMatchOut(BaseModel):
    """Persisted `job_matches` row returned by POST /matches/analyze."""

    id: int
    user_id: int
    job_id: int
    match_score: int
    match_explanation: str
    missing_skills: list[str]
    strengths: list[str]
    cv_tailoring_suggestion: str
    cover_letter_draft: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
