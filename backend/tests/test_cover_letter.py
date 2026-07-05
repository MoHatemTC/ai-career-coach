"""Integration test: the real ApplicationAIService end-to-end via the live proxy.

Exercises the full two-call pipeline (CV tailoring + cover letter) against the
LiteLLM proxy and asserts the response carries usable content. The mocked/unit
coverage of this pipeline lives in ``test_application_ai_service.py``; this test
verifies the real proxy path.

Marked ``integration`` (deselected by the default ``make test`` run) and skips
itself when ``TEST_LITELLM_API_KEY`` is unset — see ``.env.example``.
"""

import pytest

from app.core.config import get_test_settings
from app.schemas.application_ai import ApplicationRequest
from app.services.application_ai_service import ApplicationAIService
from tests.services.mock_data import MOCK_JOB_DATA, PERFECT_CANDIDATE

pytestmark = pytest.mark.integration


async def test_generate_application_materials_live():
    if not get_test_settings().TEST_LITELLM_API_KEY.get_secret_value():
        pytest.skip("TEST_LITELLM_API_KEY not configured")

    request = ApplicationRequest(
        candidate_id=MOCK_JOB_DATA["job_id"],
        job_id=MOCK_JOB_DATA["job_id"],
        candidate_profile=PERFECT_CANDIDATE,
        job_description=MOCK_JOB_DATA["description"],
    )

    response = await ApplicationAIService().generate_application_materials(request)

    assert response.cv_tailoring.tailored_summary
    assert response.cover_letter.draft_content
    assert response.cover_letter.tone_analysis
