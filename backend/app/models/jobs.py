"""
Two layers of models live here:

Layer 1 — SQLModel Table Models (SQLModel with table=True)
    These map 1-to-1 to the PostgreSQL database tables.
    They handle JSON serialization/deserialization of list columns.
    Use these when reading/writing to PostgreSQL via SQLModel sessions.

Layer 2 — Pydantic Domain Schemas
    These are the validated business objects used everywhere else
    (LLM extraction, API responses, matching engine).
    Defined in the project brief — kept in sync with the DB models.
"""

import hashlib
from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Any, List, Optional

import structlog
from pgvector.sqlalchemy import Vector
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import CheckConstraint, Column, DateTime, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field as SQLField, Relationship, SQLModel

from app.models.helpers import HIDDEN_COMPANY, WORK_MODES, _normalize_text, _utcnow
from app.core.embeddings import EMBEDDING_DIM

logger = structlog.get_logger()

# =============================================================================
# LAYER 1: SQLModel Table Classes
# =============================================================================

class UserTable(SQLModel, table=True):
    """
    Maps to the `users` table in PostgreSQL.
    List fields are stored as JSON strings in TEXT columns.
    """
    __tablename__ = "users"

    id: Optional[int] = SQLField(default=None, primary_key=True)
    name: str
    email: Optional[str] = SQLField(default=None, unique=True)
    years_of_experience: int = SQLField(default=0)
    career_level: str
    education: Optional[str] = SQLField(default=None)
    preferred_location: Optional[str] = SQLField(default=None)

    # List fields — stored natively as JSONB; read back as Python lists.
    # Facts (from the CV parser):
    skills: list[str] = SQLField(default_factory=list, sa_column=Column(JSONB, nullable=False))
    tools: list[str] = SQLField(default_factory=list, sa_column=Column(JSONB, nullable=False))
    # Preferences (user-supplied via the profile endpoint, NOT CV-parsed):
    desired_roles: list[str] = SQLField(default_factory=list, sa_column=Column(JSONB, nullable=False))
    job_titles: list[str] = SQLField(default_factory=list, sa_column=Column(JSONB, nullable=False))
    workplace_settings: list[str] = SQLField(default_factory=list, sa_column=Column(JSONB, nullable=False))
    job_categories: list[str] = SQLField(default_factory=list, sa_column=Column(JSONB, nullable=False))
    completed_courses: list[str] = SQLField(default_factory=list, sa_column=Column(JSONB, nullable=False))
    projects: list[str] = SQLField(default_factory=list, sa_column=Column(JSONB, nullable=False))
    certifications: list[str] = SQLField(default_factory=list, sa_column=Column(JSONB, nullable=False))
    # NOTE: "missing skills" is a per-(user, job) result — it lives on
    # JobMatchTable.missing_skills, not here.

    created_at: datetime = SQLField(default_factory=_utcnow, sa_type=DateTime(timezone=True))
    updated_at: datetime = SQLField(default_factory=_utcnow, sa_type=DateTime(timezone=True))

    # Relationships
    job_matches: List["JobMatchTable"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"passive_deletes": True},
    )
    logs: List["LogTable"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"passive_deletes": True},
    )


