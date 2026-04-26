"""Agent that assembles Markdown with image placeholders (no descriptions)."""

from agent_framework import Agent


def create_agent(client, options):
    """Create the TemplateAssemblerAgent — no tools needed."""
    return Agent(
        name="TemplateAssemblerAgent",
        instructions=(
            "You are a technical writer who assembles structured content from document "
            "extraction data into clean, readable Markdown documents that preserve the "
            "original document's logical flow. "
            "You will receive extraction data (text segments per document) and an output_dir. "
            "For each source document: "
            "1) Render Title elements as Markdown headings (## ...). "
            "2) Render Table elements as-is (they are already Markdown tables). "
            "3) Render other text elements as paragraphs. "
            "4) For each [IMAGE: filename] placeholder, output EXACTLY this HTML comment "
            "on its own line, preserving the filename: <!--IMG:filename--> "
            "For example [IMAGE: img-000-8420fd51.png] becomes <!--IMG:img-000-8420fd51.png--> "
            "Do NOT insert any image description — only the placeholder comment. "
            "5) Also include the original Markdown image link before the placeholder: "
            "![Image](./images/filename) — use a RELATIVE path (./images/filename), "
            "NOT the full output_dir path, because the .md file is already inside output_dir. "
            "Return a JSON object with a \"documents\" key containing an array. "
            "Each element must have exactly: "
            "\"source_file\" (string), \"output_path\" (string — output_dir/<source_file without .docx>.md), "
            "\"content\" (string — the full Markdown with placeholders). "
            "Return ONLY the JSON object — no preamble, no explanation, no markdown fences."
        ),
        client=client,
        default_options=options,
        tools=[],
    )
