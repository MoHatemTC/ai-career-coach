"""
tests/services/test_career_roadmap_service.py
===============================================
Tests for the career roadmap generation LangGraph pipeline.

Includes:
- Happy-path test: valid readiness score → realistic 30-day roadmap
- Edge-case test: high-scoring candidate with minimal gaps
- Retry test: ValidationError triggers retry, eventual success
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.role_benchmark import RoleBenchmark as RoleBenchmarkModel
from app.models.readiness_score import ReadinessScore as ReadinessScoreModel
from app.models.career_roadmap import CareerRoadmap as CareerRoadmapModel
from app.models.jobs import UserTable

from app.schemas.career_roadmap import (
    ActionCategory,
    ActionPriority,
    CareerRoadmapLLMOutput,
    RoadmapAction,
    RoadmapWeek,
)
from app.services.career_roadmap_service import (
    MAX_RETRIES,
    RoadmapState,
    build_graph,
    route_after_generate,
    run_roadmap_pipeline,
    save_career_roadmap,
    mark_roadmap_reviewed,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_readiness_score(**overrides):
    """Create a mock ReadinessScore ORM object."""
    defaults = {
        "id": 1,
        "benchmark_id": 10,
        "overall_score": 52,
        "must_have_skills_score": 20,
        "tools_score": 12,
        "experience_score": 14,
        "soft_skills_score": 6,
        "critical_gaps": ["Docker", "Kubernetes"],
        "nice_to_have_gaps": ["GraphQL"],
        "strengths": ["Python (5 years)", "FastAPI", "PostgreSQL"],
        "explanation": (
            "The candidate scores 52/100. Major gaps in containerisation "
            "technologies (Docker, Kubernetes) block hiring readiness."
        ),
        "candidate_skills": ["Python", "API design", "SQL"],
        "candidate_tools": ["Python", "FastAPI", "PostgreSQL"],
        "candidate_experience_years": 5,
    }
    defaults.update(overrides)
    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _make_benchmark(**overrides):
    """Create a mock RoleBenchmark ORM object."""
    defaults = {
        "id": 10,
        "must_have_skills": ["Python", "API design", "Containerisation"],
        "nice_to_have_skills": ["GraphQL", "gRPC"],
        "required_tools": ["Python", "Docker", "Kubernetes", "PostgreSQL"],
        "minimum_years": 3,
        "seniority_level": "Senior",
        "common_responsibilities": [
            "Design and implement microservices",
            "Code review",
            "Mentoring junior developers",
        ],
    }
    defaults.update(overrides)
    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _make_valid_roadmap_output():
    """Create a valid CareerRoadmapLLMOutput for testing."""
    return CareerRoadmapLLMOutput(
        weeks=[
            RoadmapWeek(
                week_number=1,
                theme="Foundation Building — Container Technologies",
                actions=[
                    RoadmapAction(
                        action="Complete Docker official getting-started tutorial and containerise a sample Python Flask API.",
                        category=ActionCategory.skill_building,
                        priority=ActionPriority.critical,
                        estimated_hours=8,
                        traced_to="Critical gap: Docker",
                    ),
                    RoadmapAction(
                        action="Set up a local Kubernetes cluster using minikube and deploy the containerised API.",
                        category=ActionCategory.skill_building,
                        priority=ActionPriority.critical,
                        estimated_hours=10,
                        traced_to="Critical gap: Kubernetes",
                    ),
                ],
            ),
            RoadmapWeek(
                week_number=2,
                theme="Skill Deepening & Portfolio Start",
                actions=[
                    RoadmapAction(
                        action="Build a multi-container microservice project using Docker Compose with FastAPI and PostgreSQL.",
                        category=ActionCategory.portfolio_project,
                        priority=ActionPriority.critical,
                        estimated_hours=15,
                        traced_to="Critical gap: Docker",
                    ),
                    RoadmapAction(
                        action="Add a GraphQL endpoint to the portfolio project using Strawberry.",
                        category=ActionCategory.skill_building,
                        priority=ActionPriority.high,
                        estimated_hours=5,
                        traced_to="Nice-to-have gap: GraphQL",
                    ),
                ],
            ),
            RoadmapWeek(
                week_number=3,
                theme="Portfolio Completion & CV Enhancement",
                actions=[
                    RoadmapAction(
                        action="Write Kubernetes deployment manifests for the portfolio project and deploy to a free-tier cloud.",
                        category=ActionCategory.portfolio_project,
                        priority=ActionPriority.critical,
                        estimated_hours=8,
                        traced_to="Critical gap: Kubernetes",
                    ),
                    RoadmapAction(
                        action="Update CV to add Docker and Kubernetes skills with the portfolio project as evidence.",
                        category=ActionCategory.cv_enhancement,
                        priority=ActionPriority.high,
                        estimated_hours=3,
                        traced_to="Critical gap: Docker",
                    ),
                    RoadmapAction(
                        action="Tailor CV keywords to match the Senior Backend Engineer benchmark requirements.",
                        category=ActionCategory.cv_enhancement,
                        priority=ActionPriority.high,
                        estimated_hours=2,
                        traced_to="Critical gap: Kubernetes",
                    ),
                ],
            ),
            RoadmapWeek(
                week_number=4,
                theme="Interview Preparation & Final Polish",
                actions=[
                    RoadmapAction(
                        action="Complete 3 mock system design interviews focusing on containerised microservice architectures.",
                        category=ActionCategory.interview_prep,
                        priority=ActionPriority.high,
                        estimated_hours=6,
                        traced_to="Critical gap: Kubernetes",
                    ),
                    RoadmapAction(
                        action="Practice Docker and Kubernetes troubleshooting scenarios commonly asked in interviews.",
                        category=ActionCategory.interview_prep,
                        priority=ActionPriority.high,
                        estimated_hours=4,
                        traced_to="Critical gap: Docker",
                    ),
                    RoadmapAction(
                        action="Final CV proofread and formatting check, ensure all quantified achievements are included.",
                        category=ActionCategory.cv_enhancement,
                        priority=ActionPriority.medium,
                        estimated_hours=2,
                        traced_to="Critical gap: Docker",
                    ),
                ],
            ),
        ],
        executive_summary=(
            "The candidate has strong Python and FastAPI foundations (52/100 readiness) "
            "but lacks critical containerisation skills. This 30-day plan prioritises "
            "Docker and Kubernetes mastery through hands-on projects, followed by CV "
            "optimisation and targeted interview preparation. Completing this plan should "
            "meaningfully close the identified skill gaps."
        ),
        key_focus_areas=[
            "Docker containerisation",
            "Kubernetes orchestration",
            "Portfolio project development",
            "CV keyword optimisation",
        ],
        responsible_ai_disclaimer=(
            "This roadmap is an AI-generated career development suggestion based on "
            "automated gap analysis. It does not guarantee employment outcomes, interview "
            "success, or job placement. Individual results depend on effort, market "
            "conditions, and many factors beyond the scope of this assessment. Use this "
            "roadmap as a guide alongside professional career advice."
        ),
    )


def _make_high_score_readiness():
    """Create a readiness score with minimal gaps (score 95)."""
    return _make_readiness_score(
        overall_score=95,
        must_have_skills_score=38,
        tools_score=24,
        experience_score=25,
        soft_skills_score=8,
        critical_gaps=[],
        nice_to_have_gaps=["GraphQL"],
        strengths=[
            "Python (5 years, exceeds 3-year minimum)",
            "Docker",
            "Kubernetes",
            "PostgreSQL",
            "API design",
        ],
        explanation=(
            "The candidate scores 95/100 and is strongly prepared for this role. "
            "Only minor nice-to-have gaps remain in GraphQL."
        ),
    )


def _make_high_score_roadmap_output():
    """Create a roadmap for a high-scoring candidate with minimal gaps."""
    return CareerRoadmapLLMOutput(
        weeks=[
            RoadmapWeek(
                week_number=1,
                theme="Strengthening Existing Skills",
                actions=[
                    RoadmapAction(
                        action="Build a GraphQL API using Strawberry to complement existing REST expertise.",
                        category=ActionCategory.skill_building,
                        priority=ActionPriority.high,
                        estimated_hours=10,
                        traced_to="Nice-to-have gap: GraphQL",
                    ),
                ],
            ),
            RoadmapWeek(
                week_number=2,
                theme="Advanced Portfolio Development",
                actions=[
                    RoadmapAction(
                        action="Create a showcase project combining FastAPI, GraphQL, and Docker demonstrating full-stack capability.",
                        category=ActionCategory.portfolio_project,
                        priority=ActionPriority.high,
                        estimated_hours=12,
                        traced_to="Nice-to-have gap: GraphQL",
                    ),
                ],
            ),
            RoadmapWeek(
                week_number=3,
                theme="CV Optimisation for Senior Roles",
                actions=[
                    RoadmapAction(
                        action="Rewrite CV with quantified achievements and senior-level language emphasising leadership.",
                        category=ActionCategory.cv_enhancement,
                        priority=ActionPriority.high,
                        estimated_hours=4,
                        traced_to="Nice-to-have gap: GraphQL",
                    ),
                ],
            ),
            RoadmapWeek(
                week_number=4,
                theme="Interview Mastery",
                actions=[
                    RoadmapAction(
                        action="Complete 5 mock system design interviews focusing on microservice architecture patterns.",
                        category=ActionCategory.interview_prep,
                        priority=ActionPriority.high,
                        estimated_hours=10,
                        traced_to="Nice-to-have gap: GraphQL",
                    ),
                ],
            ),
        ],
        executive_summary=(
            "The candidate is exceptionally well-prepared (95/100) with only minor "
            "nice-to-have gaps. This 30-day plan focuses on adding GraphQL expertise, "
            "building a showcase portfolio project, and refining interview skills to "
            "maximise competitiveness for senior roles."
        ),
        key_focus_areas=[
            "GraphQL API development",
            "Portfolio showcase project",
            "Interview preparation",
        ],
        responsible_ai_disclaimer=(
            "This roadmap is an AI-generated career development suggestion based on "
            "automated gap analysis. It does not guarantee employment outcomes."
        ),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRouteAfterGenerate:
    """Unit tests for the conditional edge routing function."""

    def test_returns_end_on_success(self):
        """When roadmap is present, route to END."""
        state: RoadmapState = {
            "readiness_score": _make_readiness_score(),
            "benchmark": _make_benchmark(),
            "roadmap": _make_valid_roadmap_output(),
            "error_count": 0,
            "validation_errors": [],
        }
        result = route_after_generate(state)
        assert result == "__end__"  # langgraph.graph.END

    def test_retries_on_failure_with_remaining_attempts(self):
        """When roadmap is None and retries remain, route to generate."""
        state: RoadmapState = {
            "readiness_score": _make_readiness_score(),
            "benchmark": _make_benchmark(),
            "roadmap": None,
            "error_count": 1,
            "validation_errors": ["some error"],
        }
        result = route_after_generate(state)
        assert result == "generate"

    def test_raises_after_max_retries(self):
        """When roadmap is None and MAX_RETRIES reached, raise ValueError."""
        state: RoadmapState = {
            "readiness_score": _make_readiness_score(),
            "benchmark": _make_benchmark(),
            "roadmap": None,
            "error_count": MAX_RETRIES,
            "validation_errors": ["error1", "error2", "error3"],
        }
        with pytest.raises(ValueError, match="failed after"):
            route_after_generate(state)


class TestRunRoadmapPipelineHappyPath:
    """Happy-path test: valid readiness score → realistic 30-day roadmap."""

    @pytest.mark.asyncio
    async def test_generates_valid_roadmap(self):
        """A sample readiness score generates a realistic 30-day roadmap."""
        valid_output = _make_valid_roadmap_output()

        mock_registry = MagicMock()
        mock_registry.acomplete = AsyncMock(return_value=valid_output)

        readiness_score = _make_readiness_score()
        benchmark = _make_benchmark()

        final_state = await run_roadmap_pipeline(
            readiness_score=readiness_score,
            benchmark=benchmark,
            registry=mock_registry,
        )

        # ── Assert pipeline succeeded ────────────────────────────
        assert final_state["roadmap"] is not None
        assert final_state["error_count"] == 0

        roadmap = final_state["roadmap"]

        # ── Assert 4-week structure ──────────────────────────────
        assert len(roadmap.weeks) == 4
        for i, week in enumerate(roadmap.weeks, start=1):
            assert week.week_number == i
            assert len(week.theme) > 0
            assert len(week.actions) >= 1

        # ── Assert traceability ──────────────────────────────────
        all_actions = [a for w in roadmap.weeks for a in w.actions]
        for action in all_actions:
            assert len(action.traced_to) > 0, (
                f"Action '{action.action}' is missing traced_to"
            )

        # ── Assert all 4 categories are represented ──────────────
        categories = {a.category for a in all_actions}
        assert ActionCategory.skill_building in categories
        assert ActionCategory.portfolio_project in categories
        assert ActionCategory.cv_enhancement in categories
        assert ActionCategory.interview_prep in categories

        # ── Assert responsible AI disclaimer ─────────────────────
        assert len(roadmap.responsible_ai_disclaimer) > 0
        assert "guarantee" not in roadmap.responsible_ai_disclaimer.lower() or \
               "not guarantee" in roadmap.responsible_ai_disclaimer.lower() or \
               "does not guarantee" in roadmap.responsible_ai_disclaimer.lower()

        # ── Assert executive summary ─────────────────────────────
        assert len(roadmap.executive_summary) > 0

        # ── Assert key focus areas ───────────────────────────────
        assert len(roadmap.key_focus_areas) >= 1

        # ── Assert LLM was called with correct format ────────────
        mock_registry.acomplete.assert_called_once()
        call_kwargs = mock_registry.acomplete.call_args
        assert call_kwargs.kwargs.get("response_format") == CareerRoadmapLLMOutput


class TestRunRoadmapPipelineEdgeCases:
    """Edge-case tests for the roadmap pipeline."""

    @pytest.mark.asyncio
    async def test_high_score_candidate_focuses_on_nice_to_haves(self):
        """
        When candidate has score 95+ with no critical gaps, the roadmap
        focuses on nice-to-have improvements and interview prep.
        """
        high_score_output = _make_high_score_roadmap_output()

        mock_registry = MagicMock()
        mock_registry.acomplete = AsyncMock(return_value=high_score_output)

        readiness_score = _make_high_score_readiness()
        benchmark = _make_benchmark()

        final_state = await run_roadmap_pipeline(
            readiness_score=readiness_score,
            benchmark=benchmark,
            registry=mock_registry,
        )

        assert final_state["roadmap"] is not None
        roadmap = final_state["roadmap"]

        # ── No actions should be critical priority ───────────────
        all_actions = [a for w in roadmap.weeks for a in w.actions]
        critical_actions = [a for a in all_actions if a.priority == ActionPriority.critical]
        assert len(critical_actions) == 0, (
            "High-score candidate should not have critical-priority actions"
        )

        # ── All traced_to references should mention nice-to-have ─
        for action in all_actions:
            assert "nice-to-have" in action.traced_to.lower() or \
                   "Nice-to-have" in action.traced_to, (
                f"Action '{action.action}' should trace to nice-to-have gap, "
                f"got: '{action.traced_to}'"
            )

    @pytest.mark.asyncio
    async def test_retries_on_validation_error_then_succeeds(self):
        """
        Pipeline retries on ValidationError and succeeds on second attempt.
        """
        from pydantic import ValidationError

        valid_output = _make_valid_roadmap_output()

        # First call raises ValidationError, second succeeds
        mock_registry = MagicMock()
        mock_registry.acomplete = AsyncMock(
            side_effect=[
                ValidationError.from_exception_data(
                    title="CareerRoadmapLLMOutput",
                    line_errors=[
                        {
                            "type": "missing",
                            "loc": ("weeks",),
                            "msg": "Field required",
                            "input": {},
                        }
                    ],
                ),
                valid_output,
            ]
        )

        readiness_score = _make_readiness_score()
        benchmark = _make_benchmark()

        final_state = await run_roadmap_pipeline(
            readiness_score=readiness_score,
            benchmark=benchmark,
            registry=mock_registry,
        )

        # Pipeline should succeed on the second attempt
        assert final_state["roadmap"] is not None
        assert final_state["error_count"] == 1  # One failure before success
        assert len(final_state["validation_errors"]) == 1

    @pytest.mark.asyncio
    async def test_raises_after_max_retries_exhausted(self):
        """Pipeline raises ValueError after MAX_RETRIES failures."""
        mock_registry = MagicMock()
        mock_registry.acomplete = AsyncMock(
            side_effect=Exception("LLM unavailable")
        )

        readiness_score = _make_readiness_score()
        benchmark = _make_benchmark()

        with pytest.raises(ValueError, match="failed after"):
            await run_roadmap_pipeline(
                readiness_score=readiness_score,
                benchmark=benchmark,
                registry=mock_registry,
            )


class TestSaveCareerRoadmap:
    """Tests for the persistence helper."""

    @pytest.mark.asyncio
    async def test_raises_on_none_roadmap(self):
        """save_career_roadmap raises ValueError if roadmap is None."""
        state: RoadmapState = {
            "readiness_score": _make_readiness_score(),
            "benchmark": _make_benchmark(),
            "roadmap": None,
            "error_count": 3,
            "validation_errors": ["error"],
        }
        mock_session = AsyncMock()

        with pytest.raises(ValueError, match="roadmap is None"):
            await save_career_roadmap(state, mock_session)


async def _make_real_roadmap(session):
    benchmark = RoleBenchmarkModel(must_have_skills=["Python"], nice_to_have_skills=[], required_tools=[], common_responsibilities=[], minimum_years=3, seniority_level="Mid")
    session.add(benchmark)
    await session.commit()
    await session.refresh(benchmark)

    user = UserTable(name="Test User", career_level="mid", years_of_experience=3, skills=["Python"], tools=["Git"])
    session.add(user)
    await session.commit()
    await session.refresh(user)

    score = ReadinessScoreModel(benchmark_id=benchmark.id, user_id=user.id, overall_score=70, must_have_skills_score=30, tools_score=20, experience_score=15, soft_skills_score=5)
    session.add(score)
    await session.commit()
    await session.refresh(score)

    roadmap = CareerRoadmapModel(readiness_score_id=score.id, weeks=[], executive_summary="test", key_focus_areas=[], responsible_ai_disclaimer="test")
    session.add(roadmap)
    await session.commit()
    await session.refresh(roadmap)
    return roadmap


class TestRoadmapReview:
    @pytest.mark.asyncio
    async def test_new_roadmap_starts_unreviewed(self, async_session):
        roadmap = await _make_real_roadmap(async_session)
        assert roadmap.reviewed_at is None

    @pytest.mark.asyncio
    async def test_mark_reviewed_sets_timestamp(self, async_session):
        roadmap = await _make_real_roadmap(async_session)
        reviewed = await mark_roadmap_reviewed(async_session, roadmap.id)
        assert reviewed.reviewed_at is not None

    @pytest.mark.asyncio
    async def test_raises_for_missing_roadmap(self, async_session):
        with pytest.raises(ValueError, match="not found"):
            await mark_roadmap_reviewed(async_session, 999_999)
