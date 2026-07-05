"""
Pydantic request/response schemas for the Job Collection API.

These models define the shape of data going in and out of
the /api/v1/jobs endpoints.  They are intentionally separate
from the domain models in app.models so the API surface
can evolve independently of the database layer.
"""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from app.models import JobTable
from app.services.job_collection_service import CollectionResult


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class CollectRequest(BaseModel):
    """Body for POST /jobs/collect — which sources to pull from."""

    sources: list[str] = Field(
        default=["fixture"],
        description="List of source names to collect from (e.g. ['fixture', 'wuzzuf']).",
    )


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class SourceResultOut(BaseModel):
    """Per-source outcome inside a CollectResponse."""

    source: str
    fetched: int
    inserted: int
    duplicates: int
    errors: int

    @classmethod
    def from_result(cls, r: CollectionResult) -> "SourceResultOut":
        """Build from the service-layer dataclass."""
        return cls(
            source=r.source,
            fetched=r.fetched,
            inserted=r.inserted,
            duplicates=r.duplicates,
            errors=r.errors,
        )


class CollectResponse(BaseModel):
    """Aggregated response for a collection run."""

    results: list[SourceResultOut]
    total_inserted: int
    total_duplicates: int
    total_errors: int


class JobOut(BaseModel):
    """Public representation of a stored job posting."""

    id: int
    title: str
    company: str
    location: str
    description: str
    required_skills: list[str]
    experience_level: str
    source: str
    posted_date: Optional[str] = None
    url: Optional[str] = None

    # Structured fields captured at ingestion.
    country_code: Optional[str] = None
    city: Optional[str] = None
    area: Optional[str] = None
    work_mode: Optional[str] = None
    job_types: list[str] = Field(default_factory=list)
    work_roles: list[str] = Field(default_factory=list)
    career_level_raw: Optional[str] = None
    exp_years_min: Optional[int] = None
    exp_years_max: Optional[int] = None

    # Salary — raw values + currency.
    salary_min: Optional[Decimal] = None
    salary_max: Optional[Decimal] = None
    salary_currency: Optional[str] = None
    salary_period: Optional[str] = None
    salary_hidden: bool = False

    @classmethod
    def from_row(cls, row: JobTable) -> "JobOut":
        """Build from a JobTable database row."""
        return cls(
            id=row.id or 0,
            title=row.title,
            company=row.company,
            location=row.location,
            description=row.description,
            required_skills=row.required_skills,
            experience_level=row.experience_level,
            source=row.source,
            posted_date=str(row.posted_date) if row.posted_date else None,
            url=row.url,
            country_code=row.country_code,
            city=row.city,
            area=row.area,
            work_mode=row.work_mode,
            job_types=row.job_types,
            work_roles=row.work_roles,
            career_level_raw=row.career_level_raw,
            exp_years_min=row.exp_years_min,
            exp_years_max=row.exp_years_max,
            salary_min=row.salary_min,
            salary_max=row.salary_max,
            salary_currency=row.salary_currency,
            salary_period=row.salary_period,
            salary_hidden=row.salary_hidden,
        )


class JobListResponse(BaseModel):
    """Paginated list of jobs."""

    jobs: list[JobOut]
    total: int


class SourcesResponse(BaseModel):
    """Available job sources."""

    sources: list[str]
