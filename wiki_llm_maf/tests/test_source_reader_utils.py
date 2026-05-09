"""Unit tests for the pure helper functions in source_reader.py."""

import pytest

from afw_core.executors.source_reader import (
    _absorb_thin_concepts,
    _consolidate_extraction,
    _dedup_items,
    _filter_noise_entities,
    _find_matching_group,
    _fuzzy_merge_items,
    _has_code_block,
    _is_prefix_match,
    _merge_extractions,
    _merge_item_into,
    _should_merge_slugs,
    _slug_normalize,
)


# ---------------------------------------------------------------------------
# _slug_normalize
# ---------------------------------------------------------------------------

class TestSlugNormalize:
    def test_strips_trailing_s(self):
        assert _slug_normalize("tools") == "tool"

    def test_preserves_short_slug(self):
        # slug "bus" has len 3 → should NOT strip
        assert _slug_normalize("bus") == "bus"

    def test_no_trailing_s(self):
        assert _slug_normalize("agent") == "agent"

    def test_empty_string(self):
        assert _slug_normalize("") == ""

    def test_single_s(self):
        assert _slug_normalize("s") == "s"

    def test_strips_all_trailing_s(self):
        # rstrip("s") removes ALL trailing 's' chars
        assert _slug_normalize("stress") == "stre"


# ---------------------------------------------------------------------------
# _is_prefix_match
# ---------------------------------------------------------------------------

class TestIsPrefixMatch:
    def test_exact_match(self):
        assert _is_prefix_match("agent", "agent") is True

    def test_one_extra_segment(self):
        assert _is_prefix_match("logging", "logging-module") is True

    def test_reversed_order(self):
        assert _is_prefix_match("logging-module", "logging") is True

    def test_two_extra_segments(self):
        # "logging" vs "logging-module-extra" → 2 segments → False
        assert _is_prefix_match("logging", "logging-module-extra") is False

    def test_no_prefix(self):
        assert _is_prefix_match("agent", "workflow") is False

    def test_partial_prefix_not_at_hyphen(self):
        # "log" is prefix of "logging" but remainder is "ging" (no hyphen)
        assert _is_prefix_match("log", "logging") is False


# ---------------------------------------------------------------------------
# _should_merge_slugs
# ---------------------------------------------------------------------------

class TestShouldMergeSlugs:
    def test_exact(self):
        assert _should_merge_slugs("tool", "tool") is True

    def test_plural(self):
        assert _should_merge_slugs("tool", "tools") is True

    def test_prefix_match(self):
        assert _should_merge_slugs("logging", "logging-module") is True

    def test_unrelated(self):
        assert _should_merge_slugs("agent", "workflow") is False

    def test_similar_prefix_but_not_segment(self):
        # "configuration" vs "connection" — should NOT merge
        assert _should_merge_slugs("configuration", "connection") is False


# ---------------------------------------------------------------------------
# _has_code_block
# ---------------------------------------------------------------------------

class TestHasCodeBlock:
    def test_with_code(self):
        assert _has_code_block("some text\n```python\nprint()\n```") is True

    def test_without_code(self):
        assert _has_code_block("just plain text") is False


# ---------------------------------------------------------------------------
# _merge_item_into
# ---------------------------------------------------------------------------

class TestMergeItemInto:
    def test_appends_content(self):
        survivor = {"content": "AAA", "claims": ["c1"]}
        absorbed = {"content": "BBB", "claims": ["c2"]}
        _merge_item_into(survivor, absorbed)
        assert "AAA" in survivor["content"]
        assert "BBB" in survivor["content"]
        assert set(survivor["claims"]) == {"c1", "c2"}

    def test_no_duplicate_content(self):
        survivor = {"content": "AAA", "claims": []}
        absorbed = {"content": "AAA", "claims": []}
        _merge_item_into(survivor, absorbed)
        # Content should NOT be doubled
        assert survivor["content"] == "AAA"

    def test_empty_absorbed(self):
        survivor = {"content": "AAA", "claims": ["c1"]}
        absorbed = {"content": "", "claims": []}
        _merge_item_into(survivor, absorbed)
        assert survivor["content"] == "AAA"


