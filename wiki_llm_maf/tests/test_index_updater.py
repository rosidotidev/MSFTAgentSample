"""Tests for IndexUpdaterExecutor — deterministic, no LLM."""

import json
import os

import pytest

from afw_core.executors.index_updater import IndexUpdaterExecutor


class FakeContext:
    """Minimal WorkflowContext stub."""

    def __init__(self):
        self.messages: list[str] = []

    async def send_message(self, msg: str) -> None:
        self.messages.append(msg)


@pytest.fixture
def updater():
    return IndexUpdaterExecutor()


@pytest.fixture
def ctx():
    return FakeContext()


class TestIndexUpdater:
    """IndexUpdater rebuilds index.md and appends to log.md."""

    async def test_rebuilds_index(self, wiki_root, updater, ctx):
        """After running, index.md should list all existing pages."""
        input_data = json.dumps({
            "extraction": {"file_name": "test.md", "title": "Test"},
            "written_pages": ["wiki/sources/test-source.md"],
        })
        await updater.handle(input_data, ctx)

        index_path = wiki_root / "wiki" / "index.md"
        content = index_path.read_text(encoding="utf-8")

        # Should contain frontmatter
        assert content.startswith("---")
        assert "title: Wiki Index" in content

        # Should contain all existing pages
        assert "[[sources/test-source]]" in content
        assert "[[entities/test-entity]]" in content
        assert "[[concepts/test-concept]]" in content

    async def test_index_has_summaries(self, wiki_root, updater, ctx):
        """Index entries should have one-line summaries extracted from pages."""
        input_data = json.dumps({
            "extraction": {"file_name": "test.md", "title": "Test"},
            "written_pages": [],
        })
        await updater.handle(input_data, ctx)

        index_path = wiki_root / "wiki" / "index.md"
        content = index_path.read_text(encoding="utf-8")

        # test-source.md first paragraph after ## Summary is about decorators
        assert "[[sources/test-source]] —" in content

    async def test_appends_log_entry(self, wiki_root, updater, ctx):
        """Should append a timestamped log entry with source name and pages touched."""
        input_data = json.dumps({
            "extraction": {"file_name": "new-source.md", "title": "New Source"},
            "written_pages": ["wiki/sources/new-source.md", "wiki/entities/python.md"],
        })
        await updater.handle(input_data, ctx)

        log_path = wiki_root / "wiki" / "log.md"
        content = log_path.read_text(encoding="utf-8")

        assert "ingest | New Source" in content
        assert "Source: new-source.md" in content
        assert "sources/new-source" in content
        assert "entities/python" in content

    async def test_no_log_entry_without_extraction(self, wiki_root, updater, ctx):
        """If extraction is empty, no log entry should be appended."""
        log_path = wiki_root / "wiki" / "log.md"
        original = log_path.read_text(encoding="utf-8")

        input_data = json.dumps({
            "extraction": {},
            "written_pages": [],
        })
        await updater.handle(input_data, ctx)

        after = log_path.read_text(encoding="utf-8")
        # Log content should not grow (no new ## heading added)
        assert after.count("## [") == original.count("## [")

    async def test_signals_cycle_complete(self, wiki_root, updater, ctx):
        """Should send cycle_complete=True in its output message."""
        input_data = json.dumps({
            "extraction": {"file_name": "x.md", "title": "X"},
            "written_pages": [],
        })
        await updater.handle(input_data, ctx)
        result = json.loads(ctx.messages[0])
        assert result["cycle_complete"] is True

    async def test_categories_ordered(self, wiki_root, updater, ctx):
        """Index sections should be ordered: Sources, Entities, Concepts, Synthesis."""
        input_data = json.dumps({"extraction": {}, "written_pages": []})
        await updater.handle(input_data, ctx)

        index_path = wiki_root / "wiki" / "index.md"
        content = index_path.read_text(encoding="utf-8")

        sources_pos = content.find("## Sources")
        entities_pos = content.find("## Entities")
        concepts_pos = content.find("## Concepts")
        assert sources_pos < entities_pos < concepts_pos
