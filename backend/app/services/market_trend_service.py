"""
Market trend service — aggregate intelligence over the ``jobs`` table.

Each public function is a **single focused query** against the postings the
Wuzzuf pipeline collected, returning lightweight dataclasses. They are
read-only; the caller owns the session as elsewhere in the codebase.

Since the ingestion pipeline now captures Wuzzuf's structured fields directly
(``work_mode``, ``work_roles``, ``country_code``, ``job_types``, the salary
block) and canonicalizes skills into the ``skills`` / ``job_skills`` tables,
every metric here is a plain ``GROUP BY`` — no text heuristics, no length
filters, no keyword-bucketing.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional

import structlog
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LabeledCount:
    """A generic ``(label, count)`` aggregation bucket."""

    label: str
    count: int


@dataclass(frozen=True)
class PostingVolumePoint:
    """One point on the posting-volume-over-time series."""

    period: date
    count: int


@dataclass(frozen=True)
class SalaryStat:
    """Salary aggregates for one ``(currency, period)`` group.

    Grouped by currency *and* period because values across currencies/periods
    are not comparable (an EGP/month figure can't be averaged with a USD/hour
    one). Only postings with a visible salary are included.
    """

    currency: str
    period: Optional[str]
    count: int
    min: float
    max: float
    avg: float


# ---------------------------------------------------------------------------
# Metrics — one focused query each
# ---------------------------------------------------------------------------


async def top_companies(session: AsyncSession, *, limit: int = 10) -> list[LabeledCount]:
    """Companies posting the most jobs, busiest first."""
    sql = text(
        """
        SELECT company AS label, COUNT(*) AS count
        FROM jobs
        WHERE company != 'Confidential'
        GROUP BY company
        ORDER BY count DESC, label ASC
        LIMIT :limit
        """
    )
    rows = (await session.exec(sql, params={"limit": limit})).all()
    return [LabeledCount(label=r.label, count=r.count) for r in rows]


async def experience_level_distribution(session: AsyncSession) -> list[LabeledCount]:
    """How postings split across junior / mid / senior."""
    sql = text(
        """
        SELECT experience_level AS label, COUNT(*) AS count
        FROM jobs
        GROUP BY experience_level
        ORDER BY count DESC, label ASC
        """
    )
    rows = (await session.exec(sql)).all()
    return [LabeledCount(label=r.label, count=r.count) for r in rows]


async def work_type_distribution(session: AsyncSession) -> list[LabeledCount]:
    """Remote / hybrid / on-site split, straight from the ``work_mode`` column."""
    sql = text(
        """
        SELECT work_mode AS label, COUNT(*) AS count
        FROM jobs
        WHERE work_mode IS NOT NULL
        GROUP BY work_mode
        ORDER BY count DESC, label ASC
        """
    )
    rows = (await session.exec(sql)).all()
    return [LabeledCount(label=r.label, count=r.count) for r in rows]


async def top_categories(session: AsyncSession, *, limit: int = 10) -> list[LabeledCount]:
    """Top job categories, unnesting the multi-valued ``work_roles`` column."""
    sql = text(
        """
        SELECT role AS label, COUNT(*) AS count
        FROM jobs, LATERAL jsonb_array_elements_text(jobs.work_roles) AS role
        GROUP BY role
        ORDER BY count DESC, label ASC
        LIMIT :limit
        """
    )
    rows = (await session.exec(sql, params={"limit": limit})).all()
    return [LabeledCount(label=r.label, count=r.count) for r in rows]


async def country_distribution(session: AsyncSession) -> list[LabeledCount]:
    """Posting counts per country code (EG / SA / QA / AE)."""
    sql = text(
        """
        SELECT country_code AS label, COUNT(*) AS count
        FROM jobs
        WHERE country_code IS NOT NULL
        GROUP BY country_code
        ORDER BY count DESC, label ASC
        """
    )
    rows = (await session.exec(sql)).all()
    return [LabeledCount(label=r.label, count=r.count) for r in rows]


async def job_type_distribution(session: AsyncSession) -> list[LabeledCount]:
    """Employment-type split (full_time / part_time / ...), unnesting ``job_types``."""
    sql = text(
        """
        SELECT jt AS label, COUNT(*) AS count
        FROM jobs, LATERAL jsonb_array_elements_text(jobs.job_types) AS jt
        GROUP BY jt
        ORDER BY count DESC, label ASC
        """
    )
    rows = (await session.exec(sql)).all()
    return [LabeledCount(label=r.label, count=r.count) for r in rows]


async def posting_volume(session: AsyncSession) -> list[PostingVolumePoint]:
    """Posting volume over time, bucketed by month (oldest first).

    Postings without a ``posted_date`` are excluded — they carry no time signal.
    """
    sql = text(
        """
        SELECT date_trunc('month', posted_date)::date AS period, COUNT(*) AS count
        FROM jobs
        WHERE posted_date IS NOT NULL
        GROUP BY period
        ORDER BY period ASC
        """
    )
    rows = (await session.exec(sql)).all()
    return [PostingVolumePoint(period=r.period, count=r.count) for r in rows]


async def top_skills(session: AsyncSession, *, limit: int = 20) -> list[LabeledCount]:
    """Most in-demand canonical skills, joined from the normalized skills tables."""
    sql = text(
        """
        SELECT s.name AS label, COUNT(*) AS count
        FROM job_skills js
        JOIN skills s ON s.id = js.skill_id
        GROUP BY s.name
        ORDER BY count DESC, label ASC
        LIMIT :limit
        """
    )
    rows = (await session.exec(sql, params={"limit": limit})).all()
    return [LabeledCount(label=r.label, count=r.count) for r in rows]


async def salary_stats(session: AsyncSession) -> list[SalaryStat]:
    """Salary min/avg/max per currency+period, over visible salaries only."""
    sql = text(
        """
        SELECT
            salary_currency AS currency,
            salary_period   AS period,
            COUNT(*)        AS count,
            MIN(COALESCE(salary_min, salary_max)) AS min,
            MAX(COALESCE(salary_max, salary_min)) AS max,
            ROUND(AVG((COALESCE(salary_min, salary_max)
                       + COALESCE(salary_max, salary_min)) / 2.0), 2) AS avg
        FROM jobs
        WHERE salary_hidden = false
          AND salary_currency IS NOT NULL
          AND (salary_min IS NOT NULL OR salary_max IS NOT NULL)
        GROUP BY salary_currency, salary_period
        ORDER BY count DESC, currency ASC
        """
    )
    rows = (await session.exec(sql)).all()
    return [
        SalaryStat(
            currency=r.currency,
            period=r.period,
            count=r.count,
            min=float(r.min),
            max=float(r.max),
            avg=float(r.avg),
        )
        for r in rows
    ]
