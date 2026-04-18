import asyncio
import logging
import os

from dotenv import load_dotenv

from afw_core.llms.openai import create_client
from afw_core.mcps.jira import create_proxy
from afw_core.tools.file_reader import read_file
from afw_core.tools.file_writer import write_file
from afw_core.agents.backlog_reader import create_agent as create_reader_agent
from afw_core.agents.jira_executor import create_agent as create_executor_agent
from afw_core.models.backlog import BacklogOutput

# Enable debug logging only for agent_framework
logging.basicConfig(level=logging.WARNING, format="%(name)s %(levelname)s %(message)s")
logging.getLogger("agent_framework").setLevel(logging.INFO)

load_dotenv()


async def main():
    # --- Shared resources ------------------------------------------------------
    client, options = create_client(
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        model=os.environ.get("OPENAI_CHAT_MODEL", "gpt-5-nano"),
    )
    jira_proxy = create_proxy()

    # --- Create agents ---------------------------------------------------------
    reader_agent = create_reader_agent(client=client, options=options, tools=[read_file])
    executor_agent = create_executor_agent(client=client, options=options, tools=[jira_proxy, write_file])

    print("🚀 Backlog-from-MD pipeline is online...")

    # --- Step 1: Read backlog --------------------------------------------------
    backlog_file = "backlog.md"
    print(f"\n📖 Step 1: Reading backlog from input/{backlog_file}...")
    read_response = await reader_agent.run(f"Read the file '{backlog_file}' and return its contents.")
    backlog = BacklogOutput.model_validate_json(read_response.text)
    print(f"Backlog loaded: {backlog.epic_count} epic(s), {backlog.story_count} story/stories")

    # --- Step 2: Execute on Jira and write results -----------------------------
    print("\n⚙️  Step 2: Executing backlog on Jira...")
    try:
        exec_query = (
            f"Execute the following backlog on Jira. Create all issues described below, "
            f"one at a time. When done, write the execution results to a file using the write_file tool.\n\n"
            f"--- BACKLOG START ---\n{backlog.description}\n--- BACKLOG END ---"
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
