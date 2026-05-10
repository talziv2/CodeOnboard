# Code Structure Agent

The Code Structure Agent is the second step in the pipeline. It clones the target
repo, parses all Python files into AST chunks, embeds those chunks into a
per-commit ChromaDB collection, and calls Haiku once to produce a validated
module map describing the codebase's architecture.

---

## Files

```
backend/agents/code_structure/
    __init__.py      re-exports the public API (run, ModuleEntry)
    agent.py         run(), _embed_chunks(), _build_prompt(), _parse_module_map(), ModuleEntry
backend/rag/
    cloner.py        git clone --depth 1; parse_repo_url; get_commit_sha
    chunker.py       tree-sitter AST parse → list of chunk dicts
    embedder.py      nomic-embed-text-v1.5 wrapper (sentence-transformers)
    store.py         ChromaDB persistent client at data/chroma/
```

---

## What it does

1. **Clone** — `clone_repo(state.repo_url)` runs `git clone --depth 1`.
   If `data/repos/<name>` already exists, it skips the clone.
2. **Chunk** — `chunk_repo(repo_path)` walks all `.py` files and extracts
   functions, classes, and imports as chunk dicts via tree-sitter.
3. **Embed** — `_embed_chunks(state, chunks)` filters out import chunks, derives
   a per-commit collection name, and either skips (cache hit) or embeds via
   `embedder.embed_documents()` and writes to ChromaDB via `store.add_chunks()`.
   Sets `state.chunks_embedded = True` on success. Wrapped in its own
   try/except so embedding failures don't block the module-map step.
4. **Sample** — takes the first `MAX_CHUNKS = 80` non-import chunks (enough
   context for Haiku without hitting the token limit).
5. **Summarise** — sends the chunk list to Haiku with a prompt asking for a
   JSON module map. Parses and validates the response through `ModuleEntry`.
6. **Write** — stores the validated map as `state.module_map`.

---

## Embedding step

| Item | Value |
|---|---|
| Model | `nomic-ai/nomic-embed-text-v1.5` |
| Runtime | Local CPU via `sentence-transformers` (no API key) |
| Vector dim | 768 |
| Indexing prefix | `search_document: ` |
| Query prefix (used by Mentor Agent) | `search_query: ` |
| Vector store | ChromaDB persistent client at `data/chroma/` |
| Collection name | `{owner}_{repo}_{commit_sha[:12]}`, lowercased, non-alphanumeric → `_`, capped at 63 chars |
| Caching rule | If a collection with that name already exists, skip both embedding and store writes |

The first run downloads the nomic weights (~550 MB) from Hugging Face. After
that, the model is cached on disk and loaded once per process via
`@lru_cache(maxsize=1)`.

Each chunk is stored with metadata `{file, start_line, end_line, type, name,
language}` and an id of `{file}:{start_line}-{end_line}:{name}` so retrieval
results carry exact source coordinates.

---

## What Claude does

Claude is called **once**, with a list of `[TYPE] name — file (lines X–Y)` lines.
Its job is to group these into logical modules and describe each one's purpose,
key files, exports, and dependencies.

The response is validated entry-by-entry through `ModuleEntry` (Pydantic). Any
malformed or missing field raises an error that is caught and appended to
`state.errors` without crashing the process.

---

## ModuleEntry schema

Each key in `state.module_map` is a module name (without `.py`), with this shape:

```json
{
  "sessions": {
    "purpose": "Core abstraction managing persistent HTTP settings and sending requests",
    "key_files": ["requests/sessions.py"],
    "exports": ["Session", "PreparedRequest"],
    "dependencies": ["adapters", "auth", "models"]
  }
}
```

Validated by:

```python
class ModuleEntry(BaseModel):
    purpose: str
    key_files: list[str]
    exports: list[str]
    dependencies: list[str]
```

---

## Entry point

```python
from backend.agents.code_structure import run

state = run(state, client=anthropic.Anthropic())
# state.repo_path        → "data/repos/requests"
# state.module_map       → { "sessions": {...}, "auth": {...}, ... }
# state.chunks_embedded  → True if the ChromaDB collection was written or already cached
# state.errors           → [] on success; ["cloner failed: ..."] etc. on failure
```

`client` defaults to `None` — when omitted, the agent constructs one using
`ANTHROPIC_API_KEY` from the environment.

---

## RAG chunker output format

Each chunk produced by `chunker.py` has this shape:

```json
{
  "file": "requests/sessions.py",
  "start_line": 394,
  "end_line": 470,
  "type": "class",
  "name": "Session",
  "language": "python",
  "content": "class Session:\n    ..."
}
```

`type` is one of: `function` · `class` · `import`

Import chunks are excluded both from the LLM prompt (too noisy) and from the
embedding step (too short to carry meaning).

---

## Error handling

Each phase has its own try/except. Errors are appended to `state.errors`; the
agent only returns early on cloner or chunker failure (since later steps depend
on those outputs).

| Error prefix | Cause | Effect |
|---|---|---|
| `cloner failed:` | Network error or invalid repo URL during `git clone` | Returns early — module map and embeddings skipped |
| `chunker failed:` | tree-sitter parse error | Returns early |
| `embedding failed:` | sentence-transformers/ChromaDB error during `_embed_chunks` | Logged; module-map step still runs |
| `code_structure_agent LLM call failed:` | API error, malformed JSON, or `ModuleEntry` validation failure | Module map left as `None` |
