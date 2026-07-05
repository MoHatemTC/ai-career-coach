import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.jobs import JobPosting, UserTable
from app.services.match_service import upsert_job_match
from app.schemas.role_benchmark import RoleBenchmark as RoleBenchmarkSchema
from app.schemas.readiness_score import ReadinessGapAnalysis, SubScores

pytestmark = pytest.mark.asyncio


async def _make_user(session: AsyncSession) -> UserTable:
    user = UserTable(name="Test", career_level="mid", years_of_experience=3, skills=["Python"], tools=["Docker"])
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _make_job(session: AsyncSession):
    row = JobPosting(
        title="Backend Engineer", company="TestCo", location="Cairo, Egypt",
        description="We are looking for a backend engineer who can build and scale complex APIs for our platform.", experience_level="mid", source="wuzzuf",
        required_skills=["python"],
    ).to_job_table()
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def test_review_match_endpoint_success(async_client: AsyncClient, async_session: AsyncSession):
    user = await _make_user(async_session)
    job = await _make_job(async_session)
    await upsert_job_match(async_session, user_id=user.id, job_id=job.id, match_score=50, match_explanation="test")
    await async_session.commit()

    from sqlmodel import select
    from app.models.jobs import JobMatchTable
    row = (await async_session.exec(select(JobMatchTable).where(JobMatchTable.user_id == user.id, JobMatchTable.job_id == job.id))).first()

    response = await async_client.patch(f"/api/v1/matches/{row.id}/review")
    assert response.status_code == 200
    data = response.json()
    assert data["reviewed_at"] is not None
    assert data["id"] == row.id


async def test_review_match_endpoint_404_for_missing_match(async_client: AsyncClient):
    response = await async_client.patch("/api/v1/matches/999999/review")
    assert response.status_code == 404


def _make_fake_benchmark_state(raw_text: str) -> dict:
    return {
        "raw_text": raw_text,
        "extracted_data": RoleBenchmarkSchema(
            must_have_skills=["Python", "FastAPI"],
            nice_to_have_skills=["Docker"],
            required_tools=["Git", "PostgreSQL"],
            minimum_years=3,
            seniority_level="Mid-Level",
            common_responsibilities=["Develop APIs"],
        ),
        "embedding": [0.1] * 768,
        "error_count": 0,
        "validation_errors": [],
    }


def _make_fake_readiness_state(request, benchmark, candidate_profile) -> dict:
    return {
        "request": request,
        "candidate_profile": candidate_profile,
        "benchmark": benchmark,
        "analysis": ReadinessGapAnalysis(
            overall_score=60,
            sub_scores=SubScores(
                must_have_skills_score=25, tools_score=15,
                experience_score=15, soft_skills_score=5,
            ),
            critical_gaps=["FastAPI"],
            nice_to_have_gaps=["Docker"],
            strengths=["Python"],
            explanation="Test explanation.",
        ),
        "error_count": 0,
        "validation_errors": [],
    }


async def test_deepen_match_endpoint_success(async_client: AsyncClient, async_session: AsyncSession, monkeypatch):
    user = await _make_user(async_session)
    job = await _make_job(async_session)
    await upsert_job_match(async_session, user_id=user.id, job_id=job.id, match_score=50, match_explanation="test")
    await async_session.commit()

    from sqlmodel import select
    from app.models.jobs import JobMatchTable
    match = (await async_session.exec(select(JobMatchTable).where(JobMatchTable.user_id == user.id, JobMatchTable.job_id == job.id))).first()

    async def fake_benchmark_pipeline(raw_text, registry=None):
        return _make_fake_benchmark_state(raw_text)

    async def fake_readiness_pipeline(request, benchmark, candidate_profile, registry=None):
        return _make_fake_readiness_state(request, benchmark, candidate_profile)

    monkeypatch.setattr("app.api.v1.matches.run_benchmark_pipeline", fake_benchmark_pipeline)
    monkeypatch.setattr("app.api.v1.matches.run_readiness_pipeline", fake_readiness_pipeline)

    response = await async_client.post(f"/api/v1/matches/{match.id}/deepen")
    assert response.status_code == 201
    data = response.json()
    assert data["job_match_id"] == match.id
    assert data["user_id"] == user.id
    assert data["benchmark_id"] is not None
    assert data["sub_scores"]["must_have_skills_score"] == 25
    assert data["critical_gaps"] == ["FastAPI"]


async def test_deepen_match_endpoint_404_for_missing_match(async_client: AsyncClient):
    response = await async_client.post("/api/v1/matches/999999/deepen")
    assert response.status_code == 404


async def test_deepen_match_endpoint_422_for_short_job_description(async_client: AsyncClient, async_session: AsyncSession):
    user = await _make_user(async_session)
    from app.models.jobs import JobPosting
    short_job = JobPosting(
        title="Backend Engineer", company="TestCo", location="Cairo, Egypt",
        description="Too short.", experience_level="mid", source="wuzzuf",
        required_skills=["python"],
    ).to_job_table()
    async_session.add(short_job)
    await async_session.commit()
    await async_session.refresh(short_job)

    await upsert_job_match(async_session, user_id=user.id, job_id=short_job.id, match_score=50, match_explanation="test")
    await async_session.commit()

    from sqlmodel import select
    from app.models.jobs import JobMatchTable
    match = (await async_session.exec(select(JobMatchTable).where(JobMatchTable.user_id == user.id, JobMatchTable.job_id == short_job.id))).first()

    response = await async_client.post(f"/api/v1/matches/{match.id}/deepen")
    assert response.status_code == 422
