"""
Category 8 – Sample Dataset Tests
==================================

These tests load the curated real-world sample file at
``data/sample_jobs.json`` (119 real Wuzzuf job postings) and verify
end-to-end behaviour against a **real PostgreSQL** database via the shared
``session`` fixture from ``tests/conftest.py``.

Coverage:
  8a. JSON file existence and valid JSON array structure
  8b. Every record validates through the Pydantic JobPosting schema
  8c. Bulk insert of all jobs — row count matches file
  8d. Full round-trip fidelity (JobPosting → JobTable → DB → JobTable)
  8e. Idempotent deduplication via UNIQUE constraint on content_hash
  8f. All SHA-256 hashes are unique across the fixture
  8g. Filter by source='wuzzuf'
  8h. Filter by source='bayt'
  8i. experience_level distribution matches the fixture
  8j. Python skill query — Python appears in every posting
  8k. FastAPI skill query — FastAPI appears in a subset
  8l. posted_date DESC feed is correctly ordered
  8m. One log entry written per ingested job

Design notes
------------
* All tests use the shared ``session`` fixture from ``tests/conftest.py``.
  Each test gets a completely fresh PostgreSQL schema.
* JSON skill queries use Python-level filtering (not SQLite json_each).
* posted_date is a PostgreSQL DATE — compared as date objects, not strings.
"""

import json
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select, func

