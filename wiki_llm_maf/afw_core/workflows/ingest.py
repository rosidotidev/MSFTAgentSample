"""Workflow: per-source ingest loop using WorkflowBuilder with back-edge.

Pattern: Scanner → Dispatcher → Reader → Integrator → Writer → Validator → IndexUpdater → Dispatcher
The Dispatcher holds the file queue. When empty, it yields output (ends the workflow).
"""

from __future__ import annotations

from agent_framework import WorkflowBuilder

from ..executors.scanner import ScannerExecutor
from ..executors.dispatcher import DispatcherExecutor
from ..executors.source_reader import SourceReaderExecutor
from ..executors.integrator import IntegratorExecutor
from ..executors.writer import WriterExecutor
from ..executors.write_validator import WriteValidatorExecutor
from ..executors.index_updater import IndexUpdaterExecutor


def build_ingest_workflow(client, options):
    """Build and return the ingest workflow with per-source looping."""
    scanner = ScannerExecutor()
    dispatcher = DispatcherExecutor()
    reader = SourceReaderExecutor(client, options)
    integrator = IntegratorExecutor(client, options)
    writer = WriterExecutor(client, options)
    validator = WriteValidatorExecutor()
    index_updater = IndexUpdaterExecutor()

    workflow = (
        WorkflowBuilder(start_executor=scanner)
        .add_edge(scanner, dispatcher)
        .add_edge(dispatcher, reader)
        .add_edge(reader, integrator)
        .add_edge(integrator, writer)
        .add_edge(writer, validator)
        .add_edge(validator, index_updater)
        .add_edge(index_updater, dispatcher)  # back-edge: loop
        .build()
    )
    return workflow

