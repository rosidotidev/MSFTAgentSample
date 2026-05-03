"""E2E test: ingest a raw source and verify the wiki is populated.

Requires a real OpenAI API key (OPENAI_API_KEY in .env or environment).
"""

import json
import os

import pytest

from afw_core.llms.openai import create_client
from afw_core.workflows.ingest import build_ingest_workflow


pytestmark = pytest.mark.e2e


class TestE2EIngest:
    """Full ingest cycle: raw source → wiki pages."""

    async def test_ingest_creates_pages(self, e2e_wiki_root):
        """Ingest a single raw file and verify pages are created."""
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            pytest.skip("OPENAI_API_KEY not set")

        model = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o")
        client, options = create_client(api_key=api_key, model=model)

        workflow = build_ingest_workflow(client, options)

        # Run the ingest workflow
        async for event in workflow.run("start", stream=True):
            pass  # Let it complete

        # Verify: at least a source page was created
        sources_dir = e2e_wiki_root / "wiki" / "sources"
        source_pages = list(sources_dir.glob("*.md"))
        assert len(source_pages) >= 1, "Expected at least one source page created"

        # Verify: index.md was updated with the new page
        index_content = (e2e_wiki_root / "wiki" / "index.md").read_text(encoding="utf-8")
        assert "## Sources" in index_content
        assert "[[sources/" in index_content

        # Verify: log.md has an ingest entry
        log_content = (e2e_wiki_root / "wiki" / "log.md").read_text(encoding="utf-8")
        assert "ingest |" in log_content
        assert "test-python-decorators.md" in log_content

    async def test_ingest_creates_entity_or_concept(self, e2e_wiki_root):
        """Ingest should create at least one entity or concept page beyond the source."""
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            pytest.skip("OPENAI_API_KEY not set")

        model = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o")
        client, options = create_client(api_key=api_key, model=model)
        workflow = build_ingest_workflow(client, options)

        async for event in workflow.run("start", stream=True):
            pass

        entities_dir = e2e_wiki_root / "wiki" / "entities"
        concepts_dir = e2e_wiki_root / "wiki" / "concepts"
        entity_pages = list(entities_dir.glob("*.md"))
        concept_pages = list(concepts_dir.glob("*.md"))

        assert len(entity_pages) + len(concept_pages) >= 1, (
            "Expected at least one entity or concept page from the Python decorators source"
        )

    async def test_ingest_idempotent(self, e2e_wiki_root):
        """Running ingest twice on the same source should not duplicate pages."""
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            pytest.skip("OPENAI_API_KEY not set")

        model = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o")
        client, options = create_client(api_key=api_key, model=model)

        # First ingest
        workflow = build_ingest_workflow(client, options)
        async for event in workflow.run("start", stream=True):
            pass

        sources_dir = e2e_wiki_root / "wiki" / "sources"
        count_after_first = len(list(sources_dir.glob("*.md")))

        # Second ingest (same source already in log)
        workflow2 = build_ingest_workflow(client, options)
        async for event in workflow2.run("start", stream=True):
            pass

        count_after_second = len(list(sources_dir.glob("*.md")))
        assert count_after_second == count_after_first, "Second ingest should not create duplicate source pages"
