"""Tests for _deterministic_lint() in main_lint.py — no LLM."""

import os
import sys

import pytest

# Add wiki_llm_maf to path so we can import main_lint
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main_lint import _deterministic_lint


class TestDeterministicLint:
    """_deterministic_lint() should detect structural issues without an LLM."""

    def test_detects_broken_wikilink(self, wiki_root):
        """test-concept.md links to [[entities/nonexistent-entity]] → broken."""
        issues = _deterministic_lint()
        broken = [i for i in issues if "BROKEN LINK" in i and "nonexistent-entity" in i]
        assert len(broken) == 1

    def test_does_not_flag_valid_links(self, wiki_root):
        """[[entities/test-entity]] exists → should not be flagged."""
        issues = _deterministic_lint()
        false_positives = [i for i in issues if "BROKEN LINK" in i and "test-entity" in i]
        assert false_positives == []

    def test_detects_orphan_page(self, wiki_root):
        """Create a page not in index → should be flagged as orphan."""
        orphan = wiki_root / "wiki" / "entities" / "orphan-page.md"
        orphan.write_text(
            "---\ntitle: Orphan\ntype: entity\n---\n\n# Orphan\n\n## Overview\n\nNobody links here.",
            encoding="utf-8",
        )

        issues = _deterministic_lint()
        orphans = [i for i in issues if "ORPHAN" in i and "orphan-page" in i]
        assert len(orphans) == 1

    def test_does_not_flag_indexed_pages(self, wiki_root):
        """Pages listed in index.md should NOT be orphans."""
        issues = _deterministic_lint()
        # test-source, test-entity, test-concept are all in the fixture index
        false_orphans = [
            i for i in issues if "ORPHAN" in i and ("test-source" in i or "test-entity" in i or "test-concept" in i)
        ]
        assert false_orphans == []

    def test_detects_missing_frontmatter(self, wiki_root):
        """A page without --- at the start should be flagged."""
        bad = wiki_root / "wiki" / "concepts" / "no-frontmatter.md"
        bad.write_text("# No Frontmatter\n\nThis page has no YAML frontmatter.", encoding="utf-8")

        issues = _deterministic_lint()
        fm_issues = [i for i in issues if "NO FRONTMATTER" in i and "no-frontmatter" in i]
        assert len(fm_issues) == 1

    def test_valid_pages_no_frontmatter_issue(self, wiki_root):
        """All fixture pages start with --- → no frontmatter issues for them."""
        issues = _deterministic_lint()
        fm_issues = [
            i
            for i in issues
            if "NO FRONTMATTER" in i and ("test-source" in i or "test-entity" in i or "test-concept" in i)
        ]
        assert fm_issues == []

    def test_returns_list_of_strings(self, wiki_root):
        """_deterministic_lint() should always return a list of strings."""
        issues = _deterministic_lint()
        assert isinstance(issues, list)
        for issue in issues:
            assert isinstance(issue, str)
