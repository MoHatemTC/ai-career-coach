"""Tests for MatchService.analyze and the canonical upsert_job_match helper."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.jobs import JobMatchTable, JobPosting, UserTable
from app.schemas.match_analysis import MatchAnalysis
from app.services.match_service import (
    MatchService,
    mark_job_match_reviewed,
    upsert_job_match,
)

pytestmark = pytest.mark.asyncio


async def _make_user(session: AsyncSession) -> UserTable:
    user = UserTable(name="Atef", career_level="mid", years_of_experience=3,
                     skills=["Python"], tools=["Docker"])
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _make_job(session: AsyncSession):
    row = JobPosting(
        title="Backend Engineer",
        company="Breadfast",
        location="Cairo, Egypt",
        description="Build APIs with Python.",
        experience_level="mid",
        source="wuzzuf",
        required_skills=["python", "sql"],
    ).to_job_table()
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def _match_count(session: AsyncSession, user_id: int, job_id: int) -> int:
    stmt = select(func.count()).select_from(JobMatchTable).where(
        JobMatchTable.user_id == user_id, JobMatchTable.job_id == job_id
    )
    return (await session.exec(stmt)).one()


async def test_analyze_persists_and_upserts(async_session: AsyncSession):
    user = await _make_user(async_session)
    job = await _make_job(async_session)

    def _mock_registry(score, explanation="ok"):
        reg = MagicMock()
        reg._LLM_MODEL = "test-model"
        reg.acomplete = AsyncMock(
            return_value=MatchAnalysis(
                match_score=score,
                match_explanation=explanation,
                missing_skills=["sql"],
                cv_tailoring_suggestion="emphasize python",
                cover_letter_draft="Dear team...",
            )
        )
        return reg

    with patch("app.services.match_service.get_registry", return_value=_mock_registry(75)):
        row = await MatchService(async_session).analyze(user.id, job.id)

    assert row.match_score == 75
    assert row.missing_skills == ["sql"]
    assert await _match_count(async_session, user.id, job.id) == 1

    # Re-run → upsert on the unique constraint (no duplicate row, values updated).
    with patch("app.services.match_service.get_registry", return_value=_mock_registry(90, "better")):
        row2 = await MatchService(async_session).analyze(user.id, job.id)

    assert await _match_count(async_session, user.id, job.id) == 1
    assert row2.match_score == 90
    assert row2.match_explanation == "better"


async def test_upsert_preserves_match_score_when_only_materials_written(
    async_session: AsyncSession,
):
    user = await _make_user(async_session)
    job = await _make_job(async_session)

    # Seed a real score.
    await upsert_job_match(
        async_session, user_id=user.id, job_id=job.id,
        match_score=80, match_explanation="scored",
    )
    await async_session.commit()

    # Materials path writes only CV/cover columns — must not clobber match_score.
    await upsert_job_match(
        async_session, user_id=user.id, job_id=job.id,
        cv_tailoring_suggestion="tips", cover_letter_draft="draft",
    )
    await async_session.commit()

    row = (
        await async_session.exec(
            select(JobMatchTable).where(
                JobMatchTable.user_id == user.id, JobMatchTable.job_id == job.id
            )
        )
    ).first()
    assert row.match_score == 80
    assert row.cv_tailoring_suggestion == "tips"
    assert row.cover_letter_draft == "draft"


async def test_analyze_raises_for_missing_user_or_job(async_session: AsyncSession):
    with pytest.raises(ValueError, match="User .* not found"):
        await MatchService(async_session).analyze(999_999, 1)


async def test_new_match_starts_unreviewed(async_session: AsyncSession):
    user = await _make_user(async_session)
    job = await _make_job(async_session)
    await upsert_job_match(async_session, user_id=user.id, job_id=job.id, match_score=50, match_explanation="test")
    await async_session.commit()
    row = (await async_session.exec(select(JobMatchTable).where(JobMatchTable.user_id==user.id, JobMatchTable.job_id==job.id))).first()
    assert row.reviewed_at is None

async def test_mark_job_match_reviewed_sets_timestamp(async_session: AsyncSession):
    user = await _make_user(async_session)
    job = await _make_job(async_session)
    await upsert_job_match(async_session, user_id=user.id, job_id=job.id, match_score=50, match_explanation="test")
    await async_session.commit()
    row = (await async_session.exec(select(JobMatchTable).where(JobMatchTable.user_id==user.id, JobMatchTable.job_id==job.id))).first()
    reviewed = await mark_job_match_reviewed(async_session, row.id)
    assert reviewed.reviewed_at is not None

async def test_mark_job_match_reviewed_raises_for_missing_match(async_session: AsyncSession):
    with pytest.raises(ValueError, match="not found"):
        await mark_job_match_reviewed(async_session, 999_999)

async def test_regenerating_match_resets_review_status(async_session: AsyncSession):
    """The auto-reset behavior in upsert_job_match's _CONTENT_COLUMNS check — this is the exact behavior tonight's manual script proved, now locked in permanently."""
    user = await _make_user(async_session)
    job = await _make_job(async_session)
    await upsert_job_match(async_session, user_id=user.id, job_id=job.id, match_score=50, match_explanation="test")
    await async_session.commit()
    row = (await async_session.exec(select(JobMatchTable).where(JobMatchTable.user_id==user.id, JobMatchTable.job_id==job.id))).first()
    await mark_job_match_reviewed(async_session, row.id)

    # Regenerate WITHOUT passing reviewed_at — this is the auto-reset check.
    await upsert_job_match(async_session, user_id=user.id, job_id=job.id, match_score=60, match_explanation="regenerated")
    await async_session.commit()
    row2 = (await async_session.exec(select(JobMatchTable).where(JobMatchTable.user_id==user.id, JobMatchTable.job_id==job.id).execution_options(populate_existing=True))).first()
    assert row2.reviewed_at is None
