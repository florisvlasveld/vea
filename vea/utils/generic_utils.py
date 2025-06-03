import os
from pathlib import Path
from typing import Optional
import logging
import typer

logger = logging.getLogger(__name__)


def check_required_directories(journal_dir: Optional[str], extras_dir: Optional[str], save_path: Optional[str]) -> None:
    for path_name, path in [('journal_dir', journal_dir), ('extras_dir', extras_dir), ('save_path', save_path)]:
        if path and not os.path.isdir(path):
            typer.echo(f"Error: Provided path for {path_name} does not exist: {path}", err=True)
            raise typer.Exit(code=1)
