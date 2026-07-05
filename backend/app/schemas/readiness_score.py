"""
app/schemas/readiness_score.py
==============================
Pydantic v2 schemas for the **Career Readiness Score** feature.

Two groups of models are defined here:

1. **LLM output contract** (``ReadinessGapAnalysis`` + ``SubScores``)
   These are passed as ``response_format`` to
   :meth:`~app.ai.registry.LLMServiceRegistry.complete` so litellm requests
   structured JSON output and parses it automatically.

2. **API surface** (``CandidateProfile``, ``ReadinessRequest``,
   ``ReadinessResponse``)
   These drive FastAPI's request validation and OpenAPI documentation.

Scoring rubric
--------------
| Dimension             | Max points |
|-----------------------|-----------|
| Must-have skills      | 40        |
| Required tools        | 25        |
| Experience level      | 25        |
| Soft skills / education | 10      |
| **Total**             | **100**   |

Gap classification
------------------
* **Critical gap** — a benchmark ``must_have_skill`` or ``required_tool``
  that the candidate does not possess.
* **Nice-to-have gap** — a benchmark ``nice_to_have_skill`` that the
  candidate does not possess.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Sub-schemas: LLM structured output
# ---------------------------------------------------------------------------


class SubScores(BaseModel):
    """
    Dimensional breakdown of the overall readiness score.

    All values are non-negative integers.  The sum of all sub-scores equals
    ``overall_score`` in the parent :class:`ReadinessGapAnalysis`.

    Rubric (max points per dimension):
    * ``must_have_skills_score`` — 40 pts
    * ``tools_score``            — 25 pts
    * ``experience_score``       — 25 pts
    * ``soft_skills_score``      — 10 pts
    """

    must_have_skills_score: int = Field(
        ge=0,
        le=40,
        description=(
            "Score for conceptual / must-have skill coverage. "
            "Maximum 40 points."
        ),
    )
    tools_score: int = Field(
        ge=0,
        le=25,
        description=(
            "Score for required-tool coverage. "
            "Maximum 25 points."
        ),
    )
    experience_score: int = Field(
        ge=0,
        le=25,
        description=(
            "Score for years-of-experience fit relative to the benchmark minimum. "
            "Maximum 25 points."
        ),
    )
    soft_skills_score: int = Field(
        ge=0,
        le=10,
        description=(
            "Score for soft skills, education, and domain knowledge breadth. "
            "Maximum 10 points."
        ),
    )


class ReadinessGapAnalysis(BaseModel):
    """
    Structured output returned by the LLM gap-analysis call.

    This model is used both as the ``response_format`` for the LiteLLM
    structured-output request *and* as the core payload embedded in
    :class:`ReadinessResponse`.
    """

    overall_score: int = Field(
        ge=0,
        le=100,
        description=(
            "Composite readiness score in the range [0, 100]. "
            "Must equal the sum of all sub-scores."
        ),
    )
    sub_scores: SubScores = Field(
        description="Dimensional breakdown of the overall score."
    )
    critical_gaps: List[str] = Field(
        description=(
            "Must-have skills or required tools from the benchmark that the "
            "candidate demonstrably lacks. These are the primary blockers to "
            "hiring readiness."
        ),
    )
    nice_to_have_gaps: List[str] = Field(
        description=(
            "Nice-to-have skills from the benchmark that the candidate lacks. "
            "These are non-blocking but represent growth opportunities."
        ),
    )
    strengths: List[str] = Field(
        description=(
            "Concrete skills, tools, or experience areas where the candidate "
            "meets or exceeds the benchmark requirements."
        ),
    )
    explanation: str = Field(
        description=(
            "A concise, human-readable explanation (2–5 sentences) of the "
            "overall readiness assessment, key blockers, and top actionable "
            "recommendation for the candidate."
        ),
    )


# ---------------------------------------------------------------------------
# API request schema
# ---------------------------------------------------------------------------


class ReadinessRequest(BaseModel):
    """
    Request body for ``POST /api/v1/readiness/score``.

    The caller supplies the integer primary key of a previously extracted
    :class:`~app.models.role_benchmark.RoleBenchmark` record together with
    the user's ID to look up their profile.
    """

    benchmark_id: int = Field(
        gt=0,
        description=(
            "Primary key of the target RoleBenchmark record in the database. "
            "Obtain this from the ``id`` field returned by "
            "``POST /api/v1/benchmarks/analyze``."
        ),
    )
    user_id: int = Field(
        gt=0,
        description=(
            "Primary key of the target User record in the database."
        )
    )


# ---------------------------------------------------------------------------
# API response schema
# ---------------------------------------------------------------------------


class ReadinessResponse(ReadinessGapAnalysis):
    """
    Response returned by ``POST /api/v1/readiness/score``.

    Extends :class:`ReadinessGapAnalysis` with the database primary key,
    the benchmark reference, and the persistence timestamp.
    """

    id: int = Field(
        description="Database primary key of the persisted ReadinessScore record."
    )
    benchmark_id: int = Field(
        description="Primary key of the RoleBenchmark used for this assessment."
    )
    user_id: int = Field(
        description="Primary key of the User evaluated for this assessment."
    )
    job_match_id: Optional[int] = Field(
        default=None,
        description="Primary key of the JobMatch, if this score was generated by deepening a match."
    )
    created_at: datetime = Field(
        description="UTC timestamp of when the readiness score was persisted."
    )
    reviewed_at: Optional[datetime] = Field(
        default=None,
        description=(
            "UTC timestamp of when a human reviewer validated this score. "
            "``null`` until reviewed."
        ),
    )

    model_config = {"from_attributes": True}
