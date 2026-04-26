---
title: "Microsoft Agent Framework: From Agents to Workflows, Five Iterations of a DOCX-to-Markdown Pipeline"
published: true
tags: agentframework, openai, python, ai
cover_image: https://dev-to-uploads.s3.amazonaws.com/uploads/articles/6293jxf2gxazvde1uuy8.jpg
---

In my [previous article](https://dev.to/rosidotidev/microsoft-agent-framework-from-zero-to-multi-agent-pipeline-1np2), I built a multi-agent pipeline that reads a Markdown backlog and provisions Epics and Stories on Jira. That project used two agents collaborating sequentially, wired together with plain Python orchestration.

This time I wanted to understand something specific: does the Microsoft Agent Framework (MFA) have a construct for defining execution graphs, similar to what LangGraph offers with its `StateGraph` or CrewAI with its `Flow`? In other words, can you define nodes, edges, and let the framework handle execution order, state propagation, and event streaming? To find out, I needed a use case that was practical enough to be reusable, complex enough to stress the graph model, and different enough from the Jira pipeline to force me into new territory.

I landed on **converting Word documents into rich Markdown files with AI-generated image descriptions**. The kind of structured, image-heavy documents (functional specifications, architecture documents, technical guides) that are notoriously hard to index in a RAG system because the images carry as much information as the text. A useful asset in itself, and a good bench for a multi-step pipeline.

## MFA Workflows in 30 Seconds

The answer to my question turned out to be yes. The framework provides a [Workflow system](https://learn.microsoft.com/en-us/agent-framework/workflows/) built on three primitives:

- **Executor**: a processing node. You subclass it, implement a `@handler` method, and it receives typed input and produces output. An executor can wrap an agent, call an API directly, or run pure Python, the framework doesn't care.
- **WorkflowBuilder**: the graph constructor. You declare a start node, then chain `.add_edge(source, target)` calls to define the execution path.
- **Edges**: directed connections between executors. Data flows along edges via `ctx.send_message()`, while `ctx.set_state()` / `ctx.get_state()` provide a shared store accessible by any node in the graph.

When you call `workflow.run(input, stream=True)`, the framework walks the graph and emits events (`executor_invoked`, `executor_completed`, `output`) that give you real-time visibility into each step.

With these primitives in hand, I could start building.

The idea behind the use case is simple: if you can turn every image into a detailed textual description embedded directly in the Markdown, a future RAG pipeline can "see" diagrams, screenshots, and flowcharts without needing a multimodal model at query time. The image content becomes searchable text.

What started as a straightforward agent-based pipeline evolved through five iterations into something quite different: a **workflow-based, LLM-minimal architecture** where Python does 90% of the work and the LLM is called only for what it's genuinely good at, describing images.

All the code is available on [GitHub (MSFTAgentSample)](https://github.com/rosidotidev/MSFTAgentSample).

## The Use Case

Given a folder of `.docx` files, the pipeline should:

1. **Extract** all text, tables, and images from each document, preserving the logical order and tracking where each image appears in the text flow.
2. **Describe** every extracted image using GPT-4o vision, producing thorough, structured descriptions that capture every visible element.
3. **Assemble** a clean Markdown document where headings, paragraphs, tables, and images are rendered correctly, with each image followed by its AI-generated description.
4. **Write** the final `.md` files to disk, ready for indexing or publishing.

The output looks like this:

```markdown
## 6. Functional Requirements

The system shall provide a task management interface...

![Image](./images/img-003-a1b2c3d4.png)
**[Image Description]:** This is a screenshot of a UI mockup showing
a task management dashboard with three columns: To Do, In Progress,
and Done. Each column contains card-like elements with task titles...
**[End Image Description]**
```

<!-- TODO: screenshot of a generated Markdown file rendered in VS Code preview -->

## The Starting Point: Agents Only (v1)

The first version followed the same pattern as the Jira pipeline: sequential agents, no workflow. Three agents collaborating in a chain:

```plaintext
DocExtractorAgent → ImageAnalystAgent → ContentAssemblerAgent
```

Each agent wraps a specific capability:

- **DocExtractorAgent** calls a `@tool` function that uses `unstructured` and `python-docx` to extract text segments and images from `.docx` files. The output is a structured JSON with `text_segments` (typed: Title, NarrativeText, Table, ListItem, image) and an `images` array with file paths and surrounding context.
- **ImageAnalystAgent** receives the extraction JSON, collects all image references, and calls a `describe_images` tool that sends each image to GPT-4o-mini vision. The vision prompt is thorough: it asks for image type identification, element-by-element description, all visible text transcription, relationships and flow, and layout details.
- **ContentAssemblerAgent** takes the extraction data plus the image descriptions and produces the final Markdown.

The orchestration is plain Python, same as before:

```python
response1 = await extractor_agent.run(f'input_dir="{INPUT_DIR}", output_dir="{OUTPUT_DIR}"')
response2 = await analyst_agent.run(response1.text)
response3 = await assembler_agent.run(
    f"extraction:\n{response1.text}\n\ndescriptions:\n{response2.text}\n\noutput_dir=\"{OUTPUT_DIR}\""
)
```

This worked, but several problems were immediately visible.

## What Broke and Why

**The LLM forgot to close tags.** The ContentAssemblerAgent was instructed to wrap each image description in `**[Image Description]:**` and `**[End Image Description]**` tags. But on long documents, the LLM would sometimes omit the closing tag, breaking downstream parsing.

**No observability.** With plain `agent.run()` calls, you only see the final output. You don't know which agent is running, how long each step took, or where a failure occurred.

**Sequential image analysis was slow.** Each image was sent to GPT-4o-mini one at a time. A document with 10 images meant 10 sequential API calls, each taking 3-5 seconds.

**Scalability was questionable.** The ContentAssemblerAgent received the entire extraction JSON in its prompt. For a 50-page document, that JSON could exceed the model's context window, causing truncation or quality degradation.

These issues led me to explore the **Workflow** feature of the Microsoft Agent Framework.

## Introducing Workflows (v2)

With the workflow primitives I described above, the first step was straightforward: wrap each agent inside an executor. Here's what a minimal executor looks like:

```python
from agent_framework import Executor, WorkflowContext, handler

class MyExecutor(Executor):

    def __init__(self):
        super().__init__(id="my_executor")

    @handler
    async def handle(self, input_data: str, ctx: WorkflowContext[str]) -> None:
        result = do_something(input_data)
        await ctx.send_message(result)  # forward to next executor
```

Wire them up, and you get a graph with event streaming out of the box:

```python
workflow = (
    WorkflowBuilder(start_executor=executor_a)
    .add_edge(executor_a, executor_b)
    .add_edge(executor_b, executor_c)
    .build()
)

async for event in workflow.run(input_data, stream=True):
    if event.type == "executor_invoked":
        print(f"Starting {event.executor_id}...")
    elif event.type == "executor_completed":
        print(f"Done: {event.executor_id}")
    elif event.type == "output":
        print(f"Result: {event.data}")
```

For v2, the graph was:

```plaintext
DocExtractorExecutor ──▶ ImageAnalystExecutor ──▶ ContentAssemblerExecutor
```

One thing worth noting: besides edge-based data flow (`ctx.send_message`), executors can also use **shared state** (`ctx.set_state` / `ctx.get_state`). This lets a node store data that any downstream node can read directly, without it having to pass through intermediate nodes.

For example, the DocExtractor saves the extraction result to state so that the ContentAssembler (two steps later) can read it directly, without the data having to flow through the ImageAnalyst:

```python
class DocExtractorExecutor(Executor):

    @handler
    async def handle(self, prompt: str, ctx: WorkflowContext[str]) -> None:
        response = await self._agent.run(prompt)
        ctx.set_state("extraction", response.text)  # shared state
        await ctx.send_message(response.text)        # edge to next executor
```

Same functionality as v1, but now with event streaming and a clear graph structure.

## The Template + Filler Pattern (v3)

The closing-tag problem from v1 persisted in v2, because the ContentAssembler was still an LLM generating the full Markdown including image descriptions. LLMs are inherently unreliable for repetitive structural tasks like "always close every tag."

The solution was to split the assembly into two steps:

1. **TemplateAssembler** (LLM), generates the Markdown structure with `<!--IMG:filename-->` HTML comment placeholders instead of actual descriptions.
2. **TemplateFiller** (pure Python), reads the image descriptions from state and replaces each placeholder with the formatted description using a regex.

The workflow became a 4-node graph:

```plaintext
DocExtractor ──▶ ImageAnalystStateful ──▶ TemplateAssembler ──▶ TemplateFiller
```

The TemplateFiller is completely deterministic:

```python
_PLACEHOLDER_RE = re.compile(r"<!--IMG:([\w.\-]+)-->")

def _replace(match: re.Match) -> str:
    fname = match.group(1)
    replacement = desc_map.get(fname)
    if replacement is None:
        return match.group(0)  # leave placeholder as-is
    return replacement

filled = _PLACEHOLDER_RE.sub(_replace, content)
```

No LLM, no token cost, no randomness. The closing tag problem disappeared because the Python code always writes both the opening and closing tags.

This was the turning point. It made me ask: **where else am I using an LLM for something Python can do better?**

## Scaling Up (v4): Parallel Vision + Chunked Assembly

With the architecture cleaned up, two scaling bottlenecks remained:

**Image analysis was sequential.** The ImageAnalyst agent called the `describe_images` tool, which internally looped through images one at a time. For N images, that's N sequential API calls.

The fix: a new `ParallelImageAnalystExecutor` that bypasses the agent entirely and calls `AsyncOpenAI` directly with `asyncio.gather`, bounded by a semaphore:

```python
class ParallelImageAnalystExecutor(Executor):

    def __init__(self):
        super().__init__(id="parallel_image_analyst")

    @handler
    async def handle(self, extraction_json: str, ctx: WorkflowContext[str]) -> None:
        aclient = AsyncOpenAI()
        semaphore = asyncio.Semaphore(MAX_CONCURRENT)

        tasks = [
            _describe_image_async(aclient, img["path"], img.get("context", ""), semaphore)
            for img in all_images
        ]
        results = await asyncio.gather(*tasks)

        result_json = json.dumps({"images": list(results)}, ensure_ascii=False)
        ctx.set_state("descriptions", result_json)
        await ctx.send_message(result_json)
```

With `MAX_CONCURRENT=5` (configurable via environment variable), 10 images now take ~5 seconds instead of ~40.

**Template assembly could exceed context window.** The TemplateAssembler received the entire document extraction in a single prompt. For large documents, this meant prompt truncation or degraded output quality.

The fix: a `ChunkedTemplateAssemblerExecutor` that splits the document's `text_segments` at heading boundaries (using the `Title` type from `unstructured`), processes each chunk with a separate LLM call, and concatenates the results:

```python
def _chunk_segments(text_segments: list[dict]) -> list[list[dict]]:
    chunks: list[list[dict]] = []
    current: list[dict] = []

    for seg in text_segments:
        if seg.get("type") in {"Title", "Header"} and current:
            chunks.append(current)
            current = []
        current.append(seg)

    if current:
        chunks.append(current)
    return chunks
```

Each LLM call sees only one section (~5-15 paragraphs), keeping token usage low and quality consistent regardless of document length.

## Going LLM-Minimal (v5): The Final Architecture

At this point I stepped back and asked: **do I actually need an LLM for any of the remaining steps?**

### The DocExtractor

The DocExtractor agent received a prompt, called the `extract_docx_files` tool, and returned the tool's JSON output unchanged. The agent was a pure passthrough, it added zero value over calling the Python function directly.

The replacement is trivial:

```python
from afw_core.tools.docx_extractor import _extract_all_docx

class DocExtractorDirectExecutor(Executor):

    def __init__(self, input_dir: str, output_dir: str):
        super().__init__(id="doc_extractor_direct")
        self._input_dir = input_dir
        self._output_dir = output_dir

    @handler
    async def handle(self, prompt: str, ctx: WorkflowContext[str]) -> None:
        results = _extract_all_docx(
            Path(self._input_dir), Path(self._output_dir),
        )
        result_json = json.dumps(results, ensure_ascii=False)
        ctx.set_state("extraction", result_json)
        await ctx.send_message(result_json)
```

One LLM call eliminated.

### The TemplateAssembler

This is where I had to think harder. The LLM was converting `text_segments` JSON into Markdown. The segments already had type information:

```json
{"type": "Title", "text": "6.1 Functional Overview"}
{"type": "NarrativeText", "text": "The system shall provide..."}
{"type": "Table", "text": "| Col1 | Col2 |..."}
{"type": "image", "text": "[IMAGE: img-003-a1b2c3d4.png]"}
{"type": "ListItem", "text": "Enable a user to capture a task in less than 10 seconds"}
```

I investigated what metadata `unstructured` provides. It turned out that `Title` elements have a `category_depth` field (0 for top-level headings, 1 for sub-headings), and heading numbering patterns (`6.1`, `6.1.2`) can be used to infer deeper nesting.

The entire Markdown assembly became a `for` loop with type-based rules:

```python
def _segments_to_markdown(text_segments: list[dict]) -> str:
    lines: list[str] = []
    prev_type: str | None = None

    for seg in text_segments:
        seg_type = seg.get("type", "")
        text = seg.get("text", "").strip()
        if not text:
            continue

        if prev_type == "ListItem" and seg_type != "ListItem":
            lines.append("")

        if seg_type == "Title":
            prefix = _heading_prefix(text)  # ## / ### / #### based on numbering
            lines.append(f"{prefix} {text}")

        elif seg_type == "ListItem":
            lines.append(f"- {text}")

        elif seg_type == "Table":
            lines.append(text)  # already Markdown from extractor

        elif seg_type == "image":
            fname = _extract_filename(text)
            lines.append(f"![Image](./images/{fname})")
            lines.append(f"<!--IMG:{fname}-->")

        else:  # NarrativeText, Text, etc.
            lines.append(text)

        prev_type = seg_type

    return "\n".join(lines)
```

Deterministic, instantaneous, zero cost. And the heading hierarchy is actually more consistent than what the LLM produced, because it follows strict rules rather than "inferring" structure.

Many more LLM calls eliminated.

### The Final Workflow Graph

```plaintext
DocExtractorDirect ──▶ ParallelImageAnalyst ──▶ DeterministicAssembler ──▶ TemplateFillerMulti
   (Python)               (async Vision)             (Python)                  (Python)
```

**LLM usage: only the N parallel vision calls for image descriptions.** Everything else is pure Python.

<!-- TODO: screenshot of the console output showing the 4 executors running -->

### The Workflow Builder

The wiring is clean and concise:

```python
from agent_framework import WorkflowBuilder

def build_doc_ingest_tpl_multi_opt_workflow(input_dir: str, output_dir: str):
    extractor = DocExtractorDirectExecutor(input_dir, output_dir)
    analyst = ParallelImageAnalystExecutor()
    assembler = DeterministicAssemblerExecutor()
    filler = TemplateFillerMultiExecutor()

    return (
        WorkflowBuilder(start_executor=extractor)
        .add_edge(extractor, analyst)
        .add_edge(analyst, assembler)
        .add_edge(assembler, filler)
        .build()
    )
```

Notice: **no `client` or `options` parameter.** Since no executor uses an agent, there's no LLM client to inject. The `ParallelImageAnalyst` creates its own `AsyncOpenAI` client internally because it needs vision, not chat.

### The Entry Point

The entry point consumes the workflow's event stream:

```python
async def main():
    workflow = build_doc_ingest_tpl_multi_opt_workflow(INPUT_DIR, OUTPUT_DIR)

    async for event in workflow.run(
        f'input_dir="{INPUT_DIR}", output_dir="{OUTPUT_DIR}"',
        stream=True,
    ):
        if event.type == "executor_invoked":
            label = {
                "doc_extractor_direct": "📖 Extracting documents (direct)",
                "parallel_image_analyst": "🔍 Analysing images (parallel)",
                "deterministic_assembler": "📝 Assembling Markdown (deterministic)",
                "template_filler_multi": "🔧 Filling image descriptions",
            }.get(event.executor_id, event.executor_id)
            print(f"\n{label}...")

        elif event.type == "executor_completed":
            print(f"   ✓ {event.executor_id} completed")

        elif event.type == "output":
            assembled = AssembledDocumentList.model_validate_json(event.data)
            for doc in assembled.documents:
                print(f"   ✅ {doc.source_file} → {doc.output_path}")
```

<!-- TODO: screenshot of the complete console output -->

## Evolution Summary

| Version | Entry Point | Architecture | LLM Calls | Key Change |
|:---:|---|---|---|---|
| v1 | `main_doc_ingest.py` | Sequential agents | 3 per file | Baseline |
| v2 | `main_doc_ingest_wfl.py` | Workflow (3 executors) | 3 per file | Graph-based, event streaming |
| v3 | `main_doc_ingest_wfl_tpl.py` | Workflow (4 executors) | 2 + N images | Template + filler pattern |
| v4 | `main_doc_ingest_wfl_tpl_multi.py` | Workflow (4 executors) | N parallel + M chunks | Parallel vision, chunked assembly |
| v5 | `main_doc_ingest_wfl_tpl_multi_opt.py` | Workflow (4 executors) | N parallel only | LLM-minimal: Python does the rest |

The cost reduction from v1 to v5 is dramatic. For a document with 5 images and 10 sections, v1 makes ~8 LLM calls (3 agents). V5 makes exactly 5 (one per image, in parallel). The extraction and assembly are free.

## Key Lessons Learned

**Executors don't have to wrap agents.** The framework's `Executor` class is a general-purpose processing unit. It can wrap an agent, call an API directly, or run pure Python logic. The best executors are often the ones with no LLM at all.

**The template + filler pattern is widely applicable.** Whenever you need an LLM to generate structured output with repetitive elements (tags, placeholders, formatting), consider splitting the task: let the LLM generate the structure, and let Python fill in the repetitive parts deterministically.

**`asyncio.gather` with a semaphore is the right pattern for parallel API calls.** It's simple, it respects rate limits, and it keeps you in control of concurrency. No need for complex job queues or thread pools.

**`unstructured` gives you more metadata than you think.** Before deciding to use an LLM for heading hierarchy, I checked what `unstructured` already provides. It turned out it has `category_depth`, `parent_id`, and typed elements (Title, ListItem, NarrativeText, Table), enough to build a complete Markdown document without any AI involvement.

**Workflow versioning via file suffixes works well.** Each iteration is a separate file (`doc_ingest.py`, `doc_ingest_tpl.py`, `doc_ingest_tpl_multi.py`, `doc_ingest_tpl_multi_opt.py`) with its own entry point. Previous versions are preserved for comparison and rollback. No git archaeology needed.

## Conclusion: Takeaways

There is an old saying: "When all you have is a hammer, everything looks like a nail." Working with LLMs can feel exactly like that. You have this incredibly powerful tool that can understand language, generate text, analyze images, and it becomes tempting to route every step through it. Extraction? Let the LLM handle it. Assembly? The LLM can figure out the Markdown. Heading hierarchy? Surely the LLM knows best.

The single biggest takeaway from this project is that **the best LLM call is the one you don't make**. Before building v5, I assumed the extraction and assembly steps "needed" an LLM because they involved understanding document structure. They didn't. The extraction was already a Python tool behind an agent wrapper. The assembly was a deterministic mapping from typed segments to Markdown. The LLM added cost, latency, and randomness without adding value.

Stripping away those unnecessary calls didn't just save tokens. It made the pipeline faster, more predictable, and easier to debug. When something goes wrong in a pure Python executor, you get a stack trace, not a hallucination.

The MFA workflow model made this evolution natural. Because each step is an independent executor wired into a graph, I could replace an agent-based node with a pure Python node without touching anything else. The framework doesn't push you toward LLMs, it gives you the scaffolding and lets you decide what goes inside each node. That turned out to be exactly the right level of abstraction.

The pattern of wrapping agents inside executors and passing data through shared state also proved valuable for reuse. The same agent can be plugged into different workflows without modification, because the executor handles the wiring and the state handles the context. This, combined with a clean, well-defined workflow API, made it straightforward to evolve the solution incrementally, from a naive agent chain all the way to an aggressively optimized pipeline, without ever having to rewrite from scratch.

If the first article was about discovering the framework's building blocks, this one was about learning when *not* to use them. Use the LLM where it genuinely shines, like describing images. For everything else, write Python.

The generated Markdown files, with their embedded image descriptions, are ready for a RAG pipeline. A simple chunking strategy (split on headings, keep image descriptions with their context) would make both text and image content searchable through standard text embeddings, no multimodal retrieval model required.

All the code is available on [GitHub (MSFTAgentSample)](https://github.com/rosidotidev/MSFTAgentSample). The [PIPELINE_DOCX_TO_MD.md](https://github.com/rosidotidev/MSFTAgentSample/blob/main/PIPELINE_DOCX_TO_MD.md) file documents all five variants with setup instructions and usage commands.
