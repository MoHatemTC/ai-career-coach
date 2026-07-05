"""
app/ai/local_embedder.py
========================
Backwards-compatible thin wrapper around :mod:`app.core.embeddings`.

The model, device, and dimension now live in ``app.core.embeddings`` (the single
source of truth). This module remains only so existing callers of
``get_local_embedder().embed(...)`` keep working; new code should import from
``app.core.embeddings`` directly.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.embeddings import EMBEDDING_DIM, embed, get_embedder


class LocalEmbedder:
    """Adapter exposing ``embed(texts) -> list[list[float]]`` over the shared model."""

    def __init__(self) -> None:
        # Trigger model load so failures surface eagerly, as before.
        get_embedder()

    @property
    def dim(self) -> int:
        """Dimensionality of the output vectors."""
        return EMBEDDING_DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of strings into L2-normalized vectors."""
        return embed(texts)


@lru_cache(maxsize=1)
def get_local_embedder() -> LocalEmbedder:
    """Return the process-wide :class:`LocalEmbedder` singleton."""
    return LocalEmbedder()
