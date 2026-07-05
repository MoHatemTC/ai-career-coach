"""
Skill alias map — collapses synonyms onto a single canonical form.

The map lives in ``data/skill_aliases.json`` as ``alias -> canonical`` (both
expected to be lowercase). It is loaded once and cached. Keys are matched
against an *already-normalized* token (lowercased, whitespace-collapsed,
stripped — see :mod:`app.services.skills.canonicalizer`), so the JSON keys must
themselves be in that normalized form.

Unknown tokens are returned unchanged, so missing aliases degrade gracefully:
the skill is still recorded, just under its own name.
"""

import json
from functools import lru_cache

import structlog

from app.core.config import get_settings

logger = structlog.get_logger()


@lru_cache(maxsize=1)
def _alias_map() -> dict[str, str]:
    """Load and cache the alias map. Missing/invalid file → empty map."""
    path = get_settings().SKILL_ALIASES_PATH
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning("skill_aliases_unavailable", path=str(path))
        return {}
    # Normalize keys/values defensively so a stray capital in the JSON can't
    # silently disable an alias.
    return {str(k).strip().lower(): str(v).strip().lower() for k, v in data.items()}


def resolve(token: str) -> str:
    """Return the canonical form for ``token``, or ``token`` itself if unknown.

    ``token`` must already be normalized (lowercase, trimmed).
    """
    return _alias_map().get(token, token)
