"""
Destructive DB reset — drops the entire schema and rebuilds it from Alembic.

Usage:
    uv run python -m scripts.reset_db

WARNING: This permanently deletes ALL data and objects in the public schema.
There is no undo. Intended for development only.

Unlike a plain create_all, this rebuilds through the migration history
(`alembic upgrade head`), so the database — including the pgvector extension
and the alembic_version stamp — ends up identical to a fresh `make setup`.
"""

import asyncio
import sys
from pathlib import Path

import structlog
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.db.connection import engine

logger = structlog.get_logger()

# alembic.ini lives at the project root, one level above this scripts/ dir.
ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


async def _drop_schema() -> None:
    """Drop every object by recreating the public schema from scratch."""
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
    await engine.dispose()


def reset_db() -> None:
    """Drop the schema, then rebuild it by running all migrations."""
    logger.info("db_reset_started")

    asyncio.run(_drop_schema())

    # Run migrations to re-enable the vector extension, recreate all tables, and write the alembic stamp.
    command.upgrade(Config(str(ALEMBIC_INI)), "head")

    logger.info("db_reset_complete")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    reset_db()
