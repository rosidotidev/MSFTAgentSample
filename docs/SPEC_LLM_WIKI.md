# LLM Wiki MFA — Technical Specification v2

> This document is the technical specification for the LLM Wiki system.
> Guiding principle: the wiki is an intellectual organism that evolves, not a data store.

---

## 1. Philosophy

The wiki is NOT a database of mechanically extracted cards. It is a **cumulative artifact** that:

- **Integrates** new knowledge in the context of what already exists
- **Evolves** — updates, corrects, supersedes previous information
- **Connects** — each ingest can touch 10-15 existing pages
- **Contradicts** — flags when new sources contradict existing claims
- **Compounds** — queries produce syntheses that flow back into the wiki

The LLM is not a parser. It is a **knowledge integrator** with judgment.

---

## 2. Three-Layer Architecture

```
raw/                    ← Immutable sources. The LLM reads but NEVER modifies.
wiki/                   ← LLM-owned artifact. Markdown + frontmatter.
schema.md               ← Page format reference (frontmatter, structure, wikilink conventions).
questions_pending/      ← Query answers land here (auto-generated).
questions_approved/     ← User moves worthy answers here for integration.
```

### Data Root (`WIKI_ROOT_DIR`)

The data directories (`wiki/`, `raw/`, `questions_pending/`, `questions_approved/`) are located under a configurable root, defined by the `WIKI_ROOT_DIR` environment variable in `.env`. If not set, it defaults to the project directory (`wiki_llm_maf/`).

This allows the user to place the wiki data anywhere on the filesystem — separate from the code.

```env
# .env
WIKI_ROOT_DIR=c:\Users\me\my-wiki-data\
```

All tools and executors resolve paths at runtime via `os.environ.get("WIKI_ROOT_DIR", <default>)`.

### Logging (`WIKI_LOG_LEVEL`)

All three workflows use Python's standard `logging` module, configured centrally by `afw_core/logging_config.py`. The log level is controlled via the `WIKI_LOG_LEVEL` environment variable:

| Level | Output |
|-------|--------|
| `ERROR` | Only failures |
| `WARNING` | Failures + validation issues |
| `INFO` | Executor start/end, summaries, timing (default) |
| `DEBUG` | Full input/output payloads, plan JSON, entity counts |

```env
# .env
WIKI_LOG_LEVEL=INFO
```

Third-party loggers (`httpx`, `openai`, `httpcore`) are suppressed to `WARNING` regardless of the configured level. Each executor uses `logging.getLogger(__name__)` so log lines show the originating module.

### Console Verbosity (`WIKI_VERBOSITY`)

Controls the user-facing console output level, independent of Python logging. The console provides structured, colour-coded output with pipeline phases, progress, and results.

| Level | Value | Output |
|-------|-------|--------|
| `SILENT` | `0` | Errors + final result only. Ideal for automated pipelines. |
| `NORMAL` | `1` | Pipeline phases with progress, key results, timing (default). |
| `VERBOSE` | `2` | All internal details: slug mapping, merge decisions, chunk processing. |

```env
# .env
WIKI_VERBOSITY=1
```

The console system (`afw_core/console.py`) uses a singleton `console` instance with these methods:

| Method | Verbosity | Purpose |
|--------|-----------|---------|
| `banner(title)` | NORMAL+ | Top-level pipeline banner with box drawing |
| `step(msg)` | NORMAL+ | Major pipeline phase (⏵ marker) |
| `info(msg)` | NORMAL+ | Secondary info inside a step |
| `detail(msg)` | VERBOSE only | Internal detail (dim text) |
| `success(msg)` | ALL | Green ✔ — final result |
| `warning(msg)` | ALL | Yellow ⚠ — warnings |
| `error(msg)` | ALL | Red ✗ — errors |
| `result(msg)` | ALL | Plain text block for answers |

Python `logging` remains in all executors for `WARNING`/`ERROR`/`DEBUG` internals. Console calls are added alongside `logger.info()` for user-facing messages — they do not replace logging.

`WIKI_MONITOR` remains a separate concern (JSON diagnostic dumps ≠ console verbosity).

### Page Visit Limit (`PAGE_VISIT_LIMIT`)

Controls the maximum number of wiki pages the WikiQuerierAgent can read per question. This limits navigation depth to prevent unbounded exploration on vague queries while allowing the agent to follow `## Connections` links for richer answers.

```env
# .env
PAGE_VISIT_LIMIT=5
```

The limit is enforced at two levels:
1. **Prompt-level (soft)**: the agent's instructions state the budget, encouraging it to stop when enough context is gathered.
2. **Tool-level (hard)**: `main_query.py` wraps `read_wiki_page` with a counter that returns a "budget exceeded" message after the N-th call, regardless of what the LLM decides.

The counter resets on every new question. If not set, defaults to `5`.

### Minimum Page Ratio (`MIN_PAGE_RATIO`)

