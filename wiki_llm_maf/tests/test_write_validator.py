"""Tests for WriteValidatorExecutor — deterministic, no LLM."""

import json
import os

import pytest

from afw_core.executors.write_validator import WriteValidatorExecutor


class FakeContext:
    """Minimal WorkflowContext stub."""

    def __init__(self):
        self.messages: list[str] = []

    async def send_message(self, msg: str) -> None:
        self.messages.append(msg)


@pytest.fixture
def validator():
    return WriteValidatorExecutor()


@pytest.fixture
def ctx():
    return FakeContext()


class TestWriteValidator:
    """WriteValidator checks multiple conditions deterministically."""

    async def test_valid_page_passes(self, wiki_root, validator, ctx):
        """A well-formed page should pass all checks."""
        input_data = json.dumps({
            "written_pages": ["wiki/sources/test-source.md"],
            "extraction": {},
        })
        await validator.handle(input_data, ctx)
        result = json.loads(ctx.messages[0])
        assert result["passed"] is True
        assert result["issues"] == []

    async def test_missing_file(self, wiki_root, validator, ctx):
        """A page that doesn't exist on disk should be flagged."""
        input_data = json.dumps({
            "written_pages": ["wiki/sources/nonexistent.md"],
            "extraction": {},
        })
        await validator.handle(input_data, ctx)
        result = json.loads(ctx.messages[0])
        assert result["passed"] is False
        assert any("MISSING" in i for i in result["issues"])

    async def test_too_short(self, wiki_root, validator, ctx):
        """A page with less than 50 chars should be flagged."""
        short_path = wiki_root / "wiki" / "entities" / "short.md"
        short_path.write_text("---\ntitle: X\ntype: entity\n---\nHi", encoding="utf-8")

        input_data = json.dumps({
            "written_pages": ["wiki/entities/short.md"],
            "extraction": {},
        })
        await validator.handle(input_data, ctx)
        result = json.loads(ctx.messages[0])
        assert any("TOO SHORT" in i for i in result["issues"])

    async def test_no_frontmatter(self, wiki_root, validator, ctx):
        """A page without frontmatter should be flagged."""
        no_fm = wiki_root / "wiki" / "entities" / "no-fm.md"
        no_fm.write_text(
            "# No Frontmatter Page\n\nThis page has no YAML frontmatter at all and is long enough to pass the length check.",
            encoding="utf-8",
        )

        input_data = json.dumps({
            "written_pages": ["wiki/entities/no-fm.md"],
            "extraction": {},
        })
        await validator.handle(input_data, ctx)
        result = json.loads(ctx.messages[0])
        assert any("NO FRONTMATTER" in i for i in result["issues"])

    async def test_missing_title_in_frontmatter(self, wiki_root, validator, ctx):
        """Frontmatter without title: should be flagged."""
        page = wiki_root / "wiki" / "entities" / "no-title.md"
        page.write_text(
            "---\ntype: entity\ncreated: 2026-05-01\n---\n\n# No Title Field\n\nThis has frontmatter but it is missing the title field entirely from the YAML block.",
            encoding="utf-8",
        )

        input_data = json.dumps({
            "written_pages": ["wiki/entities/no-title.md"],
            "extraction": {},
        })
        await validator.handle(input_data, ctx)
        result = json.loads(ctx.messages[0])
        assert any("MISSING TITLE" in i for i in result["issues"])

    async def test_source_page_without_source_ref(self, wiki_root, validator, ctx):
        """A source page without 'source:' reference should be flagged."""
        page = wiki_root / "wiki" / "sources" / "no-ref.md"
        page.write_text(
            "---\ntitle: No Ref Source\ntype: source\n---\n\n# No Ref Source\n\nThis source page does not have a source_file or sources reference anywhere in the content.",
            encoding="utf-8",
        )

        input_data = json.dumps({
            "written_pages": ["wiki/sources/no-ref.md"],
            "extraction": {},
        })
        await validator.handle(input_data, ctx)
        result = json.loads(ctx.messages[0])
        assert any("NO SOURCE REF" in i for i in result["issues"])

    async def test_placeholder_detection(self, wiki_root, validator, ctx):
        """Pages containing TODO or PLACEHOLDER should be flagged."""
        page = wiki_root / "wiki" / "concepts" / "placeholder.md"
        page.write_text(
            "---\ntitle: Placeholder Page\ntype: concept\n---\n\n# Placeholder Page\n\n## Definition\n\nTODO: fill this in later with actual content about the concept.",
            encoding="utf-8",
        )

        input_data = json.dumps({
            "written_pages": ["wiki/concepts/placeholder.md"],
            "extraction": {},
        })
        await validator.handle(input_data, ctx)
        result = json.loads(ctx.messages[0])
        assert any("PLACEHOLDER" in i for i in result["issues"])

    async def test_broken_wikilink(self, wiki_root, validator, ctx):
        """The fixture test-concept.md has [[entities/nonexistent-entity]] → broken."""
        input_data = json.dumps({
            "written_pages": ["wiki/concepts/test-concept.md"],
            "extraction": {},
        })
        await validator.handle(input_data, ctx)
        result = json.loads(ctx.messages[0])
        assert result["passed"] is False
        assert any("BROKEN LINK" in i and "nonexistent-entity" in i for i in result["issues"])

    async def test_valid_wikilink_not_flagged(self, wiki_root, validator, ctx):
        """[[entities/test-entity]] exists → should NOT be flagged."""
        input_data = json.dumps({
            "written_pages": ["wiki/sources/test-source.md"],
            "extraction": {},
        })
        await validator.handle(input_data, ctx)
        result = json.loads(ctx.messages[0])
        # test-source.md links to test-entity and test-concept — both exist
        broken = [i for i in result["issues"] if "BROKEN LINK" in i]
        assert broken == []
