"""
Tests for the job tracking service (Sprint 3, Task 9).

Coverage:
    1. State transitions          — create, transition, current-state upsert
    2. Duplicate handling          — same status is a silent no-op (no event)
    3. 404 behaviour               — unknown job, untracked pair
    4. Full lifecycle              — reviewed → saved → shortlisted → applied → rejected
    5. Append-only audit log       — one event per real transition, ordered, immutable
    6. Market trend aggregations   — including the skills length filter

Following the repo's documented "Real PostgreSQL database for all tests"
convention, these use the shared async ``async_session`` fixture rather than a
mocked session — that is what actually exercises the DB-level UNIQUE constraint
and the append-only event table this feature relies on.
"""

import pytest
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import JobPosting, JobTable, UserTable
from app.models.job_tracking import (
    JobTrackingEventTable,
    JobTrackingTable,
    TrackingStatus,
)
from app.services import market_trend_service as trends
from app.services.job_tracking_service import (
    JobNotFoundError,
    TrackingNotFoundError,
    get_tracking,
    get_tracking_history,
    list_tracked_jobs,
    track_job,
)
from app.services.skills.repository import link_skills


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


async def _make_user(session: AsyncSession, *, name: str = "Atef") -> UserTable:
    user = UserTable(name=name, career_level="mid", years_of_experience=3)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _make_job(session: AsyncSession, **overrides) -> JobTable:
    """Insert a job via the same JobPosting → JobTable path the pipeline uses."""
    defaults = {
        "title": "Backend Engineer",
        "company": "Breadfast",
        "location": "Cairo, Egypt",
        "description": "Build APIs.",
        "experience_level": "mid",
        "source": "wuzzuf",
        "required_skills": ["Python", "SQL"],
    }
    defaults.update(overrides)
    row = JobPosting(**defaults).to_job_table()
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def _event_count(session: AsyncSession, *, user_id: int, job_id: int) -> int:
    stmt = select(func.count()).select_from(JobTrackingEventTable).where(
        JobTrackingEventTable.user_id == user_id,
        JobTrackingEventTable.job_id == job_id,
    )
    return (await session.exec(stmt)).one()


# =============================================================================
# 1. STATE TRANSITIONS
# =============================================================================


class TestTrackJobCreate:
    async def test_first_track_creates_row_with_default_reviewed(
        self, async_session: AsyncSession
    ) -> None:
        user = await _make_user(async_session)
        job = await _make_job(async_session)

        row = await track_job(async_session, user_id=user.id, job_id=job.id)
        await async_session.commit()

        assert row.status == TrackingStatus.REVIEWED
        assert row.user_id == user.id and row.job_id == job.id

    async def test_first_track_writes_opening_event_with_null_from(
        self, async_session: AsyncSession
    ) -> None:
        user = await _make_user(async_session)
        job = await _make_job(async_session)

        await track_job(async_session, user_id=user.id, job_id=job.id, status=TrackingStatus.SAVED)
        await async_session.commit()

        events = (await async_session.exec(select(JobTrackingEventTable))).all()
        assert len(events) == 1
        assert events[0].from_status is None
        assert events[0].to_status == TrackingStatus.SAVED

    async def test_transition_updates_current_state_and_logs_event(
        self, async_session: AsyncSession
    ) -> None:
        user = await _make_user(async_session)
        job = await _make_job(async_session)

        await track_job(async_session, user_id=user.id, job_id=job.id, status=TrackingStatus.REVIEWED)
        row = await track_job(async_session, user_id=user.id, job_id=job.id, status=TrackingStatus.APPLIED)
        await async_session.commit()

        assert row.status == TrackingStatus.APPLIED

        events = (
            await async_session.exec(
                select(JobTrackingEventTable).order_by(JobTrackingEventTable.id.asc())
            )
        ).all()
        assert [e.to_status for e in events] == [TrackingStatus.REVIEWED, TrackingStatus.APPLIED]
        assert events[1].from_status == TrackingStatus.REVIEWED

    async def test_single_row_per_pair_after_many_transitions(
        self, async_session: AsyncSession
    ) -> None:
        """The UNIQUE (user_id, job_id) row is upserted in place, never duplicated."""
        user = await _make_user(async_session)
        job = await _make_job(async_session)

        for status in (TrackingStatus.SAVED, TrackingStatus.SHORTLISTED, TrackingStatus.APPLIED):
            await track_job(async_session, user_id=user.id, job_id=job.id, status=status)
        await async_session.commit()

        count = (await async_session.exec(select(func.count()).select_from(JobTrackingTable))).one()
        assert count == 1


# =============================================================================
# 2. DUPLICATE HANDLING
# =============================================================================


