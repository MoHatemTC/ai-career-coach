import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_job_tracking_pipeline(async_client: AsyncClient):
    # Try getting tracking for a non-existent job
    response = await async_client.get("/api/v1/tracking/jobs/999?user_id=1")
    assert response.status_code == 404
    
    # Try getting market trends
    response = await async_client.get("/api/v1/trends")
    assert response.status_code == 200
    data = response.json()
    assert "top_companies" in data
    assert isinstance(data["top_companies"], list)
