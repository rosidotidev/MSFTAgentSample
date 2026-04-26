# Microsoft Agent Framework – Sample Projects

A collection of pipelines and workflows built with the [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) (`agent-framework` 1.0.1), following an incremental approach — from a bare-minimum single-agent script to scalable, LLM-minimal workflow pipelines.

---

## Pipelines

### Backlog → Jira

Two agents collaborate sequentially: a reader parses a Markdown backlog, an executor provisions Epics and Stories on Jira via MCP.

→ **[PIPELINE_BACKLOG_JIRA.md](PIPELINE_BACKLOG_JIRA.md)**

### DOCX → Markdown

A workflow-based pipeline that extracts content and images from `.docx` files, analyses images via GPT-4o vision, and assembles structured Markdown documents. Five progressive variants, from fully LLM-driven to LLM-minimal.

→ **[PIPELINE_DOCX_TO_MD.md](PIPELINE_DOCX_TO_MD.md)**

---

## Entry Points Catalog

| # | Entry Point | Pipeline | What it demonstrates |
|:---:|---|---|---|
| 1 | `main.py` | — | **Hello world**: single agent, no tools |
| 2 | `main_mcp_jira.py` | Backlog → Jira | **Single agent + MCP**: interactive Jira commands (OpenAI) |
| 3 | `main_mcp_jira_lf.py` | Backlog → Jira | **Single agent + MCP**: Foundry Local experiment (see [note](PIPELINE_BACKLOG_JIRA.md#note-foundry-local-experiment)) |
| 4 | `main_backlog_from_md.py` | Backlog → Jira | **Two-agent pipeline (monolithic)**: reader + executor in one file |
| 5 | `main_backlog_from_md_std.py` | Backlog → Jira | **Two-agent pipeline (modular)**: refactored into `afw_core/` |
| 6 | `main_doc_ingest.py` | DOCX → MD | **Agent-based**: sequential agents, no workflow |
| 7 | `main_doc_ingest_wfl.py` | DOCX → MD | **Workflow**: 3-executor graph |
| 8 | `main_doc_ingest_wfl_tpl.py` | DOCX → MD | **Workflow + template**: deterministic image filling |
| 9 | `main_doc_ingest_wfl_tpl_multi.py` | DOCX → MD | **Scaled**: parallel vision + chunked assembly |
| 10 | `main_doc_ingest_wfl_tpl_multi_opt.py` | DOCX → MD | **LLM-minimal**: only vision calls use an LLM |

---

## Project Structure

```
MSFTAgentSample/
├── afw_core/
│   ├── agents/             # Agent definitions (create_agent factories)
│   ├── executors/          # Workflow executors (processing units)
│   ├── workflows/          # Workflow builders (graph wiring)
│   ├── tools/              # Custom @tool functions
│   ├── mcps/               # MCP server proxy configurations
│   ├── llms/               # LLM client factories
│   └── models/             # Pydantic data models
│
├── input/                  # Input files (backlogs, .docx documents)
├── output/                 # Generated output (reports, Markdown docs)
├── docs/                   # Documentation and reference material
│
├── main_*.py               # Entry point scripts (see catalog above)
├── .env                    # Environment variables
├── Pipfile                 # pipenv dependencies
└── setup.txt               # Pinned install commands
```

---

## Prerequisites

- **Python 3.12**
- **pipenv** (`pip install pipenv`)
- **OpenAI API key** with access to a chat model (e.g. `gpt-4o-mini`)

Additional prerequisites per pipeline:

| Pipeline | Requires |
|---|---|
| Backlog → Jira | Jira Cloud instance + API token |
| DOCX → Markdown | `.docx` files in `input/docx/` |

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/MSFTAgentSample.git
cd MSFTAgentSample
```

### 2. Install dependencies

```bash
pipenv --python 3.12
pipenv install
```

Or install manually:

```bash
pipenv install agent-framework==1.0.1
pipenv install agent-framework-openai==1.0.1
pipenv install python-dotenv==1.2.2
pipenv install mcp-atlassian==0.21.1      # only for Backlog → Jira
pipenv install unstructured==0.17.2       # only for DOCX → Markdown
pipenv install python-docx==1.1.2         # only for DOCX → Markdown
```

### 3. Configure environment variables

Create a `.env` file in the project root:

```env
# Common (required)
OPENAI_API_KEY=sk-...
OPENAI_CHAT_MODEL=gpt-4o-mini

# Backlog → Jira (optional, only if using Jira pipeline)
JIRA_URL=https://your-domain.atlassian.net
JIRA_USERNAME=your-email@example.com
JIRA_API_TOKEN=your-jira-api-token
TOOLSETS=all

# DOCX → Markdown (optional, defaults shown)
DOC_INGEST_INPUT_DIR=input/docx
DOC_INGEST_OUTPUT_DIR=output/doc_ingest
VISION_MODEL=gpt-4o-mini
VISION_MAX_CONCURRENT=5
```

---

## Key Design Decisions

- **Microsoft Agent Framework** chosen for native MCP support, function tools, and multi-agent orchestration.
- **Incremental evolution**: each pipeline variant builds on the previous one without modifying existing files.
- **Agent instructions** define behavioral constraints (how); user queries define task specifics (what).
- **Pydantic models** validate structured data between pipeline stages.
- **Workflow pattern** (graph-based): executors connected by edges, with typed message passing and shared state.
- **LLM minimisation**: if a step can be implemented deterministically in Python, do not use an LLM. Reserve LLM calls for tasks that genuinely require language understanding or vision.
- **Scaling patterns**: parallel I/O via `asyncio.gather`, document chunking at heading boundaries, bounded concurrency via semaphore.

---

## Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `expected 'key' property to be a string` | LLM sends parallel MCP tool calls | Ensure agent instructions say "ONE AT A TIME" |
| Import errors on `afw_core` | Missing directory or wrong cwd | Run from project root |
| `max_consecutive_errors_per_request` hit | Agent retries exceed 3 | Check MCP server logs, verify credentials |
| Jira 401/403 | Invalid API token or permissions | Verify `.env` values and Jira project permissions |
| `ModuleNotFoundError` for `agent_framework` | Not running inside pipenv | Use `pipenv run python ...` |
| `input message is too large` | Model context window too small | Switch to GPU variant or use a larger model |

### Foundry Local – Managing Models

```bash
foundry service list          # Models loaded in memory
foundry cache list            # Models cached on disk
foundry cache location        # Cache directory path
foundry model unload <alias>  # Unload from memory
foundry cache rm <model-id>   # Delete from disk
```

> **Tip:** GPU variants support ~32K token context. NPU variants are limited to ~4K tokens.

---

## Tech Stack

| Component | Package | Version |
|---|---|---|
| Agent Framework | `agent-framework` | 1.0.1 |
| OpenAI Provider | `agent-framework-openai` | 1.0.1 |
| Jira MCP Server | `mcp-atlassian` | 0.21.1 |
| DOCX Parsing | `unstructured`, `python-docx` | — |
| Env Variables | `python-dotenv` | 1.2.2 |
| Validation | `pydantic` | (transitive) |
| Runtime | Python | 3.12 |

---

## License

This project is provided as-is for educational and demonstration purposes.
