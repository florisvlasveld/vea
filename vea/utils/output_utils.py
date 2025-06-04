import os
from datetime import date
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def resolve_output_path(
    path: Optional[Path],
    target_date: date,
    custom_filename: Optional[str] = None
) -> Path:
    """
    Determine output file path: use given path or environment or default to ~/DailyBrief/{date}.md
    If the target file already exists, append a number suffix to avoid overwriting:
    e.g., "YYYY-MM-DD.md", "YYYY-MM-DD_(1).md", "YYYY-MM-DD_(2).md", etc.

    If `custom_filename` is provided, it overrides the default date-based name.
    """
    path_str = str(path) if path else os.environ.get("SAVE_PATH")

    if path_str:
        path_obj = Path(path_str)
        if path_obj.is_dir():
            base_name = custom_filename or f"{target_date.isoformat()}.md"
            base_path = path_obj / base_name
        else:
            base_path = path_obj
    else:
        default_dir = Path.home() / "DailyBrief"
        default_dir.mkdir(parents=True, exist_ok=True)
        base_name = custom_filename or f"{target_date.isoformat()}.md"
        base_path = default_dir / base_name

    # If file exists, append _(1), _(2), etc.
    final_path = base_path
    counter = 1
    while final_path.exists():
        stem = base_path.stem
        suffix = base_path.suffix
        final_path = base_path.with_name(f"{stem}_({counter}){suffix}")
        counter += 1

    return final_path


def truncate_prompt(prompt: str, max_tokens: int = 180000) -> str:
    """
    Truncate the prompt to fit within maximum input limit.
    Assumes ~4 characters per token.
    """
    max_chars = max_tokens * 4
    if len(prompt) > max_chars:
        logger.warning(f"⚠️ Prompt too long ({len(prompt)} chars). Truncating to {max_chars} chars.")
        return prompt[:max_chars]
    return prompt
