"""
Wuzzuf job source — the HTTP/orchestration layer.

Implements :class:`BaseJobSource` for Wuzzuf via its three internal APIs:

  1. POST /api/search/job                    → job IDs per category
  2. GET  /api/job?filter[other][ids]=...    → full job details
  3. GET  /api/company?filter[id]=...        → company names

All HTTP is async (httpx + asyncio.gather). ``fetch()`` is the single public
entry point used by the collection pipeline.

Pure JSON → :class:`JobPosting` mapping lives in
:mod:`app.services.job_sources.wuzzuf_parsing`; this module keeps only the I/O,
the search/category orchestration, and company-name resolution.
"""

import asyncio
import json
from datetime import date
from typing import Callable, Optional

import httpx
import structlog

from app.models import JobPosting
from app.services.job_sources.base import BaseJobSource
from app.services.job_sources import wuzzuf_parsing

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEARCH_URL = "https://wuzzuf.net/api/search/job"
JOBS_URL = "https://wuzzuf.net/api/job"
COMPANY_URL = "https://wuzzuf.net/api/company"

DEFAULT_CATEGORIES: list[str] = [
    "Software Engineer",
    "Backend Developer",
    "Frontend Developer",
    "Full Stack Developer",
    "Data Analyst",
    "Data Scientist",
    "Machine Learning Engineer",
    "AI Engineer",
    "DevOps Engineer",
    "Data Engineer",
    "Product Manager",
    "Business Analyst",
    "QA Engineer",
    "Mobile Developer",
    "Cybersecurity",
]

# Scope: collect ICT jobs across these MENA countries only. Passed to the search
# API's ``searchFilters.country`` (a list), so one query covers all of them.
MENA_COUNTRIES: list[str] = [
    "Egypt",
    "Saudi Arabia",
    "Qatar",
    "United Arab Emirates",
]

# max simultaneous open connections — be polite to Wuzzuf
_CONCURRENCY = 5
_BATCH_SIZE = 50    # IDs per /api/job and /api/company request
_PAGE_SIZE = 200    # results per search page
_TIMEOUT = 15.0     # seconds

# Max pages per category (None fetches all). A "page" is one search request returning up to _PAGE_SIZE jobs.
MAX_PAGES_PER_CATEGORY: Optional[int] = 1

_HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


# ---------------------------------------------------------------------------
# Pure helper — company relationship lookup (kept here; tied to the join below)
# ---------------------------------------------------------------------------

def _company_id_of(job_item: dict) -> str:
    """Return the related company id for a job item, or ``""`` when absent."""
    data = (
        job_item.get("relationships", {})
        .get("company", {})
        .get("data")
    )
    if not data:
        return ""
    return str(data.get("id", ""))


# ---------------------------------------------------------------------------
# WuzzufSource
# ---------------------------------------------------------------------------