Sets a **floor** on how many pages the WikiQuerierAgent must read before answering. Expressed as a fraction of `PAGE_VISIT_LIMIT`:

```env
# .env
MIN_PAGE_RATIO=0.6
```

With `PAGE_VISIT_LIMIT=5` and `MIN_PAGE_RATIO=0.6`, the agent must read at least `ceil(0.6 × 5) = 3` pages before it can answer. This prevents the agent from giving shallow answers after reading only 1-2 pages on broad questions.

The minimum is enforced at prompt level (soft) — the agent's instructions state *"you MUST read at least N pages before answering"*. The floor is always at least 1, even with very low ratios.

If not set, defaults to `0.6` (60%).

> **Note**: `MIN_PAGE_RATIO` is only used by the legacy query pipeline (`main_query.py`). The ADV pipeline uses `ADV_MAX_SEEDS` instead.

### ADV Max Seeds (`ADV_MAX_SEEDS`)

Controls the maximum number of seed pages the ADV Planner can select from the index. The Graph Walker then expands from these seeds via BFS on `## Connections`, up to the `PAGE_VISIT_LIMIT` budget.

```env
# .env
ADV_MAX_SEEDS=3
```

If not set, defaults to `3`.

### Role of `schema.md`

`schema.md` is a **format reference**, not a program. In a conversational setup (e.g. Claude Code), a CLAUDE.md file acts as the entire orchestration layer — telling the LLM what to do, when, and how. In our agentic solution, orchestration lives in Python code (the workflow), and agent behavior lives in each agent's `INSTRUCTIONS`. 

`schema.md` has one job: define what wiki pages look like. It is **sectioned** with HTML markers (`<!-- SECTION:name -->`) so that each agent can load only the sections it needs:

| Section | Content | Used by |
|---------|---------|---------|
| `core` | Language rule, directory layout, frontmatter, wikilink format | (available for reference) |
| `templates` | Page body templates (source, entity, concept, synthesis) | (available for reference) |
| `index-log` | Index and log format conventions | (available for reference) |

The shared helper `afw_core/agents/_schema.py` provides two functions:
- `load_schema(*sections)` — loads specific sections by marker name
- `load_full_schema()` — loads all sections (core + templates + index-log)

Agent-specific injection:
- **SourceReaderAgent** → no schema — produces structured JSON, not wiki pages
- **WikiQuerierAgent** → no schema — reads existing pages, doesn't create them
- **WikiLinterAgent** → no schema — analyzes existing pages for issues

Note: the Integrator and Writer executors do NOT use the schema — the Integrator works with slugs/paths, and the Writer uses hardcoded templates in Python code.

`schema.md` does NOT contain workflow logic, agent behavior rules, or orchestration instructions.

### wiki/ structure
```
wiki/
  index.md          ← Navigable catalog (LLM reads this first)
  log.md            ← Append-only timeline of operations
  sources/          ← One page per ingested source
  entities/         ← Pages for named entities
  concepts/         ← Pages for abstract concepts
  synthesis/        ← Pages generated from approved query answers
```

### log.md format

The log is append-only. Each operation appends a heading with a parseable format:

```markdown
## [2026-05-03 14:28] ingest | Microsoft Agent Framework Agents How-To
Source: mfa_agents_howto.md
Pages touched: sources/mfa-agents-howto, entities/agent-framework, concepts/tools

## [2026-05-03 15:10] query | How do tools work in the agent framework?
Sources used: concepts/tools, entities/agent-framework

## [2026-05-03 16:00] lint | 3 issues found
```

Format: `## [YYYY-MM-DD HH:MM] operation | title`. Operations: `ingest`, `query`, `lint`, `reset`.

### index.md format

The index is rebuilt **deterministically** by the IndexUpdater (no LLM) after each source cycle. It is the primary navigation tool for all agents — the Integrator reads it to discover existing pages, the Querier reads it to plan which pages to fetch.

Each entry is a wikilink followed by a one-line summary extracted from the page (first sentence after the first `##` heading):

```markdown
---
title: Wiki Index
type: index
---

# Wiki Index

## Sources
- [[sources/mfa-agents-howto]] — Explains how to define agents with instructions, tools, and LLM clients.
- [[sources/mfa-workflow-howto]] — Covers workflow construction using WorkflowBuilder and executors.

## Entities
- [[entities/agent-framework]] — A Python package for building LLM-powered agents with tools.

## Concepts
- [[concepts/workflow]] — A structured sequence of steps orchestrated by a WorkflowBuilder.
- [[concepts/tools]] — Functions exposed to agents via the @tool decorator.

## Synthesis
- [[synthesis/agent-vs-executor]] — Comparison of Agent and Executor roles in the framework.
```

The one-liner gives the Integrator enough context to decide relevance without reading every page. If a page has no extractable sentence, the entry falls back to the page title.

### Project Directory Structure

