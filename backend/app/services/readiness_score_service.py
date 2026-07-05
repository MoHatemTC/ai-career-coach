"""
app/services/readiness_score_service.py
========================================
LangGraph pipeline for the **Career Readiness Score** feature.

Architecture
------------
The pipeline is a single-node ``StateGraph`` with a retry loop:

.. code-block:: text

    entry → "score" node (LLM structured-output call)
                │
                ▼ route_after_score()
          ┌─────┴──────┐
         retry?        success?
          │                │
          └──► "score"    END

This mirrors the ``role_benchmark_service.py`` design exactly:
- ``LLMServiceRegistry`` for all LLM calls (no LangChain wrappers)
- ``PromptBuilder`` for prompt construction
- ``MAX_RETRIES = 3`` with ValidationError and generic Exception handling
- ``save_readiness_score()`` for PostgreSQL persistence

Public API
----------
``run_readiness_pipeline(request, benchmark, registry)``
    Execute the full scoring pipeline and return the final ``ReadinessState``.
``save_readiness_score(state, session)``
    Persist the scored result to the database and return the ORM record.
``build_graph(registry)``
    Compile and return the LangGraph ``StateGraph``.
``route_after_score(state)``
    Conditional edge: ``"score"`` (retry) or ``END`` (success / raise).
"""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any, List, Optional, TypedDict

from langgraph.graph import END, StateGraph
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.prompts import PromptBuilder
from app.ai.registry import LLMServiceRegistry, get_registry
from app.models.readiness_score import ReadinessScore as ReadinessScoreModel
from app.models.role_benchmark import RoleBenchmark as RoleBenchmarkModel
from app.schemas.matching import CandidateProfile
from app.schemas.readiness_score import (
    ReadinessGapAnalysis,
    ReadinessRequest,
)

logger = logging.getLogger(__name__)

MAX_RETRIES: int = 3

_prompt_builder = PromptBuilder()


# ---------------------------------------------------------------------------
# LangGraph state
# ---------------------------------------------------------------------------


class ReadinessState(TypedDict):
    """Shared mutable state dictionary passed between LangGraph nodes."""

    request: ReadinessRequest
    candidate_profile: CandidateProfile
    benchmark: Optional[RoleBenchmarkModel]
    analysis: Optional[ReadinessGapAnalysis]
    error_count: int
    validation_errors: List[str]


# ---------------------------------------------------------------------------
# Node factories
# ---------------------------------------------------------------------------


def make_score_node(registry: LLMServiceRegistry | None = None):
    """
    Return an async ``score`` node function bound to the given registry.

    The returned function calls the LLM with structured output
    (:class:`~app.schemas.readiness_score.ReadinessGapAnalysis`) and populates
    ``state["analysis"]`` on success, or increments ``state["error_count"]``
    on failure.
    """
    resolved_registry: LLMServiceRegistry = (
        registry if registry is not None else get_registry()
    )

    async def score(state: ReadinessState) -> ReadinessState:
        attempt = state["error_count"] + 1
        logger.debug("score node – attempt %d / %d", attempt, MAX_RETRIES)

        benchmark: RoleBenchmarkModel = state["benchmark"]
        profile: CandidateProfile = state["candidate_profile"]

        # Build serialisable dicts from the ORM model and Pydantic schema
        benchmark_dict = {
            "must_have_skills": benchmark.must_have_skills,
            "nice_to_have_skills": benchmark.nice_to_have_skills,
            "required_tools": benchmark.required_tools,
            "minimum_years": benchmark.minimum_years,
            "seniority_level": benchmark.seniority_level,
            "common_responsibilities": benchmark.common_responsibilities,
        }
        profile_dict = {
            "skills": profile.skills,
            "tools": profile.tools,
            "experience_years": profile.experience_years,
            "education": profile.education,
        }

        messages = _prompt_builder.build_readiness_gap_analysis_messages(
            candidate_profile=profile_dict,
            benchmark=benchmark_dict,
        )

        try:
            result: ReadinessGapAnalysis = await resolved_registry.acomplete(
                messages,
                response_format=ReadinessGapAnalysis,
            )
            return {
                **state,
                "analysis": result,
            }
        except ValidationError as exc:
            logger.warning("ValidationError on attempt %d: %s", attempt, exc)
            error_msg: str = ", ".join(str(e) for e in exc.errors())
            return {
                **state,
                "analysis": None,
                "validation_errors": state["validation_errors"] + [error_msg],
                "error_count": state["error_count"] + 1,
            }
        except Exception as exc:
            logger.warning("Scoring error on attempt %d: %s", attempt, exc)
            return {
                **state,
                "analysis": None,
                "validation_errors": state["validation_errors"] + [str(exc)],
                "error_count": state["error_count"] + 1,
            }

    return score


# ---------------------------------------------------------------------------
# Conditional edge
# ---------------------------------------------------------------------------


def route_after_score(state: ReadinessState) -> str:
    """
    Decide the next node after the ``score`` node:

    * ``"score"`` — if the analysis failed and retries remain.
    * :data:`~langgraph.graph.END` — if the analysis succeeded.
    * raises :exc:`ValueError` — after ``MAX_RETRIES`` failures.

    Parameters
    ----------
    state:
        Current ``ReadinessState``.

    Returns
    -------
    str
        ``"score"`` or ``END``.

    Raises
    ------
    ValueError
        If ``MAX_RETRIES`` consecutive failures are recorded.
    """
    if state["analysis"] is not None:
        return END  # type: ignore[return-value]

    if state["error_count"] < MAX_RETRIES:
        logger.info(
            "Retrying readiness scoring (%d / %d failures so far).",
            state["error_count"],
            MAX_RETRIES,
        )
        return "score"

    raise ValueError(
        f"LLM readiness scoring failed after {MAX_RETRIES} attempts. "
        "Validation errors collected:\n" + "\n".join(state["validation_errors"])
    )


