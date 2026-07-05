"""
app/core/embeddings.py
======================
Single source of truth for the local embedding model and the canonical text
construction used across the whole app (ingestion, recommendation, matching).

The embedding **model** and its output **dimension** are plain Python constants
here — *not* env vars. `EMBEDDING_DIM` is what `app/models/jobs.py` uses to size
the pgvector column and what the Alembic migration hardcodes, so it must be a
compile-time constant that cannot drift from the model at runtime.

Model: ``BAAI/bge-base-en-v1.5`` — 768-dim, 512-token English retrieval model.
It is an *asymmetric* retriever: the short candidate text (the "query") is
prefixed with :data:`QUERY_PREFIX`; job descriptions (the "passages") are not.
Embeddings are L2-normalized so pgvector cosine distance is meaningful
(``vector_cosine_ops``).
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

# Heavy imports (torch, sentence_transformers) are deferred to get_embedder()
# to prevent Alembic startup failures and circular import bugs on Windows.

if TYPE_CHECKING:  # avoid a heavy import cycle at module load
    from sentence_transformers import SentenceTransformer

    from app.models.jobs import JobTable, UserTable

# ---------------------------------------------------------------------------
# Constants — the one place model + dimension are defined
# ---------------------------------------------------------------------------

EMBEDDING_MODEL: str = "BAAI/bge-base-en-v1.5"
EMBEDDING_DIM: int = 768

# bge-v1.5 wants a retrieval instruction on the *query* side only.
QUERY_PREFIX: str = "Represent this sentence for searching relevant passages: "

# Keep the assembled job passage within the model's 512-token window. Job
# descriptions run long (p95 ≈ 4.2k chars); title/skills/roles carry the
# strongest retrieval signal and are always kept in full, so only the
# description tail (boilerplate benefits/EEO text) is dropped.
_DESC_CHAR_CAP: int = 1500


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_embedder() -> SentenceTransformer:
    """Return the process-wide sentence-transformers model (loaded once)."""
    import torch
    from sentence_transformers import SentenceTransformer
    device = "cuda" if torch.cuda.is_available() else "cpu"
    return SentenceTransformer(EMBEDDING_MODEL, device=device)


def embed(texts: list[str]) -> list[list[float]]:
    """Embed pre-built texts into L2-normalized vectors.

    Callers are responsible for building the text via :func:`build_candidate_text`
    / :func:`build_job_text` (which own the query-prefix asymmetry); this function
    only encodes and normalizes.
    """
    vectors = get_embedder().encode(
        texts, convert_to_numpy=True, normalize_embeddings=True
    )
    return [v.tolist() for v in vectors]


# ---------------------------------------------------------------------------
# Canonical text construction — used by every call site
# ---------------------------------------------------------------------------


def _join(values: list[str] | None) -> str:
    return ", ".join(v for v in (values or []) if v)


def build_candidate_text(user: "UserTable") -> str:
    """Build the **query**-side text for a candidate (bge query prefix included).

    Combines facts (skills, tools, career level, experience) with the user's
    stated preferences (desired roles, target titles, categories) so the vector
    search is steered toward what the candidate *wants*, not just what they've
    done. Preference fields are read defensively — they are empty until the user
    sets them via the profile endpoint.
    """
    # `getattr` defaults keep this robust for lightweight stubs and empty prefs.
    roles = _join(getattr(user, "desired_roles", None))
    titles = _join(getattr(user, "job_titles", None))
    categories = _join(getattr(user, "job_categories", None))
    skills = _join(user.skills)
    tools = _join(user.tools)
    body = (
        f"{roles} | {titles} | {categories} | {user.career_level} | "
        f"skills: {skills} | tools: {tools} | "
        f"{user.years_of_experience} years experience"
    )
    return QUERY_PREFIX + body


def build_candidate_text_from_profile(profile) -> str:
    """Adapter for call sites that only hold a ``CandidateProfile`` schema.

    Mirrors :func:`build_candidate_text` using the fields a ``CandidateProfile``
    exposes (no ``desired_roles``/``career_level`` there).
    """
    skills = _join(getattr(profile, "skills", None))
    tools = _join(getattr(profile, "tools", None))
    body = (
        f"skills: {skills} | tools: {tools} | "
        f"{getattr(profile, 'experience_years', 0)} years experience"
    )
    return QUERY_PREFIX + body


def build_job_text(job: "JobTable") -> str:
    """Build the **passage**-side text for a job (no prefix, description budgeted)."""
    header = (
        f"{job.title}\n"
        f"roles: {_join(job.work_roles)}\n"
        f"skills: {_join(job.required_skills)}\n"
        f"keywords: {_join(job.keywords_raw)}"
    )
    description = (job.description or "")[:_DESC_CHAR_CAP]
    return f"{header}\n{description}"
