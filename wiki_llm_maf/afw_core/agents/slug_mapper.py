"""Agent: slug mapper — maps new entity/concept slugs to existing wiki pages.

Single LLM call, no tools. Uses structured output (response_format)
to return a SlugMapping Pydantic model.
"""

from agent_framework import Agent


INSTRUCTIONS = """\
You are a wiki deduplication assistant. Given a list of EXISTING wiki page slugs \
and NEW slugs extracted from a source, map each new slug to the most semantically \
equivalent existing slug, or mark it as "NEW" if no good match exists.

Rules:
- Match only when the new item clearly covers the SAME topic as the existing page.
- Partial keyword overlap is NOT enough. "mcp-integration" and "mcp-server-proxies" \
  are different topics unless they truly cover the same concept.
- Plural/singular variants are a match (e.g., "tool" ↔ "tools").
- A more specific slug can match a more general one if they cover the same ground \
  (e.g., "tools" → "custom-function-tools" when both are about the tool system).
- When in doubt, return "NEW". Creating a duplicate is cheaper than merging unrelated topics.
"""


def create_agent(client, options):
    """Create the SlugMapperAgent."""
    return Agent(
        name="SlugMapperAgent",
        instructions=INSTRUCTIONS,
        client=client,
        default_options=options,
        tools=[],
    )
