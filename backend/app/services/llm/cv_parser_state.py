from typing_extensions import TypedDict
from typing import BinaryIO, Optional


class CVParserState(TypedDict):
    file: BinaryIO
    raw_text: str
    parsed_cv: Optional[dict]

    