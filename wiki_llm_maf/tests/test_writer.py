"""Tests for WriterExecutor — deterministic, no LLM."""

import json
import os

import pytest

from afw_core.executors.writer import (
    WriterExecutor,
    _render_entity_page,
    _render_concept_page,
    _render_source_page,
    _render_update,
)


class FakeContext:
    """Minimal WorkflowContext stub."""

    def __init__(self):
        self.messages: list[str] = []

    async def send_message(self, msg: str) -> None:
        self.messages.append(msg)


@pytest.fixture
def writer():
    return WriterExecutor()


@pytest.fixture
def ctx():
    return FakeContext()


# ── Sample extraction data ──────────────────────────────────────────────

_ENTITY = {
    "name": "WorkflowBuilder",
    "slug": "workflowbuilder",
    "type": "tool",
    "description": "A builder class for constructing workflows.",
    "content": "WorkflowBuilder wires executors together into a directed graph.",
}

_CONCEPT = {
    "name": "Workflow Definitions",
    "slug": "workflow-definitions",
    "definition": "Guidelines for defining workflows that connect executors.",
    "content": "Each file defines one workflow using WorkflowBuilder.",
}

_RAW_EXTRACTION = {
    "file_name": "test-doc.md",
    "slug": "test-doc",
    "title": "Test Document",
    "summary": "A test document about workflows.",
    "key_takeaways": ["Workflows connect executors.", "Use WorkflowBuilder."],
    "claims": [],
    "entities": [_ENTITY],
    "concepts": [_CONCEPT],
    "_origin": "raw",
}

_QA_EXTRACTION = {
    "file_name": "what-is-workflow_20260504.md",
    "slug": "what-is-workflow",
    "title": "What is a workflow?",
    "summary": "Explains what a workflow is.",
    "key_takeaways": ["A workflow connects executors."],
    "claims": [],
    "entities": [_ENTITY],
    "concepts": [_CONCEPT],
    "_origin": "questions_approved",
}


# ── _render_entity_page ─────────────────────────────────────────────────

class TestRenderEntityPage:
    """Entity pages should include entity_type and use the correct source prefix."""

    def test_raw_source_links_to_sources(self):
        page = _render_entity_page(_ENTITY, "test-doc", {})
        assert "## From [[sources/test-doc]]" in page

    def test_qa_source_links_to_synthesis(self):
        page = _render_entity_page(_ENTITY, "what-is-workflow", {}, source_prefix="synthesis")
        assert "## From [[synthesis/what-is-workflow]]" in page
        assert "## From [[sources/" not in page

    def test_default_prefix_is_sources(self):
        page = _render_entity_page(_ENTITY, "any-slug", {})
        assert "## From [[sources/any-slug]]" in page

    def test_entity_type_in_frontmatter(self):
        page = _render_entity_page(_ENTITY, "test-doc", {})
        assert 'entity_type: "tool"' in page

    def test_overview_section(self):
        page = _render_entity_page(_ENTITY, "test-doc", {})
        assert "## Overview" in page
        assert _ENTITY["description"] in page

    def test_content_preserved(self):
        page = _render_entity_page(_ENTITY, "test-doc", {})
        assert _ENTITY["content"] in page


# ── _render_concept_page ────────────────────────────────────────────────

class TestRenderConceptPage:
    """Concept pages should include definition and use the correct source prefix."""

    def test_raw_source_links_to_sources(self):
        page = _render_concept_page(_CONCEPT, "test-doc", {})
        assert "## From [[sources/test-doc]]" in page

    def test_qa_source_links_to_synthesis(self):
        page = _render_concept_page(_CONCEPT, "what-is-workflow", {}, source_prefix="synthesis")
        assert "## From [[synthesis/what-is-workflow]]" in page
        assert "## From [[sources/" not in page

    def test_default_prefix_is_sources(self):
        page = _render_concept_page(_CONCEPT, "any-slug", {})
        assert "## From [[sources/any-slug]]" in page

    def test_definition_section(self):
        page = _render_concept_page(_CONCEPT, "test-doc", {})
        assert "## Definition" in page
        assert _CONCEPT["definition"] in page

    def test_no_overview_section(self):
        """Concepts use Definition, not Overview (that's for entities)."""
        page = _render_concept_page(_CONCEPT, "test-doc", {})
        assert "## Overview" not in page

    def test_no_entity_type_in_frontmatter(self):
        """Concepts should NOT have entity_type in frontmatter."""
        page = _render_concept_page(_CONCEPT, "test-doc", {})
        assert "entity_type" not in page

    def test_type_is_concept(self):
        page = _render_concept_page(_CONCEPT, "test-doc", {})
        assert 'type: "concept"' in page


