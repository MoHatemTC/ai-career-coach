"""
Job collection pipeline orchestrator.

Runs the full pipeline for one or more job sources:
    Source.fetch() → deduplicate() → insert into DB

Source-agnostic: accepts any BaseJobSource subclass.
New sources are added by creating a class that extends BaseJobSource
and registering it in the SOURCE_REGISTRY.
"""

import asyncio
from dataclasses import dataclass, field

import structlog
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import JobPosting, JobTable
from app.core.embeddings import EMBEDDING_DIM, EMBEDDING_MODEL, build_job_text, embed
from app.services.job_sources.base import BaseJobSource
from app.services.job_sources.fixture import FixtureSource
from app.services.job_sources.wuzzuf import WuzzufSource
from app.services.job_deduplication_service import deduplicate
from app.services.log_service import write_log
from app.services.skills.repository import link_skills

logger = structlog.get_logger()


async def _embed_rows(rows: list[JobTable]) -> int:
    """Populate ``row.embedding`` for each row via one batched encode.

    Runs the CPU/GPU-bound model in a worker thread so the async pipeline is not
    blocked. Returns the number of rows embedded.
    """
    if not rows:
        return 0
    texts = [build_job_text(row) for row in rows]
    vectors = await asyncio.to_thread(embed, texts)
    for row, vector in zip(rows, vectors):
        row.embedding = vector
    return len(rows)

# Maps source_name strings used in API/CLI requests to BaseJobSource classes.
# Register new sources here to keep the pipeline source-agnostic.
SOURCE_REGISTRY: dict[str, type[BaseJobSource]] = {
    "fixture": FixtureSource,
    "wuzzuf": WuzzufSource,
}


def get_available_sources() -> list[str]:
    """Return the list of registered source names."""
    return list(SOURCE_REGISTRY.keys())


def get_source(name: str) -> BaseJobSource:
    """Instantiate a registered source by name.

    Raises:
        ValueError: If the source name is not in the registry.
    """
    source_cls = SOURCE_REGISTRY.get(name)
    if source_cls is None:
        available = ", ".join(SOURCE_REGISTRY.keys())
        raise ValueError(
            f"Unknown job source '{name}'. Available sources: {available}"
        )
    return source_cls()


# ---------------------------------------------------------------------------
# Pipeline result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CollectionResult:
    """Outcome of a single collection run."""

    source: str
    fetched: int
    inserted: int
    duplicates: int
    errors: int


@dataclass(frozen=True)
class BatchCollectionResult:
    """Outcome when collecting from multiple sources in one call."""

    results: list[CollectionResult] = field(default_factory=list)

    @property
    def total_inserted(self) -> int:
        return sum(r.inserted for r in self.results)

    @property
    def total_duplicates(self) -> int:
        return sum(r.duplicates for r in self.results)

    @property
    def total_errors(self) -> int:
        return sum(r.errors for r in self.results)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

