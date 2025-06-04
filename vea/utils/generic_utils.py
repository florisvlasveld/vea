from pathlib import Path
from typing import Optional
import logging
import typer

logger = logging.getLogger(__name__)


def check_required_directories(
    journal_dir: Optional[Path],
    extras_dir: Optional[Path],
    save_path: Optional[Path]
) -> None:
    for path_name, path in [
        ("journal_dir", journal_dir),
        ("extras_dir", extras_dir),
        ("save_path", save_path),
    ]:
        if path and not Path(path).is_dir():
            typer.echo(f"Error: Provided path for {path_name} does not exist: {path}", err=True)
            raise typer.Exit(code=1)