class TestDuplicateHandling:
    async def test_same_status_twice_is_noop_no_extra_event(
        self, async_session: AsyncSession
    ) -> None:
        user = await _make_user(async_session)
        job = await _make_job(async_session)

        await track_job(async_session, user_id=user.id, job_id=job.id, status=TrackingStatus.SAVED)
        await track_job(async_session, user_id=user.id, job_id=job.id, status=TrackingStatus.SAVED)
        await async_session.commit()

        assert await _event_count(async_session, user_id=user.id, job_id=job.id) == 1

    async def test_redundant_default_reviewed_is_noop(
        self, async_session: AsyncSession
    ) -> None:
        user = await _make_user(async_session)
        job = await _make_job(async_session)

        await track_job(async_session, user_id=user.id, job_id=job.id)  # reviewed
        await track_job(async_session, user_id=user.id, job_id=job.id)  # reviewed again
        await async_session.commit()

        assert await _event_count(async_session, user_id=user.id, job_id=job.id) == 1

    async def test_returning_to_a_previous_status_is_a_real_transition(
        self, async_session: AsyncSession
    ) -> None:
        """saved → shortlisted → saved logs three events (no-op only on same→same)."""
        user = await _make_user(async_session)
        job = await _make_job(async_session)

        await track_job(async_session, user_id=user.id, job_id=job.id, status=TrackingStatus.SAVED)
        await track_job(async_session, user_id=user.id, job_id=job.id, status=TrackingStatus.SHORTLISTED)
        await track_job(async_session, user_id=user.id, job_id=job.id, status=TrackingStatus.SAVED)
        await async_session.commit()

        assert await _event_count(async_session, user_id=user.id, job_id=job.id) == 3


# =============================================================================
# 3. 404 / NOT-FOUND BEHAVIOUR
# =============================================================================


class TestNotFound:
    async def test_track_unknown_job_raises(self, async_session: AsyncSession) -> None:
        user = await _make_user(async_session)
        with pytest.raises(JobNotFoundError):
            await track_job(async_session, user_id=user.id, job_id=999_999)

    async def test_get_tracking_untracked_pair_raises(
        self, async_session: AsyncSession
    ) -> None:
        user = await _make_user(async_session)
        job = await _make_job(async_session)
        with pytest.raises(TrackingNotFoundError):
            await get_tracking(async_session, user_id=user.id, job_id=job.id)

    async def test_history_untracked_pair_raises(
        self, async_session: AsyncSession
    ) -> None:
        user = await _make_user(async_session)
        job = await _make_job(async_session)
        with pytest.raises(TrackingNotFoundError):
            await get_tracking_history(async_session, user_id=user.id, job_id=job.id)


# =============================================================================
# 4. FULL LIFECYCLE
# =============================================================================


class TestLifecycle:
    async def test_reviewed_through_rejected(self, async_session: AsyncSession) -> None:
        user = await _make_user(async_session)
        job = await _make_job(async_session)

        lifecycle = [
            TrackingStatus.REVIEWED,
            TrackingStatus.SAVED,
            TrackingStatus.SHORTLISTED,
            TrackingStatus.APPLIED,
            TrackingStatus.REJECTED,
        ]
        for status in lifecycle:
            await track_job(async_session, user_id=user.id, job_id=job.id, status=status)
        await async_session.commit()

        # Current state is the last one.
        current = await get_tracking(async_session, user_id=user.id, job_id=job.id)
        assert current.status == TrackingStatus.REJECTED

        # The audit log captured every transition, in order, immutably.
        history = await get_tracking_history(async_session, user_id=user.id, job_id=job.id)
        assert [e.to_status for e in history] == lifecycle
        assert history[0].from_status is None
        assert [e.from_status for e in history[1:]] == lifecycle[:-1]


# =============================================================================
# 5. LISTING
# =============================================================================


class TestListTracked:
    async def test_list_filters_by_status(self, async_session: AsyncSession) -> None:
        user = await _make_user(async_session)
        job_a = await _make_job(async_session, title="Job A", company="Co A")
        job_b = await _make_job(async_session, title="Job B", company="Co B")

        await track_job(async_session, user_id=user.id, job_id=job_a.id, status=TrackingStatus.SAVED)
        await track_job(async_session, user_id=user.id, job_id=job_b.id, status=TrackingStatus.APPLIED)
        await async_session.commit()

        saved = await list_tracked_jobs(async_session, user_id=user.id, status=TrackingStatus.SAVED)
        assert [r.job_id for r in saved] == [job_a.id]

        all_tracked = await list_tracked_jobs(async_session, user_id=user.id)
        assert len(all_tracked) == 2

    async def test_list_isolated_per_user(self, async_session: AsyncSession) -> None:
        user_a = await _make_user(async_session, name="A")
        user_b = await _make_user(async_session, name="B")
        job = await _make_job(async_session)

        await track_job(async_session, user_id=user_a.id, job_id=job.id, status=TrackingStatus.SAVED)
        await async_session.commit()

        assert len(await list_tracked_jobs(async_session, user_id=user_a.id)) == 1
        assert len(await list_tracked_jobs(async_session, user_id=user_b.id)) == 0


