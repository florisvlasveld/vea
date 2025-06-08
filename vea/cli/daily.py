import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import logging

import typer

from ..loaders import gcal, gmail, journals, extras, todoist, slack as slack_loader
from ..loaders.journals import load_journals
from ..loaders.extras import load_extras
from ..utils.date_utils import parse_date
from ..utils.output_utils import resolve_output_path
from ..utils.error_utils import enable_debug_logging, handle_exception
from ..utils.summarization import summarize_daily
from ..utils.filtering import run_pipeline
from ..utils.slack_utils import send_slack_dm
from ..utils.pdf_utils import convert_markdown_to_pdf
from ..utils.generic_utils import check_required_directories

app = typer.Typer()
logger = logging.getLogger(__name__)


@app.command("daily")
def generate(
    date: str = typer.Option(
        datetime.today().strftime("%Y-%m-%d"), help="Date for the brief (YYYY-MM-DD)"
    ),
    journal_dir: Optional[Path] = typer.Option(None, help="Directory with Markdown journal files"),
    journal_days: int = typer.Option(21, help="Number of past days of journals to include"),
    extras_dir: Optional[Path] = typer.Option(None, help="Directory with additional Markdown files"),
    gmail_labels: Optional[List[str]] = typer.Option(None, help="List of additional Gmail labels to fetch emails from"),
    todoist_project: Optional[str] = typer.Option(None, help="Name of the Todoist project to filter tasks by"),
    my_email: Optional[str] = typer.Option(None, help="Your email address to filter declined calendar events"),
    include_slack: bool = typer.Option(True, help="Include recent Slack messages"),
    slack_days: int = typer.Option(
        slack_loader.DEFAULT_DAYS_LOOKBACK,
        help="Number of past days of Slack messages to load",
    ),
    calendar_blacklist: Optional[List[str]] = typer.Option(
        None,
        help="Comma-separated list of keywords to blacklist from calendar events (overrides CALENDAR_EVENT_BLACKLIST)"
    ),
    skip_past_events: bool = typer.Option(
        False,
        help="Skip calendar events earlier than the current time when generating today's brief",
    ),
    save_markdown: bool = typer.Option(True, help="Save output to Markdown file"),
    save_pdf: bool = typer.Option(False, help="Save output to PDF file"),
    save_path: Optional[Path] = typer.Option(None, help="Custom file path or directory to save the output"),
    prompt_file: Optional[Path] = typer.Option(None, help="Path to custom prompt file"),
    model: str = typer.Option(
        "gemini-2.5-pro-preview-06-05", help="Model to use for summarization (OpenAI, Google Gemini, or Anthropic)"
    ),
    token_budget: int = typer.Option(10000, help="Token budget for filtering contextual documents"),
    budget_scope: str = typer.Option(
        "global",
        help="How to apply the token budget: 'global' for all docs combined or 'group' per source",
    ),
    focus_topics_override: Optional[List[str]] = typer.Option(None, help="Override focus topics for filtering"),
    skip_path_checks: bool = typer.Option(False, help="Skip checks for existence of input and output paths"),
    debug: bool = typer.Option(False, help="Enable debug logging"),
    quiet: bool = typer.Option(False, help="Suppress output to stdout"),
) -> None:

    if debug:
        enable_debug_logging()

    if not skip_path_checks:
        check_required_directories(journal_dir, extras_dir, save_path)

    prompt_path = prompt_file or Path(__file__).parent.parent / "prompts" / "daily-default.prompt"
    if not prompt_path.is_file():
        typer.echo(f"Error: Default prompt file does not exist: {prompt_path}", err=True)
        raise typer.Exit(code=1)

    try:
        target_date = parse_date(date)
        extras_data = extras.load_extras([extras_dir] if extras_dir else [])
        alias_map = extras.build_alias_map(extras_data)
        journals_data = (
            journals.load_journals(
                journal_dir,
                journal_days=journal_days,
                alias_map=alias_map,
                target_date=target_date,
            )
            if journal_dir
            else []
        )
        calendars = gcal.load_events(
            target_date,
            my_email=my_email,
            blacklist=calendar_blacklist,
            skip_past_events=skip_past_events,
        )
        tasks = todoist.load_tasks(target_date, todoist_project=todoist_project or "")
        emails = gmail.load_emails(target_date, gmail_labels=gmail_labels)
        slack_data = (
            slack_loader.load_slack_messages(days_lookback=slack_days)
            if include_slack
            else {}
        )

        # --- Build focus topics from events and tasks ---
        focus_topics: List[str] = []
        for ev in calendars:
            if ev.get("summary"):
                focus_topics.append(ev["summary"])
            if ev.get("description"):
                focus_topics.append(ev["description"])
            for att in ev.get("attendees", []):
                if att.get("name"):
                    focus_topics.append(att["name"])
                if att.get("email"):
                    focus_topics.append(att["email"])
        for task in tasks:
            focus_topics.append(task["content"])
            if task.get("description"):
                focus_topics.append(task["description"])
        # boost with known aliases
        focus_topics.extend(alias_map.keys())
        if focus_topics_override:
            focus_topics = list(focus_topics_override)

        logger.debug("Focus topics: %s", focus_topics)

        # --- Helper to filter a single group of documents ---
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
            return result["documents"]

        # --- Build document dictionaries and filter ---
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

        if budget_scope.lower() == "group":
            filtered_journals = [d["original"] for d in _filter_group("journal", journal_docs)]
            filtered_extras = [d["original"] for d in _filter_group("extra", extras_docs)]
            _email_results = _filter_group("email", email_docs)
            _slack_results = _filter_group("slack", slack_docs)
        else:
            all_docs = journal_docs + extras_docs + email_docs + slack_docs
            result = run_pipeline(all_docs, focus_topics, token_budget=token_budget, return_scores=debug)
            logger.debug(
                "All docs before=%d after=%d tokens=%d",
                len(all_docs),
                len(result["documents"]),
                result["total_tokens"],
            )
            _email_results = []
            _slack_results = []
            filtered_journals = []
            filtered_extras = []
            for d in result["documents"]:
                logger.debug(
                    "%s kept %s score=%.2f tokens=%d",
                    d["type"],
                    d["id"],
                    d.get("combined_score", 0.0),
                    d["token_count"],
                )
                if d["type"] == "journal":
                    filtered_journals.append(d["original"])
                elif d["type"] == "extra":
                    filtered_extras.append(d["original"])
                elif d["type"] == "email":
                    _email_results.append(d)
                elif d["type"] == "slack":
                    _slack_results.append(d)
            if not result["documents"]:
                logger.warning("No documents retained after filtering")

        filtered_emails: dict[str, List[dict]] = {}
        for d in _email_results:
            label = d["metadata"].get("label", "inbox")
            filtered_emails.setdefault(label, []).append(d["original"])

        filtered_slack: dict[str, List[dict]] = {}
        for d in _slack_results:
            chan = d["metadata"].get("channel", "")
            filtered_slack.setdefault(chan, []).append(d["original"])

        if not filtered_journals:
            logger.warning("No journal documents retained after filtering")
        if not filtered_extras:
            logger.warning("No extra documents retained after filtering")
        if all(len(v) == 0 for v in filtered_emails.values()):
            logger.warning("No email documents retained after filtering")
        if all(len(v) == 0 for v in filtered_slack.values()):
            logger.warning("No Slack messages retained after filtering")

        bio = os.getenv("BIO", "")

        summary = summarize_daily(
            model=model,
            date=target_date,
            emails=filtered_emails,
            calendars=calendars,
            tasks=tasks,
            journals=filtered_journals,
            extras=filtered_extras,
            slack=filtered_slack,
            bio=bio,
            prompt_path=prompt_path,
            quiet=quiet,
            debug=debug,
        )

        if not quiet:
            print(summary)

        if save_markdown or save_pdf:
            out_path = resolve_output_path(save_path, target_date)

        if save_markdown:
            out_path.write_text(summary)

        if save_pdf:
            pdf_path = out_path.with_suffix(".pdf")
            convert_markdown_to_pdf(summary, pdf_path, debug=debug)

    except Exception as e:
        handle_exception(e)
