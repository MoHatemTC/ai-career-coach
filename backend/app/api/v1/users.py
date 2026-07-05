"""
User profile API — /api/v1/users

- GET  /users/{user_id}              → read the stored profile
- PATCH /users/{user_id}/preferences → set career preferences (user-supplied)

Career preferences (desired_roles, job_titles, job_categories, workplace_settings,
preferred_location) are collected here, NOT inferred from the CV. They drive the
recommendation engine (semantic steering + work-mode filter).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.connection import get_session
from app.models.helpers import _utcnow
from app.models.jobs import UserTable
from app.schemas.profile import ProfilePreferencesIn, UserProfileOut

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/{user_id}", response_model=UserProfileOut)
async def get_user_profile(
    user_id: int,
    session: AsyncSession = Depends(get_session),
) -> UserProfileOut:
    """Return the stored profile (facts + preferences) for a user."""
    user = await session.get(UserTable, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return UserProfileOut.model_validate(user)


@router.patch("/{user_id}/preferences", response_model=UserProfileOut)
async def update_preferences(
    user_id: int,
    body: ProfilePreferencesIn,
    session: AsyncSession = Depends(get_session),
) -> UserProfileOut:
    """Update a user's career preferences (partial — only provided fields change)."""
    user = await session.get(UserTable, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(user, field, value)
    user.updated_at = _utcnow()

    session.add(user)
    await session.commit()
    await session.refresh(user)
    return UserProfileOut.model_validate(user)
