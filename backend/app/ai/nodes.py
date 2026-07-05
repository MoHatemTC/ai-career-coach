import os
import logging
from app.ai.state import MatchingState
from app.schemas.matching import JobMatchResult, MatchScoreDetails
from app.ai.registry import get_registry
from app.core.embeddings import build_candidate_text_from_profile
from sqlmodel import select
from app.models.jobs import JobTable

logger = logging.getLogger("job_matching")

async def pre_filter_node(state: MatchingState) -> MatchingState:
    """Stage 1: Vector Database Search Node."""
    request = state["request"]
    session = state["session"]
    
    target_job = await session.get(JobTable, request.job_id)
    if not target_job:
        # Signal the graph to halt by injecting an error
        state["error"] = f"Job with ID {request.job_id} not found."
        return state
        
    state["target_job"] = target_job
    
    # Perform vector search using the canonical candidate text builder
    candidate_summary = build_candidate_text_from_profile(request.candidate_profile)
    try:
        registry = get_registry()
        vectors = await registry.aembed([candidate_summary])
        candidate_embedding = vectors[0]
    except Exception as e:
        logger.error(f"Failed to generate embedding for candidate {request.candidate_id}: {str(e)}")
        candidate_embedding = [0.0] * get_registry().embedding_dim
        
    distance = 0.12
    if target_job.embedding is not None:
        try:
            stmt = select(JobTable.embedding.cosine_distance(candidate_embedding)).where(JobTable.id == target_job.id)
            res = await session.exec(stmt)
            db_dist = res.first()
            if db_dist is not None:
                distance = db_dist
        except Exception as e:
            logger.error(f"Vector distance calculation failed for job {target_job.id}: {str(e)}")
            
    state["vector_distance"] = distance
    return state

async def llm_evaluation_node(state: MatchingState) -> MatchingState:
    """Stage 2: LLM Re-ranking Node."""
    request = state["request"]
    target_job = state["target_job"]
    
    from app.ai.prompts import PromptBuilder

    # Scrub PII before inference
    safe_profile = request.candidate_profile.model_copy(deep=True)
    safe_profile.name = "REDACTED"
    safe_profile.contact = {}
    candidate_profile_json = safe_profile.model_dump_json()
    
    messages = PromptBuilder.build_job_matching_messages(
        candidate_profile=candidate_profile_json,
        job_description=target_job.description
    )

    registry = get_registry()
    
    # Use the unified LLM service registry
    try:
        result = await registry.acomplete(messages, response_format=JobMatchResult)
        state["llm_result"] = result
        logger.info(f"Match successful | candidate_id={request.candidate_id} | job_id={request.job_id} | score={result.total_score}")
    except Exception as e:
        logger.error(f"LLM Error | candidate_id={request.candidate_id} | job_id={request.job_id} | error={str(e)}")
        state["llm_result"] = JobMatchResult(
            score_details=MatchScoreDetails(
                hard_skills_score=0,
                experience_score=0,
                soft_skills_score=0,
                logistics_score=0
            ),
            total_score=0,
            explanation=f"Error evaluating candidate (JSON parsing or LLM API failure): {str(e)}",
            strengths=[],
            missing_skills=[],
            recommendation="Evaluation aborted due to system error."
        )

    return state
