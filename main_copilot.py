# Copyright (c) Microsoft. All rights reserved.

"""ManagerAgent: Single-query agent using OpenAI via Microsoft Agent Framework."""

from __future__ import annotations

import asyncio
import os


from azure.core.credentials import AccessToken
from agent_framework import Agent
from agent_framework.foundry import FoundryLocalClient
from agent_framework.foundry import FoundryChatClient
from agent_framework.openai import OpenAIChatClient, OpenAIChatCompletionClient, OpenAIChatOptions
from dotenv import load_dotenv

class _LocalCredential:
    """Dummy async token credential for local Foundry (no real auth needed)."""

    async def get_token(self, *scopes, **kwargs) -> AccessToken:
        return AccessToken(token="none", expires_on=0)

    async def close(self) -> None:
        pass


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


async def run_manager_agent_local(query: str) -> None:
    """Run ManagerAgent against a local Foundry model (OpenAI-compatible endpoint)."""

    client: OpenAIChatCompletionClient = OpenAIChatCompletionClient(
        base_url="http://127.0.0.1:62770/v1",
        model="phi-4-mini-instruct-openvino-npu:3",
        api_key="none",
    )

    agent: Agent[OpenAIChatOptions] = Agent(
        client=client,
        name="ManagerAgent",
        instructions=(
            "You are a manager agent. Answer the user's query "
            "as accurately and concisely as possible."
        ),
    )

    result = await agent.run(query)
    print(result.text)


async def run_manager_agent_local_foundry(query: str) -> None:
    """Run ManagerAgent against a local Foundry model via FoundryChatClient."""

    client: FoundryChatClient = FoundryChatClient(
        project_endpoint="http://127.0.0.1:62770/v1",
        model="phi-4-mini-instruct-openvino-npu:3",
        credential=_LocalCredential(),
    )

    agent: Agent = Agent(
        client=client,
        name="ManagerAgent",
        instructions=(
            "You are a manager agent. Answer the user's query "
            "as accurately and concisely as possible."
        ),
    )

    result = await agent.run(query)
    print(result.text)


def main() -> None:
    """Entry-point: load .env, resolve the query, and run the agent."""
    load_dotenv()

    query= "What is a Large Language Model and how does it work?"

    asyncio.run(run_manager_agent(query))


def main_local() -> None:
    """Entry-point for local Foundry model (OpenAIChatCompletionClient)."""
    query = "What is a Large Language Model and how does it work?"

    asyncio.run(run_manager_agent_local(query))


def main_local_foundry() -> None:
    """Entry-point for local Foundry model (FoundryChatClient)."""
    query = "What is a Large Language Model and how does it work?"

    asyncio.run(run_manager_agent_local_foundry(query))


async def run_manager_agent_foundry_local(query: str) -> None:
    """Run ManagerAgent via FoundryLocalClient (auto-manages local Foundry service)."""

    client: FoundryLocalClient = FoundryLocalClient(
        model="phi-4-mini",
        bootstrap=True,
        prepare_model=True,
    )

    agent: Agent = Agent(
        client=client,
        name="ManagerAgent",
        instructions=(
            "You are a manager agent. Answer the user's query "


            "as accurately and concisely as possible."
        ),
    )

    result = await agent.run(query)
    print(result.text)


def main_foundry_local() -> None:
    """Entry-point for FoundryLocalClient (auto-bootstrap)."""
    query = "What is a Large Language Model and how does it work?"

    asyncio.run(run_manager_agent_foundry_local(query))


if __name__ == "__main__":
    main_foundry_local()
