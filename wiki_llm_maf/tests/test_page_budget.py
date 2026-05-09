"""Unit tests: page visit budget enforcement and querier instructions."""

import asyncio
import os

import pytest

from afw_core.agents.wiki_querier import _build_instructions, _DEFAULT_PAGE_VISIT_LIMIT, _DEFAULT_MIN_PAGE_RATIO


class TestQuerierInstructions:
    """Verify the prompt template injects the page limit correctly."""

    def test_default_limit_in_instructions(self):
        instructions = _build_instructions()
        assert f"at most {_DEFAULT_PAGE_VISIT_LIMIT} times" in instructions

    def test_custom_limit_in_instructions(self):
        instructions = _build_instructions(page_visit_limit=10)
        assert "at most 10 times" in instructions

    def test_sequential_navigation_in_instructions(self):
        instructions = _build_instructions()
        assert "ONE read_wiki_page call per turn" in instructions
        assert "Connections" in instructions

    def test_default_min_pages_in_instructions(self):
        # limit=5, ratio=0.6 → ceil(3.0) = 3
        instructions = _build_instructions()
        assert "at least 3 pages" in instructions

    def test_min_pages_custom_ratio(self):
        # limit=10, ratio=0.8 → ceil(8.0) = 8
        instructions = _build_instructions(page_visit_limit=10, min_page_ratio=0.8)
        assert "at least 8 pages" in instructions

    def test_min_pages_custom_limit_default_ratio(self):
        # limit=8, ratio=0.6 → ceil(4.8) = 5
        instructions = _build_instructions(page_visit_limit=8)
        assert "at least 5 pages" in instructions

    def test_min_pages_always_at_least_one(self):
        # limit=1, ratio=0.1 → ceil(0.1) = 1
        instructions = _build_instructions(page_visit_limit=1, min_page_ratio=0.1)
        assert "at least 1 pages" in instructions

    def test_min_pages_zero_ratio(self):
        # ratio=0.0 → max(1, ceil(0)) = 1
        instructions = _build_instructions(page_visit_limit=5, min_page_ratio=0.0)
        assert "at least 1 pages" in instructions


def _invoke_read(main_query, path: str) -> str:
    """Call the FunctionTool.invoke() coroutine and extract the text result."""
    loop = asyncio.new_event_loop()
    try:
        contents = loop.run_until_complete(
            main_query.read_wiki_page.invoke(arguments={"path": path})
        )
    finally:
        loop.close()
    # invoke returns list[Content]; each Content has a .text attribute
    return contents[0].text


class TestPageBudgetEnforcement:
    """Verify the tool-level counter blocks reads after budget is exceeded.

    These tests exercise the wrapper defined in main_query.py by importing
    and invoking the module-level counter/reset functions.
    """

    def test_reads_within_budget(self, wiki_root):
        """Reads within budget return page content normally."""
        # Import after wiki_root sets WIKI_ROOT_DIR
        import main_query

        main_query._page_read_limit = 3
        main_query._reset_page_counter()

        # Read an existing fixture page
        result = _invoke_read(main_query, "entities/test-entity")
        assert "pytest" in result.lower()
        assert main_query._page_read_counter == 1

    def test_budget_exceeded_returns_message(self, wiki_root):
        """After exceeding the budget, the tool returns a stop message."""
        import main_query

        main_query._page_read_limit = 2
        main_query._reset_page_counter()

        # Use up the budget
        _invoke_read(main_query, "entities/test-entity")
        _invoke_read(main_query, "concepts/test-concept")

        # Third call should be blocked
        result = _invoke_read(main_query, "entities/test-entity")
        assert "PAGE BUDGET EXCEEDED" in result
        assert main_query._page_read_counter == 3

    def test_counter_resets(self, wiki_root):
        """After reset, reads succeed again."""
        import main_query

        main_query._page_read_limit = 1
        main_query._reset_page_counter()

        _invoke_read(main_query, "entities/test-entity")
        # Budget exhausted
        result = _invoke_read(main_query, "entities/test-entity")
        assert "PAGE BUDGET EXCEEDED" in result

        # Reset
        main_query._reset_page_counter()
        result = _invoke_read(main_query, "entities/test-entity")
        assert "PAGE BUDGET EXCEEDED" not in result
        assert "pytest" in result.lower()

    def test_budget_from_env(self, wiki_root):
        """PAGE_VISIT_LIMIT from env is respected."""
        os.environ["PAGE_VISIT_LIMIT"] = "7"
        try:
            import main_query
            # Re-import won't re-execute module, so call the function directly
            assert main_query._page_visit_limit() == 7
        finally:
            del os.environ["PAGE_VISIT_LIMIT"]

    def test_default_budget(self):
        """Default budget is 5 when env var is not set."""
        # Ensure env var is not set
        os.environ.pop("PAGE_VISIT_LIMIT", None)

        import main_query
        assert main_query._page_visit_limit() == 5

    def test_min_page_ratio_from_env(self):
        """MIN_PAGE_RATIO from env is respected."""
        os.environ["MIN_PAGE_RATIO"] = "0.8"
        try:
            import main_query
            assert main_query._min_page_ratio() == 0.8
        finally:
            del os.environ["MIN_PAGE_RATIO"]

    def test_default_min_page_ratio(self):
        """Default min page ratio is 0.6 when env var is not set."""
        os.environ.pop("MIN_PAGE_RATIO", None)

        import main_query
        assert main_query._min_page_ratio() == 0.6
