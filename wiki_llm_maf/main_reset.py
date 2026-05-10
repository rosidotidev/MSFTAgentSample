"""Entry point: reset the wiki (delete all content, keep directory structure)."""

import asyncio

from dotenv import load_dotenv

from afw_core.workflows.reset import build_reset_workflow
from afw_core.console import console


async def main():
    load_dotenv()
    confirm = input("This will DELETE all wiki content. Type 'yes' to confirm: ")
    if confirm.strip().lower() != "yes":
        print("Aborted.")
        return

    workflow = build_reset_workflow()

    console.banner("WIKI RESET")

    async for event in workflow.run("start", stream=True):
        if event.type == "executor_invoked":
            console.step(f"{event.executor_id}...")
        elif event.type == "executor_completed":
            console.detail(f"{event.executor_id} completed")

    console.success("Reset complete")


if __name__ == "__main__":
    asyncio.run(main())
