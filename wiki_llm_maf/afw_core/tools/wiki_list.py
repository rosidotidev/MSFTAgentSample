"""Tool: list all wiki pages."""

from __future__ import annotations

import os

from agent_framework import tool

_DEFAULT_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _base_dir() -> str:
    return os.environ.get("WIKI_ROOT_DIR", _DEFAULT_BASE)


@tool
def list_wiki_pages() -> str:
    """List all wiki pages with their relative paths. Returns one path per line."""
    print("  [DEBUG] list_wiki_pages called")
    base = _base_dir()
    wiki_dir = os.path.join(base, "wiki")
    pages: list[str] = []
    for root, _dirs, files in os.walk(wiki_dir):
        for f in files:
            if f.endswith(".md") and f not in ("index.md", "log.md"):
                rel = os.path.relpath(os.path.join(root, f), base).replace("\\", "/")
                pages.append(rel)
    pages.sort()
    if not pages:
        return "No wiki pages found."
    return "\n".join(pages)
