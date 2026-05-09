"""Unit tests for integrator pure helpers: _normalize_slug, _pre_filter_slugs."""

from afw_core.executors.integrator import _normalize_slug, _pre_filter_slugs


class TestNormalizeSlug:
    def test_kebab_passthrough(self):
        assert _normalize_slug("agent-framework") == "agent-framework"

    def test_camel_case(self):
        assert _normalize_slug("openaiChatClient") == "openai-chat-client"

    def test_pascal_case(self):
        assert _normalize_slug("AgentFramework") == "agent-framework"

    def test_underscores(self):
        assert _normalize_slug("openai_chat_client") == "openai-chat-client"

    def test_mixed_upper_acronym(self):
        result = _normalize_slug("OpenAIChatClient")
        assert result == "open-ai-chat-client"

    def test_collapses_hyphens(self):
        assert _normalize_slug("foo--bar---baz") == "foo-bar-baz"

    def test_strips_edge_hyphens(self):
        assert _normalize_slug("-leading-trailing-") == "leading-trailing"

    def test_lowercase(self):
        assert _normalize_slug("FOO") == "foo"


class TestPreFilterSlugs:
    def test_exact_match(self):
        auto, remaining = _pre_filter_slugs(["agent"], ["agent", "tool"])
        assert auto == {"agent": "agent"}
        assert remaining == []

    def test_normalized_match(self):
        auto, remaining = _pre_filter_slugs(
            ["openai_chat_client"], ["openai-chat-client"]
        )
        assert auto == {"openai_chat_client": "openai-chat-client"}
        assert remaining == []

    def test_no_match_goes_to_remaining(self):
        auto, remaining = _pre_filter_slugs(["new-thing"], ["existing-thing"])
        assert auto == {}
        assert remaining == ["new-thing"]

    def test_mixed(self):
        auto, remaining = _pre_filter_slugs(
            ["AgentFramework", "brand-new", "tool"],
            ["agent-framework", "tool", "other"],
        )
        assert auto == {"AgentFramework": "agent-framework", "tool": "tool"}
        assert remaining == ["brand-new"]

    def test_empty_inputs(self):
        auto, remaining = _pre_filter_slugs([], ["agent"])
        assert auto == {}
        assert remaining == []

    def test_empty_existing(self):
        auto, remaining = _pre_filter_slugs(["agent"], [])
        assert auto == {}
        assert remaining == ["agent"]
