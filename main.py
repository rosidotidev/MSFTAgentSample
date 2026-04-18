# Copyright (c) Microsoft. All rights reserved.

"""ManagerAgent: Single-query agent using OpenAI via Microsoft Agent Framework."""

from __future__ import annotations

import asyncio
import os


from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient, OpenAIChatOptions
from dotenv import load_dotenv


async def run_manager_agent(query: str) -> None:
    """Initialise the ManagerAgent, execute *query*, and print the result."""

    # --- Chat client (OpenAI Responses API) ------------------------------------
    client: OpenAIChatClient = OpenAIChatClient(
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        model=os.environ.get("OPENAI_CHAT_MODEL", "gpt-5-nano"),
    )

    # --- Agent -----------------------------------------------------------------
    agent: Agent[OpenAIChatOptions] = Agent(
        client=client,
        name="ManagerAgent",
        instructions=(
            "You are a manager agent. Answer the user's query "
            "as accurately and concisely as possible."
        )

    )

    result = await agent.run(query)
    print(result.text)


def main() -> None:
    """Entry-point: load .env, resolve the query, and run the agent."""
    load_dotenv()

    query= "What is a Large Language Model and how does it work?"

    asyncio.run(run_manager_agent(query))


if __name__ == "__main__":
    main()
