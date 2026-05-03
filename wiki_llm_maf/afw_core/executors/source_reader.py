"""Executor: reads a single source file and extracts structured data via SourceReaderAgent."""

from __future__ import annotations

import json
import logging
import os
import time

from agent_framework import Executor, handler, WorkflowContext

from ..agents import source_reader
from ..models.extraction import SourceExtraction

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
        agent = source_reader.create_agent(self._client, self._options)

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        prompt = f"FILE: {fname}\n\n{content}"
        result = await agent.run(prompt, options={"response_format": SourceExtraction})

        extraction = result.value.model_dump() if result.value else json.loads(result.final_output)
        extraction["_source_path"] = file_path
        # Tag origin so Integrator knows where it came from
        if "questions_approved" in file_path.replace("\\", "/"):
            extraction["_origin"] = "questions_approved"
        else:
            extraction["_origin"] = "raw"

        elapsed = time.time() - t0
        logger.info("Extraction complete: %s (%.1fs)", extraction.get('title', fname), elapsed)
        logger.debug("Entities: %d, Concepts: %d", len(extraction.get('entities', [])), len(extraction.get('concepts', [])))
        await ctx.send_message(json.dumps({"extraction": extraction}))