```
wiki_llm_mfa/                       ← Project root (code)
  main_ingest.py                    ← Entry point: ingest new sources
  main_query.py                     ← Entry point: legacy query (deprecated)
  main_query_adv.py                 ← Entry point: ADV query pipeline (recommended)
  main_lint.py                      ← Entry point: wiki health check
  main_reset.py                     ← Entry point: clear and rebuild wiki
  schema.md                         ← Page format reference (sectioned)
  pytest.ini                        ← Test configuration
  .env.example                      ← Environment variable template
  afw_core/
    logging_config.py               ← Centralized logging setup
    agents/                         ← Agent definitions (instructions + factory)
      _schema.py                    ← Shared helper: loads schema sections by marker
      source_reader.py              ← SourceReader agent (LLM extraction)
      adv_query_planner.py          ← ADV: selects seed pages via structured output
      adv_answerer.py               ← ADV: iterative answerer (one page per call)
      wiki_querier.py               ← Legacy: agentic Q&A loop (deprecated)
      wiki_linter.py                ← WikiLinter agent (semantic lint)
    executors/                      ← Workflow step executors
      scanner.py                    ← Finds new files in raw/ + questions_approved/
      dispatcher.py                 ← Per-source loop controller (holds file queue)
      source_reader.py              ← Chunked extraction with parallel LLM calls
      splitter.py                   ← Document splitting (heading-based + LLM fallback)
      integrator.py                 ← Dedup + deterministic integration plan
      writer.py                     ← Deterministic page writer (no LLM)
      write_validator.py            ← Post-write validation (no LLM)
      index_updater.py              ← Rebuilds index.md + appends log entry
      reset.py                      ← Clears wiki for full rebuild
    tools/                          ← Tools exposed to agents
      wiki_read.py
      wiki_write.py
      wiki_search.py
      wiki_list.py
      log_append.py
      adv_graph_walker.py           ← ADV: deterministic BFS on ## Connections
    models/                         ← Pydantic data models
      extraction.py                 ← SourceExtraction model
      adv_query.py                  ← ADV: ADV_QueryPlan, ADV_PageRequest
    workflows/                      ← Workflow definitions
      ingest.py                     ← Per-source loop workflow
      reset.py                      ← Reset workflow
  tests/                            ← Test suite
    conftest.py                     ← Shared fixtures (wiki_root, e2e_wiki_root)
    test_scanner.py                 ← Unit: Scanner idempotency
    test_index_updater.py           ← Unit: IndexUpdater deterministic rebuild
    test_write_validator.py         ← Unit: WriteValidator checks
    test_writer.py                  ← Unit: Writer template output
    test_deterministic_lint.py      ← Unit: broken links, orphans, frontmatter
    test_source_reader_utils.py     ← Unit: slug matching, merge, dedup, consolidation
    test_e2e_ingest.py              ← E2E: full ingest cycle (mocked LLM)
    test_e2e_lint.py                ← E2E: lint pipeline
    test_e2e_query.py               ← E2E: query pipeline

<WIKI_ROOT_DIR>/                    ← Data root (configurable via .env)
  raw/                              ← Immutable source documents
  wiki/                             ← LLM-generated wiki pages
    index.md
    log.md
    sources/
    entities/
    concepts/
    synthesis/
  questions_pending/                ← Query answers (auto-generated)
  questions_approved/               ← User-promoted answers for integration
  lint_pending/                     ← Lint suggestions (auto-generated)
  lint_approved/                    ← User-approved lint fixes for integration
```

---

## 3. Operations

### 3.1 INGEST

**Input**: a file in `raw/` (markdown, txt, converted pdf)

**Idempotency mechanism**: the Scanner checks `log.md` for previously ingested filenames (extracted via regex). A file that already appears in the log is skipped. This makes re-running ingest safe — only new files are processed.

**Process** (3 phases, not an ETL pipeline):

#### Phase 1 — Comprehension (SourceReader)

**Document Splitting (adaptive)**

Before extraction, the source document is split into chunks to ensure each LLM call receives a manageable amount of content:

1. **Heading-based split**: if the document has ≥ 2 `##` headings, it is split deterministically at heading boundaries.
2. **Adaptive target**: the number of chunks is computed from the total document size: `target = ceil(total_chars / MAX_CHUNK_CHARS)`, capped at `HARD_CAP_CHUNKS`. This avoids fixed limits — small documents stay as 1 chunk, large ones scale up.
3. **Merge pass**: if the initial heading-split produces more sections than the target, adjacent sections are merged (smallest first) until the target is reached.
4. **LLM fallback**: if the document has no headings and exceeds 60 lines, a lightweight LLM call identifies semantic split points.

| Constant | Value | Meaning |
|----------|-------|---------|
| `MAX_CHUNK_CHARS` | 3000 | Target max chars per chunk |
| `HARD_CAP_CHUNKS` | 30 | Absolute max chunks (limits LLM calls) |
| `MIN_CHUNK_LINES` | 5 | Sections shorter than this are merged into the previous |

