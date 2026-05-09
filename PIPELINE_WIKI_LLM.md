# Pipeline: LLM Wiki

An experimental implementation of [Andrej Karpathy's LLM Wiki concept](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f): an LLM-powered, markdown-based, evergreen knowledge base that integrates, connects, and evolves knowledge over time.

---

## Overview

The wiki is not a database of mechanically extracted cards. It is a **cumulative artifact** where each new source is integrated in the context of what already exists. Three independent workflows operate on the same wiki:

1. **Ingest** — reads raw sources and integrates them into the wiki (new pages, updates, cross-references, contradictions)
2. **Query** — answers questions using the wiki as a knowledge base, with citations
3. **Lint** — performs deterministic + semantic health checks, producing actionable suggestions

All three use the wiki as a knowledge base — no vector search, no embeddings. The LLM reads index + pages directly.

> **Status**: experimental. The core pipeline works end-to-end, but agent prompts, deduplication heuristics, and remediation logic still need tuning. See [BACKLOG_KARPATHY_GAPS.md](docs/BACKLOG_KARPATHY_GAPS.md) for the gap analysis.

---

## Entry Points

| # | Entry Point | Workflow | What it does |
|:---:|---|---|---|
| 1 | `wiki_llm_maf/main_ingest.py` | Ingest | Scans `raw/` + `questions_approved/` + `lint_approved/` for new files, integrates them into the wiki |
| 2 | **`wiki_llm_maf/main_query_adv.py`** | **Query (ADV)** | **Recommended.** Plan → Walk → Answer. 3 steps, 2 LLM calls, deterministic graph traversal |
| 3 | `wiki_llm_maf/main_query.py` | Query (legacy) | Agentic loop with tool calls. Deprecated — will be removed |
| 4 | `wiki_llm_maf/main_lint.py` | Lint | Two-phase health check (deterministic + semantic), saves suggestions to `lint_pending/` |
| 5 | `wiki_llm_maf/main_reset.py` | Reset | Clears the wiki and rebuilds from scratch |

---

## Architecture

### Ingest Workflow

```
Scanner → SourceReader → WikiIntegrator → WikiWriter → WriteValidator → IndexUpdater
                              ↕                ↕
                         (agentic loop)   (agentic loop)
                         reads wiki pages  reads/writes pages
```

The pipeline loops **per source file** (not per phase), ensuring the Integrator always sees an up-to-date wiki.

### Query Workflow

Two pipelines are available:

#### ADV Pipeline (recommended) — `main_query_adv.py`

```
Step 1: PLANNER  (LLM)    — selects seed pages from wiki index (structured output)
Step 2: WALKER   (Python)  — BFS on ## Connections, respects page budget
Step 3: ANSWERER (LLM)    — iterative: one call per page, grows draft answer

  ┌──────────┐     ┌──────────┐     ┌──────────────────────┐
  │ Planner  │────▶│  Walker  │────▶│  Answerer (× N pages)│────▶ Answer
  │ (1 call) │     │ (Python) │     │  (N calls)           │
  └──────────┘     └──────────┘     └──────────────────────┘
      seeds ──────▶ BFS read ──────▶ iterative integration
```

Max seeds: `ADV_MAX_SEEDS` (default 3). Page budget: `PAGE_VISIT_LIMIT` (default 5).

#### Legacy Pipeline (deprecated) — `main_query.py`

> Will be removed in a future version.

```
User question → WikiQuerierAgent (agentic loop, sequential navigation) → Answer
                       ↕
                  reads index + pages (one page per turn, follows ## Connections)
```

### Lint Workflow

```
Phase 1: Deterministic (broken links, orphans, missing frontmatter) → instant
Phase 2: LLM semantic (contradictions, stale claims, missing pages) → lint_pending/

User reviews lint_pending/ → moves approved to lint_approved/ → next ingest picks them up
```

---

## Components

```
wiki_llm_maf/
├── main_ingest.py                  # Entry point: ingest new sources
├── main_query_adv.py               # Entry point: ADV query (recommended)
├── main_query.py                   # Entry point: legacy query (deprecated)
├── main_lint.py                    # Entry point: wiki health check
├── main_reset.py                   # Entry point: clear and rebuild wiki
├── schema.md                       # Wiki page format reference
├── .env.example                    # Environment variable template
│
├── afw_core/
│   ├── agents/
│   │   ├── _schema.py             # Shared helper: loads schema sections by marker
│   │   ├── source_reader.py       # SourceReader: extracts structured data from raw files
│   │   ├── adv_query_planner.py   # ADV: selects seed pages via structured output
│   │   ├── adv_answerer.py        # ADV: iterative answerer (one page per call)
│   │   ├── wiki_querier.py        # Legacy: agentic Q&A loop (deprecated)
│   │   └── wiki_linter.py         # WikiLinter: semantic health checks
│   │
│   ├── executors/
│   │   ├── scanner.py             # Finds new files in raw/, questions_approved/, lint_approved/
│   │   ├── dispatcher.py          # Per-source loop controller (holds file queue)
│   │   ├── source_reader.py       # Chunked extraction with parallel LLM calls
│   │   ├── splitter.py            # Heading-based split + LLM fallback
│   │   ├── integrator.py          # Deterministic dedup + single LLM slug mapping
│   │   ├── writer.py              # Deterministic page writer (no LLM)
│   │   ├── write_validator.py     # Deterministic post-write checks (no LLM)
│   │   ├── index_updater.py       # Rebuilds index.md deterministically
│   │   └── reset.py               # Clears wiki data
│   │
│   ├── tools/
│   │   ├── wiki_read.py           # read_wiki_page(), read_index()
│   │   ├── wiki_write.py          # write_wiki_page()
│   │   ├── wiki_list.py          # list_wiki_pages()
│   │   ├── wiki_search.py         # search_wiki() — grep across pages
│   │   ├── log_append.py          # append_log()
│   │   └── adv_graph_walker.py    # ADV: deterministic BFS on ## Connections
│   │
│   ├── models/
│   │   ├── extraction.py          # SourceExtraction Pydantic model
│   │   └── adv_query.py           # ADV: ADV_QueryPlan, ADV_PageRequest
│   │
│   ├── llms/
│   │   └── openai.py              # OpenAI client factory
│   │
│   └── logging_config.py          # Centralized logging (WIKI_LOG_LEVEL)
│
└── <WIKI_ROOT_DIR>/                # Data root (configurable via .env)
    ├── raw/                        # Immutable source documents
    ├── wiki/                       # LLM-generated wiki pages
    │   ├── index.md                # Navigable catalog
    │   ├── log.md                  # Append-only operation timeline
    │   ├── sources/                # One page per ingested source
    │   ├── entities/               # Named entity pages
    │   ├── concepts/               # Abstract concept pages
    │   └── synthesis/              # Pages from approved query answers
    ├── questions_pending/          # Query answers (auto-generated)
    ├── questions_approved/         # User-promoted answers for integration
    ├── lint_pending/               # Lint suggestions (auto-generated)
    └── lint_approved/              # User-approved lint fixes for integration
```

---

## Prerequisites

In addition to the [common prerequisites](README.md#prerequisites):

- **OpenAI API key** with access to `gpt-4o` (recommended for integration quality)
- Source documents (`.md`, `.txt`) placed in the `raw/` directory

`.env` variables:

```env
# Required
OPENAI_API_KEY=sk-...
OPENAI_CHAT_MODEL=gpt-4o

# Wiki data location (defaults to wiki_llm_maf/ if not set)
WIKI_ROOT_DIR=c:\path\to\your\wiki-data

# Logging verbosity: ERROR | WARNING | INFO | DEBUG
WIKI_LOG_LEVEL=INFO

# Max wiki pages to read per question (default: 5)
PAGE_VISIT_LIMIT=5

# Max seed pages the ADV planner can select (default: 3)
ADV_MAX_SEEDS=3

# Legacy only: minimum fraction of PAGE_VISIT_LIMIT to read before answering
MIN_PAGE_RATIO=0.6
```

---

## Usage

### Ingest new sources

Place source files in `<WIKI_ROOT_DIR>/raw/`, then:

```bash
cd wiki_llm_maf
pipenv run python main_ingest.py
```

The Scanner detects new files (not yet in `log.md`), and processes each through: Reader → Integrator → Writer → Validator → IndexUpdater.

### Query the wiki

```bash
# Recommended: ADV pipeline (plan → walk → answer)
cd wiki_llm_maf
pipenv run python main_query_adv.py
```

```bash
# Legacy: agentic loop (deprecated, will be removed)
cd wiki_llm_maf
pipenv run python main_query.py
```

Interactive loop. Type a question, get a grounded answer with `[[page]]` citations. Answers are saved to `questions_pending/`.

### Lint the wiki

```bash
cd wiki_llm_maf
pipenv run python main_lint.py
```

Phase 1 (deterministic) runs instantly. Phase 2 (semantic) uses an LLM to find contradictions, stale claims, and gaps. All suggestions are saved to `lint_pending/`.

### Filing back (human-curated)

The wiki compounds through human curation:

1. Review `questions_pending/` — move valuable answers to `questions_approved/`
2. Review `lint_pending/` — move actionable suggestions to `lint_approved/`
3. Run `main_ingest.py` again — the Scanner picks up approved files and integrates them

### Reset the wiki

```bash
cd wiki_llm_maf
pipenv run python main_reset.py
```

Clears all wiki pages, index, and log. Source files in `raw/` are preserved.

---

## Testing

Tests live in `wiki_llm_maf/tests/` and are split into two tiers separated by a `@pytest.mark.e2e` marker.

### Unit tests (deterministic, no API key needed)

```bash
# All unit tests — fast, free, no network
pipenv run pytest wiki_llm_maf/tests/ -m "not e2e" -v
```

Covers: Scanner, WriteValidator, IndexUpdater, deterministic lint.

### E2E tests (real LLM calls, requires OPENAI_API_KEY)

```bash
# All E2E tests (~$0.05-0.10 in API costs)
pipenv run pytest wiki_llm_maf/tests/ -m e2e -v

# Only ingest E2E
pipenv run pytest wiki_llm_maf/tests/test_e2e_ingest.py -v

# Only query E2E
pipenv run pytest wiki_llm_maf/tests/test_e2e_query.py -v

# Only lint E2E
pipenv run pytest wiki_llm_maf/tests/test_e2e_lint.py -v

# A single test method
pipenv run pytest wiki_llm_maf/tests/test_e2e_ingest.py::TestE2EIngest::test_ingest_creates_pages -v
```

### Filtering with `-k`

```bash
# Run only tests with "scanner" in the name
pipenv run pytest wiki_llm_maf/tests/ -k "scanner" -v

# Run only tests with "broken" in the name
pipenv run pytest wiki_llm_maf/tests/ -k "broken" -v
```

---

## Key Design Decisions

- **ADV pipeline: separation of concerns** — the query pipeline splits planning (LLM), navigation (deterministic BFS), and answering (LLM) into independent steps. This prevents the LLM from skipping pages or inventing paths, which were recurring issues with the agentic loop approach.
- **Iterative answering with XML tags** — the answerer receives structured XML sections (`<question>`, `<new_page>`, `<previous_draft>`) to prevent prompt confusion. Each page is integrated in a separate LLM call, growing the draft incrementally.
- **Per-source sequential loop** — each source completes the full cycle before the next begins, ensuring the Integrator always sees a current wiki state.
- **Deterministic where possible** — index rebuilding, write validation, graph walking, broken link detection, and orphan checks are pure Python. LLMs are reserved for judgment tasks (seed selection, text integration, semantic analysis).
- **Human-gated compounding** — the LLM produces (answers, suggestions); the human decides what enters the wiki. No automatic modification without review.
- **Structured output** — both the SourceReader and the ADV Planner use Pydantic `response_format` for guaranteed valid structured output.
- **Provenance tracking** — every piece of information in the wiki traces back to its source via `From [[source]]` sections and the append-only `log.md`.

---

## Specification

For the full technical specification (philosophy, data model, agent design, contradiction handling, filing-back mechanism):

→ **[docs/SPEC_LLM_WIKI.md](docs/SPEC_LLM_WIKI.md)**

---

## Known Limitations & Roadmap

- **Writer wikilink enforcement** — the Writer sometimes invents links to nonexistent pages despite being given an allowed list. The WriteValidator catches these post-hoc but doesn't auto-fix yet.
- **Integrator conservatism** — deduplication heuristics can be too aggressive, merging distinct concepts. A creation threshold rule mitigates this but isn't perfect.
- **Lint remediation** — currently lint only diagnoses. Auto-remediation (creating stub pages, fixing broken links) is planned.
- **Single LLM provider** — only OpenAI is supported. Local model support is a future goal.

Full gap analysis: **[docs/BACKLOG_KARPATHY_GAPS.md](docs/BACKLOG_KARPATHY_GAPS.md)**
