"""Tool: grep-based text search across wiki pages."""

from __future__ import annotations

import os
from typing import Annotated

from agent_framework import tool

_DEFAULT_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _base_dir() -> str:
    return os.environ.get("WIKI_ROOT_DIR", _DEFAULT_BASE)


@tool
def search_wiki(
    query: Annotated[str, "Text to search for across all wiki pages (case-insensitive)"],
) -> str:
    """Search for text across all wiki pages. Returns matching lines with file paths."""
    print(f"  [DEBUG] search_wiki called with query='{query}'")
    base = _base_dir()
    wiki_dir = os.path.join(base, "wiki")
    results: list[str] = []
    query_lower = query.lower()

    for root, _dirs, files in os.walk(wiki_dir):
        for fname in files:
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, base).replace("\\", "/")
            with open(fpath, "r", encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    if query_lower in line.lower():
                        results.append(f"{rel}:{i}: {line.rstrip()}")

    if not results:
        return f"No results for '{query}'."
    # Limit to 50 results to avoid context explosion
    if len(results) > 50:
        results = results[:50]
        results.append(f"... ({len(results)} total matches, showing first 50)")
    return "\n".join(results)