Each chunk is then extracted independently (in parallel) by the SourceReaderAgent:

The LLM reads the source and produces a structured analysis:
- Summary
- Key takeaways
- Entities mentioned (with context)
- Concepts covered (with context)
- Main claims (with source spans)

This is "what's in the source". Output: structured JSON.

#### Phase 2 — Integration (IntegratorExecutor)
The Integrator is a **hybrid executor**: one lightweight LLM call for semantic slug mapping, then fully deterministic plan construction. It does NOT use an agentic loop.

**Process:**
1. It receives the Phase 1 extraction
2. It scans existing wiki pages on disk (file system walk)
3. **Deterministic pre-filter**: normalizes slugs (camelCase → kebab-case, plural/singular) and matches exact variants without an LLM call
4. **Single LLM call**: for remaining unmatched slugs, a lightweight `SlugMapper` agent maps each new entity/concept slug to the most semantically equivalent existing slug, or marks it `"NEW"`
5. **Deterministic routing**: based on the mapping, each entity/concept goes to either `pages_to_create` or `pages_to_update`
6. Source page is always created (or replaced if re-ingesting)

Output: an **integration plan** (JSON dict) with `pages_to_create`, `pages_to_update`, `contradictions`, `new_cross_references`.

**Why not agentic?** The original design used an agentic loop with `read_index()` + `read_wiki_page()` tool calls. In practice, slug-level dedup is sufficient for the integration decision — the expensive page reads are unnecessary. A single LLM call with the list of existing slugs vs new slugs achieves the same quality at ~10x lower cost and latency. At moderate scale (~100 pages), the slug list fits easily in one prompt.

#### Phase 3 — Writing (WriterExecutor)
The Writer is **fully deterministic** — zero LLM calls:
- Builds pages from templates using extraction data
- Creates source pages with frontmatter, summary, takeaways, and claims
- Creates entity/concept pages with content, claims, and connections
- For updates: reads existing page, appends a new "From [[source]]" section, merges the Connections block
- Connections between pages are derived from co-occurring entities/concepts in claims

#### Phase 4 — Validation + Index (deterministic)
- **WriteValidator**: checks frontmatter, wikilink validity, placeholder detection, content presence
- **IndexUpdater**: rebuilds `index.md` from disk (with one-liner summaries extracted from pages), appends to `log.md`

**Key insight**: Phase 2 is where the (minimal) intelligence lives — deciding which pages already exist semantically. Everything else is deterministic template-filling, which is faster, cheaper, and fully reproducible.

---

### 3.2 QUERY

**Input**: a user question

Two query pipelines are available. The **ADV pipeline** (`main_query_adv.py`) is the recommended approach; the **legacy pipeline** (`main_query.py`) is preserved for reference but will be removed in a future version.

#### 3.2.1 ADV Query Pipeline (recommended)

Entry point: `main_query_adv.py`

**Architecture**: 3 deterministic steps, only 2 LLM calls per question (no agentic loop).

```
Step 1: PLANNER  (LLM, structured output)  → selects seed pages from index
Step 2: WALKER   (Python, deterministic)    → BFS on ## Connections
Step 3: ANSWERER (LLM, iterative)           → one call per page, grows draft
```

**Step-by-step**:
1. The **Planner** receives the full wiki index (in `<wiki_index>` XML tags) and the user question (in `<question>` tags). It returns an `ADV_QueryPlan` — an ordered list of seed page paths with reasons, via structured output.
2. Seeds are validated against the index — invalid paths are discarded.
3. The **Graph Walker** (pure Python, no LLM) performs a BFS starting from the seeds. For each page read, it parses `## Connections` and queues linked pages. It stops when the page budget is exhausted.
4. The **Answerer** is called iteratively — once per page, in read order. Each call receives three XML sections: `<question>`, `<new_page>`, and `<previous_draft>`. The answerer integrates relevant content from the new page into the growing draft, preserving everything already written.
5. After all pages are processed, the final draft is returned as the answer.

**Why not agentic?** The tool-calling approach in the legacy pipeline gives the LLM full control over navigation, but gpt-4o-mini consistently exhibited two problems:
- **Shallow answers**: the model stopped reading after 1-2 pages, ignoring the budget.
- **Path invention**: the model fabricated page paths not present in the index.

The ADV pipeline solves both by separating concerns: the Planner selects seeds (constrained to the index), the Walker navigates deterministically (no LLM can skip pages), and the Answerer focuses only on text integration (no navigation decisions).

**Planner rules**: The planner is instructed to prefer specific pages over generic overviews, read descriptions carefully (not just titles), and copy paths exactly from the index. Maximum seeds controlled by `ADV_MAX_SEEDS` (default: 3).

