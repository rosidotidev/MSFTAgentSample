"""Tests for ScannerExecutor — deterministic, no LLM."""

import json
import os

import pytest

from afw_core.executors.scanner import ScannerExecutor


class FakeContext:
    """Minimal WorkflowContext stub that captures sent messages."""

    def __init__(self):
        self.messages: list[str] = []

    async def send_message(self, msg: str) -> None:
        self.messages.append(msg)


@pytest.fixture
def scanner():
    return ScannerExecutor()


@pytest.fixture
def ctx():
    return FakeContext()


class TestScanner:
    """Scanner should find new files and skip already-processed ones."""

    async def test_finds_new_file(self, wiki_root, scanner, ctx):
        """new-source.md is NOT in log.md → should be found."""
        await scanner.handle("", ctx)
        result = json.loads(ctx.messages[0])
        basenames = [os.path.basename(f) for f in result["new_files"]]
        assert "new-source.md" in basenames

    async def test_skips_processed_file(self, wiki_root, scanner, ctx):
        """already-processed.md IS in log.md → should be skipped."""
        await scanner.handle("", ctx)
        result = json.loads(ctx.messages[0])
        basenames = [os.path.basename(f) for f in result["new_files"]]
        assert "already-processed.md" not in basenames

    async def test_returns_absolute_paths(self, wiki_root, scanner, ctx):
        """All returned paths should be absolute."""
        await scanner.handle("", ctx)
        result = json.loads(ctx.messages[0])
        for f in result["new_files"]:
            assert os.path.isabs(f)

    async def test_scans_questions_approved(self, wiki_root, scanner, ctx):
        """Files in questions_approved/ should be picked up."""
        approved_dir = wiki_root / "questions_approved"
        (approved_dir / "new-question.md").write_text("# A question", encoding="utf-8")

        await scanner.handle("", ctx)
        result = json.loads(ctx.messages[0])
        basenames = [os.path.basename(f) for f in result["new_files"]]
        assert "new-question.md" in basenames

    async def test_scans_lint_approved(self, wiki_root, scanner, ctx):
        """Files in lint_approved/ should be picked up."""
        lint_dir = wiki_root / "lint_approved"
        (lint_dir / "lint-fix.md").write_text("# A lint fix", encoding="utf-8")

        await scanner.handle("", ctx)
        result = json.loads(ctx.messages[0])
        basenames = [os.path.basename(f) for f in result["new_files"]]
        assert "lint-fix.md" in basenames

    async def test_empty_log_treats_all_as_new(self, wiki_root, scanner, ctx):
        """If log.md is empty, all .md files in raw/ are new."""
        log_path = wiki_root / "wiki" / "log.md"
        log_path.write_text("# Wiki Log\n", encoding="utf-8")

        await scanner.handle("", ctx)
        result = json.loads(ctx.messages[0])
        basenames = [os.path.basename(f) for f in result["new_files"]]
        assert "already-processed.md" in basenames
        assert "new-source.md" in basenames

    async def test_no_log_file(self, wiki_root, scanner, ctx):
        """If log.md doesn't exist at all, all files are new."""
        log_path = wiki_root / "wiki" / "log.md"
        log_path.unlink()

        await scanner.handle("", ctx)
        result = json.loads(ctx.messages[0])
        assert len(result["new_files"]) >= 2
