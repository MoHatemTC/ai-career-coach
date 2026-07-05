"""Recommendation work-mode preference filter.

Verifies that `workplace_settings` filters by `jobs.work_mode` — preferred modes
plus unknown (NULL) modes are eligible; other modes are excluded.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.embeddings import EMBEDDING_DIM
from app.models.jobs import JobPosting, UserTable
import app.services.job_recommendation_service as rec

pytestmark = pytest.mark.asyncio


async def _make_user(session: AsyncSession) -> UserTable:
    user = UserTable(
        name="Atef", career_level="mid", years_of_experience=3,
        skills=["python"], tools=["docker"], workplace_settings=["remote"],
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _make_job(session: AsyncSession, *, title: str, work_mode):
    row = JobPosting(
        title=title, company="Acme", location="Cairo, Egypt",
        description="Build Python APIs.", experience_level="mid",
        source="wuzzuf", required_skills=["python"],
        work_mode=work_mode,
    ).to_job_table()
    row.embedding = [0.1] * EMBEDDING_DIM  # non-null so the vector query includes it
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def test_workplace_settings_filters_by_work_mode(async_session: AsyncSession):
    user = await _make_user(async_session)
    remote = await _make_job(async_session, title="Remote Dev", work_mode="remote")
    onsite = await _make_job(async_session, title="Onsite Dev", work_mode="on_site")
    unknown = await _make_job(async_session, title="Unknown Dev", work_mode=None)

    # Mock the embedder (no model call) and the LLM matcher (no LLM call).
    fake_registry = SimpleNamespace(
        aembed=AsyncMock(return_value=[[0.1] * EMBEDDING_DIM]),
        embedding_dim=EMBEDDING_DIM,
    )
    fake_result = SimpleNamespace(
        result=SimpleNamespace(
            total_score=80, explanation="ok", strengths=[], missing_skills=[]
        )
    )
    fake_matcher = SimpleNamespace(execute_match=AsyncMock(return_value=fake_result))

    with patch.object(rec, "get_registry", return_value=fake_registry), patch.object(
        rec, "JobMatchingService", return_value=fake_matcher
    ):
        results = await rec.recommend_jobs_for_user(user.id, async_session)

    returned_ids = {r["job"]["id"] for r in results}
    assert remote.id in returned_ids       # preferred mode → included
    assert unknown.id in returned_ids      # unknown mode → not pruned
    assert onsite.id not in returned_ids   # non-preferred mode → excluded