**Answerer rules**: retrieval-only — no training data, no synthesis, no meta-commentary. If a page adds nothing, the draft is returned unchanged. Empty first draft uses a `"(empty — start a new answer)"` placeholder to prevent prompt confusion.

**Page budget**: controlled by the `PAGE_VISIT_LIMIT` environment variable (default: 5). The Walker reads exactly up to this limit. Seeds count toward the budget.

#### 3.2.2 Legacy Query Pipeline (deprecated)

Entry point: `main_query.py`

> **Note**: this pipeline is preserved for reference and will be removed in a future version. Use `main_query_adv.py` instead.

The WikiQuerierAgent is an LLM with tools in an agentic loop. It reads the index, reasons about which pages are relevant, and navigates the wiki sequentially, following `## Connections` links — ONE `read_wiki_page` call per turn.

The agent must read at least `ceil(MIN_PAGE_RATIO × PAGE_VISIT_LIMIT)` pages before answering (default: 3). Page budget is enforced both in the prompt (soft) and via a tool-level counter (hard).

#### Common: Pending Mechanism & Filing Back

**Pending mechanism**: Every answer (from either pipeline) is saved as a markdown file in `questions_pending/<slug>.md` with frontmatter (query, date, pipeline type). The folder is an archive — nothing is ever deleted from it.

**Filing back (human-curated)**: The user reviews answers in `questions_pending/` at their own pace. If an answer has lasting value (synthesis, comparison, new insight), the user moves it to `questions_approved/`. On the next ingest run, the Scanner picks it up and the Integrator processes it into the wiki — creating/updating synthesis, entity, and concept pages as needed.

This keeps the human as the curator: the LLM produces, the human decides what compounds.

**Output forms**: The answer can be a markdown page, a comparison table, a list, or any format appropriate to the question. What matters is that it's grounded in wiki pages with citations.

---

### 3.3 LINT

**Input**: the entire wiki

**Two-phase approach**:

#### Phase 1 — Deterministic (instant, no LLM)
Runs structural checks in code:
- **Broken links**: `[[wikilinks]]` pointing to nonexistent pages
- **Orphan pages**: pages with no inbound links from the index
- **Missing frontmatter**: pages that don't start with `---`

These are infallible — the LLM cannot be trusted with structural checks.

#### Phase 2 — Semantic (LLM agent)
The LLM reads pages and produces semantic findings:
- **Contradictions**: claims in one page that conflict with another
- **Stale claims**: information that newer sources have superseded
- **Missing pages**: entities/concepts discussed substantively but lacking their own page
- **Missing cross-references**: pages that should link to each other but don't
- **Suggested questions**: knowledge gaps that new sources could fill

#### Output → `lint_pending/`
Each semantic suggestion is saved as a markdown file in `lint_pending/` with type, severity, pages involved, and suggested action.

**Human review**: The user reviews `lint_pending/` files. Approved suggestions are moved to `lint_approved/`. On the next ingest run, the Scanner picks them up and processes them into the wiki — just like `questions_approved/`.

This keeps the lint → fix cycle under human control. The LLM diagnoses; the human decides what gets acted on.

---

## 4. Agent Design

### 4.1 SourceReaderAgent + SourceReaderExecutor
- **Agent input**: raw file content (one chunk at a time)
- **Agent output**: `SourceExtraction` Pydantic model (guaranteed valid JSON via framework `response_format`)
- **No tools** — text analysis → structured output only
- **No wiki context** — works only on the source
- **Structured output enforcement** — the executor passes `options={"response_format": SourceExtraction}` to `agent.run()`. The framework guarantees a validated Pydantic instance, eliminating JSON parse failures regardless of LLM provider.

**Executor orchestration** (`executors/source_reader.py`):
- Splits the document into chunks using `splitter.py` (heading-based, with LLM fallback for unstructured docs)
- Extracts each chunk **in parallel** via `asyncio.gather` — one LLM call per chunk
- Merges chunk extractions into a single `SourceExtraction` (dedup entities/concepts across chunks)
- Runs a **consolidation pass** (deterministic) to remove near-duplicate slugs within the same extraction
- Tags the extraction with `_origin` (`raw` or `questions_approved`) and `_source_path`

### 4.2 IntegratorExecutor (the dedup brain)
- **Input**: source extraction (JSON from SourceReader)
- **Output**: integration plan (JSON dict)
- **LLM usage**: single call to a lightweight `SlugMapper` agent — no tools, no agentic loop
- **Two-phase dedup**:
  1. Deterministic pre-filter: normalizes slugs (camelCase/PascalCase/underscores → kebab-case, plural stripping) and matches against existing wiki page slugs
  2. LLM mapping: remaining unmatched slugs are sent (in one prompt) with the full list of existing slugs; the LLM returns a mapping `{new_slug: existing_slug | "NEW"}`
