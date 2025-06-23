import logging
import json
import re
from datetime import date
from pathlib import Path
from typing import Any, List, Dict, Optional, Union, Tuple

from vea.utils.llm_utils import run_llm_prompt
from vea.utils.embedding_utils import (
    load_or_create_index,
    query_index,
    INDEX_DIR,
)

logger = logging.getLogger(__name__)

APP_ROOT = Path(__file__).resolve().parents[2]
PROMPT_TEMPLATE_PATH = APP_ROOT / "vea" / "prompts" / "daily-default.prompt"
APP_WEEKLY_PROMPT_PATH = APP_ROOT / "vea/prompts/weekly-default.prompt"
APP_PREPARE_EVENT_PROMPT_PATH = APP_ROOT / "vea/prompts/prepare-event.prompt"
APP_CHECK_FOR_TASKS_PROMPT_PATH = APP_ROOT / "vea/prompts/check-for-tasks-default.prompt"


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


def _split_bullets(text: str) -> List[str]:
    """Split Markdown text into top-level bullet blocks."""
    parts: List[str] = []
    current: List[str] = []
    for line in text.splitlines():
        if re.match(r"^[*-]\s+", line):
            if current:
                parts.append("\n".join(current).strip())
                current = []
        current.append(line)
    if current:
        parts.append("\n".join(current).strip())
    return [p for p in parts if p.strip()]


