import typer
from pathlib import Path
from datetime import datetime

from ..loaders import journals, gmail
from ..embeddings import ensure_index, build_index, INDEX_DIR
from ..utils.date_utils import parse_date

app = typer.Typer(help="Embedding index commands")


@app.command("index-journals")
def index_journals(journal_dir: Path, journal_days: int = 21) -> None:
    """Build or update the journal embeddings index."""
    data = journals.load_journals(journal_dir, journal_days=journal_days)
    texts = [entry["content"] for entry in data]
    paths = [journal_dir / f"{entry['filename']}.md" for entry in data]
    index_path = ensure_index(texts, "journals", paths)
    typer.echo(f"Journal index written to {index_path}")


@app.command("index-emails")
def index_emails(date: str = datetime.today().strftime("%Y-%m-%d")) -> None:
    """Build the email embeddings index for the given date."""
    day = parse_date(date)
    emails = gmail.load_emails(day)
    texts = []
    for msgs in emails.values():
        for e in msgs:
            texts.append(e.get("body", ""))
    index_path = INDEX_DIR / "emails.index"
    build_index(texts, index_path)
    typer.echo(f"Email index written to {index_path}")
