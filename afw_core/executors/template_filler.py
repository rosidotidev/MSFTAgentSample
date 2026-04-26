"""Workflow executor that fills image placeholders into Markdown templates.

Pure Python — no LLM involved. Replaces <!--IMG:filename--> placeholders
with formatted image descriptions and writes the final .md files to disk.
"""

import json
import logging
import re
from pathlib import Path
from typing import Never

from agent_framework import Executor, WorkflowContext, handler

logger = logging.getLogger(__name__)


def _build_description_map(descriptions_json: str) -> dict[str, str]:
    """Build a filename → formatted description mapping."""
    data = json.loads(descriptions_json)
    images = data.get("images", [])
    desc_map: dict[str, str] = {}
    for img in images:
        filename = Path(img["path"]).name
        description = img.get("description", "")
        if description:
            formatted = (
                f"**[Image Description]:** {description}\n"
                f"**[End Image Description]**"
            )
            desc_map[filename] = formatted
    return desc_map


_PLACEHOLDER_RE = re.compile(r"<!--IMG:([\w.\-]+)-->")


class TemplateFillerExecutor(Executor):

    def __init__(self):
        super().__init__(id="template_filler")

    @handler
    async def handle(self, template_json: str, ctx: WorkflowContext[Never, str]) -> None:
        descriptions_json = ctx.get_state("descriptions")
        output_dir = ctx.get_state("output_dir")
        desc_map = _build_description_map(descriptions_json)

        data = json.loads(template_json)
        documents = data.get("documents", [])
        results = []

        for doc in documents:
            content = doc.get("content", "")
            output_path = doc.get("output_path", "")
            source_file = doc.get("source_file", "")

            # Replace each <!--IMG:filename--> with the formatted description
            def _replace(match: re.Match) -> str:
                fname = match.group(1)
                replacement = desc_map.get(fname)
                if replacement is None:
                    logger.warning("No description found for %s", fname)
                    return match.group(0)  # leave placeholder as-is
                return replacement

            filled = _PLACEHOLDER_RE.sub(_replace, content)

            # Write to disk
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(filled, encoding="utf-8")
            logger.info("Wrote: %s", path)

            results.append({
                "source_file": source_file,
                "output_path": output_path,
                "content": filled,
            })

        result_json = json.dumps({"documents": results}, ensure_ascii=False)
        await ctx.yield_output(result_json)
