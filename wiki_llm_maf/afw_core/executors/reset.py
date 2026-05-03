"""Executor: resets the wiki by clearing all content directories."""

from __future__ import annotations

import json
import os
import shutil

from agent_framework import Executor, handler, WorkflowContext

_DEFAULT_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _base_dir() -> str:
    return os.environ.get("WIKI_ROOT_DIR", _DEFAULT_BASE)


_DIRS_TO_CLEAR = [
    os.path.join("wiki", "sources"),
    os.path.join("wiki", "entities"),
    os.path.join("wiki", "concepts"),
    os.path.join("wiki", "synthesis"),
    "raw",
    "questions_approved",
    "questions_pending",
]


class ResetExecutor(Executor):
    """Deletes all files in wiki content dirs, raw, and questions. Keeps directory structure."""

    def __init__(self):
        super().__init__(id="reset")

    @handler
    async def handle(self, input: str, ctx: WorkflowContext[str]) -> None:
        base = _base_dir()
        total = 0
        cleared: dict[str, int] = {}

        for rel in _DIRS_TO_CLEAR:
            dirpath = os.path.join(base, rel)
            if not os.path.isdir(dirpath):
                os.makedirs(dirpath, exist_ok=True)
                cleared[rel] = 0
                continue

            count = 0
            for entry in os.listdir(dirpath):
                entry_path = os.path.join(dirpath, entry)
                if os.path.isdir(entry_path):
                    shutil.rmtree(entry_path)
                else:
                    os.remove(entry_path)
                count += 1
            total += count
            cleared[rel] = count
            print(f"  {rel}/ — {count} item(s) removed")

        # Reset index.md
        index_path = os.path.join(base, "wiki", "index.md")
        with open(index_path, "w", encoding="utf-8") as f:
            f.write("---\ntitle: Wiki Index\ntype: index\n---\n\n# Wiki Index\n")
        print("  wiki/index.md — reset")

        # Clear log.md
        log_path = os.path.join(base, "wiki", "log.md")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("")
        print("  wiki/log.md — cleared")

        await ctx.send_message(json.dumps({"reset": True, "items_removed": total, "dirs": cleared}))
