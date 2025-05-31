"""
Output utility functions.
"""

import os
from datetime import date
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def resolve_output_path(path: Optional[Path], target_date: date) -> Path:
    """
    Determine output file path: use given path or environment or default to ~/DailyBrief/YYYY-MM-DD.md.
    """
    path_str = str(path) if path else os.environ.get("SAVE_PATH")
    if path_str:
        path_obj = Path(path_str)
        if path_obj.is_dir():
            return path_obj / f"{target_date.isoformat()}.md"
        return path_obj
    # Default directory in home
    default_dir = Path.home() / "DailyBrief"
    default_dir.mkdir(parents=True, exist_ok=True)
    return default_dir / f"{target_date.isoformat()}.md"


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