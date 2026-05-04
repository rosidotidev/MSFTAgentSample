"""Executor: deterministic wiki page writer — no LLM, pure template fill."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import date

from agent_framework import Executor, handler, WorkflowContext

logger = logging.getLogger(__name__)

_DEFAULT_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _base_dir() -> str:
    return os.environ.get("WIKI_ROOT_DIR", _DEFAULT_BASE)


def _today() -> str:
    return date.today().isoformat()


def _write_file(path: str, content: str) -> None:
    full_path = os.path.join(_base_dir(), path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)


def _read_file(path: str) -> str | None:
    full_path = os.path.join(_base_dir(), path)
    if not os.path.isfile(full_path):
        return None
    with open(full_path, "r", encoding="utf-8") as f:
        return f.read()


_MAX_CONNECTION_DESC = 120


def _truncate(text: str, max_len: int = _MAX_CONNECTION_DESC) -> str:
    """Truncate text to max_len, adding ellipsis if needed."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _build_connections_from_claims(extraction: dict) -> dict[str, dict[str, str]]:
    """Build a map: slug -> {connected_slug: relationship_description}.

    Uses claim text as the relationship description between co-occurring items.
    If multiple claims bridge the same pair, keeps the shortest (most concise).
    """
    claims = extraction.get("claims", [])
    entities = extraction.get("entities", [])
    concepts = extraction.get("concepts", [])

    # name -> category/slug maps
    entity_name_to_slug: dict[str, str] = {}
    for e in entities:
        entity_name_to_slug[e.get("name", "")] = f"entities/{e.get('slug', '')}"
        entity_name_to_slug[e.get("slug", "")] = f"entities/{e.get('slug', '')}"

    concept_name_to_slug: dict[str, str] = {}
    for c in concepts:
        concept_name_to_slug[c.get("name", "")] = f"concepts/{c.get('slug', '')}"
        concept_name_to_slug[c.get("slug", "")] = f"concepts/{c.get('slug', '')}"

    # For each claim, collect all entity/concept slugs mentioned + claim text
    claim_groups: list[tuple[set[str], str]] = []
    for claim in claims:
        group: set[str] = set()
        for ename in claim.get("entities", []):
            path = entity_name_to_slug.get(ename)
            if path:
                group.add(path)
        for cname in claim.get("concepts", []):
            path = concept_name_to_slug.get(cname)
            if path:
                group.add(path)
        if len(group) > 1:
            claim_groups.append((group, claim.get("text", "")))

    # Build adjacency with descriptions: keep shortest claim text per pair
    connections: dict[str, dict[str, str]] = {}
    for group, claim_text in claim_groups:
        items = list(group)
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                # a → b
                if a not in connections:
                    connections[a] = {}
                existing_desc = connections[a].get(b, "")
                if not existing_desc or (claim_text and len(claim_text) < len(existing_desc)):
                    connections[a][b] = _truncate(claim_text)
                # b → a
                if b not in connections:
                    connections[b] = {}
                existing_desc = connections[b].get(a, "")
                if not existing_desc or (claim_text and len(claim_text) < len(existing_desc)):
                    connections[b][a] = _truncate(claim_text)

    return connections


def _parse_existing_connections(content: str) -> dict[str, str]:
    """Parse ## Connections section from existing page content.

    Returns {slug_path: description} from lines like:
    - [[entities/foo]] — some description
    - [[concepts/bar]]
    """
    connections: dict[str, str] = {}
    in_section = False
    for line in content.split("\n"):
        if line.strip() == "## Connections":
            in_section = True
            continue
        if in_section:
            if line.startswith("## "):
                break
            m = re.match(r"- \[\[(.+?)\]\](?:\s*—\s*(.*))?", line)
            if m:
                connections[m.group(1)] = (m.group(2) or "").strip()
    return connections


