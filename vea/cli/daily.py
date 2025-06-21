import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import typer

from ..loaders import gcal, gmail, journals, extras, todoist, slack as slack_loader
from ..utils.date_utils import parse_date
from ..utils.output_utils import resolve_output_path
from ..utils.error_utils import enable_debug_logging, handle_exception
from ..utils.summarization import summarize_daily
from ..utils.pdf_utils import convert_markdown_to_pdf
from ..utils.generic_utils import check_required_directories

app = typer.Typer()


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
        "gemini-2.5-pro", help="Model to use for summarization (OpenAI, Google Gemini, or Anthropic)"
    ),
    use_embeddings: bool = typer.Option(False, help="Use embeddings for retrieval"),
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

        if use_embeddings:
            from ..utils.embeddings import ensure_index, query_index

            if journal_dir:
                journal_paths = [journal_dir / f"{j['filename']}.md" for j in journals_data]
                idx = ensure_index([j['content'] for j in journals_data], "journals", journal_paths)
                journals_data = query_index(str(target_date), idx, k=5)

            email_texts = []
            for msgs in emails.values():
                for e in msgs:
                    email_texts.append(e.get("body", ""))
            idx_em = ensure_index(email_texts, "emails")
            emails = query_index(str(target_date), idx_em, k=5)
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
