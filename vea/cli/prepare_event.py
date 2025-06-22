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
from ..utils.output_utils import resolve_output_path
from ..utils.error_utils import enable_debug_logging, handle_exception
from ..utils.summarization import summarize_event_preparation
from ..utils.slack_utils import send_slack_dm
from ..utils.pdf_utils import convert_markdown_to_pdf
from ..utils.generic_utils import check_required_directories

app = typer.Typer()


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
    use_embeddings: bool = typer.Option(False, help="Use embeddings-based retrieval"),
    outliner_mode: bool = typer.Option(False, help="Split journals by top-level bullets"),
    topk_journals: int = typer.Option(5, help="Top K journal passages"),
    topk_extras: int = typer.Option(5, help="Top K extras passages"),
    topk_emails: int = typer.Option(5, help="Top K email passages"),
    topk_slack: int = typer.Option(5, help="Top K Slack passages"),
    slack_dm: bool = typer.Option(False, help="Send the output as a DM to yourself on Slack"),
    save_markdown: bool = typer.Option(True, help="Save output to Markdown file"),
    save_pdf: bool = typer.Option(False, help="Save output to PDF file"),
    save_path: Optional[Path] = typer.Option(None, help="Custom file path or directory to save the output"),
    prompt_file: Optional[Path] = typer.Option(None, help="Path to custom prompt file"),
    model: str = typer.Option("gemini-2.5-pro", help="Model to use for summarization"),
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
        bio = os.getenv("BIO", "")

        summary = summarize_event_preparation(
            model=model,
            events=events,
            journals=journals_data,
            extras=extras_data,
            emails=emails,
            tasks=tasks,
            slack=slack_data,
            bio=bio,
            prompt_path=prompt_path,
            quiet=quiet,
            debug=debug,
            use_embeddings=use_embeddings,
            outliner_mode=outliner_mode,
            topk_journals=topk_journals,
            topk_extras=topk_extras,
            topk_emails=topk_emails,
            topk_slack=topk_slack,
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
