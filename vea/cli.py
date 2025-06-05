import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import typer
from dotenv import load_dotenv

from vea.loaders import gcal, gmail, journals, extras, todoist, slack as slack_loader
from vea.loaders.journals import load_journals
from vea.loaders.extras import load_extras
from vea.auth import authorize

from vea.utils.date_utils import parse_date, parse_week_input
from vea.utils.event_utils import parse_event_dt, find_upcoming_events
from vea.utils.output_utils import resolve_output_path
from vea.utils.error_utils import enable_debug_logging, handle_exception
from vea.utils.summarization import (
    summarize_daily,
    summarize_weekly,
    summarize_event_preparation,
)
from zoneinfo import ZoneInfo
from vea.utils.slack_utils import send_slack_dm
from vea.utils.pdf_utils import convert_markdown_to_pdf
from vea.utils.generic_utils import check_required_directories


app = typer.Typer(help="Vea: Generate a personalized daily briefing or weekly summary.")

load_dotenv()


def _find_upcoming_events(
    *,
    start: datetime,
    my_email: Optional[str],
    blacklist: Optional[List[str]],
    lookahead_minutes: Optional[int] = None,
) -> List[dict]:
    """Wrapper for :func:`find_upcoming_events` to allow easier testing."""
    if blacklist is None:
        env_bl = os.getenv("CALENDAR_EVENT_BLACKLIST", "")
        blacklist = [b.strip() for b in env_bl.split(",") if b.strip()]

    return find_upcoming_events(
        start=start,
        my_email=my_email,
        blacklist=blacklist,
        lookahead_minutes=lookahead_minutes,
    )


@app.command("auth")
def auth_command(
    scopes: List[str] = typer.Argument(..., help="Services to authorize (e.g., `calendar gmail`)")
) -> None:
    try:
        authorize(scopes)
    except Exception as e:
        handle_exception(e)


@app.command("daily")
def generate(
    date: str = typer.Option(datetime.today().strftime("%Y-%m-%d"), help="Date for the brief (YYYY-MM-DD)"),
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
    model: str = typer.Option("gemini-2.5-pro-preview-05-06", help="Model to use for summarization (OpenAI, Google Gemini, or Anthropic)"),
    skip_path_checks: bool = typer.Option(False, help="Skip checks for existence of input and output paths"),
    debug: bool = typer.Option(False, help="Enable debug logging"),
    quiet: bool = typer.Option(False, help="Suppress output to stdout"),
) -> None:

    if debug:
        enable_debug_logging()

    if not skip_path_checks:
        check_required_directories(journal_dir, extras_dir, save_path)

    prompt_path = prompt_file or Path(__file__).parent / "prompts" / "daily-default.prompt"
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
        bio = os.getenv("BIO", "")

        summary = summarize_daily(
            model=model,
            date=target_date,
            emails=emails,
            calendars=calendars,
            tasks=tasks,
            journals=journals_data,
            extras=extras_data,
            slack=slack_data,
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


@app.command("weekly")
def generate_weekly_summary(
    week: str = typer.Option(datetime.today().strftime("%Y-%m-%d"), help="Week (e.g., 2025-W22, 2025-22, 22, or 2025-05-28)"),
    journal_dir: Optional[Path] = typer.Option(None, help="Directory with Markdown journal files"),
    journal_days: int = typer.Option(21, help="Number of past days of journals to include"),
    extras_dir: Optional[Path] = typer.Option(None, help="Directory with additional Markdown files"),
    save_markdown: bool = typer.Option(True, help="Save output as markdown file."),
    save_pdf: bool = typer.Option(False, help="Save output as PDF."),
    save_path: Optional[Path] = typer.Option(None, help="Optional override path to save output."),
    prompt_file: Optional[Path] = typer.Option(None, help="Path to custom prompt file"),
    model: str = typer.Option("gemini-2.5-pro-preview-05-06", help="Model to use for summarization (OpenAI, Google Gemini, or Anthropic)"),
    skip_path_checks: bool = typer.Option(False, help="Skip path existence checks."),
    debug: bool = typer.Option(False, help="Enable debug logging"),
    quiet: bool = typer.Option(False, help="Suppress output to stdout"),
):
    if debug:
        enable_debug_logging()

    if not skip_path_checks:
        check_required_directories(journal_dir, extras_dir, save_path)

    prompt_path = prompt_file or Path(__file__).parent / "prompts" / "weekly-default.prompt"
    if not prompt_path.is_file():
        typer.echo(f"Error: Default prompt file does not exist: {prompt_path}", err=True)
        raise typer.Exit(code=1)

    try:
        week_start, week_end = parse_week_input(week)
        extras_paths = [Path(extras_dir)] if extras_dir else []
        all_extras = load_extras(extras_paths)
        alias_map = extras.build_alias_map(all_extras)

        all_journals = load_journals(
            journal_dir,
            journal_days=journal_days,
            alias_map=alias_map,
            latest_date=week_end  # <-- this ensures future entries are excluded
        )

        def journal_in_week(entry: dict) -> bool:
            return "date" in entry and week_start <= entry["date"] <= week_end

        journals_in_week = [e for e in all_journals if journal_in_week(e)]
        journals_contextual = [e for e in all_journals if not journal_in_week(e)]
        extras_data = all_extras
        bio = os.getenv("BIO", "")

        summary = summarize_weekly(
            model=model,
            week=f"{week_start.isocalendar().week:02d}",
            journals_in_week=journals_in_week,
            journals_contextual=journals_contextual,
            extras=extras_data,
            bio=bio,
            prompt_path=prompt_path,
            quiet=quiet,
            debug=debug,
        )

        if not quiet:
            print(summary)

        if save_markdown or save_pdf:
            filename = f"{week_start.isocalendar().year}-W{week_start.isocalendar().week:02d}.md"
            md_path = resolve_output_path(save_path, week_start, custom_filename=filename)

            if save_markdown:
                md_path.write_text(summary, encoding="utf-8")

            if save_pdf:
                convert_markdown_to_pdf(summary, md_path.with_suffix(".pdf"), debug=debug)

    except Exception as e:
        handle_exception(e)


@app.command("prepare-event")
def prepare_event(
    event: Optional[str] = typer.Option(
        None,
        help="Event start time to prepare for (YYYY-MM-DD HH:MM). If omitted, use the next upcoming event.",
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
    model: str = typer.Option("gemini-2.5-pro-preview-05-06", help="Model to use for summarization"),
    skip_path_checks: bool = typer.Option(False, help="Skip checks for existence of input and output paths"),
    debug: bool = typer.Option(False, help="Enable debug logging"),
    quiet: bool = typer.Option(False, help="Suppress output to stdout"),
) -> None:

    if debug:
        enable_debug_logging()

    if not skip_path_checks:
        check_required_directories(journal_dir, extras_dir, save_path)

    prompt_path = prompt_file or Path(__file__).parent / "prompts" / "prepare-event.prompt"
    if not prompt_path.is_file():
        typer.echo(f"Error: Default prompt file does not exist: {prompt_path}", err=True)
        raise typer.Exit(code=1)

    try:
        tz = ZoneInfo(os.getenv("TIMEZONE", "Europe/Amsterdam"))
        now = datetime.now(tz)
        if event:
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
