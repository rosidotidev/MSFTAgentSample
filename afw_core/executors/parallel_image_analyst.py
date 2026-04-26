"""Workflow executor that analyses images in parallel via asyncio.gather.

Wraps the same describe_images logic but fires all vision calls concurrently
instead of sequentially.  Saves descriptions to workflow state like the
stateful variant.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from pathlib import Path
from typing import Never

from agent_framework import Executor, WorkflowContext, handler
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

VISION_MODEL = os.getenv("VISION_MODEL", "gpt-4o-mini")
MAX_CONCURRENT = int(os.getenv("VISION_MAX_CONCURRENT", "5"))


def _encode_image(image_path: str | Path) -> str:
    return base64.b64encode(Path(image_path).read_bytes()).decode("utf-8")


async def _describe_image_async(
    aclient: AsyncOpenAI,
    image_path: str,
    context: str,
    semaphore: asyncio.Semaphore,
) -> dict:
    """Call GPT-4o-mini vision for a single image, respecting concurrency."""
    async with semaphore:
        b64 = _encode_image(image_path)
        ext = Path(image_path).suffix.lstrip(".").lower()
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "gif": "image/gif"}.get(ext, "image/png")

        system_prompt = (
            "You are a technical document analyst. Provide a DETAILED and THOROUGH "
            "description of the image content. Be exhaustive — do not summarise, describe "
            "everything visible. "
            "First, identify what type of visual this is: screenshot, UI mockup, UML diagram, "
            "architecture diagram, flowchart, sequence diagram, network topology, ERD, "
            "wireframe, chart, graph, table, photograph, or other. "
            "Then structure your response with: "
            "1) A 2-3 sentence overview of what the image represents and its purpose. "
            "2) Every visible element — nodes, boxes, panels, sections, columns, rows, "
            "shapes, actors, swimlanes, regions — describe each one individually. "
            "3) ALL visible text, labels, values, annotations, placeholders, buttons, "
            "menu items, status indicators, badges, and legends — transcribe them exactly "
            "as shown, omit nothing. "
            "4) Relationships and flow: arrows, connectors, lines, dependencies, "
            "sequence order, hierarchy, data flow direction. "
            "5) Layout, spatial relationships, colours, icons, borders, groupings, "
            "and any visual cue that carries meaning. "
            "Use Markdown headings and bullet points. Be verbose. "
            "Omit speculation; describe only what is visible."
        )

        user_content = []
        if context:
            user_content.append({
                "type": "text",
                "text": (
                    f"This image appears in a document near the following text:\n\n"
                    f"{context}\n\nDescribe what the image shows:"
                ),
            })
        else:
            user_content.append({"type": "text", "text": "Describe what this image shows in detail:"})

        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"},
        })

        logger.info("Describing image (async): %s", image_path)
        response = await aclient.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            max_tokens=2048,
        )
        description = response.choices[0].message.content.strip()
        logger.info("Done: %s (len=%d)", image_path, len(description))

        return {
            "path": image_path,
            "context": context,
            "description": description,
        }


class ParallelImageAnalystExecutor(Executor):
    """Analyses all images in parallel using AsyncOpenAI, no agent needed."""

    def __init__(self):
        super().__init__(id="parallel_image_analyst")

    @handler
    async def handle(self, extraction_json: str, ctx: WorkflowContext[Never, str]) -> None:
        # Collect all images from all documents
        data = json.loads(extraction_json)
        documents = data if isinstance(data, list) else [data]

        all_images: list[dict] = []
        for doc in documents:
            for img in doc.get("images", []):
                path = img["path"]
                if Path(path).exists():
                    all_images.append(img)
                else:
                    logger.warning("Image not found, skipping: %s", path)

        if not all_images:
            result = json.dumps({"images": []})
            ctx.set_state("descriptions", result)
            await ctx.send_message(result)
            return

        # Fire all vision calls concurrently (bounded by semaphore)
        aclient = AsyncOpenAI()
        semaphore = asyncio.Semaphore(MAX_CONCURRENT)

        tasks = [
            _describe_image_async(aclient, img["path"], img.get("context", ""), semaphore)
            for img in all_images
        ]
        results = await asyncio.gather(*tasks)

        result_json = json.dumps({"images": list(results)}, ensure_ascii=False)
        ctx.set_state("descriptions", result_json)
        await ctx.send_message(result_json)
