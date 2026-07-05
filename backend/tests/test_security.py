import re
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# KEY=<literal value>  is bad;  KEY=${VAR}  (an env reference) is fine, and so is
# an empty  KEY=  line. The negative lookaheads encode exactly that.
KEY_VALUE_PATTERNS = [
    re.compile(r"LITELLM_API_KEY\s*=\s*(?!\$\{)(?!$)\S+"),
    re.compile(r"OPENAI_API_KEY\s*=\s*(?!\$\{)(?!$)\S+"),
    re.compile(r"GEMINI_API_KEY\s*=\s*(?!\$\{)(?!$)\S+"),
    re.compile(r"ANTHROPIC_API_KEY\s*=\s*(?!\$\{)(?!$)\S+"),
]
# Provider key prefixes — unambiguously a secret wherever they appear.
TOKEN_PATTERNS = ["sk" + "-ant-", "sk" + "-proj-", "sk" + "-or-"]

# Tracked paths we intentionally skip:
#   tests/ — holds the fixtures and pattern strings used by this very test
#   data/  — the curated job-dataset dump
SKIP_DIRS = ("tests/", "data/")
#   .pre-commit-config.yaml — contains the literal sk-ant-/sk-proj-/sk-or- regex
#   uv.lock                 — hashes can coincidentally contain a token substring
SKIP_FILES = {".pre-commit-config.yaml", "uv.lock"}
# Env templates legitimately carry KEY=placeholder lines (e.g.
# LITELLM_API_KEY=your_litellm_key), so the KEY=value check is skipped for them —
# the TOKEN_PATTERNS scan still runs, so a real key pasted in is still caught.
ENV_TEMPLATE_SUFFIXES = (".env.example", ".env.sample", ".env.template")


def _tracked_files() -> list[str]:
    """Every git-tracked path, as forward-slash relative strings."""
    out = subprocess.run(
        ["git", "ls-files"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [line for line in out.splitlines() if line]


def test_no_hardcoded_secrets_in_repo():
    """Fail if any *git-tracked* file contains a hardcoded API key.

    Scans what is actually committed (via ``git ls-files``) rather than walking
    the working tree, so it ignores ``.env`` (gitignored) and ``.venv`` for free
    and covers every tracked text file — Dockerfile, Makefile, shell scripts,
    ini — without maintaining an extension allowlist. Undecodable (binary) files
    are skipped rather than crashing the run.
    """
    for rel in _tracked_files():
        if rel.startswith(SKIP_DIRS) or Path(rel).name in SKIP_FILES:
            continue

        try:
            content = (PROJECT_ROOT / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            # Binary blob, or a path staged for deletion — nothing to scan.
            continue

        for token in TOKEN_PATTERNS:
            assert token not in content, (
                f"Hardcoded secret token '{token}...' found in {rel}!"
            )

        # Placeholder-bearing env templates are exempt from the KEY=value check.
        if rel.endswith(ENV_TEMPLATE_SUFFIXES):
            continue

        for pattern in KEY_VALUE_PATTERNS:
            match = pattern.search(content)
            assert match is None, (
                f"Hardcoded secret found in {rel}: '{match.group()}'"
            )
