import re
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

MAX_SIZE = 100_000  # bytes


def resolve_references(content: str, alias_map: Dict[str, str]) -> str:
    """
    Replace Wiki-style [[reference]] with canonical names based on alias_map.
    """
    def replace_match(match):
        ref = match.group(1).lower()
        return f"[[{alias_map.get(ref, ref)}]]"

    return re.sub(r"\[\[([^\\]]+)\]\]", replace_match, content)


def load_journals(
    journal_dir: Path,
    journal_days: int = 21,
    alias_map: Optional[Dict[str, str]] = None,
    target_date: Optional[datetime.date] = None,
) -> List[Dict[str, str]]:
    """
    Load journal entries (Markdown files) within the past journal_days. If target_date is provided,
    only include entries with matching date.
    """
    if not journal_dir.is_dir():
        logger.warning(f"Journal directory not found: {journal_dir}")
        return []

    today = datetime.today().date()
    cutoff_date = today - timedelta(days=journal_days)
    entries = []

    for path in sorted(journal_dir.glob("*.md")):
        try:
            date_str = path.stem.replace("_", "-")
            file_date = datetime.strptime(date_str, "%Y-%m-%d").date()

            if cutoff_date <= file_date <= target_date and path.stat().st_size <= MAX_SIZE:    
                content = path.read_text(encoding="utf-8")

                # If target_date is set, remove lines beginning with '- [[Vea]]' from other dates
                if target_date and file_date != target_date:
                    content = "\n".join(
                        line for line in content.splitlines()
                        if not re.match(r"^\s*-\s*(\[\[)Vea(\]\])?", line, re.IGNORECASE)
                    )

                if alias_map:
                    content = resolve_references(content, alias_map)

                entries.append({
                    "filename": path.stem,
                    "content": content
                })
        except Exception as e:
            logger.warning(f"Skipping file {path} due to error: {e}", exc_info=e)
            continue

    logger.info(f"Included {len(entries)} journal files from the past {journal_days} days.")
    return entries
