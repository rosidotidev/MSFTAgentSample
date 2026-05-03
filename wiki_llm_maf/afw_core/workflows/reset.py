"""Workflow: wiki reset (single-step pipeline)."""

from __future__ import annotations

from agent_framework import WorkflowBuilder

from ..executors.reset import ResetExecutor


def build_reset_workflow():
    """Build and return the reset workflow."""
    reset = ResetExecutor()

    workflow = (
        WorkflowBuilder(start_executor=reset)
        .build()
    )
    return workflow
