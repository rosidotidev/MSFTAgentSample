import asyncio
import logging
import os

from dotenv import load_dotenv

from afw_core.llms.openai import create_client
from afw_core.models.doc_ingest import AssembledDocumentList
from afw_core.workflows.doc_ingest_tpl import build_doc_ingest_tpl_workflow

# Logging
logging.basicConfig(level=logging.WARNING, format="%(name)s %(levelname)s %(message)s")
logging.getLogger("agent_framework").setLevel(logging.INFO)

load_dotenv()

INPUT_DIR = os.getenv("DOC_INGEST_INPUT_DIR", "input/docx")
OUTPUT_DIR = os.getenv("DOC_INGEST_OUTPUT_DIR", "output/doc_ingest")


async def main():
    client, options = create_client(
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        model=os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
    )

    workflow = build_doc_ingest_tpl_workflow(client, options, OUTPUT_DIR)

    print("🚀 Doc-ingest template workflow is online...")

    async for event in workflow.run(
        f'input_dir="{INPUT_DIR}", output_dir="{OUTPUT_DIR}"',
        stream=True,
    ):
        if event.type == "executor_invoked":
            label = {
                "doc_extractor": f"📖 Extracting documents from {INPUT_DIR}",
                "image_analyst_stateful": "🔍 Analysing images",
                "template_assembler": "📝 Assembling Markdown templates",
                "template_filler": "🔧 Filling image descriptions into templates",
            }.get(event.executor_id, event.executor_id)
            print(f"\n{label}...")

        elif event.type == "executor_completed":
            print(f"   ✓ {event.executor_id} completed")

        elif event.type == "output":
            assembled = AssembledDocumentList.model_validate_json(event.data)
            print(f"\n   Assembled {len(assembled.documents)} document(s)")
            for doc in assembled.documents:
                print(f"   ✅ {doc.source_file} → {doc.output_path}")

    print("\n🏁 Doc-ingest template workflow completed.")


if __name__ == "__main__":
    asyncio.run(main())
