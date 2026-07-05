import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.role_benchmark import RoleBenchmark as RoleBenchmarkModel
from app.models.readiness_score import ReadinessScore as ReadinessScoreModel
from app.models.career_roadmap import CareerRoadmap as CareerRoadmapModel
from app.models.jobs import UserTable

pytestmark = pytest.mark.asyncio


def _make_week(n: int) -> dict:
    return {
        "week_number": n,
        "theme": f"Week {n} theme",
        "actions": [
            {
                "action": "Do the thing",
                "category": "skill_building",
                "priority": "critical",
                "estimated_hours": 5,
                "traced_to": "Critical gap: Test",
            }
        ],
    }


async def _make_roadmap(session: AsyncSession) -> CareerRoadmapModel:
    benchmark = RoleBenchmarkModel(
        must_have_skills=["Python"], nice_to_have_skills=[], required_tools=[],
        common_responsibilities=[], minimum_years=3, seniority_level="Mid",
    )
    session.add(benchmark)
    await session.commit()
    await session.refresh(benchmark)

    user = UserTable(name="Test User", career_level="mid", years_of_experience=3, skills=["Python"], tools=["Git"])
    session.add(user)
    await session.commit()
    await session.refresh(user)

    score = ReadinessScoreModel(
        benchmark_id=benchmark.id, user_id=user.id, overall_score=70,
        must_have_skills_score=30, tools_score=20, experience_score=15, soft_skills_score=5,
    )
    session.add(score)
    await session.commit()
    await session.refresh(score)

    # RoadmapResponse inherits weeks: List[RoadmapWeek] = Field(min_length=4, max_length=4)
    # from CareerRoadmapLLMOutput — must seed exactly 4 to match what real LLM
    # output always produces, or response construction will raise a ValidationError.
    roadmap = CareerRoadmapModel(
        readiness_score_id=score.id,
        weeks=[_make_week(n) for n in range(1, 5)],
        executive_summary="Test summary",
        key_focus_areas=["Testing"],
        responsible_ai_disclaimer="Test disclaimer",
    )
    session.add(roadmap)
    await session.commit()
    await session.refresh(roadmap)
    return roadmap


async def test_review_roadmap_endpoint_success(async_client: AsyncClient, async_session: AsyncSession):
    roadmap = await _make_roadmap(async_session)

    response = await async_client.patch(f"/api/v1/roadmaps/{roadmap.id}/review")
    assert response.status_code == 200
    data = response.json()
    # Confirms the flat-dicts-to-nested-Pydantic coercion actually works.
    assert len(data["weeks"]) == 4
    assert data["weeks"][0]["actions"][0]["category"] == "skill_building"
    assert data["reviewed_at"] is not None


async def test_review_roadmap_endpoint_404_for_missing_roadmap(async_client: AsyncClient):
    response = await async_client.patch("/api/v1/roadmaps/999999/review")
    assert response.status_code == 404
