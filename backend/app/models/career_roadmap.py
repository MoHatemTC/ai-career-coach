"""
app/models/career_roadmap.py
=============================
SQLModel ORM model for the ``career_roadmaps`` table.

Design decisions
----------------
* ``weeks`` and ``key_focus_areas`` use ``Column(JSON)`` so they survive
  PostgreSQL without extra dependencies and round-trip correctly through
  SQLite in tests.
* ``readiness_score_id`` is a plain integer foreign key pointing at
  ``readiness_scores.id``.  No SQLModel-level ``Relationship`` is declared
  to keep the model lightweight and avoid circular imports; joins are done
  in the service layer when needed.
* This mirrors the patterns established by
  :mod:`app.models.readiness_score` and :mod:`app.models.role_benchmark`.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlmodel import Column, Field, JSON, SQLModel


class CareerRoadmap(SQLModel, table=True):
    """
    Persisted result of a single career roadmap generation.

    Each row records the full LLM output (weekly plans, executive summary,
    focus areas, responsible AI disclaimer) alongside the readiness score
    reference so the roadmap can be traced back to its source assessment.

    Attributes
    ----------
    id:
        Auto-increment primary key.
    readiness_score_id:
        Foreign key referencing ``readiness_scores.id``.
    weeks:
        JSON list of weekly roadmap plans.  Each week is a dict containing
        ``week_number``, ``theme``, and ``actions`` (list of action dicts).
    executive_summary:
        3–5 sentence overview of the roadmap strategy.
    key_focus_areas:
        JSON list of top focus areas derived from the gap analysis.
    responsible_ai_disclaimer:
        AI ethics disclaimer text included in every generated roadmap.
    created_at:
        UTC timestamp set automatically on insert.
    """

    __tablename__ = "career_roadmaps"

    id: Optional[int] = Field(default=None, primary_key=True)

    # ── Readiness score reference ────────────────────────────────────────
    readiness_score_id: int = Field(
        foreign_key="readiness_scores.id",
        index=True,
        description="FK → readiness_scores.id",
    )

    # ── Roadmap content ─────────────────────────────────────────────────
    weeks: List[dict] = Field(
        default_factory=list,
        sa_column=Column(JSON),
    )
    executive_summary: str = Field(default="")
    key_focus_areas: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSON),
    )
    responsible_ai_disclaimer: str = Field(default="")

    # ── Metadata ────────────────────────────────────────────────────────
    created_at: datetime = Field(default_factory=datetime.utcnow)
    reviewed_at: Optional[datetime] = Field(default=None)
