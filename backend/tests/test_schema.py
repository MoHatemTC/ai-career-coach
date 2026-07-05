"""
Test categories:
  1. Schema creation  — tables exist and have the correct columns (SQLModel metadata)
  2. UserTable CRUD   — insert, fetch, list field serialization
  3. JobTable CRUD    — insert, fetch, deduplication via content_hash
  4. JobMatchTable CRUD — insert, fetch, FK enforcement, score constraint
  5. LogTable         — append-only log behavior
  6. Pydantic models  — field validation and validator edge cases
  7. Cascade deletes  — deleting a user removes their job_matches rows
  8. parse_posted_date validator — string/None/date inputs

All tests use a real PostgreSQL database via the shared ``session`` fixture
in ``tests/conftest.py``. Each test gets a completely fresh schema (tables
created before, dropped after) so there is no state leakage between tests.

Requirements:
  - PostgreSQL must be running (docker compose up -d)
  - TEST_DATABASE_URL env var (or default career_coach_test DB)
"""

from datetime import datetime, date

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select, func

from app.models import (
    JobMatch,
    JobMatchTable,
    JobPosting,
    JobTable,
    LogTable,
    UserProfile,
    UserTable,
)

# =============================================================================
# FIXTURES
# =============================================================================

# The ``session`` fixture is provided by tests/conftest.py


@pytest.fixture()
def sample_user_table() -> UserTable:
    """A valid UserTable representing a junior AI engineer."""
    return UserTable(
        name="Atef Mohamed",
        email="atef@example.com",
        years_of_experience=2,
        career_level="junior",
        education="BSc Computer Science, Cairo University",
        skills=["Python", "LangChain", "Weaviate"],
        desired_roles=["AI Engineer", "ML Engineer"],
        preferred_location="Cairo",
        completed_courses=["LangChain RAG", "Weaviate Search"],
        projects=["Built a RAG pipeline with Weaviate"],
        certifications=["AI Engineering Certificate"],
    )


@pytest.fixture()
def sample_job_table() -> JobTable:
    """A valid JobTable for an AI Engineer position at a Cairo company."""
    posting = JobPosting(
        title="AI Engineer",
        company="LavaLoon",
        location="Cairo, Egypt",
        description="Design, develop, and maintain AI and Machine Learning solutions for internal and client-facing projects.",
        required_skills=["Python", "AI Agents", "FastAPI", "LLM Finetuning"],
        experience_level="senior",
        source="wuzzuf",
        posted_date="2026-06-07",
        url="https://wuzzuf.net/jobs/p/ioh4wrztmipe-senior-ai-engineer-lavaloon-cairo-egypt",
    )
    return posting.to_job_table()


# =============================================================================
# 1. SCHEMA CREATION TESTS
# =============================================================================

