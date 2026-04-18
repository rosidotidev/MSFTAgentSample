import os
from typing import Annotated

from agent_framework import tool


@tool
def read_file(file_name: Annotated[str, "Name of the file to read from the input directory"]) -> str:
    """Read and return the contents of a file from the input directory."""
    path = os.path.join("input", file_name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()
