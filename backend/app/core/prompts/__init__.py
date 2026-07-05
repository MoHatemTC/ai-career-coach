"""This file contains the prompts for the agent."""

import os
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)

from app.core.config import get_settings

settings = get_settings()
_PROMPTS_DIR = os.path.dirname(__file__)

# Read templates once at module load — no file I/O per request
try:
    with open(os.path.join(_PROMPTS_DIR, "system.md"), "r") as _f:
        _SYSTEM_PROMPT_TEMPLATE = _f.read()
except FileNotFoundError:
    logger.warning("system.md not found in prompts directory.")
    _SYSTEM_PROMPT_TEMPLATE = ""

try:
    with open(os.path.join(_PROMPTS_DIR, "session_title.md"), "r") as _f:
        SESSION_TITLE_PROMPT = _f.read()
except FileNotFoundError:
    logger.warning("session_title.md not found in prompts directory.")
    SESSION_TITLE_PROMPT = ""


def load_system_prompt(username: Optional[str] = None, **kwargs):
    """Load the system prompt from the cached template."""
    user_context = f"# User\nYou are talking to {username}.\n" if username else ""
    return _SYSTEM_PROMPT_TEMPLATE.format(
        agent_name=settings.PROJECT_NAME + " Agent",
        current_date_and_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        user_context=user_context,
        **kwargs,
    )
