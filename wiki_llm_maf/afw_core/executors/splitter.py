"""Document splitter: deterministic heading-based split with LLM fallback."""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

# --- Configuration ---
MIN_HEADING_COUNT = 2   # Minimum ## headings to use deterministic split
MAX_CHUNKS = 8          # Target maximum number of output chunks
MIN_CHUNK_LINES = 5     # Absolute minimum lines for a standalone chunk


def split_document(content: str, title: str = "") -> list[str]:
    """Split a document into logical chunks using heading-based detection.

    Returns a list of chunk strings, each with a context header.
    """
    h2_count = len(re.findall(r"^## ", content, re.MULTILINE))

    if h2_count >= MIN_HEADING_COUNT:
        logger.info("Deterministic split: %d H2 headings found", h2_count)
        return _split_by_headings(content, title)
    else:
        logger.info("No headings found — returning document as single chunk")
        # No headings and no LLM available at this level → return as-is
        # The LLM fallback is handled by split_document_with_llm() called externally
        return [content]


async def split_document_with_llm(content: str, title: str, client, options) -> list[str]:
    """Use a lightweight LLM call to identify split points when no headings exist."""
    from agent_framework import Agent

    # Build a compact outline: line numbers + first 80 chars of non-empty lines
    lines = content.split("\n")
    outline_lines = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("```"):
            outline_lines.append(f"{i}: {stripped[:80]}")
        if len(outline_lines) > 60:
            outline_lines.append(f"... ({len(lines) - i} more lines)")
            break

    outline = "\n".join(outline_lines)

    agent = Agent(
        name="SplitterAgent",
        instructions=(
            "You split documents into logical sections. "
            "Given a document outline (line_number: text), return ONLY a JSON array of "
            "line numbers where the document should be split. "
            "Each split creates a self-contained section about one topic. "
            "Return 3-15 split points. Example: [0, 25, 58, 102]"
        ),
        client=client,
        default_options=options,
    )

    prompt = f"DOCUMENT: {title}\nTOTAL LINES: {len(lines)}\n\nOUTLINE:\n{outline}"
    result = await agent.run(prompt)

    text = result.final_output.strip()
    # Parse the JSON array
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
    if text.endswith("```"):
        text = text[:text.rfind("```")]
    text = text.strip()

    try:
        split_points = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("LLM split failed to produce valid JSON, returning as single chunk")
        return [content]

    if not isinstance(split_points, list) or len(split_points) < 2:
        return [content]

    # Sort and deduplicate
    split_points = sorted(set(int(p) for p in split_points if isinstance(p, (int, float))))

    # Ensure 0 is included
    if split_points[0] != 0:
        split_points.insert(0, 0)

    # Build chunks from split points
    chunks = []
    for i in range(len(split_points)):
        start = split_points[i]
        end = split_points[i + 1] if i + 1 < len(split_points) else len(lines)
        chunk_lines = lines[start:end]
        chunk_text = "\n".join(chunk_lines).strip()
        if chunk_text:
            header = f"[Document: {title} | Lines {start+1}-{end}]\n\n"
            chunks.append(header + chunk_text)

    logger.info("LLM split produced %d chunks", len(chunks))
    return chunks if chunks else [content]


def _split_by_headings(content: str, title: str) -> list[str]:
    """Split by ## headings, then merge smallest adjacent chunks until <= MAX_CHUNKS."""
    lines = content.split("\n")
    sections = _extract_sections(lines, level=2)

    # Build initial chunks — one per H2 section, no sub-splitting
    raw_chunks: list[tuple[str, str, int]] = []  # (heading, text, line_count)
    for heading, section_lines in sections:
        chunk_text = "\n".join(section_lines).strip()
        if not chunk_text:
            continue
        if len(section_lines) < MIN_CHUNK_LINES and raw_chunks:
            # Tiny section — append to previous
            prev_h, prev_t, prev_n = raw_chunks[-1]
            raw_chunks[-1] = (prev_h, prev_t + "\n\n" + chunk_text, prev_n + len(section_lines))
        else:
            raw_chunks.append((heading, chunk_text, len(section_lines)))

    # Merge smallest adjacent chunks until we have at most MAX_CHUNKS
    while len(raw_chunks) > MAX_CHUNKS:
        # Find the smallest chunk by line count
        min_idx = min(range(len(raw_chunks)), key=lambda i: raw_chunks[i][2])
        # Merge with the smaller neighbor (prefer left, fallback right)
        if min_idx == 0:
            merge_idx = 1
        elif min_idx == len(raw_chunks) - 1:
            merge_idx = min_idx - 1
        else:
            left_size = raw_chunks[min_idx - 1][2]
            right_size = raw_chunks[min_idx + 1][2]
            merge_idx = min_idx - 1 if left_size <= right_size else min_idx + 1

        # Merge: keep the earlier index
        a, b = min(min_idx, merge_idx), max(min_idx, merge_idx)
        h_a, t_a, n_a = raw_chunks[a]
        h_b, t_b, n_b = raw_chunks[b]
        merged_heading = f"{h_a} + {h_b}"
        raw_chunks[a] = (merged_heading, t_a + "\n\n" + t_b, n_a + n_b)
        raw_chunks.pop(b)

    # Format final chunks with context headers
    chunks: list[str] = []
    for heading, text, _ in raw_chunks:
        ctx = f"[Document: {title} | Section: {heading}]\n\n"
        chunks.append(ctx + text)

    return chunks if chunks else [content]


def _extract_sections(lines: list[str], level: int) -> list[tuple[str, list[str]]]:
    """Extract sections at a given heading level, respecting code fences."""
    prefix = "#" * level + " "
    sections: list[tuple[str, list[str]]] = []
    current_heading = "(preamble)"
    current_lines: list[str] = []
    in_fence = False

    for line in lines:
        # Track code fences
        if line.strip().startswith("```"):
            in_fence = not in_fence

        if not in_fence and line.startswith(prefix) and not line.startswith(prefix + "#"):
            # New section starts
            if current_lines:
                sections.append((current_heading, current_lines))
            current_heading = line[len(prefix):].strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_heading, current_lines))

    return sections
