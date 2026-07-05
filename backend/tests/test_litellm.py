"""Integration smoke test: the LiteLLM proxy answers a trivial completion.

Marked ``integration`` so the default ``make test`` run deselects it. Reads its
proxy config from ``get_test_settings()`` (not the prod ``Settings``) and skips
itself when ``TEST_LITELLM_API_KEY`` is unset — see ``.env.example``.
"""

import pytest
from litellm import acompletion

from app.core.config import get_test_settings

pytestmark = pytest.mark.integration


async def test_litellm_proxy_responds():
    settings = get_test_settings()
    if not settings.TEST_LITELLM_API_KEY.get_secret_value():
        pytest.skip("TEST_LITELLM_API_KEY not configured")

    response = await acompletion(
        model=settings.TEST_LLM_MODEL,
        messages=[{"role": "user", "content": "Reply with exactly the word 'PING'."}],
        api_base=settings.TEST_LITELLM_BASE_URL,
        api_key=settings.TEST_LITELLM_API_KEY.get_secret_value(),
    )

    content = response.choices[0].message.content
    assert content is not None
    assert "PING" in content.upper()
