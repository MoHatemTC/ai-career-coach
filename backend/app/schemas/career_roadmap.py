"""
app/schemas/career_roadmap.py
==============================
Pydantic v2 schemas for the **Personalized Career Roadmap** feature.

Two groups of models are defined here:

1. **LLM output contract** (``RoadmapAction``, ``RoadmapWeek``,
   ``CareerRoadmapLLMOutput``)
   These are passed as ``response_format`` to
   :meth:`~app.ai.registry.LLMServiceRegistry.acomplete` so litellm requests
   structured JSON output and parses it automatically.

2. **API surface** (``RoadmapRequest``, ``RoadmapResponse``)
   These drive FastAPI's request validation and OpenAPI documentation.

Action categories
-----------------
| Category           | Description                                      |
|--------------------|--------------------------------------------------|
| skill_building     | Learning a new skill or deepening an existing one |
| portfolio_project  | Building a project to showcase competence         |
| cv_enhancement     | Improving CV content, formatting, or keywords     |
| interview_prep     | Mock interviews, behavioral prep, coding drills   |

Traceability
------------
Every ``RoadmapAction`` includes a ``traced_to`` field that references the
specific benchmark gap or profile weakness that motivates the action.  This
ensures all recommendations are defensible and auditable.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ActionCategory(str, Enum):
    """Category of a roadmap action item."""

    skill_building = "skill_building"
    portfolio_project = "portfolio_project"
    cv_enhancement = "cv_enhancement"
    interview_prep = "interview_prep"


class ActionPriority(str, Enum):
    """Priority level of a roadmap action item."""

    critical = "critical"
    high = "high"
    medium = "medium"


# ---------------------------------------------------------------------------
# Sub-schemas: LLM structured output
# ---------------------------------------------------------------------------


class RoadmapAction(BaseModel):
    """
    A single actionable item within a roadmap week.

    Each action is traceable to a specific gap or weakness identified in the
    readiness assessment, ensuring recommendations are evidence-based and
    auditable.
    """

    action: str = Field(
        description=(
            "A clear, specific, and actionable task description. "
            "Example: 'Complete a hands-on Docker tutorial and containerise "
            "a sample Python API.'"
        ),
    )
    category: ActionCategory = Field(
        description=(
            "The type of improvement this action addresses: "
            "skill_building, portfolio_project, cv_enhancement, or interview_prep."
        ),
    )
    priority: ActionPriority = Field(
        description=(
            "Priority level based on impact: "
            "critical (blocks hiring readiness), "
            "high (significantly improves candidacy), "
            "medium (nice-to-have improvement)."
        ),
    )
    estimated_hours: int = Field(
        ge=1,
        le=40,
        description=(
            "Estimated effort in hours to complete this action. "
            "Must be between 1 and 40 hours."
        ),
    )
    traced_to: str = Field(
        description=(
            "The specific benchmark gap or profile weakness this action "
            "addresses. Must reference a concrete item from critical_gaps, "
            "nice_to_have_gaps, or an identified weakness. "
            "Example: 'Critical gap: Docker' or 'Nice-to-have gap: Kubernetes'."
        ),
    )


class RoadmapWeek(BaseModel):
    """
    A single week's plan within the 30-day roadmap.

    Each week has a theme and a list of prioritised action items that build
    progressively toward closing the candidate's most impactful gaps.
    """

    week_number: int = Field(
        ge=1,
        le=4,
        description="Week number within the 30-day plan (1–4).",
    )
    theme: str = Field(
        description=(
            "A short descriptive theme for the week. "
            "Example: 'Foundation Building — Core Skill Gaps'."
        ),
    )
    actions: List[RoadmapAction] = Field(
        min_length=1,
        description=(
            "Ordered list of action items for this week. "
            "Each action is traceable to a benchmark gap or weakness."
        ),
    )


class CareerRoadmapLLMOutput(BaseModel):
    """
    Structured output returned by the LLM career roadmap generation call.

    This model is used both as the ``response_format`` for the LiteLLM
    structured-output request *and* as the core payload embedded in
    :class:`RoadmapResponse`.
    """

    weeks: List[RoadmapWeek] = Field(
        min_length=4,
        max_length=4,
        description=(
            "Exactly four weeks of structured action plans. "
            "Week 1 focuses on critical gaps, weeks 2–3 on skill building "
            "and portfolio projects, and week 4 on CV polish and interview prep."
        ),
    )
    executive_summary: str = Field(
        description=(
            "A 3–5 sentence overview of the roadmap strategy, covering "
            "the candidate's current position, the key focus areas, and "
            "the expected outcome after completing the 30-day plan."
        ),
    )
    key_focus_areas: List[str] = Field(
        min_length=1,
        description=(
            "Top 3–5 focus areas derived from the gap analysis. "
            "Each must correspond to a critical or nice-to-have gap."
        ),
    )
    responsible_ai_disclaimer: str = Field(
        description=(
            "A responsible AI disclaimer acknowledging that this roadmap "
            "is an AI-generated suggestion and does not guarantee "
            "employment outcomes. Must be present in every response."
        ),
    )


# ---------------------------------------------------------------------------
# API request schema
# ---------------------------------------------------------------------------


class RoadmapRequest(BaseModel):
    """
    Request body for ``POST /api/v1/roadmaps/generate``.

    The caller supplies the integer primary key of a previously generated
    :class:`~app.models.readiness_score.ReadinessScore` record.  The
    service layer loads the associated benchmark and gap analysis from the
    database to generate the roadmap.
    """

    readiness_score_id: int = Field(
        gt=0,
        description=(
            "Primary key of the target ReadinessScore record in the database. "
            "Obtain this from the ``id`` field returned by "
            "``POST /api/v1/readiness/score``."
        ),
    )
    focus_areas: Optional[List[ActionCategory]] = Field(
        default=None,
        description=(
            "Optional filter to restrict roadmap actions to specific "
            "categories. If omitted, all four categories are included."
        ),
    )


# ---------------------------------------------------------------------------
# API response schema
# ---------------------------------------------------------------------------


class RoadmapResponse(CareerRoadmapLLMOutput):
    """
    Response returned by ``POST /api/v1/roadmaps/generate``.

    Extends :class:`CareerRoadmapLLMOutput` with the database primary key,
    the readiness score reference, and the persistence timestamp.
    """

    id: int = Field(
        description="Database primary key of the persisted CareerRoadmap record."
    )
    readiness_score_id: int = Field(
        description="Primary key of the ReadinessScore used for this roadmap."
    )
    created_at: datetime = Field(
        description="UTC timestamp of when the roadmap was generated and persisted."
    )
    reviewed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
