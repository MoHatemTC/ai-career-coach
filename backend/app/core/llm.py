"""
app/core/llm.py
===============
Backward-compatible shim — re-exports the unified ``LLMServiceRegistry``
from :mod:`app.ai.registry`.

All new code should import directly from ``app.ai.registry``::

    from app.ai.registry import get_registry

    registry = get_registry()
    registry.complete(messages, response_format=MyModel)
    await registry.acomplete(messages, response_format=MyModel)
    registry.embed(["text to embed"])
    await registry.aembed(["text to embed"])

This module ensures that existing imports such as
``from app.core.llm import LLMServiceRegistry`` continue to work without
code changes.
"""

from app.ai.registry import LLMServiceRegistry, get_registry  # noqa: F401

__all__ = ["LLMServiceRegistry", "get_registry"]
