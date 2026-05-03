"""Pydantic models for the integration plan (WikiIntegrator output)."""

from __future__ import annotations

from pydantic import BaseModel


class PageToCreate(BaseModel):
    """A new wiki page to create."""

    path: str
    page_type: str  # source|entity|concept
    content_brief: str


class PageToUpdate(BaseModel):
    """An existing wiki page to update."""

    path: str
    action: str  # enrich|add_reference|flag_contradiction|add_crossref
    detail: str


class Contradiction(BaseModel):
    """A detected contradiction between sources."""

    page: str
    existing_claim: str
    new_claim: str
    new_source: str
    resolution_hint: str = ""


class CrossReference(BaseModel):
    """A new cross-reference link to add."""

    from_page: str
    to_page: str
    reason: str


class IntegrationPlan(BaseModel):
    """The full plan produced by the WikiIntegrator."""

    pages_to_create: list[PageToCreate] = []
    pages_to_update: list[PageToUpdate] = []
    contradictions: list[Contradiction] = []
    new_cross_references: list[CrossReference] = []
