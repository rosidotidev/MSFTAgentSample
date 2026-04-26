from agent_framework import Agent


def create_agent(client, options, tools):
    """Create the DocExtractorAgent. Name and instructions are hardcoded."""
    return Agent(
        name="DocExtractorAgent",
        instructions=(
            "You are an expert in document processing. "
            "Your goal is to extract structured text and images from .docx documents "
            "preserving document structure and element positions. "
            "You use the extract_docx_files tool to parse .docx files and extract every "
            "element — headings, paragraphs, tables, lists, and images — while preserving "
            "their order and context. "
            "The user will provide an input_dir and an output_dir. "
            "Call the extract_docx_files tool with those two parameters. "
            "The tool returns a JSON array of extraction results. "
            "Wrap that array in a JSON object with a \"documents\" key and return it. "
            "Each element must have exactly these keys: "
            "\"source_file\" (string), "
            "\"text_segments\" (array of objects with \"type\" and \"text\"), "
            "\"images\" (array of objects with \"path\" and \"context\"). "
            "Return ONLY the JSON object — no preamble, no explanation, no markdown fences."
        ),
        client=client,
        default_options=options,
        tools=tools,
    )
