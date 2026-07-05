from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from app.schemas.matching import CandidateProfile
from app.schemas.application_ai import ApplicationRequest, CVTailoringResult, CoverLetterResult
from app.services.application_ai_service import ApplicationAIService


# --- Fixtures ---

@pytest.fixture
def sample_candidate_profile():
    return CandidateProfile(
        name="John Doe",
        contact={"email": "john@example.com"},
        skills=["Python", "FastAPI"],
        experience_years=3,
        education=["BSc Computer Science"],
        preferences={"location": "Remote"}
    )


@pytest.fixture
def sample_request(sample_candidate_profile):
    return ApplicationRequest(
        candidate_id=1,
        job_id=2,
        candidate_profile=sample_candidate_profile,
        job_description="Looking for a Python developer with FastAPI experience."
    )


@pytest.fixture
def mock_cv_tailoring_result():
    return CVTailoringResult(
        tailored_summary="Python Developer with 3 years experience...",
        highlighted_skills=["Python", "FastAPI"],
        missing_skills=["Docker"],
        bullet_point_suggestions=["Rephrase to emphasize FastAPI"]
    )


@pytest.fixture
def mock_cover_letter_result():
    return CoverLetterResult(
        draft_content="Dear Hiring Manager, I am writing to apply...",
        tone_analysis="Professional and eager."
    )


# The pipeline now makes exactly two LLM calls: (1) CV tailoring, (2) cover letter.
# The content-moderation and PII-scrubbing nodes were removed.


@pytest.mark.asyncio
@patch("app.services.application_ai_service.get_registry")
async def test_application_ai_service_success(
    mock_get_registry, sample_request, mock_cv_tailoring_result, mock_cover_letter_result
):
    """Test the full happy-path pipeline with job_description provided directly."""
    mock_registry = MagicMock()
    mock_registry.acomplete = AsyncMock(side_effect=[
        mock_cv_tailoring_result,   # CV tailoring
        mock_cover_letter_result,   # cover letter
    ])
    mock_get_registry.return_value = mock_registry

    service = ApplicationAIService()
    response = await service.generate_application_materials(sample_request)

    assert response.candidate_id == sample_request.candidate_id
    assert response.job_id == sample_request.job_id
    assert response.cv_tailoring.tailored_summary == "Python Developer with 3 years experience..."
    assert "Python" in response.cv_tailoring.highlighted_skills
    assert response.cover_letter.draft_content.startswith("Dear Hiring Manager")
    assert mock_registry.acomplete.await_count == 2


# --- DB job-resolution tests (session-based) ---

@pytest.mark.asyncio
@patch("app.services.application_ai_service.get_registry")
async def test_job_resolution_from_db(
    mock_get_registry, sample_candidate_profile, mock_cv_tailoring_result, mock_cover_letter_result
):
    """Resolve job_description from the DB session when not provided in the request."""
    mock_session = MagicMock()
    mock_session.get = AsyncMock(
        return_value=MagicMock(
            description="Looking for a senior Python developer with 5+ years experience."
        )
    )

    mock_registry = MagicMock()
    mock_registry.acomplete = AsyncMock(side_effect=[
        mock_cv_tailoring_result,
        mock_cover_letter_result,
    ])
    mock_get_registry.return_value = mock_registry

    request = ApplicationRequest(
        candidate_id=1,
        job_id=42,
        candidate_profile=sample_candidate_profile,
    )

    service = ApplicationAIService(session=mock_session)
    response = await service.generate_application_materials(request)

    mock_session.get.assert_awaited_once()
    assert response.cv_tailoring.tailored_summary is not None
    assert response.cover_letter.draft_content is not None


@pytest.mark.asyncio
async def test_job_not_found_in_db(sample_candidate_profile):
    """ValueError when job_id is not found in the DB and no job_description is provided."""
    mock_session = MagicMock()
    mock_session.get = AsyncMock(return_value=None)

    request = ApplicationRequest(
        candidate_id=1,
        job_id=999,
        candidate_profile=sample_candidate_profile,
    )

    service = ApplicationAIService(session=mock_session)

    with pytest.raises(ValueError, match="not found"):
        await service.generate_application_materials(request)


@pytest.mark.asyncio
async def test_no_db_and_no_job_description(sample_candidate_profile):
    """ValueError when no job_description is provided and no session is available."""
    request = ApplicationRequest(
        candidate_id=1,
        job_id=2,
        candidate_profile=sample_candidate_profile,
    )

    service = ApplicationAIService(session=None)

    with pytest.raises(ValueError, match="No job description provided"):
        await service.generate_application_materials(request)


# --- LLM Failure Edge Cases ---

@pytest.mark.asyncio
@patch("app.services.application_ai_service.get_registry")
async def test_cv_tailoring_llm_failure(mock_get_registry, sample_request):
    """Graceful error handling when the CV tailoring LLM call fails."""
    mock_registry = MagicMock()
    mock_registry.acomplete = AsyncMock(side_effect=[Exception("LLM API timeout")])
    mock_get_registry.return_value = mock_registry

    service = ApplicationAIService()

    with pytest.raises(ValueError, match="Failed to generate tailored CV"):
        await service.generate_application_materials(sample_request)


@pytest.mark.asyncio
@patch("app.services.application_ai_service.get_registry")
async def test_cover_letter_llm_failure(
    mock_get_registry, sample_request, mock_cv_tailoring_result
):
    """Graceful error handling when CV tailoring succeeds but cover letter fails."""
    mock_registry = MagicMock()
    mock_registry.acomplete = AsyncMock(side_effect=[
        mock_cv_tailoring_result,
        Exception("LLM API timeout"),
    ])
    mock_get_registry.return_value = mock_registry

    service = ApplicationAIService()

    with pytest.raises(ValueError, match="Failed to generate cover letter"):
        await service.generate_application_materials(sample_request)


# --- Edge Cases ---

@pytest.mark.asyncio
@patch("app.services.application_ai_service.get_registry")
async def test_empty_skills_candidate(
    mock_get_registry, mock_cv_tailoring_result, mock_cover_letter_result
):
    """The pipeline handles candidates with no skills gracefully."""
    mock_registry = MagicMock()
    mock_registry.acomplete = AsyncMock(side_effect=[
        mock_cv_tailoring_result,
        mock_cover_letter_result,
    ])
    mock_get_registry.return_value = mock_registry

    request = ApplicationRequest(
        candidate_id=1,
        job_id=2,
        candidate_profile=CandidateProfile(
            name="Empty Skills User",
            skills=[],
            experience_years=0,
        ),
        job_description="Looking for a Python developer.",
    )

    service = ApplicationAIService()
    response = await service.generate_application_materials(request)

    assert response.cv_tailoring is not None
    assert response.cover_letter is not None
