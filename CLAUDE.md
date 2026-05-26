# CodeOnboard

AI-powered codebase onboarding. User provides a GitHub repo URL + goal → system generates a personalized, ordered learning path with file and line references.

This is a final-year CS project. Prefer working code over perfect architecture. Flag scope creep into later phases.

---

## Project phases

Full end-to-end roadmap: `docs/planning/phases/roadmap.md`

- **Phase 1:** Goal Agent → Code Structure Agent → Mentor Agent → FastAPI → minimal Next.js UI → see `docs/planning/phases/phase1.md`
- **Phase 2 (current):** Documentation Agent, Prioritization Agent, LangGraph migration
- **Phase 3:** Interactive learning graph — Mentor splits into Planner + Teaching + Grader; static path becomes an adaptive, stateful learning session
- **Phase 4:** TTS audio narration, code walkthrough video
- **Phase 5 (stretch):** VS Code extension

Do not implement later-phase features until the current phase works end-to-end on both target repos.

---

## Target demo repos

- `https://github.com/psf/requests` — small, clean, used for development
- `https://github.com/fastapi/fastapi` — large, used for stress testing

---

## Directory structure

```
backend/
  agents/
    goal_agent.py           # dialogue → goal JSON
    code_structure_agent.py # clone + parse → module map + RAG store
    mentor_agent.py         # goal + map + RAG → learning path
  pipeline/
    state.py                # OnboardState dataclass (shared state)
    graph.py                # LangGraph StateGraph: nodes, conditional edge, build_graph()
    runner.py               # public entry point: run_pipeline() invokes the compiled graph
  rag/
    cloner.py               # git clone --depth 1
    chunker.py              # tree-sitter → code chunks with metadata
    embedder.py             # nomic-embed-text-v1.5 via sentence-transformers
    store.py                # ChromaDB read/write
  tools/
    github.py               # GitHub REST API helpers
  api.py                    # FastAPI endpoints
frontend/                   # Next.js (added in Phase 1, Week 5)
tests/
data/
  chroma/                   # ChromaDB persistent store (gitignored)
  repos/                    # cloned repos temp storage (gitignored)
```

---

## Key API endpoints

```
POST /goal/start            → { session_id, first_question }
POST /goal/answer           → { next_question } | { goal: {...} }
POST /onboard               → { learning_path, module_map, confidence }
```

---

## Shared state

All agents read/write `OnboardState` (defined in `backend/pipeline/state.py`). Never pass data between agents any other way.

```python
@dataclass
class OnboardState:
    repo_url: str
    goal: dict | None                                # set by Goal Agent
    repo_path: str                                   # set by Code Structure Agent
    module_map: dict | None                          # set by Code Structure Agent
    relevant_modules: list[str] | None               # set by Prioritization Agent
    chunks_embedded: bool                            # set by Code Structure Agent
    learning_path: list | None                       # set by Mentor Agent
    confidence: str                                  # "high" / "medium" / "low"
    errors: Annotated[list, operator.add]            # reducer: append, never replace
    client: anthropic.Anthropic | None               # carried through the graph
```

---

## Goal object schema

```json
{
  "primary_goal": "understand the request lifecycle",
  "goal_type": "understand_component",
  "focus_area": "routing and middleware",
  "experience_level": "intermediate",
  "depth": "deep",
  "time_available": "2 hours",
  "target_repo": "https://github.com/psf/requests"
}
```

`goal_type` values: `understand_system` | `understand_component` | `contribute_code` | `debug_issue`

---

## Learning path step schema

```json
{
  "step": 1,
  "title": "Understand the Session object",
  "file": "requests/sessions.py",
  "line_range": [1, 80],
  "why": "The Session object is the core abstraction — everything flows through it",
  "understand": "How Session stores state, how it builds requests, what adapters do",
  "concepts": ["adapter pattern", "connection pooling"]
}
```

---

## LLM usage rules

- **`claude-haiku-4-5`** — Goal Agent dialogue, Code Structure Agent analysis, any loops
- **`claude-sonnet-4-6`** — Mentor Agent only (one call, final synthesis)
- Never use Sonnet in a loop. Never use Opus.
- Target: under $0.10/run. Budget: ~$7/month (~100 runs).

---

## RAG pipeline rules

- Chunk by AST unit (function, class) via tree-sitter — never by arbitrary line windows
- Chunk metadata must include: `file`, `start_line`, `end_line`, `type`, `name`, `language`
- ChromaDB collection name: sanitized `{owner}_{repo}_{commit_sha[:12]}` (lowercased, non-alphanumeric → `_`); skip re-embedding if collection exists
- Embedding model: `nomic-ai/nomic-embed-text-v1.5` via `sentence-transformers` — runs locally, no API key. Apply `search_document: ` prefix when indexing and `search_query: ` prefix when searching.
- Phase 1: Python files only. Add languages one at a time.

---

## Dev commands

```bash
# Install dependencies
uv sync

# Run backend
uvicorn backend.api:app --reload

# Run tests
pytest tests/

# Run frontend (Phase 1 Week 5+)
cd frontend && npm run dev
```

---

## Environment variables

See `.env.example`. Required:
```
ANTHROPIC_API_KEY=
GITHUB_TOKEN=        # optional, increases rate limit
```

---

## Design decisions

- **LangGraph orchestration (Phase 2).** `runner.py` keeps its public `run_pipeline(repo_url, goal, client)` signature but delegates to a compiled `StateGraph` in `backend/pipeline/graph.py`. Three nodes: `code_structure` → (conditional) → `prioritization` → `mentor`. The conditional edge short-circuits to END when `module_map` is missing. `OnboardState.errors` uses an `operator.add` reducer so future parallel nodes (e.g. Documentation Agent) can append safely. The Anthropic client rides on `OnboardState.client` because LangGraph nodes only receive state — no extra args.
- **No MCP in Phase 1.** Agents call ChromaDB directly. Add MCP when 4+ agents share tools.
- **Goal Agent runs first, always.** Its output JSON is the single source of truth for all downstream agents.
- **Mentor Agent is the only Sonnet call.** Everything upstream uses Haiku.
- **Interactive learning graph (Phase 3, future).** The current Mentor Agent will retire; its responsibilities split across a Planner Agent (owns and mutates the learning graph), a Teaching Agent (expands a node into the actual lesson), and a Grader Agent (classifies user responses). The current step JSON becomes the *lesson brief*, not the lesson itself. The Planner's learning graph is also the **user's understanding graph** — the same object, persisted across sessions and surfaced to the user as the product's centerpiece artifact (this is the project's X-factor). See `docs/planning/phases/roadmap.md` for the full Phase 3 description and the deferred design decisions.
