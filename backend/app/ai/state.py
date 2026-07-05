from typing import TypedDict, Optional, Any
from app.schemas.matching import MatchRequest, JobMatchResult

class MatchingState(TypedDict):
    """
    LangGraph State dictionary to track the flow of data through the matching pipeline nodes.
    """
    request: MatchRequest
    session: Any # Database dependency injected from the service layer
    target_job: Optional[Any] # Populated by pre_filter
    vector_distance: Optional[float] # Populated by pre_filter
    llm_result: Optional[JobMatchResult] # Populated by llm_evaluation
    error: Optional[str] # Populated if an exception or abort condition occurs
