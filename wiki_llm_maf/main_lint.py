"""Entry point: run the wiki linter."""

import asyncio
import os
import re
from datetime import datetime

from dotenv import load_dotenv

from afw_core.logging_config import setup_logging
from afw_core.llms.openai import create_client
from afw_core.agents import wiki_linter
from afw_core.tools.wiki_read import read_wiki_page, read_index
from afw_core.tools.wiki_list import list_wiki_pages
from afw_core.tools.wiki_search import search_wiki
from afw_core.tools.log_append import append_log

_DEFAULT_BASE = os.path.dirname(os.path.abspath(__file__))


def _base_dir() -> str:
    return os.environ.get("WIKI_ROOT_DIR", _DEFAULT_BASE)


def _deterministic_lint() -> list[str]:
    """Run deterministic checks that don't require an LLM."""
    wiki_dir = os.path.join(_base_dir(), "wiki")
    issues: list[str] = []

    # Collect all existing page paths (e.g. "entities/agent", "concepts/workflows")
    existing_pages: set[str] = set()
    categories = ("sources", "entities", "concepts", "synthesis")
    for cat in categories:
        cat_dir = os.path.join(wiki_dir, cat)
        if not os.path.isdir(cat_dir):
            continue
        for fname in os.listdir(cat_dir):
            if fname.endswith(".md"):
                existing_pages.add(f"{cat}/{fname.replace('.md', '')}")

    # Scan all pages for wikilinks and check them
    for cat in categories:
        cat_dir = os.path.join(wiki_dir, cat)
        if not os.path.isdir(cat_dir):
            continue
        for fname in sorted(os.listdir(cat_dir)):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(cat_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()

            rel_path = f"wiki/{cat}/{fname}"
            wikilinks = re.findall(r"\[\[([^\]]+)\]\]", content)
            for link in wikilinks:
                link_normalized = link.replace(".md", "")
                if link_normalized not in existing_pages:
                    issues.append(f"BROKEN LINK: {rel_path} — [[{link}]] → page not found")

    # Check for orphan pages (not in index)
    index_path = os.path.join(wiki_dir, "index.md")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            index_content = f.read()
        index_links = set(re.findall(r"\[\[([^\]]+)\]\]", index_content))
        for page in existing_pages:
            if page not in index_links:
                issues.append(f"ORPHAN: wiki/{page}.md — not referenced in index")

    # Check for missing frontmatter
    for cat in categories:
        cat_dir = os.path.join(wiki_dir, cat)
        if not os.path.isdir(cat_dir):
            continue
        for fname in sorted(os.listdir(cat_dir)):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(cat_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            if not content.startswith("---"):
                issues.append(f"NO FRONTMATTER: wiki/{cat}/{fname}")

    return issues


def _count_issues(report: str) -> int:
    """Count issue lines in the lint report (heuristic: lines starting with - or numbered)."""
    return len(re.findall(r"^[\-\d]", report, re.MULTILINE))


async def main():
    load_dotenv()
    setup_logging()
    api_key = os.environ["OPENAI_API_KEY"]
    model = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o")

    print("=== WIKI LINT ===\n")

    # Phase 1: deterministic checks (no LLM, instant)
    print("— Deterministic checks —")
    det_issues = _deterministic_lint()
    if det_issues:
        for issue in det_issues:
            print(f"  - {issue}")
        print(f"\n  → {len(det_issues)} deterministic issue(s) found.\n")

        # Save deterministic issues to lint_pending/
        base = _base_dir()
        lint_dir = os.path.join(base, "lint_pending")
        os.makedirs(lint_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        for i, issue in enumerate(det_issues, 1):
            det_suggestion = _parse_deterministic_issue(issue)
            slug = re.sub(r"[^a-z0-9]+", "-", det_suggestion["description"][:60].lower()).strip("-")
            fname = f"lint-{ts}-det-{i:02d}-{slug}.md"
            content = _format_suggestion(det_suggestion)
            fpath = os.path.join(lint_dir, fname)
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(content)
        print(f"  Saved {len(det_issues)} deterministic issue(s) to lint_pending/\n")
    else:
        print("  All deterministic checks passed.\n")

    # Phase 2: LLM-based semantic analysis
    print("— Semantic analysis (LLM) —")
    client, options = create_client(api_key=api_key, model=model)

    tools = [read_index, read_wiki_page, list_wiki_pages, search_wiki, append_log]
    agent = wiki_linter.create_agent(client, options, tools)

    result = await agent.run("Perform a full semantic lint of the wiki.")
    raw_output = result.final_output if hasattr(result, "final_output") else str(result)

    # Parse LLM suggestions
    import json
    suggestions = []
    try:
        text = raw_output.strip()
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:])
        if text.endswith("```"):
            text = text[: text.rfind("```")]
        suggestions = json.loads(text.strip())
    except (json.JSONDecodeError, ValueError):
        print(f"  (Could not parse LLM output as JSON, raw output below)")
        print(raw_output)

    if suggestions:
        print(f"\n  → {len(suggestions)} semantic suggestion(s):\n")
        for s in suggestions:
            print(f"  [{s.get('severity', '?').upper()}] {s.get('type', '?')}: {s.get('description', '')}")

        # Save each suggestion to lint_pending/
        base = _base_dir()
        lint_dir = os.path.join(base, "lint_pending")
        os.makedirs(lint_dir, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        for i, s in enumerate(suggestions, 1):
            slug = re.sub(r"[^a-z0-9]+", "-", s.get("description", "suggestion")[:60].lower()).strip("-")
            fname = f"lint-{ts}-{i:02d}-{slug}.md"
            content = _format_suggestion(s)
            fpath = os.path.join(lint_dir, fname)
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(content)

        print(f"\n  Saved to lint_pending/ — review and copy to lint_approved/ to action them.")
    else:
        print("  No semantic issues found.")

    # Append to log.md
    log_path = os.path.join(_base_dir(), "wiki", "log.md")
    ts_log = datetime.now().strftime("%Y-%m-%d %H:%M")
    total_issues = len(det_issues) + len(suggestions)
    log_entry = f"\n## [{ts_log}] lint | {len(det_issues)} deterministic + {len(suggestions)} semantic issues\n"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(log_entry)
    print(f"\n[logged to wiki/log.md]")


def _parse_deterministic_issue(issue: str) -> dict:
    """Convert a deterministic issue string into a suggestion dict."""
    if issue.startswith("BROKEN LINK:"):
        # e.g. "BROKEN LINK: wiki/sources/foo.md — [[concepts/bar]] → page not found"
        parts = issue.split(" — ", 1)
        page = parts[0].replace("BROKEN LINK: ", "").strip()
        link_desc = parts[1] if len(parts) > 1 else ""
        return {
            "type": "broken_link",
            "severity": "high",
            "description": f"Broken wikilink in {page}: {link_desc}",
            "pages_involved": [page],
            "suggested_action": f"Create the missing page or remove/fix the link in {page}.",
        }
    elif issue.startswith("ORPHAN:"):
        page = issue.replace("ORPHAN: ", "").split(" — ")[0].strip()
        return {
            "type": "orphan_page",
            "severity": "medium",
            "description": f"Orphan page not in index: {page}",
            "pages_involved": [page],
            "suggested_action": f"Add {page} to index.md or link from another page.",
        }
    elif issue.startswith("NO FRONTMATTER:"):
        page = issue.replace("NO FRONTMATTER: ", "").strip()
        return {
            "type": "missing_frontmatter",
            "severity": "medium",
            "description": f"Missing frontmatter in {page}",
            "pages_involved": [page],
            "suggested_action": f"Add YAML frontmatter (title, tags) to {page}.",
        }
    else:
        return {
            "type": "unknown",
            "severity": "low",
            "description": issue,
            "pages_involved": [],
            "suggested_action": "Review manually.",
        }


def _format_suggestion(s: dict) -> str:
    """Format a single lint suggestion as a markdown file for lint_pending/."""
    stype = s.get("type", "unknown")
    severity = s.get("severity", "medium")
    description = s.get("description", "")
    pages = s.get("pages_involved", [])
    action = s.get("suggested_action", "")

    lines = [
        f"# Lint Suggestion: {description}",
        "",
        f"**Type:** {stype}",
        f"**Severity:** {severity}",
        f"**Pages involved:** {', '.join(pages) if pages else 'N/A'}",
        "",
        "## Description",
        "",
        description,
        "",
        "## Suggested Action",
        "",
        action,
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    asyncio.run(main())
