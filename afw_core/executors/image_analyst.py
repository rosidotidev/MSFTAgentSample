"""Workflow executor that wraps the ImageAnalyst agent."""

from agent_framework import Executor, WorkflowContext, handler

from afw_core.agents.image_analyst import create_agent
from afw_core.tools.image_describer import describe_images


class ImageAnalystExecutor(Executor):

    def __init__(self, client, options):
        super().__init__(id="image_analyst")
        self._agent = create_agent(
            client=client, options=options, tools=[describe_images],
        )

    @handler
    async def handle(self, extraction_json: str, ctx: WorkflowContext[str]) -> None:
        response = await self._agent.run(extraction_json)
        await ctx.send_message(response.text)
