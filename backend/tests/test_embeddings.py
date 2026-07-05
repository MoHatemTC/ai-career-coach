"""Unit tests for the canonical embedding text builders and the materials trigger.

Pure functions — no model download or DB required.
"""

from types import SimpleNamespace

from app.core.embeddings import (
    EMBEDDING_DIM,
    QUERY_PREFIX,
    _DESC_CHAR_CAP,
    build_candidate_text,
    build_candidate_text_from_profile,
    build_job_text,
)
from app.models.job_tracking import TrackingStatus
from app.services.job_tracking_service import should_generate_materials


def test_embedding_dim_is_768():
    assert EMBEDDING_DIM == 768


def test_build_candidate_text_has_query_prefix_and_fields():
    user = SimpleNamespace(
        desired_roles=["AI Engineer"],
        job_titles=["Senior ML Engineer"],
        job_categories=["machine learning"],
        career_level="mid",
        skills=["Python", "LangChain"],
        tools=["Docker"],
        years_of_experience=4,
    )
    text = build_candidate_text(user)
    assert text.startswith(QUERY_PREFIX)
    # Preferences steer the query alongside the facts.
    assert "AI Engineer" in text
    assert "Senior ML Engineer" in text
    assert "machine learning" in text
    assert "Python" in text and "LangChain" in text
    assert "Docker" in text
    assert "4 years experience" in text


def test_build_candidate_text_tolerates_missing_preferences():
    """Preferences are empty until the user sets them — must not error."""
    user = SimpleNamespace(
        desired_roles=[],
        career_level="junior",
        skills=["SQL"],
        tools=[],
        years_of_experience=0,
    )
    text = build_candidate_text(user)  # no job_titles/job_categories attrs
    assert text.startswith(QUERY_PREFIX)
    assert "SQL" in text


def test_build_candidate_text_from_profile_has_prefix():
    profile = SimpleNamespace(skills=["SQL"], tools=["dbt"], experience_years=2)
    text = build_candidate_text_from_profile(profile)
    assert text.startswith(QUERY_PREFIX)
    assert "SQL" in text and "dbt" in text
    assert "2 years experience" in text


def test_build_job_text_no_prefix_and_caps_description():
    long_desc = "x" * (_DESC_CHAR_CAP + 5000)
    job = SimpleNamespace(
        title="Senior Backend Engineer",
        work_roles=["IT/Software Development"],
        required_skills=["python", "sql"],
        keywords_raw=["Python", "SQL"],
        description=long_desc,
    )
    text = build_job_text(job)
    assert not text.startswith(QUERY_PREFIX)
    assert "Senior Backend Engineer" in text
    assert "python" in text and "sql" in text
    # Title/skills/roles always kept; only the description tail is truncated.
    assert text.count("x") == _DESC_CHAR_CAP


def test_should_generate_materials_first_entry_only():
    T = TrackingStatus
    assert should_generate_materials(previous_status=T.SAVED, new_status=T.SHORTLISTED)
    assert should_generate_materials(previous_status=None, new_status=T.SHORTLISTED)
    # Skipping shortlist (SAVED -> APPLIED) does not trigger.
    assert not should_generate_materials(previous_status=T.SAVED, new_status=T.APPLIED)
    # Re-entry from SHORTLISTED does not re-trigger.
    assert not should_generate_materials(
        previous_status=T.SHORTLISTED, new_status=T.SHORTLISTED
    )
