
from app.services.llm.cv_parser_tool_node import read_text_from_file_object
from app.services.llm.cv_parser_state import CVParserState


def read_cv_text_node(state: CVParserState) -> dict:
    text = read_text_from_file_object(state["file"])

    return {
        "raw_text": text
    }

