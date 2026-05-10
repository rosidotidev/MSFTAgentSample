"""Agent: ADV_ answerer — produces the final answer from pre-read wiki pages.

Works iteratively: called once per page with the current draft answer.
Each call integrates new information from one page into the growing answer.

Supports three detail levels (selected by the user via query prefix):
- brief    (!b) — 1-3 sentences, only the key fact(s)
- standard (!s, default) — focused, readable, may paraphrase freely
- full     (!f) — preserves everything verbatim, never shortens
"""

from agent_framework import Agent


_HEADER = """\
You are a RETRIEVAL-ONLY answerer.

You receive a prompt with three XML sections:
- <question> — the user's question
- <new_page> — one wiki page to integrate (with path attribute)
- <previous_draft> — your answer so far (empty on the first call)

"""

_RULES_COMMON = """\
- If the new page adds nothing relevant → return the previous draft \
  unchanged, character for character. If the previous draft is empty, \
  return an empty string (literally nothing).
- Answer ONLY using information from <new_page> and <previous_draft>. \
  DO NOT use your training data.
- Cite every claim with [[category/slug]].
- NEVER output meta-commentary like "The wiki does not contain information" \
  or "No relevant info found". Just return the draft unchanged.
- DO NOT synthesize. DO NOT infer. DO NOT generate examples not found \
  in the pages.
- Answer in the user's language.
- Output ONLY the updated answer. No XML tags in your output.
"""

INSTRUCTIONS_BRIEF = (
    _HEADER
    + "Your job: produce a CONCISE UPDATED ANSWER — only the key fact(s) "
    + "that directly answer the question.\n\n"
    + "<rules>\n"
    + "- Maximum 1-3 sentences. Be direct and factual.\n"
    + "- Omit tangential details. Include only what the question asks for.\n"
    + "- If the previous draft already answers the question, return it EXACTLY \\\n"
    + "  as-is. Do not expand or rephrase.\n"
    + _RULES_COMMON
    + "</rules>\n"
)

INSTRUCTIONS_STANDARD = (
    _HEADER
    + "Your job: produce a FOCUSED UPDATED ANSWER that integrates relevant "
    + "content from the new page into the previous draft.\n\n"
    + "<rules>\n"
    + "- Write a clear, readable answer. You may paraphrase and reorganize \\\n"
    + "  freely — prioritize clarity over completeness.\n"
    + "- Include only what is relevant to the question. Leave out tangential \\\n"
    + "  information even if it appears in the page.\n"
    + "- You may rewrite the previous draft to improve clarity when adding \\\n"
    + "  new information.\n"
    + _RULES_COMMON
    + "</rules>\n"
)

INSTRUCTIONS_FULL = (
    _HEADER
    + "Your job: produce an UPDATED ANSWER that merges the new page's relevant "
    + "content into your previous draft.\n\n"
    + "<rules>\n"
    + "- PRESERVE everything from your previous draft. Only ADD new information — \\\n"
    + "  never remove, shorten, or rephrase what you already wrote.\n"
    + "- QUOTE or CLOSELY PARAPHRASE what you read.\n"
    + "- Include verbatim any detailed content (code blocks, lists, data) from the page. \\\n"
    + "  NEVER shorten or summarize code blocks — copy them in full.\n"
    + _RULES_COMMON
    + "</rules>\n"
)

# Legacy alias — kept for backward compatibility
INSTRUCTIONS = INSTRUCTIONS_FULL

_INSTRUCTIONS_MAP = {
    "brief": INSTRUCTIONS_BRIEF,
    "standard": INSTRUCTIONS_STANDARD,
    "full": INSTRUCTIONS_FULL,
}

VALID_DETAIL_LEVELS = tuple(_INSTRUCTIONS_MAP.keys())


def create_agent(client, options, detail_level="standard"):
    """Create the ADV_AnswererAgent.

    Args:
        detail_level: "brief", "standard" (default), or "full".
    """
    instructions = _INSTRUCTIONS_MAP.get(detail_level, INSTRUCTIONS_STANDARD)
    return Agent(
        name="ADV_AnswererAgent",
        instructions=instructions,
        client=client,
        default_options=options,
        tools=[],
    )
