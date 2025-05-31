import os
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import typer
from dotenv import load_dotenv

from vea.loaders import gcal, gmail, journals, extras, todoist, slack as slack_loader
from vea.auth import authorize
from vea.utils.date_utils import parse_date
from vea.utils.output_utils import resolve_output_path
from vea.utils.error_utils import enable_debug_logging, handle_exception
from vea.utils.summarization import summarize

app = typer.Typer(help="Vea: Generate a personalized daily briefing.")

load_dotenv()


def check_required_directories(journal_dir: Optional[str], extras_dir: Optional[str], save_path: Optional[str]) -> None:
    for path_name, path in [('journal_dir', journal_dir), ('extras_dir', extras_dir), ('save_path', save_path)]:
        if path and not os.path.isdir(path):
            typer.echo(f"Error: Provided path for {path_name} does not exist: {path}", err=True)
            raise typer.Exit(code=1)


@app.command("auth")
def auth_command(
    scopes: List[str] = typer.Argument(..., help="Services to authorize (e.g., calendar gmail)")
) -> None:
    try:
        authorize(scopes)
    except Exception as e:
        handle_exception(e)


@app.command("generate")
def generate(
    date: str = typer.Option(datetime.today().strftime("%Y-%m-%d"), help="Date for the brief (YYYY-MM-DD)"),
    save: bool = typer.Option(True, help="Save output to file"),
    save_path: Optional[Path] = typer.Option(None, help="Custom path or directory to save the output"),
    debug: bool = typer.Option(False, help="Enable debug logging"),
    quiet: bool = typer.Option(False, help="Suppress output to stdout"),
    journal_dir: Optional[Path] = typer.Option(None, help="Directory with Markdown journal files"),
    journal_days: int = typer.Option(21, help="Number of past days of journals to include"),
    extra_dir: Optional[Path] = typer.Option(None, help="Directory with additional Markdown files"),
    extra_labels: Optional[List[str]] = typer.Option(None, help="List of additional Gmail labels to fetch emails from"),
    model: str = typer.Option("gemini-2.5-pro-preview-05-06", help="Model to use for summarization (OpenAI, Google Gemini, or Anthropic)"),
    openai_key: Optional[str] = typer.Option(None, help="OpenAI API key (or set OPENAI_KEY in env)"),
    todoist_token: Optional[str] = typer.Option(None, help="Todoist API token (or set TODOIST_TOKEN in env)"),
    project_name: Optional[str] = typer.Option(None, help="Name of the Todoist project to filter tasks by"),
    my_email: Optional[str] = typer.Option(None, help="Your email address to filter declined calendar events"),
    include_slack: bool = typer.Option(True, help="Include recent Slack messages"),
    calendar_blacklist: Optional[List[str]] = typer.Option(
        None,
        help="Comma-separated list of keywords to blacklist from calendar events (overrides CALENDAR_EVENT_BLACKLIST)"
    ),
    skip_path_checks: bool = typer.Option(False, help="Skip checks for input/output directory existence"),
) -> None:

    if debug:
        enable_debug_logging()

    if not skip_path_checks:
        check_required_directories(journal_dir, extra_dir, save_path)

    prompt_path = Path(__file__).parent / "prompts" / "daily-default.prompt"
    if not prompt_path.is_file():
        typer.echo(f"Error: Default prompt file does not exist: {prompt_path}", err=True)
        raise typer.Exit(code=1)

    try:
        target_date = parse_date(date)

        calendars = gcal.load_events(target_date, my_email=my_email, blacklist=calendar_blacklist)
        tasks = todoist.load_tasks(target_date, todoist_token or os.getenv("TODOIST_TOKEN", ""), project_name or "")
        emails = gmail.load_emails(target_date, extra_labels=extra_labels)
        extras_data = extras.load_extras([extra_dir] if extra_dir else [])
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
        slack_data = slack_loader.load_slack_messages() if include_slack else {}

        if openai_key:
            os.environ["OPENAI_API_KEY"] = openai_key
        bio = os.getenv("BIO", "")

        summary = summarize(
            model=model,
            date=target_date,
            emails=emails,
            calendars=calendars,
            tasks=tasks,
            journals=journals_data,
            extras=extras_data,
            slack=slack_data,
            bio=bio,
            quiet=quiet,
            debug=debug,
        )

        if not quiet:
            print(summary)

        if save:
            out_path = resolve_output_path(save_path, target_date)
            out_path.write_text(summary)

    except Exception as e:
        handle_exception(e)