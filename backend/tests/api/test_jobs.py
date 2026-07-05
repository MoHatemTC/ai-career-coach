import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_list_sources(async_client: AsyncClient):
    response = await async_client.get("/api/v1/jobs/sources")
    assert response.status_code == 200
    data = response.json()
    assert "sources" in data
    assert isinstance(data["sources"], list)

@pytest.mark.asyncio
async def test_list_jobs_empty(async_client: AsyncClient):
    response = await async_client.get("/api/v1/jobs")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["jobs"] == []
