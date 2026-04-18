import os
from datetime import datetime
from typing import Annotated

from agent_framework import tool


@tool
def write_file(content: Annotated[str, "The content to write to the output file"]) -> str:
    """Write content to an execution result file in the output directory. Returns the file path."""
    os.makedirs("output", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    file_name = f"execution_result_{timestamp}.md"
    path = os.path.join("output", file_name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"File written: {path}"
