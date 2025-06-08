"""Helpers for constructing prompts and calling the LLM."""

import logging
import json
from datetime import date
from pathlib import Path
from typing import List, Dict, Optional, Union

from vea.utils.llm_utils import run_llm_prompt

logger = logging.getLogger(__name__)

APP_ROOT = Path(__file__).resolve().parents[2]
PROMPT_TEMPLATE_PATH = APP_ROOT / "vea" / "prompts" / "daily-default.prompt"
APP_WEEKLY_PROMPT_PATH = APP_ROOT / "vea/prompts/weekly-default.prompt"
APP_PREPARE_EVENT_PROMPT_PATH = APP_ROOT / "vea/prompts/prepare-event.prompt"
APP_CHECK_FOR_TASKS_PROMPT_PATH = APP_ROOT / "vea/prompts/check-for-tasks-default.prompt"


def load_prompt_template(path: Optional[Path] = None) -> str:
    """Return the text of the prompt template located at ``path``."""
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
    """Fill ``template`` with the provided serialized data chunks."""
    return template.format(
        date=str(date),
        bio=bio,
        calendars=calendars,
        tasks=tasks,
        emails=emails,
        journals=journals,
        extras=extras,
        slack=slack,
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
    prompt_path: Optional[Path] = None,
) -> str:
    """Render and submit the daily prompt with the selected model."""

    prompt_template = load_prompt_template(prompt_path)
    prompt = render_daily_prompt(
        prompt_template,
        date=date,
        bio=bio,
        calendars=json.dumps(calendars, indent=2, default=str, ensure_ascii=False),
        tasks=json.dumps(tasks, indent=2, default=str, ensure_ascii=False),
        emails=json.dumps(emails, indent=2, default=str, ensure_ascii=False),
        journals=json.dumps(journals, indent=2, default=str, ensure_ascii=False),
        extras=json.dumps(extras, indent=2, default=str, ensure_ascii=False),
        slack=json.dumps(slack, indent=2, default=str, ensure_ascii=False) if slack else ""
    )



    if debug and not quiet:
        logger.debug("========== BEGIN PROMPT ==========")
        logger.debug(prompt)
        logger.debug("=========== END PROMPT ===========")

    return run_llm_prompt(prompt, model, quiet=quiet)


def summarize_weekly(
    model: str,
    week: str,
    journals_in_week: List,
    journals_contextual: List,
    extras: List,
    bio: str = "",
    quiet: bool = False,
    debug: bool = False,
    prompt_path: Optional[Path] = None,
) -> str:
    """Produce a narrative summary for the specified week."""

    template = load_prompt_template(prompt_path or APP_WEEKLY_PROMPT_PATH)
    prompt = template.format(
        week=week,
        journals_in_week=json.dumps(journals_in_week, indent=2, default=str, ensure_ascii=False),
        journals_contextual=json.dumps(journals_contextual, indent=2, default=str, ensure_ascii=False),
        extras=json.dumps(extras, indent=2, default=str, ensure_ascii=False),
        bio=bio
    )

    if debug and not quiet:
        logger.debug("========== BEGIN PROMPT ==========")
        logger.debug(prompt)
        logger.debug("=========== END PROMPT ===========")

    return run_llm_prompt(prompt, model, quiet=quiet)


def summarize_event_preparation(
    model: str,
    events: List[dict],
    journals: List,
    extras: List,
    emails: Dict,
    tasks: List,
    slack: Optional[Dict[str, List[Dict[str, str]]]] = None,
    bio: str = "",
    quiet: bool = False,
    debug: bool = False,
    prompt_path: Optional[Path] = None,
) -> str:
    """Summarize last-minute insights for upcoming events."""

    template = load_prompt_template(prompt_path or APP_PREPARE_EVENT_PROMPT_PATH)
    prompt = template.format(
        bio=bio,
        events=json.dumps(events, indent=2, default=str, ensure_ascii=False),
        journals=json.dumps(journals, indent=2, default=str, ensure_ascii=False),
        extras=json.dumps(extras, indent=2, default=str, ensure_ascii=False),
        emails=json.dumps(emails, indent=2, default=str, ensure_ascii=False),
        tasks=json.dumps(tasks, indent=2, default=str, ensure_ascii=False),
        slack=json.dumps(slack, indent=2, default=str, ensure_ascii=False) if slack else "",
    )

    if debug and not quiet:
        logger.debug("========== BEGIN PROMPT ==========")
        logger.debug(prompt)
        logger.debug("=========== END PROMPT ===========")

    return run_llm_prompt(prompt, model, quiet=quiet)


def summarize_check_for_tasks(
    model: str,
    journals: List,
    emails: Dict,
    completed_tasks: List,
    open_tasks: List,
    slack: Optional[Dict[str, List[Dict[str, str]]]] = None,
    bio: str = "",
    quiet: bool = False,
    debug: bool = False,
    prompt_path: Optional[Path] = None,
) -> str:
    """Identify potentially forgotten or uncaptured tasks."""

    template = load_prompt_template(prompt_path or APP_CHECK_FOR_TASKS_PROMPT_PATH)
    prompt = template.format(
        bio=bio,
        journals=json.dumps(journals, indent=2, default=str, ensure_ascii=False),
        emails=json.dumps(emails, indent=2, default=str, ensure_ascii=False),
        completed_tasks=json.dumps(completed_tasks, indent=2, default=str, ensure_ascii=False),
        open_tasks=json.dumps(open_tasks, indent=2, default=str, ensure_ascii=False),
        slack=json.dumps(slack, indent=2, default=str, ensure_ascii=False) if slack else "",
    )

    if debug and not quiet:
        logger.debug("========== BEGIN PROMPT ==========")
        logger.debug(prompt)
        logger.debug("=========== END PROMPT ===========")

    return run_llm_prompt(prompt, model, quiet=quiet)
