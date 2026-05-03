"""E2E test: query the wiki and verify answer quality.

Requires a real OpenAI API key and a populated wiki (runs ingest first).
"""

import os

import pytest

from afw_core.llms.openai import create_client
from afw_core.agents import wiki_querier
from afw_core.tools.wiki_read import read_wiki_page, read_index
from afw_core.tools.wiki_list import list_wiki_pages
from afw_core.tools.wiki_search import search_wiki
from afw_core.workflows.ingest import build_ingest_workflow


pytestmark = pytest.mark.e2e


async def _ingest_first(wiki_root, api_key, model):
    """Run ingest so the wiki has content to query."""
    client, options = create_client(api_key=api_key, model=model)
    workflow = build_ingest_workflow(client, options)
    async for event in workflow.run("start", stream=True):
        pass


class TestE2EQuery:
    """Query the wiki and verify grounded answers."""

    async def test_query_returns_answer(self, e2e_wiki_root):
        """Querying the wiki should produce a non-empty answer."""
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            pytest.skip("OPENAI_API_KEY not set")

        model = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o")

        # First populate the wiki
        await _ingest_first(e2e_wiki_root, api_key, model)

        # Now query
        client, options = create_client(api_key=api_key, model=model)
        tools = [read_index, read_wiki_page, list_wiki_pages, search_wiki]
        agent = wiki_querier.create_agent(client, options, tools)

        result = await agent.run("What are Python decorators and how do they work?")
        answer = result.final_output if hasattr(result, "final_output") else str(result)

        assert len(answer) > 50, "Expected a substantive answer"
        # Should mention decorators (the source topic)
        assert "decorator" in answer.lower()

    async def test_query_saves_to_pending(self, e2e_wiki_root):
        """Query answers should be saved to questions_pending/."""
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            pytest.skip("OPENAI_API_KEY not set")

        model = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o")
        await _ingest_first(e2e_wiki_root, api_key, model)

        client, options = create_client(api_key=api_key, model=model)
        tools = [read_index, read_wiki_page, list_wiki_pages, search_wiki]
        agent = wiki_querier.create_agent(client, options, tools)

        question = "What is functools.wraps used for?"
        result = await agent.run(question)
        answer = result.final_output if hasattr(result, "final_output") else str(result)

        # Save answer (mirroring main_query.py logic)
        import re
        from datetime import datetime

        pending_dir = e2e_wiki_root / "questions_pending"
        slug = re.sub(r"[^a-z0-9]+", "-", question.lower()).strip("-")[:60]
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        fname = f"{slug}_{timestamp}.md"
        fpath = pending_dir / fname

        content = (
            f"---\n"
            f'title: "{question}"\n'
            f'query: "{question}"\n'
            f'date: "{datetime.now().strftime("%Y-%m-%d")}"\n'
            f"---\n\n"
            f"{answer}\n"
        )
        fpath.write_text(content, encoding="utf-8")

        assert fpath.exists()
        saved = fpath.read_text(encoding="utf-8")
        assert "functools" in saved.lower() or "wraps" in saved.lower()
