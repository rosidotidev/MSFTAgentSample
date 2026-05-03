"""Executor: deterministic post-write validation."""

from __future__ import annotations

import json
import logging
import os
import re

from agent_framework import Executor, handler, WorkflowContext

logger = logging.getLogger(__name__)

_DEFAULT_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _base_dir() -> str:
    return os.environ.get("WIKI_ROOT_DIR", _DEFAULT_BASE)


def _page_exists(link_path: str) -> bool:
    """Check if a wikilink target resolves to an existing file."""
    wiki_dir = os.path.join(_base_dir(), "wiki")
    # link_path could be "entities/agent-framework" or "concepts/tools"
    candidate = os.path.join(wiki_dir, link_path + ".md")
    return os.path.exists(candidate)


class WriteValidatorExecutor(Executor):
    """Validates written pages with deterministic checks (no LLM)."""

    def __init__(self):
        super().__init__(id="write_validator")

    @handler
    async def handle(self, input: str, ctx: WorkflowContext[str]) -> None:
        data = json.loads(input)
        written_pages: list[str] = data.get("written_pages", [])
        extraction: dict = data.get("extraction", {})
        issues: list[str] = []

        for rel_path in written_pages:
            abs_path = os.path.join(_base_dir(), rel_path)
            if not os.path.exists(abs_path):
                issues.append(f"MISSING: {rel_path} — file was not actually created")
                continue

            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Check 1: Non-empty content
            if len(content.strip()) < 50:
                issues.append(f"TOO SHORT: {rel_path} — less than 50 chars")

            # Check 2: Has frontmatter
            if not content.startswith("---"):
                issues.append(f"NO FRONTMATTER: {rel_path} — must start with ---")

            # Check 3: Frontmatter has required fields
            fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
            if fm_match:
                fm = fm_match.group(1)
                if "title:" not in fm:
                    issues.append(f"MISSING TITLE: {rel_path} — frontmatter lacks title:")
                if "type:" not in fm:
                    issues.append(f"MISSING TYPE: {rel_path} — frontmatter lacks type:")
            else:
                issues.append(f"BAD FRONTMATTER: {rel_path} — could not parse frontmatter block")

            # Check 4: Source pages should reference their source file
            if "/sources/" in rel_path:
                if "source:" not in content and "sources:" not in content and "source_file:" not in content:
                    issues.append(f"NO SOURCE REF: {rel_path} — source page lacks source: field")

            # Check 5: No placeholder content
            placeholders = ["TODO", "PLACEHOLDER", "INSERT HERE", "TBD"]
            for ph in placeholders:
                if ph in content:
                    issues.append(f"PLACEHOLDER: {rel_path} — contains '{ph}'")

            # Check 6: Broken wikilinks (post-mortem)
            wikilinks = re.findall(r"\[\[([^\]]+)\]\]", content)
            for link in wikilinks:
                # Normalize: remove .md if present
                link_normalized = link.replace(".md", "")
                if not _page_exists(link_normalized):
                    issues.append(f"BROKEN LINK: {rel_path} — [[{link}]] points to nonexistent page")

        if issues:
            report = "\n".join(f"  - {i}" for i in issues)
            logger.warning("Validation issues (%d):\n%s", len(issues), report)
        else:
            logger.info("Validation passed: %d page(s) OK.", len(written_pages))

        await ctx.send_message(json.dumps({
            "issues": issues,
            "passed": len(issues) == 0,
            "written_pages": written_pages,
            "extraction": extraction,
        }))
