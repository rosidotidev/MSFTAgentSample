---
title: "Microsoft Agent Framework: From Zero to Multi-Agent Pipeline"
published: true
tags: agentframework, openai, python, ai
cover_image: https://dev-to-uploads.s3.amazonaws.com/uploads/articles/nmlqbw783t1en5ootpey.png
---

I have some background with other agent frameworks like CrewAI and LangGraph, so when Microsoft released the [Agent Framework](https://github.com/microsoft/agent-framework), a lightweight Python package for building AI agents with native MCP (Model Context Protocol) support, I was curious to give it a try. I decided to build something practical: a pipeline that reads a product backlog from a Markdown file and automatically creates Epics and Stories on Jira. I chose this specific use case because I had already implemented it with CrewAI, so I was familiar with the configuration setup and could focus on comparing the frameworks rather than figuring out the integration details from scratch.

As reported in the [official documentation](https://learn.microsoft.com/en-us/agent-framework/overview/?pivots=programming-language-python), the Microsoft Agent Framework is the direct successor of both **Semantic Kernel** and **AutoGen**, created by the same Microsoft teams. It combines AutoGen's simple abstractions for single- and multi-agent patterns with Semantic Kernel's enterprise-grade features like session-based state management, type safety, telemetry, and extensive model support. On top of that, the Microsoft Agent Framework introduces workflows for explicit control over multi-agent execution paths and a robust state management system for long-running and human-in-the-loop scenarios.

What I found was a framework that favors simplicity and explicitness. You write Python functions, you wire them together, and you stay in control of the flow. In this article, I walk through the incremental approach I followed, from an "hello world" agent to a fully modular multi-agent pipeline.

You can find all the code shown in this post on this [GitHub repo (MSFTAgentSample)](https://github.com/rosidotidev/MSFTAgentSample).

## What I Used So Far

I have only scratched the surface of the framework, but here are the building blocks I worked with in this project:

- **`Agent`**: the core class. You give it a name, instructions, a chat client, and a list of tools. It runs autonomously, deciding which tools to call and when to stop.
- **`OpenAIChatClient`**: one of the available LLM providers. The framework integrates with most major LLMs, but for simplicity I used OpenAI since I still had some tokens to spend :-).
- **`MCPStdioTool`**: a bridge to any MCP server. Point it at a command and it auto-discovers all available tools via the MCP protocol.
- **`@tool`**: a decorator to turn any Python function into a tool the agent can invoke.

There is certainly more to explore, but these four primitives were enough to build a fully working multi-agent pipeline.

## Step 1: Hello World, One Agent, No Tools

The very first thing I did was verify that the framework works. The simplest possible setup: one agent, one LLM client, one hardcoded query, no tools at all.

```python
from __future__ import annotations
import asyncio
import os

from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient, OpenAIChatOptions
from dotenv import load_dotenv


async def run_manager_agent(query: str) -> None:
    client: OpenAIChatClient = OpenAIChatClient(
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        model=os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
    )

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
    load_dotenv()
    query = "What is a Large Language Model and how does it work?"
    asyncio.run(run_manager_agent(query))


if __name__ == "__main__":
    main()
```

Mental Model: This is the equivalent of a "print hello world" in the agent framework world. You create a client, create an agent, call `agent.run()`, and print the result. Everything is async, so you need `asyncio.run()` as the entry point. The `.env` file provides the API key and model name via `python-dotenv`.

Notice how explicit everything is. There is no magic configuration, no auto-discovery. You pass the API key, you choose the model, you write the instructions. The agent's identity is fully defined by a single `instructions` string.

## Step 2: Adding an MCP Tool (Jira)

Once the basics worked, the next step was connecting the agent to the real world. The Microsoft Agent Framework has first-class support for MCP (Model Context Protocol), which is the standard for exposing tools to AI agents. The `mcp-atlassian` package provides a full MCP server for Jira and Confluence.

```python
import asyncio
import os
from dotenv import load_dotenv
from agent_framework import Agent, MCPStdioTool
from agent_framework.openai import OpenAIChatClient, OpenAIChatOptions

load_dotenv()

async def main():
    # MCP Proxy: auto-discovers all Jira tools via MCP protocol
    jira_proxy = MCPStdioTool(
        name="jira_server",
        command="pipenv",
        args=["run", "mcp-atlassian"],
        env={
            "JIRA_URL": os.getenv("JIRA_URL"),
            "JIRA_USERNAME": os.getenv("JIRA_USERNAME"),
            "JIRA_API_TOKEN": os.getenv("JIRA_API_TOKEN"),
        },
    )

    client = OpenAIChatClient(
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        model=os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
    )
    options = OpenAIChatOptions(temperature=0.0)

    jira_agent = Agent(
        name="JiraManagerAgent",
        instructions=(
            "You are a professional Project Management Assistant. "
            "You have direct access to Jira via integrated tools. "
            "Your goal is to help users manage tickets, track progress, "
            "and create issues."
        ),
        client=client,
        default_options=options,
        tools=[jira_proxy],
    )

    print("Jira Manager Agent is online...")

    user_query = """
        IMPORTANT: Execute each step below ONE AT A TIME.
        Step 1: Create an epic in the SARI project called 'Shopping List'.
        Step 2: Create a story: 'Story 1: Shopping List CRUD Angular UI' 
                and set the epic as parent.
        Step 3: Create a story: 'Story 2: Shopping List CRUD Angular 
                in memory mocked service' and set the epic as parent.
        Create issues one at a time, never in parallel.
    """

    try:
        response = await jira_agent.run(user_query)
        print("\nAgent Response:")
        print(response.text)
    finally:
        await jira_proxy.close()

if __name__ == "__main__":
    asyncio.run(main())
```

The key piece here is `MCPStdioTool`. You point it at a command (`pipenv run mcp-atlassian`), pass the necessary environment variables, and the framework auto-discovers every tool the MCP server exposes: `jira_create_issue`, `jira_search`, `jira_get_issue`, `jira_link_to_epic`, and many more. The agent sees all of them and decides which ones to call based on your query.

### A Hard Lesson: Parallel Tool Calls

This step is where I hit my first real problem. When asked to create an epic and two stories, the agent would sometimes send multiple `jira_create_issue` calls in parallel. The second call would fail with a cryptic error: `expected 'key' property to be a string`. After adding debug logging and investigating, I discovered that the MCP server cannot handle parallel tool calls reliably.

The fix was surprisingly simple: tell the agent explicitly in its instructions to "Create issues ONE AT A TIME, never in parallel." This is a pattern I now apply consistently. If your MCP server doesn't handle concurrency well, just instruct the agent accordingly. It respects the instruction.

## Step 3: Two-Agent Pipeline (Monolithic)

With the Jira integration working, I wanted to build something more structured: a pipeline with two agents collaborating sequentially. The idea was simple:

1. **BacklogReaderAgent** reads a Markdown backlog file from disk
2. **JiraExecutorAgent** takes the backlog content and creates all issues on Jira

To give agents the ability to read and write files, I used the `@tool` decorator to create custom function tools:

```python
from typing import Annotated
from agent_framework import tool

@tool
def read_file(file_name: Annotated[str, "Name of the file to read"]) -> str:
    """Read and return the contents of a file from the input directory."""
    path = os.path.join("input", file_name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

@tool
def write_file(content: Annotated[str, "The content to write"]) -> str:
    """Write content to a timestamped file in the output directory."""
    os.makedirs("output", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    file_name = f"execution_result_{timestamp}.md"
    path = os.path.join("output", file_name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"File written: {path}"
```

The `Annotated[str, "description"]` syntax is how you document parameters for the agent. The framework reads these annotations and exposes them as part of the tool schema, so the LLM knows what to pass.

Then, the two agents and the orchestration logic, all in one file:

```python
    # Agent 1: reads the backlog file
    reader_agent = Agent(
        name="BacklogReaderAgent",
        instructions=(
            "You are a backlog reader assistant. "
            "When asked, use the read_file tool to read a markdown file. "
            "Return the full contents of the file as-is."
        ),
        client=client,
        default_options=options,
        tools=[read_file],
    )

    # Agent 2: executes the backlog on Jira
    executor_agent = Agent(
        name="JiraExecutorAgent",
        instructions=(
            "You are a Jira execution assistant. "
            "Create issues ONE AT A TIME, never in parallel. "
            "After all operations, write a summary using write_file."
        ),
        client=client,
        default_options=options,
        tools=[jira_proxy, write_file],
    )

    # Orchestration: sequential pipeline
    read_response = await reader_agent.run(
        f"Read the file '{backlog_file}' and return its contents."
    )
    backlog_content = read_response.text

    exec_response = await executor_agent.run(
        f"Execute the following backlog on Jira.\n\n{backlog_content}"
    )
```

Mental Model: Notice that the orchestration is plain Python. There is no pipeline abstraction, no DAG. You call `agent.run()`, get the result, and pass it to the next agent. **You** are the orchestrator.

The backlog file is a simple Markdown document placed in the `input/` directory:

```markdown
# Weather Dashboard Backlog - SARI Project

## Epic: Weather Dashboard
- Type: Epic
- Description: Real-time weather dashboard application.

### Stories

- **Story 1: City Search and Autocomplete**
  - Type: Story
  - Description: Implement a search bar with autocomplete...

- **Story 2: Current Weather Display**
  - Type: Story
  - Description: Show current weather conditions...
```

The agent reads this, understands the structure, and creates the epic first, then each story linked to the epic as parent. All on Jira, automatically.

## Step 4: Modular Pipeline with Pydantic Validation

The monolithic version worked perfectly, but everything was in one file. For a production-ready layout, I refactored the code into a well-structured directory:

```plaintext
MSFTAgentSample/
├── afw_core/
│   ├── agents/
│   │   ├── backlog_reader.py
│   │   └── jira_executor.py
│   ├── tools/
│   │   ├── file_reader.py
│   │   └── file_writer.py
│   ├── mcps/
│   │   └── jira.py
│   ├── llms/
│   │   └── openai.py
│   └── models/
│       └── backlog.py
│
├── input/
│   └── backlog.md
├── output/
├── main_backlog_from_md_std.py
└── .env
```

Each module has a single responsibility and exposes a factory function. For example, the agent definitions:

```python
# afw_core/agents/backlog_reader.py
from agent_framework import Agent

def create_agent(client, options, tools):
    return Agent(
        name="BacklogReaderAgent",
        instructions=(
            "You are a backlog reader assistant. "
            "When asked, use the read_file tool to read a markdown file. "
            "After reading, respond with ONLY a JSON object matching this schema: "
            '{"epic_count": <int>, "story_count": <int>, "description": <string>}.'
        ),
        client=client,
        default_options=options,
        tools=tools,
    )
```

```python
# afw_core/agents/jira_executor.py
from agent_framework import Agent

def create_agent(client, options, tools):
    return Agent(
        name="JiraExecutorAgent",
        instructions=(
            "You are a Jira execution assistant. "
            "Create issues ONE AT A TIME, never in parallel. "
            "When linking stories to an epic, first create the epic, "
            "then create each story and set the epic as parent. "
            "After all operations, write a summary using write_file."
        ),
        client=client,
        default_options=options,
        tools=tools,
    )
```

The convention I adopted is: **name and instructions are hardcoded** inside the factory function (they are intrinsic to the agent's identity), while **client, options, and tools are always injected** from outside (they are infrastructure concerns). This separation keeps agent definitions clean and reusable.

### Pydantic for Structured Output

A key improvement in the modular version was adding Pydantic validation between the two agents. Instead of passing raw text from the reader to the executor, I defined a model:

```python
# afw_core/models/backlog.py
from pydantic import BaseModel

class BacklogOutput(BaseModel):
    epic_count: int
    story_count: int
    description: str
```

The reader agent is instructed to return JSON matching this schema. The main script validates it:

```python
from afw_core.models.backlog import BacklogOutput

read_response = await reader_agent.run(
    f"Read the file '{backlog_file}' and return its contents."
)
backlog = BacklogOutput.model_validate_json(read_response.text)
print(f"Backlog loaded: {backlog.epic_count} epic(s), {backlog.story_count} stories")
```

If the agent returns malformed JSON, Pydantic throws a validation error immediately, rather than letting corrupted data propagate to the executor agent. This is a simple but effective pattern for inter-agent data contracts.

### The Entry Point

The modular entry point becomes clean orchestration logic with no implementation details:

```python
# main_backlog_from_md_std.py
import asyncio
import os
from dotenv import load_dotenv

from afw_core.llms.openai import create_client
from afw_core.mcps.jira import create_proxy
from afw_core.tools.file_reader import read_file
from afw_core.tools.file_writer import write_file
from afw_core.agents.backlog_reader import create_agent as create_reader_agent
from afw_core.agents.jira_executor import create_agent as create_executor_agent
from afw_core.models.backlog import BacklogOutput

load_dotenv()

async def main():
    client, options = create_client(
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        model=os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
    )
    jira_proxy = create_proxy()

    reader_agent = create_reader_agent(client=client, options=options, tools=[read_file])
    executor_agent = create_executor_agent(client=client, options=options, tools=[jira_proxy, write_file])

    # Step 1: Read and validate
    read_response = await reader_agent.run("Read the file 'backlog.md' and return its contents.")
    backlog = BacklogOutput.model_validate_json(read_response.text)

    # Step 2: Execute on Jira
    try:
        exec_response = await executor_agent.run(
            f"Execute the following backlog on Jira.\n\n{backlog.description}"
        )
        print(exec_response.text)
    finally:
        await jira_proxy.close()

if __name__ == "__main__":
    asyncio.run(main())
```

How you can see, the entry point reads like a recipe: create the infrastructure, create the agents, run them in sequence, handle cleanup. All the complexity lives in the modules under `afw_core/`.

## The Pipeline in Action

Here is what the pipeline produces when you run it against a real Jira project:

**Jira board after execution**: the Epic and all linked Stories created automatically.

![Jira Epic and Stories](https://raw.githubusercontent.com/rosidotidev/MSFTAgentSample/main/docs/images/jira_result.png)

**Console output**: the full agent execution log showing each tool call and result.

![Console Output](https://raw.githubusercontent.com/rosidotidev/MSFTAgentSample/main/docs/images/console_output.png)

**Execution report**: the summary file generated by the executor agent in the `output/` directory.

![Execution Report](https://raw.githubusercontent.com/rosidotidev/MSFTAgentSample/main/docs/images/execution_report.png)

## Key Lessons Learned

Working through these four steps, several patterns emerged that are worth sharing:

**MCP tools don't handle parallelism well.** When the LLM sends multiple tool calls in a single response, the MCP server may fail. The workaround is simple: add "ONE AT A TIME" to the agent's instructions. The agent respects this.

**The framework's error handling has a hidden default.** The `max_consecutive_errors_per_request` parameter defaults to 3. If an agent hits 3 consecutive tool errors, it stops retrying. This is defined in `agent_framework._tools` and caught me off guard initially. Knowing this default helps you debug "why did it stop?" scenarios.

**No `__init__.py` needed.** Python's implicit namespace packages work fine. The key is choosing a unique directory name (`afw_core`) that doesn't collide with installed packages. I initially tried naming directories `agents/`, `tools/`, `mcp/`, but these collided with the framework's own modules. Renaming to `afw_core/agents/` solved everything.

**A well-defined directory structure makes a real difference.** Applying a clear project layout (`afw_core/` with separate modules for agents, tools, MCP proxies, LLM clients, and models) greatly simplifies working with the framework. It keeps things organized and makes the codebase easy to extend as you add more agents and integrations.

**The biggest gap today: no native tools.** This is, in my opinion, the framework's main weakness right now. Other frameworks like LangChain/LangGraph and CrewAI ship with a rich ecosystem of built-in tools (web search, PDF readers, database connectors, vector stores, and many more). With the Microsoft Agent Framework, you either build every tool yourself with `@tool` or rely on MCP servers. For simple use cases that's fine, but for projects that need quick access to common integrations, the lack of native tools is a significant disadvantage that other frameworks still handle much better.

**Pydantic validation between agents is cheap insurance.** It adds minimal overhead and catches data corruption early. Especially useful when the first agent's output is the second agent's input.

**Agent instructions are powerful.** You have a single `instructions` string that gives you full freedom to express exactly what you need, including operational constraints like "never call tools in parallel."

## Conclusion: Takeaways

The Microsoft Agent Framework is a solid entry point into the world of AI agent development. Its explicit, code-first approach means there are very few surprises: what you write is what gets executed. The MCP integration is first-class and makes it trivial to connect agents to external services like Jira, Confluence, or GitHub.

The incremental approach I followed, from a single agent with no tools to a modular multi-agent pipeline, worked well as a learning strategy. Each step introduced exactly one new concept, making it easy to debug when things went wrong.

If you are starting with AI agents and want a framework with minimal abstraction, the Microsoft Agent Framework is worth a try. The codebase in this article serves as a progressive tutorial you can follow step by step.

All the code is available on [GitHub (MSFTAgentSample)](https://github.com/rosidotidev/MSFTAgentSample).
