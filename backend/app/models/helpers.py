"""
Shared helpers and constants used across the models package — kept separate
from any single domain file so neither `jobs.py` nor `job_tracking.py` has to
reach into the other just to get a timestamp factory.
"""

from datetime import datetime, timezone

# Allowed values for the structured enum-like columns sourced from Wuzzuf.
WORK_MODES = ("on_site", "remote", "hybrid")

# Sentinel that every job source normalizes a hidden/missing company to.
# When the company is hidden it carries no identifying signal, so the hash
# must not rely on it (see JobPosting.compute_content_hash).
HIDDEN_COMPANY = "confidential"


def _utcnow() -> datetime:
    """Current UTC time as a timezone-aware datetime object.
    SQLModel maps this to PostgreSQL TIMESTAMPTZ automatically."""
    return datetime.now(timezone.utc)


def _normalize_text(value: str) -> str:
    """Lowercase, strip, and collapse internal whitespace for stable hashing."""
    return " ".join(value.split()).lower()
