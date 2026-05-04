"""Executor: reads a single source file and extracts structured data via SourceReaderAgent.

Supports chunked extraction: long documents are split into logical sections,
each extracted independently, then merged into a single extraction.
"""

from __future__ import annotations

import json
import logging
import os
import time

from agent_framework import Executor, handler, WorkflowContext

from ..agents import source_reader
from ..models.extraction import SourceExtraction
from .splitter import split_document, split_document_with_llm

logger = logging.getLogger(__name__)


class SourceReaderExecutor(Executor):
    """Reads one file and produces a single extraction."""

    def __init__(self, client, options):
        super().__init__(id="source_reader")
        self._client = client
        self._options = options

    @handler
    async def handle(self, input: str, ctx: WorkflowContext[str]) -> None:
        data = json.loads(input)
        file_path: str = data["file_path"]
        fname = os.path.basename(file_path)

        logger.info("Reading: %s", fname)
        logger.debug("Input: %s", input[:500])
        t0 = time.time()

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # --- Split into chunks ---
        doc_title = fname.replace(".md", "")
        chunks = split_document(content, title=doc_title)

        # If deterministic split returned a single chunk and doc is large, try LLM split
        if len(chunks) == 1 and content.count("\n") > 60:
            logger.info("Document has no headings and is large — using LLM split")
            chunks = await split_document_with_llm(
                content, doc_title, self._client, self._options
            )

        logger.info("Processing %d chunk(s) for: %s", len(chunks), fname)

        # --- Extract each chunk (parallel) ---
        async def _extract_chunk(i: int, chunk: str) -> dict | None:
            agent = source_reader.create_agent(self._client, self._options)
            prompt = f"FILE: {fname} (chunk {i+1}/{len(chunks)})\n\n{chunk}"
            try:
                result = await agent.run(prompt, options={"response_format": SourceExtraction})
                ext = result.value.model_dump() if result.value else json.loads(result.final_output)
            except Exception as e:
                logger.warning("Chunk %d/%d structured extraction failed (%s), retrying without response_format",
                               i+1, len(chunks), type(e).__name__)
                agent2 = source_reader.create_agent(self._client, self._options)
                result = await agent2.run(prompt)
                text = result.final_output.strip()
                if text.startswith("```"):
                    text = "\n".join(text.split("\n")[1:])
                if text.endswith("```"):
                    text = text[:text.rfind("```")]
                text = text.strip()
                try:
                    ext = json.loads(text)
                except json.JSONDecodeError:
                    logger.error("Chunk %d/%d: JSON parse failed, skipping", i+1, len(chunks))
                    return None
            logger.debug("Chunk %d/%d: %d entities, %d concepts",
                         i+1, len(chunks),
                         len(ext.get("entities", [])),
                         len(ext.get("concepts", [])))
            return ext

        import asyncio as _aio
        results = await _aio.gather(*[_extract_chunk(i, chunk) for i, chunk in enumerate(chunks)])
        extractions: list[dict] = [r for r in results if r is not None]

        # --- Merge extractions ---
        if len(extractions) == 1:
            extraction = extractions[0]
        else:
            extraction = _merge_extractions(extractions, fname)

        extraction["_source_path"] = file_path
        # Tag origin so Integrator knows where it came from
        if "questions_approved" in file_path.replace("\\", "/"):
            extraction["_origin"] = "questions_approved"
        else:
            extraction["_origin"] = "raw"

        # --- Consolidate: deterministic dedup & noise filtering ---
        extraction = _consolidate_extraction(extraction)

        elapsed = time.time() - t0
        logger.info("Extraction complete: %s (%.1fs, %d chunks)", extraction.get('title', fname), elapsed, len(chunks))
        logger.debug("Entities: %d, Concepts: %d", len(extraction.get('entities', [])), len(extraction.get('concepts', [])))

        # --- MONITOR: dump extraction ---
        from ..logging_config import is_monitor_enabled, get_diagnostics_dir
        if is_monitor_enabled():
            dump_dir = get_diagnostics_dir()
            slug = extraction.get("slug", fname.replace(".md", ""))
            dump_path = os.path.join(dump_dir, f"1_extraction_{slug}.json")
            with open(dump_path, "w", encoding="utf-8") as df:
                json.dump(extraction, df, indent=2, ensure_ascii=False)
            logger.info("MONITOR: extraction → %s", dump_path)

        await ctx.send_message(json.dumps({"extraction": extraction}))


# ---------------------------------------------------------------------------
# Slug matching utilities
# ---------------------------------------------------------------------------

