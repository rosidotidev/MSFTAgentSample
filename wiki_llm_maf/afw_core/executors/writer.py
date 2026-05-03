"""Executor: runs WikiWriterAgent for each page in a single plan."""

from __future__ import annotations

import json
import logging
import os
import time

from agent_framework import Executor, handler, WorkflowContext

from ..agents import wiki_writer
from ..tools.wiki_read import read_wiki_page
from ..tools.wiki_write import write_wiki_page

logger = logging.getLogger(__name__)

_DEFAULT_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _base_dir() -> str:
    return os.environ.get("WIKI_ROOT_DIR", _DEFAULT_BASE)


def _get_existing_pages() -> list[str]:
    """Scan wiki directories and return all existing page paths (e.g. 'entities/agent')."""
    wiki_dir = os.path.join(_base_dir(), "wiki")
    pages: list[str] = []
    for cat in ("sources", "entities", "concepts", "synthesis"):
        cat_dir = os.path.join(wiki_dir, cat)
        if not os.path.isdir(cat_dir):
            continue
        for fname in os.listdir(cat_dir):
            if fname.endswith(".md"):
                pages.append(f"{cat}/{fname.replace('.md', '')}")
    return pages


def _build_allowed_wikilinks(existing_pages: list[str], plan: dict) -> str:
    """Build the allowed wikilinks string from existing pages + plan entries."""
    allowed = set(existing_pages)
    for entry in plan.get("pages_to_create", []):
        # Normalize path: "wiki/entities/foo.md" → "entities/foo"
        path = entry["path"].replace("wiki/", "").replace(".md", "")
        allowed.add(path)
    for entry in plan.get("pages_to_update", []):
        path = entry["path"].replace("wiki/", "").replace(".md", "")
        allowed.add(path)
    return ", ".join(f"[[{p}]]" for p in sorted(allowed))


def _filter_content_for_page(extraction: dict, path: str, page_type: str) -> str:
    """Return only the content subset relevant to the page being written."""
    slug = path.rsplit("/", 1)[-1].replace(".md", "")

    if page_type in ("source", "synthesis"):
        filtered = {
            "file_name": extraction.get("file_name", ""),
            "slug": extraction.get("slug", ""),
            "title": extraction.get("title", ""),
            "summary": extraction.get("summary", ""),
            "key_takeaways": extraction.get("key_takeaways", []),
            "entities": [{"name": e.get("name"), "slug": e.get("slug")} for e in extraction.get("entities", [])],
            "concepts": [{"name": c.get("name"), "slug": c.get("slug")} for c in extraction.get("concepts", [])],
        }
        return json.dumps(filtered, indent=2)

    if page_type == "entity":
        for entity in extraction.get("entities", []):
            if entity.get("slug") == slug:
                return json.dumps({
                    "source_title": extraction.get("title", ""),
                    "source_slug": extraction.get("slug", ""),
                    "entity": entity,
                }, indent=2)

    if page_type == "concept":
        for concept in extraction.get("concepts", []):
            if concept.get("slug") == slug:
                return json.dumps({
                    "source_title": extraction.get("title", ""),
                    "source_slug": extraction.get("slug", ""),
                    "concept": concept,
                }, indent=2)

    # Fallback
    return json.dumps(extraction, indent=2)


class WriterExecutor(Executor):
    """Executes a single plan through the WikiWriterAgent."""

    def __init__(self, client, options):
        super().__init__(id="writer")
        self._client = client
        self._options = options

    @handler
    async def handle(self, input: str, ctx: WorkflowContext[str]) -> None:
        data = json.loads(input)
        plan: dict = data.get("plan", {})
        extraction: dict = data.get("extraction", {})

        pages_to_create = plan.get("pages_to_create", [])
        pages_to_update = plan.get("pages_to_update", [])

        if not pages_to_create and not pages_to_update:
            logger.info("No pages to write.")
            await ctx.send_message(json.dumps({"written_pages": [], "extraction": extraction}))
            return

        tools = [read_wiki_page, write_wiki_page]
        agent = wiki_writer.create_agent(self._client, self._options, tools)

        # Build allowed wikilinks: existing pages + all pages in this plan
        existing_pages = _get_existing_pages()
        allowed_links = _build_allowed_wikilinks(existing_pages, plan)

        written_pages: list[str] = []
        t0 = time.time()

        # Process creates
        for entry in pages_to_create:
            path = entry["path"]
            page_type = entry.get("page_type", "unknown")
            brief = entry.get("content_brief", "")
            logger.info("Writing new %s: %s", page_type, path)

            filtered = _filter_content_for_page(extraction, path, page_type)

            prompt = (
                f"TASK: Create a new {page_type} page at '{path}'.\n"
                f"BRIEF: {brief}\n\n"
                f"RELEVANT CONTENT (include ALL code blocks from this):\n"
                f"```json\n{filtered}\n```\n\n"
                f"ALLOWED WIKILINKS (use ONLY these in the Connections section, do NOT invent others):\n"
                f"{allowed_links}\n\n"
                f"Write the page now using write_wiki_page."
            )
            await agent.run(prompt)
            written_pages.append(path)

        # Process updates
        for entry in pages_to_update:
            path = entry["path"]
            action = entry.get("action", "enrich")
            detail = entry.get("detail", "")
            page_type = entry.get("page_type", "entity")
            logger.info("Updating (%s): %s", action, path)

            filtered = _filter_content_for_page(extraction, path, page_type)

            prompt = (
                f"TASK: Update the existing page at '{path}'.\n"
                f"ACTION: {action}\n"
                f"DETAIL: {detail}\n\n"
                f"RELEVANT CONTENT (include ALL code blocks from this):\n"
                f"```json\n{filtered}\n```\n\n"
                f"ALLOWED WIKILINKS (use ONLY these in the Connections section, do NOT invent others):\n"
                f"{allowed_links}\n\n"
                f"First read the page with read_wiki_page, then rewrite it with "
                f"write_wiki_page integrating the new information."
            )
            await agent.run(prompt)
            written_pages.append(path)

        elapsed = time.time() - t0
        logger.info("Writer complete: %d page(s) written/updated (%.1fs)", len(written_pages), elapsed)
        await ctx.send_message(json.dumps({"written_pages": written_pages, "extraction": extraction}))
