"""Markdown parsing utilities."""

import re
from typing import List


def split_outliner_blocks(content: str) -> List[str]:
    """Return top-level bullets with children from Logseq-style Markdown."""
    blocks: List[List[str]] = []
    current: List[str] = []
    for line in content.splitlines():
        if re.match(r"^-\s|^-\[", line):
            if current:
                blocks.append(current)
                current = []
            current.append(line)
        else:
            if current:
                current.append(line)
    if current:
        blocks.append(current)
    return ["\n".join(b).rstrip() for b in blocks]