def _render_connections_section(conn: dict[str, str]) -> list[str]:
    """Render a sorted ## Connections section from a slug→description map."""
    if not conn:
        return []
    lines = ["", "## Connections"]
    for slug in sorted(conn.keys()):
        desc = conn[slug]
        if desc:
            lines.append(f"- [[{slug}]] — {desc}")
        else:
            lines.append(f"- [[{slug}]]")
    return lines


# ---------------------------------------------------------------------------
# Page renderers
# ---------------------------------------------------------------------------

def _render_source_page(extraction: dict) -> str:
    slug = extraction.get("slug", "unknown")
    title = extraction.get("title", slug)
    file_name = extraction.get("file_name", "")
    summary = extraction.get("summary", "")
    takeaways = extraction.get("key_takeaways", [])
    entities = extraction.get("entities", [])
    concepts = extraction.get("concepts", [])
    today = _today()

    entity_slugs = [e.get("slug", "") for e in entities if e.get("slug")]
    concept_slugs = [c.get("slug", "") for c in concepts if c.get("slug")]

    lines = [
        "---",
        f'title: "{title}"',
        'type: "source"',
        f'source_file: "{file_name}"',
        f'created: "{today}"',
        f'updated: "{today}"',
        f'entities: {json.dumps(entity_slugs)}',
        f'concepts: {json.dumps(concept_slugs)}',
        "---",
        "",
        "## Summary",
        summary,
        "",
        "## Key Takeaways",
    ]
    for t in takeaways:
        lines.append(f"- {t}")

    lines.append("")
    lines.append("## Entities Mentioned")
    for e in entities:
        s = e.get("slug", "")
        desc = e.get("description", e.get("name", s))
        lines.append(f"- [[entities/{s}]] — {desc}")

    lines.append("")
    lines.append("## Concepts Covered")
    for c in concepts:
        s = c.get("slug", "")
        defn = c.get("definition", c.get("name", s))
        lines.append(f"- [[concepts/{s}]] — {defn}")

    return "\n".join(lines) + "\n"


def _render_entity_page(entity: dict, source_slug: str, conn_map: dict[str, dict[str, str]]) -> str:
    slug = entity.get("slug", "unknown")
    name = entity.get("name", slug)
    etype = entity.get("type", "other")
    description = entity.get("description", "")
    content = entity.get("content", "")
    today = _today()

    conn = conn_map.get(f"entities/{slug}", {})

    lines = [
        "---",
        f'title: "{name}"',
        'type: "entity"',
        f'entity_type: "{etype}"',
        f'created: "{today}"',
        f'updated: "{today}"',
        f'sources: ["{source_slug}"]',
        "---",
        "",
        "## Overview",
        description,
        "",
        f"## From [[sources/{source_slug}]]",
        content,
    ]

    lines.extend(_render_connections_section(conn))

    return "\n".join(lines) + "\n"


def _render_concept_page(concept: dict, source_slug: str, conn_map: dict[str, dict[str, str]]) -> str:
    slug = concept.get("slug", "unknown")
    name = concept.get("name", slug)
    definition = concept.get("definition", "")
    content = concept.get("content", "")
    today = _today()

    conn = conn_map.get(f"concepts/{slug}", {})

    lines = [
        "---",
        f'title: "{name}"',
        'type: "concept"',
        f'created: "{today}"',
        f'updated: "{today}"',
        f'sources: ["{source_slug}"]',
        "---",
        "",
        "## Definition",
        definition,
        "",
        f"## From [[sources/{source_slug}]]",
        content,
    ]

    lines.extend(_render_connections_section(conn))

    return "\n".join(lines) + "\n"


