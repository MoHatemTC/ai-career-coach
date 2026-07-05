"""
app/api/v1/roadmaps.py
========================
FastAPI router that exposes:

  POST /roadmaps/generate
    - Accepts a ``RoadmapRequest`` (readiness_score_id + optional focus_areas).
    - Fetches the target ``ReadinessScore`` and linked ``RoleBenchmark``
      from PostgreSQL.
    - Runs the LangGraph roadmap generation pipeline.
    - Persists the result in PostgreSQL via SQLModel.
    - Returns the generated ``RoadmapResponse`` to the caller.

  GET /roadmaps/{roadmap_id}
    - Retrieves a previously generated roadmap by its database primary key.

.. important::
   Career roadmaps produced by this endpoint are **AI-generated suggestions**.
   They do not guarantee employment outcomes, interview success, or job
   placement.  Use them as a guide alongside professional career advice.
"""

from __future__ import annotations

import logging
from typing import Annotated

import openai
from fastapi import APIRouter, Depends, HTTPException, Response, status
from prometheus_client import Histogram
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.metrics import get_or_create_metric
from app.db.connection import get_session
from app.models.career_roadmap import CareerRoadmap as CareerRoadmapModel
from app.models.readiness_score import ReadinessScore as ReadinessScoreModel
from app.models.role_benchmark import RoleBenchmark as RoleBenchmarkModel
from app.schemas.career_roadmap import (
    RoadmapRequest,
    RoadmapResponse,
    RoadmapWeek,
)
from app.services.career_roadmap_service import (
    mark_roadmap_reviewed,
    run_roadmap_pipeline,
    save_career_roadmap,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

ROADMAP_GENERATION_LATENCY = get_or_create_metric(
    Histogram,
    "roadmap_generation_latency_seconds",
    "End-to-end latency for the LLM career roadmap generation pipeline",
)

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/roadmaps", tags=["roadmaps"])

# ---------------------------------------------------------------------------
# Database session dependency
# ---------------------------------------------------------------------------

SessionDep = Annotated[AsyncSession, Depends(get_session)]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/generate",
    response_model=RoadmapResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a personalized 30-day career roadmap (AI suggestion)",
    description=(
        "Generate a structured 30-day career improvement roadmap based on a "
        "previously generated readiness score and its associated role benchmark.\n\n"
        "The roadmap recommends specific actions across four categories: "
        "skill building, portfolio projects, CV enhancements, and interview "
        "preparation — all traceable to identified gaps or weaknesses.\n\n"
        "**⚠ AI-Generated Suggestion — Does not guarantee employment outcomes.**\n\n"
        "Supply the ``readiness_score_id`` returned by ``POST /readiness/score``."
    ),
)
async def generate_roadmap(
    session: SessionDep,
    request: RoadmapRequest,
    response: Response,
) -> RoadmapResponse:
    """
    POST /roadmaps/generate

    Generates a personalized career roadmap from an existing readiness score,
    persists the result, and returns it.

    Parameters
    ----------
    session:
        Injected SQLModel database session.
    request:
        :class:`~app.schemas.career_roadmap.RoadmapRequest` — the
        ``readiness_score_id`` and optional ``focus_areas``.
    response:
        FastAPI ``Response`` object (used to set custom headers).

    Returns
    -------
    RoadmapResponse
        The generated and persisted career roadmap.

    Raises
    ------
    404 Not Found
        If ``readiness_score_id`` or the associated benchmark does not match
        any record in the database.
    502 Bad Gateway
        If the LLM API returns an error or fails after all retries.
    503 Service Unavailable
        If the LLM rate limit is reached.
    500 Internal Server Error
        For unexpected errors during the pipeline or persistence.
    """
    # ------------------------------------------------------------------
    # 1. Load the readiness score from the database
    # ------------------------------------------------------------------
    readiness_score: ReadinessScoreModel | None = await session.get(
        ReadinessScoreModel, request.readiness_score_id
    )
    if readiness_score is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"ReadinessScore with id={request.readiness_score_id!r} was not found. "
                "Create a readiness score first via POST /api/v1/readiness/score."
            ),
        )

    # ------------------------------------------------------------------
    # 2. Load the associated benchmark from the database
    # ------------------------------------------------------------------
    benchmark: RoleBenchmarkModel | None = await session.get(
        RoleBenchmarkModel, readiness_score.benchmark_id
    )
    if benchmark is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"RoleBenchmark with id={readiness_score.benchmark_id!r} was not found. "
                "The benchmark associated with this readiness score may have been deleted."
            ),
        )

    # ------------------------------------------------------------------
    # 3. Run the LangGraph roadmap pipeline (latency observed via Prometheus)
    # ------------------------------------------------------------------
    try:
        with ROADMAP_GENERATION_LATENCY.time():
            final_state = await run_roadmap_pipeline(
                readiness_score=readiness_score,
                benchmark=benchmark,
            )
    except ValueError as exc:
        logger.error("Roadmap generation pipeline exhausted retries: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM roadmap generation failed after maximum retries: {exc}",
        ) from exc
    except openai.RateLimitError as exc:
        logger.error("LLM rate limit hit during roadmap generation: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The AI model rate limit has been reached. Please retry shortly.",
        ) from exc
    except openai.AuthenticationError as exc:
        logger.error("LLM authentication failed during roadmap generation: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI model authentication failed. Check LITELLM_API_KEY.",
        ) from exc
    except openai.APIError as exc:
        logger.exception("LLM API error during roadmap generation pipeline")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI model returned an error: {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error during roadmap generation pipeline")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during roadmap generation.",
        ) from exc

    # ------------------------------------------------------------------
    # 4. Persist to PostgreSQL via the service layer
    # ------------------------------------------------------------------
    try:
        db_record: CareerRoadmapModel = await save_career_roadmap(
            state=final_state,
            session=session,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    # ------------------------------------------------------------------
    # 5. Set observability header (Langfuse trace integration point)
    # ------------------------------------------------------------------
    response.headers["X-Career-Roadmap-Id"] = str(db_record.id)

    # ------------------------------------------------------------------
    # 6. Build and return the API response
    # ------------------------------------------------------------------
    roadmap = final_state["roadmap"]

    # Apply focus_areas filter if provided
    filtered_weeks = roadmap.weeks
    if request.focus_areas:
        allowed_categories = set(request.focus_areas)
        filtered_weeks = []
        for week in roadmap.weeks:
            filtered_actions = [
                a for a in week.actions if a.category in allowed_categories
            ]
            if filtered_actions:
                filtered_weeks.append(
                    RoadmapWeek(
                        week_number=week.week_number,
                        theme=week.theme,
                        actions=filtered_actions,
                    )
                )
            else:
                # Keep the week with original actions if filter empties it
                filtered_weeks.append(week)

    return RoadmapResponse(
        id=db_record.id,
        readiness_score_id=db_record.readiness_score_id,
        created_at=db_record.created_at,
        weeks=filtered_weeks,
        executive_summary=roadmap.executive_summary,
        key_focus_areas=roadmap.key_focus_areas,
        responsible_ai_disclaimer=roadmap.responsible_ai_disclaimer,
    )


@router.get(
    "/{roadmap_id}",
    response_model=RoadmapResponse,
    summary="Retrieve a previously generated career roadmap",
    description=(
        "Fetch a career roadmap by its database primary key. "
        "Returns the full roadmap including all weekly plans, "
        "executive summary, and responsible AI disclaimer."
    ),
)
async def get_roadmap(
    session: SessionDep,
    roadmap_id: int,
) -> RoadmapResponse:
    """
    GET /roadmaps/{roadmap_id}

    Retrieves a previously generated and persisted career roadmap.

    Parameters
    ----------
    session:
        Injected SQLModel database session.
    roadmap_id:
        Database primary key of the roadmap to retrieve.

    Returns
    -------
    RoadmapResponse
        The persisted career roadmap.

    Raises
    ------
    404 Not Found
        If no roadmap with the given ID exists.
    """
    db_record: CareerRoadmapModel | None = await session.get(
        CareerRoadmapModel, roadmap_id
    )
    if db_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"CareerRoadmap with id={roadmap_id!r} was not found.",
        )

    return RoadmapResponse(
        id=db_record.id,
        readiness_score_id=db_record.readiness_score_id,
        created_at=db_record.created_at,
        weeks=db_record.weeks,
        executive_summary=db_record.executive_summary,
        key_focus_areas=db_record.key_focus_areas,
        responsible_ai_disclaimer=db_record.responsible_ai_disclaimer,
    )


@router.patch("/{roadmap_id}/review", response_model=RoadmapResponse, status_code=status.HTTP_200_OK)
async def review_roadmap(roadmap_id: int, session: AsyncSession = Depends(get_session)):
    """Record that a human has reviewed this career roadmap."""
    try:
        roadmap = await mark_roadmap_reviewed(session, roadmap_id)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    return RoadmapResponse(
        id=roadmap.id,
        readiness_score_id=roadmap.readiness_score_id,
        created_at=roadmap.created_at,
        reviewed_at=roadmap.reviewed_at,
        weeks=roadmap.weeks,
        executive_summary=roadmap.executive_summary,
        key_focus_areas=roadmap.key_focus_areas,
        responsible_ai_disclaimer=roadmap.responsible_ai_disclaimer,
    )
