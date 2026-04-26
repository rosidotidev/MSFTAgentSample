"""Workflow executor that assembles Markdown templates in chunks.

Splits the extraction data by heading boundaries so that each LLM call
processes a small section (~5-15 paragraphs).  This keeps token usage low
and quality high even for very long documents.
"""

from __future__ import annotations

import json
import logging
from typing import Never

from agent_framework import Agent, Executor, WorkflowContext, handler

from afw_core.agents.template_assembler import create_agent

logger = logging.getLogger(__name__)

# Segment types that signal a new section boundary
_HEADING_TYPES = {"Title", "Header"}


# ------------------------------------------------------------------
# Chunking helpers
# ------------------------------------------------------------------

def _chunk_segments(text_segments: list[dict]) -> list[list[dict]]:
    """Split text_segments into chunks at heading boundaries.

    Each chunk starts with a heading (except possibly the first one if
    the document starts without a heading).  Image placeholders are kept
    with their surrounding text.
    """
    if not text_segments:
        return []

    chunks: list[list[dict]] = []
    current: list[dict] = []

    for seg in text_segments:
        if seg.get("type") in _HEADING_TYPES and current:
            chunks.append(current)
            current = []
        current.append(seg)

    if current:
        chunks.append(current)

    return chunks


def _images_for_chunk(chunk: list[dict], all_images: list[dict]) -> list[dict]:
    """Return only the images referenced in a chunk's [IMAGE: ...] placeholders."""
    referenced: set[str] = set()
    for seg in chunk:
        text = seg.get("text", "")
        if seg.get("type") == "image" and text.startswith("[IMAGE:"):
            fname = text.replace("[IMAGE:", "").replace("]", "").strip()
            referenced.add(fname)
    return [img for img in all_images if _filename(img["path"]) in referenced]


def _filename(path: str) -> str:
    from pathlib import Path as P
    return P(path).name


# ------------------------------------------------------------------
# Executor
# ------------------------------------------------------------------

class ChunkedTemplateAssemblerExecutor(Executor):
    """Processes each document section-by-section to avoid LLM token limits."""

    def __init__(self, client, options):
        super().__init__(id="chunked_template_assembler")
        self._client = client
        self._options = options

    @handler
    async def handle(self, descriptions_json: str, ctx: WorkflowContext[Never, str]) -> None:
        extraction_json = ctx.get_state("extraction")
        output_dir = ctx.get_state("output_dir")

        data = json.loads(extraction_json)
        documents = data if isinstance(data, list) else [data]

        all_results = []

        for doc in documents:
            source_file: str = doc.get("source_file", "unknown.docx")
            text_segments: list[dict] = doc.get("text_segments", [])
            images: list[dict] = doc.get("images", [])

            chunks = _chunk_segments(text_segments)
            logger.info(
                "%s: %d segments → %d chunks",
                source_file, len(text_segments), len(chunks),
            )

            md_parts: list[str] = []

            for i, chunk in enumerate(chunks):
                chunk_images = _images_for_chunk(chunk, images)

                # Build a mini-extraction for just this chunk
                mini_extraction = json.dumps(
                    [{
                        "source_file": source_file,
                        "text_segments": chunk,
                        "images": chunk_images,
                    }],
                    ensure_ascii=False,
                )

                # Fresh agent per chunk (stateless)
                agent = create_agent(client=self._client, options=self._options)
                prompt = (
                    f"extraction:\n{mini_extraction}\n\n"
                    f'output_dir="{output_dir}"\n\n'
                    "IMPORTANT: Return ONLY the Markdown content string for this section, "
                    "NOT the JSON wrapper. No ```markdown fences. Start directly with "
                    "the heading or first paragraph."
                )

                response = await agent.run(prompt)
                md_parts.append(response.text.strip())
                logger.info(
                    "%s chunk %d/%d done (%d chars)",
                    source_file, i + 1, len(chunks), len(response.text),
                )

            # Combine all chunks into the final document
            stem = source_file.rsplit(".", 1)[0] if "." in source_file else source_file
            output_path = f"{output_dir}/{stem}.md"
            full_content = "\n\n".join(md_parts)

            all_results.append({
                "source_file": source_file,
                "output_path": output_path,
                "content": full_content,
            })

        result_json = json.dumps({"documents": all_results}, ensure_ascii=False)
        await ctx.send_message(result_json)
