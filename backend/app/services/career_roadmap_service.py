"""
app/services/career_roadmap_service.py
========================================
LangGraph pipeline for the **Personalized Career Roadmap** feature.

Architecture
------------
The pipeline is a single-node ``StateGraph`` with a retry loop:

.. code-block:: text

    entry → "generate" node (LLM structured-output call)
                │
                ▼ route_after_generate()
          ┌─────┴──────┐
         retry?        success?
          │                │
          └──► "generate"  END

This mirrors the ``readiness_score_service.py`` design exactly:
- ``LLMServiceRegistry`` for all LLM calls (no LangChain wrappers)
- ``PromptBuilder`` for prompt construction
- ``MAX_RETRIES = 3`` with ValidationError and generic Exception handling
- ``save_career_roadmap()`` for PostgreSQL persistence

Public API
----------
``run_roadmap_pipeline(readiness_score, benchmark, registry)``
    Execute the full roadmap generation pipeline and return the final
    ``RoadmapState``.
``save_career_roadmap(state, session)``
    Persist the generated roadmap to the database and return the ORM record.
``build_graph(registry)``
    Compile and return the LangGraph ``StateGraph``.
``route_after_generate(state)``
    Conditional edge: ``"generate"`` (retry) or ``END`` (success / raise).
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
from app.models.career_roadmap import CareerRoadmap as CareerRoadmapModel
from app.models.readiness_score import ReadinessScore as ReadinessScoreModel
from app.models.role_benchmark import RoleBenchmark as RoleBenchmarkModel
from app.schemas.career_roadmap import CareerRoadmapLLMOutput

logger = logging.getLogger(__name__)

MAX_RETRIES: int = 3

_prompt_builder = PromptBuilder()


# ---------------------------------------------------------------------------
# LangGraph state
# ---------------------------------------------------------------------------


class RoadmapState(TypedDict):
    """Shared mutable state dictionary passed between LangGraph nodes."""

    readiness_score: ReadinessScoreModel
    benchmark: RoleBenchmarkModel
    roadmap: Optional[CareerRoadmapLLMOutput]
    error_count: int
    validation_errors: List[str]


# ---------------------------------------------------------------------------
# Node factories
# ---------------------------------------------------------------------------


def make_generate_node(registry: LLMServiceRegistry | None = None):
    """
    Return an async ``generate`` node function bound to the given registry.

    The returned function calls the LLM with structured output
    (:class:`~app.schemas.career_roadmap.CareerRoadmapLLMOutput`) and populates
    ``state["roadmap"]`` on success, or increments ``state["error_count"]``
    on failure.
    """
    resolved_registry: LLMServiceRegistry = (
        registry if registry is not None else get_registry()
    )

    async def generate(state: RoadmapState) -> RoadmapState:
        attempt = state["error_count"] + 1
        logger.debug("generate node – attempt %d / %d", attempt, MAX_RETRIES)

        score: ReadinessScoreModel = state["readiness_score"]
        benchmark: RoleBenchmarkModel = state["benchmark"]

        # Build serialisable dicts from the ORM models
        readiness_dict = {
            "overall_score": score.overall_score,
            "sub_scores": {
                "must_have_skills_score": score.must_have_skills_score,
                "tools_score": score.tools_score,
                "experience_score": score.experience_score,
                "soft_skills_score": score.soft_skills_score,
            },
            "critical_gaps": score.critical_gaps,
            "nice_to_have_gaps": score.nice_to_have_gaps,
            "strengths": score.strengths,
            "explanation": score.explanation,
        }
        benchmark_dict = {
            "must_have_skills": benchmark.must_have_skills,
            "nice_to_have_skills": benchmark.nice_to_have_skills,
            "required_tools": benchmark.required_tools,
            "minimum_years": benchmark.minimum_years,
            "seniority_level": benchmark.seniority_level,
            "common_responsibilities": benchmark.common_responsibilities,
        }

        messages = _prompt_builder.build_career_roadmap_messages(
            readiness_analysis=readiness_dict,
            benchmark=benchmark_dict,
        )

        try:
            result: CareerRoadmapLLMOutput = await resolved_registry.acomplete(
                messages,
                response_format=CareerRoadmapLLMOutput,
            )
            return {
                **state,
                "roadmap": result,
            }
        except ValidationError as exc:
            logger.warning("ValidationError on attempt %d: %s", attempt, exc)
            error_msg: str = ", ".join(str(e) for e in exc.errors())
            return {
                **state,
                "roadmap": None,
                "validation_errors": state["validation_errors"] + [error_msg],
                "error_count": state["error_count"] + 1,
            }
        except Exception as exc:
            logger.warning("Roadmap generation error on attempt %d: %s", attempt, exc)
            return {
                **state,
                "roadmap": None,
                "validation_errors": state["validation_errors"] + [str(exc)],
                "error_count": state["error_count"] + 1,
            }

    return generate


# ---------------------------------------------------------------------------
# Conditional edge
# ---------------------------------------------------------------------------


def route_after_generate(state: RoadmapState) -> str:
    """
    Decide the next node after the ``generate`` node:

    * ``"generate"`` — if the roadmap generation failed and retries remain.
    * :data:`~langgraph.graph.END` — if the roadmap was generated successfully.
    * raises :exc:`ValueError` — after ``MAX_RETRIES`` failures.

    Parameters
    ----------
    state:
        Current ``RoadmapState``.

    Returns
    -------
    str
        ``"generate"`` or ``END``.

    Raises
    ------
    ValueError
        If ``MAX_RETRIES`` consecutive failures are recorded.
    """
    if state["roadmap"] is not None:
        return END  # type: ignore[return-value]

    if state["error_count"] < MAX_RETRIES:
        logger.info(
            "Retrying roadmap generation (%d / %d failures so far).",
            state["error_count"],
            MAX_RETRIES,
        )
        return "generate"

    raise ValueError(
        f"LLM roadmap generation failed after {MAX_RETRIES} attempts. "
        "Validation errors collected:\n" + "\n".join(state["validation_errors"])
    )


# ---------------------------------------------------------------------------
# Graph factory
# ---------------------------------------------------------------------------


def build_graph(registry: LLMServiceRegistry | None = None) -> Any:
    """
    Assemble and compile the roadmap-generation ``StateGraph``.

    Parameters
    ----------
    registry:
        The :class:`~app.ai.registry.LLMServiceRegistry` to bind to the
        generate node.  If ``None``, the process-wide singleton from
        :func:`~app.ai.registry.get_registry` is used.

    Returns
    -------
    Any
        A compiled LangGraph runnable (``CompiledGraph``).
    """
    graph = StateGraph(RoadmapState)

    graph.add_node("generate", make_generate_node(registry))

    graph.set_entry_point("generate")

    graph.add_conditional_edges(
        "generate",
        route_after_generate,
        {
            "generate": "generate",
            END: END,
        },
    )

    return graph.compile()


# ---------------------------------------------------------------------------
# Public pipeline runner
# ---------------------------------------------------------------------------


async def run_roadmap_pipeline(
    readiness_score: ReadinessScoreModel,
    benchmark: RoleBenchmarkModel,
    registry: LLMServiceRegistry | None = None,
) -> RoadmapState:
    """
    Execute the full roadmap generation pipeline.

    Parameters
    ----------
    readiness_score:
        The :class:`~app.models.readiness_score.ReadinessScore` ORM record
        loaded from the database.
    benchmark:
        The :class:`~app.models.role_benchmark.RoleBenchmark` ORM record
        loaded from the database.
    registry:
        Optional :class:`~app.ai.registry.LLMServiceRegistry` override.
        Defaults to the process-wide singleton.

    Returns
    -------
    RoadmapState
        The final graph state.  ``state["roadmap"]`` is a
        :class:`~app.schemas.career_roadmap.CareerRoadmapLLMOutput` instance
        on success.

    Raises
    ------
    ValueError
        If the LLM fails to produce a valid roadmap after ``MAX_RETRIES``
        attempts.
    """
    initial_state: RoadmapState = {
        "readiness_score": readiness_score,
        "benchmark": benchmark,
        "roadmap": None,
        "error_count": 0,
        "validation_errors": [],
    }

    compiled_graph = build_graph(registry=registry)
    final_state: RoadmapState = await compiled_graph.ainvoke(initial_state)
    return final_state


# ---------------------------------------------------------------------------
# Persistence helper
# ---------------------------------------------------------------------------


async def save_career_roadmap(
    state: RoadmapState,
    session: AsyncSession,
) -> CareerRoadmapModel:
    """
    Persist the result of :func:`run_roadmap_pipeline` to the database.

    Parameters
    ----------
    state:
        The final ``RoadmapState`` returned by :func:`run_roadmap_pipeline`.
    session:
        An active SQLModel ``AsyncSession``.

    Returns
    -------
    CareerRoadmapModel
        The persisted ORM record with its database-assigned ``id`` and
        ``created_at`` populated.

    Raises
    ------
    ValueError
        If ``state["roadmap"]`` is ``None`` (pipeline did not succeed).
    RuntimeError
        If the database commit fails.
    """
    roadmap = state["roadmap"]
    if roadmap is None:
        raise ValueError(
            "Cannot persist career roadmap: roadmap is None. "
            "Run run_roadmap_pipeline() successfully before calling "
            "save_career_roadmap()."
        )

    score: ReadinessScoreModel = state["readiness_score"]

    # Serialise the Pydantic weeks to plain dicts for JSON storage
    weeks_data = [week.model_dump() for week in roadmap.weeks]

    db_record = CareerRoadmapModel(
        readiness_score_id=score.id,
        weeks=weeks_data,
        executive_summary=roadmap.executive_summary,
        key_focus_areas=roadmap.key_focus_areas,
        responsible_ai_disclaimer=roadmap.responsible_ai_disclaimer,
    )

    try:
        session.add(db_record)
        await session.commit()
        await session.refresh(db_record)
    except Exception as exc:
        await session.rollback()
        logger.exception("Database commit failed in save_career_roadmap()")
        raise RuntimeError(
            "Failed to persist the career roadmap to the database."
        ) from exc

    logger.info(
        "Persisted career roadmap id=%s (readiness_score_id=%s)",
        db_record.id,
        db_record.readiness_score_id,
    )
    return db_record


async def mark_roadmap_reviewed(session: AsyncSession, roadmap_id: int) -> CareerRoadmapModel:
    """Record that a human has reviewed this career roadmap."""
    roadmap = await session.get(CareerRoadmapModel, roadmap_id)
    if not roadmap:
        raise ValueError(f"Career roadmap {roadmap_id} not found")
    roadmap.reviewed_at = datetime.utcnow()
    session.add(roadmap)
    await session.commit()
    await session.refresh(roadmap)
    return roadmap
