"""
Responsibilities:
  1. Provide an async SQLAlchemy engine and AsyncSession factory for PostgreSQL.
  2. Schema is owned by Alembic migrations (run ``alembic upgrade head``);
     the app does not create tables at startup.

The engine uses the psycopg3 driver in async mode — the same
``postgresql+psycopg`` URL works for both sync and async, so no extra driver
(asyncpg) is required.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.DATABASE_URL, echo=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides an async database session per request.

    Yields an AsyncSession inside a context manager so the connection is
    always closed — even if the route raises an exception. ``expire_on_commit``
    is disabled so ORM objects stay usable after commit without triggering a
    lazy (and therefore blocking) reload.

    Usage (FastAPI route):
        @router.get("/jobs")
        async def list_jobs(session: AsyncSession = Depends(get_session)):
            return (await session.exec(select(JobTable))).all()
    """
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