class TestSchemaCreation:
    """Verify all tables exist and have the correct columns after schema creation."""

    def test_all_tables_exist(self, session: Session):
        """All four expected tables should be present in the PostgreSQL schema."""
        expected_tables = {"users", "jobs", "job_matches", "logs"}
        from sqlalchemy import inspect
        inspector = inspect(session.get_bind())
        actual_tables = set(inspector.get_table_names())
        assert expected_tables.issubset(actual_tables), (
            f"Missing tables: {expected_tables - actual_tables}"
        )

    def test_users_columns(self, session: Session):
        """users table should have all expected columns."""
        from sqlalchemy import inspect
        inspector = inspect(session.get_bind())
        cols = {c["name"] for c in inspector.get_columns("users")}
        expected = {
            "id", "name", "email", "years_of_experience", "career_level",
            "education", "skills", "desired_roles", "preferred_location",
            "completed_courses", "projects", "certifications",
            "tools", "job_titles", "workplace_settings",
            "job_categories", "created_at", "updated_at",
        }
        assert expected == cols

    def test_jobs_columns(self, session: Session):
        """jobs table should have all expected columns."""
        from sqlalchemy import inspect
        inspector = inspect(session.get_bind())
        cols = {c["name"] for c in inspector.get_columns("jobs")}
        expected = {
            "id", "title", "company", "location", "description",
            "required_skills", "experience_level", "source",
            "posted_date", "url", "content_hash", "created_at", "updated_at",
            "embedding",
            # Structured fields added by the Wuzzuf-enrichment migration.
            "external_id", "country_code", "city", "area", "work_mode",
            "career_level_raw", "exp_years_min", "exp_years_max", "language",
            "salary_min", "salary_max", "salary_currency", "salary_period",
            "salary_hidden", "salary_details", "job_types", "work_roles",
            "keywords_raw", "raw_payload", "posted_at", "expires_at",
        }
        assert expected == cols

    def test_job_matches_columns(self, session: Session):
        """job_matches table should have all expected columns."""
        from sqlalchemy import inspect
        inspector = inspect(session.get_bind())
        cols = {c["name"] for c in inspector.get_columns("job_matches")}
        expected = {
            "id", "user_id", "job_id", "match_score", "match_explanation",
            "missing_skills", "strengths", "cv_tailoring_suggestion",
            "cover_letter_draft", "created_at", "updated_at", "reviewed_at",
        }
        assert expected == cols

    def test_logs_columns(self, session: Session):
        """logs table should have all expected columns."""
        from sqlalchemy import inspect
        inspector = inspect(session.get_bind())
        cols = {c["name"] for c in inspector.get_columns("logs")}
        expected = {
            "id", "stage", "user_id", "job_id", "status",
            "message", "metadata", "created_at",
        }
        assert expected == cols


# =============================================================================
# 2. UserTable TESTS
# =============================================================================

class TestUserTable:
    """Test CRUD operations and JSON serialization for the users table."""

    def test_insert_and_fetch(self, session: Session, sample_user_table: UserTable):
        """Inserting a UserTable and reading it back should round-trip correctly."""
        session.add(sample_user_table)
        session.commit()
        session.refresh(sample_user_table)

        fetched = session.exec(
            select(UserTable).where(UserTable.id == sample_user_table.id)
        ).first()
        assert fetched is not None
        assert fetched.name == sample_user_table.name
        assert fetched.email == sample_user_table.email
        assert fetched.career_level == sample_user_table.career_level
        assert fetched.years_of_experience == sample_user_table.years_of_experience

    def test_skills_roundtrip(self, session: Session, sample_user_table: UserTable):
        """List fields should survive the JSONB round-trip intact as native lists."""
        session.add(sample_user_table)
        session.commit()
        session.refresh(sample_user_table)

        fetched = session.exec(
            select(UserTable).where(UserTable.id == sample_user_table.id)
        ).first()
        assert fetched is not None
        assert fetched.skills == sample_user_table.skills
        assert fetched.completed_courses == sample_user_table.completed_courses
        assert fetched.projects == sample_user_table.projects
        assert fetched.certifications == sample_user_table.certifications

    def test_email_uniqueness(self, session: Session, sample_user_table: UserTable):
        """Inserting two users with the same email should raise an IntegrityError."""
        session.add(sample_user_table)
        session.commit()

        duplicate = UserTable(
            name="Sara Ali",
            email=sample_user_table.email,   # same email
            years_of_experience=3,
            career_level="mid",
        )
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_null_email_is_allowed(self, session: Session):
        """Multiple users with NULL email should not trigger the unique constraint."""
        for name in ("User One", "User Two"):
            row = UserTable(
                name=name, email=None,
                years_of_experience=1, career_level="junior"
            )
            session.add(row)
        session.commit()

        count = session.exec(
            select(func.count()).select_from(UserTable).where(UserTable.email.is_(None))  # type: ignore[union-attr]
        ).one()
        assert count == 2

    def test_empty_lists_default(self, session: Session):
        """Users with no skills/courses should default to empty JSON arrays."""
        row = UserTable(
            name="Minimal User",
            years_of_experience=0,
            career_level="junior",
        )
        session.add(row)
        session.commit()
        session.refresh(row)

        fetched = session.exec(
            select(UserTable).where(UserTable.id == row.id)
        ).first()
        assert fetched is not None
        assert fetched.skills == []
        assert fetched.desired_roles == []

    def test_created_at_is_datetime(self, session: Session, sample_user_table: UserTable):
        """created_at should be a timezone-aware datetime (PostgreSQL TIMESTAMPTZ)."""
        session.add(sample_user_table)
        session.commit()
        session.refresh(sample_user_table)

        fetched = session.exec(
            select(UserTable).where(UserTable.id == sample_user_table.id)
        ).first()
        assert fetched is not None
        assert isinstance(fetched.created_at, datetime)
        assert fetched.created_at.tzinfo is not None

    def test_row_count_after_insert(self, session: Session):
        """Inserting multiple users should be reflected in the row count."""
        for i in range(3):
            session.add(UserTable(
                name=f"User {i}", years_of_experience=i, career_level="junior"
            ))
        session.commit()

        count = session.exec(
            select(func.count()).select_from(UserTable)
        ).one()
        assert count == 3


