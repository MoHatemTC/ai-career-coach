"""
Tests for Search Orchestration Service (Sprint 4, Task 13).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.jobs import JobPosting, JobTable, LogTable, UserTable
from app.models.notification import NotificationStatus, NotificationTable
from app.services.job_collection_service import SOURCE_REGISTRY
from app.services.job_sources.base import BaseJobSource
from app.services.search_orchestration_service import run_search

# --- Helpers ---

class StubSource(BaseJobSource):
    source_name = "stub"

    def __init__(self, jobs: list[JobPosting] | None = None) -> None:
        self._jobs = jobs or []

    async def fetch(self) -> list[JobPosting]:
        return self._jobs

    def _normalize(self, raw: dict) -> JobPosting | None:
        raise NotImplementedError

async def _make_user(session: AsyncSession, **overrides) -> UserTable:
    defaults = {
        "name": "Test User",
        "email": "test@example.com",
        "years_of_experience": 3,
        "career_level": "mid",
        "skills": ["python", "sql", "fastapi"],
    }
    defaults.update(overrides)
    user = UserTable(**defaults)
    
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user

def _make_posting() -> JobPosting:
    return JobPosting(
        title="Software Engineer",
        company="TechCorp",
        location="Remote",
        description="Looking for Python and FastAPI skills.",
        experience_level="mid",
        source="wuzzuf",
    )

@pytest.fixture
def patch_source_registry(monkeypatch):
    """Monkeypatch SOURCE_REGISTRY to use StubSource."""
    def _get_stub():
        return StubSource([_make_posting()])
    monkeypatch.setitem(SOURCE_REGISTRY, "stub", _get_stub)
    return "stub"

@pytest.fixture(autouse=True)
def mock_embedding_fn(monkeypatch):
    from app.services import job_collection_service
    from app.core.embeddings import EMBEDDING_DIM

    def fake_embed(texts):
        return [[0.0] * EMBEDDING_DIM for _ in texts]

    monkeypatch.setattr(job_collection_service, "embed", fake_embed)

@pytest.fixture
def patch_recommend(monkeypatch):
    from app.services import search_orchestration_service
    async def mock_recommend(user_id: int, session: AsyncSession):
        job = (await session.exec(select(JobTable))).first()
        if not job:
            return []
        return [{"job": {"id": job.id}, "total_score": 85}]
    monkeypatch.setattr(search_orchestration_service, "recommend_jobs_for_user", mock_recommend)

@pytest.mark.asyncio
async def test_run_search_happy_path(async_session: AsyncSession, patch_source_registry: str, patch_recommend):
    """Test 1 - happy path: fetch -> match -> notify."""
    user = await _make_user(async_session)

    result = await run_search(
        async_session,
        source_names=[patch_source_registry],
        user_ids=[user.id],
        notify=True
    )

    assert result.jobs_inserted == 1
    assert result.notifications_sent == 1
    assert result.errors == []

    # Verify DB state
    notifications = (await async_session.exec(select(NotificationTable))).all()
    assert len(notifications) == 1
    assert notifications[0].status == NotificationStatus.SENT
    assert notifications[0].user_id == user.id

    logs = (await async_session.exec(select(LogTable).where(LogTable.stage == "search_run").order_by(LogTable.id))).all()
    # Should have 'started' and 'success' logs
    assert len(logs) == 2
    assert logs[-1].status == "success"


@pytest.mark.asyncio
async def test_run_search_duplicate_prevention(async_session: AsyncSession, patch_source_registry: str, patch_recommend):
    """Test 2 - edge case, duplicate prevention."""
    user = await _make_user(async_session)

    # Run 1
    result1 = await run_search(async_session, source_names=[patch_source_registry], user_ids=[user.id])
    assert result1.notifications_sent == 1
    
    # Run 2
    result2 = await run_search(async_session, source_names=[patch_source_registry], user_ids=[user.id])
    assert result2.jobs_inserted == 0  # Deduplicated
    assert result2.notifications_sent == 0
    assert result2.notifications_skipped_duplicate == 1

    # Verify still exactly one notification
    notifications = (await async_session.exec(select(NotificationTable))).all()
    assert len(notifications) == 1


@pytest.mark.asyncio
async def test_run_search_no_email_user(async_session: AsyncSession, patch_source_registry: str, patch_recommend):
    """Optional - no email user gets SKIPPED."""
    user = await _make_user(async_session, email=None)

    result = await run_search(async_session, source_names=[patch_source_registry], user_ids=[user.id])
    assert result.notifications_skipped_no_email == 1
    assert result.notifications_sent == 0
    assert result.errors == []


@pytest.mark.asyncio
async def test_run_search_resilience(async_session: AsyncSession, patch_source_registry: str, monkeypatch):
    """Optional - resilience when one user fails."""
    user1 = await _make_user(async_session, email="u1@test.com")
    user2 = await _make_user(async_session, email="u2@test.com")

    # Monkeypatch recommend_jobs_for_user to fail for user1
    from app.services import search_orchestration_service

    async def mock_recommend(user_id: int, session: AsyncSession):
        if user_id == user1.id:
            raise ValueError("Simulated ranking failure")
        job = (await session.exec(select(JobTable))).first()
        return [{"job": {"id": job.id}, "total_score": 85}] if job else []

    monkeypatch.setattr(search_orchestration_service, "recommend_jobs_for_user", mock_recommend)

    result = await run_search(async_session, source_names=[patch_source_registry], user_ids=[user1.id, user2.id])
    
    assert len(result.errors) == 1
    assert f"user {user1.id}: Simulated ranking failure" in result.errors[0]
    
    # user2 should still succeed
    assert result.notifications_sent == 1

    logs = (await async_session.exec(select(LogTable).where(LogTable.stage == "search_run").order_by(LogTable.id))).all()
    assert logs[-1].status == "failure"  # Since there were errors
