"""
Skill canonicalization and persistence.

Two layers, split by concern:

  * ``canonicalizer`` / ``aliases`` — pure functions that turn raw, dirty,
    bilingual keyword data into canonical lowercase skill tokens. No I/O.
  * ``repository`` — the only piece that touches the database: get-or-create
    ``SkillTable`` rows and link them to a job.

The pure layer is reusable anywhere a free-text skill needs normalizing
(job keywords today, CV skills later).
"""

from app.services.skills.canonicalizer import (
    canonicalize_keywords,
    canonicalize_one,
)

__all__ = ["canonicalize_one", "canonicalize_keywords"]
