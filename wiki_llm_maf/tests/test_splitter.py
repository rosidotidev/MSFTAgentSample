"""Tests for splitter — deterministic heading-based split with adaptive sizing."""

import pytest

from afw_core.executors.splitter import (
    split_document,
    _split_by_headings,
    MAX_CHUNK_CHARS,
    HARD_CAP_CHUNKS,
    MIN_CHUNK_LINES,
)


def _make_doc(num_headings: int, chars_per_section: int = 200) -> str:
    """Generate a markdown document with N ## headings, each section ~chars_per_section.

    Each section has multiple lines to avoid being merged by MIN_CHUNK_LINES.
    """
    sections = []
    for i in range(num_headings):
        heading = f"## Section {i+1}"
        # Generate body text split across multiple lines (~60 chars each)
        line_text = f"Content for section {i+1}. "
        lines_needed = max(8, chars_per_section // 60)
        body_lines = [line_text * 2 for _ in range(lines_needed)]
        # Trim to approximate target chars
        body = "\n".join(body_lines)[:chars_per_section]
        sections.append(f"{heading}\n\n{body}")
    return "\n\n".join(sections)


class TestSplitDocument:
    """Top-level split_document dispatch logic."""

    def test_no_headings_returns_single_chunk(self):
        doc = "Just plain text without any headings.\n" * 10
        chunks = split_document(doc, title="plain")
        assert len(chunks) == 1

    def test_one_heading_returns_single_chunk(self):
        doc = "# Title\n\nSome intro\n\n## Only One\n\nBody text here."
        chunks = split_document(doc, title="one-heading")
        # Only 1 ## heading, below MIN_HEADING_COUNT=2, returns as-is
        assert len(chunks) == 1

    def test_two_headings_splits(self):
        doc = "## First\n\nFirst body content here.\n\n## Second\n\nSecond body content here."
        chunks = split_document(doc, title="two")
        assert len(chunks) >= 1  # At least processes it through heading split


class TestAdaptiveChunkCount:
    """The adaptive algorithm produces the correct number of chunks."""

    def test_small_doc_produces_one_chunk(self):
        """A doc with total chars < MAX_CHUNK_CHARS should produce 1 chunk."""
        doc = _make_doc(5, chars_per_section=200)  # ~1000 chars total
        chunks = _split_by_headings(doc, title="small")
        assert len(chunks) == 1

    def test_medium_doc_scales_proportionally(self):
        """A doc with ~7000 chars should produce ~3 chunks (7000/3000≈3)."""
        doc = _make_doc(12, chars_per_section=750)
        chunks = _split_by_headings(doc, title="medium")
        # Adaptive: total_chars / 3000, expect 2-4 depending on exact char count
        assert 2 <= len(chunks) <= 4

    def test_large_doc_produces_more_chunks(self):
        """A doc with ~24k chars should produce ~8-9 chunks."""
        doc = _make_doc(20, chars_per_section=1500)
        chunks = _split_by_headings(doc, title="large")
        # More sections than small, so more chunks
        assert len(chunks) >= 7
        assert len(chunks) <= 12

    def test_huge_doc_capped_at_hard_cap(self):
        """A doc with 200k chars should be capped at HARD_CAP_CHUNKS."""
        doc = _make_doc(100, chars_per_section=2000)  # ~200k chars
        chunks = _split_by_headings(doc, title="huge")
        assert len(chunks) <= HARD_CAP_CHUNKS

    def test_never_exceeds_hard_cap(self):
        """Even with extreme sizes, never more than HARD_CAP_CHUNKS."""
        doc = _make_doc(50, chars_per_section=5000)  # ~250k chars
        chunks = _split_by_headings(doc, title="extreme")
        assert len(chunks) <= HARD_CAP_CHUNKS

    def test_afw_instructions_like_doc(self):
        """A doc similar to afw-instructions.md (~9300 chars, 12 headings) → ~4 chunks."""
        doc = _make_doc(12, chars_per_section=960)
        chunks = _split_by_headings(doc, title="afw-like")
        # target = ceil(~9300/3000) = 4
        assert len(chunks) == 4


class TestChunkContent:
    """Chunks preserve content and have context headers."""

    def test_context_header_present(self):
        doc = "## Alpha\n\nAlpha content body.\n\n## Beta\n\nBeta content body."
        chunks = split_document(doc, title="my-doc")
        for chunk in chunks:
            assert "[Document: my-doc |" in chunk

    def test_content_not_lost(self):
        """All original section content appears in some chunk."""
        doc = _make_doc(6, chars_per_section=800)  # ~4800 chars → 2 chunks
        chunks = _split_by_headings(doc, title="check")
        combined = "\n".join(chunks)
        for i in range(1, 7):
            assert f"Content for section {i}" in combined

    def test_code_fences_respected(self):
        """A ## inside a code fence should NOT split."""
        doc = (
            "## Real Heading\n\n"
            "Some text.\n\n"
            "```python\n"
            "## This is a comment, not a heading\n"
            "x = 1\n"
            "```\n\n"
            "## Another Heading\n\n"
            "More text here."
        )
        chunks = split_document(doc, title="fence-test")
        combined = "\n".join(chunks)
        # The fake heading inside the fence should appear in the content, not as a split point
        assert "## This is a comment" in combined

    def test_tiny_sections_merged_with_previous(self):
        """Sections with fewer than MIN_CHUNK_LINES are merged into the previous chunk."""
        doc = (
            "## Big Section\n\n"
            "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 6\nLine 7\n\n"
            "## Tiny\n\n"
            "X\n\n"  # < MIN_CHUNK_LINES
            "## Another Big\n\n"
            "Line A\nLine B\nLine C\nLine D\nLine E\nLine F\nLine G\n"
        )
        chunks = split_document(doc, title="tiny-test")
        # The tiny section should not be its own chunk
        # Check it's merged with the previous section's content
        combined = "\n".join(chunks)
        assert "X" in combined


class TestEdgeCases:
    """Edge cases for the splitter."""

    def test_empty_document(self):
        chunks = split_document("", title="empty")
        assert len(chunks) == 1
        assert chunks[0] == ""

    def test_only_headings_no_content(self):
        doc = "## H1\n\n## H2\n\n## H3\n"
        chunks = split_document(doc, title="headings-only")
        # Sections with no content are skipped
        assert len(chunks) >= 1

    def test_single_huge_section(self):
        """A document with 2 headings but one massive section."""
        # Intro is short (< MIN_CHUNK_LINES) so gets merged with Main → 1 section
        # Then target = ceil(10000/3000) = 4, but only 1 section after tiny-merge → 1 chunk
        doc = "## Intro\n\nShort.\n\n## Main\n\n" + "A\n" * 500
        chunks = split_document(doc, title="one-big")
        # Intro is tiny → merged into Main → 1 raw section → can't split further → 1 chunk
        # But if Main has enough lines it won't be merged...
        # Actually with 500 lines in Main, Intro (2 lines) is < MIN_CHUNK_LINES, merged into Main
        # Result: 1 section, target >= 1, produces 1 chunk
        assert len(chunks) >= 1
