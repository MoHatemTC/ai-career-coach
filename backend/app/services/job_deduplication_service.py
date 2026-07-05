"""
Deduplication service for job postings.

Two-tier dedup key, in priority order:

  1. **`(source, external_id)`** — the source's stable per-posting id (e.g. the
     Wuzzuf UUID). Preferred whenever present: immune to title/company edits.
  2. **`content_hash`** — SHA-256 fallback for sources without a stable id
     (fixtures). Computed by ``JobPosting.compute_content_hash()`` — the single
     source of truth for that recipe.

Works on validated ``JobPosting`` objects only; never sees source-specific raw
data.
"""

from collections import defaultdict
from dataclasses import dataclass

import structlog
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import JobPosting, JobTable

logger = structlog.get_logger()


@dataclass(frozen=True)
class DeduplicationResult:
    """Outcome of a deduplication run."""

    new_jobs: list[JobPosting]
    duplicate_count: int
    total_incoming: int


def _internal_key(job: JobPosting) -> tuple:
    """Stable key for collapsing duplicates *within* the incoming batch."""
    if job.external_id:
        return ("ext", job.source, job.external_id)
    return ("hash", job.compute_content_hash())


async def _existing_external_ids(
    session: AsyncSession, jobs: list[JobPosting]
) -> set[tuple[str, str]]:
    """Return the `(source, external_id)` pairs already stored, in one query per source."""
    by_source: dict[str, list[str]] = defaultdict(list)
    for job in jobs:
        by_source[job.source].append(job.external_id)  # type: ignore[arg-type]

    existing: set[tuple[str, str]] = set()
    for source, ids in by_source.items():
        stmt = select(JobTable.source, JobTable.external_id).where(
            JobTable.source == source,
            JobTable.external_id.in_(ids),  # type: ignore[attr-defined]
        )
        rows = (await session.exec(stmt)).all()
        existing.update((r[0], r[1]) for r in rows)
    return existing


async def _existing_hashes(
    session: AsyncSession, hashes: list[str]
) -> set[str]:
    """Return the content hashes already stored (single query)."""
    if not hashes:
        return set()
    stmt = select(JobTable.content_hash).where(
        JobTable.content_hash.in_(hashes)  # type: ignore[attr-defined]
    )
    return set((await session.exec(stmt)).all())


async def deduplicate(
    jobs: list[JobPosting],
    session: AsyncSession,
) -> DeduplicationResult:
    """Filter out jobs already present in the DB (by external_id, else hash)."""
    if not jobs:
        logger.info("deduplication_skipped", reason="empty_input")
        return DeduplicationResult(new_jobs=[], duplicate_count=0, total_incoming=0)

    # 1. Collapse duplicates within the incoming batch.
    seen: set[tuple] = set()
    unique_jobs: list[JobPosting] = []
    for job in jobs:
        key = _internal_key(job)
        if key in seen:
            continue
        seen.add(key)
        unique_jobs.append(job)
    internal_dupes = len(jobs) - len(unique_jobs)

    # 2. Split by which dedup tier applies.
    ext_jobs = [j for j in unique_jobs if j.external_id]
    hash_jobs = [j for j in unique_jobs if not j.external_id]

    # 3. Single round-trip per tier.
    existing_ext = await _existing_external_ids(session, ext_jobs)
    existing_hashes = await _existing_hashes(
        session, [j.compute_content_hash() for j in hash_jobs]
    )

    # 4. Keep only genuinely new jobs.
    new_jobs = [
        j for j in ext_jobs if (j.source, j.external_id) not in existing_ext
    ] + [
        j for j in hash_jobs if j.compute_content_hash() not in existing_hashes
    ]

    db_dupes = len(unique_jobs) - len(new_jobs)
    total_dupes = db_dupes + internal_dupes

    logger.info(
        "deduplication_complete",
        total_incoming=len(jobs),
        internal_duplicates=internal_dupes,
        db_duplicates=db_dupes,
        new_jobs=len(new_jobs),
    )

    return DeduplicationResult(
        new_jobs=new_jobs,
        duplicate_count=total_dupes,
        total_incoming=len(jobs),
    )
