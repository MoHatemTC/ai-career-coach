from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from app.schemas.matching import (
    MatchRequest,
    JobMatchResult,
    MatchScoreDetails,
)
from app.services.job_matching_service import JobMatchingService
from tests.services.mock_data import PERFECT_CANDIDATE, TARGET_JOB_ID, CANDIDATE_ID


def _make_request(candidate_profile=PERFECT_CANDIDATE):
    return MatchRequest(
        candidate_id=CANDIDATE_ID,
        job_id=TARGET_JOB_ID,
        candidate_profile=candidate_profile,
    )


@pytest.mark.asyncio
@patch("app.services.job_matching_service.compiled_matching_graph")
async def test_execute_match_job_not_found(mock_graph):
    """execute_match raises ValueError when the matching graph reports the job is missing."""
    mock_graph.ainvoke = AsyncMock(return_value={"error": f"Job with id={TARGET_JOB_ID} not found"})

    service = JobMatchingService(session=MagicMock())

    with pytest.raises(ValueError, match="not found"):
        await service.execute_match(_make_request())


@pytest.mark.asyncio
@patch("app.services.job_matching_service.compiled_matching_graph")
async def test_execute_match_maps_graph_result_to_response(mock_graph):
    """execute_match maps the final LangGraph state onto a JobMatchResponse."""
    llm_result = JobMatchResult(
        score_details=MatchScoreDetails(
            hard_skills_score=38,
            experience_score=28,
            soft_skills_score=19,
            logistics_score=10,
        ),
        total_score=95,
        explanation="Strong match.",
        strengths=["Python", "FastAPI"],
        missing_skills=[],
        recommendation="Apply.",
    )
    mock_graph.ainvoke = AsyncMock(
        return_value={"llm_result": llm_result, "vector_distance": 0.15}
    )

    service = JobMatchingService(session=MagicMock())
    response = await service.execute_match(_make_request())

    assert response.job_id == TARGET_JOB_ID
    assert response.candidate_id == CANDIDATE_ID
    assert response.result == llm_result
    assert response.vector_distance == 0.15
