"""Executor: integrator — produces an integration plan.

Uses a single LLM call to map new entity/concept slugs to existing wiki pages
(semantic dedup), then deterministically routes to create or update.
When the wiki is empty or no LLM client is available, everything is routed to create.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time

from agent_framework import Executor, handler, WorkflowContext

from ..agents import slug_mapper
from ..models.slug_mapping import SlugMapping
from ..console import console

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _normalize_slug(slug: str) -> str:
    """Normalize a slug for comparison: camelCase/PascalCase/underscores → kebab-case.

    Examples:
        openaiChatClient → openai-chat-client
        openai_chat_client → openai-chat-client
        OpenAIChatClient → open-ai-chat-client  (close enough for matching)
    """
    # Split camelCase/PascalCase
    s = _CAMEL_RE.sub("-", slug)
    # Replace underscores with hyphens
    s = s.replace("_", "-")
    # Lowercase, collapse multiple hyphens, strip edges
    s = re.sub(r"-+", "-", s.lower()).strip("-")
    return s


def _pre_filter_slugs(
    new_slugs: list[str], existing_slugs: list[str]
) -> tuple[dict[str, str], list[str]]:
    """Deterministically match new slugs to existing ones via normalization.

    Returns:
        auto_map: {new_slug: existing_slug} for deterministic matches
        remaining: new slugs that need LLM mapping
    """
    existing_normalized = {_normalize_slug(s): s for s in existing_slugs}
    auto_map: dict[str, str] = {}
    remaining: list[str] = []

    for slug in new_slugs:
        norm = _normalize_slug(slug)
        if norm in existing_normalized and existing_normalized[norm] != slug:
            auto_map[slug] = existing_normalized[norm]
        elif slug in existing_slugs:
            # Exact match — will be caught as existing, route to update
            auto_map[slug] = slug
        else:
            remaining.append(slug)

    return auto_map, remaining


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
    """Single LLM call to map new slugs to existing ones (structured output)."""
    prompt = (
        f"EXISTING entity pages: {json.dumps(existing_entity_slugs)}\n"
        f"EXISTING concept pages: {json.dumps(existing_concept_slugs)}\n\n"
        f"NEW entity slugs to map: {json.dumps(new_entity_slugs)}\n"
        f"NEW concept slugs to map: {json.dumps(new_concept_slugs)}"
    )

    agent = slug_mapper.create_agent(client, options)

    try:
        result = await agent.run(prompt, options={"response_format": SlugMapping})
        mapping: SlugMapping = result.value
        return {
            "entity_mapping": mapping.entity_mapping,
            "concept_mapping": mapping.concept_mapping,
        }
    except Exception:
        logger.warning("Structured slug mapping failed, falling back to all-NEW", exc_info=True)
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
        logger.debug("Integrating: %s", title)
        console.detail(f"Integrating: {title}")
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

        if has_existing and has_new:
            # Phase 1: deterministic pre-filter (normalize slugs)
            entity_auto, entity_remaining = _pre_filter_slugs(new_entity_slugs, existing_entity_slugs)
            concept_auto, concept_remaining = _pre_filter_slugs(new_concept_slugs, existing_concept_slugs)

            if entity_auto or concept_auto:
                logger.debug(
                    "Pre-filter matched: %d entities, %d concepts (deterministic)",
                    len(entity_auto), len(concept_auto),
                )
                console.detail(f"Pre-filter matched: {len(entity_auto)} entities, {len(concept_auto)} concepts (deterministic)")
            entity_map.update(entity_auto)
            concept_map.update(concept_auto)

            # Phase 2: LLM mapping for remaining slugs
            if (entity_remaining or concept_remaining) and self._client:
                logger.debug(
                    "LLM slug mapping: %d+%d remaining vs %d+%d existing",
                    len(entity_remaining), len(concept_remaining),
                    len(existing_entity_slugs), len(existing_concept_slugs),
                )
                console.detail(f"LLM slug mapping: {len(entity_remaining)}+{len(concept_remaining)} remaining vs {len(existing_entity_slugs)}+{len(existing_concept_slugs)} existing")
                mapping = await _llm_slug_mapping(
                    self._client, self._options,
                    entity_remaining, concept_remaining,
                    existing_entity_slugs, existing_concept_slugs,
                )
                entity_map.update(mapping.get("entity_mapping", {}))
                concept_map.update(mapping.get("concept_mapping", {}))
                logger.debug("Mapping result: %s", json.dumps(mapping))
                console.detail(f"Mapping result: {json.dumps(mapping)}")
            elif entity_remaining or concept_remaining:
                logger.info("No LLM client — remaining slugs will be created.")
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
                logger.debug("Entity merge: '%s' → '%s'", slug, mapped)
                console.detail(f"Entity merge: '{slug}' → '{mapped}'")
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
                logger.debug("Concept merge: '%s' → '%s'", slug, mapped)
                console.detail(f"Concept merge: '{slug}' → '{mapped}'")
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
        logger.debug("Plan: %d create, %d update (%.3fs)", len(pages_to_create), len(pages_to_update), elapsed)
        console.info(f"Plan: {len(pages_to_create)} create, {len(pages_to_update)} update ({elapsed:.3f}s)")

        # --- MONITOR: dump plan ---
        from ..logging_config import is_monitor_enabled, get_diagnostics_dir
        if is_monitor_enabled():
            dump_dir = get_diagnostics_dir()
            dump_path = os.path.join(dump_dir, f"2_plan_{source_slug}.json")
            with open(dump_path, "w", encoding="utf-8") as df:
                json.dump(plan, df, indent=2, ensure_ascii=False)
            logger.info("MONITOR: plan → %s", dump_path)

        await ctx.send_message(json.dumps({"plan": plan, "extraction": extraction}))
