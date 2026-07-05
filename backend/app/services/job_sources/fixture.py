import json

import structlog
from pydantic import ValidationError

from app.models import JobPosting
from app.services.job_sources.base import BaseJobSource
from app.core.config import get_settings

logger = structlog.get_logger()

FIXTURE_JOBS_PATH = get_settings().FIXTURE_JOBS_PATH


class FixtureSource(BaseJobSource):

    source_name = "fixture"

    async def fetch(self) -> list[JobPosting]:
        # Reads a small local JSON file — fast enough to do inline without
        # blocking the event loop meaningfully. No network I/O involved.
        if not FIXTURE_JOBS_PATH.exists():
            raise FileNotFoundError("Fixture jobs file not found")

        with FIXTURE_JOBS_PATH.open("r", encoding="utf-8") as f:
            raw_jobs = json.load(f)

        jobs: list[JobPosting] = []
        skipped = 0
        for index, raw in enumerate(raw_jobs):
            job = self._normalize(raw, index=index)
            if job is None:
                skipped += 1
                continue
            jobs.append(job)

        # Surface how much fixture data was dropped during validation so bad
        # records don't disappear silently — the per-record reason is logged
        # in _normalize, this is the run-level summary.
        if skipped:
            logger.warning(
                "fixture_jobs_skipped",
                source=self.source_name,
                skipped=skipped,
                total=len(raw_jobs),
            )

        logger.info(
            "fixture_jobs_normalized",
            source=self.source_name,
            normalized=len(jobs),
            skipped=skipped,
            total=len(raw_jobs),
        )
        return jobs

    def _normalize(self, raw: dict, index: int) -> JobPosting | None:
        try:
            return JobPosting.model_validate(raw)
        except ValidationError as e:
            # Don't drop invalid records silently: log which record failed and
            # exactly why, so bad fixture data is debuggable. Returning None
            # keeps the source resilient (one bad row doesn't kill the batch).
            logger.warning(
                "fixture_job_validation_failed",
                source=self.source_name,
                index=index,
                title=raw.get("title") if isinstance(raw, dict) else None,
                company=raw.get("company") if isinstance(raw, dict) else None,
                errors=e.errors(include_url=False, include_input=False),
            )
            return None
