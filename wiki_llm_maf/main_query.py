"""Entry point: query the wiki interactively."""

import asyncio
import os
import re
from datetime import datetime

from dotenv import load_dotenv

from afw_core.logging_config import setup_logging
from afw_core.llms.openai import create_client
from afw_core.agents import wiki_querier
from afw_core.tools.wiki_read import read_wiki_page, read_index
from afw_core.tools.wiki_list import list_wiki_pages
from afw_core.tools.wiki_search import search_wiki

_DEFAULT_BASE = os.path.dirname(os.path.abspath(__file__))


def _base_dir() -> str:
    return os.environ.get("WIKI_ROOT_DIR", _DEFAULT_BASE)


def _save_answer(question: str, answer: str) -> str:
    """Save the answer to questions_pending/ and return the file path."""
    pending_dir = os.path.join(_base_dir(), "questions_pending")
    os.makedirs(pending_dir, exist_ok=True)
    # Generate slug from question
    slug = re.sub(r"[^a-z0-9]+", "-", question.lower()).strip("-")[:60]
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    fname = f"{slug}_{timestamp}.md"
    fpath = os.path.join(pending_dir, fname)

    content = (
        f"---\n"
        f'title: "{question}"\n'
        f'query: "{question}"\n'
        f'date: "{datetime.now().strftime("%Y-%m-%d")}"\n'
        f"---\n\n"
        f"{answer}\n"
    )
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(content)
    return fname


async def main():
    load_dotenv()
    setup_logging()
    api_key = os.environ["OPENAI_API_KEY"]
    model = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o")

    client, options = create_client(api_key=api_key, model=model)

    tools = [read_index, read_wiki_page, list_wiki_pages, search_wiki]
    agent = wiki_querier.create_agent(client, options, tools)

    # Pre-load index so the agent doesn't need to call read_index() every time
    index_path = os.path.join(_base_dir(), "wiki", "index.md")
    with open(index_path, "r", encoding="utf-8") as f:
        index_content = f.read()

    print("Wiki Querier ready. Type your question (or 'quit' to exit).\n")
    while True:
        question = input("Q: ").strip()
        if question.lower() in ("quit", "exit", "q"):
            break
        if not question:
            continue

        # Prepend index to question so agent already knows what pages exist
        # Reorder index: entities and concepts first (they have the richest content)
        lines = index_content.split("\n")
        sections: dict[str, list[str]] = {}
        current_section = ""
        for line in lines:
            if line.startswith("## "):
                current_section = line
                sections[current_section] = []
            elif current_section:
                sections[current_section].append(line)

        # Put Entities and Concepts before Sources
        reordered_parts = []
        for heading in ["## Entities", "## Concepts", "## Sources", "## Synthesis"]:
            if heading in sections:
                reordered_parts.append(heading)
                reordered_parts.extend(sections[heading])
        reordered_index = "\n".join(reordered_parts) if reordered_parts else index_content

        prompt = (
            f"WIKI INDEX — read ALL relevant pages (entities, concepts, AND sources):\n"
            f"{reordered_index}\n\n"
            f"QUESTION: {question}\n\n"
            f"You MUST read entity and concept pages — they contain the detailed content. "
            f"Source pages are only summaries. Answer using ONLY text from pages you read. "
            f"Do NOT add information that is not in the pages."
        )
        result = await agent.run(prompt)
        answer = result.text
        print(f"\nA: {answer}\n")

        # Save to questions_pending/
        fname = _save_answer(question, answer)
        print(f"   [saved to questions_pending/{fname}]")

        # Append to log.md
        log_path = os.path.join(_base_dir(), "wiki", "log.md")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        log_entry = f"\n## [{ts}] query | {question}\nAnswer saved: questions_pending/{fname}\n"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(log_entry)
        print(f"   [logged to wiki/log.md]\n")


if __name__ == "__main__":
    asyncio.run(main())
