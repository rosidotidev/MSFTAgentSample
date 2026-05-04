"""Executor: integrator — produces an integration plan.

Uses a single LLM call to map new entity/concept slugs to existing wiki pages
(semantic dedup), then deterministically routes to create or update.
When the wiki is empty or no LLM client is available, everything is routed to create.
"""

from __future__ import annotations

import json
import logging
import os
import time

from agent_framework import Agent, Executor, handler, WorkflowContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM prompt for slug mapping (single call)
# ---------------------------------------------------------------------------

_MAPPING_INSTRUCTIONS = """\
You are a wiki deduplication assistant. Given a list of EXISTING wiki page slugs \
and NEW slugs extracted from a source, map each new slug to the most semantically \
equivalent existing slug, or mark it as "NEW" if no good match exists.

Rules:
- Match only when the new item clearly covers the SAME topic as the existing page.
- Partial keyword overlap is NOT enough. "mcp-integration" and "mcp-server-proxies" \
  are different topics unless they truly cover the same concept.
- Plural/singular variants are a match (e.g., "tool" ↔ "tools").
- A more specific slug can match a more general one if they cover the same ground \
  (e.g., "tools" → "custom-function-tools" when both are about the tool system).
- When in doubt, return "NEW". Creating a duplicate is cheaper than merging unrelated topics.

Respond with ONLY a valid JSON object (no markdown fences, no commentary):
{
  "entity_mapping": {"<new-slug>": "<existing-slug or NEW>", ...},
  "concept_mapping": {"<new-slug>": "<existing-slug or NEW>", ...}
}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wiki_base_dir() -> str:
    default = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.environ.get("WIKI_ROOT_DIR", default)


def _existing_wiki_pages() -> set[str]:
    """Return set of relative paths like 'wiki/entities/agent-framework.md'."""
    base = _wiki_base_dir()
    wiki_dir = os.path.join(base, "wiki")
    pages: set[str] = set()
    if not os.path.isdir(wiki_dir):
        return pages
    for root, _dirs, files in os.walk(wiki_dir):
        for f in files:
            if f.endswith(".md") and f not in ("index.md", "log.md"):
                rel = os.path.relpath(os.path.join(root, f), base).replace("\\", "/")
                pages.add(rel)
    return pages


def _slugs_in_folder(existing: set[str], folder: str) -> list[str]:
    """Extract sorted slug list from existing paths for a given folder."""
    prefix = f"wiki/{folder}/"
    return sorted(
        p[len(prefix):-3]
        for p in existing
        if p.startswith(prefix) and p.endswith(".md")
    )


async def _llm_slug_mapping(
    client,
    options,
    new_entity_slugs: list[str],
    new_concept_slugs: list[str],
    existing_entity_slugs: list[str],
    existing_concept_slugs: list[str],
) -> dict:
    """Single LLM call to map new slugs to existing ones."""
    prompt = (
        f"EXISTING entity pages: {json.dumps(existing_entity_slugs)}\n"
        f"EXISTING concept pages: {json.dumps(existing_concept_slugs)}\n\n"
        f"NEW entity slugs to map: {json.dumps(new_entity_slugs)}\n"
        f"NEW concept slugs to map: {json.dumps(new_concept_slugs)}"
    )

    agent = Agent(
        name="SlugMapper",
        instructions=_MAPPING_INSTRUCTIONS,
        client=client,
        default_options=options,
        tools=[],
    )

    result = await agent.run(prompt)
    text = result.final_output.strip()

    # Strip markdown fences if present
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
    if text.endswith("```"):
        text = text[: text.rfind("```")]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("LLM slug mapping returned invalid JSON, falling back to all-NEW")
        return {
            "entity_mapping": {s: "NEW" for s in new_entity_slugs},
            "concept_mapping": {s: "NEW" for s in new_concept_slugs},
        }


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

class IntegratorExecutor(Executor):
    """Integrator: 1 LLM call for semantic slug mapping, then deterministic plan."""

    def __init__(self, client=None, options=None):
        super().__init__(id="integrator")
        self._client = client
        self._options = options

    @handler
    async def handle(self, input: str, ctx: WorkflowContext[str]) -> None:
        data = json.loads(input)
        extraction: dict = data.get("extraction", {})
        if not extraction:
            logger.warning("No extraction to integrate.")
            await ctx.send_message(json.dumps({"plan": {}, "extraction": {}}))
            return

        title = extraction.get("title", extraction.get("file_name", "unknown"))
        logger.info("Integrating: %s", title)
        t0 = time.time()

        existing = _existing_wiki_pages()
        pages_to_create: list[dict] = []
        pages_to_update: list[dict] = []

        # --- Source page (always create / replace) ---
        source_slug = extraction.get("slug", "unknown")
        origin = extraction.get("_origin", "raw")
        source_path = (
            f"wiki/synthesis/{source_slug}.md"
            if origin == "questions_approved"
            else f"wiki/sources/{source_slug}.md"
        )
        if source_path in existing:
            pages_to_update.append({
                "path": source_path,
                "action": "replace",
                "detail": "Re-ingested source, replace content.",
            })
        else:
            pages_to_create.append({
                "path": source_path,
                "page_type": "source" if origin == "raw" else "synthesis",
                "content_brief": extraction.get("summary", title),
            })

        # --- Collect slugs ---
        new_entity_slugs = [e["slug"] for e in extraction.get("entities", []) if e.get("slug")]
        new_concept_slugs = [c["slug"] for c in extraction.get("concepts", []) if c.get("slug")]
        existing_entity_slugs = _slugs_in_folder(existing, "entities")
        existing_concept_slugs = _slugs_in_folder(existing, "concepts")

        # --- LLM slug mapping (skip when wiki empty or no new items) ---
        entity_map: dict[str, str] = {}
        concept_map: dict[str, str] = {}

        has_existing = existing_entity_slugs or existing_concept_slugs
        has_new = new_entity_slugs or new_concept_slugs

        if has_existing and has_new and self._client:
            logger.info(
                "LLM slug mapping: %d+%d new vs %d+%d existing",
                len(new_entity_slugs), len(new_concept_slugs),
                len(existing_entity_slugs), len(existing_concept_slugs),
            )
            mapping = await _llm_slug_mapping(
                self._client, self._options,
                new_entity_slugs, new_concept_slugs,
                existing_entity_slugs, existing_concept_slugs,
            )
            entity_map = mapping.get("entity_mapping", {})
            concept_map = mapping.get("concept_mapping", {})
            logger.info("Mapping result: %s", json.dumps(mapping))
        else:
            logger.info("No existing pages or no LLM — all items will be created.")

        # --- Entities: apply mapping, rename slugs in extraction ---
        existing_entity_set = set(existing_entity_slugs)
        for entity in extraction.get("entities", []):
            slug = entity.get("slug", "")
            if not slug:
                continue
            mapped = entity_map.get(slug)
            if mapped and mapped != "NEW" and mapped in existing_entity_set:
                logger.info("Entity merge: '%s' → '%s'", slug, mapped)
                entity["_original_slug"] = slug
                entity["slug"] = mapped          # rename so writer finds it
                pages_to_update.append({
                    "path": f"wiki/entities/{mapped}.md",
                    "action": "enrich",
                    "detail": f"Add info from new source: {entity.get('description', '')}",
                })
            else:
                pages_to_create.append({
                    "path": f"wiki/entities/{slug}.md",
                    "page_type": "entity",
                    "content_brief": entity.get("description", entity.get("name", slug)),
                })

        # --- Concepts: apply mapping, rename slugs in extraction ---
        existing_concept_set = set(existing_concept_slugs)
        for concept in extraction.get("concepts", []):
            slug = concept.get("slug", "")
            if not slug:
                continue
            mapped = concept_map.get(slug)
            if mapped and mapped != "NEW" and mapped in existing_concept_set:
                logger.info("Concept merge: '%s' → '%s'", slug, mapped)
                concept["_original_slug"] = slug
                concept["slug"] = mapped         # rename so writer finds it
                pages_to_update.append({
                    "path": f"wiki/concepts/{mapped}.md",
                    "action": "enrich",
                    "detail": f"Add info from new source: {concept.get('definition', '')}",
                })
            else:
                pages_to_create.append({
                    "path": f"wiki/concepts/{slug}.md",
                    "page_type": "concept",
                    "content_brief": concept.get("definition", concept.get("name", slug)),
                })

        plan = {
            "pages_to_create": pages_to_create,
            "pages_to_update": pages_to_update,
            "contradictions": [],
            "new_cross_references": [],
        }

        elapsed = time.time() - t0
        logger.info("Plan: %d create, %d update (%.3fs)", len(pages_to_create), len(pages_to_update), elapsed)

        # --- MONITOR: dump plan ---
        from ..logging_config import is_monitor_enabled, get_diagnostics_dir
        if is_monitor_enabled():
            dump_dir = get_diagnostics_dir()
            dump_path = os.path.join(dump_dir, f"2_plan_{source_slug}.json")
            with open(dump_path, "w", encoding="utf-8") as df:
                json.dump(plan, df, indent=2, ensure_ascii=False)
            logger.info("MONITOR: plan → %s", dump_path)

        await ctx.send_message(json.dumps({"plan": plan, "extraction": extraction}))
