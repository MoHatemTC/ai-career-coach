"""
app/ai/prompts.py
=================
``PromptBuilder`` — centralised factory for building LLM message payloads.

Prompt templates are stored as plain Markdown files in ``app/ai/prompts/``
and loaded once at module import time.  Callers receive standard
OpenAI-style message lists (``list[dict[str, str]]``) that can be passed
directly to :class:`~app.ai.registry.LLMServiceRegistry`.

Usage
-----
::

    from app.ai.prompts import PromptBuilder

    messages = PromptBuilder.build_cv_tailoring_messages(
        candidate_profile=profile_json,
        job_description=jd_text,
    )
    result = await get_registry().acomplete(messages, response_format=CVTailoringResult)
"""

from __future__ import annotations

import json
import os
from typing import Any

# ---------------------------------------------------------------------------
# Template loading — file I/O happens once at import time, not per request
# ---------------------------------------------------------------------------

_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")

with open(os.path.join(_PROMPTS_DIR, "role_benchmark.md"), "r", encoding="utf-8") as _f:
    _ROLE_BENCHMARK_SYSTEM_PROMPT: str = _f.read()

with open(
    os.path.join(_PROMPTS_DIR, "readiness_gap_analysis.md"), "r", encoding="utf-8"
) as _f:
    _READINESS_GAP_ANALYSIS_SYSTEM_PROMPT: str = _f.read()

with open(
    os.path.join(_PROMPTS_DIR, "career_roadmap.md"), "r", encoding="utf-8"
) as _f:
    _CAREER_ROADMAP_SYSTEM_PROMPT: str = _f.read()

with open(os.path.join(_PROMPTS_DIR, "job_matching.md"), "r", encoding="utf-8") as _f:
    JOB_MATCHING_PROMPT: str = _f.read()

with open(os.path.join(_PROMPTS_DIR, "match_analysis.md"), "r", encoding="utf-8") as _f:
    MATCH_ANALYSIS_PROMPT: str = _f.read()

with open(os.path.join(_PROMPTS_DIR, "cv_tailoring.md"), "r", encoding="utf-8") as _f:
    CV_TAILORING_PROMPT: str = _f.read()

with open(os.path.join(_PROMPTS_DIR, "cover_letter.md"), "r", encoding="utf-8") as _f:
    COVER_LETTER_PROMPT: str = _f.read()

# CV Parsing doesn't have an external file yet — inline template
CV_PARSING_PROMPT = """\
You are an expert technical recruiter and career coach. Your task is to parse the following CV text and extract the candidate's profile into a structured JSON format.

Extract the following fields:
- "name": string
- "contact": object with email and phone
- "skills": list of strings (technical and soft skills)
- "experience_years": integer
- "education": list of degrees/certifications
- "preferences": object (e.g., job titles of interest, locations if mentioned)

CV Text:
{cv_text}

Output ONLY valid JSON."""


# ---------------------------------------------------------------------------
# PromptBuilder
# ---------------------------------------------------------------------------


