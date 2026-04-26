"""Workflow executor that wraps the ImageAnalyst agent and saves descriptions to state."""

from agent_framework import Executor, WorkflowContext, handler

from afw_core.agents.image_analyst import create_agent
from afw_core.tools.image_describer import describe_images


class ImageAnalystStatefulExecutor(Executor):

    def __init__(self, client, options):
        super().__init__(id="image_analyst_stateful")
        self._agent = create_agent(
            client=client, options=options, tools=[describe_images],
        )

    @handler
    async def handle(self, extraction_json: str, ctx: WorkflowContext[str]) -> None:
        response = await self._agent.run(extraction_json)
        # Save descriptions in state for the filler (Step 4)
        ctx.set_state("descriptions", response.text)
        await ctx.send_message(response.text)
