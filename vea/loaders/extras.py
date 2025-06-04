import logging
import re
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

MAX_SIZE = 100_000  # bytes
EXCLUDED_FILENAMES = {"templates", "file", "file-path"}


def extract_aliases(content: str) -> List[str]:
    """
    Extract comma-separated aliases from a Markdown file that uses the pattern 'alias:: alias1, alias2'.
    """
    aliases = []
    match = re.search(r"^alias::\s*(.+)$", content, re.MULTILINE)
    if match:
        alias_line = match.group(1)
        aliases = [alias.strip() for alias in alias_line.split(",") if alias.strip()]
    return aliases


def build_alias_map(extras: List[Dict[str, str]]) -> Dict[str, str]:
    """
    Build a mapping from alias (lowercased) to canonical filename.
    """
    alias_map: Dict[str, str] = {}
    for entry in extras:
        canonical = entry["filename"]
        alias_map[canonical.lower()] = canonical
        for alias in entry.get("aliases", []):
            alias_map[alias.lower()] = canonical
    return alias_map


def load_extras(paths: Optional[List[Path]]) -> List[Dict[str, str]]:
    """
    Load content from additional Markdown files or directories. Returns a list of entries with filename, content, and aliases.
    """
    if not paths:
        return []

    entries = []
    for path in paths:
        if path.is_dir():
            files = sorted(path.glob("*.md"))
        elif path.is_file():
            files = [path]
        else:
            continue

        for file in files:
            try:
                stem = file.stem.lower()
                if stem in EXCLUDED_FILENAMES:
                    continue

                if file.stat().st_size > MAX_SIZE:
                    logger.warning(f"Skipped large file: {file}")
                    continue

                content = file.read_text(encoding="utf-8")

                if not content or content == "-" or content == "exclude-from-graph-view:: true\n" or content == "exclude-from-graph-view:: true":
                    logger.debug(f"Excluded file with trivial or empty content: {file}")
                    continue

                if content.lstrip().lower().startswith("file::"):
                    logger.debug(f"Excluded file with 'file::' marker: {file}")
                    continue

                aliases = extract_aliases(content)
                entries.append({
                    "filename": file.stem,
                    "content": content,
                    "aliases": aliases
                })

            except Exception as e:
                logger.warning(f"Failed to read file {file}: {e}", exc_info=e)

    return entries