# ---------------------------------------------------------------------------
# _find_matching_group
# ---------------------------------------------------------------------------

class TestFindMatchingGroup:
    def test_exact_key(self):
        groups = {"agent": {}, "workflow": {}}
        assert _find_matching_group("agent", groups) == "agent"

    def test_normalized_match(self):
        groups = {"tool": {}}
        assert _find_matching_group("tools", groups) == "tool"

    def test_prefix_match(self):
        groups = {"logging": {}}
        assert _find_matching_group("logging-module", groups) == "logging"

    def test_no_match(self):
        groups = {"agent": {}}
        assert _find_matching_group("workflow", groups) is None

    def test_empty_groups(self):
        assert _find_matching_group("agent", {}) is None


# ---------------------------------------------------------------------------
# _fuzzy_merge_items
# ---------------------------------------------------------------------------

class TestFuzzyMergeItems:
    def test_empty(self):
        assert _fuzzy_merge_items([]) == []

    def test_no_duplicates(self):
        items = [
            {"slug": "agent", "content": "A", "claims": []},
            {"slug": "workflow", "content": "B", "claims": []},
        ]
        result = _fuzzy_merge_items(items)
        assert len(result) == 2

    def test_merges_same_slug(self):
        items = [
            {"slug": "tool", "content": "chunk1", "claims": ["c1"]},
            {"slug": "tool", "content": "chunk2", "claims": ["c2"]},
        ]
        result = _fuzzy_merge_items(items)
        assert len(result) == 1
        assert "chunk1" in result[0]["content"]
        assert "chunk2" in result[0]["content"]

    def test_merges_plural(self):
        items = [
            {"slug": "agent", "content": "A", "claims": []},
            {"slug": "agents", "content": "B", "claims": []},
        ]
        result = _fuzzy_merge_items(items)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _dedup_items
# ---------------------------------------------------------------------------

class TestDedupItems:
    def test_single_item(self):
        items = [{"slug": "x", "content": "hello", "claims": []}]
        assert _dedup_items(items) == items

    def test_slug_merge(self):
        items = [
            {"slug": "tool", "content": "short", "claims": []},
            {"slug": "tools", "content": "longer content here", "claims": ["c1"]},
        ]
        result = _dedup_items(items)
        assert len(result) == 1
        # survivor is the one with longer content
        assert "longer content here" in result[0]["content"]
        assert "short" in result[0]["content"]

    def test_content_substring_dedup(self):
        items = [
            {"slug": "alpha", "content": "Tools extend agents", "claims": []},
            {"slug": "beta", "content": "Tools extend agents. They support MCP too.", "claims": []},
        ]
        result = _dedup_items(items)
        assert len(result) == 1
        assert "MCP" in result[0]["content"]

    def test_no_merge_unrelated(self):
        items = [
            {"slug": "agent", "content": "aaa", "claims": []},
            {"slug": "workflow", "content": "bbb", "claims": []},
        ]
        result = _dedup_items(items)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# _absorb_thin_concepts
# ---------------------------------------------------------------------------

