"""Executor: loop controller for per-source ingest.

Receives the file list from Scanner (first call) or a cycle-complete signal
from IndexUpdater (subsequent calls). Pops one file at a time and sends it
forward. When no files remain, yields output to end the workflow.
"""

from __future__ import annotations

import json
import logging

from agent_framework import Executor, handler, WorkflowContext

logger = logging.getLogger(__name__)


class DispatcherExecutor(Executor):
    """Manages the per-source loop. Holds file queue in instance state."""

    def __init__(self):
        super().__init__(id="dispatcher")
        self._files: list[str] = []
        self._processed: int = 0
        self._total: int = 0

    @handler
    async def handle(self, input: str, ctx: WorkflowContext[str]) -> None:
        data = json.loads(input)

        # First call: receives file list from Scanner
        if "new_files" in data:
            self._files = list(data["new_files"])
            self._total = len(self._files)
            self._processed = 0
            if not self._files:
                logger.info("No new files to ingest.")
                await ctx.yield_output(json.dumps({"status": "complete", "processed": 0}))
                return

        # Subsequent calls: IndexUpdater signals cycle complete
        # (the payload may contain cycle results, but we just need to advance)

        if not self._files:
            # All files processed — end the workflow
            logger.info("All %d source(s) processed.", self._total)
            await ctx.yield_output(json.dumps({
                "status": "complete",
                "processed": self._processed,
            }))
            return

        # Pop next file and send it forward
        next_file = self._files.pop(0)
        self._processed += 1
        fname = next_file.rsplit('/', 1)[-1].rsplit(chr(92), 1)[-1]
        logger.info("[%d/%d] Dispatching: %s", self._processed, self._total, fname)

        await ctx.send_message(json.dumps({"file_path": next_file}))
