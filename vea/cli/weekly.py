import os
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import typer

from ..loaders import journals, extras
from ..loaders.journals import load_journals
from ..loaders.extras import load_extras
from ..utils.date_utils import parse_week_input
from ..utils.output_utils import resolve_output_path
from ..utils.error_utils import enable_debug_logging, handle_exception
from ..utils.summarization import summarize_weekly
from ..utils.pdf_utils import convert_markdown_to_pdf
from ..utils.generic_utils import check_required_directories
from ..utils.text_utils import estimate_tokens, summarize_text


logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"\b\w+\b")

app = typer.Typer()


@app.command("weekly")
def generate_weekly_summary(
    week: str = typer.Option(
        datetime.today().strftime("%Y-%m-%d"),
        help="Week (e.g., 2025-W22, 2025-22, 22, or 2025-05-28)",
    ),
    journal_dir: Optional[Path] = typer.Option(None, help="Directory with Markdown journal files"),
    journal_days: int = typer.Option(21, help="Number of past days of journals to include"),
    extras_dir: Optional[Path] = typer.Option(None, help="Directory with additional Markdown files"),
    save_markdown: bool = typer.Option(True, help="Save output as markdown file."),
    save_pdf: bool = typer.Option(False, help="Save output as PDF."),
    save_path: Optional[Path] = typer.Option(None, help="Optional override path to save output."),
    prompt_file: Optional[Path] = typer.Option(None, help="Path to custom prompt file"),
    model: str = typer.Option(
        "gemini-2.5-pro-preview-06-05", help="Model to use for summarization (OpenAI, Google Gemini, or Anthropic)"
    ),
    token_budget: int = typer.Option(10000, help="Token budget for summarized context"),
    skip_path_checks: bool = typer.Option(False, help="Skip path existence checks."),
    debug: bool = typer.Option(False, help="Enable debug logging"),
    quiet: bool = typer.Option(False, help="Suppress output to stdout"),
):
    if debug:
        enable_debug_logging()

    if not skip_path_checks:
        check_required_directories(journal_dir, extras_dir, save_path)

    prompt_path = prompt_file or Path(__file__).parent.parent / "prompts" / "weekly-default.prompt"
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
            latest_date=week_end,
        )

        def _score_entry(entry: dict) -> float:
            content = entry.get("content", "")
            tokens = _TOKEN_RE.findall(content.lower())
            if not tokens:
                return 0.0
            unique_words = len(set(tokens))
            density = unique_words / len(tokens)

            alias_bonus = 0.0
            for alias in alias_map.keys():
                if alias.lower() in content.lower():
                    alias_bonus = 100.0
                    break

            recency = 0.0
            if "date" in entry and entry["date"]:
                recency = max(0, 7 - (week_end - entry["date"]).days) * 10.0

            return len(tokens) * density + alias_bonus + recency

        def _compress_group(name: str, entries: List[dict], remaining: int) -> tuple[List[dict], int]:
            if not entries or remaining <= 0:
                logger.warning("No budget left for %s", name)
                return [], 0

            ranked = sorted(entries, key=_score_entry, reverse=True)
            out: List[dict] = []
            used = 0
            for entry in ranked:
                summary = summarize_text(entry["content"])
                tokens = estimate_tokens(summary)
                entry_id = entry.get("filename") or entry.get("id")
                logger.debug("%s candidate %s tokens=%d", name, entry_id, tokens)
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
            logger.debug(
                "%s before=%d after=%d tokens=%d",
                name,
                len(entries),
                len(out),
                used,
            )
            return out, used

        def journal_in_week(entry: dict) -> bool:
            return "date" in entry and week_start <= entry["date"] <= week_end

        journals_in_week = [e for e in all_journals if journal_in_week(e)]
        journals_contextual = [e for e in all_journals if not journal_in_week(e)]
        extras_data = all_extras

        remaining = token_budget
        journals_in_week, used = _compress_group("week_journals", journals_in_week, remaining)
        remaining -= used
        journals_contextual, used = _compress_group("context_journals", journals_contextual, remaining)
        remaining -= used
        extras_data, used = _compress_group("extras", extras_data, remaining)
        remaining -= used

        logger.debug("Total tokens used %d of %d", token_budget - remaining, token_budget)

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