class TestAbsorbThinConcepts:
    def test_single_concept(self):
        concepts = [{"slug": "x", "content": "short", "claims": []}]
        assert _absorb_thin_concepts(concepts) == concepts

    def test_absorbs_into_matching_substantial(self):
        concepts = [
            {"slug": "logging", "content": "x" * 300, "claims": []},       # substantial
            {"slug": "logging-module", "content": "thin", "claims": []},    # thin, matches
        ]
        result = _absorb_thin_concepts(concepts)
        assert len(result) == 1
        assert "thin" in result[0]["content"]

    def test_does_not_absorb_unrelated(self):
        concepts = [
            {"slug": "agent", "content": "x" * 300, "claims": []},
            {"slug": "workflow", "content": "thin", "claims": []},  # thin but unrelated
        ]
        result = _absorb_thin_concepts(concepts)
        # "workflow" should survive as its own item
        assert len(result) == 2

    def test_no_spurious_prefix_match(self):
        """configuration and connection should NOT merge (old bug)."""
        concepts = [
            {"slug": "connection", "content": "x" * 300, "claims": []},
            {"slug": "configuration", "content": "thin", "claims": []},
        ]
        result = _absorb_thin_concepts(concepts)
        assert len(result) == 2

    def test_preserves_code_block_concepts(self):
        concepts = [
            {"slug": "agent", "content": "x" * 300, "claims": []},
            {"slug": "tool", "content": "```python\nprint()```", "claims": []},  # has code
        ]
        result = _absorb_thin_concepts(concepts)
        # tool has code block → not thin → both survive
        assert len(result) == 2


# ---------------------------------------------------------------------------
# _filter_noise_entities
# ---------------------------------------------------------------------------

class TestFilterNoiseEntities:
    def test_keeps_normal_entity(self):
        entities = [{"slug": "agent", "type": "tool", "content": "short", "claims": []}]
        assert len(_filter_noise_entities(entities)) == 1

    def test_filters_noise(self):
        entities = [{"slug": "misc", "type": "other", "content": "tiny", "claims": []}]
        assert len(_filter_noise_entities(entities)) == 0

    def test_keeps_other_with_code(self):
        entities = [{"slug": "misc", "type": "other", "content": "```python\ncode```", "claims": []}]
        assert len(_filter_noise_entities(entities)) == 1

    def test_keeps_other_with_long_content(self):
        entities = [{"slug": "misc", "type": "other", "content": "x" * 200, "claims": []}]
        assert len(_filter_noise_entities(entities)) == 1


# ---------------------------------------------------------------------------
# _merge_extractions
# ---------------------------------------------------------------------------

class TestMergeExtractions:
    def test_merges_two_chunks(self):
        ext1 = {
            "slug": "doc", "title": "Doc", "summary": "S1",
            "key_takeaways": ["t1"], "claims": [{"text": "c1"}],
            "entities": [{"slug": "agent", "content": "A", "claims": []}],
            "concepts": [{"slug": "tool", "content": "T", "claims": []}],
        }
        ext2 = {
            "slug": "doc", "title": "Doc", "summary": "S2",
            "key_takeaways": ["t2", "t1"],  # t1 is duplicate
            "claims": [{"text": "c2"}],
            "entities": [{"slug": "agent", "content": "B", "claims": []}],
            "concepts": [{"slug": "workflow", "content": "W", "claims": []}],
        }
        result = _merge_extractions([ext1, ext2], "test.md")

        assert result["summary"] == "S1"  # from first chunk
        assert set(result["key_takeaways"]) == {"t1", "t2"}
        assert len(result["claims"]) == 2
        # entities with same slug should merge
        assert len(result["entities"]) == 1
        assert "A" in result["entities"][0]["content"]
        assert "B" in result["entities"][0]["content"]
        # concepts are different → 2
        assert len(result["concepts"]) == 2


# ---------------------------------------------------------------------------
# _consolidate_extraction
# ---------------------------------------------------------------------------

class TestConsolidateExtraction:
    def test_full_pipeline(self):
        extraction = {
            "concepts": [
                {"slug": "tool", "content": "x" * 300, "claims": []},
                {"slug": "tools", "content": "short dup", "claims": []},
            ],
            "entities": [
                {"slug": "good", "type": "tool", "content": "real", "claims": []},
                {"slug": "noise", "type": "other", "content": "tiny", "claims": []},
            ],
        }
        result = _consolidate_extraction(extraction)
        # tool/tools should merge into 1
        assert len(result["concepts"]) == 1
        # noise entity should be filtered
        assert len(result["entities"]) == 1
        assert result["entities"][0]["slug"] == "good"
