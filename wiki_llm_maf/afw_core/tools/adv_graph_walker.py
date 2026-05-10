"""ADV_ graph walker — deterministic BFS traversal of wiki Connections.

Reads seed pages, parses their ## Connections sections, and follows
links breadth-first until the page budget is exhausted.

No LLM calls — pure Python I/O + regex parsing.
"""

from __future__ import annotations

import logging
import os
import re
from collections import OrderedDict

from ..console import console

logger = logging.getLogger(__name__)

# Matches [[category/slug]] in Connections lines
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def _load_page(wiki_dir: str, path: str) -> str | None:
    """Load a wiki page by relative path.  Returns None if not found."""
    p = path.replace("\\", "/")
    if not p.endswith(".md"):
        p += ".md"
    full = os.path.join(wiki_dir, p)
    if not os.path.isfile(full):
        logger.debug("Page not found: %s", full)
        return None
    with open(full, "r", encoding="utf-8") as f:
        return f.read()


def _parse_connections(content: str) -> list[str]:
    """Extract linked paths from the ## Connections section of a page."""
    paths: list[str] = []
    in_connections = False
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("## Connections"):
            in_connections = True
            continue
        if in_connections:
            if stripped.startswith("## "):
                break  # next section
            for m in _WIKILINK_RE.finditer(stripped):
                paths.append(m.group(1))
    return paths


def walk_graph(
    seeds: list[str],
    budget: int,
    wiki_dir: str,
) -> OrderedDict[str, str]:
    """BFS walk starting from seed pages, following ## Connections.

    Args:
        seeds: ordered list of seed page paths (from the Planner).
        budget: max number of pages to read.
        wiki_dir: absolute path to the wiki/ directory.

    Returns:
        OrderedDict mapping path → page content, in read order.
    """
    read: OrderedDict[str, str] = OrderedDict()
    queue: list[str] = list(seeds)

    while queue and len(read) < budget:
        path = queue.pop(0)
        if path in read:
            continue

        content = _load_page(wiki_dir, path)
        if content is None:
            logger.warning("Seed/connection page not found, skipping: %s", path)
            continue

        read[path] = content
        logger.debug("Read [%d/%d]: %s", len(read), budget, path)
        console.detail(f"Read [{len(read)}/{budget}]: {path}")

        # Discover new pages from Connections
        for conn_path in _parse_connections(content):
            if conn_path not in read and conn_path not in queue:
                queue.append(conn_path)
                logger.debug("Queued connection: %s (from %s)", conn_path, path)

    if queue:
        logger.debug("Budget reached (%d/%d). Unread in queue: %d",
                     len(read), budget, len(queue))

    return read
