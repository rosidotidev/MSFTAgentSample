"""Executor: reads source files in parallel and extracts structured data via SourceReaderAgent."""

from __future__ import annotations

import asyncio
import json
import os

from agent_framework import Executor, handler, WorkflowContext

from ..agents import source_reader


class BatchReaderExecutor(Executor):
    """Reads all new files concurrently (with semaphore) and produces extractions."""

    def __init__(self, client, options, concurrency: int = 3):
        super().__init__(id="batch_reader")
        self._client = client
        self._options = options
        self._concurrency = concurrency

    @handler
    async def handle(self, input: str, ctx: WorkflowContext[str]) -> None:
        data = json.loads(input)
        new_files: list[str] = data.get("new_files", [])
        if not new_files:
            print("No files to read.")
            await ctx.send_message(json.dumps({"extractions": []}))
            return

        agent = source_reader.create_agent(self._client, self._options)
        semaphore = asyncio.Semaphore(self._concurrency)
        extractions: list[dict] = []

        async def read_one(file_path: str):
            async with semaphore:
                fname = os.path.basename(file_path)
                print(f"Reading: {fname}")
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                prompt = f"FILE: {fname}\n\n{content}"
                result = await agent.run(prompt)

                # Parse JSON from agent response
                text = result.text
                # Strip markdown fences if present
                text = text.strip()
                if text.startswith("```"):
                    text = "\n".join(text.split("\n")[1:])
                if text.endswith("```"):
                    text = text[: text.rfind("```")]
                text = text.strip()

                extraction = json.loads(text)
                extraction["_source_path"] = file_path
                # Tag origin so Integrator knows where it came from
                if "questions_approved" in file_path.replace("\\", "/"):
                    extraction["_origin"] = "questions_approved"
                else:
                    extraction["_origin"] = "raw"
                return extraction

        tasks = [read_one(fp) for fp in new_files]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, r in enumerate(results):
            if isinstance(r, Exception):
                print(f"ERROR reading {new_files[i]}: {r}")
            else:
                extractions.append(r)

        print(f"Batch read complete: {len(extractions)} extraction(s).")
        await ctx.send_message(json.dumps({"extractions": extractions}))