# =============================================================================
# 3. JobTable TESTS
# =============================================================================

class TestJobTable:
    """Test CRUD operations and deduplication for the jobs table."""

    def test_insert_and_fetch(self, session: Session, sample_job_table: JobTable):
        """Inserting a JobTable and reading it back should round-trip correctly."""
        session.add(sample_job_table)
        session.commit()
        session.refresh(sample_job_table)

        fetched = session.exec(
            select(JobTable).where(JobTable.id == sample_job_table.id)
        ).first()
        assert fetched is not None
        assert fetched.title == sample_job_table.title
        assert fetched.company == sample_job_table.company
        assert fetched.source == sample_job_table.source
        assert fetched.experience_level == sample_job_table.experience_level

    def test_required_skills_roundtrip(self, session: Session, sample_job_table: JobTable):
        """required_skills list should survive the JSONB round-trip."""
        session.add(sample_job_table)
        session.commit()
        session.refresh(sample_job_table)

        fetched = session.exec(
            select(JobTable).where(JobTable.id == sample_job_table.id)
        ).first()
        assert fetched is not None
        assert fetched.required_skills == sample_job_table.required_skills

    def test_content_hash_auto_computed(self):
        """JobPosting.to_job_table() should auto-compute content_hash."""
        posting = JobPosting(
            title="ML Engineer", company="Paymob",
            location="Cairo", description="...", experience_level="mid", source="wuzzuf",
            posted_date="2025-06-02",
        )
        job = posting.to_job_table()
        assert job.content_hash is not None
        assert len(job.content_hash) == 64  # SHA-256 hex digest length

    def test_duplicate_content_hash_rejected(self, session: Session, sample_job_table: JobTable):
        """Inserting the same job twice should raise IntegrityError on content_hash."""
        session.add(sample_job_table)
        session.commit()

        posting2 = JobPosting(
            title=sample_job_table.title,
            company=sample_job_table.company,
            location=sample_job_table.location,
            description=sample_job_table.description,
            required_skills=sample_job_table.required_skills,
            experience_level=sample_job_table.experience_level,
            source=sample_job_table.source,
            posted_date=sample_job_table.posted_date,
            url=sample_job_table.url,
        )
        duplicate = posting2.to_job_table()
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_posted_date_is_date_type(self, session: Session, sample_job_table: JobTable):
        """posted_date should be a Python date object (PostgreSQL DATE column)."""
        session.add(sample_job_table)
        session.commit()
        session.refresh(sample_job_table)

        fetched = session.exec(
            select(JobTable).where(JobTable.id == sample_job_table.id)
        ).first()
        assert fetched is not None
        assert isinstance(fetched.posted_date, date)
        assert fetched.posted_date == date(2026, 6, 7)

    def test_created_at_is_datetime(self, session: Session, sample_job_table: JobTable):
        """created_at should be a timezone-aware datetime (PostgreSQL TIMESTAMPTZ)."""
        session.add(sample_job_table)
        session.commit()
        session.refresh(sample_job_table)

        fetched = session.exec(
            select(JobTable).where(JobTable.id == sample_job_table.id)
        ).first()
        assert fetched is not None
        assert isinstance(fetched.created_at, datetime)
        assert fetched.created_at.tzinfo is not None

    def test_all_jobs_selectable(self, session: Session):
        """All inserted jobs should be retrievable with select(JobTable).all()."""
        for i in range(3):
            posting = JobPosting(
                title=f"Job {i}", company=f"Company {i}",
                location="Cairo", description="desc",
                experience_level="junior", source="wuzzuf",
                posted_date=f"2025-0{i + 1}-01",
            )
            session.add(posting.to_job_table())
        session.commit()

        all_jobs = session.exec(select(JobTable)).all()
        assert len(all_jobs) == 3

    def test_job_count_via_func(self, session: Session):
        """Row count via func.count() should match number of inserts."""
        for i in range(4):
            posting = JobPosting(
                title=f"Count Job {i}", company=f"Co {i}",
                location="Cairo", description="desc",
                experience_level="mid", source="bayt",
                posted_date=f"2025-0{i + 1}-15",
            )
            session.add(posting.to_job_table())
        session.commit()

        count = session.exec(
            select(func.count()).select_from(JobTable)
        ).one()
        assert count == 4


