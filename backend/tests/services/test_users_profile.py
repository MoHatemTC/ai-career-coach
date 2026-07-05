"""Tests for the user profile / preferences endpoints."""

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.jobs import UserTable

pytestmark = pytest.mark.asyncio


async def _make_user(session: AsyncSession) -> UserTable:
    user = UserTable(name="Atef", career_level="mid", years_of_experience=3,
                     skills=["python"], tools=["docker"])
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def test_get_profile_returns_facts_and_empty_prefs(
    async_session: AsyncSession, async_client: AsyncClient
):
    user = await _make_user(async_session)
    resp = await async_client.get(f"/api/v1/users/{user.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["skills"] == ["python"]
    # Preferences start empty (not CV-parsed).
    assert body["desired_roles"] == []
    assert body["workplace_settings"] == []


async def test_patch_preferences_partial_update(
    async_session: AsyncSession, async_client: AsyncClient
):
    user = await _make_user(async_session)

    resp = await async_client.patch(
        f"/api/v1/users/{user.id}/preferences",
        json={"desired_roles": ["ai engineer"], "workplace_settings": ["remote"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["desired_roles"] == ["ai engineer"]
    assert body["workplace_settings"] == ["remote"]
    # Untouched fields remain unchanged.
    assert body["skills"] == ["python"]
    assert body["job_titles"] == []


async def test_patch_preferences_rejects_bad_workplace(
    async_session: AsyncSession, async_client: AsyncClient
):
    user = await _make_user(async_session)
    resp = await async_client.patch(
        f"/api/v1/users/{user.id}/preferences",
        json={"workplace_settings": ["office"]},  # not in {remote,hybrid,on_site}
    )
    assert resp.status_code == 422


async def test_profile_404_for_missing_user(async_client: AsyncClient):
    assert (await async_client.get("/api/v1/users/999999")).status_code == 404
    resp = await async_client.patch(
        "/api/v1/users/999999/preferences", json={"desired_roles": ["x"]}
    )
    assert resp.status_code == 404