from app.models import (
    JobPosting,
    JobTable,
    LogTable,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Absolute path to the curated 119-job Wuzzuf fixture shipped with the project.
SAMPLE_JOBS_PATH: Path = (
    Path(__file__).resolve().parent.parent / "data" / "sample_jobs.json"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_raw() -> list[dict[str, Any]]:
    """Load the raw JSON array from disk. Fails fast if the file is missing."""
    assert SAMPLE_JOBS_PATH.exists(), (
        f"Sample dataset not found at {SAMPLE_JOBS_PATH}. "
        "Run pytest from the repository root."
    )
    return json.loads(SAMPLE_JOBS_PATH.read_text(encoding="utf-8"))


def _ingest_all(
    session: Session,
    records: list[dict[str, Any]],
    *,
    ignore_duplicates: bool = False,
) -> list[int]:
    """
    Validate each raw dict through JobPosting, convert to JobTable, and insert
    into the jobs table.

    Args:
        session: An open SQLModel Session.
        records: List of raw dicts loaded from the JSON file.
        ignore_duplicates: When True, catches IntegrityError per duplicate,
            rolls back that row, and continues. When False, raises on first dupe.

    Returns:
        List of inserted row IDs (0 for skipped rows when ignore_duplicates=True).
    """
    ids: list[int] = []
    for raw in records:
        posting = JobPosting(**raw)
        job = posting.to_job_table()
        session.add(job)
        try:
            session.commit()
            session.refresh(job)
            ids.append(job.id or 0)
        except IntegrityError:
            session.rollback()
            if not ignore_duplicates:
                raise
            ids.append(0)
    return ids


# ---------------------------------------------------------------------------
# 8. SAMPLE DATASET TESTS
# ---------------------------------------------------------------------------


class TestSampleDataset:
    """
    Integration tests for the ``data/sample_jobs.json`` fixture.

    The fixture ships 119 real-world job postings scraped from Wuzzuf.
    All tests run against a fresh PostgreSQL schema (via conftest.py session)
    so they are isolated and reproducible.
    """

    # 8a -------------------------------------------------------------------

    def test_sample_file_exists_and_is_valid_json(self) -> None:
        """The fixture file must exist and parse as a non-empty JSON array."""
        records = _load_raw()
        assert isinstance(records, list), "Top-level JSON structure must be a list"
        assert len(records) > 0, "sample_jobs.json must not be empty"

    # 8b -------------------------------------------------------------------

    def test_all_records_validate_as_job_postings(self) -> None:
        """Every record must pass Pydantic validation without errors.

        If JobPosting.model_validate(raw) succeeds, experience_level and source
        are already validated by the model's field_validators.
        We only sanity-check non-empty strings here since Pydantic's
        ``str`` type does not reject empty strings by itself.
        """
        records = _load_raw()
        for i, raw in enumerate(records):
            posting = JobPosting.model_validate(raw)
            assert posting.title.strip(), f"Record {i}: title is blank"
            assert posting.company.strip(), f"Record {i}: company is blank"

    # 8c -------------------------------------------------------------------

    def test_bulk_insert_all_jobs(self, session: Session) -> None:
        """All sample jobs should insert without errors and be queryable."""
        records = _load_raw()
        ids = _ingest_all(session, records)

        count = session.exec(
            select(func.count()).select_from(JobTable)
        ).one()
        assert count == len(records), f"Expected {len(records)} rows, got {count}"
        assert all(isinstance(row_id, int) and row_id > 0 for row_id in ids), (
            "All inserted row IDs must be positive integers"
        )

    # 8d -------------------------------------------------------------------

    def test_all_rows_round_trip_through_job_table(self, session: Session) -> None:
        """Each inserted row should deserialize back to a JobTable with intact fields."""
        records = _load_raw()
        _ingest_all(session, records)

        db_rows = session.exec(select(JobTable)).all()
        assert len(db_rows) == len(records)

        # Build a lookup by title+company for order-independent comparison
        db_by_key = {(r.title, r.company): r for r in db_rows}

        for original in records:
            key = (original["title"], original["company"])
            assert key in db_by_key, f"Row not found for {key}"
            job_row = db_by_key[key]

            assert job_row.title == original["title"], "title mismatch"
            assert job_row.company == original["company"], "company mismatch"
            assert job_row.source == original["source"], "source mismatch"
            assert job_row.experience_level == original["experience_level"], (
                "experience_level mismatch"
            )
            assert job_row.required_skills == original["required_skills"], (
                "required_skills mismatch"
            )
            # content_hash is only the *fallback* dedup key: it is populated when
            # a posting has no stable (source, external_id), and left NULL when
            # external_id is present.
            if original.get("external_id"):
                assert job_row.content_hash is None, (
                    "content_hash must be NULL when external_id is present"
                )
            else:
                assert job_row.content_hash is not None, (
                    "content_hash must be set when there is no external_id"
                )

    # 8e -------------------------------------------------------------------

    def test_deduplication_is_idempotent(self, session: Session) -> None:
        """
        Re-ingesting the same dataset must produce the same number of rows.

        This simulates a typical nightly pipeline re-run. Duplicate postings
        are caught as IntegrityError and rolled back, leaving the count intact.
        """
        records = _load_raw()
        expected_count = len(records)

        # First pass — all rows must insert
        _ingest_all(session, records)
        count_after_first = session.exec(
            select(func.count()).select_from(JobTable)
        ).one()
        assert count_after_first == expected_count

        # Second pass — identical records → IntegrityError → rollback → no new rows
        _ingest_all(session, records, ignore_duplicates=True)
        count_after_second = session.exec(
            select(func.count()).select_from(JobTable)
        ).one()
        assert count_after_second == expected_count, (
            "Re-ingestion must not create duplicate rows"
        )

    # 8f -------------------------------------------------------------------

    def test_dedup_keys_are_unique_across_all_jobs(self) -> None:
        """
        Every job in the fixture must have a distinct deduplication key.

        The primary key is ``(source, external_id)``; ``content_hash`` (SHA-256 of
        title | company | posted_date) is only the fallback for postings without a
        stable external_id. A collision would be a data error in the fixture.
        """
        records = _load_raw()
        keys = []
        for r in records:
            posting = JobPosting(**r)
            if posting.external_id:
                keys.append(("ext", posting.source, posting.external_id))
            else:
                keys.append(("hash", posting.to_job_table().content_hash))
        assert len(set(keys)) == len(keys), (
            "Collision detected: two sample jobs share the same dedup key "
            "((source, external_id) or content_hash fallback)."
        )

    # 8g -------------------------------------------------------------------

    def test_filter_by_source_wuzzuf(self, session: Session) -> None:
        """Filtering by source='wuzzuf' must return only Wuzzuf-sourced jobs."""
        records = _load_raw()
        _ingest_all(session, records)

        expected = sum(1 for r in records if r["source"] == "wuzzuf")
        actual_rows = session.exec(
            select(JobTable).where(JobTable.source == "wuzzuf")
        ).all()
        assert len(actual_rows) == expected, (
            f"Expected {expected} wuzzuf rows, got {len(actual_rows)}"
        )

    # 8h -------------------------------------------------------------------

    def test_filter_by_source_bayt(self, session: Session) -> None:
        """Filtering by source='bayt' must return only Bayt-sourced jobs."""
        records = _load_raw()
        _ingest_all(session, records)

        expected = sum(1 for r in records if r["source"] == "bayt")
        actual_rows = session.exec(
            select(JobTable).where(JobTable.source == "bayt")
        ).all()
        assert len(actual_rows) == expected, (
            f"Expected {expected} bayt rows, got {len(actual_rows)}"
        )

    # 8i -------------------------------------------------------------------

    def test_experience_level_distribution(self, session: Session) -> None:
        """
        Count of jobs at each seniority level must match the fixture data.

        This ensures that Pydantic validators and the ingest path all agree
        on the canonical level strings.
        """
        records = _load_raw()
        _ingest_all(session, records)

        for level in ("junior", "mid", "senior"):
            expected = sum(1 for r in records if r["experience_level"] == level)
            actual_rows = session.exec(
                select(JobTable).where(JobTable.experience_level == level)
            ).all()
            assert len(actual_rows) == expected, (
                f"Level '{level}': expected {expected}, got {len(actual_rows)}"
            )

    # 8j -------------------------------------------------------------------

    def test_skill_query_python(self, session: Session) -> None:
        """In-Python skill filtering must find all jobs requiring 'python'.

        Skills are now stored canonicalized to lowercase, so the query token is
        lowercase too. List columns are JSONB arrays; we load rows and filter in
        Python here for parity with the matching engine.
        """
        records = _load_raw()
        _ingest_all(session, records)

        expected = sum(1 for r in records if "python" in r["required_skills"])
        all_jobs = session.exec(select(JobTable)).all()
        python_jobs = [j for j in all_jobs if "python" in (j.required_skills or [])]
        assert len(python_jobs) == expected, (
            f"python skill query: expected {expected} jobs, got {len(python_jobs)}"
        )

    # 8k -------------------------------------------------------------------

    def test_skill_query_javascript(self, session: Session) -> None:
        """In-Python skill filtering must correctly count 'javascript' jobs."""
        records = _load_raw()
        _ingest_all(session, records)

        expected = sum(1 for r in records if "javascript" in r["required_skills"])
        all_jobs = session.exec(select(JobTable)).all()
        js_jobs = [j for j in all_jobs if "javascript" in (j.required_skills or [])]
        assert len(js_jobs) == expected, (
            f"javascript skill query: expected {expected} jobs, got {len(js_jobs)}"
        )

    # 8l -------------------------------------------------------------------

    def test_date_sorted_feed_is_ordered_desc(self, session: Session) -> None:
        """
        Fetching jobs ORDER BY posted_date DESC must return the most recent
        posting first.

        posted_date is a PostgreSQL DATE column — we compare date objects,
        not strings.
        """
        records = _load_raw()
        _ingest_all(session, records)

        rows = session.exec(
            select(JobTable).order_by(JobTable.posted_date.desc())  # type: ignore[union-attr]
        ).all()
        dates = [r.posted_date for r in rows if r.posted_date is not None]

        # Verify all values are date objects (not strings)
        for d in dates:
            assert isinstance(d, date), f"Expected date object, got {type(d)}"

        # Verify descending order
        assert dates == sorted(dates, reverse=True), (
            "Date-ordered feed is not sorted DESC"
        )

    # 8m -------------------------------------------------------------------

    def test_pipeline_log_written_for_each_ingested_job(
        self, session: Session
    ) -> None:
        """
        A realistic ingest pipeline writes one ``job_ingest`` log entry per job.

        This test verifies the full write path — ingest all jobs, emit a log
        for each one, then query logs to confirm the count matches.
        """
        records = _load_raw()
        job_ids = _ingest_all(session, records)

        for job_id in job_ids:
            if job_id:
                log = LogTable(
                    stage="job_ingest",
                    status="success",
                    message="Job ingested from sample dataset.",
                    job_id=job_id,
                    log_metadata={"source_file": "sample_jobs.json"},
                )
                session.add(log)
        session.commit()

        log_count = session.exec(
            select(func.count()).select_from(LogTable).where(
                LogTable.stage == "job_ingest"
            )
        ).one()
        non_zero_ids = [jid for jid in job_ids if jid]
        assert log_count == len(non_zero_ids), (
            f"Expected {len(non_zero_ids)} log entries, found {log_count}"
        )

    # 8n -------------------------------------------------------------------

    def test_posted_date_stored_as_date_object(self, session: Session) -> None:
        """
        After ingestion, posted_date must be a date object (PostgreSQL DATE)
        """
        records = _load_raw()

        # Find the first raw record with a posted_date
        target_raw = next((r for r in records if r.get("posted_date")), None)
        assert target_raw is not None, "No jobs in the dataset have a posted_date"

        _ingest_all(session, records, ignore_duplicates=True)

        # Retrieve the job from the DB using company and title
        db_job = session.exec(
            select(JobTable).where(
                JobTable.company == target_raw["company"],
                JobTable.title == target_raw["title"],
            )
        ).first()
        assert db_job is not None

        assert isinstance(db_job.posted_date, date), (
            f"posted_date should be a date object, got {type(db_job.posted_date)}"
        )
        expected_date = date.fromisoformat(target_raw["posted_date"])
        assert db_job.posted_date == expected_date
