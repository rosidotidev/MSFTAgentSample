"""Workflow executor that assembles Markdown deterministically — no LLM needed.

Converts text_segments directly to Markdown using type-based rules:
  Title      → ## / ### / #### (depth inferred from numbering pattern)
  ListItem   → - bullet
  Table      → as-is (already Markdown from extractor)
  image      → ![Image](./images/fname) + <!--IMG:fname-->
  everything else → paragraph

Output format is identical to TemplateAssemblerExecutor / ChunkedTemplateAssemblerExecutor.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Never

from agent_framework import Executor, WorkflowContext, handler

logger = logging.getLogger(__name__)

# ---- Heading depth heuristics ----
# "6.1.2 Something" → H4,  "6.1 Something" → H3,  "6. Something" or unnumbered → H2
_RE_H4 = re.compile(r"^\d+\.\d+\.\d+")
_RE_H3 = re.compile(r"^\d+\.\d+\s")
_RE_H2 = re.compile(r"^\d+\.\s")


def _heading_prefix(text: str) -> str:
    if _RE_H4.match(text):
        return "####"
    if _RE_H3.match(text):
        return "###"
    return "##"


# ---- Image placeholder extraction ----
_IMAGE_RE = re.compile(r"^\[IMAGE:\s*([\w.\-]+)\]$")


def _segments_to_markdown(text_segments: list[dict]) -> str:
    """Convert a list of text_segments to a Markdown string."""
    lines: list[str] = []
    prev_type: str | None = None

    for seg in text_segments:
        seg_type = seg.get("type", "")
        text = seg.get("text", "").strip()
        if not text:
            continue

        # Close a list group when switching away from ListItem
        if prev_type == "ListItem" and seg_type != "ListItem":
            lines.append("")

        if seg_type == "Title":
            if lines:
                lines.append("")
            prefix = _heading_prefix(text)
            lines.append(f"{prefix} {text}")
            lines.append("")

        elif seg_type == "ListItem":
            lines.append(f"- {text}")

        elif seg_type == "Table":
            if lines and lines[-1] != "":
                lines.append("")
            lines.append(text)
            lines.append("")

        elif seg_type == "image":
            m = _IMAGE_RE.match(text)
            if m:
                fname = m.group(1)
                lines.append(f"![Image](./images/{fname})")
                lines.append(f"<!--IMG:{fname}-->")
                lines.append("")
            else:
                # Fallback: keep the raw placeholder text
                lines.append(text)
                lines.append("")

        else:
            # NarrativeText, Text, UncategorizedText, etc.
            if lines and lines[-1] != "":
                lines.append("")
            lines.append(text)

        prev_type = seg_type

    # Clean up trailing blank lines
    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


# ------------------------------------------------------------------
# Executor
# ------------------------------------------------------------------


class DeterministicAssemblerExecutor(Executor):
    """Pure-Python Markdown assembler — zero LLM calls."""

    def __init__(self):
        super().__init__(id="deterministic_assembler")

    @handler
    async def handle(self, trigger: str, ctx: WorkflowContext[Never, str]) -> None:
        extraction_json = ctx.get_state("extraction")
        output_dir = ctx.get_state("output_dir")

        data = json.loads(extraction_json)
        documents = data if isinstance(data, list) else [data]

        all_results = []

        for doc in documents:
            source_file: str = doc.get("source_file", "unknown.docx")
            text_segments: list[dict] = doc.get("text_segments", [])

            content = _segments_to_markdown(text_segments)

            stem = source_file.rsplit(".", 1)[0] if "." in source_file else source_file
            output_path = f"{output_dir}/{stem}.md"

            logger.info(
                "%s: %d segments → %d chars Markdown",
                source_file, len(text_segments), len(content),
            )

            all_results.append({
                "source_file": source_file,
                "output_path": output_path,
                "content": content,
            })

        result_json = json.dumps({"documents": all_results}, ensure_ascii=False)
        await ctx.send_message(result_json)