# ---------------------------------------------------------------------------
# Graph factory
# ---------------------------------------------------------------------------


def build_graph(registry: LLMServiceRegistry | None = None) -> Any:
    """
    Assemble and compile the readiness-scoring ``StateGraph``.

    Parameters
    ----------
    registry:
        The :class:`~app.ai.registry.LLMServiceRegistry` to bind to the score
        node.  If ``None``, the process-wide singleton from
        :func:`~app.ai.registry.get_registry` is used.

    Returns
    -------
    Any
        A compiled LangGraph runnable (``CompiledGraph``).
    """
    graph = StateGraph(ReadinessState)

    graph.add_node("score", make_score_node(registry))

    graph.set_entry_point("score")

    graph.add_conditional_edges(
        "score",
        route_after_score,
        {
            "score": "score",
            END: END,
        },
    )

    return graph.compile()


# ---------------------------------------------------------------------------
# Public pipeline runner
# ---------------------------------------------------------------------------


async def run_readiness_pipeline(
    request: ReadinessRequest,
    benchmark: RoleBenchmarkModel,
    candidate_profile: CandidateProfile,
    registry: LLMServiceRegistry | None = None,
) -> ReadinessState:
    """
    Execute the full readiness scoring pipeline.

    Parameters
    ----------
    request:
        The validated :class:`~app.schemas.readiness_score.ReadinessRequest`.
    candidate_profile:
        The :class:`~app.schemas.matching.CandidateProfile` for the user.
    benchmark:
        The :class:`~app.models.role_benchmark.RoleBenchmark` ORM record
        loaded from the database.
    registry:
        Optional :class:`~app.ai.registry.LLMServiceRegistry` override.
        Defaults to the process-wide singleton.

    Returns
    -------
    ReadinessState
        The final graph state.  ``state["analysis"]`` is a
        :class:`~app.schemas.readiness_score.ReadinessGapAnalysis` instance
        on success.

    Raises
    ------
    ValueError
        If the LLM fails to produce a valid analysis after ``MAX_RETRIES``
        attempts.
    """
    initial_state: ReadinessState = {
        "request": request,
        "candidate_profile": candidate_profile,
        "benchmark": benchmark,
        "analysis": None,
        "error_count": 0,
        "validation_errors": [],
    }

    compiled_graph = build_graph(registry=registry)
    final_state: ReadinessState = await compiled_graph.ainvoke(initial_state)
    return final_state


# ---------------------------------------------------------------------------
# Persistence helper
# ---------------------------------------------------------------------------


async def save_readiness_score(
    state: ReadinessState,
    session: AsyncSession,
    job_match_id: Optional[int] = None,
) -> ReadinessScoreModel:
    """
    Persist the result of :func:`run_readiness_pipeline` to the database.

    Parameters
    ----------
    state:
        The final ``ReadinessState`` returned by :func:`run_readiness_pipeline`.
    session:
        An active SQLModel ``AsyncSession``.
    job_match_id:
        Optional ID of the job match this score is deepening.

    Returns
    -------
    ReadinessScoreModel
        The persisted ORM record with its database-assigned ``id`` and
        ``created_at`` populated.

    Raises
    ------
    ValueError
        If ``state["analysis"]`` is ``None`` (pipeline did not succeed).
    RuntimeError
        If the database commit fails.
    """
    analysis = state["analysis"]
    if analysis is None:
        raise ValueError(
            "Cannot persist readiness score: analysis is None. "
            "Run run_readiness_pipeline() successfully before calling "
            "save_readiness_score()."
        )

    request: ReadinessRequest = state["request"]
    profile: CandidateProfile = state["candidate_profile"]

    db_record = ReadinessScoreModel(
        benchmark_id=request.benchmark_id,
        user_id=request.user_id,
        job_match_id=job_match_id,
        overall_score=analysis.overall_score,
        must_have_skills_score=analysis.sub_scores.must_have_skills_score,
        tools_score=analysis.sub_scores.tools_score,
        experience_score=analysis.sub_scores.experience_score,
        soft_skills_score=analysis.sub_scores.soft_skills_score,
        critical_gaps=analysis.critical_gaps,
        nice_to_have_gaps=analysis.nice_to_have_gaps,
        strengths=analysis.strengths,
        explanation=analysis.explanation,
        candidate_skills=profile.skills,
        candidate_tools=profile.tools,
        candidate_experience_years=profile.experience_years,
    )

    try:
        session.add(db_record)
        await session.commit()
        await session.refresh(db_record)
    except Exception as exc:
        await session.rollback()
        logger.exception("Database commit failed in save_readiness_score()")
        raise RuntimeError(
            "Failed to persist the readiness score to the database."
        ) from exc

    logger.info(
        "Persisted readiness score id=%s (benchmark_id=%s, overall_score=%d)",
        db_record.id,
        db_record.benchmark_id,
        db_record.overall_score,
    )
    return db_record


async def mark_readiness_score_reviewed(
    session: AsyncSession, readiness_score_id: int
) -> ReadinessScoreModel:
    """Record that a human has reviewed this readiness assessment."""
    score = await session.get(ReadinessScoreModel, readiness_score_id)
    if not score:
        raise ValueError(f"Readiness score {readiness_score_id} not found")
    score.reviewed_at = datetime.utcnow()
    session.add(score)
    await session.commit()
    await session.refresh(score)
    return score
