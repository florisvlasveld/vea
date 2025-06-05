import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import typer

from ..loaders import gmail, journals, slack as slack_loader, todoist
from ..utils.output_utils import resolve_output_path
from ..utils.error_utils import enable_debug_logging, handle_exception
from ..utils.summarization import summarize_check_for_tasks
from ..utils.pdf_utils import convert_markdown_to_pdf
from ..utils.generic_utils import check_required_directories

app = typer.Typer()


@app.command("check-for-tasks")
def check_for_tasks(
    journal_dir: Optional[Path] = typer.Option(None, help="Directory with Markdown journal files"),
    journal_days: int = typer.Option(21, help="Number of past days of journals to include"),
    gmail_labels: Optional[List[str]] = typer.Option(None, help="List of additional Gmail labels to fetch emails from"),
    todoist_project: Optional[str] = typer.Option(None, help="Name of the Todoist project to filter tasks by"),
    todoist_lookback_days: int = typer.Option(14, help="Number of days to look back for completed Todoist tasks"),
    include_slack: bool = typer.Option(True, help="Include recent Slack messages"),
    slack_days: int = typer.Option(
        slack_loader.DEFAULT_DAYS_LOOKBACK,
        help="Number of past days of Slack messages to load",
    ),
    save_markdown: bool = typer.Option(True, help="Save output to Markdown file"),
    save_pdf: bool = typer.Option(False, help="Save output to PDF file"),
    save_path: Optional[Path] = typer.Option(None, help="Custom file path or directory to save the output"),
    prompt_file: Optional[Path] = typer.Option(None, help="Path to custom prompt file"),
    model: str = typer.Option(
        "gemini-2.5-pro-preview-05-06", help="Model to use for summarization (OpenAI, Google Gemini, or Anthropic)"
    ),
    skip_path_checks: bool = typer.Option(False, help="Skip checks for existence of input and output paths"),
    debug: bool = typer.Option(False, help="Enable debug logging"),
    quiet: bool = typer.Option(False, help="Suppress output to stdout"),
) -> None:

    if debug:
        enable_debug_logging()

    if not skip_path_checks:
        check_required_directories(journal_dir, None, save_path)

    prompt_path = prompt_file or Path(__file__).parent.parent / "prompts" / "check-for-tasks-default.prompt"
    if not prompt_path.is_file():
        typer.echo(f"Error: Default prompt file does not exist: {prompt_path}", err=True)
        raise typer.Exit(code=1)

    try:
        journals_data = (
            journals.load_journals(journal_dir, journal_days=journal_days)
            if journal_dir
            else []
        )
        emails = gmail.load_emails(datetime.today().date(), gmail_labels=gmail_labels)
        slack_data = (
            slack_loader.load_slack_messages(days_lookback=slack_days)
            if include_slack
            else {}
        )
        completed_tasks = todoist.load_completed_tasks(
            lookback_days=todoist_lookback_days,
            todoist_project=todoist_project or "",
        )
        future_tasks = todoist.load_future_tasks(todoist_project=todoist_project or "")
        bio = os.getenv("BIO", "")

        summary = summarize_check_for_tasks(
            model=model,
            journals=journals_data,
            emails=emails,
            completed_tasks=completed_tasks,
            future_tasks=future_tasks,
            slack=slack_data,
            bio=bio,
            prompt_path=prompt_path,
            quiet=quiet,
            debug=debug,
        )

        if not quiet:
            print(summary)

        if save_markdown or save_pdf:
            today = datetime.today().date()
            filename = f"{today.isoformat()}_tasks.md"
            out_path = resolve_output_path(save_path, today, custom_filename=filename)

        if save_markdown:
            out_path.write_text(summary)

        if save_pdf:
            convert_markdown_to_pdf(summary, out_path.with_suffix(".pdf"), debug=debug)

    except Exception as e:
        handle_exception(e)
