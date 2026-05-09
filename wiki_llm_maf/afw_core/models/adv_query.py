"""Pydantic models for ADV_ query pipeline (plan → walk → answer)."""

from __future__ import annotations

from pydantic import BaseModel


class ADV_PageRequest(BaseModel):
    """A single page selected by the Planner from the wiki index."""

    path: str  # e.g. "concepts/materials-product-innovation"
    reason: str  # why this page is relevant to the query


class ADV_QueryPlan(BaseModel):
    """Output of the ADV_QueryPlannerAgent: ordered list of seed pages to read."""

    pages: list[ADV_PageRequest]