def _dedupe_dicts(items: List[dict]) -> List[dict]:
    seen = set()
    result = []
    for item in items:
        key = json.dumps(item, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result

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
    use_embeddings: bool = False,
    outliner_mode: bool = False,
    topk_journals: int = 5,
    topk_extras: int = 5,
    topk_emails: int = 5,
    topk_slack: int = 5,
) -> str:

    prompt_template = load_prompt_template(prompt_path)

    if use_embeddings:
        journal_docs: List[Tuple[str, dict]] = []
        for entry in journals:
            content = entry.get("content", "")
            if outliner_mode:
                for idx, part in enumerate(_split_bullets(content), 1):
                    doc = {
                        "filename": f"{entry.get('filename')}-{idx}",
                        "date": entry.get("date"),
                        "content": part,
                    }
                    journal_docs.append((part, doc))
            else:
                journal_docs.append((content, entry))

        extras_docs: List[Tuple[str, dict]] = []
        for e in extras:
            extras_docs.append((e.get("content", ""), e))

        email_docs: List[Tuple[str, dict]] = []
        for msgs in emails.values():
            for m in msgs:
                text = f"{m.get('subject','')} {m.get('body','')}"
                email_docs.append((text, m))

        slack_docs: List[Tuple[str, dict]] = []
        if slack:
            for msgs in slack.values():
                for m in msgs:
                    slack_docs.append((m.get("text", ""), dict(m)))
                    for r in m.get("replies", []):
                        slack_docs.append((r.get("text", ""), dict(r)))

        journal_index = load_or_create_index(INDEX_DIR / "journals.index", journal_docs, debug=debug)
        extras_index = load_or_create_index(INDEX_DIR / "extras.index", extras_docs, debug=debug)
        email_index = load_or_create_index(INDEX_DIR / "emails.index", email_docs, debug=debug)
        slack_index = load_or_create_index(INDEX_DIR / "slack.index", slack_docs, debug=debug)

        journals_hits: List[dict] = []
        extras_hits: List[dict] = []
        emails_hits: List[dict] = []
        slack_hits: List[dict] = []

        def _accumulate(query: str) -> None:
            journals_hits.extend(query_index(journal_index, query, topk_journals))
            extras_hits.extend(query_index(extras_index, query, topk_extras))
            emails_hits.extend(query_index(email_index, query, topk_emails))
            slack_hits.extend(query_index(slack_index, query, topk_slack))

        for event in calendars:
            q = " ".join([
                event.get("summary", ""),
                event.get("description", ""),
                " ".join(a.get("email", "") for a in event.get("attendees", [])),
            ])
            _accumulate(q)

        for task in tasks:
            q = f"{task.get('content','')} {task.get('description','')}"
            _accumulate(q)

        slack_grouped: Dict[str, List[dict]] = {}
        for item in _dedupe_dicts(slack_hits):
            ch = item.get("channel", "unknown")
            slack_grouped.setdefault(ch, []).append(item)

        prompt = render_daily_prompt(
            prompt_template,
            date=date,
            bio=bio,
            calendars=json.dumps(calendars, indent=2, default=str, ensure_ascii=False),
            tasks=json.dumps(tasks, indent=2, default=str, ensure_ascii=False),
            emails=json.dumps(_dedupe_dicts(emails_hits), indent=2, default=str, ensure_ascii=False),
            journals=json.dumps(_dedupe_dicts(journals_hits), indent=2, default=str, ensure_ascii=False),
            extras=json.dumps(_dedupe_dicts(extras_hits), indent=2, default=str, ensure_ascii=False),
            slack=json.dumps(slack_grouped, indent=2, default=str, ensure_ascii=False) if slack else "",
        )
    else:
        prompt = render_daily_prompt(
            prompt_template,
            date=date,
            bio=bio,
            calendars=json.dumps(calendars, indent=2, default=str, ensure_ascii=False),
            tasks=json.dumps(tasks, indent=2, default=str, ensure_ascii=False),
            emails=json.dumps(emails, indent=2, default=str, ensure_ascii=False),
            journals=json.dumps(journals, indent=2, default=str, ensure_ascii=False),
            extras=json.dumps(extras, indent=2, default=str, ensure_ascii=False),
            slack=json.dumps(slack, indent=2, default=str, ensure_ascii=False) if slack else "",
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
    use_embeddings: bool = False,
    outliner_mode: bool = False,
    topk_journals: int = 5,
    topk_extras: int = 5,
    topk_emails: int = 5,
    topk_slack: int = 5,
) -> str:
    """Summarize last-minute insights for upcoming events."""

    template = load_prompt_template(prompt_path or APP_PREPARE_EVENT_PROMPT_PATH)

    if use_embeddings:
        journal_docs: List[Tuple[str, dict]] = []
        for entry in journals:
            content = entry.get("content", "")
            if outliner_mode:
                for idx, part in enumerate(_split_bullets(content), 1):
                    doc = {
                        "filename": f"{entry.get('filename')}-{idx}",
                        "date": entry.get("date"),
                        "content": part,
                    }
                    journal_docs.append((part, doc))
            else:
                journal_docs.append((content, entry))

        extras_docs: List[Tuple[str, dict]] = []
        for e in extras:
            extras_docs.append((e.get("content", ""), e))

        email_docs: List[Tuple[str, dict]] = []
        for msgs in emails.values():
            for m in msgs:
                text = f"{m.get('subject','')} {m.get('body','')}"
                email_docs.append((text, m))

        slack_docs: List[Tuple[str, dict]] = []
        if slack:
            for msgs in slack.values():
                for m in msgs:
                    slack_docs.append((m.get("text", ""), dict(m)))
                    for r in m.get("replies", []):
                        slack_docs.append((r.get("text", ""), dict(r)))

        journal_index = load_or_create_index(INDEX_DIR / "journals.index", journal_docs, debug=debug)
        extras_index = load_or_create_index(INDEX_DIR / "extras.index", extras_docs, debug=debug)
        email_index = load_or_create_index(INDEX_DIR / "emails.index", email_docs, debug=debug)
        slack_index = load_or_create_index(INDEX_DIR / "slack.index", slack_docs, debug=debug)

        journals_hits: List[dict] = []
        extras_hits: List[dict] = []
        emails_hits: List[dict] = []
        slack_hits: List[dict] = []

        def _accumulate(query: str) -> None:
            journals_hits.extend(query_index(journal_index, query, topk_journals))
            extras_hits.extend(query_index(extras_index, query, topk_extras))
            emails_hits.extend(query_index(email_index, query, topk_emails))
            slack_hits.extend(query_index(slack_index, query, topk_slack))

        for event in events:
            q = " ".join([
                event.get("summary", ""),
                event.get("description", ""),
                " ".join(a.get("email", "") for a in event.get("attendees", [])),
            ])
            _accumulate(q)

        for task in tasks:
            q = f"{task.get('content','')} {task.get('description','')}"
            _accumulate(q)

        slack_grouped: Dict[str, List[dict]] = {}
        for item in _dedupe_dicts(slack_hits):
            ch = item.get("channel", "unknown")
            slack_grouped.setdefault(ch, []).append(item)

        prompt = template.format(
            bio=bio,
            events=json.dumps(events, indent=2, default=str, ensure_ascii=False),
            journals=json.dumps(_dedupe_dicts(journals_hits), indent=2, default=str, ensure_ascii=False),
            extras=json.dumps(_dedupe_dicts(extras_hits), indent=2, default=str, ensure_ascii=False),
            emails=json.dumps(_dedupe_dicts(emails_hits), indent=2, default=str, ensure_ascii=False),
            tasks=json.dumps(tasks, indent=2, default=str, ensure_ascii=False),
            slack=json.dumps(slack_grouped, indent=2, default=str, ensure_ascii=False) if slack else "",
        )
    else:
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
