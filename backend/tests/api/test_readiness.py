import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.role_benchmark import RoleBenchmark as RoleBenchmarkModel
from app.models.readiness_score import ReadinessScore as ReadinessScoreModel
from app.models.jobs import UserTable

pytestmark = pytest.mark.asyncio


async def _make_benchmark(session: AsyncSession) -> RoleBenchmarkModel:
    benchmark = RoleBenchmarkModel(
        must_have_skills=["Python"], nice_to_have_skills=[], required_tools=[],
        common_responsibilities=[], minimum_years=3, seniority_level="Mid",
    )
    session.add(benchmark)
    await session.commit()
    await session.refresh(benchmark)
    return benchmark


async def _make_user(session: AsyncSession) -> UserTable:
    user = UserTable(name="Test User", career_level="mid", years_of_experience=3, skills=["Python"], tools=["Git"])
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _make_readiness_score(session: AsyncSession, benchmark_id: int, user_id: int) -> ReadinessScoreModel:
    score = ReadinessScoreModel(
        benchmark_id=benchmark_id, user_id=user_id, overall_score=70,
        must_have_skills_score=30, tools_score=20, experience_score=15, soft_skills_score=5,
    )
    session.add(score)
    await session.commit()
    await session.refresh(score)
    return score


async def test_review_readiness_score_endpoint_success(async_client: AsyncClient, async_session: AsyncSession):
    benchmark = await _make_benchmark(async_session)
    user = await _make_user(async_session)
    score = await _make_readiness_score(async_session, benchmark.id, user.id)

    response = await async_client.patch(f"/api/v1/readiness/{score.id}/review")
    assert response.status_code == 200
    data = response.json()
    # Confirms the sub_scores nesting is correctly built, not a flat/broken response.
    assert data["sub_scores"] == {
        "must_have_skills_score": 30, "tools_score": 20,
        "experience_score": 15, "soft_skills_score": 5,
    }
    assert data["reviewed_at"] is not None


async def test_review_readiness_score_endpoint_404_for_missing_score(async_client: AsyncClient):
    response = await async_client.patch("/api/v1/readiness/999999/review")
    assert response.status_code == 404
