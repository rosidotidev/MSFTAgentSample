"""Build the scaled doc-ingest workflow with parallel vision + chunked assembly.

Graph:  DocExtractor ──▶ ParallelImageAnalyst ──▶ ChunkedTemplateAssembler ──▶ TemplateFillerMulti

Improvements over doc_ingest_tpl:
- Image analysis runs concurrently (asyncio.gather, bounded by semaphore)
- Template assembly splits long documents into heading-based chunks
- Each LLM call sees a small section → consistent quality on any doc length
"""

from agent_framework import WorkflowBuilder

from afw_core.executors.doc_extractor import DocExtractorExecutor
from afw_core.executors.parallel_image_analyst import ParallelImageAnalystExecutor
from afw_core.executors.chunked_template_assembler import ChunkedTemplateAssemblerExecutor
from afw_core.executors.template_filler_multi import TemplateFillerMultiExecutor


def build_doc_ingest_tpl_multi_workflow(client, options, output_dir: str):
    """Return a ready-to-run Workflow for the scaled template-based doc-ingest pipeline."""
    extractor = DocExtractorExecutor(client, options, output_dir)
    analyst = ParallelImageAnalystExecutor()
    assembler = ChunkedTemplateAssemblerExecutor(client, options)
    filler = TemplateFillerMultiExecutor()

    return (
        WorkflowBuilder(start_executor=extractor)
        .add_edge(extractor, analyst)
        .add_edge(analyst, assembler)
        .add_edge(assembler, filler)
        .build()
    )
