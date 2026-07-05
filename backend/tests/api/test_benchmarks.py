import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.role_benchmark import RoleBenchmark as RoleBenchmarkModel

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


async def test_review_benchmark_endpoint_success(async_client: AsyncClient, async_session: AsyncSession):
    benchmark = await _make_benchmark(async_session)

    response = await async_client.patch(f"/api/v1/benchmarks/{benchmark.id}/review")
    assert response.status_code == 200
    data = response.json()
    # This is the exact trap found tonight: review_required must be computed
    # from reviewed_at, not silently fall back to its True default.
    assert data["review_required"] is False
    assert data["reviewed_at"] is not None


async def test_review_benchmark_endpoint_404_for_missing_benchmark(async_client: AsyncClient):
    response = await async_client.patch("/api/v1/benchmarks/999999/review")
    assert response.status_code == 404
