"""
Tests for the job collection pipeline services.

Coverage:
    1. Deduplication service  — hash computation, internal dedup, DB dedup
    2. Collection service     — registry, single-source pipeline, batch pipeline
    3. FixtureSource adapter  — fetch from sample_jobs.json

All tests that touch the database use the shared async ``async_session``
fixture from ``tests/conftest.py`` (real PostgreSQL, fresh schema per test).
The services and source ``fetch()`` are async, so DB-touching tests are
``async def`` and run under pytest-asyncio's auto mode.
"""

from tests.test_sample_dataset import _load_raw
from pathlib import Path
import json
import httpx
import pytest
from sqlmodel import select, func
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import JobPosting, JobTable, LogTable
from app.services.job_sources.base import BaseJobSource
from app.services.job_sources.wuzzuf import WuzzufSource
from app.services.job_deduplication_service import (
    deduplicate,
)
from app.services.job_collection_service import (
    SOURCE_REGISTRY,
    BatchCollectionResult,
    collect_from_source,
    collect_from_sources,
    get_available_sources,
    get_source,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_JOBS_PATH: Path = (
    Path(__file__).resolve().parent.parent.parent / "data" / "sample_jobs.json"
)


def _make_posting(**overrides) -> JobPosting:
    """Create a minimal valid JobPosting with optional field overrides."""
    defaults = {
        "title": "Test Engineer",
        "company": "TestCo",
        "location": "Cairo",
        "description": "A test job.",
        "experience_level": "mid",
        "source": "wuzzuf",
    }
    defaults.update(overrides)
    return JobPosting(**defaults)


class StubSource(BaseJobSource):
    """A controllable test double for any job source."""

    source_name = "stub"

    def __init__(self, jobs: list[JobPosting] | None = None, *, should_raise: bool = False) -> None:
        self._jobs = jobs or []
        self._should_raise = should_raise

    async def fetch(self) -> list[JobPosting]:
        if self._should_raise:
            raise RuntimeError("Simulated source failure")
        return self._jobs

    def _normalize(self, raw: dict) -> JobPosting | None:
        # Required by the BaseJobSource ABC; this double produces JobPostings
        # directly in fetch(), so normalization is never exercised here.
        raise NotImplementedError


# --- Doubles for the batch-rollback regression test ------------------------
#
# The registry instantiates sources with no arguments (``source_cls()``), so
# the batch doubles below are zero-arg classes registered via monkeypatch.

_COLLIDING_HASH = "fixed-content-hash-that-collides-on-flush"


class _CollidingPosting(JobPosting):
    """A posting whose DB row always carries the same ``content_hash``.

    Its dedup fingerprint (title|company|posted_date) still varies with the
    title, so ``deduplicate()`` treats two of these as distinct *new* jobs and
    lets both reach the insert step — where the UNIQUE constraint on
    ``content_hash`` then fails at flush time. This is exactly the case the
    per-source SAVEPOINT must contain without harming earlier sources.
    """

    def to_job_table(self) -> JobTable:
        row = super().to_job_table()
        row.content_hash = _COLLIDING_HASH
        return row


class _GoodBatchSource(BaseJobSource):
    """An earlier source in the batch that inserts cleanly."""

    source_name = "good_batch"

    async def fetch(self) -> list[JobPosting]:
        return [
            _make_posting(title="Good A", company="GoodCo A"),
            _make_posting(title="Good B", company="GoodCo B"),
        ]

    def _normalize(self, raw: dict) -> JobPosting | None:
        raise NotImplementedError


class _CollidingBatchSource(BaseJobSource):
    """A later source whose flush fails on a content_hash collision."""

    source_name = "bad_batch"

    async def fetch(self) -> list[JobPosting]:
        common = dict(
            location="Cairo",
            description="A test job.",
            experience_level="mid",
            source="wuzzuf",
        )
        # Distinct titles → distinct dedup hash (both pass dedup) but identical
        # content_hash → UNIQUE violation when the second row is flushed.
        return [
            _CollidingPosting(title="Bad A", company="BadCo", **common),
            _CollidingPosting(title="Bad B", company="BadCo", **common),
        ]

    def _normalize(self, raw: dict) -> JobPosting | None:
        raise NotImplementedError


# =============================================================================
# 1. DEDUPLICATION SERVICE
# =============================================================================


class TestContentHash:
    """Verify the SHA-256 content hash computation."""

    def test_same_job_produces_same_hash(self) -> None:
        job = _make_posting(title="AI Engineer", company="Breadfast")
        assert job.compute_content_hash() == job.compute_content_hash()

    def test_different_jobs_produce_different_hashes(self) -> None:
        job_a = _make_posting(title="AI Engineer", company="Breadfast")
        job_b = _make_posting(title="Data Scientist", company="Instabug")
        assert job_a.compute_content_hash() != job_b.compute_content_hash()

    def test_hash_is_case_insensitive(self) -> None:
        """Title/company are lowered before hashing — casing should not matter."""
        job_lower = _make_posting(title="ai engineer", company="breadfast")
        job_upper = _make_posting(title="AI Engineer", company="Breadfast")
        assert job_lower.compute_content_hash() == job_upper.compute_content_hash()

    def test_hash_ignores_surrounding_and_internal_whitespace(self) -> None:
        """Whitespace is collapsed so cosmetic variants hash identically."""
        job_clean = _make_posting(title="AI Engineer", company="Breadfast")
        job_messy = _make_posting(title="  AI   Engineer ", company="Breadfast")
        assert job_clean.compute_content_hash() == job_messy.compute_content_hash()

    def test_hash_length_is_64_hex_chars(self) -> None:
        job = _make_posting()
        assert len(job.compute_content_hash()) == 64

    def test_hash_matches_to_job_table_hash(self) -> None:
        """to_job_table() must use the same recipe as compute_content_hash()."""
        job = _make_posting(title="ML Engineer", company="Paymob", posted_date="2025-06-02")
        assert job.external_id is None  # hash tier only applies without an external_id
        assert job.compute_content_hash() == job.to_job_table().content_hash

    def test_to_job_table_omits_hash_when_external_id_present(self) -> None:
        """With an external_id, content_hash is left NULL so (source, external_id)
        is the sole discriminator — two distinct postings sharing a
        title|company|date fingerprint must not collide on UNIQUE(content_hash)."""
        job = _make_posting(
            title="Home Automation Site Engineer",
            company="Sphere Smart Solutions",
            posted_date="2026-06-09",
            external_id="wuzzuf-abc",
        )
        assert job.to_job_table().content_hash is None

    def test_distinct_confidential_jobs_do_not_collide(self) -> None:
        """Different hidden-company postings must stay distinct (no data loss).

        With company dropped, the unique URL is the discriminator.
        """
        job_a = _make_posting(
            title="Backend Engineer", company="Confidential",
            url="https://wuzzuf.net/jobs/p/aaa",
        )
        job_b = _make_posting(
            title="Backend Engineer", company="Confidential",
            url="https://wuzzuf.net/jobs/p/bbb",
        )
        assert job_a.compute_content_hash() != job_b.compute_content_hash()

    def test_same_confidential_job_rescraped_dedupes(self) -> None:
        """The same hidden-company posting (same URL) hashes identically."""
        first = _make_posting(
            title="Backend Engineer", company="Confidential",
            url="https://wuzzuf.net/jobs/p/aaa",
        )
        again = _make_posting(
            title="Backend Engineer", company="confidential",
            url="https://wuzzuf.net/jobs/p/aaa",
        )
        assert first.compute_content_hash() == again.compute_content_hash()


class TestDeduplicate:
    """Verify deduplication against the database."""

    async def test_empty_input_returns_empty(self, async_session: AsyncSession) -> None:
        result = await deduplicate([], async_session)
        assert result.new_jobs == []
        assert result.duplicate_count == 0
        assert result.total_incoming == 0

    async def test_all_new_jobs_pass_through(self, async_session: AsyncSession) -> None:
        """With an empty DB, all jobs should be returned as new."""
        jobs = [
            _make_posting(title="Job A", company="Co A"),
            _make_posting(title="Job B", company="Co B"),
        ]
        result = await deduplicate(jobs, async_session)
        assert len(result.new_jobs) == 2
        assert result.duplicate_count == 0

    async def test_existing_jobs_filtered_out(self, async_session: AsyncSession) -> None:
        """Jobs already in the DB should be identified as duplicates."""
        existing = _make_posting(title="Existing Job", company="OldCo")
        row = existing.to_job_table()
        async_session.add(row)
        await async_session.commit()

        incoming = [
            existing,  # duplicate
            _make_posting(title="New Job", company="NewCo"),  # new
        ]
        result = await deduplicate(incoming, async_session)

        assert len(result.new_jobs) == 1
        assert result.new_jobs[0].title == "New Job"
        assert result.duplicate_count == 1

    async def test_internal_duplicates_caught(self, async_session: AsyncSession) -> None:
        """Two identical jobs in the same batch should be de-duped."""
        job = _make_posting(title="Dup Job", company="DupCo")
        result = await deduplicate([job, job], async_session)

        assert len(result.new_jobs) == 1
        assert result.duplicate_count == 1
        assert result.total_incoming == 2

    async def test_external_id_is_primary_dedup_key(self, async_session: AsyncSession) -> None:
        """A re-scraped posting with the same (source, external_id) is a duplicate,
        even if its title/company changed (so its content_hash differs)."""
        original = _make_posting(title="Old Title", company="Co", external_id="wuzzuf-xyz")
        async_session.add(original.to_job_table())
        await async_session.commit()

        incoming = [
            _make_posting(title="Edited Title", company="Co", external_id="wuzzuf-xyz"),  # same id → dup
            _make_posting(title="Fresh", company="Co", external_id="wuzzuf-new"),         # new id
        ]
        result = await deduplicate(incoming, async_session)

        assert len(result.new_jobs) == 1
        assert result.new_jobs[0].external_id == "wuzzuf-new"
        assert result.duplicate_count == 1

    async def test_internal_dedup_by_external_id(self, async_session: AsyncSession) -> None:
        """Two incoming postings sharing an external_id collapse to one."""
        a = _make_posting(title="A", company="Co", external_id="dup-id")
        b = _make_posting(title="B", company="Co", external_id="dup-id")
        result = await deduplicate([a, b], async_session)

        assert len(result.new_jobs) == 1
        assert result.duplicate_count == 1


# =============================================================================
# 2. COLLECTION SERVICE — Registry
# =============================================================================


class TestSourceRegistry:
    """Verify source registration and lookup."""

    def test_fixture_is_registered(self) -> None:
        assert "fixture" in get_available_sources()

    def test_get_source_returns_instance(self) -> None:
        source = get_source("fixture")
        assert source.source_name == "fixture"

    def test_get_source_unknown_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown job source"):
            get_source("nonexistent_source")

    def test_available_sources_returns_list(self) -> None:
        sources = get_available_sources()
        assert isinstance(sources, list)
        assert len(sources) >= 1


# =============================================================================
# 3. COLLECTION SERVICE — Single source pipeline
# =============================================================================


class TestCollectFromSource:
    """Test the full fetch → deduplicate → insert pipeline for a single source."""

    async def test_successful_collection(self, async_session: AsyncSession) -> None:
        """Happy path: stub source returns 3 jobs, all inserted."""
        jobs = [
            _make_posting(title=f"Job {i}", company=f"Co {i}")
            for i in range(3)
        ]
        stub = StubSource(jobs)

        result = await collect_from_source(stub, async_session)
        await async_session.commit()

        assert result.source == "stub"
        assert result.fetched == 3
        assert result.inserted == 3
        assert result.duplicates == 0
        assert result.errors == 0

        count = (await async_session.exec(select(func.count()).select_from(JobTable))).one()
        assert count == 3

    async def test_duplicates_not_inserted(self, async_session: AsyncSession) -> None:
        """Running the pipeline twice should insert 0 new rows the second time."""
        jobs = [_make_posting(title="Same Job", company="SameCo")]
        stub = StubSource(jobs)

        first = await collect_from_source(stub, async_session)
        await async_session.commit()
        assert first.inserted == 1

        second = await collect_from_source(StubSource(jobs), async_session)
        await async_session.commit()
        assert second.inserted == 0
        assert second.duplicates == 1

    async def test_source_failure_returns_error_result(self, async_session: AsyncSession) -> None:
        """If the source raises, the result should report 1 error and 0 fetched."""
        stub = StubSource(should_raise=True)
        result = await collect_from_source(stub, async_session)

        assert result.errors == 1
        assert result.fetched == 0
        assert result.inserted == 0

    async def test_empty_source_returns_zero_counts(self, async_session: AsyncSession) -> None:
        """A source that returns no jobs should produce all-zero counts."""
        stub = StubSource(jobs=[])
        result = await collect_from_source(stub, async_session)

        assert result.fetched == 0
        assert result.inserted == 0
        assert result.duplicates == 0
        assert result.errors == 0

    async def test_pipeline_writes_job_ingest_log(self, async_session: AsyncSession) -> None:
        """A successful run must persist exactly one ``job_ingest`` audit row.

        Regression test for the empty ``logs`` table: the collection pipeline
        previously emitted only structlog events and never wrote ``LogTable``
        rows, so the audit log stayed empty after every ingest. This asserts the
        DB write path, not just the console log.
        """
        jobs = [_make_posting(title=f"Job {i}", company=f"Co {i}") for i in range(3)]

        result = await collect_from_source(StubSource(jobs), async_session)
        await async_session.commit()

        logs = (
            await async_session.exec(
                select(LogTable).where(LogTable.stage == "job_ingest")
            )
        ).all()

        assert len(logs) == 1
        log = logs[0]
        assert log.status == "success"
        assert log.log_metadata is not None
        assert log.log_metadata["source"] == "stub"
        assert log.log_metadata["inserted"] == result.inserted == 3
        assert log.log_metadata["fetched"] == 3

    async def test_source_failure_writes_failure_log(self, async_session: AsyncSession) -> None:
        """A fetch failure must still leave a ``failure`` audit row behind."""
        result = await collect_from_source(StubSource(should_raise=True), async_session)
        await async_session.commit()

        assert result.errors == 1

        logs = (
            await async_session.exec(
                select(LogTable).where(LogTable.stage == "job_ingest")
            )
        ).all()

        assert len(logs) == 1
        assert logs[0].status == "failure"


# =============================================================================
# 4. COLLECTION SERVICE — Batch pipeline
# =============================================================================


class TestCollectFromSources:
    """Test the multi-source batch pipeline."""

    async def test_batch_with_registered_source(self, async_session: AsyncSession) -> None:
        """Collecting from 'fixture' via the batch function should succeed."""
        batch = await collect_from_sources(["fixture"], async_session)

        assert isinstance(batch, BatchCollectionResult)
        assert len(batch.results) == 1
        assert batch.results[0].source == "fixture"
        assert batch.total_inserted >= 1

    async def test_batch_with_unknown_source(self, async_session: AsyncSession) -> None:
        """Unknown sources should produce an error result, not crash."""
        batch = await collect_from_sources(["nonexistent"], async_session)

        assert len(batch.results) == 1
        assert batch.results[0].errors == 1
        assert batch.results[0].source == "nonexistent"

    async def test_batch_idempotent(self, async_session: AsyncSession) -> None:
        """Running fixture twice: second run should insert 0, all duplicates."""
        first = await collect_from_sources(["fixture"], async_session)
        second = await collect_from_sources(["fixture"], async_session)

        assert first.total_inserted >= 1
        assert second.total_inserted == 0
        assert second.total_duplicates >= 1

    async def test_later_source_failure_preserves_earlier_rows(
        self, async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A flush failure in a later source must NOT roll back earlier sources.

        Regression test for the batch-transaction fix: each source's writes run
        inside their own SAVEPOINT, so when ``bad_batch`` fails on a content_hash
        collision, ``good_batch``'s rows still survive and its reported counts
        stay honest.
        """
        monkeypatch.setitem(SOURCE_REGISTRY, "good_batch", _GoodBatchSource)
        monkeypatch.setitem(SOURCE_REGISTRY, "bad_batch", _CollidingBatchSource)

        batch = await collect_from_sources(["good_batch", "bad_batch"], async_session)

        good = next(r for r in batch.results if r.source == "good_batch")
        bad = next(r for r in batch.results if r.source == "bad_batch")

        # Earlier source committed cleanly and its count is truthful.
        assert good.inserted == 2
        assert good.errors == 0

        # Later source failed at flush, rolled back its own savepoint, and
        # honestly reports zero inserts plus an error.
        assert bad.inserted == 0
        assert bad.errors >= 1

        # The earlier source's rows survived the later source's failure —
        # exactly the data-loss bug this fix prevents.
        count = (await async_session.exec(select(func.count()).select_from(JobTable))).one()
        assert count == 2


# =============================================================================
# 5. FIXTURE SOURCE ADAPTER
# =============================================================================


class TestFixtureSource:
    """Verify the FixtureSource reads and validates sample_jobs.json."""

    def test_sample_file_exists(self) -> None:
        assert SAMPLE_JOBS_PATH.exists(), f"Missing: {SAMPLE_JOBS_PATH}"

    async def test_fixture_source_returns_job_postings(self) -> None:
        source = get_source("fixture")
        jobs = await source.fetch()

        assert isinstance(jobs, list)
        assert len(jobs) == len(_load_raw())
        for job in jobs:
            assert isinstance(job, JobPosting)

    async def test_fixture_jobs_have_meaningful_content(self) -> None:
        """Sanity-check that fixture data has non-blank strings.

        Pydantic already validates experience_level and source via
        field_validators — we only need to guard against blank strings
        which ``str`` type does not reject.
        """
        source = get_source("fixture")
        for i, job in enumerate(await source.fetch()):
            assert job.title.strip(), f"Record {i}: title is blank"
            assert job.company.strip(), f"Record {i}: company is blank"
            assert job.description.strip(), f"Record {i}: description is blank"

    async def test_fixture_full_pipeline_inserts_all(self, async_session: AsyncSession) -> None:
        """End-to-end: fixture source → pipeline → DB should insert all fixture jobs."""
        source = get_source("fixture")
        result = await collect_from_source(source, async_session)
        await async_session.commit()

        assert result.fetched > 0
        assert result.inserted == result.fetched
        assert result.duplicates == 0
        assert result.errors == 0

        count = (await async_session.exec(select(func.count()).select_from(JobTable))).one()
        assert count == result.fetched


# =============================================================================
# 6. WUZZUF SOURCE ADAPTER
# =============================================================================
#
# The network layer is exercised without real HTTP by injecting an
# ``httpx.MockTransport`` through ``WuzzufSource._build_client`` (monkeypatched).
# The pure helpers and ``_normalize`` are tested directly with plain dicts.


def _wuzzuf_job_item(
    job_id: str,
    *,
    title: str = "Backend Developer",
    company_id: str | None = "9",
    career_level: str = "Experienced",
    min_years: int | None = 3,
    hide_company: bool = False,
) -> dict:
    """Build a Wuzzuf ``/api/job`` item matching the real API shape."""
    attrs: dict = {
        "title": title,
        "description": "<p>Build &amp; ship APIs</p>",
        "requirements": "<ul><li>Python</li><li>SQL</li></ul>",
        "careerLevel": {"name": career_level},
        "workExperienceYears": {"min": min_years, "max": 6},
        "keywords": [{"name": "Python"}, {"name": "SQL"}, {"name": "Python"}],
        "location": {
            "country": {"name": "Egypt", "code": "EG"},
            "city": {"name": "Cairo"},
            "area": None,
        },
        "workplaceArrangement": {
            "translations": {"displayed_name": {"en": "remote"}}
        },
        "workTypes": [{"translations": {"displayed_name": {"en": "full_time"}}}],
        "workRoles": [{"name": "IT/Software Development"}],
        "salary": {
            "min": 1000,
            "max": 2000,
            "currency": {"code": "USD"},
            "period": {"name": "Per Month"},
        },
        "hideSalary": False,
        "postedAt": "06/01/2025 10:30:00",
        "expireAt": "08/01/2025 10:30:00",
        "uri": f"jobs/p/{job_id}",
        "hideCompany": hide_company,
    }
    relationships = (
        {"company": {"data": {"id": company_id}}} if company_id else {}
    )
    return {"id": job_id, "attributes": attrs, "relationships": relationships}


def _wuzzuf_transport(
    job_items: list[dict],
    company_items: list[dict],
) -> httpx.MockTransport:
    """A MockTransport that answers Wuzzuf's search / job / company endpoints."""
    job_ids = [item["id"] for item in job_items]

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/search/job":
            return httpx.Response(
                200,
                json={
                    "data": [{"id": jid} for jid in job_ids],
                    "meta": {"totalResultsCount": len(job_ids)},
                },
            )
        if path == "/api/job":
            return httpx.Response(200, json={"data": job_items})
        if path == "/api/company":
            return httpx.Response(200, json={"data": company_items})
        return httpx.Response(404, json={"data": []})

    return httpx.MockTransport(handler)


class TestWuzzufNormalize:
    """``WuzzufSource._normalize`` resolves the company, then delegates to the parser.

    The pure parsing/extraction is covered in ``test_wuzzuf_parsing.py``; here we
    focus on company-name resolution and the drop/keep decision.
    """

    def test_normalize_happy_path(self) -> None:
        source = WuzzufSource()
        company = {"id": "9", "attributes": {"name": "Breadfast"}}
        posting = source._normalize(_wuzzuf_job_item("100"), company)

        assert posting is not None
        assert posting.title == "Backend Developer"
        assert posting.company == "Breadfast"
        assert posting.country_code == "EG"
        assert posting.city == "Cairo"
        assert posting.work_mode == "remote"
        assert posting.experience_level == "mid"
        assert posting.source == "wuzzuf"
        assert posting.external_id == "100"
        # Skills are canonicalized to lowercase.
        assert posting.required_skills == ["python", "sql"]
        assert posting.salary_currency == "USD"

    def test_normalize_discards_senior_management(self) -> None:
        source = WuzzufSource()
        job = _wuzzuf_job_item("200", career_level="Senior Management")
        assert source._normalize(job, {"id": "9", "attributes": {"name": "X"}}) is None

    def test_normalize_hidden_company_is_confidential(self) -> None:
        source = WuzzufSource()
        job = _wuzzuf_job_item("300", hide_company=True, career_level="Manager")
        posting = source._normalize(job, {"id": "9", "attributes": {"name": "Breadfast"}})

        assert posting is not None
        assert posting.company == "Confidential"
        assert posting.experience_level == "senior"

    def test_normalize_missing_company_is_confidential(self) -> None:
        source = WuzzufSource()
        posting = source._normalize(_wuzzuf_job_item("400", company_id=None), None)

        assert posting is not None
        assert posting.company == "Confidential"


class TestWuzzufRegistry:
    """Wuzzuf should be wired into the source registry."""

    def test_wuzzuf_is_registered(self) -> None:
        assert "wuzzuf" in get_available_sources()

    def test_get_source_returns_wuzzuf_instance(self) -> None:
        source = get_source("wuzzuf")
        assert isinstance(source, WuzzufSource)
        assert source.source_name == "wuzzuf"


class TestWuzzufFetch:
    """End-to-end ``fetch()`` with the HTTP layer mocked via MockTransport."""

    def _patch_transport(
        self,
        monkeypatch: pytest.MonkeyPatch,
        source: WuzzufSource,
        transport: httpx.MockTransport,
    ) -> None:
        monkeypatch.setattr(
            source, "_build_client", lambda: httpx.AsyncClient(transport=transport)
        )

    async def test_fetch_returns_normalized_postings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # One mid-level job, one executive (discarded), one hidden-company senior.
        job_items = [
            _wuzzuf_job_item("100", title="Backend Developer"),
            _wuzzuf_job_item("200", title="CEO", career_level="Senior Management"),
            _wuzzuf_job_item(
                "300", title="Eng Manager", hide_company=True, career_level="Manager"
            ),
        ]
        company_items = [{"id": "9", "attributes": {"name": "Breadfast"}}]

        source = WuzzufSource(categories=["Backend Developer"])
        self._patch_transport(
            monkeypatch, source, _wuzzuf_transport(job_items, company_items)
        )

        postings = await source.fetch()

        # Executive role dropped; the other two survive.
        assert len(postings) == 2
        titles = {p.title for p in postings}
        assert titles == {"Backend Developer", "Eng Manager"}
        assert all(p.source == "wuzzuf" for p in postings)

    async def test_fetch_empty_when_no_results(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source = WuzzufSource(categories=["Backend Developer"])
        self._patch_transport(monkeypatch, source, _wuzzuf_transport([], []))

        assert await source.fetch() == []

    async def test_fetch_pipeline_inserts_into_db(
        self, async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Wuzzuf source → collection pipeline → DB rows."""
        job_items = [
            _wuzzuf_job_item("100", title="Backend Developer"),
            _wuzzuf_job_item("300", title="Frontend Developer"),
        ]
        company_items = [{"id": "9", "attributes": {"name": "Breadfast"}}]

        source = WuzzufSource(categories=["Backend Developer"])
        self._patch_transport(
            monkeypatch, source, _wuzzuf_transport(job_items, company_items)
        )

        result = await collect_from_source(source, async_session)
        await async_session.commit()

        assert result.source == "wuzzuf"
        assert result.fetched == 2
        assert result.inserted == 2
        assert result.errors == 0

        count = (await async_session.exec(select(func.count()).select_from(JobTable))).one()
        assert count == 2
