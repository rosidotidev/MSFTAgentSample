"""Entry point: run the full wiki ingest pipeline."""

import asyncio
import os

from dotenv import load_dotenv

from afw_core.logging_config import setup_logging
from afw_core.llms.openai import create_client
from afw_core.workflows.ingest import build_ingest_workflow


async def main():
    load_dotenv()
    setup_logging()
    api_key = os.environ["OPENAI_API_KEY"]
    model = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o")

    client, options = create_client(api_key=api_key, model=model)

    workflow = build_ingest_workflow(client, options)

    print("=== WIKI INGEST PIPELINE ===\n")

    async for event in workflow.run("start", stream=True):
        if event.type == "executor_invoked":
            print(f">> {event.executor_id}")
        elif event.type == "output":
            print(f"\n=== INGEST COMPLETE ===")
            print(f"Result: {event.data}")

    print()


if __name__ == "__main__":
    asyncio.run(main())
