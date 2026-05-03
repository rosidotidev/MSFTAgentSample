"""Shared helper to load schema sections for agent instructions."""

import os
import re

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SCHEMA_PATH = os.path.join(_BASE_DIR, "schema.md")

_SECTION_RE = re.compile(
    r"<!-- SECTION:([\w-]+) -->\s*\n(.*?)<!-- /SECTION:\1 -->",
    re.DOTALL,
)


def _read_schema_file() -> str:
    with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return f.read()


def load_schema(*sections: str) -> str:
    """Load specific sections from schema.md by marker name.

    Usage:
        load_schema("core")              # only core
        load_schema("core", "templates") # core + templates
    """
    content = _read_schema_file()
    all_sections = {m.group(1): m.group(2).strip() for m in _SECTION_RE.finditer(content)}

    parts = []
    for name in sections:
        if name not in all_sections:
            raise ValueError(f"Schema section '{name}' not found. Available: {list(all_sections.keys())}")
        parts.append(all_sections[name])

    return "\n\n---\n\n".join(parts)


def load_full_schema() -> str:
    """Load all sections (core + templates + index-log)."""
    return load_schema("core", "templates", "index-log")
