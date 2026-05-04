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

### Role of `schema.md`

`schema.md` is a **format reference**, not a program. In a conversational setup (e.g. Claude Code), a CLAUDE.md file acts as the entire orchestration layer — telling the LLM what to do, when, and how. In our agentic solution, orchestration lives in Python code (the workflow), and agent behavior lives in each agent's `INSTRUCTIONS`. 

`schema.md` has one job: define what wiki pages look like. It is **sectioned** with HTML markers (`<!-- SECTION:name -->`) so that each agent can load only the sections it needs:

| Section | Content | Used by |
|---------|---------|---------|
| `core` | Language rule, directory layout, frontmatter, wikilink format | Integrator |
| `templates` | Page body templates (source, entity, concept, synthesis) | Writer |
| `index-log` | Index and log format conventions | Writer |

The shared helper `afw_core/agents/_schema.py` provides two functions:
- `load_schema(*sections)` — loads specific sections by marker name
- `load_full_schema()` — loads all sections (core + templates + index-log)

Agent-specific injection:
- **WikiIntegrator** → `load_schema("core")` — only needs format rules to plan, not full templates
- **WikiWriter** → `load_full_schema()` — needs everything to produce correct pages
- **WikiQuerier** → no schema — it reads existing pages, it doesn't create them

This keeps prompt size bounded: the Integrator (which already carries the extraction + tool results) avoids ~60% of the schema payload.

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
  main_query.py                     ← Entry point: answer questions
  main_lint.py                      ← Entry point: wiki health check
  schema.md                         ← Page format reference (sectioned)
  pytest.ini                        ← Test configuration
  .env.example                      ← Environment variable template
  afw_core/
    agents/                         ← Agent definitions (instructions + factory)
      _schema.py                    ← Shared helper: loads schema sections by marker
      source_reader.py
      wiki_integrator.py
      wiki_writer.py
      wiki_querier.py
      wiki_linter.py
    executors/                      ← Workflow step executors
      scanner.py
      batch_reader.py
      integrator.py
      writer.py
      write_validator.py
      index_updater.py
    tools/                          ← Tools exposed to agents
      wiki_read.py
      wiki_write.py
      wiki_search.py
      wiki_list.py
      log_append.py
    models/                         ← Pydantic data models
      extraction.py
      integration_plan.py
    workflows/                      ← Workflow definitions
      ingest.py
  tests/                            ← Test suite
    conftest.py                     ← Shared fixtures (wiki_root, e2e_wiki_root)
    test_scanner.py                 ← Unit: Scanner idempotency
    test_index_updater.py           ← Unit: IndexUpdater deterministic rebuild
    test_write_validator.py         ← Unit: WriteValidator checks
    test_deterministic_lint.py      ← Unit: broken links, orphans, frontmatter
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
The LLM reads the source and produces a structured analysis:
- Summary
- Key takeaways
- Entities mentioned (with context)
- Concepts covered (with context)
- Main claims (with source spans)

This is "what's in the source". Output: structured JSON.

#### Phase 2 — Integration (WikiIntegrator)
The WikiIntegrator is an **agent with tools in an agentic loop** — not a one-shot prompt. It does NOT receive all wiki content upfront. Instead, it explores the wiki on-demand:

1. It receives the Phase 1 extraction in its prompt
2. It calls `read_index()` to see the current wiki map
3. It reasons about which existing pages are relevant to this new source
4. It calls `read_wiki_page(path)` for each page it wants to inspect (typically 3-10 pages)
5. It may iterate — reading more pages if cross-references reveal further connections
6. Once it has enough context, it produces the integration plan

The LLM autonomously decides:
1. **Which pages to create** (source summary, new entities, new concepts)
2. **Which pages to update** (existing entities/concepts that the new source enriches)
3. **Which contradictions to flag** (if the new source contradicts claims in existing pages)
4. **Which new cross-references to add** (links between pages that are now connected)

Output: an **integration plan** (JSON) that is then executed.

**Why agentic loop?** The alternative (inject index + all relevant pages into one prompt) doesn't scale. At 100+ pages, the context explodes. With tools, the Integrator loads only what it needs — keeping context bounded regardless of wiki size.

