from pypdf import PdfReader
from typing import BinaryIO

from app.services.llm.cv_parser_state import CVParserState


def read_text_from_file_node(state:CVParserState)->str:

    reader=PdfReader(state['file'])

    text=""


    for page in reader.pages:

        page_text=page.extract_text()

        if page_text:
            text+=page_text+'\n'
    
    return {
        "raw_text": text
    }
        