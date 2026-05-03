"""Pydantic models for source extraction (SourceReader output)."""

from __future__ import annotations

from pydantic import BaseModel


class Claim(BaseModel):
    """A single factual assertion from a source."""

    text: str
    context: str
    entities: list[str] = []
    concepts: list[str] = []


class EntityMention(BaseModel):
    """An entity mentioned in a source."""

    name: str
    slug: str
    type: str  # person|tool|company|project|other
    description: str
    content: str
    claims: list[str] = []


class ConceptMention(BaseModel):
    """A concept discussed in a source."""

    name: str
    slug: str
    definition: str
    content: str
    claims: list[str] = []


class SourceExtraction(BaseModel):
    """Complete structured extraction from a single source document."""

    file_name: str
    slug: str
    title: str
    summary: str
    key_takeaways: list[str]
    claims: list[Claim] = []
    entities: list[EntityMention] = []
    concepts: list[ConceptMention] = []
