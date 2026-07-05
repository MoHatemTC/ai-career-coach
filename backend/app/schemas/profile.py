"""Schemas for the user profile / preferences endpoints.

Career preferences are **user-supplied** (not inferred from the CV). These schemas
carry OpenAPI examples so Swagger UI shows real request/response payloads.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator

# Must match the values allowed on jobs.work_mode.
_WORKPLACE_VALUES = {"remote", "hybrid", "on_site"}


class ProfilePreferencesIn(BaseModel):
    """Partial update of a user's career preferences.

    All fields are optional — only the fields you send are updated.
    """

    desired_roles: Optional[list[str]] = None
    job_titles: Optional[list[str]] = None
    job_categories: Optional[list[str]] = None
    workplace_settings: Optional[list[str]] = None
    preferred_location: Optional[str] = None

    @field_validator("workplace_settings")
    @classmethod
    def _validate_workplace(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return v
        bad = [x for x in v if x not in _WORKPLACE_VALUES]
        if bad:
            raise ValueError(
                f"workplace_settings must be a subset of {sorted(_WORKPLACE_VALUES)}; "
                f"got invalid values {bad}"
            )
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "desired_roles": ["ai engineer", "ml engineer"],
                "job_titles": ["senior backend engineer"],
                "job_categories": ["machine learning", "software engineering"],
                "workplace_settings": ["remote", "hybrid"],
                "preferred_location": "cairo, egypt",
            }
        }
    }


class UserProfileOut(BaseModel):
    """A user's stored profile (facts + preferences)."""

    id: int
    name: str
    email: Optional[str] = None
    years_of_experience: int
    career_level: str
    education: Optional[str] = None
    preferred_location: Optional[str] = None

    # Facts
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    completed_courses: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)

    # Preferences (user-supplied)
    desired_roles: list[str] = Field(default_factory=list)
    job_titles: list[str] = Field(default_factory=list)
    job_categories: list[str] = Field(default_factory=list)
    workplace_settings: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}
