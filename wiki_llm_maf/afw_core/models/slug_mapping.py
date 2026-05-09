"""Pydantic model for slug mapper output (structured output)."""

from __future__ import annotations

from pydantic import BaseModel


class SlugMapping(BaseModel):
    """LLM output: maps new slugs to existing wiki slugs or "NEW"."""

    entity_mapping: dict[str, str]   # new-slug → existing-slug or "NEW"
    concept_mapping: dict[str, str]  # new-slug → existing-slug or "NEW"
