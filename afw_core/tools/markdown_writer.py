"""Write assembled Markdown content to disk."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

from agent_framework import tool

logger = logging.getLogger(__name__)


@tool
def write_markdown(
    output_path: Annotated[str, "File path where the Markdown file will be saved"],
    content: Annotated[str, "Markdown text to write"],
) -> str:
    """Write Markdown content to a file on disk. Returns the path of the written file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    logger.info("Wrote: %s", path)
    return str(path)