# =============================================================================
# 4. JobMatchTable TESTS
# =============================================================================

class TestJobMatchTable:
    """Test match insertion, FK enforcement, and unique constraint."""

    def _setup(
        self, session: Session, user: UserTable, job: JobTable
    ) -> tuple[int, int]:
        """Insert one user and one job, return their IDs."""
        session.add(user)
        session.add(job)
        session.commit()
        session.refresh(user)
        session.refresh(job)
        assert user.id is not None
        assert job.id is not None
        return user.id, job.id

    def test_insert_and_fetch(
        self, session: Session, sample_user_table: UserTable, sample_job_table: JobTable
    ):
        """A valid JobMatchTable should insert and round-trip correctly."""
        uid, jid = self._setup(session, sample_user_table, sample_job_table)

        match = JobMatchTable(
            user_id=uid, job_id=jid, match_score=82,
            match_explanation="Strong Python and LangChain overlap.",
            missing_skills=["SQL", "Docker"],
            cv_tailoring_suggestion="Highlight your RAG project.",
        )
        session.add(match)
        session.commit()
        session.refresh(match)

        fetched = session.exec(
            select(JobMatchTable).where(JobMatchTable.id == match.id)
        ).first()
        assert fetched is not None
        assert fetched.match_score == 82
        assert fetched.missing_skills == ["SQL", "Docker"]
        assert fetched.match_explanation == "Strong Python and LangChain overlap."

    def test_created_at_is_datetime(
        self, session: Session, sample_user_table: UserTable, sample_job_table: JobTable
    ):
        """created_at on job_matches should be a timezone-aware datetime."""
        uid, jid = self._setup(session, sample_user_table, sample_job_table)

        match = JobMatchTable(user_id=uid, job_id=jid, match_score=70)
        session.add(match)
        session.commit()
        session.refresh(match)

        fetched = session.exec(
            select(JobMatchTable).where(JobMatchTable.id == match.id)
        ).first()
        assert fetched is not None
        assert isinstance(fetched.created_at, datetime)
        assert fetched.created_at.tzinfo is not None

    def test_fk_rejects_nonexistent_user(
        self, session: Session, sample_job_table: JobTable
    ):
        """A match referencing a non-existent user_id should fail FK check."""
        session.add(sample_job_table)
        session.commit()
        session.refresh(sample_job_table)

        match = JobMatchTable(user_id=9999, job_id=sample_job_table.id, match_score=50)
        session.add(match)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


# =============================================================================
# 5. LogTable TESTS
# =============================================================================

