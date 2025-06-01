import os
import time
import logging
from datetime import date
from pathlib import Path
from typing import List, Dict, Optional, Union

from vea.utils.llm_utils import run_llm_prompt

logger = logging.getLogger(__name__)

APP_ROOT = Path(__file__).resolve().parents[2]
PROMPT_TEMPLATE_PATH = APP_ROOT / "vea" / "prompts" / "daily-default.prompt"
APP_WEEKLY_PROMPT_PATH = APP_ROOT / "vea/prompts/weekly-default.prompt"


def load_prompt_template(path: Optional[Path] = None) -> str:
    template_path = path or PROMPT_TEMPLATE_PATH
    with open(template_path, encoding="utf-8") as f:
        return f.read()


def render_daily_prompt(
    template: str,
    *,
    date: Union[date, str],
    bio: str,
    calendars: str,
    tasks: str,
    emails: str,
    journals: str,
    extras: str,
    slack: str = ""
) -> str:
    return template.format(
        date=str(date),
        bio=bio,
        calendars=calendars,
        tasks=tasks,
        emails=emails,
        journals=journals,
        extras=extras,
        slack=slack
    )


def summarize_daily(
    model: str,
    date: date,
    emails: List,
    calendars: List,
    tasks: List,
    journals: List,
    extras: List,
    slack: Optional[Dict[str, List[Dict[str, str]]]] = None,
    bio: str = "",
    quiet: bool = False,
    debug: bool = False,
) -> str:

    prompt_template = load_prompt_template()
    prompt = render_daily_prompt(
        prompt_template,
        date=date,
        bio=bio,
        calendars=str(calendars),
        tasks=str(tasks),
        emails=str(emails),
        journals=str(journals),
        extras=str(extras),
        slack=str(slack) if slack else ""
    )

    if debug:
        logger.debug("========== BEGIN PROMPT ==========")
        logger.debug(prompt)
        logger.debug("=========== END PROMPT ===========")

    return run_llm_prompt(prompt, model)


def summarize_weekly(
    model: str,   
    journals: str,
    extras: str,
    bio: str = "",
    quiet: bool = False,
    debug: bool = False,
) -> str:
    template = load_prompt_template(APP_WEEKLY_PROMPT_PATH)
    prompt = template.format(journals=(journals), extras=(extras), bio=bio)

    if debug:
        logger.debug("========== BEGIN PROMPT ==========")
        logger.debug(prompt)
        logger.debug("=========== END PROMPT ===========")

    return run_llm_prompt(prompt, model)