class JobTable(SQLModel, table=True):
    """
    Maps to the `jobs` table in PostgreSQL.

    Deduplication prefers the source's stable `external_id`
    (UNIQUE(source, external_id)); `content_hash` is the fallback for sources
    that lack one (e.g. fixtures).
    """
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_jobs_source_external_id"),
        CheckConstraint(
            "work_mode IS NULL OR work_mode IN ('on_site', 'remote', 'hybrid')",
            name="ck_jobs_work_mode",
        ),
    )

    id: Optional[int] = SQLField(default=None, primary_key=True)
    # Stable per-posting id from the source (Wuzzuf UUID). Primary dedup key.
    external_id: Optional[str] = SQLField(default=None, index=True)
    title: str
    company: str
    description: str
    experience_level: str                       # "junior" | "mid" | "senior"
    source: str                                 # "wuzzuf" | "bayt" | "linkedin" | "other"

    # --- Location (split from the old "City, Country" string) ----------------
    location: str = SQLField(default="Cairo")    # human-readable, kept for display
    country_code: Optional[str] = SQLField(default=None, index=True)   # "EG","SA","QA","AE"
    city: Optional[str] = SQLField(default=None)
    area: Optional[str] = SQLField(default=None)

    # --- Structured classification (from the Wuzzuf detail payload) ----------
    work_mode: Optional[str] = SQLField(default=None, index=True)      # on_site|remote|hybrid
    career_level_raw: Optional[str] = SQLField(default=None)           # "Experienced", etc.
    exp_years_min: Optional[int] = SQLField(default=None)
    exp_years_max: Optional[int] = SQLField(default=None)
    language: Optional[str] = SQLField(default=None)

    # --- Salary (raw values + currency; never inferred from country) ---------
    salary_min: Optional[Decimal] = SQLField(default=None, sa_column=Column(Numeric(12, 2)))
    salary_max: Optional[Decimal] = SQLField(default=None, sa_column=Column(Numeric(12, 2)))
    salary_currency: Optional[str] = SQLField(default=None)            # "EGP","USD","SAR",...
    salary_period: Optional[str] = SQLField(default=None)              # "Per Month","Per Hour"
    salary_hidden: bool = SQLField(default=False)
    salary_details: Optional[str] = SQLField(default=None)

    # --- List/JSONB fields (queryable, GIN-indexable) ------------------------
    # Canonical lowercase skill cache for the matching engine; the normalized
    # source of truth is the skills/job_skills tables.
    required_skills: list[str] = SQLField(default_factory=list, sa_column=Column(JSONB, nullable=False))
    job_types: list[str] = SQLField(default_factory=list, sa_column=Column(JSONB, nullable=False))
    work_roles: list[str] = SQLField(default_factory=list, sa_column=Column(JSONB, nullable=False))
    keywords_raw: list[str] = SQLField(default_factory=list, sa_column=Column(JSONB, nullable=False))
    # Raw source attributes — lets us backfill new fields without re-scraping.
    raw_payload: Optional[dict[str, Any]] = SQLField(
        default=None, sa_column=Column(JSONB, nullable=True)
    )

    posted_date: Optional[date] = SQLField(default=None)
    posted_at: Optional[datetime] = SQLField(default=None, sa_type=DateTime(timezone=True))
    expires_at: Optional[datetime] = SQLField(default=None, sa_type=DateTime(timezone=True))
    url: Optional[str] = SQLField(default=None)
    content_hash: Optional[str] = SQLField(default=None, unique=True)

    # Nullable until Sprint 3 — populated by the semantic search pipeline.
    embedding: Optional[list[float]] = SQLField(
        default=None, sa_column=Column(Vector(EMBEDDING_DIM), nullable=True)
    )

    # Audit — PostgreSQL TIMESTAMPTZ
    created_at: datetime = SQLField(default_factory=_utcnow, sa_type=DateTime(timezone=True))
    updated_at: datetime = SQLField(default_factory=_utcnow, sa_type=DateTime(timezone=True))

    # Relationships
    job_matches: List["JobMatchTable"] = Relationship(
        back_populates="job",
        sa_relationship_kwargs={"passive_deletes": True},
    )
    logs: List["LogTable"] = Relationship(
        back_populates="job",
        sa_relationship_kwargs={"passive_deletes": True},
    )


class SkillTable(SQLModel, table=True):
    """
    Canonical skill dictionary — one row per unique lowercase skill token.
    Populated at ingestion via the skills canonicalizer; the normalized source
    of truth behind `jobs.required_skills` (which is a denormalized cache).
    """
    __tablename__ = "skills"

    id: Optional[int] = SQLField(default=None, primary_key=True)
    name: str = SQLField(unique=True, index=True)


