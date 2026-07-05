"""
app/ai/registry.py
==================
Unified LLM gateway — ``LLMServiceRegistry``.

All LLM and embedding calls across every feature in this project route through
this single registry.  It talks to the LiteLLM proxy via the ``litellm`` SDK
directly (no LangChain wrappers), giving us one consistent place to configure
models, keys, and base URLs.

Environment variables
---------------------
LITELLM_BASE_URL
    Base URL of the LiteLLM proxy.
    Example: ``https://management.sprints.ai/litellm``

LITELLM_API_KEY
    API key for the LiteLLM proxy.

LLM_MODEL
    The chat/completion model identifier as recognised by the proxy.
    Default: ``azure/FW-Kimi-K2.6``

Embeddings run locally via ``app.core.embeddings`` (``BAAI/bge-base-en-v1.5``,
768-dim); the model and dimension are compile-time constants, not env vars.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Type

import litellm
from pydantic import BaseModel
from app.core.config import get_settings
from app.core.embeddings import EMBEDDING_DIM, EMBEDDING_MODEL

# ---------------------------------------------------------------------------
# Configuration — read once from the environment at import time
# ---------------------------------------------------------------------------

settings = get_settings()
_LITELLM_BASE_URL: str = settings.LITELLM_BASE_URL
_LITELLM_API_KEY: str = settings.LITELLM_API_KEY.get_secret_value()
_LLM_MODEL: str = settings.LLM_MODEL
# Embeddings run locally (sentence-transformers); model + dim are compile-time
# constants co-located with the pgvector column size in app.core.embeddings.
_EMBEDDING_MODEL: str = EMBEDDING_MODEL
_EMBEDDING_DIMENSION: int = EMBEDDING_DIM


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class LLMServiceRegistry:
    """
    Single, unified gateway for all LLM and embedding calls.

    Uses the ``litellm`` SDK to talk directly to the LiteLLM proxy so that
    every feature in the project shares the same model configuration, API key,
    and base URL without going through LangChain wrappers.

    Obtain the process-wide singleton via :func:`get_registry` rather than
    instantiating this class directly.

    Parameters
    ----------
    base_url:
        Root URL of the LiteLLM proxy (without a trailing slash).
    api_key:
        API key passed as the ``Authorization: Bearer`` header.
    default_model:
        Model identifier used when the caller does not specify one.
    default_embedding_model:
        Embedding model identifier used when the caller does not specify one.
    embedding_dim:
        Dimensionality of the embeddings produced by the default embedding model.
    """

    def __init__(
        self,
        base_url: str = _LITELLM_BASE_URL,
        api_key: str = _LITELLM_API_KEY,
        default_model: str = _LLM_MODEL,
        default_embedding_model: str = _EMBEDDING_MODEL,
        embedding_dim: int = _EMBEDDING_DIMENSION,
    ) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._LLM_MODEL = default_model
        self._default_embedding_model = default_embedding_model
        # Model and dim are now a matched pair fixed in app.core.embeddings, so the
        # old runtime dimension-mismatch guard is no longer needed.
        self.embedding_dim = embedding_dim

    # ------------------------------------------------------------------
    # Chat / completion
    # ------------------------------------------------------------------

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        response_format: Type[BaseModel] | None = None,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> Any:
        """
        Send a chat completion request to the LiteLLM proxy.

        Parameters
        ----------
        messages:
            OpenAI-style message list, e.g.
            ``[{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]``
        model:
            Override the default model for this call.
        response_format:
            A Pydantic ``BaseModel`` subclass.  When provided, litellm will
            request structured JSON output conforming to the model's schema and
            parse the response into an instance of that class automatically.
        temperature:
            Sampling temperature (default ``0.0`` for deterministic output).
        **kwargs:
            Any additional litellm keyword arguments.

        Returns
        -------
        Any
            If *response_format* is given, returns a parsed Pydantic model
            instance.  Otherwise returns the raw
            ``litellm.ModelResponse`` object.
        """
        resolved_model = model or self._LLM_MODEL

        completion_kwargs: dict[str, Any] = dict(
            model=resolved_model,
            messages=messages,
            temperature=temperature,
            api_base=self._base_url,
            api_key=self._api_key,
            **kwargs,
        )

        if response_format is not None:
            completion_kwargs["response_format"] = response_format

        response = litellm.completion(**completion_kwargs)

        if response_format is not None:
            # litellm returns the parsed object in .choices[0].message.content
            # when a Pydantic model is passed as response_format.
            content = response.choices[0].message.content
            if isinstance(content, str):
                return response_format.model_validate_json(content)
            return content

        return response

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
        **kwargs: Any,
    ) -> list[list[float]]:
        """
        Embed a list of text strings via the LiteLLM proxy.

        Parameters
        ----------
        texts:
            One or more strings to embed.
        model:
            Override the default embedding model for this call.
        **kwargs:
            Any additional litellm keyword arguments.

        Returns
        -------
        list[list[float]]
            A list of embedding vectors, one per input string.
        """
        resolved_model = model or self._default_embedding_model

        if resolved_model in ("local", "all-MiniLM-L6-v2", EMBEDDING_MODEL):
            from app.core.embeddings import embed as _embed
            return _embed(texts)

        response = litellm.embedding(
            model=resolved_model,
            input=texts,
            api_base=self._base_url,
            api_key=self._api_key,
            **kwargs,
        )

        return [item["embedding"] for item in response.data]

    # ------------------------------------------------------------------
    # Async chat / completion
    # ------------------------------------------------------------------

    async def acomplete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        response_format: Type[BaseModel] | None = None,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> Any:
        """
        Async variant of :meth:`complete`.

        Sends a chat completion request to the LiteLLM proxy using
        ``litellm.acompletion``.  Parameters and return semantics are
        identical to :meth:`complete`.
        """
        resolved_model = model or self._LLM_MODEL

        completion_kwargs: dict[str, Any] = dict(
            model=resolved_model,
            messages=messages,
            temperature=temperature,
            api_base=self._base_url,
            api_key=self._api_key,
            **kwargs,
        )

        if response_format is not None:
            completion_kwargs["response_format"] = response_format

        response = await litellm.acompletion(**completion_kwargs)

        if response_format is not None:
            content = response.choices[0].message.content
            if isinstance(content, str):
                return response_format.model_validate_json(content)
            return content

        return response

    # ------------------------------------------------------------------
    # Async embeddings
    # ------------------------------------------------------------------

    async def aembed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
        **kwargs: Any,
    ) -> list[list[float]]:
        """
        Async variant of :meth:`embed`.

        Embeds a list of text strings via the LiteLLM proxy using
        ``litellm.aembedding``.  Parameters and return semantics are
        identical to :meth:`embed`.
        """
        resolved_model = model or self._default_embedding_model

        if resolved_model in ("local", "all-MiniLM-L6-v2", EMBEDDING_MODEL):
            from app.core.embeddings import embed as _embed
            return _embed(texts)

        response = await litellm.aembedding(
            model=resolved_model,
            input=texts,
            api_base=self._base_url,
            api_key=self._api_key,
            **kwargs,
        )

        return [item["embedding"] for item in response.data]


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_registry() -> LLMServiceRegistry:
    """
    Return the process-wide :class:`LLMServiceRegistry` singleton.

    The instance is constructed once from environment variables and cached for
    the lifetime of the process.  In tests, call
    ``get_registry.cache_clear()`` after patching env vars if you need a
    fresh instance.
    """
    return LLMServiceRegistry()