# ── _render_source_page ─────────────────────────────────────────────────

class TestRenderSourcePage:
    """Source pages list entities and concepts with correct prefixes."""

    def test_entities_listed(self):
        page = _render_source_page(_RAW_EXTRACTION)
        assert "[[entities/workflowbuilder]]" in page

    def test_concepts_listed(self):
        page = _render_source_page(_RAW_EXTRACTION)
        assert "[[concepts/workflow-definitions]]" in page

    def test_type_is_source(self):
        page = _render_source_page(_RAW_EXTRACTION)
        assert 'type: "source"' in page

    def test_key_takeaways(self):
        page = _render_source_page(_RAW_EXTRACTION)
        assert "- Workflows connect executors." in page


# ── _render_update ──────────────────────────────────────────────────────

class TestRenderUpdate:
    """Update render should use correct source prefix for new sections."""

    _EXISTING_ENTITY = (
        '---\ntitle: "WorkflowBuilder"\ntype: "entity"\nentity_type: "tool"\n'
        'created: "2026-05-01"\nupdated: "2026-05-01"\nsources: ["old-source"]\n---\n\n'
        "## Overview\nA builder class.\n\n"
        "## From [[sources/old-source]]\nOriginal content.\n"
    )

    _EXISTING_CONCEPT = (
        '---\ntitle: "Workflow Definitions"\ntype: "concept"\n'
        'created: "2026-05-01"\nupdated: "2026-05-01"\nsources: ["old-source"]\n---\n\n'
        "## Definition\nGuidelines for workflows.\n\n"
        "## From [[sources/old-source]]\nOriginal concept content.\n"
    )

    def test_update_entity_from_raw_uses_sources(self):
        entry = {"path": "wiki/entities/workflowbuilder.md", "action": "enrich", "detail": ""}
        result = _render_update(self._EXISTING_ENTITY, _RAW_EXTRACTION, entry, "test-doc", source_prefix="sources")
        assert "## From [[sources/test-doc]]" in result
        # Old section preserved
        assert "## From [[sources/old-source]]" in result

    def test_update_entity_from_qa_uses_synthesis(self):
        entry = {"path": "wiki/entities/workflowbuilder.md", "action": "enrich", "detail": ""}
        result = _render_update(self._EXISTING_ENTITY, _QA_EXTRACTION, entry, "what-is-workflow", source_prefix="synthesis")
        assert "## From [[synthesis/what-is-workflow]]" in result
        # Old section preserved
        assert "## From [[sources/old-source]]" in result

    def test_update_concept_from_qa_uses_synthesis(self):
        entry = {"path": "wiki/concepts/workflow-definitions.md", "action": "enrich", "detail": ""}
        result = _render_update(self._EXISTING_CONCEPT, _QA_EXTRACTION, entry, "what-is-workflow", source_prefix="synthesis")
        assert "## From [[synthesis/what-is-workflow]]" in result

    def test_update_adds_source_to_frontmatter(self):
        entry = {"path": "wiki/entities/workflowbuilder.md", "action": "enrich", "detail": ""}
        result = _render_update(self._EXISTING_ENTITY, _RAW_EXTRACTION, entry, "test-doc")
        assert '"test-doc"' in result
        assert '"old-source"' in result


# ── WriterExecutor.handle — integration ─────────────────────────────────