class TestLogTable:
    """Test the append-only audit log table."""

    def test_insert_log(self, session: Session):
        """A log entry should insert successfully and be retrievable."""
        log = LogTable(
            stage="cv_parse",
            status="success",
            message="Extracted 450 tokens from CV.",
            log_metadata={"tokens": 450, "latency_ms": 120},
        )
        session.add(log)
        session.commit()
        session.refresh(log)

        fetched = session.exec(select(LogTable).where(LogTable.id == log.id)).first()
        assert fetched is not None
        assert fetched.stage == "cv_parse"
        assert fetched.status == "success"
        assert fetched.log_metadata == {"tokens": 450, "latency_ms": 120}

    def test_created_at_is_datetime(self, session: Session):
        """created_at on logs should be a timezone-aware datetime (TIMESTAMPTZ)."""
        log = LogTable(stage="job_ingest", status="started")
        session.add(log)
        session.commit()
        session.refresh(log)

        fetched = session.exec(select(LogTable).where(LogTable.id == log.id)).first()
        assert fetched is not None
        assert isinstance(fetched.created_at, datetime)
        assert fetched.created_at.tzinfo is not None

    def test_multiple_logs_appended(self, session: Session):
        """Multiple log entries for the same stage should all be stored."""
        for status in ("started", "success"):
            session.add(LogTable(stage="cv_parse", status=status))
        session.commit()

        count = session.exec(
            select(func.count()).select_from(LogTable)
        ).one()
        assert count == 2

    def test_log_without_user_or_job(self, session: Session):
        """Logs should be insertable without user_id or job_id (optional FKs)."""
        log = LogTable(stage="error", status="failure", message="Unhandled exception.")
        session.add(log)
        session.commit()
        session.refresh(log)
        assert log.id is not None
        assert log.user_id is None
        assert log.job_id is None


# =============================================================================
# 6. Pydantic Model Validation TESTS
# =============================================================================

class TestPydanticModels:
    """Test that Pydantic validators reject bad data before it reaches the DB."""

    def test_valid_user_profile(self):
        """A fully valid UserProfile should be created without errors."""
        profile = UserProfile(
            name="Sara Ali",
            email="sara@example.com",
            years_of_experience=3,
            career_level="mid",
            education="BSc CS, AUC",
            skills=["Python", "SQL"],
        )
        assert profile.career_level == "mid"

    def test_career_level_normalised_to_lowercase(self):
        """career_level should be normalised to lowercase by the validator."""
        profile = UserProfile(
            name="Test", years_of_experience=1, career_level="JUNIOR"
        )
        assert profile.career_level == "junior"

    def test_invalid_career_level_raises(self):
        """An invalid career_level should raise a ValidationError."""
        with pytest.raises(ValidationError):
            UserProfile(name="Test", years_of_experience=1, career_level="intern")

    def test_negative_experience_raises(self):
        """years_of_experience cannot be negative."""
        with pytest.raises(ValidationError):
            UserProfile(name="Test", years_of_experience=-1, career_level="junior")

    def test_valid_job_posting(self):
        """A valid JobPosting should be created without errors."""
        job = JobPosting(
            title="AI Engineer", company="Breadfast",
            location="Cairo", description="...",
            required_skills=["Python"],
            experience_level="mid", source="wuzzuf",
        )
        assert job.source == "wuzzuf"

    def test_invalid_source_raises(self):
        """An unrecognized job source should raise a ValidationError."""
        with pytest.raises(ValidationError):
            JobPosting(
                title="Dev", company="Corp", location="Cairo",
                description="...", experience_level="junior",
                source="glassdoor",   # not allowed
            )

    def test_job_match_score_out_of_range(self):
        """A match_score outside 0-100 should raise a ValidationError."""
        job = JobPosting(
            title="AI Engineer", company="Breadfast",
            location="Cairo", description="...",
            experience_level="mid", source="wuzzuf",
        )
        with pytest.raises(ValidationError):
            JobMatch(
                job=job, match_score=110,
                match_explanation="Too high.",
            )

    def test_user_profile_to_user_table_conversion(self):
        """UserProfile.to_user_table() should produce a valid UserTable."""
        profile = UserProfile(
            name="Mohamed", years_of_experience=2,
            career_level="junior", skills=["Python", "SQL"],
        )
        row = profile.to_user_table()
        assert isinstance(row, UserTable)
        assert row.skills == ["Python", "SQL"]
        assert row.career_level == "junior"
        # Preferences are user-supplied, not parsed — default to empty.
        assert row.desired_roles == []

    def test_job_posting_to_job_table_conversion(self):
        """JobPosting.to_job_table() should produce a valid JobTable with a content_hash."""
        posting = JobPosting(
            title="ML Engineer", company="Paymob",
            location="Cairo", description="Build ML models.",
            required_skills=["Python", "PyTorch"],
            experience_level="mid", source="wuzzuf",
            posted_date="2025-06-02",
        )
        job = posting.to_job_table()
        assert isinstance(job, JobTable)
        assert job.content_hash is not None
        assert job.required_skills == ["Python", "PyTorch"]
        assert job.posted_date == date(2025, 6, 2)


