import asyncio
from pypdf import PdfReader
from typing import BinaryIO

from app.services.llm.cv_parser_state import CVParserState


def _extract_text_sync(file_obj) -> str:
    reader = PdfReader(file_obj)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + '\n'
    return text


async def read_text_from_file_object(state: CVParserState) -> dict:
    text = await asyncio.to_thread(_extract_text_sync, state['file'])
    return {
        "raw_text": text
    }