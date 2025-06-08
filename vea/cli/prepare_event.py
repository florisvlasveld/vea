import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo

import typer

from ..loaders import gcal, gmail, journals, extras, todoist, slack as slack_loader
from ..utils.event_utils import (
    parse_event_dt,
    find_upcoming_events,
    find_current_events,
)
from ..utils.filtering import run_pipeline

import logging
from ..utils.output_utils import resolve_output_path
from ..utils.error_utils import enable_debug_logging, handle_exception
from ..utils.summarization import summarize_event_preparation
from ..utils.slack_utils import send_slack_dm
from ..utils.pdf_utils import convert_markdown_to_pdf
from ..utils.generic_utils import check_required_directories

app = typer.Typer()
logger = logging.getLogger(__name__)


@app.command("prepare-event")
def prepare_event(
    event: Optional[str] = typer.Option(
        None,
        help=(
            "When to prepare for: a start time like '2025-05-28 14:00', "
            "'now' for the current meeting, or 'next' for the next one"
        ),
    ),
    lookahead_minutes: Optional[int] = typer.Option(None, help="Number of minutes to look ahead for upcoming events"),
    journal_dir: Optional[Path] = typer.Option(None, help="Directory with Markdown journal files"),
    journal_days: int = typer.Option(5, help="Number of past days of journals to include"),
    extras_dir: Optional[Path] = typer.Option(None, help="Directory with additional Markdown files"),
    gmail_labels: Optional[List[str]] = typer.Option(None, help="List of additional Gmail labels to fetch emails from"),
    todoist_project: Optional[str] = typer.Option(None, help="Name of the Todoist project to filter tasks by"),
    my_email: Optional[str] = typer.Option(None, help="Your email address to filter declined calendar events"),
    include_slack: bool = typer.Option(True, help="Include recent Slack messages"),
    calendar_blacklist: Optional[List[str]] = typer.Option(
        None,
        help="Comma-separated list of keywords to blacklist from calendar events (overrides CALENDAR_EVENT_BLACKLIST)",
    ),
    slack_days: int = typer.Option(
        3,
        help="Number of past days of Slack messages to load",
    ),
    slack_dm: bool = typer.Option(False, help="Send the output as a DM to yourself on Slack"),
    save_markdown: bool = typer.Option(True, help="Save output to Markdown file"),
    save_pdf: bool = typer.Option(False, help="Save output to PDF file"),
    save_path: Optional[Path] = typer.Option(None, help="Custom file path or directory to save the output"),
    prompt_file: Optional[Path] = typer.Option(None, help="Path to custom prompt file"),
    model: str = typer.Option("gemini-2.5-pro-preview-06-05", help="Model to use for summarization"),
    token_budget: int = typer.Option(10000, help="Token budget for filtering contextual documents"),
    focus_topics_override: Optional[List[str]] = typer.Option(None, help="Override focus topics for filtering"),
    skip_path_checks: bool = typer.Option(False, help="Skip checks for existence of input and output paths"),
    debug: bool = typer.Option(False, help="Enable debug logging"),
    quiet: bool = typer.Option(False, help="Suppress output to stdout"),
) -> None:

    if debug:
        enable_debug_logging()

    if not skip_path_checks:
        check_required_directories(journal_dir, extras_dir, save_path)

    prompt_path = prompt_file or Path(__file__).parent.parent / "prompts" / "prepare-event.prompt"
    if not prompt_path.is_file():
        typer.echo(f"Error: Default prompt file does not exist: {prompt_path}", err=True)
        raise typer.Exit(code=1)

    try:
        tz = ZoneInfo(os.getenv("TIMEZONE", "Europe/Amsterdam"))
        now = datetime.now(tz)

        if event:
            key = event.strip().lower()
            if key == "next":
                events = find_upcoming_events(
                    start=now,
                    my_email=my_email,
                    blacklist=calendar_blacklist,
                    lookahead_minutes=lookahead_minutes,
                )
            elif key == "now":
                events = find_current_events(
                    my_email=my_email,
                    blacklist=calendar_blacklist,
                )
            else:
                start_dt = parse_event_dt(event)
                events = find_upcoming_events(
                    start=start_dt,
                    my_email=my_email,
                    blacklist=calendar_blacklist,
                    lookahead_minutes=lookahead_minutes,
                )
        else:
            events = find_upcoming_events(
                start=now,
                my_email=my_email,
                blacklist=calendar_blacklist,
                lookahead_minutes=lookahead_minutes,
            )

        if not events:
            typer.echo("No upcoming events found", err=True)
            raise typer.Exit(code=1)

        extras_data = extras.load_extras([extras_dir] if extras_dir else [])
        alias_map = extras.build_alias_map(extras_data)
        journals_data = (
            journals.load_journals(
                journal_dir,
                journal_days=journal_days,
                alias_map=alias_map,
            )
            if journal_dir
            else []
        )
        emails = gmail.load_emails(now.date(), gmail_labels=gmail_labels)
        first_dt = datetime.fromisoformat(events[0]["start"])
        if first_dt.tzinfo is None:
            first_dt = first_dt.replace(tzinfo=tz)
        tasks = todoist.load_tasks(first_dt.date(), todoist_project=todoist_project or "")
        slack_data = (
            slack_loader.load_slack_messages(days_lookback=slack_days)
            if include_slack
            else {}
        )
        focus_topics: List[str] = []
        for ev in events:
            logger.debug(
                "Event: summary=%s desc=%s", ev.get("summary"), ev.get("description")
            )
            if ev.get("summary"):
                focus_topics.append(ev["summary"])
            if ev.get("description"):
                focus_topics.append(ev["description"])
            for at in ev.get("attendees", []):
                for key in ("name", "displayName", "email"):
                    val = at.get(key)
                    if val:
                        focus_topics.append(val)
            org = ev.get("organizer", {})
            for key in ("displayName", "email"):
                val = org.get(key)
                if val:
                    focus_topics.append(val)
        focus_topics.extend(alias_map.keys())
        if focus_topics_override:
            focus_topics = list(focus_topics_override)

        logger.debug("Focus topics: %s", focus_topics)

        def _filter_group(name: str, docs: List[dict]) -> List[dict]:
            if not docs:
                logger.warning("No %s documents to filter", name)
                return []
            result = run_pipeline(
                docs,
                focus_topics,
                token_budget=token_budget,
                return_scores=debug,
            )
            logger.debug(
                "%s docs before=%d after=%d tokens=%d",
                name,
                len(docs),
                len(result["documents"]),
                result["total_tokens"],
            )
            for d in result["documents"]:
                logger.debug(
                    "%s kept %s score=%.2f tokens=%d",
                    name,
                    d["id"],
                    d.get("combined_score", 0.0),
                    d["token_count"],
                )
            if not result["documents"]:
                logger.warning("No %s documents retained after filtering", name)
            return [d["original"] for d in result["documents"]]

        journal_docs = [
            {"id": j["filename"], "type": "journal", "content": j["content"], "metadata": {"date": str(j.get("date"))}, "original": j}
            for j in journals_data
        ]
        extras_docs = [
            {"id": e["filename"], "type": "extra", "content": e["content"], "metadata": {"aliases": e.get("aliases", [])}, "original": e}
            for e in extras_data
        ]
        email_docs = [
            {
                "id": f"{label}-{i}",
                "type": "email",
                "content": f"{m.get('subject','')} {m.get('body','')}",
                "metadata": {**m, "label": label},
                "original": m,
            }
            for label, msgs in emails.items()
            for i, m in enumerate(msgs)
        ]
        slack_docs = [
            {
                "id": f"{chan}-{i}",
                "type": "slack",
                "content": msg.get("text", "") + " " + " ".join(r.get("text", "") for r in msg.get("replies", [])),
                "metadata": {**msg, "channel": chan},
                "original": msg,
            }
            for chan, msgs in slack_data.items()
            for i, msg in enumerate(msgs)
        ]

        filtered_journals = _filter_group("journal", journal_docs)
        filtered_extras = _filter_group("extra", extras_docs)
        filtered_email_docs = _filter_group("email", email_docs)
        filtered_slack_docs = _filter_group("slack", slack_docs)

        filtered_emails: dict[str, List[dict]] = {}
        for d in filtered_email_docs:
            label = d.get("label", "inbox")
            filtered_emails.setdefault(label, []).append(d)

        filtered_slack: dict[str, List[dict]] = {}
        for d in filtered_slack_docs:
            chan = d.get("channel", "")
            filtered_slack.setdefault(chan, []).append(d)

        bio = os.getenv("BIO", "")

        summary = summarize_event_preparation(
            model=model,
            events=events,
            journals=filtered_journals,
            extras=filtered_extras,
            emails=filtered_emails,
            tasks=tasks,
            slack=filtered_slack,
            bio=bio,
            prompt_path=prompt_path,
            quiet=quiet,
            debug=debug,
        )

        if not quiet:
            print(summary)

        if slack_dm:
            send_slack_dm(summary, quiet=quiet)

        if save_markdown or save_pdf:
            first_dt = datetime.fromisoformat(events[0]["start"])
            if first_dt.tzinfo is None:
                first_dt = first_dt.replace(tzinfo=tz)
            filename = first_dt.strftime("%Y-%m-%d_%H%M_event.md")
            out_path = resolve_output_path(save_path, first_dt.date(), custom_filename=filename)

        if save_markdown:
            out_path.write_text(summary)

        if save_pdf:
            convert_markdown_to_pdf(summary, out_path.with_suffix(".pdf"), debug=debug)

    except Exception as e:
        handle_exception(e)