class PromptBuilder:
    """
    Factory for building OpenAI-style message lists from stored Markdown
    templates.

    Each ``build_*`` method returns a ``list[dict[str, str]]`` that is ready
    to pass to :meth:`~app.ai.registry.LLMServiceRegistry.complete` or
    :meth:`~app.ai.registry.LLMServiceRegistry.acomplete`.

    The class is stateless; instantiate it anywhere without arguments.
    """

    # ------------------------------------------------------------------
    # Match Analysis (persisted gap analysis → JobMatchTable)
    # ------------------------------------------------------------------

    @staticmethod
    def build_match_analysis_messages(
        candidate_profile: str, job_posting: str
    ) -> list[dict[str, str]]:
        """Build messages for the persisted (user, job) gap analysis.

        Parameters
        ----------
        candidate_profile:
            JSON string describing the candidate (skills, tools, experience, ...).
        job_posting:
            JSON string describing the job (title, required_skills, description, ...).
        """
        return [
            {"role": "system", "content": MATCH_ANALYSIS_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Candidate profile:\n{candidate_profile}\n\n"
                    f"Job:\n{job_posting}"
                ),
            },
        ]

    # ------------------------------------------------------------------
    # CV Parsing (Nourhan)
    # ------------------------------------------------------------------

    @staticmethod
    def build_cv_parsing_prompt(cv_text: str) -> str:
        """
        Build a CV parsing prompt string.

        .. note::
            This method returns a plain ``str`` (not ``list[dict]``) for
            backward compatibility with tests.  Callers that need messages
            should wrap the result::

                messages = [{"role": "system", "content": prompt}]
        """
        return CV_PARSING_PROMPT.replace("{cv_text}", cv_text)

    @staticmethod
    def build_cv_parsing_messages(cv_text: str) -> list[dict[str, str]]:
        """
        Build the message payload for CV parsing.

        Returns
        -------
        list[dict[str, str]]
            OpenAI-style messages with the CV parsing prompt as system content.
        """
        prompt = CV_PARSING_PROMPT.replace("{cv_text}", cv_text)
        return [
            {"role": "system", "content": prompt},
        ]

    # ------------------------------------------------------------------
    # Job Matching (Nourhan)
    # ------------------------------------------------------------------

    @staticmethod
    def build_job_matching_prompt(
        candidate_profile: str, job_description: str
    ) -> str:
        """
        Build a job matching prompt string.

        .. note::
            Returns a plain ``str`` for backward compatibility.
            Prefer :meth:`build_job_matching_messages` for new code.
        """
        prompt = JOB_MATCHING_PROMPT
        prompt = prompt.replace("{candidate_profile}", candidate_profile)
        prompt = prompt.replace("{job_description}", job_description)
        return prompt

    @staticmethod
    def build_job_matching_messages(
        candidate_profile: str, job_description: str
    ) -> list[dict[str, str]]:
        """
        Build the message payload for job matching.

        Returns
        -------
        list[dict[str, str]]
            OpenAI-style messages with the job matching prompt as system content.
        """
        prompt = JOB_MATCHING_PROMPT
        prompt = prompt.replace("{candidate_profile}", candidate_profile)
        prompt = prompt.replace("{job_description}", job_description)
        return [
            {"role": "system", "content": prompt},
        ]

    # ------------------------------------------------------------------
    # CV Tailoring (Nourhan)
    # ------------------------------------------------------------------

    @staticmethod
    def build_cv_tailoring_prompt(
        candidate_profile: str, job_description: str
    ) -> str:
        """
        Build a CV tailoring prompt string.

        .. note::
            Returns a plain ``str`` for backward compatibility.
            Prefer :meth:`build_cv_tailoring_messages` for new code.
        """
        prompt = CV_TAILORING_PROMPT
        prompt = prompt.replace("{candidate_profile}", candidate_profile)
        prompt = prompt.replace("{job_description}", job_description)
        return prompt

    @staticmethod
    def build_cv_tailoring_messages(
        candidate_profile: str, job_description: str
    ) -> list[dict[str, str]]:
        """
        Build the message payload for CV tailoring.

        Returns
        -------
        list[dict[str, str]]
            OpenAI-style messages with the CV tailoring prompt as system content.
        """
        prompt = CV_TAILORING_PROMPT
        prompt = prompt.replace("{candidate_profile}", candidate_profile)
        prompt = prompt.replace("{job_description}", job_description)
        return [
            {"role": "system", "content": prompt},
        ]

    # ------------------------------------------------------------------
    # Cover Letter (Nourhan)
    # ------------------------------------------------------------------

    @staticmethod
    def build_cover_letter_prompt(
        cv_tailoring_result: str, job_description: str
    ) -> str:
        """
        Build a cover letter prompt string.

        .. note::
            Returns a plain ``str`` for backward compatibility.
            Prefer :meth:`build_cover_letter_messages` for new code.
        """
        prompt = COVER_LETTER_PROMPT
        prompt = prompt.replace("{cv_tailoring_result}", cv_tailoring_result)
        prompt = prompt.replace("{job_description}", job_description)
        return prompt

    @staticmethod
    def build_cover_letter_messages(
        cv_tailoring_result: str, job_description: str
    ) -> list[dict[str, str]]:
        """
        Build the message payload for cover letter generation.

        Returns
        -------
        list[dict[str, str]]
            OpenAI-style messages with the cover letter prompt as system content.
        """
        prompt = COVER_LETTER_PROMPT
        prompt = prompt.replace("{cv_tailoring_result}", cv_tailoring_result)
        prompt = prompt.replace("{job_description}", job_description)
        return [
            {"role": "system", "content": prompt},
        ]

    # ------------------------------------------------------------------
    # Role Benchmark (Ahmed)
    # ------------------------------------------------------------------

    @staticmethod
    def build_role_benchmark_messages(raw_text: str) -> list[dict[str, str]]:
        """
        Build the message payload for the role-benchmark extraction task.

        Combines the cached system prompt (loaded from
        ``app/ai/prompts/role_benchmark.md``) with the caller-supplied job
        description text.

        Parameters
        ----------
        raw_text:
            The raw, unstructured job description as plain text.

        Returns
        -------
        list[dict[str, str]]
            OpenAI-style messages::

                [
                    {"role": "system", "content": "<role_benchmark system prompt>"},
                    {"role": "user",   "content": "Job Description:\\n\\n<raw_text>"},
                ]
        """
        return [
            {"role": "system", "content": _ROLE_BENCHMARK_SYSTEM_PROMPT},
            {"role": "user", "content": f"Job Description:\n\n{raw_text}"},
        ]

    # ------------------------------------------------------------------
    # Readiness Gap Analysis (Ahmed)
    # ------------------------------------------------------------------

    @staticmethod
    def build_readiness_gap_analysis_messages(
        candidate_profile: dict[str, Any],
        benchmark: dict[str, Any],
    ) -> list[dict[str, str]]:
        """
        Build the message payload for the career readiness gap-analysis task.

        Combines the cached system prompt (loaded from
        ``app/ai/prompts/readiness_gap_analysis.md``) with the caller-supplied
        candidate profile and role benchmark, serialised as JSON.

        Parameters
        ----------
        candidate_profile:
            A dict representation of the candidate's qualifications, containing
            at minimum the keys ``skills``, ``tools``, ``experience_years``, and
            ``education``.
        benchmark:
            A dict representation of the role benchmark, containing at minimum
            ``must_have_skills``, ``nice_to_have_skills``, ``required_tools``,
            ``minimum_years``, ``seniority_level``, and
            ``common_responsibilities``.

        Returns
        -------
        list[dict[str, str]]
            OpenAI-style messages::

                [
                    {"role": "system", "content": "<readiness gap-analysis system prompt>"},
                    {"role": "user",   "content": "<JSON payload with profile + benchmark>"},
                ]
        """
        user_payload = json.dumps(
            {
                "candidate_profile": candidate_profile,
                "role_benchmark": benchmark,
            },
            indent=2,
            ensure_ascii=False,
        )
        return [
            {"role": "system", "content": _READINESS_GAP_ANALYSIS_SYSTEM_PROMPT},
            {"role": "user", "content": user_payload},
        ]

    # ------------------------------------------------------------------
    # Career Roadmap (Ahmed — Sprint 4)
    # ------------------------------------------------------------------

    @staticmethod
    def build_career_roadmap_messages(
        readiness_analysis: dict[str, Any],
        benchmark: dict[str, Any],
    ) -> list[dict[str, str]]:
        """
        Build the message payload for the career roadmap generation task.

        Combines the cached system prompt (loaded from
        ``app/ai/prompts/career_roadmap.md``) with the caller-supplied
        readiness assessment and role benchmark, serialised as JSON.

        Parameters
        ----------
        readiness_analysis:
            A dict representation of the readiness gap analysis, containing
            at minimum ``overall_score``, ``sub_scores``, ``critical_gaps``,
            ``nice_to_have_gaps``, ``strengths``, and ``explanation``.
        benchmark:
            A dict representation of the role benchmark, containing at minimum
            ``must_have_skills``, ``nice_to_have_skills``, ``required_tools``,
            ``minimum_years``, ``seniority_level``, and
            ``common_responsibilities``.

        Returns
        -------
        list[dict[str, str]]
            OpenAI-style messages::

                [
                    {"role": "system", "content": "<career roadmap system prompt>"},
                    {"role": "user",   "content": "<JSON payload with analysis + benchmark>"},
                ]
        """
        user_payload = json.dumps(
            {
                "readiness_assessment": readiness_analysis,
                "role_benchmark": benchmark,
            },
            indent=2,
            ensure_ascii=False,
        )
        return [
            {"role": "system", "content": _CAREER_ROADMAP_SYSTEM_PROMPT},
            {"role": "user", "content": user_payload},
        ]
