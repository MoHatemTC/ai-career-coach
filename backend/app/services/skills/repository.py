"""
Persistence for canonical skills — the only skills layer that touches the DB.

`link_skills` get-or-creates `SkillTable` rows for a job's canonical skill
tokens and links them via `JobSkillLink`. Pure normalization lives in
:mod:`app.services.skills.canonicalizer`; this module deliberately does no
canonicalization of its own — callers pass already-canonical names.
"""

from collections.abc import Iterable

import structlog
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import JobSkillLink, JobTable, SkillTable

logger = structlog.get_logger()


async def link_skills(
    session: AsyncSession,
    job_row: JobTable,
    skill_names: Iterable[str],
) -> None:
    """Link a persisted job to its canonical skills, creating any new skills.

    `job_row` must already have an `id` (i.e. be flushed). Names are assumed
    canonical/lowercase; blanks and duplicates are ignored. New `SkillTable`
    rows are flushed so their ids are available for the link rows.
    """
    names = list(dict.fromkeys(n for n in skill_names if n))
    if not names:
        return

    existing = (
        await session.exec(select(SkillTable).where(SkillTable.name.in_(names)))  # type: ignore[attr-defined]
    ).all()
    by_name: dict[str, SkillTable] = {s.name: s for s in existing}

    new_skills = [SkillTable(name=n) for n in names if n not in by_name]
    if new_skills:
        session.add_all(new_skills)
        await session.flush()  # assign primary keys before linking
        by_name.update({s.name: s for s in new_skills})

    for name in names:
        session.add(JobSkillLink(job_id=job_row.id, skill_id=by_name[name].id))
