# CodeOnboard

AI-powered codebase onboarding. User provides a GitHub repo URL + goal → system generates a personalized, ordered learning path with file and line references.

This is a final-year CS project. Prefer working code over perfect architecture. Flag Phase 2/3 scope creep.

---

## Project phases

Full end-to-end roadmap: `docs/planning/phases/roadmap.md`

- **Phase 1 (current):** Goal Agent → Code Structure Agent → Pedagogical Agent → FastAPI → minimal Next.js UI → see `docs/planning/phases/phase1.md`
- **Phase 2:** Documentation Agent, Prioritization Agent, LangGraph migration
- **Phase 3:** TTS audio narration, code walkthrough video
- **Phase 4 (stretch):** VS Code extension

Do not implement Phase 2+ features until Phase 1 works end-to-end on both target repos.

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
    pedagogical_agent.py    # goal + map + RAG → learning path
  pipeline/
    state.py                # OnboardState dataclass (shared state)
    runner.py               # sequential chain: calls agents in order
  rag/
    cloner.py               # git clone --depth 1
    chunker.py              # tree-sitter → code chunks with metadata
    embedder.py             # Voyage AI voyage-code-2
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
    goal: dict | None          # set by Goal Agent
    repo_path: str             # set by Code Structure Agent
    module_map: dict | None    # set by Code Structure Agent
    chunks_embedded: bool      # set by Code Structure Agent
    learning_path: list | None # set by Pedagogical Agent
    confidence: str            # "high" / "medium" / "low"
    errors: list
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
- **`claude-sonnet-4-6`** — Pedagogical Agent only (one call, final synthesis)
- Never use Sonnet in a loop. Never use Opus.
- Target: under $0.10/run. Budget: ~$7/month (~100 runs).

---

## RAG pipeline rules

- Chunk by AST unit (function, class) via tree-sitter — never by arbitrary line windows
- Chunk metadata must include: `file`, `start_line`, `end_line`, `type`, `name`, `language`
- ChromaDB collection key: `{owner}/{repo}@{commit_sha}` — skip re-embedding if exists
- Embedding model: `voyage-code-2` (Voyage AI)
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
VOYAGE_API_KEY=
GITHUB_TOKEN=        # optional, increases rate limit
```

---

## Design decisions

- **No LangGraph in Phase 1.** Plain Python function chain in `runner.py`. Migrate to LangGraph in Phase 2 when conditional branching is actually needed.
- **No MCP in Phase 1.** Agents call ChromaDB directly. Add MCP when 4+ agents share tools.
- **Goal Agent runs first, always.** Its output JSON is the single source of truth for all downstream agents.
- **Pedagogical Agent is the only Sonnet call.** Everything upstream uses Haiku.
- **Progressive output** (future): generate one learning step at a time with user checkpoint, not full path upfront.