#### Phase 3 — Writing (WikiWriter)
The LLM executes the plan:
- Writes/updates pages one at a time
- For each update, reads the current page and produces the updated version
- Updates `index.md`
- Appends to `log.md`

**Key insight**: Phase 2 is where the intelligence lives. The LLM doesn't "dump" an extraction — it looks at the existing wiki and decides how to evolve it.

---

### 3.2 QUERY

**Input**: a user question

**How it works**: The WikiQuerierAgent is an LLM with tools in an agentic loop. There is no vector search, no embedding retrieval. The LLM *is* the search engine — it reads the index, reasons about which pages are relevant, and requests them one by one.

**Step-by-step**:
1. The agent receives the question in its prompt
2. It calls `read_index()` → gets the full catalog of wiki pages (title + one-liner per page)
3. The LLM reasons: "To answer this, I need pages X, Y, and Z"
4. It calls `read_wiki_page(path)` for each relevant page (typically 2-5 pages)
5. If needed, it calls `search_wiki(query)` to grep for specific terms not obvious from the index
6. With enough context gathered, it synthesizes the answer with `[[source/page]]` citations
7. The agent may iterate — if a page references another that seems relevant, it reads that too

**Pending mechanism**: Every answer is saved as a markdown file in `questions_pending/<slug>.md` with frontmatter (query, date, sources used). The folder is an archive — nothing is ever deleted from it.

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

### 4.1 SourceReaderAgent
- **Input**: raw file content
- **Output**: `SourceExtraction` Pydantic model (guaranteed valid JSON via framework `response_format`)
- **No tools** — text analysis → structured output only
- **No wiki context** — works only on the source
- **Structured output enforcement** — the executor passes `options={"response_format": SourceExtraction}` to `agent.run()`. The framework guarantees a validated Pydantic instance, eliminating JSON parse failures regardless of LLM provider.

### 4.2 WikiIntegratorAgent (the heart of the system)
- **Input**: source extraction (in prompt)
- **Output**: integration plan (JSON)
- **Tools**: `read_index()`, `read_wiki_page(path)`, `list_wiki_pages()`
- **Runs as an agentic loop** — explores the wiki on-demand via tool calls
- **This agent is the "brain"** — it decides what to update, create, and flag
- **Context stays bounded** — it only loads pages it deems relevant, never the full wiki
- **Deduplication judgment** — the Integrator must not rely only on exact slug matching. When checking the index, it should reason about semantic overlap — if an existing page covers substantially the same entity/concept under a different name or slightly different scope, the Integrator should route to `pages_to_update` (enrich) rather than `pages_to_create`. The index one-liners exist precisely to support this judgment without reading every page.

Integration plan schema:
```json
{
  "pages_to_create": [
    {"path": "wiki/sources/x.md", "type": "source", "reason": "..."},
    {"path": "wiki/entities/y.md", "type": "entity", "reason": "..."}
  ],
  "pages_to_update": [
    {"path": "wiki/concepts/z.md", "action": "enrich", "what": "adds section about X"},
    {"path": "wiki/entities/w.md", "action": "add_reference", "what": "new source mentions it"}
  ],
  "contradictions": [
    {"page": "wiki/concepts/foo.md", "existing_claim": "...", "new_claim": "...", "source": "..."}
  ],
  "new_cross_references": [
    {"from": "wiki/entities/a.md", "to": "wiki/concepts/b.md", "reason": "..."}
  ]
}
```

### 4.3 WikiWriterAgent
- **Input**: for each page in the plan, receives: (1) the plan entry, (2) the **filtered** source extraction, (3) the current page content (read via tool), (4) the list of allowed wikilinks
- **Output**: written/updated pages
- **Tools**: `read_wiki_page`, `write_wiki_page`
- **Follows schema.md for format** — but content is driven by the extraction
- The plan tells it *what to do*; the extraction gives it *the material*; the current page gives it *what exists*
- Works one page at a time: reads current → integrates extraction content per the plan → writes the full updated page
- Does NOT invent content — everything it writes comes from the extraction or the existing page
- **Content filtering** — the Writer does NOT receive the full extraction. For each page it writes, it receives only the relevant subset: for an entity page, only that entity's data + source metadata; for a source page, only the summary + takeaways + entity/concept names. This keeps the LLM focused and prevents cross-contamination between pages.
- **Allowed wikilinks (preventive)** — the Writer receives the list of all existing wiki pages (from the current index) plus all pages in the current integration plan. It may only use `[[wikilinks]]` pointing to pages in this set. Links to nonexistent pages must not be created.

