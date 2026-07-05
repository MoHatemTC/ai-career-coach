import logging
from typing import TypedDict, Optional, Any
from langgraph.graph import StateGraph, END
from langfuse import observe
from prometheus_client import Counter, Histogram
from app.core.metrics import get_or_create_metric

from app.schemas.application_ai import (
    ApplicationRequest,
    CVTailoringResult,
    CoverLetterResult,
    ApplicationResponse
)
from app.ai.registry import get_registry
from app.models.jobs import JobTable
from sqlmodel.ext.asyncio.session import AsyncSession

logger = logging.getLogger("application_ai")

# --- Prometheus Metrics ---
PIPELINE_REQUESTS = get_or_create_metric(Counter, "application_ai_requests_total", "Count of application AI requests", ["status"])
LLM_LATENCY = get_or_create_metric(Histogram, "llm_call_duration_seconds", "Duration of LLM calls", ["stage"])

# --- 1. State Definition ---
class ApplicationState(TypedDict):
    """LangGraph State for tracking application materials generation."""
    request: ApplicationRequest
    session: Any  # Database dependency injected from the service layer
    job_description: Optional[str]  # Resolved job description (from request or DB)
    cv_tailoring_result: Optional[CVTailoringResult]
    cover_letter_result: Optional[CoverLetterResult]
    error: Optional[str]

# --- 2. Node Functions ---
# (Prompt templates are now managed by app.ai.prompts.PromptBuilder)

@observe()
async def job_resolution_node(state: ApplicationState) -> ApplicationState:
    """Stage 0: Resolve job description from DB if not provided in the request."""
    request = state["request"]
    session = state["session"]

    if request.job_description:
        # Client provided the job description directly
        state["job_description"] = request.job_description
        return state

    # Resolve from the database using job_id
    if session is None:
        state["error"] = "No job description provided and no database connection available."
        return state

    target_job = await session.get(JobTable, request.job_id)
    if not target_job:
        state["error"] = f"Job with ID {request.job_id} not found."
        return state

    state["job_description"] = target_job.description
    logger.info(f"Resolved job description from DB | job_id={request.job_id}")
    return state

@observe()
async def cv_tailoring_node(state: ApplicationState) -> ApplicationState:
    """Stage 2: CV Tailoring using LLM"""
    from app.ai.prompts import PromptBuilder
    request = state["request"]
    job_description = state["job_description"]
    registry = get_registry()
    
    candidate_profile_json = request.candidate_profile.model_dump_json()
    
    messages = PromptBuilder.build_cv_tailoring_messages(
        candidate_profile=candidate_profile_json,
        job_description=job_description
    )
    
    try:
        with LLM_LATENCY.labels(stage="cv_tailoring").time():
            result = await registry.acomplete(messages, response_format=CVTailoringResult)
        state["cv_tailoring_result"] = result
        logger.info(f"CV Tailoring successful | candidate_id={request.candidate_id} | job_id={request.job_id}")
    except Exception as e:
        logger.error(f"CV Tailoring Error | candidate_id={request.candidate_id} | job_id={request.job_id} | error={str(e)}")
        state["error"] = f"Failed to generate tailored CV: {str(e)}"
        
    return state

@observe()
async def cover_letter_node(state: ApplicationState) -> ApplicationState:
    """Stage 3: Cover Letter Generation using LLM"""
    from app.ai.prompts import PromptBuilder
    request = state["request"]
    job_description = state["job_description"]
    cv_result = state["cv_tailoring_result"]
    registry = get_registry()
    
    cv_result_json = cv_result.model_dump_json() if cv_result else "{}"
    
    messages = PromptBuilder.build_cover_letter_messages(
        cv_tailoring_result=cv_result_json,
        job_description=job_description
    )
    
    try:
        with LLM_LATENCY.labels(stage="cover_letter").time():
            result = await registry.acomplete(messages, response_format=CoverLetterResult)
        state["cover_letter_result"] = result
        logger.info(f"Cover Letter Generation successful | candidate_id={request.candidate_id} | job_id={request.job_id}")
    except Exception as e:
        logger.error(f"Cover Letter Error | candidate_id={request.candidate_id} | job_id={request.job_id} | error={str(e)}")
        state["error"] = f"Failed to generate cover letter: {str(e)}"
        
    return state

# --- 3. Graph Compilation ---
def create_application_graph():
    workflow = StateGraph(ApplicationState)
    
    workflow.add_node("job_resolution", job_resolution_node)
    workflow.add_node("cv_tailoring", cv_tailoring_node)
    workflow.add_node("cover_letter", cover_letter_node)

    workflow.set_entry_point("job_resolution")

    def check_resolution_error(state: ApplicationState):
        if state.get("error"):
            return END
        return "cv_tailoring"

    def check_cv_error(state: ApplicationState):
        if state.get("error"):
            return END
        return "cover_letter"

    workflow.add_conditional_edges("job_resolution", check_resolution_error, {"cv_tailoring": "cv_tailoring", END: END})
    workflow.add_conditional_edges("cv_tailoring", check_cv_error, {"cover_letter": "cover_letter", END: END})
    workflow.add_edge("cover_letter", END)

    return workflow.compile()

compiled_application_graph = create_application_graph()

# --- 4. Service Class ---
class ApplicationAIService:
    def __init__(self, session: AsyncSession = None):
        """
        Initialize the Application AI Service.
        
        Args:
            session: Optional AsyncSession instance. Required when the client does not
                provide a job_description in the request and expects the service to
                resolve it from the database using job_id.
        """
        self.session = session

    async def generate_application_materials(self, request: ApplicationRequest) -> ApplicationResponse:
        """
        Executes the application-material generation pipeline via LangGraph.

        Stages:
            1. Job Resolution — use the provided job description (or resolve from DB)
            2. CV Tailoring — LLM-powered CV improvement suggestions
            3. Cover Letter — LLM-powered cover letter generation (uses the CV result)
        """
        initial_state = {
            "request": request,
            "session": self.session,
            "job_description": request.job_description,
            "cv_tailoring_result": None,
            "cover_letter_result": None,
            "error": None
        }
        
        final_state = await compiled_application_graph.ainvoke(initial_state)
        
        if final_state.get("error"):
            PIPELINE_REQUESTS.labels(status="error").inc()
            raise ValueError(final_state["error"])
            
        PIPELINE_REQUESTS.labels(status="success").inc()
        return ApplicationResponse(
            candidate_id=request.candidate_id,
            job_id=request.job_id,
            cv_tailoring=final_state["cv_tailoring_result"],
            cover_letter=final_state["cover_letter_result"]
        )
