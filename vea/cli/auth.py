from typing import List

import typer

from ..auth import authorize
from ..utils.error_utils import handle_exception

app = typer.Typer()


@app.command("auth")
def auth_command(
    scopes: List[str] = typer.Argument(
        ..., help="Services to authorize (e.g., `calendar gmail`)")
) -> None:
    try:
        authorize(scopes)
    except Exception as e:
        handle_exception(e)
