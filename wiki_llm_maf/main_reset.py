"""Entry point: reset the wiki (delete all content, keep directory structure)."""

import asyncio

from dotenv import load_dotenv

from afw_core.workflows.reset import build_reset_workflow


async def main():
    load_dotenv()
    confirm = input("This will DELETE all wiki content. Type 'yes' to confirm: ")
    if confirm.strip().lower() != "yes":
        print("Aborted.")
        return

    workflow = build_reset_workflow()

    print("=== WIKI RESET ===\n")

    async for event in workflow.run("start", stream=True):
        if event.type == "executor_invoked":
            print(f"\n>> {event.executor_id} started...")
        elif event.type == "executor_completed":
            print(f"   ✓ {event.executor_id} completed")

    print("\n=== RESET COMPLETE ===")


if __name__ == "__main__":
    asyncio.run(main())
