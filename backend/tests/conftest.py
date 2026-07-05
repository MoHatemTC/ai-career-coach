"""
Shared pytest fixtures for the Career Coach test suite.

Requires PostgreSQL to be running (docker compose up -d).
Uses a separate test database to avoid polluting development data.

Set TEST_DATABASE_URL environment variable to override the default
connection string.
"""

import asyncio
import sys

import psycopg
import pytest
import pytest_asyncio
from sqlalchemy import text

# psycopg3's async driver cannot run on Windows' default ProactorEventLoop.
# Select the selector loop policy before any event loop is created so the
# async fixtures/tests use a compatible loop.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.ext.asyncio.session import AsyncSession
from app.core.config import get_test_settings
from fastapi.testclient import TestClient
from app.main import app
settings = get_test_settings()

TEST_DATABASE_URL = settings.DATABASE_URL


def _ensure_test_database_exists() -> None:
    """
    Create the test database if it doesn't exist yet.

    CREATE DATABASE can't run inside a transaction, so this connects to the
    server's default "postgres" maintenance database with autocommit rather
    than going through SQLAlchemy.
    """
    conn = psycopg.connect(
        host=settings.TEST_POSTGRES_HOST,
        port=settings.TEST_POSTGRES_PORT,
        user=settings.TEST_POSTGRES_USER,
        password=settings.TEST_POSTGRES_PASSWORD.get_secret_value(),
        dbname="postgres",
        autocommit=True,
    )
    try:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (settings.TEST_POSTGRES_DB,),
        ).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{settings.TEST_POSTGRES_DB}"')
    finally:
        conn.close()


_ensure_test_database_exists()


@pytest.fixture(scope="function")
def session():
    """
    Provide a clean PostgreSQL **sync** Session for each test.

    Used by the model / dataset tests that exercise the ORM and schema
    directly (no async service code involved).

    Lifecycle per test:
      1. Create engine pointed at the test database
      2. Enable pgvector extension
      3. Create all SQLModel tables
      4. Yield the session to the test
      5. Drop all tables after the test completes

    Each test therefore starts with a completely empty database.
    """
    engine = create_engine(TEST_DATABASE_URL)

    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        yield s

    SQLModel.metadata.drop_all(engine)


@pytest_asyncio.fixture(scope="function")
async def async_session():
    """
    Provide a clean PostgreSQL **async** AsyncSession for each test.

    Mirrors the ``session`` fixture but for the async pipeline: the
    collection / deduplication services and the Wuzzuf ``fetch()`` are all
    async, so their tests need an AsyncSession over the psycopg3 async driver.

    ``expire_on_commit`` is disabled so rows stay usable after commit without a
    blocking lazy reload — matching the app's request-scoped session.
    """
    engine = create_async_engine(TEST_DATABASE_URL)

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(SQLModel.metadata.create_all)

    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()


from httpx import AsyncClient, ASGITransport
from app.db.connection import get_session

@pytest_asyncio.fixture(scope="function")
async def async_client(async_session: AsyncSession):
    """
    Provide an AsyncClient for FastAPI endpoint testing.
    Overrides the get_session dependency to use the isolated test database session.
    """
    async def override_get_session():
        yield async_session
        
    app.dependency_overrides[get_session] = override_get_session
    
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
        
    app.dependency_overrides.clear()
