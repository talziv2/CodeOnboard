# Code Structure Agent

The Code Structure Agent is the second step in the pipeline. It clones the target
repo, parses all Python files into AST chunks, and calls Haiku once to produce a
validated module map that describes the codebase's architecture.

---

## Files

```
backend/agents/code_structure/
    __init__.py      re-exports the public API (run, ModuleEntry)
    agent.py         run(), _build_prompt(), _parse_module_map(), ModuleEntry
backend/rag/
    cloner.py        git clone --depth 1 into data/repos/<name>
    chunker.py       tree-sitter AST parse → list of chunk dicts
```

---

## What it does

1. **Clone** — calls `clone_repo(state.repo_url)` which runs `git clone --depth 1`.
   If `data/repos/<name>` already exists, it skips the clone.
2. **Chunk** — calls `chunk_repo(repo_path)` which walks all `.py` files and extracts
   functions, classes, and imports as individual chunk dicts via tree-sitter.
3. **Sample** — takes the first `MAX_CHUNKS = 80` non-import chunks (enough context
   for Haiku without hitting the token limit).
4. **Summarise** — sends the chunk list to Haiku with a prompt asking for a JSON
   module map. Parses and validates the response through `ModuleEntry`.
5. **Write** — stores the validated map as `state.module_map`.

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
# state.repo_path  → "data/repos/requests"
# state.module_map → { "sessions": {...}, "auth": {...}, ... }
# state.errors     → [] on success, ["cloner failed: ..."] etc. on failure
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

Import chunks are excluded from the prompt (too noisy) but are retained in the
full chunk list for the embedder (Phase 1 Part 3).

---

## Error handling

Errors are appended to `state.errors` and the agent returns early. The module map
is left as `None` so downstream agents can detect the failure.

| Error prefix | Cause |
|---|---|
| `cloner failed:` | Network error or invalid repo URL during `git clone` |
| `chunker failed:` | tree-sitter parse error on the cloned repo |
| `code_structure_agent LLM call failed:` | API error, malformed JSON, or `ModuleEntry` validation failure |
