"""
scripts/backfill_embeddings.py
==============================
One-time backfill of ``jobs.embedding`` for rows left NULL by the scraper (which
historically never generated embeddings).

Streams jobs where ``embedding IS NULL`` ordered by id, embeds each chunk with the
canonical :func:`app.core.embeddings.build_job_text` + model, and commits per
chunk so it never holds a long lock and can run while the scraper is live.
Idempotent — re-running only fills whatever remains NULL.

Run (Windows-friendly event loop):
    uv run python -m scripts.backfill_embeddings
"""

from __future__ import annotations

import asyncio
import sys

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.embeddings import EMBEDDING_MODEL, build_job_text, embed
from app.db.connection import get_session
from app.models.jobs import JobTable

CHUNK_SIZE = 128


async def _next_chunk(session: AsyncSession, after_id: int) -> list[JobTable]:
    stmt = (
        select(JobTable)
        .where(JobTable.embedding.is_(None))
        .where(JobTable.id > after_id)
        .order_by(JobTable.id)
        .limit(CHUNK_SIZE)
    )
    return list((await session.exec(stmt)).all())


async def backfill() -> int:
    total = 0
    async for session in get_session():  # type: ignore[assignment]
        after_id = 0
        while True:
            rows = await _next_chunk(session, after_id)
            if not rows:
                break
            texts = [build_job_text(row) for row in rows]
            vectors = await asyncio.to_thread(embed, texts)
            for row, vector in zip(rows, vectors):
                row.embedding = vector
            await session.commit()
            total += len(rows)
            after_id = rows[-1].id
            print(f"embedded {total} jobs (last id={after_id})", flush=True)
        break
    print(f"done — {total} job(s) embedded with {EMBEDDING_MODEL}", flush=True)
    return total


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(backfill())
