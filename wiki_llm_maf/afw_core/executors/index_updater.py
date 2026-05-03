"""Executor: rebuilds wiki/index.md and appends to wiki/log.md."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime

from agent_framework import Executor, handler, WorkflowContext

logger = logging.getLogger(__name__)

_DEFAULT_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _base_dir() -> str:
    return os.environ.get("WIKI_ROOT_DIR", _DEFAULT_BASE)


def _extract_summary(filepath: str, max_len: int = 120) -> str:
    """Extract a one-line summary from a wiki page (deterministic, no LLM).

    Strategy:
    1. Find the first paragraph after the first ## heading.
    2. Take the first sentence (up to the first period).
    3. Truncate to max_len characters.
    4. Fallback: use the title from frontmatter.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return ""

    # Extract title from frontmatter as fallback
    title = ""
    fm_match = re.search(r'^title:\s*"?([^"\r\n]+)"?', content, re.MULTILINE)
    if fm_match:
        title = fm_match.group(1).strip()

    # Find first ## heading, then grab the first non-empty paragraph after it
    heading_match = re.search(r"^## .+$", content, re.MULTILINE)
    if heading_match:
        after_heading = content[heading_match.end():]
        # Skip blank lines, grab first non-empty line(s) that aren't headings/lists/code
        for line in after_heading.split("\n"):
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("```") or line.startswith("|") or line.startswith("-"):
                continue
            # Take first sentence
            sentence_match = re.match(r"(.+?[.!?])\s", line + " ")
            summary = sentence_match.group(1) if sentence_match else line
            if len(summary) > max_len:
                summary = summary[:max_len - 3].rsplit(" ", 1)[0] + "..."
            return summary

    # Fallback to title
    return title


class IndexUpdaterExecutor(Executor):
    """Rebuilds the wiki index and appends ingestion log entry for one source."""

    def __init__(self):
        super().__init__(id="index_updater")

    @handler
    async def handle(self, input: str, ctx: WorkflowContext[str]) -> None:
        data = json.loads(input)
        wiki_dir = os.path.join(_base_dir(), "wiki")
        index_path = os.path.join(wiki_dir, "index.md")
        log_path = os.path.join(wiki_dir, "log.md")

        # Rebuild index by scanning wiki directories
        categories = ["sources", "entities", "concepts", "synthesis"]
        index_lines = [
            "---",
            "title: Wiki Index",
            "type: index",
            "---",
            "",
            "# Wiki Index",
            "",
        ]

        for cat in categories:
            cat_dir = os.path.join(wiki_dir, cat)
            if not os.path.isdir(cat_dir):
                continue
            files = sorted(f for f in os.listdir(cat_dir) if f.endswith(".md"))
            if not files:
                continue
            index_lines.append(f"## {cat.title()}")
            index_lines.append("")
            for fname in files:
                slug = fname.replace(".md", "")
                fpath = os.path.join(cat_dir, fname)
                summary = _extract_summary(fpath)
                if summary:
                    index_lines.append(f"- [[{cat}/{slug}]] — {summary}")
                else:
                    index_lines.append(f"- [[{cat}/{slug}]]")
            index_lines.append("")

        # Write index
        with open(index_path, "w", encoding="utf-8") as f:
            f.write("\n".join(index_lines))

        # Append to log — single extraction
        extraction: dict = data.get("extraction", {})
        written_pages: list[str] = data.get("written_pages", [])
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        if extraction:
            fname = extraction.get("file_name", os.path.basename(extraction.get("_source_path", "unknown")))
            title = extraction.get("title", fname)
            entry = f"## [{timestamp}] ingest | {title}\n"
            entry += f"Source: {fname}\n"
            if written_pages:
                # Normalize paths for log: "wiki/entities/foo.md" → "entities/foo"
                touched = [p.replace("wiki/", "").replace(".md", "") for p in written_pages]
                entry += f"Pages touched: {', '.join(touched)}\n"

            with open(log_path, "a", encoding="utf-8") as f:
                f.write("\n" + entry)

        logger.info("Index rebuilt. Log entry appended.")
        # Signal back to dispatcher (cycle complete)
        await ctx.send_message(json.dumps({"cycle_complete": True}))