def _slug_normalize(slug: str) -> str:
    """Strip trailing 's' for plural-insensitive comparison."""
    return slug.rstrip("s") if slug.endswith("s") and len(slug) > 3 else slug


def _is_prefix_match(a: str, b: str) -> bool:
    """True if one slug is a prefix of the other with at most one extra segment."""
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    if not long.startswith(short):
        return False
    remainder = long[len(short):]
    # e.g. "logging" → "logging-module": remainder is "-module" (1 segment)
    return remainder == "" or (remainder.startswith("-") and "-" not in remainder[1:])


def _should_merge_slugs(slug_a: str, slug_b: str) -> bool:
    """Determine if two concept/entity slugs are near-duplicates."""
    if slug_a == slug_b:
        return True
    na, nb = _slug_normalize(slug_a), _slug_normalize(slug_b)
    if na == nb:
        return True
    return _is_prefix_match(na, nb)


def _has_code_block(text: str) -> bool:
    return "```" in text


def _merge_item_into(survivor: dict, absorbed: dict) -> None:
    """Merge absorbed item's content and claims into survivor."""
    abs_content = absorbed.get("content", "")
    surv_content = survivor.get("content", "")
    if abs_content and abs_content not in surv_content:
        survivor["content"] = surv_content + "\n\n" + abs_content
    survivor["claims"] = list(set(survivor.get("claims", []) + absorbed.get("claims", [])))


# ---------------------------------------------------------------------------
# Multi-chunk merge
# ---------------------------------------------------------------------------

def _merge_extractions(extractions: list[dict], fname: str) -> dict:
    """Merge multiple chunk extractions into a single extraction with fuzzy slug matching."""
    # Use the first extraction as base for top-level fields
    base = extractions[0]
    merged = {
        "file_name": fname,
        "slug": base.get("slug", fname.replace(".md", "")),
        "title": base.get("title", fname),
        "summary": base.get("summary", ""),
        "key_takeaways": [],
        "claims": [],
        "entities": [],
        "concepts": [],
    }

    # Collect all takeaways (deduplicate)
    seen_takeaways: set[str] = set()
    for ext in extractions:
        for t in ext.get("key_takeaways", []):
            if t not in seen_takeaways:
                seen_takeaways.add(t)
                merged["key_takeaways"].append(t)

    # Merge claims
    for ext in extractions:
        merged["claims"].extend(ext.get("claims", []))

    # Merge entities with fuzzy slug matching
    merged["entities"] = _fuzzy_merge_items(
        [entity for ext in extractions for entity in ext.get("entities", [])]
    )

    # Merge concepts with fuzzy slug matching
    merged["concepts"] = _fuzzy_merge_items(
        [concept for ext in extractions for concept in ext.get("concepts", [])]
    )

    logger.info("Merged %d extractions → %d entities, %d concepts",
                len(extractions), len(merged["entities"]), len(merged["concepts"]))
    return merged


def _fuzzy_merge_items(items: list[dict]) -> list[dict]:
    """Merge items (entities or concepts) using fuzzy slug matching across chunks.

    Two items are merged if their slugs match exactly, differ only by plural 's',
    or one is a prefix of the other with at most one extra hyphen-segment.
    The item with the longer content becomes the survivor.
    """
    if not items:
        return []

    # Build groups: assign each item to a group by finding a matching existing group key
    groups: dict[str, dict] = {}  # canonical_slug → merged item

    for item in items:
        slug = item.get("slug", "")
        match_key = _find_matching_group(slug, groups)

        if match_key is not None:
            # Merge into existing group
            existing = groups[match_key]
            new_content = item.get("content", "")
            existing_content = existing.get("content", "")
            if new_content and new_content not in existing_content:
                existing["content"] = existing_content + "\n\n" + new_content
            existing["claims"] = list(set(existing.get("claims", []) + item.get("claims", [])))
        else:
            # New group
            groups[slug] = dict(item)

    return list(groups.values())


def _find_matching_group(slug: str, groups: dict[str, dict]) -> str | None:
    """Find a group key that fuzzy-matches the given slug. Returns None if no match."""
    if slug in groups:
        return slug

    norm_slug = _slug_normalize(slug)
    for key in groups:
        if _slug_normalize(key) == norm_slug:
            return key
        if _is_prefix_match(norm_slug, _slug_normalize(key)):
            return key

    return None


# ---------------------------------------------------------------------------
# Post-extraction consolidation — deterministic dedup & noise filtering
# ---------------------------------------------------------------------------

