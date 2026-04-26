"""Build the doc-ingest workflow graph."""

from agent_framework import WorkflowBuilder

from afw_core.executors.doc_extractor import DocExtractorExecutor
from afw_core.executors.image_analyst import ImageAnalystExecutor
from afw_core.executors.content_assembler import ContentAssemblerExecutor


def build_doc_ingest_workflow(client, options, output_dir: str):
    """Return a ready-to-run Workflow for the doc-ingest pipeline.

    Graph:  DocExtractor ──▶ ImageAnalyst ──▶ ContentAssembler
    """
    extractor = DocExtractorExecutor(client, options, output_dir)
    analyst = ImageAnalystExecutor(client, options)
    assembler = ContentAssemblerExecutor(client, options)

    return (
        WorkflowBuilder(start_executor=extractor)
        .add_edge(extractor, analyst)
        .add_edge(analyst, assembler)
        .build()
    )