# =============================================================================
# 7. CASCADE DELETE TESTS
# =============================================================================

class TestCascadeDeletes:
    """Verify that deleting a parent row cascades to child rows."""

    def test_deleting_user_removes_job_matches(
        self, session: Session, sample_user_table: UserTable, sample_job_table: JobTable
    ):
        """When a user is deleted, their job_matches should be deleted automatically."""
        session.add(sample_user_table)
        session.add(sample_job_table)
        session.commit()
        session.refresh(sample_user_table)
        session.refresh(sample_job_table)

        match = JobMatchTable(
            user_id=sample_user_table.id,
            job_id=sample_job_table.id,
            match_score=75,
        )
        session.add(match)
        session.commit()

        # Verify match exists before delete
        count_before = session.exec(
            select(func.count()).select_from(JobMatchTable)
        ).one()
        assert count_before == 1

        # Delete the user
        session.delete(sample_user_table)
        session.commit()

        # Match should be gone due to cascade (SQLModel handles via relationship)
        count_after = session.exec(
            select(func.count()).select_from(JobMatchTable)
        ).one()
        assert count_after == 0

    def test_deleting_job_removes_job_matches(
        self, session: Session, sample_user_table: UserTable, sample_job_table: JobTable
    ):
        """When a job is deleted, its job_matches should be deleted automatically."""
        session.add(sample_user_table)
        session.add(sample_job_table)
        session.commit()
        session.refresh(sample_user_table)
        session.refresh(sample_job_table)

        match = JobMatchTable(
            user_id=sample_user_table.id,
            job_id=sample_job_table.id,
            match_score=80,
        )
        session.add(match)
        session.commit()

        session.delete(sample_job_table)
        session.commit()

        count_after = session.exec(
            select(func.count()).select_from(JobMatchTable)
        ).one()
        assert count_after == 0


# =============================================================================
# 8. parse_posted_date VALIDATOR TESTS
# =============================================================================

class TestParsedPostedDate:
    """Test the parse_posted_date validator on the JobPosting Pydantic schema."""

    def test_string_input_parses_to_date(self):
        """String '2025-06-01' should be converted to date(2025, 6, 1)."""
        posting = JobPosting(
            title="T", company="C", location="L", description="D",
            experience_level="junior", source="wuzzuf",
            posted_date="2025-06-01",
        )
        assert posting.posted_date == date(2025, 6, 1)

    def test_empty_string_returns_none(self):
        """Empty string '' should be converted to None."""
        posting = JobPosting(
            title="T", company="C", location="L", description="D",
            experience_level="junior", source="wuzzuf",
            posted_date="",
        )
        assert posting.posted_date is None

    def test_none_returns_none(self):
        """None input should return None."""
        posting = JobPosting(
            title="T", company="C", location="L", description="D",
            experience_level="junior", source="wuzzuf",
            posted_date=None,
        )
        assert posting.posted_date is None

    def test_invalid_string_returns_none(self):
        """Unparseable string 'not-date' should return None — never raises."""
        posting = JobPosting(
            title="T", company="C", location="L", description="D",
            experience_level="junior", source="wuzzuf",
            posted_date="not-date",
        )
        assert posting.posted_date is None

    def test_date_object_passed_through(self):
        """A date object passed directly should be returned unchanged."""
        d = date(2025, 12, 25)
        posting = JobPosting(
            title="T", company="C", location="L", description="D",
            experience_level="junior", source="wuzzuf",
            posted_date=d,
        )
        assert posting.posted_date == d
