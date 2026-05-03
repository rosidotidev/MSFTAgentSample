"""Tool: write/overwrite a wiki page."""

from __future__ import annotations

import os
from typing import Annotated

from agent_framework import tool

_DEFAULT_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _base_dir() -> str:
    return os.environ.get("WIKI_ROOT_DIR", _DEFAULT_BASE)


@tool
def write_wiki_page(
    path: Annotated[str, "Relative path to the wiki page, e.g. 'wiki/entities/openai.md'"],
    content: Annotated[str, "Full markdown content to write (including frontmatter)"],
) -> str:
    """Write or overwrite a wiki page. Creates parent directories if needed."""
    full_path = os.path.join(_base_dir(), path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"OK: Written {path}"
