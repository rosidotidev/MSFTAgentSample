"""Tests for adv_answerer detail-level prompts and main_query_adv prefix parsing."""

from unittest.mock import MagicMock, patch

import pytest


# ── adv_answerer agent tests ─────────────────────────────────────────────────

class TestAnswererDetailLevels:
    """Verify that create_agent selects the correct instructions per level."""

    @pytest.fixture(autouse=True)
    def _load_module(self):
        from afw_core.agents import adv_answerer
        self.mod = adv_answerer
        self.client = MagicMock()
        self.options = {}

    @patch("afw_core.agents.adv_answerer.Agent")
    def test_default_is_standard(self, mock_agent):
        self.mod.create_agent(self.client, self.options)
        _, kwargs = mock_agent.call_args
        assert kwargs["instructions"] == self.mod.INSTRUCTIONS_STANDARD

    @patch("afw_core.agents.adv_answerer.Agent")
    def test_brief(self, mock_agent):
        self.mod.create_agent(self.client, self.options, detail_level="brief")
        _, kwargs = mock_agent.call_args
        assert kwargs["instructions"] == self.mod.INSTRUCTIONS_BRIEF

    @patch("afw_core.agents.adv_answerer.Agent")
    def test_standard_explicit(self, mock_agent):
        self.mod.create_agent(self.client, self.options, detail_level="standard")
        _, kwargs = mock_agent.call_args
        assert kwargs["instructions"] == self.mod.INSTRUCTIONS_STANDARD

    @patch("afw_core.agents.adv_answerer.Agent")
    def test_full(self, mock_agent):
        self.mod.create_agent(self.client, self.options, detail_level="full")
        _, kwargs = mock_agent.call_args
        assert kwargs["instructions"] == self.mod.INSTRUCTIONS_FULL

    @patch("afw_core.agents.adv_answerer.Agent")
    def test_unknown_level_falls_back_to_standard(self, mock_agent):
        self.mod.create_agent(self.client, self.options, detail_level="xyz")
        _, kwargs = mock_agent.call_args
        assert kwargs["instructions"] == self.mod.INSTRUCTIONS_STANDARD

    def test_legacy_alias_equals_full(self):
        assert self.mod.INSTRUCTIONS is self.mod.INSTRUCTIONS_FULL

    def test_valid_detail_levels_tuple(self):
        assert self.mod.VALID_DETAIL_LEVELS == ("brief", "standard", "full")


class TestInstructionContent:
    """Verify key rules appear in the right instruction sets."""

    @pytest.fixture(autouse=True)
    def _load_module(self):
        from afw_core.agents import adv_answerer
        self.mod = adv_answerer

    def test_brief_has_concise_directive(self):
        assert "CONCISE" in self.mod.INSTRUCTIONS_BRIEF

    def test_brief_has_sentence_limit(self):
        assert "1-3 sentences" in self.mod.INSTRUCTIONS_BRIEF

    def test_standard_has_focused_directive(self):
        assert "FOCUSED" in self.mod.INSTRUCTIONS_STANDARD

    def test_standard_allows_paraphrase(self):
        assert "paraphrase" in self.mod.INSTRUCTIONS_STANDARD

    def test_full_has_preserve_directive(self):
        assert "PRESERVE" in self.mod.INSTRUCTIONS_FULL

    def test_full_has_verbatim_rule(self):
        assert "verbatim" in self.mod.INSTRUCTIONS_FULL

    def test_all_share_common_rules(self):
        for instructions in (
            self.mod.INSTRUCTIONS_BRIEF,
            self.mod.INSTRUCTIONS_STANDARD,
            self.mod.INSTRUCTIONS_FULL,
        ):
            assert "DO NOT use your training data" in instructions
            assert "[[category/slug]]" in instructions
            assert "meta-commentary" in instructions
            assert "DO NOT synthesize" in instructions


# ── prefix parsing tests ─────────────────────────────────────────────────────

class TestParsePrefixes:
    """Verify _parse_detail_prefix from main_query_adv."""

    @pytest.fixture(autouse=True)
    def _load_module(self):
        import main_query_adv
        self.mod = main_query_adv

    def test_no_prefix_returns_standard(self):
        q, level = self.mod._parse_detail_prefix("What is X?")
        assert q == "What is X?"
        assert level == "standard"

    def test_brief_prefix(self):
        q, level = self.mod._parse_detail_prefix("!b Who created Y?")
        assert q == "Who created Y?"
        assert level == "brief"

    def test_full_prefix(self):
        q, level = self.mod._parse_detail_prefix("!f Explain architecture of Z")
        assert q == "Explain architecture of Z"
        assert level == "full"

    def test_standard_prefix(self):
        q, level = self.mod._parse_detail_prefix("!s What is X?")
        assert q == "What is X?"
        assert level == "standard"

    def test_prefix_strips_extra_whitespace(self):
        q, level = self.mod._parse_detail_prefix("!b   lots of space  ")
        assert q == "lots of space"
        assert level == "brief"

    def test_prefix_without_space_is_not_parsed(self):
        q, level = self.mod._parse_detail_prefix("!bno space")
        assert q == "!bno space"
        assert level == "standard"

    def test_prefix_case_sensitive(self):
        q, level = self.mod._parse_detail_prefix("!B uppercase")
        assert q == "!B uppercase"
        assert level == "standard"

    def test_empty_question_after_prefix(self):
        q, level = self.mod._parse_detail_prefix("!b ")
        assert q == ""
        assert level == "brief"