def _render_update(existing_content: str, extraction: dict, entry: dict, source_slug: str) -> str:
    """Append a new 'From source' section and merge Connections."""
    path = entry["path"]
    slug = path.rsplit("/", 1)[-1].replace(".md", "")
    page_type = "entity" if "/entities/" in path else "concept"

    item = None
    items_key = "entities" if page_type == "entity" else "concepts"
    for it in extraction.get(items_key, []):
        if it.get("slug") == slug:
            item = it
            break

    new_content = item.get("content", "") if item else entry.get("detail", "")
    new_section = f"\n\n## From [[sources/{source_slug}]]\n{new_content}\n"

    today = _today()
    updated = re.sub(r'updated: "[^"]*"', f'updated: "{today}"', existing_content)
    if source_slug not in updated:
        updated = re.sub(
            r'sources: \[([^\]]*)\]',
            lambda m: f'sources: [{m.group(1)}, "{source_slug}"]' if m.group(1) else f'sources: ["{source_slug}"]',
            updated,
        )

    # --- Merge Connections ---
    # Parse existing connections from page
    existing_conn = _parse_existing_connections(updated)

    # Build new connections from current extraction
    conn_map = _build_connections_from_claims(extraction)
    page_key = f"{page_type.replace('entity', 'entities').replace('concept', 'concepts')}/{slug}"
    new_conn = conn_map.get(page_key, {})

    # Merge: new descriptions win on conflict
    merged = {**existing_conn, **new_conn}

    # Remove old Connections section from content
    lines = updated.split("\n")
    result_lines: list[str] = []
    skip = False
    for line in lines:
        if line.strip() == "## Connections":
            skip = True
            continue
        if skip and line.startswith("## "):
            skip = False
        if not skip:
            result_lines.append(line)

    updated = "\n".join(result_lines).rstrip() + new_section

    # Append merged connections at the end
    conn_lines = _render_connections_section(merged)
    if conn_lines:
        updated = updated.rstrip() + "\n" + "\n".join(conn_lines) + "\n"

    return updated


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

class WriterExecutor(Executor):
    """Deterministic wiki writer — no LLM calls."""

    def __init__(self, client=None, options=None):
        super().__init__(id="writer")

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

        source_slug = extraction.get("slug", "unknown")
        conn_map = _build_connections_from_claims(extraction)
        written_pages: list[str] = []
        t0 = time.time()

        entities_by_slug = {e["slug"]: e for e in extraction.get("entities", []) if e.get("slug")}
        concepts_by_slug = {c["slug"]: c for c in extraction.get("concepts", []) if c.get("slug")}

        from ..logging_config import is_monitor_enabled, get_diagnostics_dir
        monitor = is_monitor_enabled()
        dump_dir = get_diagnostics_dir() if monitor else ""

        # Process creates
        for entry in pages_to_create:
            path = entry["path"]
            page_type = entry.get("page_type", "unknown")
            slug = path.rsplit("/", 1)[-1].replace(".md", "")
            logger.info("Writing new %s: %s", page_type, path)

            if page_type in ("source", "synthesis"):
                content = _render_source_page(extraction)
            elif page_type == "entity" and slug in entities_by_slug:
                content = _render_entity_page(entities_by_slug[slug], source_slug, conn_map)
            elif page_type == "concept" and slug in concepts_by_slug:
                content = _render_concept_page(concepts_by_slug[slug], source_slug, conn_map)
            else:
                logger.warning("No data found for %s '%s', skipping", page_type, slug)
                continue

            _write_file(path, content)
            written_pages.append(path)

            if monitor:
                page_slug = path.replace("wiki/", "").replace("/", "_").replace(".md", "")
                dump_path = os.path.join(dump_dir, f"3_writer_input_{page_slug}.json")
                with open(dump_path, "w", encoding="utf-8") as df:
                    json.dump({"path": path, "page_type": page_type}, df, indent=2, ensure_ascii=False)

        # Process updates
        for entry in pages_to_update:
            path = entry["path"]
            logger.info("Updating: %s", path)

            existing = _read_file(path)
            if not existing:
                logger.warning("Page not found for update: %s, skipping", path)
                continue

            content = _render_update(existing, extraction, entry, source_slug)
            _write_file(path, content)
            written_pages.append(path)

        elapsed = time.time() - t0
        logger.info("Writer complete: %d page(s) written (%.3fs)", len(written_pages), elapsed)
        await ctx.send_message(json.dumps({"written_pages": written_pages, "extraction": extraction}))
