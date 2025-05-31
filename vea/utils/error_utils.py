"""
Error handling and logging utilities.
"""

import logging
import traceback
import typer

logger = logging.getLogger(__name__)


def handle_exception(e: Exception) -> None:
    """
    Log the exception details, print traceback, and exit the CLI with error code.
    """
    logger.error("Exception occurred: %s", e, exc_info=e)
    traceback.print_exc()
    raise typer.Exit(code=1)


def enable_debug_logging() -> None:
    """
    Enable debug-level logging to stdout.
    """
    logging.basicConfig(level=logging.DEBUG)
    logger.debug("Debug logging enabled.")
