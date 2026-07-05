"""Tests for the reshaped POST /applications endpoint ({user_id, job_id})."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.jobs import JobPosting, UserTable
from app.schemas.application_ai import CVTailoringResult, CoverLetterResult

pytestmark = pytest.mark.asyncio


async def _make_user(session: AsyncSession) -> UserTable:
    user = UserTable(name="Atef", email="atef@example.com", career_level="mid",
                     years_of_experience=3, skills=["python"], tools=["docker"])
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _make_job(session: AsyncSession):
    row = JobPosting(
        title="Backend Engineer", company="Breadfast", location="Cairo, Egypt",
        description="Build Python APIs.", experience_level="mid",
        source="wuzzuf", required_skills=["python"],
    ).to_job_table()
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


def _mock_registry():
    reg = MagicMock()
    reg.acomplete = AsyncMock(side_effect=[
        CVTailoringResult(
            tailored_summary="Python dev...", highlighted_skills=["python"],
            missing_skills=[], bullet_point_suggestions=["do x"],
        ),
        CoverLetterResult(draft_content="Dear Hiring Manager...", tone_analysis="pro"),
    ])
    return reg


async def test_generate_materials_persists_and_returns(
    async_session: AsyncSession, async_client: AsyncClient
):
    user = await _make_user(async_session)
    job = await _make_job(async_session)

    with patch(
        "app.services.application_ai_service.get_registry", return_value=_mock_registry()
    ):
        resp = await async_client.post(
            "/api/v1/applications/", json={"user_id": user.id, "job_id": job.id}
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["cv_tailoring"]["tailored_summary"] == "Python dev..."
    assert body["cover_letter"]["draft_content"].startswith("Dear Hiring Manager")

    # Persisted → readable via the tracking materials endpoint.
    read = await async_client.get(
        f"/api/v1/tracking/jobs/{job.id}/application-materials",
        params={"user_id": user.id},
    )
    assert read.status_code == 200
    materials = read.json()
    assert materials["cv_tailoring_suggestion"]["tailored_summary"] == "Python dev..."
    assert materials["cover_letter_draft"]["draft_content"].startswith("Dear Hiring")


async def test_generate_materials_404_for_missing_user_or_job(
    async_session: AsyncSession, async_client: AsyncClient
):
    job = await _make_job(async_session)
    r1 = await async_client.post(
        "/api/v1/applications/", json={"user_id": 999999, "job_id": job.id}
    )
    assert r1.status_code == 404

    user = await _make_user(async_session)
    r2 = await async_client.post(
        "/api/v1/applications/", json={"user_id": user.id, "job_id": 999999}
    )
    assert r2.status_code == 404
