"""
Pure Wuzzuf JSON → :class:`JobPosting` mapping.

Every function here is side-effect-free and unit-testable against a saved
detail payload (see ``tests/fixtures/wuzzuf/``). The HTTP/orchestration layer
lives in :mod:`app.services.job_sources.wuzzuf`; this module never does I/O.

A Wuzzuf detail record has two relevant parts:
  * ``job_item``         — one element of ``/api/job``'s ``data`` list.
  * ``job_item["attributes"]`` (``attrs``) — the rich field bag.

Storage is **English-first**: where Wuzzuf provides a translation
(``userContentTranslations``) we prefer the English text and fall back to the
raw field.
"""

import re
from datetime import datetime, timezone
from typing import NamedTuple, Optional

import structlog

from app.models import JobPosting
from app.services.skills.canonicalizer import canonicalize_keywords

logger = structlog.get_logger()

SOURCE_NAME = "wuzzuf"


# ---------------------------------------------------------------------------
# Grouped return types
# ---------------------------------------------------------------------------

class Geo(NamedTuple):
    country_code: Optional[str]
    country_name: Optional[str]
    city: Optional[str]
    area: Optional[str]


class Salary(NamedTuple):
    min: Optional[float]
    max: Optional[float]
    currency: Optional[str]   # ISO-ish code: EGP / USD / SAR / QAR / AED
    period: Optional[str]     # "Per Month" / "Per Hour"
    hidden: bool
    details: Optional[str]


# ---------------------------------------------------------------------------
# Small text helpers
# ---------------------------------------------------------------------------

def strip_html(html: Optional[str]) -> str:
    """Remove HTML tags and decode the common entities Wuzzuf emits."""
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    return re.sub(r"\s+", " ", text).strip()


def parse_datetime(raw: Optional[str]) -> Optional[datetime]:
    """Parse Wuzzuf's ``MM/DD/YYYY HH:MM:SS`` timestamp to a UTC datetime.

    Wuzzuf does not declare a timezone; we treat the value as UTC for
    consistency with the rest of the schema. Returns ``None`` when missing
    or unparseable.
    """
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%m/%d/%Y %H:%M:%S").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _translation(attrs: dict, field: str) -> tuple[Optional[str], Optional[str]]:
    """Return ``(english_text, lang_detected)`` for a translated field, if any."""
    node = (attrs.get("userContentTranslations") or {}).get(field)
    if isinstance(node, dict):
        return node.get("en"), node.get("lang_detected")
    return None, None


# ---------------------------------------------------------------------------
# Field extractors (one concern each)
# ---------------------------------------------------------------------------

def extract_external_id(job_item: dict) -> Optional[str]:
    """The stable per-posting Wuzzuf UUID."""
    job_id = job_item.get("id")
    return str(job_id) if job_id else None


def extract_geo(attrs: dict) -> Geo:
    """Split the nested ``location`` object into country/city/area parts."""
    loc = attrs.get("location") or {}
    country = loc.get("country") or {}
    city = loc.get("city") or {}
    area = loc.get("area") or {}
    return Geo(
        country_code=country.get("code"),
        country_name=country.get("name"),
        city=city.get("name") if isinstance(city, dict) else None,
        area=area.get("name") if isinstance(area, dict) else None,
    )


_WORK_MODE_MAP = {
    "on_site": "on_site",
    "onsite": "on_site",
    "remote": "remote",
    "work_from_home": "remote",
    "hybrid": "hybrid",
}


def extract_workplace(attrs: dict) -> Optional[str]:
    """Work arrangement as the canonical token: ``on_site`` / ``remote`` / ``hybrid``."""
    wa = attrs.get("workplaceArrangement") or {}
    
    raw = (wa.get("translations", {}).get("displayed_name", {}) or {}).get("en")
    if not raw:
        raw = wa.get("displayedName")
        
    if not raw:
        return None
        
    normalized = raw.lower().strip().replace("-", "_").replace(" ", "_")
    mapped = _WORK_MODE_MAP.get(normalized)
    
    if mapped is None:
        logger.warning("wuzzuf_unmapped_work_mode", raw=raw)
        
    return mapped


def extract_job_types(attrs: dict) -> list[str]:
    """Employment types (multi-valued): ``full_time``, ``part_time``, ..."""
    types: list[str] = []
    for wt in attrs.get("workTypes") or []:
        name = (wt.get("translations", {}).get("displayed_name", {}) or {}).get("en")
        if name:
            types.append(name)
    return types


def extract_work_roles(attrs: dict) -> list[str]:
    """Job categories (multi-valued), e.g. ``IT/Software Development``."""
    return [
        wr["name"]
        for wr in attrs.get("workRoles") or []
        if isinstance(wr, dict) and wr.get("name")
    ]


def extract_career_raw(attrs: dict) -> Optional[str]:
    """Wuzzuf's raw career level: ``Entry Level`` / ``Experienced`` / ``Manager`` / ..."""
    return (attrs.get("careerLevel") or {}).get("name")


