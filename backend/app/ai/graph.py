from langgraph.graph import StateGraph, END
from app.ai.state import MatchingState
from app.ai.nodes import pre_filter_node, llm_evaluation_node

def create_matching_graph():
    """
    Compiles the two-stage Job Matching Engine into a scalable LangGraph flow.
    """
    workflow = StateGraph(MatchingState)
    
    # Add our processing nodes
    workflow.add_node("pre_filter", pre_filter_node)
    workflow.add_node("llm_evaluation", llm_evaluation_node)
    
    # Set entry point
    workflow.set_entry_point("pre_filter")
    
    # Define conditional routing (e.g. abort if job not found)
    def check_error(state: MatchingState):
        if state.get("error"):
            return END
        return "llm_evaluation"
        
    workflow.add_conditional_edges(
        "pre_filter",
        check_error,
        {
            "llm_evaluation": "llm_evaluation",
            END: END
        }
    )
    
    # End successfully after LLM evaluation
    workflow.add_edge("llm_evaluation", END)
    
    return workflow.compile()

# Compile standard instance
compiled_matching_graph = create_matching_graph()