- **Deterministic plan construction**: based on the mapping, builds `pages_to_create` and `pages_to_update` lists
- **Slug renaming**: when a new slug maps to an existing one, the extraction dict is mutated in-place (slug replaced) so downstream Writer finds the right page
- **No wiki page reads** — only needs the set of existing file paths (from `os.walk`)

Integration plan schema:
```json
{
  "pages_to_create": [
    {"path": "wiki/sources/x.md", "page_type": "source", "content_brief": "..."},
    {"path": "wiki/entities/y.md", "page_type": "entity", "content_brief": "..."}
  ],
  "pages_to_update": [
    {"path": "wiki/entities/w.md", "action": "enrich", "detail": "Add info from new source: ..."}
  ],
  "contradictions": [],
  "new_cross_references": []
}
```

### 4.3 WriterExecutor (deterministic, no LLM)
- **Input**: integration plan + extraction
- **Output**: written/updated `.md` files on disk
- **Zero LLM calls** — pure template-based page generation
- **Creates pages** using extraction data: frontmatter, summary, key takeaways, content sections, claims, connections
- **Updates pages** by reading existing content and appending a new `## From [[sources/slug]]` section with the new source's contribution, then merging the `## Connections` block
- **Connections** are derived deterministically from claim co-occurrence: if two entities/concepts appear in the same claim, they get a bidirectional link with the claim text as description
- **Content comes directly from extraction** — no summarization, no generation, full verbatim `content` fields
- **Wikilinks are scoped** to pages that exist on disk or are in the current plan's `pages_to_create`

### 4.6 WriteValidator (deterministic, no LLM)
- **Runs after each page write** — pure Python, zero LLM calls
- **Checks**: code examples from extraction appear in written page, entity/concept names are present, wikilinks are syntactically valid, **all `[[wikilinks]]` point to files that exist on disk or are listed in the current plan**
- **On failure**: logs a warning with what's missing — does NOT auto-retry
- **Purpose**: safety net, not a blocker. The human reviews warnings in the log
- **Broken link detection (post-mortem)**: any `[[path]]` that does not resolve to an existing `.md` file is flagged. This catches cases where the Writer ignored the allowed list or where a planned page failed to write.

### 4.4 ADV Query Agents (recommended pipeline)

Three components, no agentic loop:

#### ADV_QueryPlannerAgent
- **Input**: wiki index + question (in XML tags)
- **Output**: `ADV_QueryPlan` (Pydantic model) — ordered list of seed pages with reasons
- **No tools** — single LLM call with structured output
- **Rules**: prefers specific pages over overviews; reads descriptions, not just titles; copies paths exactly from index; max seeds controlled by `ADV_MAX_SEEDS`

#### Graph Walker (deterministic, no LLM)
- **Input**: seed paths + page budget + wiki directory
- **Output**: `OrderedDict[path, content]` — pages in read order
- **Process**: BFS from seeds, follows `## Connections` links, stops at budget
- **Pure Python** — regex parsing of `[[wikilinks]]` in Connections sections

#### ADV_AnswererAgent
- **Input**: question + one page + previous draft (in XML tags)
- **Output**: updated draft answer
- **No tools** — single LLM call per page, called iteratively
- **Rules**: retrieval-only, preserve previous draft, cite with `[[category/slug]]`, no meta-commentary, no training data

### 4.5 WikiQuerierAgent (legacy, deprecated)
- **Input**: user query
- **Tools**: `read_wiki_page` (budget-limited wrapper), `list_wiki_pages`, `search_wiki`
- **Output**: markdown answer with citations
- **Navigation**: sequential — ONE `read_wiki_page` call per turn, follows `## Connections` links
- **Page budget**: `PAGE_VISIT_LIMIT` env var (default 5), enforced at prompt level (soft) and tool level (hard counter)
- **Minimum reads**: `ceil(MIN_PAGE_RATIO × PAGE_VISIT_LIMIT)` pages must be read before answering (default: 3). Enforced at prompt level (soft)

> **Note**: this agent is preserved for reference. Use the ADV pipeline (`main_query_adv.py`) instead.

### 4.6 WikiLinterAgent
- **Input**: "run lint"
- **Tools**: `read_wiki_page`, `list_wiki_pages`, `write_log`
- **Output**: report with findings and suggestions

---

## 5. Data Model

### SourceExtraction (SourceReader output)
```python
class Claim(BaseModel):
    text: str                    # The assertion
    context: str                 # Context in the source
    entities: list[str]          # Entities involved
    concepts: list[str]          # Concepts involved

class EntityMention(BaseModel):
    name: str
    slug: str
    type: str                    # person|tool|company|project|other
    description: str             # One-liner
    content: str                 # Everything the source says about this entity
    claims: list[str]            # Indices of related claims

class ConceptMention(BaseModel):
    name: str
    slug: str
    definition: str
    content: str                 # Everything the source says about this concept
    claims: list[str]            # Indices of related claims

class SourceExtraction(BaseModel):
    file_name: str
    slug: str
    title: str
    summary: str
    key_takeaways: list[str]
    claims: list[Claim]
    entities: list[EntityMention]
    concepts: list[ConceptMention]
```

