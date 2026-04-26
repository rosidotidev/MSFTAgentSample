# Microsoft Agent Framework — Workflows (Python How-To)

> **Source**: [https://learn.microsoft.com/en-us/agent-framework/workflows/](https://learn.microsoft.com/en-us/agent-framework/workflows/)
> Last synced: April 2026

---

## Table of Contents

1. [Overview](#overview)
2. [Agent vs Workflow](#agent-vs-workflow)
3. [Key Features](#key-features)
4. [Core Concepts](#core-concepts)
   - [Executors](#1-executors)
   - [Edges](#2-edges)
   - [Events](#3-events)
   - [Workflow Builder & Execution](#4-workflow-builder--execution)
5. [Agents in Workflows](#agents-in-workflows)
6. [State Management](#state-management)
7. [Human-in-the-Loop (HITL)](#human-in-the-loop-hitl)
8. [Installation & Prerequisites](#installation--prerequisites)
9. [Quick Reference Cheat Sheet](#quick-reference-cheat-sheet)
10. [Further Resources](#further-resources)

---

## Overview

Microsoft Agent Framework **Workflows** let you build intelligent automation systems that blend AI agents with business processes. With a **type-safe**, graph-based architecture you orchestrate complex workflows without infrastructure boiler-plate.

```
pip install agent-framework-core
```

---

## Agent vs Workflow

| | Agent | Workflow |
|---|---|---|
| **Steps** | Dynamic, LLM-driven | Predefined, explicitly defined |
| **Flow control** | Decided by the model at runtime | Graph of executors + edges |
| **Use case** | Conversational tasks, tool use | Multi-agent orchestration, business processes |

A **workflow** can _contain_ agents as components inside its graph.

---

## Key Features

- **Type Safety** — strong typing ensures messages flow correctly; comprehensive validation prevents runtime errors.
- **Flexible Control Flow** — graph-based architecture with `executors` and `edges`. Conditional routing, parallel processing, and dynamic execution paths.
- **External Integration** — built-in request/response patterns for APIs and human-in-the-loop.
- **Checkpointing** — save/restore workflow state for long-running processes.
- **Multi-Agent Orchestration** — sequential, concurrent, hand-off, and magentic patterns.

---

## Core Concepts

### 1. Executors

Executors are the fundamental building blocks. They receive typed messages, perform operations, and produce output messages or events.

#### Class-Based Executor

```python
from agent_framework import Executor, WorkflowContext, handler

class UpperCase(Executor):

    @handler
    async def to_upper_case(self, text: str, ctx: WorkflowContext[str]) -> None:
        """Convert input to uppercase and forward to the next node."""
        await ctx.send_message(text.upper())
```

Using `UpperCase` inside a workflow:

```python
import asyncio
from typing import Never
from agent_framework import WorkflowBuilder, WorkflowContext, executor

@executor(id="print_result")
async def print_result(text: str, ctx: WorkflowContext[Never, str]) -> None:
    await ctx.yield_output(text)

async def main() -> None:
    upper = UpperCase()

    workflow = (
        WorkflowBuilder(start_executor=upper)
        .add_edge(upper, print_result)
        .build()
    )

    result = await workflow.run("hello world")
    print(result.get_outputs()[0])  # → HELLO WORLD

if __name__ == "__main__":
    asyncio.run(main())
```

#### Function-Based Executor (decorator shorthand)

```python
from agent_framework import WorkflowContext, executor

@executor(id="upper_case_executor")
async def upper_case(text: str, ctx: WorkflowContext[str]) -> None:
    await ctx.send_message(text.upper())
```

#### Multiple Input Types

```python
class SampleExecutor(Executor):

    @handler
    async def to_upper_case(self, text: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(text.upper())

    @handler
    async def double_integer(self, number: int, ctx: WorkflowContext[int]) -> None:
        await ctx.send_message(number * 2)
```

#### Explicit Type Parameters

As an alternative to type annotations, specify types explicitly via decorator parameters:

```python
class ExplicitTypesExecutor(Executor):

    @handler(input=str, output=str)
    async def to_upper_case(self, text, ctx) -> None:
        await ctx.send_message(text.upper())

    @handler(input=str | int, output=str)
    async def handle_mixed(self, message, ctx) -> None:
        await ctx.send_message(str(message).upper())

    @handler(input=str, output=int, workflow_output=bool)
    async def process_with_workflow_output(self, message, ctx) -> None:
        await ctx.send_message(len(message))
        await ctx.yield_output(True)
```

#### The `WorkflowContext` Object

| Method | Purpose |
|---|---|
| `send_message(msg)` | Forward a message to connected executors |
| `yield_output(msg)` | Produce workflow output returned/streamed to the caller |
| `set_state(key, val)` | Write to shared state |
| `get_state(key)` | Read from shared state |
| `add_event(event)` | Emit a custom event |
| `request_info(...)` | Send a request for external input (HITL) |

```python
from typing import Never

class OutputExecutor(Executor):

    @handler
    async def handle(self, message: str, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output("Hello, World!")
```

---

### 2. Edges

Edges define how messages flow between executors — they are the connections in the workflow graph.

#### Edge Types Summary

| Pattern | Description | Example Use |
|---|---|---|
| **Direct** | Simple one-to-one | Linear pipelines |
| **Conditional** | Edge with a boolean predicate | Binary routing (if/else) |
| **Switch-Case** | Route to one of N targets | Multi-branch routing |
| **Multi-Selection (Fan-out)** | One executor → multiple targets | Parallel processing |
| **Fan-in** | Multiple executors → single target | Aggregation |

#### Direct Edge

```python
builder = WorkflowBuilder(start_executor=source_executor)
builder.add_edge(source_executor, target_executor)
workflow = builder.build()
```

#### Fan-in Edge

```python
builder.add_fan_in_edge([worker1, worker2, worker3], aggregator_executor)
```

#### Conditional Edge

```python
from typing import Any
from agent_framework import AgentExecutorResponse

def get_condition(expected_result: bool):
    def condition(message: Any) -> bool:
        if not isinstance(message, AgentExecutorResponse):
            return True
        try:
            detection = DetectionResult.model_validate_json(
                message.agent_run_response.text
            )
            return detection.is_spam == expected_result
        except Exception:
            return False
    return condition

# Usage in builder
workflow = (
    WorkflowBuilder(start_executor=spam_detection_agent)
    .add_edge(spam_detection_agent, email_handler, condition=get_condition(False))
    .add_edge(spam_detection_agent, spam_handler, condition=get_condition(True))
    .build()
)
```

#### Switch-Case Edge Group

```python
from agent_framework import Case, Default

workflow = (
    WorkflowBuilder(start_executor=store_email)
    .add_edge(store_email, spam_detection_agent)
    .add_edge(spam_detection_agent, to_detection_result)
    .add_switch_case_edge_group(
        to_detection_result,
        [
            Case(condition=get_case("NotSpam"), target=submit_to_email_assistant),
            Case(condition=get_case("Spam"), target=handle_spam),
            Default(target=handle_uncertain),
        ],
    )
    .add_edge(submit_to_email_assistant, email_assistant_agent)
    .add_edge(email_assistant_agent, finalize_and_send)
    .build()
)
```

#### Multi-Selection Edge Group (Fan-Out)

```python
LONG_EMAIL_THRESHOLD = 100

def select_targets(analysis: AnalysisResult, target_ids: list[str]) -> list[str]:
    handle_spam_id, assistant_id, summarize_id, uncertain_id = target_ids

    if analysis.spam_decision == "Spam":
        return [handle_spam_id]
    elif analysis.spam_decision == "NotSpam":
        targets = [assistant_id]
        if analysis.email_length > LONG_EMAIL_THRESHOLD:
            targets.append(summarize_id)
        return targets
    else:
        return [uncertain_id]

# Build
workflow = (
    WorkflowBuilder(start_executor=store_email)
    .add_edge(store_email, email_analysis_agent)
    .add_edge(email_analysis_agent, to_analysis_result)
    .add_multi_selection_edge_group(
        to_analysis_result,
        [handle_spam, submit_to_assistant, summarize_email, handle_uncertain],
        selection_func=select_targets,
    )
    .add_edge(submit_to_assistant, email_assistant_agent)
    .add_edge(email_assistant_agent, finalize_and_send)
    .add_edge(summarize_email, email_summary_agent)
    .add_edge(email_summary_agent, merge_summary)
    .build()
)
```

---

### 3. Events

The event system provides **observability** into workflow execution via real-time streaming.

#### Built-in Event Types

| `event.type` | Description |
|---|---|
| `"started"` | Workflow execution begins |
| `"status"` | Workflow state changed |
| `"output"` | Workflow produces an output |
| `"failed"` | Workflow terminated with error |
| `"error"` | Non-fatal error from user code |
| `"warning"` | Warning during execution |
| `"executor_invoked"` | Executor starts processing |
| `"executor_completed"` | Executor finishes processing |
| `"executor_failed"` | Executor encounters an error |
| `"data"` | Executor emitted data (e.g., AgentResponse) |
| `"superstep_started"` | Superstep begins |
| `"superstep_completed"` | Superstep completes |
| `"request_info"` | A request is issued (HITL) |

#### Consuming Events

```python
from agent_framework import WorkflowEvent

async for event in workflow.run_stream(input_message):
    if event.type == "executor_invoked":
        print(f"Starting {event.executor_id}")
    elif event.type == "executor_completed":
        print(f"Completed {event.executor_id}: {event.data}")
    elif event.type == "output":
        print(f"Workflow produced output: {event.data}")
        return
    elif event.type == "error":
        print(f"Workflow error: {event.data}")
        return
```

#### Custom Events

```python
from agent_framework import WorkflowEvent

# Defining
event = WorkflowEvent(type="progress", data="Step 1 complete")
event = WorkflowEvent(type="metrics", data={"latency_ms": 42, "tokens": 128})

# Emitting from an executor
class CustomExecutor(Executor):

    @handler
    async def handle(self, message: str, ctx: WorkflowContext[str]) -> None:
        await ctx.add_event(WorkflowEvent(type="progress", data="Validating input"))
        # ... executor logic ...
        await ctx.add_event(WorkflowEvent(type="progress", data="Processing complete"))

# Consuming
async for event in workflow.run(input_message, stream=True):
    if event.type == "progress":
        print(f"Progress: {event.data}")
    elif event.type == "output":
        print(f"Done: {event.data}")
```

> **Note**: Event types `"started"`, `"status"`, and `"failed"` are reserved. Custom events using those types are ignored.

---

### 4. Workflow Builder & Execution

#### Building a Workflow

```python
from agent_framework import WorkflowBuilder

processor = DataProcessor()
validator = Validator()
formatter = Formatter()

builder = WorkflowBuilder(start_executor=processor)
builder.add_edge(processor, validator)
builder.add_edge(validator, formatter)
workflow = builder.build()
```

#### Running — Non-Streaming

```python
events = await workflow.run(input_message)
print(f"Final result: {events.get_outputs()}")
```

#### Running — Streaming

```python
async for event in workflow.run(input_message, stream=True):
    if event.type == "output":
        print(f"Workflow completed: {event.data}")
```

#### Workflow Validation (automatic at `build()`)

- **Type Compatibility** — ensures message types match between connected executors
- **Graph Connectivity** — verifies all executors are reachable from the start
- **Executor Binding** — confirms all executors are properly bound
- **Edge Validation** — checks for duplicate or invalid connections

#### Execution Model: Supersteps (BSP)

The framework uses a modified **Pregel / Bulk Synchronous Parallel** model:

```
Superstep N:
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Collect All    │───▶│  Route Messages │───▶│  Execute All    │
│  Pending        │    │  Based on Type  │    │  Target         │
│  Messages       │    │  & Conditions   │    │  Executors      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                       │
                                              (barrier: wait for all)
┌─────────────────┐    ┌─────────────────┐             │
│  Start Next     │◀───│  Emit Events &  │◀────────────┘
│  Superstep      │    │  New Messages   │
└─────────────────┘    └─────────────────┘
```

Key properties:
- **Synchronization barrier** between supersteps — all executors in a superstep must finish before the next one starts.
- **Deterministic execution** — same input → same execution order.
- **Reliable checkpointing** — state saved at superstep boundaries.
- **Tip**: if you need truly independent parallel paths, consolidate sequential steps into a single executor.

---

## Agents in Workflows

AI agents can be used as executors inside workflows via `AgentExecutor` or directly via `client.as_agent()`.

### Using OpenAI Chat Client

```python
from agent_framework import AgentExecutor, AgentExecutorRequest, Message
from agent_framework.openai import OpenAIChatCompletionClient
from pydantic import BaseModel

class DetectionResult(BaseModel):
    is_spam: bool
    reason: str
    email_content: str

chat_client = OpenAIChatCompletionClient(
    model=os.environ["AZURE_OPENAI_CHAT_COMPLETION_MODEL"],
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    credential=AzureCliCredential(),
)

spam_agent = AgentExecutor(
    chat_client.as_agent(
        instructions="You are a spam detection assistant.",
        response_format=DetectionResult,
    ),
    id="spam_detection_agent",
)
```

### Using Azure Foundry Client

```python
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential

client = FoundryChatClient(
    project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
    model=os.environ["FOUNDRY_MODEL"],
    credential=AzureCliCredential(),
)

writer_agent = client.as_agent(
    name="Writer",
    instructions="You are an excellent content writer.",
)

reviewer_agent = client.as_agent(
    name="Reviewer",
    instructions="You are an excellent content reviewer.",
)

workflow = (
    WorkflowBuilder(start_executor=writer_agent)
    .add_edge(writer_agent, reviewer_agent)
    .build()
)
```

### Streaming Agent Responses

```python
from agent_framework import AgentResponseUpdate

async for event in workflow.run("Write a slogan for an electric SUV.", stream=True):
    if event.type == "output" and isinstance(event.data, AgentResponseUpdate):
        update = event.data
        print(f"{update.author_name}: {update.text}", end="", flush=True)
```

---

## State Management

### Writing & Reading Shared State

```python
import uuid

class FileReadExecutor(Executor):

    @handler
    async def handle(self, file_path: str, ctx: WorkflowContext[str]):
        with open(file_path, 'r') as f:
            content = f.read()
        file_id = str(uuid.uuid4())
        ctx.set_state(file_id, content)
        await ctx.send_message(file_id)


class WordCountingExecutor(Executor):

    @handler
    async def handle(self, file_id: str, ctx: WorkflowContext[int]):
        content = ctx.get_state(file_id)
        if content is None:
            raise ValueError("File content state not found")
        await ctx.send_message(len(content.split()))
```

### Workflow-Scoped Runtime kwargs

Pass values to agents/tools without polluting shared state:

```python
# Global — every executor receives the same dict
await workflow.run(
    "Create the report",
    function_invocation_kwargs={
        "tenant": "contoso",
        "request_id": "req-42",
    },
)

# Per-executor targeting — each gets only its own entry
await workflow.run(
    "Create the report",
    function_invocation_kwargs={
        "researcher": {"db_config": {"connection_string": "..."}},
        "writer": {"user_preferences": {"format": "markdown"}},
    },
)
```

### State Isolation Best Practice

Always wrap executor + workflow creation in a helper to avoid state leaks between runs:

```python
def create_workflow() -> Workflow:
    executor_a = CustomExecutorA()
    executor_b = CustomExecutorB()
    return (
        WorkflowBuilder(start_executor=executor_a)
        .add_edge(executor_a, executor_b)
        .build()
    )

# Each invocation gets independent state
workflow_a = create_workflow()
workflow_b = create_workflow()
```

---

## Human-in-the-Loop (HITL)

Executors can pause and request external input (human or API) via `ctx.request_info()`.

### Defining a HITL Executor

```python
from dataclasses import dataclass
from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler, response_handler

@dataclass
class NumberSignal:
    hint: str  # "init", "above", or "below"

class JudgeExecutor(Executor):
    def __init__(self, target_number: int):
        super().__init__(id="judge")
        self._target_number = target_number
        self._tries = 0

    @handler
    async def handle_guess(self, guess: int, ctx: WorkflowContext[int, str]) -> None:
        self._tries += 1
        if guess == self._target_number:
            await ctx.yield_output(f"{self._target_number} found in {self._tries} tries!")
        elif guess < self._target_number:
            await ctx.request_info(request_data=NumberSignal(hint="below"), response_type=int)
        else:
            await ctx.request_info(request_data=NumberSignal(hint="above"), response_type=int)

    @response_handler
    async def on_human_response(
        self, original_request: NumberSignal, response: int,
        ctx: WorkflowContext[int, str],
    ) -> None:
        await self.handle_guess(response, ctx)
```

### Consuming Requests and Sending Responses

```python
async def process_event_stream(stream):
    requests = []
    async for event in stream:
        if event.type == "request_info":
            requests.append((event.request_id, event.data))
    if requests:
        responses = {}
        for request_id, request in requests:
            guess = int(input(f"Guess ({request.hint}): "))
            responses[request_id] = guess
        return responses
    return None

# Run loop
stream = workflow.run(25, stream=True)
pending = await process_event_stream(stream)

while pending is not None:
    stream = workflow.run(stream=True, responses=pending)
    pending = await process_event_stream(stream)
```

---

## Installation & Prerequisites

| Requirement | Value |
|---|---|
| **Python** | 3.10+ |
| **Package** | `pip install agent-framework-core` |
| **Azure OpenAI** | Endpoint + deployment configured |
| **Authentication** | `az login` (AzureCliCredential) |

Environment variables (example):

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_CHAT_COMPLETION_MODEL=gpt-4o-mini
AZURE_OPENAI_API_VERSION=2024-12-01-preview
# Or for Foundry:
FOUNDRY_PROJECT_ENDPOINT=https://your-project.services.ai.azure.com/api
FOUNDRY_MODEL=gpt-4o
```

---

## Quick Reference Cheat Sheet

```python
from agent_framework import (
    Executor,               # Base class for executors
    WorkflowBuilder,        # Builds the workflow graph
    WorkflowContext,        # Context passed to handlers
    WorkflowEvent,          # Event class for streaming
    AgentExecutor,          # Wraps an AI agent as executor
    AgentExecutorRequest,   # Request message for agent executors
    AgentExecutorResponse,  # Response from agent executors
    Message,                # Chat message type
    Case,                   # Switch-case routing
    Default,                # Default case
    handler,                # Decorator for handler methods
    executor,               # Decorator for function-based executors
    response_handler,       # Decorator for HITL response handlers
)

# 1. Build
workflow = (
    WorkflowBuilder(start_executor=exec_a)
    .add_edge(exec_a, exec_b)
    .add_edge(exec_b, exec_c, condition=my_predicate)
    .build()
)

# 2. Run (non-streaming)
result = await workflow.run(input_data)
outputs = result.get_outputs()

# 3. Run (streaming)
async for event in workflow.run(input_data, stream=True):
    if event.type == "output":
        print(event.data)
```

---

## Further Resources

| Resource | Link |
|---|---|
| Official docs | [learn.microsoft.com/en-us/agent-framework/workflows/](https://learn.microsoft.com/en-us/agent-framework/workflows/) |
| Python samples | [github.com/.../python/samples/03-workflows](https://github.com/microsoft/agent-framework/tree/main/python/samples/03-workflows) |
| Executors | [Executors docs](https://learn.microsoft.com/en-us/agent-framework/workflows/executors) |
| Edges | [Edges docs](https://learn.microsoft.com/en-us/agent-framework/workflows/edges) |
| Events | [Events docs](https://learn.microsoft.com/en-us/agent-framework/workflows/events) |
| Workflow Builder | [Workflows docs](https://learn.microsoft.com/en-us/agent-framework/workflows/workflows) |
| Agents in Workflows | [Agents docs](https://learn.microsoft.com/en-us/agent-framework/workflows/agents-in-workflows) |
| State Management | [State docs](https://learn.microsoft.com/en-us/agent-framework/workflows/state) |
| Human-in-the-Loop | [HITL docs](https://learn.microsoft.com/en-us/agent-framework/workflows/human-in-the-loop) |
| Checkpoints | [Checkpoints docs](https://learn.microsoft.com/en-us/agent-framework/workflows/checkpoints) |
| Observability | [Observability docs](https://learn.microsoft.com/en-us/agent-framework/workflows/observability) |
