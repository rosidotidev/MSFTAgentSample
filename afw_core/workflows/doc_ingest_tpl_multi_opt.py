"""Build the LLM-minimal doc-ingest workflow.

Graph:  DocExtractorDirect ──▶ ParallelImageAnalyst ──▶ DeterministicAssembler ──▶ TemplateFillerMulti

LLM usage: ONLY the parallel vision calls for image descriptions.
Everything else is pure Python — extraction, Markdown assembly, and filling.
"""

from agent_framework import WorkflowBuilder

from afw_core.executors.doc_extractor_direct import DocExtractorDirectExecutor
from afw_core.executors.parallel_image_analyst import ParallelImageAnalystExecutor
from afw_core.executors.deterministic_assembler import DeterministicAssemblerExecutor
from afw_core.executors.template_filler_multi import TemplateFillerMultiExecutor


def build_doc_ingest_tpl_multi_opt_workflow(input_dir: str, output_dir: str):
    """Return a ready-to-run Workflow for the LLM-minimal doc-ingest pipeline.

    Note: no client/options needed — only the ParallelImageAnalyst uses
    OpenAI, and it creates its own AsyncOpenAI client internally.
    """
    extractor = DocExtractorDirectExecutor(input_dir, output_dir)
    analyst = ParallelImageAnalystExecutor()
    assembler = DeterministicAssemblerExecutor()
    filler = TemplateFillerMultiExecutor()

    return (
        WorkflowBuilder(start_executor=extractor)
        .add_edge(extractor, analyst)
        .add_edge(analyst, assembler)
        .add_edge(assembler, filler)
        .build()
    )
