"""Entry point: ADV_ query pipeline — plan → walk → answer.

Architecture (3 steps, 2 LLM calls):
  1. PLANNER (LLM)  — selects seed pages from the wiki index
  2. WALKER  (Python) — BFS on ## Connections, respects page budget
  3. ANSWERER (LLM)  — produces final answer from read pages

This is an alternative to the tool-calling approach in main_query.py.
To revert to the previous approach:  python main_query.py
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime

from dotenv import load_dotenv

from afw_core.logging_config import setup_logging
from afw_core.console import console
from afw_core.llms.openai import create_client
from afw_core.agents import adv_query_planner, adv_answerer
from afw_core.models.adv_query import ADV_QueryPlan
from afw_core.tools.adv_graph_walker import walk_graph

logger = logging.getLogger(__name__)

_DEFAULT_BASE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_PAGE_VISIT_LIMIT = 5
_DEFAULT_MAX_SEEDS = 3
_DEFAULT_DETAIL_LEVEL = "standard"

_PREFIXES = {
    "!b ": "brief",
    "!s ": "standard",
    "!f ": "full",
}

_HELP_TEXT = (
    "  Prefixes:  !b = brief  |  !s = standard  |  !f = full/detailed  |  (default = standard)\n"
    "  Commands:  ?  or  !help  = show this help\n"
)


def _parse_detail_prefix(raw_question: str) -> tuple[str, str]:
    """Strip a detail-level prefix from the question.

    Returns (clean_question, detail_level).
    """
    for prefix, level in _PREFIXES.items():
        if raw_question.startswith(prefix):
            return raw_question[len(prefix):].strip(), level
    return raw_question, _DEFAULT_DETAIL_LEVEL


def _base_dir() -> str:
    return os.environ.get("WIKI_ROOT_DIR", _DEFAULT_BASE)


def _page_visit_limit() -> int:
    return int(os.environ.get("PAGE_VISIT_LIMIT", str(_DEFAULT_PAGE_VISIT_LIMIT)))


def _max_seeds() -> int:
    return int(os.environ.get("ADV_MAX_SEEDS", str(_DEFAULT_MAX_SEEDS)))


def _load_index() -> str:
    """Load and reorder the wiki index (entities/concepts first)."""
    index_path = os.path.join(_base_dir(), "wiki", "index.md")
    with open(index_path, "r", encoding="utf-8") as f:
        raw = f.read()

    lines = raw.split("\n")
    sections: dict[str, list[str]] = {}
    current = ""
    for line in lines:
        if line.startswith("## "):
            current = line
            sections[current] = []
        elif current:
            sections[current].append(line)

    reordered: list[str] = []
    for heading in ["## Entities", "## Concepts", "## Sources", "## Synthesis"]:
        if heading in sections:
            reordered.append(heading)
            reordered.extend(sections[heading])

    return "\n".join(reordered) if reordered else raw


def _build_index_path_set(index_content: str) -> set[str]:
    """Extract all page paths from the index for validation."""
    paths: set[str] = set()
    for line in index_content.split("\n"):
        m = re.search(r"\[\[([^\]]+)\]\]", line)
        if m:
            paths.add(m.group(1))
    return paths


def _save_answer(question: str, answer: str) -> str:
    """Save the answer to questions_pending/ and return the file path."""
    pending_dir = os.path.join(_base_dir(), "questions_pending")
    os.makedirs(pending_dir, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", question.lower()).strip("-")[:60]
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    fname = f"{slug}_{timestamp}.md"
    fpath = os.path.join(pending_dir, fname)

    content = (
        f"---\n"
        f'title: "{question}"\n'
        f'query: "{question}"\n'
        f'date: "{datetime.now().strftime("%Y-%m-%d")}"\n'
        f'pipeline: "adv"\n'
        f"---\n\n"
        f"{answer}\n"
    )
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(content)
    return fname


async def main():
    load_dotenv()
    setup_logging()
    api_key = os.environ["OPENAI_API_KEY"]
    model = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o")

    budget = _page_visit_limit()
    max_seeds = _max_seeds()
    wiki_dir = os.path.join(_base_dir(), "wiki")

    client, options = create_client(api_key=api_key, model=model)

    planner = adv_query_planner.create_agent(client, options, max_seeds=max_seeds)

    index_content = _load_index()
    valid_paths = _build_index_path_set(index_content)

    print("Wiki Querier (ADV) ready. Type your question (or 'quit' to exit).")
    print(_HELP_TEXT, end="")
    console.info(f"Budget: {budget} pages | Max seeds: {max_seeds}")
    print()

    while True:
        question = input("Q: ").strip()
        if question.lower() in ("quit", "exit", "q"):
            break
        if not question or question in ("?", "!help"):
            if question:
                print(_HELP_TEXT, end="")
            continue

        question, detail_level = _parse_detail_prefix(question)
        if not question:
            continue
        answerer = adv_answerer.create_agent(client, options, detail_level=detail_level)
        console.detail(f"Detail level: {detail_level}")

        # ── STEP 1: PLAN (LLM) ──────────────────────────────────────
        planner_prompt = (
            f"<wiki_index>\n{index_content}\n</wiki_index>\n\n"
            f"<question>{question}</question>\n\n"
            f"Select the most relevant pages (max {max_seeds}) from the index."
        )

        logger.debug("Step 1/3: Planning (LLM)...")
        console.step("Step 1/3 — Planning (LLM)...")
        try:
            plan_result = await planner.run(
                planner_prompt,
                options={"response_format": ADV_QueryPlan},
            )
            plan: ADV_QueryPlan = plan_result.value
        except Exception:
            # Fallback: parse from text
            logger.warning("Structured output failed, parsing from text")
            plan_result = await planner.run(planner_prompt)
            text = plan_result.text.strip()
            if text.startswith("```"):
                text = "\n".join(text.split("\n")[1:])
            if text.endswith("```"):
                text = text[:text.rfind("```")]
            plan = ADV_QueryPlan.model_validate_json(text.strip())

        # Normalize paths: strip [[brackets]] if the LLM copied them from the index
        for p in plan.pages:
            p.path = p.path.strip("[]").strip()

        # Validate seeds against index
        valid_seeds = [p.path for p in plan.pages if p.path in valid_paths]
        invalid_seeds = [p.path for p in plan.pages if p.path not in valid_paths]
        if invalid_seeds:
            logger.warning("Planner returned invalid paths (not in index): %s", invalid_seeds)

        if not valid_seeds:
            print("\nA: The planner could not find relevant pages in the wiki.\n")
            continue

        for i, page in enumerate(plan.pages):
            marker = "✓" if page.path in valid_paths else "✗"
            logger.debug("  Seed %d: [%s] %s — %s", i + 1, marker, page.path, page.reason)
            console.detail(f"Seed {i + 1}: [{marker}] {page.path} — {page.reason}")

        console.info(f"{len(valid_seeds)} seed(s) selected")

        # ── STEP 2: WALK (deterministic) ─────────────────────────────
        logger.debug("Step 2/3: Graph walk (budget=%d, seeds=%d)...", budget, len(valid_seeds))
        console.step("Step 2/3 — Graph walk...")
        pages_read = walk_graph(valid_seeds, budget, wiki_dir)

        logger.debug("Walk complete: %d pages read", len(pages_read))
        console.info(f"{len(pages_read)} page(s) read")

        # ── STEP 3: ANSWER (iterative LLM) ──────────────────────────
        logger.debug("Step 3/3: Answering (iterative, %d pages)...", len(pages_read))
        console.step(f"Step 3/3 — Answering ({len(pages_read)} pages)...")
        draft = ""
        for i, (path, content) in enumerate(pages_read.items(), 1):
            if draft:
                draft_section = draft
            else:
                draft_section = "(empty — start a new answer)"
            answerer_prompt = (
                f"<question>{question}</question>\n\n"
                f"<new_page path=\"{path}\" index=\"{i}/{len(pages_read)}\">\n"
                f"{content}\n"
                f"</new_page>\n\n"
                f"<previous_draft>\n{draft_section}\n</previous_draft>"
            )
            answer_result = await answerer.run(answerer_prompt)
            draft = answer_result.text
            logger.debug("  Integrated page %d/%d: %s", i, len(pages_read), path)
            console.detail(f"Integrated page {i}/{len(pages_read)}: {path}")
        answer = draft.strip()

        # Detect empty or poisoned drafts
        if not answer or answer.lower().startswith("the wiki") or answer.lower().startswith("la wiki"):
            print("\nA: The wiki does not contain enough information to answer this question.\n")
            continue

        print(f"\nA: {answer}\n")

        # Save
        fname = _save_answer(question, answer)
        print(f"   [saved to questions_pending/{fname}]")

        # Log
        log_path = os.path.join(_base_dir(), "wiki", "log.md")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        seeds_str = ", ".join(valid_seeds)
        pages_str = ", ".join(pages_read.keys())
        log_entry = (
            f"\n## [{ts}] adv_query | {question}\n"
            f"Seeds: {seeds_str}\n"
            f"Pages read: {pages_str}\n"
            f"Answer saved: questions_pending/{fname}\n"
        )
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(log_entry)
        print(f"   [logged to wiki/log.md]\n")


if __name__ == "__main__":
    asyncio.run(main())