### IntegrationPlan (IntegratorExecutor output)

The integration plan is a plain JSON dict (not a Pydantic model) built deterministically by the `IntegratorExecutor`:

```python
# Runtime structure (dict, not a class)
{
    "pages_to_create": [{"path": str, "page_type": str, "content_brief": str}],
    "pages_to_update": [{"path": str, "action": str, "detail": str}],
    "contradictions": [],      # reserved for future use
    "new_cross_references": [] # reserved for future use
}
```

The `pages_to_create` and `pages_to_update` lists are consumed by the `WriterExecutor` to decide which pages to write/update.

---

## 6. Execution Workflow (Ingest)

```
┌─────────────┐
│   Scanner   │  Finds new files in raw/ + questions_approved/ + lint_approved/
└──────┬──────┘
       │ file_list
       ▼
┌─────────────────┐
│   Dispatcher    │◄────────────────────────────────────────────────┐
│  (loop control) │  Pops one file at a time. When empty → end.     │
└──────┬──────────┘                                                 │
       │ file_path                                                  │
       ▼                                                            │
┌──────────────────────────────────────────────────────────────┐    │
│              PER-SOURCE CYCLE (sequential)                    │    │
│                                                              │    │
│  ┌─────────────────────┐                                     │    │
│  │  SourceReader       │  Split → extract chunks (parallel)  │    │
│  │  (chunked, LLM)     │  → merge → consolidate              │    │
│  └──────┬──────────────┘                                     │    │
│         │ extraction                                         │    │
│         ▼                                                    │    │
│  ┌─────────────────────┐                                     │    │
│  │  Integrator         │  Deterministic pre-filter            │    │
│  │  (1 LLM call)       │  + LLM slug mapping → plan          │    │
│  └──────┬──────────────┘                                     │    │
│         │ plan + extraction                                  │    │
│         ▼                                                    │    │
│  ┌─────────────────┐                                         │    │
│  │  Writer          │  Deterministic page creation/update    │    │
│  │  (no LLM)        │  Templates + extraction data           │    │
│  └──────┬──────────┘                                         │    │
│         │                                                    │    │
│         ▼                                                    │    │
│  ┌─────────────────┐                                         │    │
│  │ WriteValidator   │  Deterministic checks (no LLM)         │    │
│  └──────┬──────────┘                                         │    │
│         │                                                    │    │
│         ▼                                                    │    │
│  ┌─────────────────┐                                         │    │
│  │  IndexUpdater    │  Rebuild index.md + append log entry   │    │
│  └──────┬──────────┘                                         │    │
│         │                                                    │    │
└─────────┼────────────────────────────────────────────────────┘    │
          └─────────────────────────────────────────────────────────┘
                              back-edge to Dispatcher
```

**Per-source loop with back-edge.** The workflow uses a `WorkflowBuilder` with a back-edge from `IndexUpdater → Dispatcher`. The Dispatcher holds the file queue in instance state and pops one file per cycle. When the queue is empty, it yields output (ending the workflow). This ensures:
- The Integrator always sees pages written by previous sources (up-to-date index)
- The IndexUpdater rebuilds `index.md` after each source, so the next cycle reads a current catalog
- No risk of duplicate page creation across sources

The Scanner runs once at the start. Everything else loops via the Dispatcher.

---

## 7. Contradiction Handling

When the Integrator detects a contradiction:
1. Documents it in the plan's `contradictions` list
2. The Writer inserts it in the page with a visible block:

```markdown
> ⚠️ **Contradiction** (detected: 2026-05-02)
> - Previous claim: "X supports only 4K context" ([[sources/paper-a]])
> - New claim: "X now supports 128K context" ([[sources/paper-b]])
> - Note: the more recent source may indicate a product update.
```

The human or a subsequent lint pass can resolve the contradiction.

---

## 8. Filing Back (Query → Wiki)

The filing-back mechanism is **human-gated**, not automatic:

1. The WikiQuerierAgent saves every answer to `questions_pending/<slug>.md` with frontmatter:
```yaml
---
title: "<Answer title>"
query: "<the original question>"
date: "YYYY-MM-DD"
sources_used: [<slugs of cited sources>]
---
```
2. The user reviews `questions_pending/` at their own pace
3. To integrate an answer into the wiki, the user moves it to `questions_approved/`
4. On the next ingest run, the Scanner detects it and processes it through the normal Integrator → Writer pipeline
5. The result lands in `wiki/synthesis/<slug>.md` (or updates existing pages)

This ensures the human remains the curator. The LLM never unilaterally decides what enters the wiki.

---

## 9. Wiki Pages — Evolved Format

