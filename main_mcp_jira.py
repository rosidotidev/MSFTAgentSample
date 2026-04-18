import asyncio
import os
import logging
from dotenv import load_dotenv
# We use Agent for the logic, OpenAIClient for the LLM, 
# and McpProxy to "bridge" your Jira MCP server
from agent_framework import Agent, MCPStdioTool
from agent_framework.openai import OpenAIChatClient, OpenAIChatOptions

# Enable debug logging only for agent_framework, silence httpcore/httpx/openai noise
logging.basicConfig(level=logging.WARNING, format="%(name)s %(levelname)s %(message)s")
logging.getLogger("agent_framework").setLevel(logging.DEBUG)

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
            "JIRA_API_TOKEN": os.getenv("JIRA_API_TOKEN")
        }
    )

     # --- Chat client (OpenAI Responses API) ------------------------------------
    client: OpenAIChatClient = OpenAIChatClient(
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        model=os.environ.get("OPENAI_CHAT_MODEL", "gpt-5-nano"),
    )
    options = OpenAIChatOptions(temperature=0.0) # Set to 0 for precise data handling

    # 3. INITIALIZE THE AGENT
    # We pass the 'jira_server' instance into the 'tools' list.
    # The agent will now "see" all Jira tools (search, create, etc.) as its own capabilities.
    jira_agent = Agent(
        name="JiraManagerAgent",
        instructions=(
            "You are a professional Project Management Assistant. "
            "You have direct access to Jira via integrated tools. "
            "Your goal is to help users manage tickets, track progress, and create issues. "
            "Always verify project keys before creating tasks and summarize search results clearly."
           
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

    user_query = """
        IMPORTANT: Execute each step below ONE AT A TIME. Wait for each tool call to complete before making the next one.
        Step 1: Create an epic in the SARI project called 'Shopping List'. Retrieve the epic reference.
        Step 2: Create a story: 'Story 1: Shopping List CRUD Angular UI' and set the epic as parent.
        Step 3: Create a story: 'Story 2: Shopping List CRUD Angular in memory mocked service' and set the epic as parent.
        Create issues one at a time, never in parallel.
    """
    
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