# Backlog — Gap Analysis vs Karpathy Spec

## Summary

- **Reference**: [Karpathy LLM Wiki Gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- **Date**: 2026-05-03
- **Completed**: 8 / 28
- **Pending**: 20 / 28

## Backlog

| GAP | Priority | Name | Description | LLM? | Status |
|-----|----------|------|-------------|------|--------|
| GAP-001 | P0 | Log format heading | Parseable format `## [date] op \| title` + Pages touched in `index_updater.py` | No | Done |
| GAP-002 | P0 | Log query operations | Append to log.md after every query | No | Done |
| GAP-003 | P0 | Log lint operations | Append to log.md after every lint pass | No | Done |
| GAP-004 | P0 | Wiki reset workflow | Deterministic workflow to clear and reset the wiki | No | Done |
| GAP-005 | P0 | Index one-liner summaries | Each index entry has a one-line summary | No | Done |
| GAP-006 | P0 | Read wiki page path normalization | `read_wiki_page` accepts partial paths (`entities/tool`, `tool.md`, etc.) | No | Done |
| GAP-007 | P0 | Query agent instructions rewrite | Explicit workflow: index → search → read → follow wikilinks → answer | No | Done |
| GAP-008 | P0 | English-only content rules | Language rule added to schema + all agents | No | Done |
| GAP-009 | P0 | Re-ingest Italian pages | Existing Italian pages must be re-ingested in English | Yes | Pending |
| GAP-010 | P1 | Lint: detect new contradictions | Linter compares claims across pages, not just existing contradiction blocks | Yes | Pending |
| GAP-011 | P1 | Lint: detect stale claims | Flag claims from older sources when newer sources exist | Yes | Pending |
| GAP-012 | P1 | Lint: suggest missing pages | Entity/concept mentioned in text without its own page → flag it | Yes | Pending |
| GAP-013 | P1 | Lint: suggest new questions | Based on gaps found, suggest research questions or sources to add | Yes | Pending |
| GAP-014 | P1 | Propagate pages_touched | Writer executor passes list of touched pages in payload for the log | No | Pending |
| GAP-015 | P2 | Human-in-the-loop ingest | After extraction, show key takeaways and ask for confirmation before writing | No | Pending |
| GAP-016 | P2 | Git auto-commit | Auto-commit after ingest/lint with parseable commit message | No | Pending |
| GAP-017 | P2 | Index metadata | Add date and source count to index entries (`— summary (3 sources, 2026-05-03)`) | No | Pending |
| GAP-018 | P2 | Overview page type | Add "overview" page type to schema for area-level synthesis pages | Yes | Pending |
| GAP-019 | P2 | Comparison page type | Add "comparison" page type for structured entity/concept comparisons | Yes | Pending |
| GAP-020 | P3 | Image handling in ingest | Support images in raw sources: local download, multimodal LLM description | Yes | Pending |
| GAP-021 | P3 | Query: comparison table output | For comparison questions, generate structured markdown tables | Yes | Pending |
| GAP-022 | P3 | Search upgrade (BM25/vector) | Replace grep with hybrid search for wikis with 100+ pages | No | Pending |
| GAP-023 | P3 | Web search in lint | Give the linter a web search tool to suggest sources for gaps | Yes | Pending |
| GAP-024 | P3 | Obsidian graph compatibility | Verify wikilinks work in Obsidian graph view without modifications | No | Pending |
| GAP-025 | P4 | Marp slide deck output | Query agent can generate Marp slide decks | No | Pending |
| GAP-026 | P4 | Dataview frontmatter enrichment | Add tags, source_count, and YAML metadata for Dataview queries | No | Pending |
| GAP-027 | P1 | Lint remediation: broken links | Auto-fix broken wikilinks by creating stub pages or removing invalid links from the source page | No | Pending |
| GAP-028 | P1 | Lint remediation: semantic suggestions | When a lint_approved suggestion is ingested, the writer should apply the fix (add cross-ref, merge contradictions, create missing page) instead of just documenting it | Yes | Pending |
