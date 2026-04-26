"""Workflow executor that extracts documents directly — no LLM agent needed.

Calls the extraction functions from docx_extractor directly, bypassing the
agent entirely.  The output format is identical to DocExtractorExecutor.
"""

import json
import logging
from pathlib import Path

from agent_framework import Executor, WorkflowContext, handler

from afw_core.tools.docx_extractor import _extract_all_docx

logger = logging.getLogger(__name__)


class DocExtractorDirectExecutor(Executor):
    """Pure-Python document extraction — zero LLM calls."""

    def __init__(self, input_dir: str, output_dir: str):
        super().__init__(id="doc_extractor_direct")
        self._input_dir = input_dir
        self._output_dir = output_dir

    @handler
    async def handle(self, prompt: str, ctx: WorkflowContext[str]) -> None:
        logger.info(
            "Extracting from %s → %s", self._input_dir, self._output_dir,
        )
        results = _extract_all_docx(
            Path(self._input_dir), Path(self._output_dir),
        )
        result_json = json.dumps(results, ensure_ascii=False)

        ctx.set_state("extraction", result_json)
        ctx.set_state("output_dir", self._output_dir)
        await ctx.send_message(result_json)