def extract_years(attrs: dict) -> tuple[Optional[int], Optional[int]]:
    """Required years of experience as ``(min, max)`` — either may be ``None``."""
    years = attrs.get("workExperienceYears") or {}
    return years.get("min"), years.get("max")


def extract_salary(attrs: dict) -> Salary:
    """Salary band, currency, and period — never inferred from country."""
    sal = attrs.get("salary") or {}
    currency = sal.get("currency")
    period = sal.get("period")
    return Salary(
        min=sal.get("min"),
        max=sal.get("max"),
        currency=currency.get("code") if isinstance(currency, dict) else currency,
        period=period.get("name") if isinstance(period, dict) else period,
        hidden=bool(attrs.get("hideSalary")),
        details=(sal.get("additionalDetails") or "").strip() or None,
    )


def map_experience_level(career_raw: Optional[str], years_min: Optional[int]) -> Optional[str]:
    """Map Wuzzuf career signals onto ``junior`` | ``mid`` | ``senior``.

    ``Senior Management`` (CTO/VP/Director/CEO) is **not** an ICT IC role and
    returns ``None`` so the caller drops the record. ``Manager`` maps to
    ``senior``; otherwise the required years refine seniority.
    """
    name = (career_raw or "").lower().strip()
    if name == "senior management":
        return None  # caller discards
    if name == "manager":
        return "senior"
    if name in ("student", "entry level"):
        return "junior"

    # "Experienced" or unknown — use the years required.
    if years_min is None:
        return "mid"
    if years_min >= 6:
        return "senior"
    if years_min >= 3:
        return "mid"
    return "junior"


def build_description(attrs: dict) -> str:
    """English-first description + requirements, HTML stripped and joined."""
    desc_en, _ = _translation(attrs, "description")
    req_en, _ = _translation(attrs, "requirements")
    description = strip_html(desc_en or attrs.get("description"))
    requirements = strip_html(req_en or attrs.get("requirements"))
    if requirements:
        return f"{description}\n\nRequirements:\n{requirements}".strip()
    return description


def build_url(attrs: dict, job_item: dict) -> str:
    """Public job URL from the human-readable ``uri`` slug."""
    uri = (attrs.get("uri") or f"jobs/p/{job_item.get('id')}").strip()
    return f"https://wuzzuf.net/{uri}"


def display_location(geo: Geo) -> str:
    """Human-readable ``City, Country`` for the display-only ``location`` column."""
    if geo.city and geo.country_name:
        return f"{geo.city}, {geo.country_name}"
    return geo.city or geo.country_name or "Cairo"


def _raw_keyword_names(attrs: dict) -> list[str]:
    """Original keyword names, pre-canonicalization, for provenance."""
    return [
        k["name"]
        for k in attrs.get("keywords") or []
        if isinstance(k, dict) and k.get("name")
    ]


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def parse_job(job_item: dict, company_name: str) -> Optional[JobPosting]:
    """Map one Wuzzuf detail record + resolved company name to a JobPosting.

    Returns ``None`` for records we deliberately drop (Senior-Management roles)
    or that fail validation — the caller skips them.
    """
    attrs = job_item.get("attributes", {})

    years_min, years_max = extract_years(attrs)
    experience_level = map_experience_level(extract_career_raw(attrs), years_min)
    if experience_level is None:
        return None  # Senior-Management — outside the ICT IC model

    geo = extract_geo(attrs)
    salary = extract_salary(attrs)
    title_en, language = _translation(attrs, "title")
    posted_at = parse_datetime(attrs.get("postedAt"))

    try:
        return JobPosting(
            title=(title_en or attrs.get("title") or "").strip(),
            company=company_name,
            location=display_location(geo),
            description=build_description(attrs),
            required_skills=canonicalize_keywords(attrs.get("keywords")),
            experience_level=experience_level,
            source=SOURCE_NAME,
            external_id=extract_external_id(job_item),
            country_code=geo.country_code,
            city=geo.city,
            area=geo.area,
            work_mode=extract_workplace(attrs),
            job_types=extract_job_types(attrs),
            work_roles=extract_work_roles(attrs),
            career_level_raw=extract_career_raw(attrs),
            exp_years_min=years_min,
            exp_years_max=years_max,
            language=language,
            salary_min=salary.min,
            salary_max=salary.max,
            salary_currency=salary.currency,
            salary_period=salary.period,
            salary_hidden=salary.hidden,
            salary_details=salary.details,
            keywords_raw=_raw_keyword_names(attrs),
            posted_date=posted_at.date() if posted_at else None,
            posted_at=posted_at,
            expires_at=parse_datetime(attrs.get("expireAt")),
            url=build_url(attrs, job_item),
            raw_payload=attrs,
        )
    except Exception:
        logger.warning(
            "wuzzuf_parse_failed",
            source=SOURCE_NAME,
            external_id=job_item.get("id"),
            exc_info=True,
        )
        return None
