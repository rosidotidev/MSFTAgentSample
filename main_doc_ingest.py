import asyncio
import logging
import os

from dotenv import load_dotenv

from afw_core.llms.openai import create_client
from afw_core.tools.docx_extractor import extract_docx_files
from afw_core.tools.image_describer import describe_images
from afw_core.tools.markdown_writer import write_markdown
from afw_core.agents.doc_extractor import create_agent as create_extractor_agent
from afw_core.agents.image_analyst import create_agent as create_analyst_agent
from afw_core.agents.content_assembler import create_agent as create_assembler_agent
from afw_core.models.doc_ingest import (
    DocumentExtractionList,
    DescribedImageList,
    AssembledDocumentList,
)

# Enable debug logging only for agent_framework
logging.basicConfig(level=logging.WARNING, format="%(name)s %(levelname)s %(message)s")
logging.getLogger("agent_framework").setLevel(logging.INFO)
logging.getLogger("afw_core.tools.image_describer").setLevel(logging.DEBUG)

load_dotenv()

INPUT_DIR = os.getenv("DOC_INGEST_INPUT_DIR", "input/docx")
OUTPUT_DIR = os.getenv("DOC_INGEST_OUTPUT_DIR", "output/doc_ingest")


async def main():
    # --- Shared resources ------------------------------------------------------
    client, options = create_client(
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        model=os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
    )

    # --- Create agents ---------------------------------------------------------
    extractor_agent = create_extractor_agent(
        client=client, options=options, tools=[extract_docx_files],
    )
    analyst_agent = create_analyst_agent(
        client=client, options=options, tools=[describe_images],
    )
    assembler_agent = create_assembler_agent(
        client=client, options=options, tools=[write_markdown],
    )

    print("🚀 Doc-ingest pipeline is online...")

    # --- Step 1: Extract text and images from .docx ----------------------------
    print(f"\n📖 Step 1: Extracting documents from {INPUT_DIR}...")
    extract_response = await extractor_agent.run(
        f"input_dir=\"{INPUT_DIR}\", output_dir=\"{OUTPUT_DIR}\""
    )
    extraction = DocumentExtractionList.model_validate_json(extract_response.text)
    print(f"   Extracted {len(extraction.documents)} document(s)")

    # --- Step 2: Describe images -----------------------------------------------
    print("\n🔍 Step 2: Analysing images...")
    describe_response = await analyst_agent.run(extract_response.text)
    described = DescribedImageList.model_validate_json(describe_response.text)
    print(f"   Described {len(described.images)} image(s)")
    for img in described.images:
        print(f"   📷 {img.path} — agent description len={len(img.description)}")
        print(f"      Preview: {img.description[:150]}...")

    # --- Step 3: Assemble Markdown ---------------------------------------------
    print("\n📝 Step 3: Assembling Markdown documents...")
    assemble_response = await assembler_agent.run(
        f"extraction:\n{extract_response.text}\n\n"
        f"descriptions:\n{describe_response.text}\n\n"
        f"output_dir=\"{OUTPUT_DIR}\""
    )
    assembled = AssembledDocumentList.model_validate_json(assemble_response.text)
    print(f"   Assembled {len(assembled.documents)} document(s)")

    for doc in assembled.documents:
        print(f"   ✅ {doc.source_file} → {doc.output_path}")

    print("\n🏁 Doc-ingest pipeline completed.")


if __name__ == "__main__":
    asyncio.run(main())
