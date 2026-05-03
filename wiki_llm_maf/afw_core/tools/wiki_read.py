"""Tool: read a wiki page by path."""

from __future__ import annotations

import os
from typing import Annotated

from agent_framework import tool

_DEFAULT_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _base_dir() -> str:
    return os.environ.get("WIKI_ROOT_DIR", _DEFAULT_BASE)


@tool
def read_wiki_page(
    path: Annotated[str, "Relative path to the wiki page, e.g. 'wiki/entities/openai.md'"],
) -> str:
    """Read the content of a wiki page. Returns the full markdown content."""
    print(f"  [DEBUG] read_wiki_page called with path='{path}'")
    base = _base_dir()

    # Normalize: accept "entities/tool", "entities/tool.md", "wiki/entities/tool.md"
    p = path.replace("\\", "/")
    if not p.endswith(".md"):
        p += ".md"
    if not p.startswith("wiki/"):
        p = "wiki/" + p

    full_path = os.path.join(base, p)
    if not os.path.isfile(full_path):
        print(f"  [DEBUG] Page NOT FOUND: {full_path}")
        return f"ERROR: Page not found: {path}"
    with open(full_path, "r", encoding="utf-8") as f:
        return f.read()


@tool
def read_index() -> str:
    """Read the wiki index.md — the catalog of all wiki pages."""
    print("  [DEBUG] read_index called")
    index_path = os.path.join(_base_dir(), "wiki", "index.md")
    if not os.path.isfile(index_path):
        return "ERROR: wiki/index.md not found"
    with open(index_path, "r", encoding="utf-8") as f:
        return f.read()
