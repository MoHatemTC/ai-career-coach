"""
Career Coach API — application entrypoint.

Uvicorn target:  app.main:app
"""

import asyncio
import sys

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from app.core.config import get_settings
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router

settings = get_settings()

logger = structlog.get_logger()


# -- Lifespan -----------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown lifecycle hook.

    Schema is managed by Alembic migrations (``alembic upgrade head``),
    not created at startup — so there is no DB setup here.
    """
    logger.info("app_startup")
    yield
    logger.info("app_shutdown")


app = FastAPI(
    title="Career Coach API",
    description="AI-powered career coaching and job matching platform.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# -- Middleware ---------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -- Routers ------------------------------------------------------------------
app.include_router(api_router, prefix="/api/v1")


# -- Root health check --------------------------------------------------------
@app.get("/", tags=["Root"])
def root() -> dict[str, str]:
    """Root endpoint — confirms the API is running."""
    return {"message": "Career Coach API is running"}


# -- Local dev entrypoint ------------------------------------------------------
# `uvicorn app.main:app` resolves its event loop via `--loop` (default "auto")
# *before* this module is imported, so setting an event loop policy here has no
# effect — psycopg3 still gets handed a ProactorEventLoop on Windows. The only
# place a custom loop can be injected is the `loop=` argument to uvicorn.run(),
# which is only reachable when uvicorn is started programmatically. Run with
# `uv run python -m app.main` locally on Windows; production keeps using the
# `uvicorn app.main:app` CLI and is unaffected.
def _win_loop_factory() -> asyncio.AbstractEventLoop:
    return asyncio.SelectorEventLoop()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        loop=_win_loop_factory if sys.platform == "win32" else "auto",
    )