### Standard frontmatter (all pages)
```yaml
---
title: "..."
type: "source|entity|concept|synthesis"
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
sources: ["slug1", "slug2"]
---
```

`updated` is refreshed every time a page is modified. This lets lint find stale pages.

### Entity page — body
```markdown
## Overview
<What it is, in context>

## From [[sources/x]]
<What this source says about the entity>

## From [[sources/y]]
<What this other source says>

## Connections
- [[concepts/...]] — relationship
- [[entities/...]] — relationship
```

Note: each "From [[source]]" section keeps provenance clear. This is the **provenance pattern** — we always know where each piece of information came from.

### Concept page — body
```markdown
## Definition
<Concise definition>

## Deep Dive
<Full explanation, built from all sources>

## Evolution
<How understanding of the concept changed with new sources — optional>

## From [[sources/x]]
<Specific contribution from this source>

## Connections
- [[concepts/...]] — relationship
- [[entities/...]] — relationship
```

---

## 10. Required Tools

| Tool | Used by | Description |
|------|---------|-------------|
| `read_wiki_page(path)` | Integrator, Writer, Querier, Linter | Reads a wiki page. Accepts flexible paths: `entities/agent-framework`, `entities/agent-framework.md`, `wiki/entities/agent-framework.md`, or just `agent-framework` (searches all categories). Normalizes internally. |
| `write_wiki_page(path, content)` | Writer, Querier | Writes/overwrites a page |
| `list_wiki_pages()` | Integrator, Querier, Linter | Lists all pages with paths |
| `search_wiki(query)` | Querier, Linter | Text search across pages (grep) |
| `read_index()` | All | Shortcut to read index.md |
| `append_log(entry)` | Writer, Querier, Linter | Appends entry to log |

---

## 11. Implementation Principles

1. **The Integrator is the brain** — that's where the system is intelligent. The Reader is mechanical, the Writer is executive. The Integrator makes decisions.

2. **Context budget** — the Integrator does NOT receive the full wiki in its prompt. It reads the index (compact) and then explores pages on-demand via tool calls. This keeps context bounded regardless of wiki size. Same pattern as the Querier.

3. **One source, one full cycle** — the pipeline loops per source, not per phase. Each source runs through Reader → Integrator → Writer → Validator → IndexUpdater before the next source begins. This guarantees the Integrator always sees a current wiki. Blind batching (all reads, then all integrations, then all writes) breaks coherence.

4. **Schema as format reference** — `schema.md` is injected into agent prompts to define page format. It does NOT contain orchestration logic — that lives in the Python workflow code.

5. **Idempotency** — re-running ingest on the same source does not duplicate content (the log tracks it, the writer checks what exists).

6. **Simplicity** — no vector DB, no embeddings, no heavy infrastructure. Just markdown files + LLM calls. The index.md is sufficient for navigation at moderate scale (~100 sources).

7. **English only** — all wiki content, agent outputs, index entries, and log entries are in English. If a source document is in another language, the SourceReader translates during extraction. Code blocks are kept as-is (language-neutral).

---

## 12. What NOT to Do

- ❌ Treat ingest as ETL (extract → transform → load without context)
- ❌ Rigid JSON schema for writer output (the writer uses Python templates, not LLM generation)
- ❌ "Never remove content" — sometimes content must be updated/superseded
- ❌ Blind parallelism on the integration phase (sequentiality needed for coherence)
- ❌ Summarize and lose detail — preserve provenance

---

## 13. Testing Strategy

The test suite lives in `wiki_llm_maf/tests/` and uses `pytest`. Tests are split into two categories:

### Unit Tests (no LLM, fast)
Test deterministic components in isolation:
- **Scanner** — idempotency (skips already-ingested files via log check)
- **IndexUpdater** — rebuilds `index.md` deterministically from wiki pages on disk
- **WriteValidator** — validates wikilinks, frontmatter, content presence
- **Deterministic Lint** — broken links, orphan pages, missing frontmatter

### E2E Tests (mocked LLM)
Test full workflow pipelines with mocked `agent.run()` returning realistic structured outputs:
- **Ingest E2E** — Scanner → Reader → Integrator → Writer → Validator → IndexUpdater
- **Query E2E** — Querier → answer filing to `questions_pending/`
- **Lint E2E** — deterministic phase + semantic phase → `lint_pending/`

Fixtures (`conftest.py`) provide isolated `tmp_path`-based wiki roots with minimal scaffolding, ensuring tests never touch the real wiki data.

---

## 14. Open Questions (to decide together)

- [x] Claim granularity: per-claim tracking with hashes, or trust context?
- [x] Automatic lint post-ingest or only on-demand? On-demand only. WriteValidator handles immediate checks.
- [x] Filing-back threshold: human-gated via questions_pending → questions_approved/ move
- [x] Image support: not needed for v1 (text-only sources)
- [x] Batching: one source at a time (sequential integration). Reader can parallelize, but Integrator + Writer run sequentially.
