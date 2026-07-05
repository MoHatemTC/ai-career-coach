"""
Job Collection API — /api/v1/jobs

Endpoints:
    POST /cv/   — parse_cv
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from app.services.llm.cv_parser_service import cv_parser_graph
from app.services.log_service import write_log
from io import BytesIO
from sqlmodel.ext.asyncio.session import AsyncSession
from app.db.connection import get_session
from app.models.jobs import UserProfile
from pydantic import BaseModel
from typing import Optional, Any

class CVParseResponse(BaseModel):
    user_id: Optional[int] = None
    parsed_cv: Any

router = APIRouter()

@router.post("", response_model=CVParseResponse)
async def parse_uploaded_cv(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session)
) -> CVParseResponse:
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are allowed"
        )

    contents = await file.read()

    await write_log(session, stage="cv_parse", status="started", message=file.filename)
    try:
        result = await cv_parser_graph.ainvoke({
            "file": BytesIO(contents),
            "raw_text": "",
            "parsed_cv": None
        })
    except Exception as e:
        await write_log(
            session, stage="error", status="failure",
            message=str(e), metadata={"stage": "cv_parse"},
        )
        await session.commit()
        raise HTTPException(status_code=500, detail=f"CV parsing failed: {e}")

    parsed_cv = result["parsed_cv"]
    await write_log(
        session, stage="cv_parse", status="success",
        metadata={"chars": len(result.get("raw_text") or "")},
    )

    # Check if the parsed result is a successful UserProfile object
    if isinstance(parsed_cv, UserProfile):
        from app.services.skills.canonicalizer import canonicalize_one
        
        canonical_skills = []
        for s in parsed_cv.skills:
            c = canonicalize_one(s)
            if c and c not in canonical_skills:
                canonical_skills.append(c)
        parsed_cv.skills = canonical_skills
        
        canonical_tools = []
        for t in parsed_cv.tools:
            c = canonicalize_one(t)
            if c and c not in canonical_tools:
                canonical_tools.append(c)
        parsed_cv.tools = canonical_tools

        # Save to database
        user_table = parsed_cv.to_user_table()
        session.add(user_table)
        await session.flush()
        await write_log(
            session, stage="profile_extract", status="success",
            user_id=user_table.id,
            metadata={"skills": len(parsed_cv.skills), "tools": len(parsed_cv.tools)},
        )
        await session.commit()
        await session.refresh(user_table)

        return CVParseResponse(
            user_id=user_table.id,
            parsed_cv=parsed_cv.model_dump()
        )

    # LLM did not return a structured profile — record a profile_extract failure.
    await write_log(session, stage="profile_extract", status="failure")
    await session.commit()

    if hasattr(parsed_cv, "model_dump"):
        return CVParseResponse(parsed_cv=parsed_cv.model_dump())

    return CVParseResponse(parsed_cv=parsed_cv)