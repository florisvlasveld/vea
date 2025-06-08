import os
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import typer

from ..loaders import gmail, journals, slack as slack_loader, todoist, extras
from ..utils.output_utils import resolve_output_path
from ..utils.error_utils import enable_debug_logging, handle_exception
from ..utils.summarization import summarize_check_for_tasks
from ..utils.pdf_utils import convert_markdown_to_pdf
from ..utils.generic_utils import check_required_directories
from ..utils.text_utils import estimate_tokens, summarize_text

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"\b\w+\b")
_TASK_PATTERNS = [
    re.compile(p, re.I)
    for p in [r"- \[ \]", r"TODO", r"follow up", r"remember to", r"check with"]
]

app = typer.Typer()


@app.command("check-for-tasks")
def check_for_tasks(
    journal_dir: Optional[Path] = typer.Option(None, help="Directory with Markdown journal files"),
    journal_days: int = typer.Option(7, help="Number of past days of journals to include"),
    extras_dir: Optional[Path] = typer.Option(None, help="Directory with additional Markdown notes"),
    gmail_labels: Optional[List[str]] = typer.Option(None, help="List of additional Gmail labels to fetch emails from"),
    todoist_project: Optional[str] = typer.Option(None, help="Name of the Todoist project to filter tasks by"),
    todoist_lookback_days: int = typer.Option(7, help="Number of days to look back for completed Todoist tasks"),
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
        "gemini-2.5-pro-preview-06-05", help="Model to use for summarization (OpenAI, Google Gemini, or Anthropic)"
    ),
    token_budget: int = typer.Option(10000, help="Token budget for summarized context"),
    skip_path_checks: bool = typer.Option(False, help="Skip checks for existence of input and output paths"),
    debug: bool = typer.Option(False, help="Enable debug logging"),
    quiet: bool = typer.Option(False, help="Suppress output to stdout"),
) -> None:

    if debug:
        enable_debug_logging()

    if not skip_path_checks:
        check_required_directories(journal_dir, extras_dir, save_path)

    prompt_path = prompt_file or Path(__file__).parent.parent / "prompts" / "check-for-tasks-default.prompt"
    if not prompt_path.is_file():
        typer.echo(f"Error: Default prompt file does not exist: {prompt_path}", err=True)
        raise typer.Exit(code=1)

    try:
        extras_paths = [extras_dir] if extras_dir else []
        extras_data = extras.load_extras(extras_paths)
        alias_map = extras.build_alias_map(extras_data)
        journals_data = (
            journals.load_journals(
                journal_dir,
                journal_days=journal_days,
                alias_map=alias_map,
            )
            if journal_dir
            else []
        ) + extras_data
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
        open_tasks = todoist.load_open_tasks(todoist_project=todoist_project or "")
        bio = os.getenv("BIO", "")

        def _score_entry(entry: dict) -> tuple[float, list[str]]:
            content = entry.get("content", "")
            tokens = _TOKEN_RE.findall(content.lower())
            reasons: list[str] = []
            score = 0.0
            for pat in _TASK_PATTERNS:
                if pat.search(content):
                    score += 50.0
                    reasons.append("task phrase")
                    break
            for alias in alias_map.keys():
                if alias.lower() in content.lower():
                    score += 20.0
                    reasons.append(f"alias:{alias}")
                    break
            if tokens:
                score += len(set(tokens)) / len(tokens) * 10.0
                score += len(tokens) * 0.1
            return score, reasons

        def _compress_group(name: str, entries: List[dict], remaining: int) -> tuple[List[dict], int]:
            if not entries or remaining <= 0:
                logger.warning("No budget left for %s", name)
                return [], 0
            ranked = []
            for e in entries:
                sc, reasons = _score_entry(e)
                ranked.append((e, sc, reasons))
            ranked.sort(key=lambda x: x[1], reverse=True)
            out: List[dict] = []
            used = 0
            for entry, sc, reasons in ranked:
                summary = summarize_text(entry["content"])
                tokens = estimate_tokens(summary)
                entry_id = entry.get("filename") or entry.get("id")
                logger.debug("%s candidate %s tokens=%d reasons=%s", name, entry_id, tokens, ",".join(reasons))
                if used + tokens > remaining:
                    logger.debug(
                        "%s excluded %s due to budget (needed %d remaining %d)",
                        name,
                        entry_id,
                        tokens,
                        remaining - used,
                    )
                    continue
                new_e = entry.copy()
                new_e["content"] = summary
                new_e["token_count"] = tokens
                out.append(new_e)
                used += tokens
                if used >= remaining:
                    break
            logger.debug("%s before=%d after=%d tokens=%d", name, len(entries), len(out), used)
            return out, used

        remaining = token_budget

        journal_docs = [
            {"id": j.get("filename", "j"), "content": j["content"], "metadata": j}
            for j in journals_data
        ]
        journal_docs, used = _compress_group("journal", journal_docs, remaining)
        remaining -= used
        journals_data = [d["metadata"] | {"content": d["content"], "token_count": d["token_count"]} for d in journal_docs]

        email_docs = [
            {
                "id": f"{label}-{i}",
                "content": f"{m.get('subject','')} {m.get('body','')}",
                "metadata": {**m, "label": label},
            }
            for label, msgs in emails.items()
            for i, m in enumerate(msgs)
        ]
        email_docs, used = _compress_group("email", email_docs, remaining)
        remaining -= used
        filtered_emails: dict[str, List[dict]] = {}
        for d in email_docs:
            meta = d["metadata"].copy()
            meta["body"] = d["content"]
            filtered_emails.setdefault(meta.get("label", "inbox"), []).append(meta)

        slack_docs = [
            {
                "id": f"{chan}-{i}",
                "content": msg.get("text", "") + " " + " ".join(r.get("text", "") for r in msg.get("replies", [])),
                "metadata": {**msg, "channel": chan},
            }
            for chan, msgs in slack_data.items()
            for i, msg in enumerate(msgs)
        ]
        slack_docs, used = _compress_group("slack", slack_docs, remaining)
        remaining -= used
        filtered_slack: dict[str, List[dict]] = {}
        for d in slack_docs:
            meta = d["metadata"].copy()
            meta["text"] = d["content"]
            filtered_slack.setdefault(meta.get("channel", ""), []).append(meta)

        summary = summarize_check_for_tasks(
            model=model,
            journals=journals_data,
            emails=filtered_emails,
            completed_tasks=completed_tasks,
            open_tasks=open_tasks,
            slack=filtered_slack,
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
