from agent_framework import Agent


def create_agent(client, options, tools):
    """Create the JiraExecutorAgent. Name and instructions are hardcoded."""
    return Agent(
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
        tools=tools,
    )
