"""Executor: scans raw/, questions_approved/, and lint_approved/ for new sources to ingest."""

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


class ScannerExecutor(Executor):
    """Checks raw/, questions_approved/, lint_approved/ for files not yet processed."""

    def __init__(self):
        super().__init__(id="scanner")

    @handler
    async def handle(self, input: str, ctx: WorkflowContext[str]) -> None:
        base = _base_dir()
        raw_dir = os.path.join(base, "raw")
        approved_dir = os.path.join(base, "questions_approved")
        lint_dir = os.path.join(base, "lint_approved")
        log_path = os.path.join(base, "wiki", "log.md")

        # Read log to find already-processed files
        processed: set[str] = set()
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as f:
                log_content = f.read()
            # Match "Source: filename.md" lines in log entries
            processed = set(re.findall(r"^Source:\s*(.+\.md)\s*$", log_content, re.MULTILINE))

        # Scan raw directory
        new_files: list[str] = []
        if os.path.isdir(raw_dir):
            for fname in sorted(os.listdir(raw_dir)):
                if fname.endswith(".md") and fname not in processed:
                    new_files.append(os.path.join(raw_dir, fname))

        # Scan questions_approved directory
        if os.path.isdir(approved_dir):
            for fname in sorted(os.listdir(approved_dir)):
                if fname.endswith(".md") and fname not in processed:
                    new_files.append(os.path.join(approved_dir, fname))

        # Scan lint_approved directory
        if os.path.isdir(lint_dir):
            for fname in sorted(os.listdir(lint_dir)):
                if fname.endswith(".md") and fname not in processed:
                    new_files.append(os.path.join(lint_dir, fname))

        logger.info("Scanner found %d new file(s) to ingest.", len(new_files))
        logger.debug("Files: %s", [os.path.basename(f) for f in new_files])
        await ctx.send_message(json.dumps({"new_files": new_files}))
