import logging
import traceback
import typer

logger = logging.getLogger(__name__)


def handle_exception(e: Exception) -> None:
    logger.error("Exception occurred: %s", e, exc_info=e)
    traceback.print_exc()
    raise typer.Exit(code=1)


def enable_debug_logging() -> None:
    logging.basicConfig(level=logging.DEBUG)
    logger.debug("Debug logging enabled.")