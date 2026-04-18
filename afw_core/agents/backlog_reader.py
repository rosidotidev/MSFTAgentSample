from agent_framework import Agent


def create_agent(client, options, tools):
    """Create the BacklogReaderAgent. Name and instructions are hardcoded."""
    return Agent(
        name="BacklogReaderAgent",
        instructions=(
            "You are a backlog reader assistant. "
            "When asked, use the read_file tool to read a markdown file from the input directory. "
            "After reading, analyze the content and respond with ONLY a JSON object (no markdown, no code fences) "
            "matching this schema: "
            '{"epic_count": <number of epics>, "story_count": <number of stories>, "description": <full file content as string>}. '
            "Count epics and stories based on the markdown structure."
        ),
        client=client,
        default_options=options,
        tools=tools,
    )