class JobSkillLink(SQLModel, table=True):
    """Many-to-many link between `jobs` and `skills` (composite primary key)."""
    __tablename__ = "job_skills"

    job_id: int = SQLField(foreign_key="jobs.id", ondelete="CASCADE", primary_key=True)
    skill_id: int = SQLField(foreign_key="skills.id", ondelete="CASCADE", primary_key=True)


class JobMatchTable(SQLModel, table=True):
    """
    Maps to the `job_matches` table in PostgreSQL.
    One row per (user_id, job_id) pair — enforced by a UNIQUE constraint.
    """
    __tablename__ = "job_matches"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_job_matches_user_job"),
    )

    id: Optional[int] = SQLField(default=None, primary_key=True)
    user_id: int = SQLField(foreign_key="users.id", ondelete="CASCADE")
    job_id: int = SQLField(foreign_key="jobs.id", ondelete="CASCADE")
    match_score: int = SQLField(ge=0, le=100)

    match_explanation: str = SQLField(default="")
    missing_skills: list[str] = SQLField(default_factory=list, sa_column=Column(JSONB, nullable=False))
    strengths: list[str] = SQLField(default_factory=list, sa_column=Column(JSONB, nullable=False))
    cv_tailoring_suggestion: str = SQLField(default="")
    cover_letter_draft: Optional[str] = SQLField(default=None)


    created_at: datetime = SQLField(default_factory=_utcnow, sa_type=DateTime(timezone=True))
    updated_at: datetime = SQLField(default_factory=_utcnow, sa_type=DateTime(timezone=True))
    reviewed_at: Optional[datetime] = SQLField(default=None, sa_type=DateTime(timezone=True))

    # Relationships
    user: Optional[UserTable] = Relationship(back_populates="job_matches")
    job: Optional[JobTable] = Relationship(back_populates="job_matches")


class LogTable(SQLModel, table=True):
    """
    Maps to the `logs` table in PostgreSQL.
    Append-only — rows are never updated after insert.
    """
    __tablename__ = "logs"

    id: Optional[int] = SQLField(default=None, primary_key=True)
    stage: str      # "cv_parse" | "profile_extract" | "job_ingest" | "matching" | "cover_letter" | "error"
    status: str     # "started" | "success" | "failure"

    user_id: Optional[int] = SQLField(default=None, foreign_key="users.id")
    job_id: Optional[int] = SQLField(default=None, foreign_key="jobs.id")
    message: Optional[str] = SQLField(default=None)
    # JSON blob stored natively as JSONB in the column named "metadata".
    log_metadata: Optional[dict[str, Any]] = SQLField(
        default=None, sa_column=Column("metadata", JSONB, nullable=True)
    )

    # Append-only — PostgreSQL TIMESTAMPTZ
    created_at: datetime = SQLField(default_factory=_utcnow, sa_type=DateTime(timezone=True))

    # Relationships
    user: Optional[UserTable] = Relationship(back_populates="logs")
    job: Optional[JobTable] = Relationship(back_populates="logs")


# =============================================================================
# LAYER 2: Pydantic Domain Schemas
# =============================================================================