async def collect_from_source(
    source: BaseJobSource,
    session: AsyncSession,
) -> CollectionResult:
    """Run the full pipeline for a single source.

    Steps:
        1. Fetch validated JobPosting objects from the source.
        2. Deduplicate against existing DB records.
        3. Convert new jobs to JobTable rows and insert them.

    All DB writes happen inside the caller's session — the caller
    is responsible for committing or rolling back.

    Args:
        source: Any BaseJobSource subclass instance.
        session: Active SQLModel session.

    Returns:
        CollectionResult with counts of fetched, inserted, duplicates, errors.
    """
    source_name = source.source_name

    # --- Step 1: Fetch -------------------------------------------------------
    logger.info("job_collection_fetch_started", source=source_name)
    try:
        jobs: list[JobPosting] = await source.fetch()
    except Exception:
        logger.exception("job_collection_fetch_failed", source=source_name)
        await write_log(
            session,
            stage="job_ingest",
            status="failure",
            message=f"fetch failed for source '{source_name}'",
            metadata={
                "source": source_name,
                "fetched": 0,
                "inserted": 0,
                "duplicates": 0,
                "errors": 1,
            },
        )
        return CollectionResult(
            source=source_name,
            fetched=0,
            inserted=0,
            duplicates=0,
            errors=1,
        )

    logger.info("job_collection_fetch_complete", source=source_name, count=len(jobs))

    if not jobs:
        await write_log(
            session,
            stage="job_ingest",
            status="success",
            message=f"no jobs returned by source '{source_name}'",
            metadata={
                "source": source_name,
                "fetched": 0,
                "inserted": 0,
                "duplicates": 0,
                "errors": 0,
            },
        )
        return CollectionResult(
            source=source_name,
            fetched=0,
            inserted=0,
            duplicates=0,
            errors=0,
        )

    # --- Step 2: Deduplicate -------------------------------------------------
    dedup_result = await deduplicate(jobs, session)

    # --- Step 3: Insert new jobs ---------------------------------------------
    inserted = 0
    insert_errors = 0

    # Use a SAVEPOINT (nested transaction) so a failure in this source
    # only rolls back its own rows, leaving previously processed sources intact.
    try:
        async with session.begin_nested():
            added_rows: list[JobTable] = []
            for job in dedup_result.new_jobs:
                try:
                    row: JobTable = job.to_job_table()
                    session.add(row)
                    added_rows.append(row)
                    inserted += 1
                except Exception:
                    insert_errors += 1
                    logger.exception(
                        "job_insert_failed",
                        source=source_name,
                        title=job.title,
                        company=job.company,
                    )

            # Flush so the rows get primary keys, then link canonical skills
            # (needs the ids). Both happen inside the savepoint, so a DB
            # constraint failure rolls back only this source.
            await session.flush()
            for row in added_rows:
                await link_skills(session, row, row.required_skills)
            # Populate semantic embeddings for the new rows before commit so
            # vector search works immediately (no NULL rows left behind).
            embedded = await _embed_rows(added_rows)
            await session.flush()
    except Exception:
        # Savepoint already rolled back this source's rows. Report 0 inserted.
        # The audit row is added to the OUTER transaction (the savepoint is
        # already gone), so the log survives even though the job rows did not.
        logger.exception("job_collection_flush_failed", source=source_name)
        await write_log(
            session,
            stage="job_ingest",
            status="failure",
            message=f"insert flush failed for source '{source_name}'",
            metadata={
                "source": source_name,
                "fetched": len(jobs),
                "inserted": 0,
                "duplicates": dedup_result.duplicate_count,
                "errors": insert_errors + 1,
            },
        )
        return CollectionResult(
            source=source_name,
            fetched=len(jobs),
            inserted=0,
            duplicates=dedup_result.duplicate_count,
            errors=insert_errors + 1,
        )

    logger.info(
        "job_collection_complete",
        source=source_name,
        fetched=len(jobs),
        inserted=inserted,
        duplicates=dedup_result.duplicate_count,
        errors=insert_errors,
    )

    await write_log(
        session,
        stage="job_ingest",
        status="success" if insert_errors == 0 else "failure",
        message=f"ingested {inserted} new job(s) from source '{source_name}'",
        metadata={
            "source": source_name,
            "fetched": len(jobs),
            "inserted": inserted,
            "duplicates": dedup_result.duplicate_count,
            "errors": insert_errors,
            "embedded": embedded,
            "embedding_model": EMBEDDING_MODEL,
            "embedding_dim": EMBEDDING_DIM,
        },
    )

    return CollectionResult(
        source=source_name,
        fetched=len(jobs),
        inserted=inserted,
        duplicates=dedup_result.duplicate_count,
        errors=insert_errors,
    )


async def collect_from_sources(
    source_names: list[str],
    session: AsyncSession,
) -> BatchCollectionResult:
    """Run the pipeline for multiple sources sequentially.

    Each source is processed independently — a failure in one
    source does not prevent the others from running.

    Args:
        source_names: List of registered source names (e.g. ["fixture", "wuzzuf"]).
        session: Active SQLModel session.

    Returns:
        BatchCollectionResult with per-source results.
    """
    results: list[CollectionResult] = []

    for name in source_names:
        try:
            source = get_source(name)
        except ValueError:
            logger.exception("job_collection_unknown_source", source=name)
            results.append(
                CollectionResult(
                    source=name,
                    fetched=0,
                    inserted=0,
                    duplicates=0,
                    errors=1,
                )
            )
            continue

        result = await collect_from_source(source, session)
        results.append(result)

    # Commit the batch. Individual sources used savepoints, so only successful ones
    # are committed. If the final commit fails, roll back everything and re-raise.
    try:
        await session.commit()
    except Exception:
        logger.exception("batch_collection_commit_failed", sources=source_names)
        await session.rollback()
        raise

    logger.info(
        "batch_collection_complete",
        sources=[r.source for r in results],
        total_inserted=sum(r.inserted for r in results),
        total_duplicates=sum(r.duplicates for r in results),
        total_errors=sum(r.errors for r in results),
    )

    return BatchCollectionResult(results=results)
