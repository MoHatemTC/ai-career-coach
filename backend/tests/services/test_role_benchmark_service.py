"""
tests/services/test_role_benchmark_service.py
=============================================
Tests for the role benchmark extraction and embedding LangGraph pipeline.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from app.models.role_benchmark import RoleBenchmark as RoleBenchmarkModel
from app.schemas.role_benchmark import RoleBenchmark
from app.services.role_benchmark_service import (
    MAX_RETRIES,
    BenchmarkState,
    route_after_extract,
    run_benchmark_pipeline,
    mark_benchmark_reviewed,
)


def _make_valid_role_benchmark_output() -> RoleBenchmark:
    return RoleBenchmark(
        must_have_skills=["Python", "FastAPI", "SQL"],
        nice_to_have_skills=["Docker", "Kubernetes"],
        required_tools=["Git", "PostgreSQL"],
        minimum_years=3,
        seniority_level="Mid-Level",
        common_responsibilities=["Develop APIs", "Write tests", "Collaborate with team"]
    )


class TestRouteAfterExtract:
    """Unit tests for the conditional edge routing function."""

    def test_returns_embed_on_success(self):
        state: BenchmarkState = {
            "raw_text": "job description",
            "extracted_data": _make_valid_role_benchmark_output(),
            "embedding": None,
            "error_count": 0,
            "validation_errors": [],
        }
        assert route_after_extract(state) == "embed"

    def test_retries_on_failure_with_remaining_attempts(self):
        state: BenchmarkState = {
            "raw_text": "job description",
            "extracted_data": None,
            "embedding": None,
            "error_count": 1,
            "validation_errors": ["some error"],
        }
        assert route_after_extract(state) == "extract"

    def test_raises_after_max_retries(self):
        state: BenchmarkState = {
            "raw_text": "job description",
            "extracted_data": None,
            "embedding": None,
            "error_count": MAX_RETRIES,
            "validation_errors": ["error1", "error2", "error3"],
        }
        with pytest.raises(ValueError, match="failed after"):
            route_after_extract(state)


class TestRunBenchmarkPipelineHappyPath:
    """Happy-path test: valid text -> extraction + embedding."""

    @pytest.mark.asyncio
    async def test_generates_valid_benchmark_with_embedding(self):
        valid_output = _make_valid_role_benchmark_output()
        mock_embedding = [0.1] * 768

        mock_registry = MagicMock()
        mock_registry.acomplete = AsyncMock(return_value=valid_output)
        mock_registry.aembed = AsyncMock(return_value=[mock_embedding])

        final_state = await run_benchmark_pipeline(
            raw_text="We need a mid-level Python dev...",
            registry=mock_registry,
        )

        assert final_state["extracted_data"] is not None
        assert final_state["error_count"] == 0

        data = final_state["extracted_data"]
        assert data.must_have_skills == ["Python", "FastAPI", "SQL"]
        assert data.nice_to_have_skills == ["Docker", "Kubernetes"]
        assert data.required_tools == ["Git", "PostgreSQL"]
        assert data.minimum_years == 3
        assert data.seniority_level == "Mid-Level"
        assert len(data.common_responsibilities) == 3

        # Explicitly check embedding length
        assert final_state["embedding"] is not None
        assert len(final_state["embedding"]) == 768

        mock_registry.acomplete.assert_called_once()
        mock_registry.aembed.assert_called_once()


class TestRunBenchmarkPipelineEdgeCases:
    """Edge-case tests for the benchmark pipeline."""

    @pytest.mark.asyncio
    async def test_retries_on_validation_error_then_succeeds(self):
        valid_output = _make_valid_role_benchmark_output()
        mock_embedding = [0.1] * 768

        mock_registry = MagicMock()
        mock_registry.acomplete = AsyncMock(
            side_effect=[
                ValidationError.from_exception_data(
                    title="RoleBenchmark",
                    line_errors=[
                        {
                            "type": "missing",
                            "loc": ("must_have_skills",),
                            "msg": "Field required",
                            "input": {},
                        }
                    ],
                ),
                valid_output,
            ]
        )
        mock_registry.aembed = AsyncMock(return_value=[mock_embedding])

        final_state = await run_benchmark_pipeline(
            raw_text="We need a mid-level Python dev...",
            registry=mock_registry,
        )

        assert final_state["extracted_data"] is not None
        assert final_state["error_count"] == 1
        assert len(final_state["validation_errors"]) == 1

    @pytest.mark.asyncio
    async def test_raises_after_max_retries_exhausted(self):
        mock_registry = MagicMock()
        mock_registry.acomplete = AsyncMock(
            side_effect=Exception("LLM API Error")
        )

        with pytest.raises(ValueError, match="failed after"):
            await run_benchmark_pipeline(
                raw_text="job description",
                registry=mock_registry,
            )


async def _make_real_benchmark(session):
    benchmark = RoleBenchmarkModel(must_have_skills=["Python"], nice_to_have_skills=[], required_tools=[], common_responsibilities=[], minimum_years=3, seniority_level="Mid")
    session.add(benchmark)
    await session.commit()
    await session.refresh(benchmark)
    return benchmark


class TestBenchmarkReview:
    @pytest.mark.asyncio
    async def test_new_benchmark_starts_unreviewed(self, async_session):
        benchmark = await _make_real_benchmark(async_session)
        assert benchmark.reviewed_at is None

    @pytest.mark.asyncio
    async def test_mark_reviewed_sets_timestamp(self, async_session):
        benchmark = await _make_real_benchmark(async_session)
        reviewed = await mark_benchmark_reviewed(async_session, benchmark.id)
        assert reviewed.reviewed_at is not None

    @pytest.mark.asyncio
    async def test_raises_for_missing_benchmark(self, async_session):
        with pytest.raises(ValueError, match="not found"):
            await mark_benchmark_reviewed(async_session, 999_999)
