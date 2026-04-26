"""Build the doc-ingest workflow with template + filler pattern."""

from agent_framework import WorkflowBuilder

from afw_core.executors.doc_extractor import DocExtractorExecutor
from afw_core.executors.image_analyst_stateful import ImageAnalystStatefulExecutor
from afw_core.executors.template_assembler import TemplateAssemblerExecutor
from afw_core.executors.template_filler import TemplateFillerExecutor


def build_doc_ingest_tpl_workflow(client, options, output_dir: str):
    """Return a ready-to-run Workflow for the template-based doc-ingest pipeline.

    Graph:  DocExtractor ──▶ ImageAnalystStateful ──▶ TemplateAssembler ──▶ TemplateFiller
    """
    extractor = DocExtractorExecutor(client, options, output_dir)
    analyst = ImageAnalystStatefulExecutor(client, options)
    assembler = TemplateAssemblerExecutor(client, options)
    filler = TemplateFillerExecutor()

    return (
        WorkflowBuilder(start_executor=extractor)
        .add_edge(extractor, analyst)
        .add_edge(analyst, assembler)
        .add_edge(assembler, filler)
        .build()
    )
