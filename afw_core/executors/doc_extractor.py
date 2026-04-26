"""Workflow executor that wraps the DocExtractor agent."""

from agent_framework import Executor, WorkflowContext, handler

from afw_core.agents.doc_extractor import create_agent
from afw_core.tools.docx_extractor import extract_docx_files


class DocExtractorExecutor(Executor):

    def __init__(self, client, options, output_dir: str):
        super().__init__(id="doc_extractor")
        self._agent = create_agent(
            client=client, options=options, tools=[extract_docx_files],
        )
        self._output_dir = output_dir

    @handler
    async def handle(self, prompt: str, ctx: WorkflowContext[str]) -> None:
        response = await self._agent.run(prompt)
        # Save extraction and output_dir in state for the assembler (Step 3)
        ctx.set_state("extraction", response.text)
        ctx.set_state("output_dir", self._output_dir)
        await ctx.send_message(response.text)
