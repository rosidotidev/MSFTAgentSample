import asyncio
import os
import logging
from datetime import datetime
from typing import Annotated

from dotenv import load_dotenv
from agent_framework import Agent, MCPStdioTool, tool
from agent_framework.openai import OpenAIChatClient, OpenAIChatOptions

# Enable debug logging only for agent_framework
logging.basicConfig(level=logging.WARNING, format="%(name)s %(levelname)s %(message)s")
logging.getLogger("agent_framework").setLevel(logging.DEBUG)

load_dotenv()

# ---------------------------------------------------------------------------
# Custom file tools
# ---------------------------------------------------------------------------

@tool
def read_file(file_name: Annotated[str, "Name of the file to read from the input directory"]) -> str:
    """Read and return the contents of a file from the input directory."""
    path = os.path.join("input", file_name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


@tool
def write_file(content: Annotated[str, "The content to write to the output file"]) -> str:
    """Write content to an execution result file in the output directory. Returns the file path."""
    os.makedirs("output", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    file_name = f"execution_result_{timestamp}.md"
    path = os.path.join("output", file_name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"File written: {path}"


async def main():
    # --- MCP Jira proxy -------------------------------------------------------
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

    # --- Chat client -----------------------------------------------------------
    client = OpenAIChatClient(
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        model=os.environ.get("OPENAI_CHAT_MODEL", "gpt-5-nano"),
    )
    options = OpenAIChatOptions(temperature=0.0)

    # --- Agent 1: Backlog Reader -----------------------------------------------
    reader_agent = Agent(
        name="BacklogReaderAgent",
        instructions=(
            "You are a backlog reader assistant. "
            "When asked, use the read_file tool to read a markdown file from the input directory. "
            "Return the full contents of the file as-is, without modifications."
        ),
        client=client,
        default_options=options,
        tools=[read_file],
    )

    # --- Agent 2: Jira Executor ------------------------------------------------
    executor_agent = Agent(
        name="JiraExecutorAgent",
        instructions=(
            "You are a Jira execution assistant. "
            "You receive a backlog in markdown format and must create all the issues described in it on Jira. "
            "Create issues ONE AT A TIME, never in parallel. Wait for each to complete before the next. "
            "When linking stories to an epic, first create the epic, then create each story and set the epic as parent. "
            "After all operations are done, write a detailed markdown summary of every issue created "
            "(key, summary, type, status, parent) using the write_file tool."
        ),
        client=client,
        default_options=options,
        tools=[jira_proxy, write_file],
    )

    print("🚀 Backlog-from-MD pipeline is online...")

    # --- Step 1: Read backlog --------------------------------------------------
    backlog_file = "backlog.md"
    print(f"\n📖 Step 1: Reading backlog from input/{backlog_file}...")
    read_response = await reader_agent.run(f"Read the file '{backlog_file}' and return its contents.")
    backlog_content = read_response.text
    print(f"Backlog loaded ({len(backlog_content)} chars)")

    # --- Step 2: Execute on Jira and write results -----------------------------
    print("\n⚙️  Step 2: Executing backlog on Jira...")
    try:
        exec_query = (
            f"Execute the following backlog on Jira. Create all issues described below, "
            f"one at a time. When done, write the execution results to a file using the write_file tool.\n\n"
            f"--- BACKLOG START ---\n{backlog_content}\n--- BACKLOG END ---"
        )
        exec_response = await executor_agent.run(exec_query)
        print("\nAgent Response:")
        print(exec_response.text)
    finally:
        await jira_proxy.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSession ended by user.")
