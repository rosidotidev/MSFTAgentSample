"""Describe images using OpenAI GPT-4o mini vision."""

from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Annotated

from agent_framework import tool
from openai import OpenAI

logger = logging.getLogger(__name__)

VISION_MODEL = os.getenv("VISION_MODEL", "gpt-4o-mini")


def _encode_image(image_path: str | Path) -> str:
    """Read an image file and return its base64-encoded string."""
    return base64.b64encode(Path(image_path).read_bytes()).decode("utf-8")


def _describe_image(image_path: str | Path, context: str = "") -> str:
    """Send an image to GPT-4o mini and get a textual description."""
    client = OpenAI()
    b64 = _encode_image(image_path)
    ext = Path(image_path).suffix.lstrip(".").lower()
    mime = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
    }.get(ext, "image/png")

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
                f"This image appears in a document near the following text:\n\n{context}\n\n"
                "Describe what the image shows:"
            ),
        })
    else:
        user_content.append({
            "type": "text",
            "text": "Describe what this image shows in detail:",
        })

    user_content.append({
        "type": "image_url",
        "image_url": {"url": f"data:{mime};base64,{b64}"},
    })

    response = client.chat.completions.create(
        model=VISION_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        max_tokens=2048,
    )

    return response.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# MAF tool
# ---------------------------------------------------------------------------


@tool
def describe_images(
    images: Annotated[
        str,
        "JSON string with an array of objects, each having 'path' (file path) and 'context' (surrounding text)",
    ],
) -> str:
    """Analyse images via LLM Vision and return structured textual descriptions.

    Returns a JSON object with an 'images' array. Each element has 'path', 'context', 'description'.
    """
    data = json.loads(images)
    results = []
    for img in data:
        path = img["path"]
        if not Path(path).exists():
            logger.warning("Image not found, skipping: %s", path)
            continue
        logger.info("Describing image: %s", path)
        description = _describe_image(path, context=img.get("context", ""))
        logger.info("=== VISION OUTPUT for %s (len=%d) ===", path, len(description))
        logger.debug("VISION DESCRIPTION:\n%s", description)
        results.append({
            "path": path,
            "context": img.get("context", ""),
            "description": description,
        })
    return json.dumps({"images": results}, ensure_ascii=False)
