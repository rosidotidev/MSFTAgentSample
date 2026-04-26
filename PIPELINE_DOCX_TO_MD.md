# Pipeline: DOCX → Markdown

Extract content and images from `.docx` files, analyse images via GPT-4o vision, and assemble structured Markdown documents with embedded image descriptions.

---

## Overview

The pipeline converts Word documents into rich Markdown with detailed, AI-generated image descriptions. It evolved through five progressive variants, from a fully LLM-driven approach to an LLM-minimal architecture where only the image vision calls require an LLM.

---

## Variants

| # | Entry Point | Architecture | LLM Calls | Key Feature |
|:---:|---|---|---|---|
| 1 | `main_doc_ingest.py` | Sequential agents | 3 per file | Baseline: all steps use LLM agents |
| 2 | `main_doc_ingest_wfl.py` | Workflow (3 executors) | 3 per file | Graph-based orchestration with streaming events |
| 3 | `main_doc_ingest_wfl_tpl.py` | Workflow (4 executors) | 2 per file + N images | Template + filler: deterministic image insertion |
| 4 | `main_doc_ingest_wfl_tpl_multi.py` | Workflow (4 executors) | N images (parallel) + M chunks | Scaled: parallel vision, chunked assembly |
| 5 | `main_doc_ingest_wfl_tpl_multi_opt.py` | Workflow (4 executors) | N images (parallel) only | **LLM-minimal**: extraction and assembly are pure Python |

### Evolution Rationale

- **v1 → v2**: Move from sequential agent calls to a workflow graph for better observability (events) and structure.
- **v2 → v3**: Separate the Markdown template (LLM) from image description filling (Python regex). Eliminates the problem of LLMs forgetting to close description tags.
- **v3 → v4**: Parallel image analysis (`asyncio.gather`) and chunked template assembly (split by heading) for scalability with large or multiple documents.
- **v4 → v5**: Replace the LLM-based doc extractor and template assembler with pure Python equivalents. The extraction was already a Python tool behind an agent wrapper; the assembly is a deterministic type-to-Markdown mapping using `unstructured` metadata (heading depth, segment types). Only vision calls remain as LLM usage.

---

## Workflow Graph (v5 — LLM-minimal)

```
DocExtractorDirect ──▶ ParallelImageAnalyst ──▶ DeterministicAssembler ──▶ TemplateFillerMulti
   (Python)               (async Vision)             (Python)                  (Python)
```

---

## Components

```
afw_core/
├── agents/
│   ├── doc_extractor.py            # DocExtractor agent (v1-v4)
│   ├── image_analyst.py            # ImageAnalyst agent (v1-v3)
│   ├── content_assembler.py        # ContentAssembler agent (v1-v2)
│   └── template_assembler.py       # TemplateAssembler agent (v3-v4)
├── executors/
│   ├── doc_extractor.py            # Agent-wrapping extractor (v2-v4)
│   ├── doc_extractor_direct.py     # Pure-Python extractor (v5)
│   ├── image_analyst.py            # Agent-wrapping analyst (v2)
│   ├── image_analyst_stateful.py   # Agent-wrapping + state (v3)
│   ├── parallel_image_analyst.py   # Direct async vision (v4-v5)
│   ├── content_assembler.py        # Agent-wrapping assembler (v2)
│   ├── template_assembler.py       # Agent-wrapping template (v3)
│   ├── chunked_template_assembler.py # Chunked LLM assembly (v4)
│   ├── deterministic_assembler.py  # Pure-Python assembly (v5)
│   ├── template_filler.py          # Regex filler (v3)
│   └── template_filler_multi.py    # Regex filler multi-doc (v4-v5)
├── workflows/
│   ├── doc_ingest.py               # v2 workflow builder
│   ├── doc_ingest_tpl.py           # v3 workflow builder
│   ├── doc_ingest_tpl_multi.py     # v4 workflow builder
│   └── doc_ingest_tpl_multi_opt.py # v5 workflow builder
├── tools/
│   ├── docx_extractor.py          # Extract text + images from .docx
│   ├── image_describer.py         # GPT-4o-mini vision descriptions
│   └── markdown_writer.py         # Write Markdown to disk
└── models/
    └── doc_ingest.py              # Pydantic models (extraction, assembly)
```

---

## Prerequisites

In addition to the [common prerequisites](README.md#prerequisites):

- `.docx` files placed in `input/docx/`
- Additional packages: `unstructured`, `python-docx`

`.env` variables (optional — defaults shown):

```env
DOC_INGEST_INPUT_DIR=input/docx
DOC_INGEST_OUTPUT_DIR=output/doc_ingest
VISION_MODEL=gpt-4o-mini
VISION_MAX_CONCURRENT=5
```

---

## Usage

### LLM-minimal variant (recommended)

```bash
pipenv run python main_doc_ingest_wfl_tpl_multi_opt.py
```

Uses LLM **only** for image descriptions. Everything else is pure Python.

### Scaled variant

```bash
pipenv run python main_doc_ingest_wfl_tpl_multi.py
```

Parallel vision + chunked LLM assembly. Better Markdown formatting (LLM-inferred heading levels) at the cost of more API calls.

### Template variant

```bash
pipenv run python main_doc_ingest_wfl_tpl.py
```

Sequential processing, template + filler pattern. Good for small batches.

### Baseline workflow

```bash
pipenv run python main_doc_ingest_wfl.py
```

3-executor workflow, fully LLM-driven.

### Agent-only baseline

```bash
pipenv run python main_doc_ingest.py
```

No workflow — sequential agent calls. Useful for comparison.

---

## Output

Each `.docx` file produces:

- `output/doc_ingest/<filename>.md` — Markdown document with image descriptions
- `output/doc_ingest/images/` — extracted images referenced by the Markdown

Image descriptions are inserted as:

```markdown
![Image](./images/img-001-abc123.png)
**[Image Description]:** Detailed vision-generated description...
**[End Image Description]**
```

---

## Customization

### Process different files

Place `.docx` files in `input/docx/` (or set `DOC_INGEST_INPUT_DIR` in `.env`).

### Change output location

Set `DOC_INGEST_OUTPUT_DIR` in `.env`.

### Adjust vision concurrency

Set `VISION_MAX_CONCURRENT` in `.env` (default: 5). Higher values speed up image analysis but increase API rate pressure.

### Adjust vision detail

Edit the system prompt in `afw_core/tools/image_describer.py` (agent variants) or `afw_core/executors/parallel_image_analyst.py` (direct variant).
