import logging
from datetime import datetime
from pathlib import Path

import typer

from ..loaders import journals, gmail
from ..utils.embeddings import ensure_index, build_index, INDEX_DIR
from ..utils.date_utils import parse_date
from ..utils.error_utils import enable_debug_logging, handle_exception

logger = logging.getLogger(__name__)

app = typer.Typer(help="Embedding index commands")


@app.command("index-journals")
def index_journals(
    journal_dir: Path,
    journal_days: int = 21,
    debug: bool = typer.Option(False, help="Enable debug logging"),
) -> None:
    """Build or update the journal embeddings index."""
    if debug:
        enable_debug_logging()
    try:
        logger.debug("Loading journals from %s", journal_dir)
        data = journals.load_journals(journal_dir, journal_days=journal_days)
        logger.debug("Loaded %d journal entries", len(data))
        texts = [entry["content"] for entry in data]
        paths = [journal_dir / f"{entry['filename']}.md" for entry in data]
        index_path = ensure_index(texts, "journals", paths)
        logger.debug("Index written to %s", index_path)
        typer.echo(f"Journal index written to {index_path}")
    except Exception as e:
        handle_exception(e)


@app.command("index-emails")
def index_emails(
    date: str = datetime.today().strftime("%Y-%m-%d"),
    debug: bool = typer.Option(False, help="Enable debug logging"),
) -> None:
    """Build the email embeddings index for the given date."""
    if debug:
        enable_debug_logging()
    try:
        logger.debug("Loading emails for %s", date)
        day = parse_date(date)
        emails = gmail.load_emails(day)
        texts = []
        for msgs in emails.values():
            for e in msgs:
                texts.append(e.get("body", ""))
        logger.debug("Loaded %d emails", len(texts))
        index_path = INDEX_DIR / "emails.index"
        build_index(texts, index_path)
        logger.debug("Index written to %s", index_path)
        typer.echo(f"Email index written to {index_path}")
    except Exception as e:
        handle_exception(e)
