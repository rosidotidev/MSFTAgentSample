# Fan-Out Index Retrieval — Design Notes

## Problema

L'indice wiki viene iniettato per intero nel prompt. Con ~190 voci (~19k token) si è nella zona di rischio "lost in the middle". Oltre 300 voci la degradazione sarà misurabile.

## Idea

**Map-Reduce sul retrieval**: splittare l'indice in chunk da 30 item, invocare l'LLM in parallelo su ogni chunk per selezionare le pagine candidate, poi fare merge e de-duplicazione.

## Flusso

```
index.md (190+ voci)
       │
   parse + interleave round-robin per categoria
       │
   chunk da 30 item ciascuno (~7 chunk)
       │
   ┌───┼───┐───...
   ▼   ▼   ▼
 LLM  LLM  LLM   ← parallelo (asyncio.gather)
   │   │   │
   └───┼───┘
       ▼
  merge & rank (frequenza cross-chunk)
       ▼
  top-5 pagine → read_wiki_page()
       ▼
  LLM finale: risposta
```

## Threshold

| Voci nell'indice | Strategia |
|---|---|
| < 150 | Passaggio singolo (come oggi) |
| 150–500 | Fan-out chunk da 30 |
| > 500 | Fan-out + eventuale embedding sull'indice |

## Snippet: parser e chunker

```python
import re

def parse_index_items(index_text: str) -> list[str]:
    """Extract all wiki link lines from index."""
    return [line.strip() for line in index_text.splitlines()
            if re.match(r"\s*-\s*\[\[", line)]

def chunk_items(items: list[str], size: int = 30) -> list[list[str]]:
    """Split items into chunks of `size`."""
    return [items[i:i+size] for i in range(0, len(items), size)]
```

## Snippet: interleave round-robin per categoria

Evita che chunk consecutivi siano tutti della stessa categoria (es. solo entities A-K). Ogni chunk ha un mix di entities, concepts, sources.

```python
from itertools import zip_longest

def interleave_by_category(sections: dict[str, list[str]]) -> list[str]:
    """Round-robin across categories so each chunk has variety."""
    iterators = [iter(v) for v in sections.values()]
    result = []
    for group in zip_longest(*iterators):
        result.extend(item for item in group if item is not None)
    return result
```

## Snippet: fan-out parallelo

```python
import asyncio

CHUNK_THRESHOLD = 150  # sotto questa soglia, passaggio singolo

SELECT_PROMPT = """\
Given this question: "{question}"
Which of these wiki pages are most likely to contain the answer?
Return a JSON array of page paths, max 5. No explanation.

{chunk}
"""

async def select_pages_from_chunk(client, options, chunk: list[str], question: str) -> list[str]:
    """Ask LLM to pick relevant pages from a single chunk."""
    prompt = SELECT_PROMPT.format(
        question=question,
        chunk="\n".join(chunk),
    )
    # lightweight LLM call — ~200 token output
    result = await client.complete(prompt, options)
    import json
    try:
        return json.loads(result.text)
    except json.JSONDecodeError:
        return []

def merge_and_rank(results: list[list[str]], top_k: int = 5) -> list[str]:
    """Merge candidates, rank by cross-chunk frequency."""
    from collections import Counter
    counter = Counter()
    for candidate_list in results:
        for page in candidate_list:
            counter[page] += 1
    return [page for page, _ in counter.most_common(top_k)]

async def fan_out_select(client, options, index_text: str, question: str) -> list[str]:
    """Fan-out index selection across chunks if above threshold."""
    items = parse_index_items(index_text)
    if len(items) < CHUNK_THRESHOLD:
        return None  # fallback to single-pass
    
    # interleave before chunking
    # (assumes sections dict is available; simplified here)
    chunks = chunk_items(items, size=30)
    
    tasks = [
        select_pages_from_chunk(client, options, chunk, question)
        for chunk in chunks
    ]
    results = await asyncio.gather(*tasks)
    return merge_and_rank(results, top_k=5)
```

## Altre migliorie collegate (da valutare)

1. **Regola LANGUAGE nel system prompt di wiki_querier.py**: "search in English, answer in user's language"
2. **Alzare limite pagine da 3 a 5** (o 3 default + 2 on-demand)
3. **search_wiki**: aggiungere contesto (±2 righe), ranking per frequenza match nella pagina

## File coinvolti

- `wiki_llm_maf/main_query.py` — orchestrazione, qui va il threshold check e il fan-out
- `wiki_llm_maf/afw_core/agents/wiki_querier.py` — system prompt, regola LANGUAGE
- `wiki_llm_maf/afw_core/tools/wiki_search.py` — grep tool, migliorie ranking