# =============================================================================
# 6. MARKET TRENDS
# =============================================================================


class TestMarketTrends:
    async def test_top_companies_counts_postings(self, async_session: AsyncSession) -> None:
        await _make_job(async_session, title="Eng 1", company="Breadfast")
        await _make_job(async_session, title="Eng 2", company="Breadfast")
        await _make_job(async_session, title="Eng 3", company="Instabug")

        result = await trends.top_companies(async_session)
        as_dict = {r.label: r.count for r in result}
        assert as_dict["Breadfast"] == 2
        assert as_dict["Instabug"] == 1

    async def test_experience_distribution(self, async_session: AsyncSession) -> None:
        await _make_job(async_session, title="J1", company="A", experience_level="junior")
        await _make_job(async_session, title="J2", company="B", experience_level="senior")
        await _make_job(async_session, title="J3", company="C", experience_level="senior")

        result = {r.label: r.count for r in await trends.experience_level_distribution(async_session)}
        assert result == {"senior": 2, "junior": 1}

    async def test_top_skills_counts_linked_skills(
        self, async_session: AsyncSession
    ) -> None:
        """top_skills aggregates the normalized job_skills links, not the JSONB cache."""
        j1 = await _make_job(
            async_session, title="J1", company="A", required_skills=["python", ".net"],
        )
        j2 = await _make_job(
            async_session, title="J2", company="B", required_skills=["python"],
        )
        for row in (j1, j2):
            await link_skills(async_session, row, row.required_skills)
        await async_session.commit()

        result = {r.label: r.count for r in await trends.top_skills(async_session)}
        assert result["python"] == 2
        assert result[".net"] == 1

    async def test_work_type_distribution_groups_by_work_mode(
        self, async_session: AsyncSession
    ) -> None:
        """Split comes straight from the work_mode column (no text heuristics)."""
        await _make_job(async_session, title="J1", company="A", work_mode="on_site")
        await _make_job(async_session, title="J2", company="B", work_mode="remote")
        await _make_job(async_session, title="J3", company="C", work_mode="remote")

        result = {r.label: r.count for r in await trends.work_type_distribution(async_session)}
        assert result.get("on_site") == 1
        assert result.get("remote") == 2

    async def test_posting_volume_buckets_by_month(self, async_session: AsyncSession) -> None:
        await _make_job(async_session, title="J1", company="A", posted_date="2025-06-01")
        await _make_job(async_session, title="J2", company="B", posted_date="2025-06-20")
        await _make_job(async_session, title="J3", company="C", posted_date="2025-07-02")

        result = await trends.posting_volume(async_session)
        by_period = {str(p.period): p.count for p in result}
        assert by_period["2025-06-01"] == 2
        assert by_period["2025-07-01"] == 1

    async def test_top_categories_unnests_work_roles(self, async_session: AsyncSession) -> None:
        """The multi-valued work_roles column is unnested and counted per role."""
        await _make_job(
            async_session, title="J1", company="A",
            work_roles=["IT/Software Development", "Data Science"],
        )
        await _make_job(
            async_session, title="J2", company="B",
            work_roles=["IT/Software Development"],
        )

        result = {r.label: r.count for r in await trends.top_categories(async_session)}
        assert result["IT/Software Development"] == 2
        assert result["Data Science"] == 1

    async def test_salary_stats_aggregates_visible_by_currency_period(
        self, async_session: AsyncSession
    ) -> None:
        """Visible salaries aggregate per (currency, period); hidden ones are excluded."""
        await _make_job(
            async_session, title="J1", company="A",
            salary_min=1000, salary_max=2000,
            salary_currency="USD", salary_period="Per Month",
        )
        await _make_job(
            async_session, title="J2", company="B",
            salary_min=3000, salary_max=5000,
            salary_currency="USD", salary_period="Per Month",
        )
        # Hidden salary → excluded from the aggregation entirely.
        await _make_job(
            async_session, title="J3", company="C",
            salary_min=9999, salary_max=9999,
            salary_currency="USD", salary_period="Per Month", salary_hidden=True,
        )

        stats = await trends.salary_stats(async_session)
        usd = next(s for s in stats if s.currency == "USD" and s.period == "Per Month")
        assert usd.count == 2       # the hidden row is not counted
        assert usd.min == 1000
        assert usd.max == 5000
        assert usd.avg == 2750      # mean of the per-posting midpoints (1500, 4000)