class UserProfile(BaseModel):
    """
    Validated career profile — the central object in the system.
    Built from CV text by the LLM extraction pipeline (Sprint 1).
    Stored in the `users` table and passed to the matching engine (Sprint 3).
    """
    # Basic info
    name: str
    email: Optional[str] = None

    # Experience
    years_of_experience: int = Field(ge=0, le=50)
    career_level: str        # "junior" | "mid" | "senior"
    education: Optional[str] = None

    # Skills — factual, extracted from the CV
    skills: list[str]           = Field(default_factory=list)
    tools: list[str]            = Field(default_factory=list)

    # Location as stated on the CV (a preference the user can later override via
    # the profile endpoint).
    preferred_location: Optional[str] = None

    # Sprints.ai-specific signals
    completed_courses: list[str]    = Field(default_factory=list)
    projects: list[str]             = Field(default_factory=list)
    certifications: list[str]       = Field(default_factory=list)

    # NOTE: intent/preference fields (desired_roles, job_titles,
    # workplace_settings, job_categories) are NOT part of the CV-parse contract —
    # they are set by the user via the profile endpoint, not inferred from a CV.

    @field_validator("career_level")
    @classmethod
    def validate_career_level(cls, v: str) -> str:
        """Ensure career_level is one of the three allowed values."""
        allowed = {"junior", "mid", "senior"}
        if v.lower() not in allowed:
            raise ValueError(f"career_level must be one of {allowed}, got '{v}'")
        return v.lower()

    def to_user_table(self) -> UserTable:
        """Convert this validated profile into a UserTable ready for DB insert."""
        # Preference fields (desired_roles, job_titles, workplace_settings,
        # job_categories) are intentionally left at their UserTable defaults ([]) —
        # they are user-supplied via the profile endpoint, not parsed from the CV.
        return UserTable(
            name=self.name,
            email=self.email,
            years_of_experience=self.years_of_experience,
            career_level=self.career_level,
            education=self.education,
            skills=self.skills,
            tools=self.tools,
            preferred_location=self.preferred_location,
            completed_courses=self.completed_courses,
            projects=self.projects,
            certifications=self.certifications,
        )