class WuzzufSource(BaseJobSource):
    """Fetch and normalize MENA tech jobs from Wuzzuf's internal APIs."""

    source_name = "wuzzuf"

    def __init__(
        self,
        categories: Optional[list[str]] = None,
        concurrency: int = _CONCURRENCY,
        batch_size: int = _BATCH_SIZE,
        page_size: int = _PAGE_SIZE,
        timeout: float = _TIMEOUT,
        max_pages: Optional[int] = MAX_PAGES_PER_CATEGORY,
    ) -> None:
        # Default mutable arg guarded against accidental sharing/mutation.
        self.categories = list(categories) if categories else list(DEFAULT_CATEGORIES)
        self.concurrency = concurrency
        self.batch_size = batch_size
        self.page_size = page_size
        self.timeout = timeout
        # ``None`` → page until each category is exhausted (historical behavior);
        # int → stop after this many pages per category.
        self.max_pages = max_pages

    # -- Public entry point (required by BaseJobSource) ----------------------

    async def fetch(self) -> list[JobPosting]:
        """Run search → job details → company details → normalize, concurrently.

        This is the full async pipeline and is awaited directly by the
        collection service (and FastAPI routes). A synchronous caller (CLI,
        script) can wrap it with ``asyncio.run(source.fetch())``.
        """
        return await self._fetch_async()

    def _normalize(self, job_item: dict, company_item: Optional[dict]) -> JobPosting | None:
        """Resolve the company name, then delegate to the pure parser.

        ``job_item`` is one item from ``/api/job``; ``company_item`` is the
        matched item from ``/api/company`` (or ``None``). Returns ``None`` for
        records the parser drops (Senior-Management) or that fail validation.
        """
        company = self._resolve_company(job_item.get("attributes", {}), company_item)
        return wuzzuf_parsing.parse_job(job_item, company_name=company)

    @staticmethod
    def _resolve_company(attrs: dict, company_item: Optional[dict]) -> str:
        """Resolve the display company name, honoring Wuzzuf's confidential flag."""
        if attrs.get("hideCompany"):
            return "Confidential"
        if company_item:
            name = (company_item.get("attributes", {}).get("name") or "").strip()
            return name or "Confidential"
        return "Confidential"

    # -- Async pipeline ------------------------------------------------------

    def _build_client(self) -> httpx.AsyncClient:
        """Create the HTTP client. Isolated so tests can inject a transport."""
        return httpx.AsyncClient(headers=_HEADERS, timeout=self.timeout)

    async def _fetch_async(self) -> list[JobPosting]:
        """Run search → job details → company details → normalize, concurrently."""
        sem = asyncio.Semaphore(self.concurrency)

        async with self._build_client() as client:
            all_ids = await self._search_all_categories(client, sem)
            logger.info("wuzzuf_unique_ids", source=self.source_name, count=len(all_ids))

            job_details = await self._fetch_batches(
                client,
                sem,
                ids=list(all_ids),
                url_fn=lambda batch: f"{JOBS_URL}?filter[other][ids]=" + ",".join(batch),
            )
            logger.info(
                "wuzzuf_job_detail_done", source=self.source_name, count=len(job_details)
            )

            company_ids = self._collect_company_ids(job_details)
            company_details = await self._fetch_batches(
                client,
                sem,
                ids=company_ids,
                url_fn=lambda batch: f"{COMPANY_URL}?filter[id]=" + ",".join(batch),
            )
            logger.info(
                "wuzzuf_company_detail_done",
                source=self.source_name,
                count=len(company_details),
            )

        postings = self._normalize_all(job_details, company_details)
        postings.sort(key=lambda p: p.posted_date or date.min, reverse=True)  # newest first

        logger.info("wuzzuf_fetch_complete", source=self.source_name, total=len(postings))
        return postings

    async def _search_all_categories(
        self, client: httpx.AsyncClient, sem: asyncio.Semaphore
    ) -> set[str]:
        """Search every category concurrently and union the returned job IDs."""
        logger.info(
            "wuzzuf_search_start", source=self.source_name, categories=len(self.categories)
        )
        results = await asyncio.gather(
            *(self._search_category(client, sem, cat) for cat in self.categories),
            return_exceptions=True,
        )

        all_ids: set[str] = set()
        for result in results:
            if isinstance(result, BaseException):
                logger.warning(
                    "wuzzuf_search_category_failed",
                    source=self.source_name,
                    error=str(result),
                )
                continue
            all_ids.update(result)
        return all_ids

    @staticmethod
    def _collect_company_ids(job_details: dict[str, dict]) -> list[str]:
        """Return the unique set of related company IDs across all job items."""
        ids = {_company_id_of(item) for item in job_details.values()}
        ids.discard("")
        return list(ids)

    def _normalize_all(
        self, job_details: dict[str, dict], company_details: dict[str, dict]
    ) -> list[JobPosting]:
        """Normalize every job item, joining it to its company and dropping Nones."""
        postings: list[JobPosting] = []
        for job_item in job_details.values():
            company_id = _company_id_of(job_item)
            posting = self._normalize(job_item, company_details.get(company_id))
            if posting is not None:
                postings.append(posting)
        return postings

    async def _search_category(
        self,
        client: httpx.AsyncClient,
        sem: asyncio.Semaphore,
        query: str,
    ) -> list[str]:
        """Page through one search query and return all job IDs it yields.

        Stops at ``self.max_pages`` pages when set, so a single high-volume
        category can't keep the loop running indefinitely.
        """
        ids: list[str] = []
        start = 0
        pages_fetched = 0

        while True:
            async with sem:
                try:
                    resp = await client.post(
                        SEARCH_URL,
                        headers={"Content-Type": "application/json;charset=UTF-8"},
                        content=json.dumps(
                            {
                                "startIndex": start,
                                "pageSize": self.page_size,
                                "longitude": "0",
                                "latitude": "0",
                                "query": query,
                                # Scope to MENA — one query covers all four countries.
                                "searchFilters": {"country": MENA_COUNTRIES},
                            }
                        ),
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as exc:
                    logger.warning(
                        "wuzzuf_search_failed",
                        source=self.source_name,
                        query=query,
                        start=start,
                        error=str(exc),
                    )
                    break

            batch = [job["id"] for job in data.get("data", [])]
            ids.extend(batch)
            pages_fetched += 1

            total = data.get("meta", {}).get("totalResultsCount", 0)
            if len(batch) < self.page_size or len(ids) >= total:
                break
            if self.max_pages is not None and pages_fetched >= self.max_pages:
                logger.info(
                    "wuzzuf_max_pages_reached",
                    source=self.source_name,
                    query=query,
                    pages=pages_fetched,
                    collected=len(ids),
                )
                break
            start += self.page_size

        return ids

    async def _fetch_batches(
        self,
        client: httpx.AsyncClient,
        sem: asyncio.Semaphore,
        ids: list[str],
        url_fn: Callable[[list[str]], str],
    ) -> dict[str, dict]:
        """Fetch ``ids`` in batches of ``batch_size`` and return an ``{id: item}`` map.

        All batch requests fire concurrently, bounded by the semaphore. A failed
        batch is logged and contributes nothing rather than aborting the run.
        """
        batches = [
            ids[i : i + self.batch_size]
            for i in range(0, len(ids), self.batch_size)
        ]

        async def _fetch_batch(batch: list[str]) -> list[dict]:
            async with sem:
                try:
                    resp = await client.get(url_fn(batch))
                    resp.raise_for_status()
                    return resp.json().get("data", [])
                except Exception as exc:
                    logger.warning(
                        "wuzzuf_batch_failed", source=self.source_name, error=str(exc)
                    )
                    return []

        results = await asyncio.gather(*(_fetch_batch(b) for b in batches))

        lookup: dict[str, dict] = {}
        for batch_result in results:
            for item in batch_result:
                lookup[str(item["id"])] = item
        return lookup
