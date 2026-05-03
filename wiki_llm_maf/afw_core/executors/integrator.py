"""Executor: runs WikiIntegratorAgent for a single extraction."""

from __future__ import annotations

import json
import logging
import time

from agent_framework import Executor, handler, WorkflowContext

from ..agents import wiki_integrator
from ..tools.wiki_read import read_wiki_page, read_index
from ..tools.wiki_list import list_wiki_pages

logger = logging.getLogger(__name__)


class IntegratorExecutor(Executor):
    """Runs the integrator agent on one extraction to produce a plan."""

    def __init__(self, client, options):
        super().__init__(id="integrator")
        self._client = client
        self._options = options

    @handler
    async def handle(self, input: str, ctx: WorkflowContext[str]) -> None:
        data = json.loads(input)
        extraction: dict = data.get("extraction", {})
        if not extraction:
            logger.warning("No extraction to integrate.")
            await ctx.send_message(json.dumps({"plan": {}, "extraction": {}}))
            return

        tools = [read_index, read_wiki_page, list_wiki_pages]
        agent = wiki_integrator.create_agent(self._client, self._options, tools)

        title = extraction.get("title", extraction.get("file_name", "unknown"))
        logger.info("Integrating: %s", title)
        t0 = time.time()

        prompt = f"SOURCE EXTRACTION:\n```json\n{json.dumps(extraction, indent=2)}\n```"
        result = await agent.run(prompt)

        text = result.final_output if hasattr(result, "final_output") else str(result)
        text = text.strip()
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:])
        if text.endswith("```"):
            text = text[: text.rfind("```")]
        text = text.strip()

        plan = json.loads(text)
        pages_to_create = plan.get("pages_to_create", [])
        pages_to_update = plan.get("pages_to_update", [])
        elapsed = time.time() - t0
        logger.info("Plan: %d create, %d update (%.1fs)", len(pages_to_create), len(pages_to_update), elapsed)
        logger.debug("Plan detail: %s", json.dumps(plan, indent=2)[:1000])

        await ctx.send_message(json.dumps({"plan": plan, "extraction": extraction}))
