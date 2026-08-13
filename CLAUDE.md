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
    goal/         # dialogue → goal JSON
    documentation/# README + docstrings → doc_context (no LLM)
    mentor/       # agent.py: wire format + LearningGraph construction
                  # dossier.py: plans the graph from the Investigation Dossier
                  # mutator.py: reshapes the graph on user/Grader signals
    reviewer/     # architectural review for goal types that need one
    teaching/     # one graph node → the lesson the user reads
    grader/       # classifies the user's answer
  repo/           # Layers A–C: repository understanding
    cloner.py     # git clone --depth 1
    parser.py     # tree-sitter → AST units with exact ranges  (Layer A)
    skeleton.py   # the deterministic file/symbol/import index (Layer A)
    anchors.py    # the grounding oracle: does this citation resolve?
    tools.py      # the six exploration primitives
    explore.py    # the budgeted agentic loop over those tools
    structure.py  # structural neighbours: prerequisite + lesson context
    survey.py     # Layer B: the goal-agnostic repository survey
    survey_store.py     # survey cache, keyed (repo, commit, schema)
    investigation.py    # Layer C: goal investigation → Dossier
    dossier_store.py    # Dossier persistence, keyed (session, commit, schema)
    dossier_context.py  # node-scoped slices of the Dossier
  pipeline/
    state.py      # OnboardState dataclass (shared state)
    graph.py      # LangGraph StateGraph — one shape
    runner.py     # public entry point: run_pipeline()
    explorer_nodes.py   # repo_survey + goal_investigation nodes
  learning/       # LearningGraph model and its SQLite store
  api.py          # FastAPI endpoints
frontend/         # Next.js
tests/
data/
  repos/          # cloned repos (gitignored)
  sessions.db     # learning graphs, dossiers, surveys (gitignored)
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
    repo_path: str                                   # set by repo_survey
    module_map: dict | None                          # set by repo_survey
    survey: dict | None                              # Layer B payload
    investigation: dict | None                       # the Dossier (D11)
    graph: LearningGraph | None                      # set by Mentor Agent
    learning_path: list | None                       # derived from the graph
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

## UI copy

The app is English-only. There is no locale selection, no translation layer, and
no per-request language plumbing — agents write prose in English because that is
the only language their prompts describe.

All user-facing wording lives in `frontend/lib/strings.ts`, imported directly as
`t` (plus `errorText`, which maps backend `detail` slugs like `session_not_found`
to a readable sentence). It is a plain module, not a React context: keeping copy
out of the components is a tidiness choice, not localization infrastructure.

Goal-interview questions are static strings in `backend/agents/goal/questions.py`
— shown verbatim rather than generated, so the interview never drifts.

Values that are *parsed* rather than read stay fixed keys: JSON keys,
`goal_type`, `depth`, `familiarity`, concept tags, edge kinds, and Grader
classifications. The frontend switches on those values, so they must not be
reworded. Only the displayed label is chosen, via `tagLabel` / `stateLabel`.

---

## LLM usage rules

- **`claude-haiku-4-5`** — Goal Agent dialogue, Code Structure Agent analysis, any loops
- **`claude-sonnet-4-6`** — Mentor Agent only (one call, final synthesis)
- Never use Sonnet in a loop. Never use Opus.
- Target: under $0.10/run. Budget: ~$7/month (~100 runs).

---

## Repository-understanding rules

There is no retrieval, no embedding model and no vector store. Stage 5 removed
them; see `docs/planning/phases/repo-understanding.md`.

- **Layer A is deterministic and model-free.** `parser.py` walks the AST with
  tree-sitter; `skeleton.py` indexes files, symbols (with exact line ranges) and
  imports. Never ask a model for something Layer A can compute.
- **Grounding is against the repository, not against evidence you were shown.**
  Every citation resolves through `anchors.resolve`. The model names a `file` +
  `symbol`; our code derives the line range, so a hallucinated range is
  structurally impossible.
- **One exploration loop.** `goal_investigation` is the only place the system
  explores. Teaching, the Mentor, the Reviewer and the Mutator read what it
  produced; none of them explores on its own.
- **Dossier first, Skeleton second.** Goal-specific understanding beats generic
  structure, but generic structure beats nothing — and both are grounded. This
  is the fallback order in Teaching and in the Mutator.
- **Python only, structurally.** The grammar, qualified-name rule, import
  resolution and public-API detection (package `__init__` re-exports) are all
  Python-specific. Adding a language means a sibling adapter, not a rewrite.

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

- **LangGraph orchestration.** `run_pipeline(repo_url, goal, client)` delegates to one compiled `StateGraph`: `repo_survey` → `documentation` → `goal_investigation` → (conditional) `reviewer` → `mentor`. Conditional edges end the run when the skeleton or the dossier is missing, rather than fabricating a graph (D15). `OnboardState.errors` uses an `operator.add` reducer. The Anthropic client rides on `OnboardState.client` because LangGraph nodes receive only state.
- **No MCP yet.** Add it when 4+ agents share tools.
- **Goal Agent runs first, always.** Its output JSON is the single source of truth for all downstream agents.
- **Mentor Agent is the only Sonnet call.** Everything upstream uses Haiku.
- **Interactive learning graph (Phase 3, future).** The current Mentor Agent will retire; its responsibilities split across a Planner Agent (owns and mutates the learning graph), a Teaching Agent (expands a node into the actual lesson), and a Grader Agent (classifies user responses). The current step JSON becomes the *lesson brief*, not the lesson itself. The Planner's learning graph is also the **user's understanding graph** — the same object, persisted across sessions and surfaced to the user as the product's centerpiece artifact (this is the project's X-factor). Strategic positioning: CodeOnboard complements AI code generation by training humans to understand, critique, and direct it — Grader scope expands to critique-of-AI-output tasks, and a new AI-Assisted Development Mode operationalizes this. See `docs/planning/phases/roadmap.md` for the full Phase 3 description and the deferred design decisions.
