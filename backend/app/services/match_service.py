"""
app/services/match_service.py
=============================
Persisted (user, job) match analysis — the real-schema replacement for the old
shadow readiness/gap-analysis feature.

Loads ``UserTable`` and ``JobTable`` from Postgres, runs an LLM gap analysis with
structured output (:class:`MatchAnalysis`), and upserts the result into
``JobMatchTable`` on the ``uq_job_matches_user_job`` constraint.

:func:`upsert_job_match` is the *single* canonical writer for ``job_matches`` and
is reused by ``job_tracking_service`` so both paths agree on conflict handling
(the materials path passes only the CV/cover columns and never clobbers a real
``match_score``).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.prompts import PromptBuilder
from app.ai.registry import get_registry
from app.models.helpers import _utcnow
from app.models.jobs import JobMatchTable, JobTable, UserTable
from app.schemas.match_analysis import MatchAnalysis
from app.services.log_service import write_log

logger = logging.getLogger(__name__)

# Job description is truncated in the LLM payload to keep the prompt bounded.
_JOB_DESC_CAP = 4000

# Any modification to these AI-generated columns definitively resets the human-review flag.
_CONTENT_COLUMNS = {
    "match_score",
    "match_explanation",
    "missing_skills",
    "strengths",
    "cv_tailoring_suggestion",
    "cover_letter_draft",
}


async def upsert_job_match(
    session: AsyncSession,
    *,
    user_id: int,
    job_id: int,
    **columns: Any,
) -> None:
    """Insert-or-update the ``job_matches`` row for ``(user_id, job_id)``.

    On conflict, only the columns explicitly passed in ``columns`` are updated
    (plus ``updated_at``), so a caller writing just CV/cover-letter fields never
    overwrites an existing ``match_score``.

    Follows the repo convention: only stages the statement on the session — the
    caller owns commit/rollback.
    """
    # Automatically un-review if any AI content is being written, unless explicitly overridden.
    if _CONTENT_COLUMNS & columns.keys() and "reviewed_at" not in columns:
        columns["reviewed_at"] = None

    now = _utcnow()
    values: dict[str, Any] = {
        "user_id": user_id,
        "job_id": job_id,
        # Defaults so INSERT satisfies NOT NULL even when a caller supplies only
        # a subset of columns (e.g. the materials path).
        "match_score": 0,
        "match_explanation": "",
        "missing_skills": [],
        "strengths": [],
        "cv_tailoring_suggestion": "",
        "reviewed_at": None,
        "created_at": now,
        "updated_at": now,
    }
    values.update(columns)

    stmt = insert(JobMatchTable).values(**values)
    update_set = {key: getattr(stmt.excluded, key) for key in columns}
    update_set["updated_at"] = stmt.excluded.updated_at
    stmt = stmt.on_conflict_do_update(
        constraint="uq_job_matches_user_job", set_=update_set
    )
    await session.execute(stmt)


def _candidate_json(user: UserTable) -> str:
    return json.dumps(
        {
            "name": user.name,
            "skills": user.skills,
            "tools": user.tools,
            "years_of_experience": user.years_of_experience,
            "career_level": user.career_level,
            "education": user.education,
            "certifications": user.certifications,
            "projects": user.projects,
            "completed_courses": user.completed_courses,
            "desired_roles": user.desired_roles,
        },
        ensure_ascii=False,
    )


def _job_json(job: JobTable) -> str:
    return json.dumps(
        {
            "title": job.title,
            "company": job.company,
            "required_skills": job.required_skills,
            "work_roles": job.work_roles,
            "experience_level": job.experience_level,
            "work_mode": job.work_mode,
            "description": (job.description or "")[:_JOB_DESC_CAP],
        },
        ensure_ascii=False,
    )


class MatchService:
    """Runs and persists AI match analysis for a real ``(user_id, job_id)`` pair."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def analyze(self, user_id: int, job_id: int) -> JobMatchTable:
        session = self.session

        user = await session.get(UserTable, user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        job = await session.get(JobTable, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        registry = get_registry()
        await write_log(
            session, stage="matching", status="started", user_id=user_id, job_id=job_id
        )

        try:
            messages = PromptBuilder.build_match_analysis_messages(
                candidate_profile=_candidate_json(user),
                job_posting=_job_json(job),
            )
            result: MatchAnalysis = await registry.acomplete(
                messages, response_format=MatchAnalysis
            )
        except Exception as e:  # noqa: BLE001 — audit then re-raise
            await write_log(
                session,
                stage="error",
                status="failure",
                message=str(e),
                user_id=user_id,
                job_id=job_id,
                metadata={"stage": "matching"},
            )
            await session.commit()
            raise

        await upsert_job_match(
            session,
            user_id=user_id,
            job_id=job_id,
            match_score=result.match_score,
            match_explanation=result.match_explanation,
            missing_skills=result.missing_skills,
            strengths=result.strengths,
            cv_tailoring_suggestion=result.cv_tailoring_suggestion,
            cover_letter_draft=result.cover_letter_draft,
        )
        await write_log(
            session,
            stage="matching",
            status="success",
            user_id=user_id,
            job_id=job_id,
            metadata={"match_score": result.match_score, "model": registry._LLM_MODEL},
        )
        await session.commit()

        # The upsert is a core INSERT ... ON CONFLICT, which bypasses the ORM
        # identity map — populate_existing forces the read to overwrite any cached
        # instance with fresh DB values.
        stmt = (
            select(JobMatchTable)
            .where(
                JobMatchTable.user_id == user_id,
                JobMatchTable.job_id == job_id,
            )
            .execution_options(populate_existing=True)
        )
        row = (await session.exec(stmt)).first()
        return row


async def mark_job_match_reviewed(session: AsyncSession, match_id: int) -> JobMatchTable:
    """Record that a human has reviewed this match's AI-generated content."""
    match = await session.get(JobMatchTable, match_id)
    if not match:
        raise ValueError(f"Job match {match_id} not found")
    match.reviewed_at = _utcnow()
    session.add(match)
    await session.commit()
    await session.refresh(match)
    return match
