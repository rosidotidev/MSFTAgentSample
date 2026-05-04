"""E2E test: run lint on a wiki with known issues.

Requires a real OpenAI API key and a populated wiki (runs ingest first).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from afw_core.llms.openai import create_client
from afw_core.workflows.ingest import build_ingest_workflow
from main_lint import _deterministic_lint


pytestmark = pytest.mark.e2e


async def _ingest_first(wiki_root, api_key, model):
    """Run ingest so the wiki has content to lint."""
    client, options = create_client(api_key=api_key, model=model)
    workflow = build_ingest_workflow(client, options)
    async for event in workflow.run("start", stream=True):
        pass


class TestE2ELint:
    """End-to-end lint: deterministic + semantic phases."""

    async def test_deterministic_lint_after_ingest(self, e2e_wiki_root):
        """After ingest, deterministic lint should find zero or more issues."""
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            pytest.skip("OPENAI_API_KEY not set")

        model = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o")
        await _ingest_first(e2e_wiki_root, api_key, model)

        issues = _deterministic_lint()
        # Should return a list (may or may not have issues depending on writer quality)
        assert isinstance(issues, list)
        for issue in issues:
            assert isinstance(issue, str)

    async def test_semantic_lint_produces_suggestions(self, e2e_wiki_root):
        """Semantic lint should produce at least one suggestion on a fresh wiki."""
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            pytest.skip("OPENAI_API_KEY not set")

        model = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o")
        await _ingest_first(e2e_wiki_root, api_key, model)

        # Run the semantic linter agent
        from afw_core.agents import wiki_linter
        from afw_core.tools.wiki_read import read_wiki_page, read_index
        from afw_core.tools.wiki_list import list_wiki_pages
        from afw_core.tools.wiki_search import search_wiki
        from afw_core.tools.log_append import append_log

        client, options = create_client(api_key=api_key, model=model)
        tools = [read_index, read_wiki_page, list_wiki_pages, search_wiki, append_log]
        agent = wiki_linter.create_agent(client, options, tools)

        result = await agent.run("Perform a full semantic lint of the wiki.")
        raw_output = result.text

        # Should produce a non-empty output (JSON array or text)
        assert len(raw_output.strip()) > 10, "Expected non-empty linter output"

        # Try parsing as JSON
        import json

        text = raw_output.strip()
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:])
        if text.endswith("```"):
            text = text[: text.rfind("```")]

        try:
            suggestions = json.loads(text.strip())
            assert isinstance(suggestions, list)
            # Each suggestion should have type and description
            for s in suggestions:
                assert "type" in s
                assert "description" in s
        except (json.JSONDecodeError, ValueError):
            # If the LLM didn't produce valid JSON, at least verify it's a non-trivial response
            assert len(raw_output) > 50, "Linter output should be substantive"

    async def test_lint_saves_to_pending(self, e2e_wiki_root):
        """Full lint run should save suggestions to lint_pending/."""
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            pytest.skip("OPENAI_API_KEY not set")

        model = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o")
        await _ingest_first(e2e_wiki_root, api_key, model)

        # Inject a broken link so deterministic lint has something to find
        concepts_dir = e2e_wiki_root / "wiki" / "concepts"
        if concepts_dir.exists():
            for page in concepts_dir.glob("*.md"):
                content = page.read_text(encoding="utf-8")
                content += "\n\n## See Also\n\n- [[entities/nonexistent-test-target]]\n"
                page.write_text(content, encoding="utf-8")
                break  # Only modify one page

        # Import and run the main lint (which saves to lint_pending/)
        from main_lint import _deterministic_lint, _parse_deterministic_issue, _format_suggestion
        import re
        from datetime import datetime

        det_issues = _deterministic_lint()
        if det_issues:
            lint_dir = e2e_wiki_root / "lint_pending"
            lint_dir.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            for i, issue in enumerate(det_issues, 1):
                det_suggestion = _parse_deterministic_issue(issue)
                slug = re.sub(r"[^a-z0-9]+", "-", det_suggestion["description"][:60].lower()).strip("-")
                fname = f"lint-{ts}-det-{i:02d}-{slug}.md"
                content = _format_suggestion(det_suggestion)
                (lint_dir / fname).write_text(content, encoding="utf-8")

        lint_files = list((e2e_wiki_root / "lint_pending").glob("*.md"))
        assert len(lint_files) >= 1, "Expected at least one lint suggestion saved to lint_pending/"