### 4.6 WriteValidator (deterministic, no LLM)
- **Runs after each page write** — pure Python, zero LLM calls
- **Checks**: code examples from extraction appear in written page, entity/concept names are present, wikilinks are syntactically valid, **all `[[wikilinks]]` point to files that exist on disk or are listed in the current plan**
- **On failure**: logs a warning with what's missing — does NOT auto-retry
- **Purpose**: safety net, not a blocker. The human reviews warnings in the log
- **Broken link detection (post-mortem)**: any `[[path]]` that does not resolve to an existing `.md` file is flagged. This catches cases where the Writer ignored the allowed list or where a planned page failed to write.

### 4.4 WikiQuerierAgent
- **Input**: user query
- **Tools**: `read_wiki_page`, `list_wiki_pages`, `write_wiki_page` (for filing back)
- **Output**: markdown answer with citations

### 4.5 WikiLinterAgent
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

### IntegrationPlan (WikiIntegrator output)
```python
class PageToCreate(BaseModel):
    path: str
    page_type: str               # source|entity|concept
    content_brief: str           # What to write (guidance for the writer)

class PageToUpdate(BaseModel):
    path: str
    action: str                  # enrich|add_reference|flag_contradiction|add_crossref
    detail: str                  # What to do specifically

class Contradiction(BaseModel):
    page: str
    existing_claim: str
    new_claim: str
    new_source: str
    resolution_hint: str         # LLM's suggestion

class IntegrationPlan(BaseModel):
    pages_to_create: list[PageToCreate]
    pages_to_update: list[PageToUpdate]
    contradictions: list[Contradiction]
    new_cross_references: list[tuple[str, str, str]]  # (from, to, reason)
```

---

## 6. Execution Workflow (Ingest)

```
┌─────────────┐
│   Scanner   │  Finds new files in raw/ + questions_approved/
└──────┬──────┘
       │ file_list
       ▼
┌──────────────────────────────────────────────────────────────┐
│              FOR EACH SOURCE FILE (sequential)               │
│                                                              │
│  ┌─────────────────┐                                         │
│  │  SourceReader   │  Read file → extract JSON               │
│  └──────┬──────────┘                                         │
│         │ extraction                                         │
│         ▼                                                    │
│  ┌─────────────────────┐                                     │
│  │  WikiIntegrator     │  Read index + relevant pages        │
│  │  (THE CORE)         │  → produce integration plan         │
│  └──────┬──────────────┘                                     │
│         │ plan                                               │
│         ▼                                                    │
│  ┌─────────────────┐                                         │
│  │   WikiWriter    │  Execute plan, write/update pages       │
│  └──────┬──────────┘                                         │
│         │                                                    │
│         ▼                                                    │
│  ┌─────────────────┐                                         │
│  │ WriteValidator  │  Deterministic checks (no LLM)          │
│  └──────┬──────────┘                                         │
│         │                                                    │
│         ▼                                                    │
│  ┌─────────────────┐                                         │
│  │  IndexUpdater   │  Rebuild index.md + append log entry    │
│  └─────────────────┘                                         │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Per-source loop, not a linear pipeline.** The five steps inside the box run sequentially for each source file before moving to the next. This ensures:
- The Integrator always sees the pages written by previous sources (up-to-date index)
- The IndexUpdater rebuilds `index.md` after each source, so the next Integrator reads a current catalog
- No risk of duplicate page creation across sources

The Scanner runs once at the start. Everything else loops.

---

## 7. Contradiction Handling

When the WikiIntegrator finds a contradiction:
1. Documents it in the plan
2. The WikiWriter inserts it in the page with a visible block:

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
- ❌ Rigid JSON schema for writer output (the writer produces free markdown, guided by schema.md)
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