class JobPosting(BaseModel):
    """
    Normalized job posting schema.
    Populated by the job ingestion pipeline (Sprint 2).
    Stored in the `jobs` table and used as input for matching (Sprint 3).
    """
    title: str
    company: str
    location: str
    description: str
    required_skills: list[str]  = Field(default_factory=list)
    experience_level: str       # "junior" | "mid" | "senior"
    source: str                 # "wuzzuf" | "bayt" | "linkedin" | "other"
    posted_date: Optional[date] = None
    url: Optional[str]          = None

    # Stable per-posting id from the source (Wuzzuf UUID) — primary dedup key.
    external_id: Optional[str] = None

    # Location, split out of the old "City, Country" string.
    country_code: Optional[str] = None
    city: Optional[str] = None
    area: Optional[str] = None

    # Structured classification.
    work_mode: Optional[str] = None             # "on_site" | "remote" | "hybrid"
    job_types: list[str] = Field(default_factory=list)
    work_roles: list[str] = Field(default_factory=list)
    career_level_raw: Optional[str] = None
    exp_years_min: Optional[int] = None
    exp_years_max: Optional[int] = None
    language: Optional[str] = None

    # Salary — raw values + currency, never inferred from country.
    salary_min: Optional[Decimal] = None
    salary_max: Optional[Decimal] = None
    salary_currency: Optional[str] = None
    salary_period: Optional[str] = None
    salary_hidden: bool = False
    salary_details: Optional[str] = None

    # Provenance.
    keywords_raw: list[str] = Field(default_factory=list)
    posted_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    raw_payload: Optional[dict[str, Any]] = None

    @field_validator("work_mode")
    @classmethod
    def validate_work_mode(cls, v: Optional[str]) -> Optional[str]:
        """Accept only the three Wuzzuf work-arrangement values (or None)."""
        if v is None:
            return None
        if v not in WORK_MODES:
            raise ValueError(f"work_mode must be one of {WORK_MODES}, got '{v}'")
        return v

    @field_validator("posted_date", mode="before")
    @classmethod
    def parse_posted_date(cls, v) -> Optional[date]:
        """
        Accept string input ("2025-06-01") from CSV/JSON sources
        and convert to a Python date object for PostgreSQL DATE column.
        Returns None if blank or unparseable — never raises.
        """
        if v is None or v == "":
            return None
        if isinstance(v, date):
            return v
        try:
            return date.fromisoformat(str(v).strip())
        except ValueError:
            logger.warning("job_posted_date_unparseable", value=str(v))
            return None

    @field_validator("experience_level")
    @classmethod
    def validate_experience_level(cls, v: str) -> str:
        """Ensure experience_level is one of the three allowed values."""
        allowed = {"junior", "mid", "senior"}
        if v.lower() not in allowed:
            raise ValueError(f"experience_level must be one of {allowed}, got '{v}'")
        return v.lower()

    @field_validator("source")
    @classmethod
    def validate_source(cls, v: str) -> str:
        """Ensure source is a known data provider."""
        allowed = {"wuzzuf", "bayt", "linkedin", "other"}
        if v.lower() not in allowed:
            raise ValueError(f"source must be one of {allowed}, got '{v}'")
        return v.lower()

    def compute_content_hash(self) -> str:
        """SHA-256 fingerprint used for deduplication.

        Single source of truth — both to_job_table() and the deduplication
        service call this so the recipe can never drift out of sync.

        Recipe:
            known company:  title | company | posted_date
            hidden company: title |         | posted_date | url

        When the company is hidden (normalized to ``HIDDEN_COMPANY`` by every
        source), it carries no identifying signal: distinct postings would
        collide and get silently dropped. So we drop the company and fall back
        to the URL — which carries a stable, per-posting id — as the
        discriminator instead.
        """
        company = _normalize_text(self.company)
        posted = str(self.posted_date) if self.posted_date else ""
        parts = [_normalize_text(self.title), company, posted]
        if company == HIDDEN_COMPANY:
            parts[1] = ""
            parts.append(_normalize_text(self.url) if self.url else "")
        raw = "|".join(parts)
        return hashlib.sha256(raw.encode()).hexdigest()

    def to_job_table(self) -> JobTable:
        """Convert this validated posting into a JobTable ready for DB insert.

        Skill links (`job_skills`) are created separately by the persistence
        layer, which needs a session to get-or-create `SkillTable` rows.

        ``content_hash`` is only populated when the posting has no
        ``external_id``. When a stable source id exists, ``(source,
        external_id)`` is the sole dedup discriminator (see the deduplication
        service), so a ``content_hash`` — a mere ``title | company |
        posted_date`` fingerprint — is redundant *and* actively harmful: two
        genuinely distinct postings of the same role (e.g. a company listing it
        as both an internship and a full role on the same day) share that
        fingerprint and would trip the ``UNIQUE(content_hash)`` constraint,
        aborting the whole insert batch. Leaving it ``NULL`` lets such postings
        coexist (Postgres treats NULLs as distinct under a UNIQUE constraint)
        while ``(source, external_id)`` still prevents true re-scrape dupes.
        """
        return JobTable(
            title=self.title,
            company=self.company,
            location=self.location,
            description=self.description,
            required_skills=self.required_skills,
            experience_level=self.experience_level,
            source=self.source,
            posted_date=self.posted_date,
            url=self.url,
            content_hash=self.compute_content_hash() if not self.external_id else None,
            external_id=self.external_id,
            country_code=self.country_code,
            city=self.city,
            area=self.area,
            work_mode=self.work_mode,
            job_types=self.job_types,
            work_roles=self.work_roles,
            career_level_raw=self.career_level_raw,
            exp_years_min=self.exp_years_min,
            exp_years_max=self.exp_years_max,
            language=self.language,
            salary_min=self.salary_min,
            salary_max=self.salary_max,
            salary_currency=self.salary_currency,
            salary_period=self.salary_period,
            salary_hidden=self.salary_hidden,
            salary_details=self.salary_details,
            keywords_raw=self.keywords_raw,
            posted_at=self.posted_at,
            expires_at=self.expires_at,
            raw_payload=self.raw_payload,
        )


class JobMatch(BaseModel):
    """
    AI-generated match result between a UserProfile and a JobPosting.
    Stored in the `job_matches` table.
    """
    job: JobPosting
    match_score: int = Field(ge=0, le=100)
    match_explanation: str
    missing_skills: list[str]   = Field(default_factory=list)
    cv_tailoring_suggestion: str = ""
    cover_letter_draft: Optional[str] = None

    @field_validator("match_score")
    @classmethod
    def validate_score(cls, v: int) -> int:
        """Guard against LLM hallucinating scores outside 0-100."""
        if not (0 <= v <= 100):
            raise ValueError(f"match_score must be 0–100, got {v}")
        return v
