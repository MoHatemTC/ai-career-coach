import uuid
from typing import List, Optional, Tuple

from app.schemas.matching import MatchRequest, JobMatchResponse
from app.ai.graph import compiled_matching_graph

from sqlmodel.ext.asyncio.session import AsyncSession

# --- Core Pipeline Service ---

class JobMatchingService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def execute_match(self, request: MatchRequest) -> JobMatchResponse:
        """
        Executes the two-stage matching pipeline via LangGraph orchestration.
        """
        # Inject the request and database dependency into the initial LangGraph state
        initial_state = {
            "request": request,
            "session": self.session
        }
        
        # Invoke the compiled StateGraph
        final_state = await compiled_matching_graph.ainvoke(initial_state)
        
        # Handle conditional aborts (e.g., job not found)
        if final_state.get("error"):
            raise ValueError(final_state["error"])
            
        # Map the final state payload to the Pydantic response contract
        return JobMatchResponse(
            job_id=request.job_id,
            candidate_id=request.candidate_id,
            result=final_state["llm_result"],
            vector_distance=final_state["vector_distance"]
        )