def _dedup_items(items: list[dict]) -> list[dict]:
    """Slug-based and content-overlap dedup for a list of concepts or entities."""
    if len(items) <= 1:
        return items

    # --- Pass 1: slug-based merge ---
    groups: list[list[int]] = []  # groups of indices that should merge
    assigned: set[int] = set()

    for i in range(len(items)):
        if i in assigned:
            continue
        group = [i]
        assigned.add(i)
        for j in range(i + 1, len(items)):
            if j in assigned:
                continue
            if _should_merge_slugs(items[i].get("slug", ""), items[j].get("slug", "")):
                group.append(j)
                assigned.add(j)
        groups.append(group)

    merged: list[dict] = []
    for group in groups:
        # Pick the item with the longest content as survivor
        group.sort(key=lambda idx: len(items[idx].get("content", "")), reverse=True)
        survivor = dict(items[group[0]])
        for idx in group[1:]:
            _merge_item_into(survivor, items[idx])
        merged.append(survivor)

    # --- Pass 2: content substring dedup ---
    final: list[dict] = []
    absorbed_indices: set[int] = set()
    for i in range(len(merged)):
        if i in absorbed_indices:
            continue
        for j in range(i + 1, len(merged)):
            if j in absorbed_indices:
                continue
            ci = merged[i].get("content", "")
            cj = merged[j].get("content", "")
            if ci and cj:
                if ci in cj:
                    _merge_item_into(merged[j], merged[i])
                    absorbed_indices.add(i)
                    break
                elif cj in ci:
                    _merge_item_into(merged[i], merged[j])
                    absorbed_indices.add(j)
        if i not in absorbed_indices:
            final.append(merged[i])
    # Add any remaining items that survived
    for j in range(len(merged)):
        if j not in absorbed_indices and merged[j] not in final:
            final.append(merged[j])

    return final


def _absorb_thin_concepts(concepts: list[dict]) -> list[dict]:
    """Absorb thin concepts (short content, no code) into the most similar surviving concept."""
    if len(concepts) <= 1:
        return concepts

    thin: list[dict] = []
    substantial: list[dict] = []
    for c in concepts:
        content = c.get("content", "")
        if len(content) < 200 and not _has_code_block(content):
            thin.append(c)
        else:
            substantial.append(c)

    if not substantial or not thin:
        return concepts

    for tc in thin:
        tc_norm = _slug_normalize(tc.get("slug", ""))
        # Find the substantial concept with the longest common prefix
        best_idx = -1
        best_prefix_len = 0
        for i, sc in enumerate(substantial):
            sc_norm = _slug_normalize(sc.get("slug", ""))
            # Compute common prefix length
            plen = 0
            for a, b in zip(tc_norm, sc_norm):
                if a == b:
                    plen += 1
                else:
                    break
            if plen > best_prefix_len:
                best_prefix_len = plen
                best_idx = i
        if best_idx >= 0 and best_prefix_len >= 3:
            _merge_item_into(substantial[best_idx], tc)
            logger.debug("Absorbed thin concept '%s' into '%s'",
                         tc.get("slug"), substantial[best_idx].get("slug"))
        else:
            # No good match — keep it
            substantial.append(tc)

    return substantial


def _filter_noise_entities(entities: list[dict]) -> list[dict]:
    """Remove entity noise: type='other', short content, no code."""
    filtered = []
    for e in entities:
        content = e.get("content", "")
        is_noise = (
            e.get("type") == "other"
            and len(content) < 150
            and not _has_code_block(content)
        )
        if is_noise:
            logger.debug("Filtered noise entity: '%s'", e.get("slug"))
        else:
            filtered.append(e)
    return filtered


def _consolidate_extraction(extraction: dict) -> dict:
    """Deterministic post-extraction consolidation: dedup concepts, absorb thin ones, filter entity noise."""
    concepts_before = len(extraction.get("concepts", []))
    entities_before = len(extraction.get("entities", []))

    # Consolidate concepts
    concepts = extraction.get("concepts", [])
    concepts = _dedup_items(concepts)
    concepts = _absorb_thin_concepts(concepts)
    extraction["concepts"] = concepts

    # Consolidate entities
    entities = extraction.get("entities", [])
    entities = _filter_noise_entities(entities)
    entities = _dedup_items(entities)
    extraction["entities"] = entities

    logger.info("Consolidation: concepts %d → %d, entities %d → %d",
                concepts_before, len(concepts), entities_before, len(entities))
    return extraction
