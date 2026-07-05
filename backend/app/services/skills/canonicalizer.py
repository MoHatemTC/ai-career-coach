"""
Turn raw Wuzzuf keyword data into canonical lowercase skill tokens.

Wuzzuf's ``keywords[]`` array is dirty and bilingual — the same field holds
several shapes:

  1. Curated tags with an English translation  ``{"name": "Data Analysis",
     "userContentTranslations": {"name": {"en": "Data Analysis", ...}}}``
  2. Clean free tokens, already lowercase, no translation  ``{"name": "capcut"}``
  3. **Comma/paren-joined lists** crammed into one tag, e.g.
     ``"Selenium, Cypress, Playwright"`` or ``"cloud computing (aws, azure, gcp)"``
  4. Full Arabic requirement *sentences*, no translation.

``canonicalize_keywords`` splits shape 3 into individual skills, canonicalizes
each to a lowercase token (shapes 1–2), drops Arabic sentences (shape 4) and
contentless generic terms. Everything here is pure and unit-testable — no I/O.
"""

import re
import unicodedata
from typing import Optional

from app.services.skills import aliases

# A keyword longer than this — by characters or by word count — is a requirement
# sentence, not a skill, and is dropped. Tuned to clear real skill names
# ("natural language processing", "google tag manager").
MAX_SKILL_CHARS = 60
MAX_SKILL_WORDS = 6

_ARABIC_RANGE = ("؀", "ۿ")  # Arabic Unicode block (letters + punctuation)

# Splits a single keyword tag into candidate skills. Users often pack several
# tools into one tag separated by commas, semicolons, parentheses, the Arabic
# comma, or a spaced conjunction ("teaching & instruction", "manager / ga4").
# Only *spaced* "&" and "/" split, so glued forms ("R&D", "ui/ux", "ci/cd")
# stay intact.
_SPLIT_RE = re.compile(r"\s[&/]\s|[,;()،؛]")

# Punctuation/bullet markers stripped from the token edges. A leading dot is
# *kept* so tokens like ".net" survive; a trailing dot is sentence punctuation
# and removed. Bullet markers ("* html5", "- css") leak in from list-style tags.
_BULLET_CHARS = "*•‣▪·->–—"
_LEADING_STRIP = " \t" + _BULLET_CHARS + "،,;؛:!?؟"
_TRAILING_STRIP = _LEADING_STRIP + "."

# A leading conjunction left over from an Oxford-comma list ("X, Y, and Z" →
# split → "and Z"). The trailing space requirement keeps real skills that merely
# start with these letters intact ("android", "oracle").
_CONJUNCTION_RE = re.compile(r"^(?:and|or)\s+")

# Contentless terms that are technically "skills" but carry no signal. Checked
# against the *canonical* form (after alias resolution), so compound skills like
# "software development" or "project management" are unaffected — only the bare
# generic token is dropped.
_BLOCKLIST = frozenset({
    "it",
    "management",
    "programming",
    "programming language",
    "programming languages",
    "software",
    "development",
    "framework",
    "frameworks",
    "tool",
    "tools",
    "database",
    "databases",
})


def _has_arabic(text: str) -> bool:
    """True if any character falls in the Arabic Unicode block."""
    return any(_ARABIC_RANGE[0] <= ch <= _ARABIC_RANGE[1] for ch in text)


def canonicalize_one(name: str, en: Optional[str] = None) -> Optional[str]:
    """Normalize one raw skill token to a canonical lowercase form.

    Prefers the English translation ``en`` when available, else ``name``. Does
    **not** split — callers that may receive joined lists should go through
    :func:`canonicalize_keywords`. Returns ``None`` for empty input, sentences,
    Arabic text (storage is English-first), or blocklisted generic terms.
    """
    candidate = (en or "").strip() or (name or "").strip()
    if not candidate:
        return None

    # NFKC folds full-width/compatibility forms; collapse all whitespace runs.
    candidate = unicodedata.normalize("NFKC", candidate)
    candidate = " ".join(candidate.split())

    # Reject sentences and Arabic free text (kept English-first).
    if len(candidate) > MAX_SKILL_CHARS or len(candidate.split()) > MAX_SKILL_WORDS:
        return None
    if _has_arabic(candidate):
        return None

    candidate = candidate.lower()
    candidate = candidate.lstrip(_LEADING_STRIP).rstrip(_TRAILING_STRIP)
    candidate = _CONJUNCTION_RE.sub("", candidate)
    if not candidate:
        return None

    canonical = aliases.resolve(candidate)
    if canonical in _BLOCKLIST:
        return None
    return canonical


def _english_of(keyword: dict) -> Optional[str]:
    """Extract ``userContentTranslations.name.en`` from a keyword dict, if any."""
    uct = keyword.get("userContentTranslations")
    if isinstance(uct, dict):
        name = uct.get("name")
        if isinstance(name, dict):
            return name.get("en")
    return None


def _split(text: str) -> list[str]:
    """Split a keyword tag into candidate skills on list delimiters."""
    return [piece for piece in _SPLIT_RE.split(text or "") if piece.strip()]


def canonicalize_keywords(keywords: Optional[list[dict]]) -> list[str]:
    """Canonicalize a Wuzzuf ``keywords`` array into de-duplicated skill tokens.

    Each keyword is split on list delimiters first (so a single
    ``"Git, GitHub, Bitbucket"`` tag becomes three skills), then every piece is
    canonicalized. Non-skills (sentences, Arabic text, generic terms) are
    dropped. Order is first-seen.
    """
    seen: set[str] = set()
    result: list[str] = []
    for keyword in keywords or []:
        if not isinstance(keyword, dict):
            continue
        source = _english_of(keyword) or keyword.get("name") or ""
        for piece in _split(source):
            skill = canonicalize_one(piece)
            if skill and skill not in seen:
                seen.add(skill)
                result.append(skill)
    return result
