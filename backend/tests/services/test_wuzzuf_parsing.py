"""
Unit tests for the pure Wuzzuf parser (``wuzzuf_parsing``) — no I/O.

Extractors are checked against both inline dicts and the saved real payloads in
``tests/fixtures/wuzzuf/``.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.job_sources import wuzzuf_parsing as wp

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "wuzzuf"


def _attrs(filename: str) -> dict:
    data = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
    return data["data"][0]["attributes"]


def _item(filename: str) -> dict:
    return json.loads((FIXTURES / filename).read_text(encoding="utf-8"))["data"][0]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

class TestTextHelpers:
    def test_strip_html_removes_tags_and_entities(self) -> None:
        assert wp.strip_html("<p>Hello&nbsp;&amp; bye</p>") == "Hello & bye"

    def test_strip_html_handles_none(self) -> None:
        assert wp.strip_html(None) == ""

    def test_parse_datetime_returns_utc_aware(self) -> None:
        dt = wp.parse_datetime("06/01/2025 10:30:00")
        assert dt == datetime(2025, 6, 1, 10, 30, 0, tzinfo=timezone.utc)

    def test_parse_datetime_returns_none_on_garbage(self) -> None:
        assert wp.parse_datetime("not-a-date") is None
        assert wp.parse_datetime(None) is None


# ---------------------------------------------------------------------------
# Field extractors
# ---------------------------------------------------------------------------

class TestExtractors:
    def test_extract_geo_splits_country_city_area(self) -> None:
        geo = wp.extract_geo(_attrs("job_arabic_sentences.json"))
        assert geo.country_code == "EG"
        assert geo.country_name == "Egypt"
        assert geo.city == "Cairo"
        assert geo.area == "Nasr City"

    def test_extract_geo_empty(self) -> None:
        geo = wp.extract_geo({})
        assert geo == wp.Geo(None, None, None, None)

    def test_extract_workplace(self) -> None:
        assert wp.extract_workplace(_attrs("job_remote_usd.json")) == "remote"
        assert wp.extract_workplace(_attrs("job_curated_tags.json")) == "on_site"
        assert wp.extract_workplace({}) is None

    @pytest.mark.parametrize(
        ("raw_label", "expected"),
        [
            ("Remote", "remote"),
            ("remote", "remote"),
            ("Work From Home", "remote"),
            ("On-site", "on_site"),
            ("On Site", "on_site"),
            ("Onsite", "on_site"),
            ("Hybrid", "hybrid"),
            ("hybrid", "hybrid"),
            ("Unknown", None),
            (None, None),
        ],
    )
    def test_extract_workplace_normalization(self, raw_label, expected) -> None:
        attrs = {"workplaceArrangement": {"displayedName": raw_label}}
        assert wp.extract_workplace(attrs) == expected
        
        if raw_label:
            attrs_translated = {
                "workplaceArrangement": {
                    "translations": {"displayed_name": {"en": raw_label}}
                }
            }
            assert wp.extract_workplace(attrs_translated) == expected

    def test_extract_job_types_and_roles(self) -> None:
        attrs = _attrs("job_curated_tags.json")
        assert wp.extract_job_types(attrs) == ["full_time"]
        assert wp.extract_work_roles(attrs) == ["IT/Software Development"]

    def test_extract_salary_visible(self) -> None:
        salary = wp.extract_salary(_attrs("job_remote_usd.json"))
        assert (salary.min, salary.max) == (100, 2000)
        assert salary.currency == "USD"
        assert salary.period == "Per Month"
        assert salary.hidden is False

    def test_extract_salary_hidden(self) -> None:
        salary = wp.extract_salary(_attrs("job_curated_tags.json"))
        assert salary.hidden is True
        assert salary.currency is None

    def test_extract_years(self) -> None:
        assert wp.extract_years(_attrs("job_curated_tags.json")) == (3, 6)
        assert wp.extract_years({}) == (None, None)

    @pytest.mark.parametrize(
        ("career_raw", "years_min", "expected"),
        [
            ("Student", None, "junior"),
            ("Entry Level", None, "junior"),
            ("Experienced", 1, "junior"),
            ("Experienced", 4, "mid"),
            ("Experienced", 8, "senior"),
            ("Experienced", None, "mid"),
            ("Manager", None, "senior"),
            ("Senior Management", None, None),
        ],
    )
    def test_map_experience_level(self, career_raw, years_min, expected) -> None:
        assert wp.map_experience_level(career_raw, years_min) == expected

    def test_display_location(self) -> None:
        assert wp.display_location(wp.Geo("EG", "Egypt", "Cairo", None)) == "Cairo, Egypt"
        assert wp.display_location(wp.Geo(None, "Egypt", None, None)) == "Egypt"
        assert wp.display_location(wp.Geo(None, None, None, None)) == "Cairo"


# ---------------------------------------------------------------------------
# parse_job — the end-to-end mapping
# ---------------------------------------------------------------------------

class TestParseJob:
    def test_curated_job(self) -> None:
        job = wp.parse_job(_item("job_curated_tags.json"), company_name="EGMED")
        assert job is not None
        assert job.title == "Data Analyst"
        assert job.company == "EGMED"
        assert job.country_code == "EG"
        assert job.work_mode == "on_site"
        assert job.experience_level == "mid"
        # "Information Technology (IT)" splits on the parens; bare "it" is dropped
        # as a blocklisted generic.
        assert job.required_skills == [
            "analysis", "computer science", "data analysis", "information technology"
        ]
        assert job.external_id == "2aae5924-f7f8-47cc-82cf-7d3bba6f94ec"
        assert str(job.posted_date) == "2026-06-17"
        assert job.raw_payload is not None

    def test_arabic_job_uses_english_title_and_extracts_latin_tools(self) -> None:
        job = wp.parse_job(_item("job_arabic_sentences.json"), company_name="X")
        assert job is not None
        # English translation preferred over the Arabic raw title.
        assert "Marketing" in job.title
        assert job.language == "ar"
        # Sentence fragments drop, but Latin tools embedded in them are recovered;
        # nothing Arabic survives.
        assert job.required_skills
        assert all(ch < "؀" or ch > "ۿ" for s in job.required_skills for ch in s)
        assert "google tag manager" in job.required_skills

    def test_remote_usd_job(self) -> None:
        job = wp.parse_job(_item("job_remote_usd.json"), company_name="X")
        assert job is not None
        assert job.work_mode == "remote"
        assert job.country_code == "MA"  # parser is country-agnostic; search does the filtering
        assert job.salary_currency == "USD"
        assert (job.salary_min, job.salary_max) == (100, 2000)
        assert job.salary_period == "Per Month"

    def test_drops_senior_management(self) -> None:
        item = _item("job_curated_tags.json")
        item["attributes"]["careerLevel"] = {"name": "Senior Management"}
        assert wp.parse_job(item, company_name="X") is None
