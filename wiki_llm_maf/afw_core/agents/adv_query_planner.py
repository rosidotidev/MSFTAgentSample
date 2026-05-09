"""Agent: ADV_ query planner — selects seed pages from the wiki index.

Given the wiki index and a user question, returns a structured list
of pages to read (ADV_QueryPlan).  No tools — single LLM call with
structured output.
"""

from agent_framework import Agent


INSTRUCTIONS = """\
You are a WIKI PAGE SELECTOR.

You receive a prompt with two XML sections:
- <wiki_index> — the full wiki index
- <question> — the user's question

<rules>
1. Select between 1 and {max_seeds} pages from the index.
2. You may ONLY select paths that appear EXACTLY in <wiki_index>. \
   The index is EXHAUSTIVE — if a path is not listed, the page does not exist.
3. Prefer concept pages for "how/what/why" questions.
4. Prefer entity pages for "who/which/what is" questions.
5. Always include the most directly relevant page first.
6. For each page, provide a brief reason explaining why it is relevant.
7. Do NOT invent, guess, or construct paths. Copy them exactly from the index.
8. Return BARE paths (e.g. "concepts/foo"), WITHOUT [[brackets]].
9. Prefer SPECIFIC pages over generic overviews. E.g. for "how to declare a tool", \
   prefer "concepts/custom-function-tools" over "concepts/tools" — the description \
   tells you which one has actionable detail.
10. READ the descriptions carefully, not just the titles. A shorter title does not \
    mean a better match.
</rules>
"""

_DEFAULT_MAX_SEEDS = 3


def create_agent(client, options, *, max_seeds: int | None = None):
    """Create the ADV_QueryPlannerAgent."""
    seeds = max_seeds or _DEFAULT_MAX_SEEDS
    return Agent(
        name="ADV_QueryPlannerAgent",
        instructions=INSTRUCTIONS.format(max_seeds=seeds),
        client=client,
        default_options=options,
        tools=[],
    )
