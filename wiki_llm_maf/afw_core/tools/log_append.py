"""Tool: append an entry to wiki/log.md."""

from __future__ import annotations

import os
from typing import Annotated

from agent_framework import tool

_DEFAULT_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _base_dir() -> str:
    return os.environ.get("WIKI_ROOT_DIR", _DEFAULT_BASE)


@tool
def append_log(
    entry: Annotated[str, "The log entry to append (markdown formatted)"],
) -> str:
    """Append an entry to wiki/log.md."""
    log_path = os.path.join(_base_dir(), "wiki", "log.md")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n{entry}\n")
    return "OK: Log entry appended."
