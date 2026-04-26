import asyncio
import os
import logging
from dotenv import load_dotenv
# We use Agent for the logic, FoundryLocalClient for the LLM, 
# and McpProxy to "bridge" your Jira MCP server
from agent_framework import Agent, MCPStdioTool
from agent_framework.foundry import FoundryLocalClient, FoundryLocalChatOptions

# Enable debug logging only for agent_framework, silence httpcore/httpx/openai noise
logging.basicConfig(level=logging.WARNING, format="%(name)s %(levelname)s %(message)s")
logging.getLogger("agent_framework").setLevel(logging.DEBUG)
logging.getLogger("openai").setLevel(logging.DEBUG)
logging.getLogger("httpx").setLevel(logging.DEBUG)

# Load environment variables from .env file
load_dotenv()

async def main():
    """
    Main execution loop to initialize the Jira Agent and run a task.
    """
    
    # 1. SETUP THE MCP PROXY
    # This replaces the manual 'stdio_client' and 'ClientSession' logic.
    # It automatically handles initialization and tool discovery.

    jira_proxy = MCPStdioTool(
        name="jira_server",
        command="pipenv",
        args=["run", "mcp-atlassian"],
        env={
            "JIRA_URL": os.getenv("JIRA_URL"),
            "JIRA_USERNAME": os.getenv("JIRA_USERNAME"),
            "JIRA_API_TOKEN": os.getenv("JIRA_API_TOKEN"),
            "TOOLSETS": "jira_issues",
        }
    )

    # --- Chat client (FoundryLocalClient - CPU for stability) --------------------
    client: FoundryLocalClient = FoundryLocalClient(
        model="qwen2.5-7b-instruct-generic-cpu:4",
        bootstrap=False,
        prepare_model=False,
        
    )
    options = FoundryLocalChatOptions(temperature=0.0, tool_choice="required") # Force tool calling

    # 3. INITIALIZE THE AGENT
    # We pass the 'jira_server' instance into the 'tools' list.
    # The agent will now "see" all Jira tools (search, create, etc.) as its own capabilities.
    jira_agent = Agent(
        name="JiraManagerAgent",
        instructions=(
            "You are a Jira assistant. Call ONE tool at a time. "
            "Use issue_type: 'Epic','Story','Task','Bug'. "
            "Set epic parent via additional_fields: {\"parent\":{\"key\":\"EPIC-KEY\"}}."
        ),
        client=client,
        default_options=options,
        tools=[jira_proxy] 
    )

    # 4. RUN A CONVERSATION
    print("🚀 Jira Manager Agent is online...")
    
    # Example Task: Combining searching and summarizing
    # The agent will:
    # 1. Decide to call 'jira_search'
    # 2. Analyze the JSON output internally
    # 3. Decide whether to call 'jira_create_issue' based on the results
    # 4. Give you a final natural language report
    
    user_query_1 = (
        "Check my current tickets in the SARI project. "
        "If there are no open bugs, create a new Story titled 'MCP Integration Test' "
        "with the description 'Verify the Microsoft Agent Framework connection'."
    )

    user_query = (
        "In SARI project: "
        "1) Create epic 'Shopping List', get its key. "
        "2) Create story 'Shopping List CRUD Angular UI' under that epic. "
        "3) Create story 'Shopping List CRUD Angular in memory mocked service' under that epic."
    )
    
    print(f"\nUser: {user_query}")
    print("-" * 30)
    
    
    try:
        response = await jira_agent.run(user_query)
        
        print("\nAgent Response:")
        print(response.text)
    finally:
        await jira_proxy.close()

if __name__ == "__main__":
    # Ensure the event loop runs the async main function
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSession ended by user.")
