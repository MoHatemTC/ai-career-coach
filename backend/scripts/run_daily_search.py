"""
Daily automated job search + notification run.

Invoked by an external scheduler — this script owns no scheduling
logic itself, only the run.

Usage:
    python -m scripts.run_daily_search
    python -m scripts.run_daily_search --sources fixture wuzzuf
    python -m scripts.run_daily_search --user-id 12 --user-id 47
    python -m scripts.run_daily_search --dry-run
"""
import argparse
import asyncio
import structlog

from app.db.connection import engine
from sqlmodel.ext.asyncio.session import AsyncSession
from app.services.search_orchestration_service import run_search

logger = structlog.get_logger()

async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Daily automated job search and notification run.")
    parser.add_argument("--sources", nargs="+", default=None, help="Specific sources to run")
    parser.add_argument("--user-id", type=int, action="append", default=None, help="Specific user IDs to run for")
    parser.add_argument("--dry-run", action="store_true", help="Run without sending notifications")
    
    args = parser.parse_args(argv)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        result = await run_search(
            session,
            source_names=args.sources,
            user_ids=args.user_id,
            notify=not args.dry_run
        )

        logger.info(
            "daily_search_run_complete",
            run_id=result.run_id,
            jobs_fetched=result.jobs_fetched,
            jobs_inserted=result.jobs_inserted,
            notifications_sent=result.notifications_sent,
            errors_count=len(result.errors)
        )

        if result.errors:
            for error in result.errors:
                logger.error("daily_search_run_error", error=error)
            return 1

        return 0

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