class TestWriterHandle:
    """Full handle() should derive source_prefix from _origin."""

    async def test_raw_origin_creates_entity_with_sources_prefix(self, wiki_root, writer, ctx):
        plan = {
            "pages_to_create": [
                {"path": "wiki/sources/test-doc.md", "page_type": "source"},
                {"path": "wiki/entities/workflowbuilder.md", "page_type": "entity"},
            ],
            "pages_to_update": [],
        }
        input_data = json.dumps({"plan": plan, "extraction": _RAW_EXTRACTION})
        await writer.handle(input_data, ctx)

        entity_path = wiki_root / "wiki" / "entities" / "workflowbuilder.md"
        content = entity_path.read_text(encoding="utf-8")
        assert "## From [[sources/test-doc]]" in content

    async def test_qa_origin_creates_entity_with_synthesis_prefix(self, wiki_root, writer, ctx):
        plan = {
            "pages_to_create": [
                {"path": "wiki/synthesis/what-is-workflow.md", "page_type": "synthesis"},
                {"path": "wiki/entities/workflowbuilder.md", "page_type": "entity"},
            ],
            "pages_to_update": [],
        }
        input_data = json.dumps({"plan": plan, "extraction": _QA_EXTRACTION})
        await writer.handle(input_data, ctx)

        entity_path = wiki_root / "wiki" / "entities" / "workflowbuilder.md"
        content = entity_path.read_text(encoding="utf-8")
        assert "## From [[synthesis/what-is-workflow]]" in content
        assert "[[sources/" not in content

    async def test_qa_origin_creates_concept_with_synthesis_prefix(self, wiki_root, writer, ctx):
        plan = {
            "pages_to_create": [
                {"path": "wiki/synthesis/what-is-workflow.md", "page_type": "synthesis"},
                {"path": "wiki/concepts/workflow-definitions.md", "page_type": "concept"},
            ],
            "pages_to_update": [],
        }
        input_data = json.dumps({"plan": plan, "extraction": _QA_EXTRACTION})
        await writer.handle(input_data, ctx)

        concept_path = wiki_root / "wiki" / "concepts" / "workflow-definitions.md"
        content = concept_path.read_text(encoding="utf-8")
        assert "## From [[synthesis/what-is-workflow]]" in content
        assert "## Definition" in content

    async def test_qa_origin_updates_use_synthesis_prefix(self, wiki_root, writer, ctx):
        # Pre-create an entity page to update
        entity_dir = wiki_root / "wiki" / "entities"
        entity_dir.mkdir(parents=True, exist_ok=True)
        (entity_dir / "workflowbuilder.md").write_text(
            '---\ntitle: "WorkflowBuilder"\ntype: "entity"\nentity_type: "tool"\n'
            'created: "2026-05-01"\nupdated: "2026-05-01"\nsources: ["old-source"]\n---\n\n'
            "## Overview\nA builder class.\n\n## From [[sources/old-source]]\nOld content.\n",
            encoding="utf-8",
        )

        plan = {
            "pages_to_create": [
                {"path": "wiki/synthesis/what-is-workflow.md", "page_type": "synthesis"},
            ],
            "pages_to_update": [
                {"path": "wiki/entities/workflowbuilder.md", "action": "enrich", "detail": "New info."},
            ],
        }
        input_data = json.dumps({"plan": plan, "extraction": _QA_EXTRACTION})
        await writer.handle(input_data, ctx)

        content = (entity_dir / "workflowbuilder.md").read_text(encoding="utf-8")
        assert "## From [[synthesis/what-is-workflow]]" in content
        assert "## From [[sources/old-source]]" in content

    async def test_entity_vs_concept_structure_differs(self, wiki_root, writer, ctx):
        """Entity pages have Overview + entity_type; concept pages have Definition, no entity_type."""
        plan = {
            "pages_to_create": [
                {"path": "wiki/sources/test-doc.md", "page_type": "source"},
                {"path": "wiki/entities/workflowbuilder.md", "page_type": "entity"},
                {"path": "wiki/concepts/workflow-definitions.md", "page_type": "concept"},
            ],
            "pages_to_update": [],
        }
        input_data = json.dumps({"plan": plan, "extraction": _RAW_EXTRACTION})
        await writer.handle(input_data, ctx)

        entity_content = (wiki_root / "wiki" / "entities" / "workflowbuilder.md").read_text(encoding="utf-8")
        concept_content = (wiki_root / "wiki" / "concepts" / "workflow-definitions.md").read_text(encoding="utf-8")

        # Entity has Overview, entity_type
        assert "## Overview" in entity_content
        assert "entity_type" in entity_content
        assert "## Definition" not in entity_content

        # Concept has Definition, no entity_type
        assert "## Definition" in concept_content
        assert "entity_type" not in concept_content
        assert "## Overview" not in concept_content
