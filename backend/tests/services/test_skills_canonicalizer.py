"""
Unit tests for the pure skill canonicalizer (no I/O, no DB).

The interesting cases come from Wuzzuf's three real keyword shapes — curated
English tags, clean lowercase tokens, and full Arabic requirement sentences —
captured in ``tests/fixtures/wuzzuf/``.
"""

import json
from pathlib import Path

import pytest

from app.services.skills.canonicalizer import (
    _has_arabic,
    canonicalize_keywords,
    canonicalize_one,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "wuzzuf"


def _keywords(filename: str) -> list[dict]:
    data = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
    return data["data"][0]["attributes"]["keywords"]


class TestCanonicalizeOne:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Python", "python"),            # lowercase
            ("  React.js ", "react"),        # alias + trim
            ("JS", "javascript"),            # alias
            ("Postgres", "postgresql"),      # alias
            (".NET Core", ".net"),           # alias, leading dot preserved
            (".NET", ".net"),                # leading dot never stripped
            ("Power BI", "power bi"),        # multi-word, kept
        ],
    )
    def test_normalizes_and_resolves_aliases(self, raw: str, expected: str) -> None:
        assert canonicalize_one(raw) == expected

    def test_prefers_english_translation(self) -> None:
        # Arabic name, but an English translation is available → use English.
        assert canonicalize_one("محلل بيانات", en="Data Analysis") == "data analysis"

    def test_rejects_long_sentence(self) -> None:
        sentence = "Proven experience analyzing sales performance and building dashboards"
        assert canonicalize_one(sentence) is None

    def test_rejects_multiword_arabic_fragment(self) -> None:
        assert canonicalize_one("فهم جيد لمبادئ seo التقني والداخلي") is None

    def test_empty_and_punctuation_only_return_none(self) -> None:
        assert canonicalize_one("") is None
        assert canonicalize_one("   ") is None
        assert canonicalize_one(",;:") is None


class TestCanonicalizeKeywords:
    def test_curated_tags_become_lowercase(self) -> None:
        # "Information Technology (IT)" splits on the parens; bare "it" is a
        # blocklisted generic, leaving just "information technology".
        result = canonicalize_keywords(_keywords("job_curated_tags.json"))
        assert result == [
            "analysis",
            "computer science",
            "data analysis",
            "information technology",
        ]

    def test_arabic_sentences_extract_only_latin_tools(self) -> None:
        # Sentence fragments are dropped, but cleanly-delimited Latin tool names
        # embedded in them are recovered — and nothing Arabic survives.
        result = canonicalize_keywords(_keywords("job_arabic_sentences.json"))
        assert result  # not empty
        assert all(not _has_arabic(s) for s in result)
        assert "google tag manager" in result
        assert "google analytics" in result  # "GA4" alias

    def test_clean_lowercase_tokens_pass_through(self) -> None:
        result = canonicalize_keywords(_keywords("job_remote_usd.json"))
        assert result == ["capcut", "ai tools", "ai ugc", "viral marketing", "iphone"]

    def test_splits_comma_joined_tags(self) -> None:
        keywords = [{"name": "Selenium, Cypress, Playwright"}]
        assert canonicalize_keywords(keywords) == ["selenium", "cypress", "playwright"]

    def test_splits_parenthetical_list(self) -> None:
        keywords = [{"name": "cloud computing (aws, azure, gcp)"}]
        assert canonicalize_keywords(keywords) == [
            "cloud computing", "aws", "azure", "google cloud",
        ]

    def test_splits_spaced_ampersand_but_keeps_glued(self) -> None:
        assert canonicalize_keywords([{"name": "teaching & instruction"}]) == [
            "teaching", "instruction",
        ]
        # Glued ampersand is NOT a delimiter.
        assert canonicalize_keywords([{"name": "R&D"}]) == ["r&d"]

    def test_drops_blocklisted_generics(self) -> None:
        keywords = [{"name": "IT"}, {"name": "Management"}, {"name": "programming language"}]
        assert canonicalize_keywords(keywords) == []

    def test_resolves_new_aliases(self) -> None:
        keywords = [
            {"name": "sw development"},
            {"name": "mysql database"},
            {"name": "AX"},
            {"name": "Certified ScrumMaster (CSM)"},
        ]
        assert canonicalize_keywords(keywords) == [
            "software development", "mysql", "dynamics ax", "certified scrummaster",
        ]

    def test_dedupes_preserving_order(self) -> None:
        keywords = [{"name": "Python"}, {"name": "SQL"}, {"name": "python"}]
        assert canonicalize_keywords(keywords) == ["python", "sql"]

    def test_handles_none_and_non_dicts(self) -> None:
        assert canonicalize_keywords(None) == []
        assert canonicalize_keywords([None, "x", {"name": "Go"}]) == ["go"]
