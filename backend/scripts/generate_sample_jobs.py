"""
Regenerate ``data/sample_jobs.json`` from live Wuzzuf data.

Runs the real :class:`WuzzufSource` over a small set of ICT categories, so every
record is already processed into the :class:`JobPosting` shape — structured
fields, split location, canonical lowercase skills, salary block — and is ready
to be ``JobPosting.model_validate``-d and inserted by the fixture source.

``raw_payload`` is dropped from the dump: it is bulky provenance only useful on
live rows, not in a checked-in demo fixture.

Usage:
    uv run python -m scripts.generate_sample_jobs [--limit N]
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

import structlog

from app.core.config import get_settings
from app.services.job_sources.wuzzuf import WuzzufSource

logger = structlog.get_logger()

# A focused ICT slice — enough variety (countries, work modes, currencies)
# without scraping the whole board.
SAMPLE_CATEGORIES = [
    "Software Engineer",
    "Backend Developer",
    "Frontend Developer",
    "Data Analyst",
    "Data Scientist",
    "DevOps Engineer",
]


async def _collect(limit: int) -> list[dict]:
    """Fetch a sample and return JobPosting dicts ready for the fixture file."""
    source = WuzzufSource(
        categories=SAMPLE_CATEGORIES,
        max_pages=1,        # one search page per category keeps the sample small
        page_size=50,
    )
    postings = await source.fetch()
    postings = postings[:limit]
    # mode="json" makes dates/datetimes/Decimals JSON-native; drop raw_payload.
    return [p.model_dump(mode="json", exclude={"raw_payload"}) for p in postings]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=150, help="Max jobs to keep.")
    args = parser.parse_args()

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    logger.info("sample_generation_started", categories=len(SAMPLE_CATEGORIES))
    records = asyncio.run(_collect(args.limit))

    out_path: Path = get_settings().FIXTURE_JOBS_PATH
    out_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("sample_generation_complete", count=len(records), path=str(out_path))


if __name__ == "__main__":
    main()
