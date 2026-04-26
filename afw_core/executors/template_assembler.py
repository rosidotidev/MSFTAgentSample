"""Workflow executor that wraps the TemplateAssembler agent."""

from agent_framework import Executor, WorkflowContext, handler

from afw_core.agents.template_assembler import create_agent


class TemplateAssemblerExecutor(Executor):

    def __init__(self, client, options):
        super().__init__(id="template_assembler")
        self._agent = create_agent(client=client, options=options)

    @handler
    async def handle(self, descriptions_json: str, ctx: WorkflowContext[str]) -> None:
        extraction_json = ctx.get_state("extraction")
        output_dir = ctx.get_state("output_dir")
        prompt = (
            f"extraction:\n{extraction_json}\n\n"
            f'output_dir="{output_dir}"'
        )
        response = await self._agent.run(prompt)
        await ctx.send_message(response.text)
