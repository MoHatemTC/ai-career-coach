from __future__ import annotations

from datetime import datetime
import logging
from typing import Any, List, Optional, TypedDict

from langgraph.graph import END, StateGraph
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.prompts import PromptBuilder
from app.ai.registry import LLMServiceRegistry, get_registry
from app.models.role_benchmark import RoleBenchmark as RoleBenchmarkModel
from app.schemas.role_benchmark import RoleBenchmark

logger = logging.getLogger(__name__)

MAX_RETRIES: int = 3

_prompt_builder = PromptBuilder()


class BenchmarkState(TypedDict):
    """Shared mutable state passed between LangGraph nodes."""

    raw_text: str
    extracted_data: Optional[RoleBenchmark]
    embedding: Optional[List[float]]
    error_count: int
    validation_errors: List[str]


def make_extract_node(registry: LLMServiceRegistry | None = None):
    """Return an async extract node function bound to the given registry."""
    resolved_registry: LLMServiceRegistry = registry if registry is not None else get_registry()

    async def extract(state: BenchmarkState) -> BenchmarkState:
        attempt = state["error_count"] + 1
        logger.debug("extract node – attempt %d / %d", attempt, MAX_RETRIES)

        messages = _prompt_builder.build_role_benchmark_messages(state["raw_text"])

        try:
            result: RoleBenchmark = await resolved_registry.acomplete(
                messages,
                response_format=RoleBenchmark,
            )
            return {
                **state,
                "extracted_data": result,
            }
        except ValidationError as exc:
            logger.warning("ValidationError on attempt %d: %s", attempt, exc)
            error_msg: str = ", ".join(str(e) for e in exc.errors())
            return {
                **state,
                "extracted_data": None,
                "validation_errors": state["validation_errors"] + [error_msg],
                "error_count": state["error_count"] + 1,
            }
        except Exception as exc:
            logger.warning("Extraction error on attempt %d: %s", attempt, exc)
            return {
                **state,
                "extracted_data": None,
                "validation_errors": state["validation_errors"] + [str(exc)],
                "error_count": state["error_count"] + 1,
            }

    return extract


def make_embed_node(registry: LLMServiceRegistry | None = None):
    """Return an async embed node function bound to the given registry."""
    resolved_registry: LLMServiceRegistry = registry if registry is not None else get_registry()

    async def embed(state: BenchmarkState) -> BenchmarkState:
        data: RoleBenchmark = state["extracted_data"]

        corpus_parts: List[str] = (
            data.must_have_skills
            + data.nice_to_have_skills
            + data.required_tools
        )
        corpus: str = ", ".join(corpus_parts)

        logger.debug("embed node – embedding %d tokens of combined skills/tools", len(corpus))

        vectors: List[List[float]] = await resolved_registry.aembed([corpus])
        return {
            **state,
            "embedding": vectors[0],
        }

    return embed


def route_after_extract(state: BenchmarkState) -> str:
    """
    Decide the next node after extract:
    - 'embed'    if extraction succeeded.
    - 'extract'  if failed with retries remaining.
    - raises ValueError after MAX_RETRIES failures.
    """
    if state["extracted_data"] is not None:
        return "embed"

    if state["error_count"] < MAX_RETRIES:
        logger.info(
            "Retrying extraction (%d / %d failures so far).",
            state["error_count"],
            MAX_RETRIES,
        )
        return "extract"

    raise ValueError(
        f"LLM extraction failed after {MAX_RETRIES} attempts. "
        f"Validation errors collected:\n" + "\n".join(state["validation_errors"])
    )


def build_graph(registry: LLMServiceRegistry | None = None) -> Any:
    """Assemble and compile the LangGraph StateGraph."""
    graph = StateGraph(BenchmarkState)

    graph.add_node("extract", make_extract_node(registry))
    graph.add_node("embed", make_embed_node(registry))

    graph.set_entry_point("extract")

    graph.add_conditional_edges(
        "extract",
        route_after_extract,
        {
            "extract": "extract",
            "embed": "embed",
        },
    )

    graph.add_edge("embed", END)

    return graph.compile()


async def run_benchmark_pipeline(
    raw_text: str,
    registry: LLMServiceRegistry | None = None,
) -> BenchmarkState:
    """Execute the full extraction + embedding pipeline for a job description."""
    initial_state: BenchmarkState = {
        "raw_text": raw_text,
        "extracted_data": None,
        "embedding": None,
        "error_count": 0,
        "validation_errors": [],
    }

    compiled_graph = build_graph(registry=registry)
    final_state: BenchmarkState = await compiled_graph.ainvoke(initial_state)
    return final_state


async def save_benchmark(state: BenchmarkState, session: AsyncSession) -> RoleBenchmarkModel:
    """Persist the result of run_benchmark_pipeline to the database."""
    extracted = state["extracted_data"]
    if extracted is None:
        raise ValueError(
            "Cannot persist benchmark: extracted_data is None. "
            "Run run_benchmark_pipeline() successfully before calling save_benchmark()."
        )

    db_record = RoleBenchmarkModel(
        must_have_skills=extracted.must_have_skills,
        nice_to_have_skills=extracted.nice_to_have_skills,
        required_tools=extracted.required_tools,
        common_responsibilities=extracted.common_responsibilities,
        minimum_years=extracted.minimum_years,
        seniority_level=extracted.seniority_level,
        embedding=state["embedding"],
    )

    try:
        session.add(db_record)
        await session.commit()
        await session.refresh(db_record)
    except Exception as exc:
        await session.rollback()
        logger.exception("Database commit failed in save_benchmark()")
        raise RuntimeError("Failed to persist the benchmark to the database.") from exc

    logger.info(
        "Persisted benchmark id=%s (seniority=%s, min_years=%d)",
        db_record.id,
        db_record.seniority_level,
        db_record.minimum_years,
    )
    return db_record


async def mark_benchmark_reviewed(session: AsyncSession, benchmark_id: int) -> RoleBenchmarkModel:
    """Record that a human has reviewed this benchmark."""
    benchmark = await session.get(RoleBenchmarkModel, benchmark_id)
    if not benchmark:
        raise ValueError(f"Role benchmark {benchmark_id} not found")
    benchmark.reviewed_at = datetime.utcnow()
    session.add(benchmark)
    await session.commit()
    await session.refresh(benchmark)
    return benchmark
