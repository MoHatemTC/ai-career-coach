"""
tests/services/test_readiness_score_service.py
==============================================
Tests for the readiness score LangGraph pipeline.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from app.models.jobs import UserTable
from app.models.readiness_score import ReadinessScore as ReadinessScoreModel
from app.models.role_benchmark import RoleBenchmark, RoleBenchmark as RoleBenchmarkModel
from app.schemas.matching import CandidateProfile
from app.schemas.readiness_score import (
    ReadinessGapAnalysis,
    ReadinessRequest,
    SubScores,
)
from app.services.readiness_score_service import (
    MAX_RETRIES,
    ReadinessState,
    mark_readiness_score_reviewed,
    route_after_score,
    run_readiness_pipeline,
)


def _make_benchmark_model(**overrides):
    defaults = {
        "id": 10,
        "must_have_skills": ["Python", "FastAPI"],
        "nice_to_have_skills": ["Docker"],
        "required_tools": ["Git"],
        "minimum_years": 3,
        "seniority_level": "Mid",
        "common_responsibilities": ["Coding"],
    }
    defaults.update(overrides)
    mock = MagicMock(spec=RoleBenchmark)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _make_candidate_profile():
    return CandidateProfile(
        name="Test Candidate",
        skills=["Python"],
        tools=["Git"],
        experience_years=2,
        education=["BSc Computer Science"],
    )


def _make_readiness_request():
    return ReadinessRequest(benchmark_id=10, user_id=5)


def _make_valid_readiness_analysis() -> ReadinessGapAnalysis:
    return ReadinessGapAnalysis(
        overall_score=75,
        sub_scores=SubScores(
            must_have_skills_score=30,
            tools_score=15,
            experience_score=20,
            soft_skills_score=10,
        ),
        critical_gaps=["FastAPI"],
        nice_to_have_gaps=["Docker"],
        strengths=["Python", "Git"],
        explanation="Candidate knows Python but needs FastAPI."
    )


class TestRouteAfterScore:
    """Unit tests for the conditional edge routing function."""

    def test_returns_end_on_success(self):
        state: ReadinessState = {
            "request": _make_readiness_request(),
            "candidate_profile": _make_candidate_profile(),
            "benchmark": _make_benchmark_model(),
            "analysis": _make_valid_readiness_analysis(),
            "error_count": 0,
            "validation_errors": [],
        }
        # route_after_score returns '__end__' when successful
        assert route_after_score(state) == "__end__"

    def test_retries_on_failure_with_remaining_attempts(self):
        state: ReadinessState = {
            "request": _make_readiness_request(),
            "candidate_profile": _make_candidate_profile(),
            "benchmark": _make_benchmark_model(),
            "analysis": None,
            "error_count": 1,
            "validation_errors": ["error"],
        }
        assert route_after_score(state) == "score"

    def test_raises_after_max_retries(self):
        state: ReadinessState = {
            "request": _make_readiness_request(),
            "candidate_profile": _make_candidate_profile(),
            "benchmark": _make_benchmark_model(),
            "analysis": None,
            "error_count": MAX_RETRIES,
            "validation_errors": ["error1", "error2", "error3"],
        }
        with pytest.raises(ValueError, match="failed after"):
            route_after_score(state)


class TestRunReadinessPipelineHappyPath:
    """Happy-path test: valid input -> gap analysis."""

    @pytest.mark.asyncio
    async def test_generates_valid_readiness_score(self):
        valid_output = _make_valid_readiness_analysis()
        mock_registry = MagicMock()
        mock_registry.acomplete = AsyncMock(return_value=valid_output)

        request = _make_readiness_request()
        benchmark = _make_benchmark_model()

        final_state = await run_readiness_pipeline(
            request=request,
            benchmark=benchmark,
            candidate_profile=_make_candidate_profile(),
            registry=mock_registry,
        )

        assert final_state["analysis"] is not None
        assert final_state["error_count"] == 0

        analysis = final_state["analysis"]
        assert 0 <= analysis.overall_score <= 100
        assert 0 <= analysis.sub_scores.must_have_skills_score <= 100
        assert len(analysis.critical_gaps) == 1
        assert "FastAPI" in analysis.critical_gaps
        assert len(analysis.nice_to_have_gaps) == 1
        assert "Docker" in analysis.nice_to_have_gaps
        assert len(analysis.strengths) == 2
        assert "Python" in analysis.strengths

        mock_registry.acomplete.assert_called_once()


class TestRunReadinessPipelineEdgeCases:
    """Edge-case tests for the readiness pipeline."""

    @pytest.mark.asyncio
    async def test_retries_on_validation_error_then_succeeds(self):
        valid_output = _make_valid_readiness_analysis()
        mock_registry = MagicMock()
        mock_registry.acomplete = AsyncMock(
            side_effect=[
                ValidationError.from_exception_data(
                    title="ReadinessGapAnalysis",
                    line_errors=[
                        {
                            "type": "missing",
                            "loc": ("overall_score",),
                            "msg": "Field required",
                            "input": {},
                        }
                    ],
                ),
                valid_output,
            ]
        )

        request = _make_readiness_request()
        benchmark = _make_benchmark_model()

        final_state = await run_readiness_pipeline(
            request=request,
            benchmark=benchmark,
            candidate_profile=_make_candidate_profile(),
            registry=mock_registry,
        )

        assert final_state["analysis"] is not None
        assert final_state["error_count"] == 1
        assert len(final_state["validation_errors"]) == 1

    @pytest.mark.asyncio
    async def test_raises_after_max_retries_exhausted(self):
        mock_registry = MagicMock()
        mock_registry.acomplete = AsyncMock(side_effect=Exception("API Error"))

        request = _make_readiness_request()
        benchmark = _make_benchmark_model()

        with pytest.raises(ValueError, match="failed after"):
            await run_readiness_pipeline(
                request=request,
                benchmark=benchmark,
                candidate_profile=_make_candidate_profile(),
                registry=mock_registry,
            )


async def _make_real_benchmark(session):
    benchmark = RoleBenchmarkModel(must_have_skills=["Python"], nice_to_have_skills=[], required_tools=[], common_responsibilities=[], minimum_years=3, seniority_level="Mid")
    session.add(benchmark)
    await session.commit()
    await session.refresh(benchmark)
    return benchmark


async def _make_real_user(session):
    user = UserTable(name="Test User", career_level="mid", years_of_experience=3, skills=["Python"], tools=["Git"])
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _make_real_readiness_score(session, benchmark_id, user_id):
    score = ReadinessScoreModel(benchmark_id=benchmark_id, user_id=user_id, overall_score=70, must_have_skills_score=30, tools_score=20, experience_score=15, soft_skills_score=5)
    session.add(score)
    await session.commit()
    await session.refresh(score)
    return score


class TestReadinessScoreReview:
    @pytest.mark.asyncio
    async def test_new_score_starts_unreviewed(self, async_session):
        benchmark = await _make_real_benchmark(async_session)
        user = await _make_real_user(async_session)
        score = await _make_real_readiness_score(async_session, benchmark.id, user.id)
        assert score.reviewed_at is None

    @pytest.mark.asyncio
    async def test_mark_reviewed_sets_timestamp(self, async_session):
        benchmark = await _make_real_benchmark(async_session)
        user = await _make_real_user(async_session)
        score = await _make_real_readiness_score(async_session, benchmark.id, user.id)
        reviewed = await mark_readiness_score_reviewed(async_session, score.id)
        assert reviewed.reviewed_at is not None

    @pytest.mark.asyncio
    async def test_raises_for_missing_score(self, async_session):
        with pytest.raises(ValueError, match="not found"):
            await mark_readiness_score_reviewed(async_session, 999_999)
