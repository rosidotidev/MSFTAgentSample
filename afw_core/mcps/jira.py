import os

from agent_framework import MCPStdioTool


def create_proxy():
    """Create and return the MCPStdioTool for Jira."""
    return MCPStdioTool(
        name="jira_server",
        command="pipenv",
        args=["run", "mcp-atlassian"],
        env={
            "JIRA_URL": os.getenv("JIRA_URL"),
            "JIRA_USERNAME": os.getenv("JIRA_USERNAME"),
            "JIRA_API_TOKEN": os.getenv("JIRA_API_TOKEN"),
        },
    )
