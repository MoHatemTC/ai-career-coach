from langgraph.graph import StateGraph, START, END
from app.services.llm.cv_parser_state import CVParserState
from app.services.llm.cv_parser_tool import read_text_from_file_object
from app.services.llm.llm_cv_parser import parse_cv
# --------------------------------------------------
# 1. Build the graph
# --------------------------------------------------

builder = StateGraph(CVParserState)

builder.add_node("read_cv_text", read_text_from_file_object)
builder.add_node("parse_cv_with_litellm", parse_cv)

builder.add_edge(START, "read_cv_text")
builder.add_edge("read_cv_text", "parse_cv_with_litellm")
builder.add_edge("parse_cv_with_litellm", END)

cv_parser_graph = builder.compile()
