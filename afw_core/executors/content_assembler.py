"""Workflow executor that wraps the ContentAssembler agent."""

from typing import Never

from agent_framework import Executor, WorkflowContext, handler

from afw_core.agents.content_assembler import create_agent
from afw_core.tools.markdown_writer import write_markdown


class ContentAssemblerExecutor(Executor):

    def __init__(self, client, options):
        super().__init__(id="content_assembler")
        self._agent = create_agent(
            client=client, options=options, tools=[write_markdown],
        )

    @handler
    async def handle(self, descriptions_json: str, ctx: WorkflowContext[Never, str]) -> None:
        extraction_json = ctx.get_state("extraction")
        output_dir = ctx.get_state("output_dir")
        prompt = (
            f"extraction:\n{extraction_json}\n\n"
            f"descriptions:\n{descriptions_json}\n\n"
            f'output_dir="{output_dir}"'
        )
        response = await self._agent.run(prompt)
        await ctx.yield_output(response.text)
