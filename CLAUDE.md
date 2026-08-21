# CodeOnboard

AI-powered codebase onboarding. User provides a GitHub repo URL + goal → system generates a personalized, ordered learning path with file and line references.

This is a final-year CS project. Prefer working code over perfect architecture. Flag scope creep into later phases.

---

## Project phases

Full end-to-end roadmap: `docs/planning/phases/roadmap.md`

- **Phase 1:** Goal Agent → Code Structure Agent → Mentor Agent → FastAPI → minimal Next.js UI → see `docs/planning/phases/phase1.md`
- **Phase 2:** Documentation Agent, Prioritization Agent, LangGraph migration
- **Learning engine (current):** turn the code tour into a curriculum — see `docs/planning/phases/learning-engine.md`
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
    briefing/     # the welcome page's paragraph: survey + README + the learner's
                  #   profile → one Haiku call, cached on the session
    mentor/       # agent.py: wire format + LearningGraph construction + the
                  #   CODEONBOARD_CURRICULUM dispatch between the two planners
                  # curriculum.py: the objective-first planner (B3) — the model
                  #   over-generates objectives, our code cuts them to a journey
                  # dossier.py: the pre-B3 planner, still the default
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
POST /goal/back             → { question, answer }   un-answers the last question
POST /onboard               → { learning_path, module_map, confidence }
```

`/goal/back` un-answers exactly one question, so stepping back N questions is N
calls. It is the **only** way backwards, because the server owns the consequence:
crossing Q2 clears `goal_type`, which is what makes the follow-up tail recompute
instead of leaving the old goal type's questions queued.

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
  "code_depth": "working",
  "depth": "moderate",
  "time_available": "2 hours",
  "target_repo": "https://github.com/psf/requests"
}
```

`goal_type` values: `understand_system` | `understand_component` | `contribute_code` | `debug_issue`

`code_depth` values: `map` | `working` | `implementation` — how far into the
implementation the user asked to go. It is **elicited**, not inferred: it is the
one personalization dial worth an interview question, because scope and code
depth are independent (a broad shallow tour and a narrow deep dive are both
legitimate).

`depth` is **derived from `code_depth` in Python** (`map→overview`,
`working→moderate`, `implementation→deep`) and is never written by a model. It
was previously invented by Haiku from answers that never mentioned it, and it
decided how much got taught. `experience_level` was the same kind of invention
and has been removed — `familiarity` (fixed options) and `background` (free
text) are both genuinely elicited and carry the real signal.

---

## Learning path step schema

```json
{
  "step": 1,
  "title": "Understand the Session object",
  "file": "requests/sessions.py",
  "line_range": [1, 80],
  "objective": "Explain what Session owns that a bare request does not — connection reuse, cookie persistence, default configuration — and why sending through a Session changes behaviour",
  "why": "The Session object is the core abstraction — everything flows through it",
  "concepts": ["adapter pattern", "connection pooling"]
}
```

`objective` is the **contract between the Planner, Teaching and the Grader**: the
claim the learner should be able to make afterwards. Teaching is instructed to
build exactly it; the Grader marks against it rather than against the
`expected_answer` Teaching invented. Read it through `LearningNode.objective()`,
never straight off `lesson_brief` — that method holds the fallback to
`understand` which keeps graphs planned before the contract working.

`understand` is **not** emitted by the objective-first planner: it meant "what
the user should take away", which is what `objective` already is. It survives
only on pre-B1/B3 graphs, as `objective()`'s fallback.

---

## UI copy

The app is English-only. There is no locale selection, no translation layer, and
no per-request language plumbing — agents write prose in English because that is
the only language their prompts describe.

All user-facing wording lives in `frontend/lib/strings.ts`, imported directly as
`t` (plus `errorText`, which maps backend `detail` slugs like `session_not_found`
to a readable sentence). It is a plain module, not a React context: keeping copy
out of the components is a tidiness choice, not localization infrastructure.

**Model-authored prose is markdown, and is rendered as markdown.** Teaching is
asked for markdown in `setup` and `reveal` (`agents/teaching/agent.py`) and the
models deliver it throughout — bolded leads, backticked identifiers, numbered
steps, the occasional fence. Every such string goes through
`frontend/components/ui/Prose.tsx`: `Prose` for a block of prose, `InlineProse`
for a single line whose element the caller already styles (the pinned objective, a
gap's claim, the verdict headline — the clamp and the strike-through belong to the
caller). `frontend/lib/markdown.ts` is the parser: pure, returns nodes, never HTML,
so `dangerouslySetInnerHTML` never enters the picture. Two subset rules are
load-bearing and documented there — **`_` is never emphasis**, because
`line_start` and `__init__` are the vocabulary, and an **unclosed delimiter stays
literal**, because prose that half-parses is worse than prose that does not.

**Learner-written text is never markdown.** Attempt answers and check answers stay
`whitespace-pre-wrap` exactly as typed. Interpreting a learner's asterisk as
emphasis rewrites what they said, and the one place their own words appear is the
one place fidelity beats polish.

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

Optional flags:
```
CODEONBOARD_CURRICULUM=1   # objective-first planner (B3). Default 0 = pre-B3 planner
CODEONBOARD_GAPS=1         # gap model. Default 0. ON IN DEV ONLY — see below
```

**`CODEONBOARD_GAPS` is not data-collection-only.** As well as recording the
misconceptions an answer contains, it makes the Grader *derive* the scalar
`gap_kind` from those gaps — and that scalar is what `adaptation.decide()` uses
to choose the intervention (hint / re-teach / prerequisite / follow-up) and what
the Mutator's `Diagnosis` carries. A flag-on session can therefore receive a
different response than the same session flag-off. Measured direction: `gap_kind`
agreement 47–48/48 against a baseline of 45, `missing_prerequisite` 4/6 → 6/6.
Gaps are collected but never shown to the learner until gap-model M6 ships
verification — until then nothing can close one, so a displayed list could only
ever grow. Decided in `learning-graph.md` §11 OQ-4.

---

## Design decisions

- **LangGraph orchestration.** `run_pipeline(repo_url, goal, client)` delegates to one compiled `StateGraph`: `repo_survey` → `documentation` → `goal_investigation` → (conditional) `reviewer` → `mentor`. Conditional edges end the run when the skeleton or the dossier is missing, rather than fabricating a graph (D15). `OnboardState.errors` uses an `operator.add` reducer. The Anthropic client rides on `OnboardState.client` because LangGraph nodes receive only state.
- **No MCP yet.** Add it when 4+ agents share tools.
- **Goal Agent runs first, always.** Its output JSON is the single source of truth for all downstream agents.
- **The goal dialogue outlives its own completion.** `/goal/answer` used to delete the session the moment the goal was synthesised, because the client started the pipeline immediately. It no longer does: the UI shows the answers back and waits for the learner to confirm, and from that review any answer can be reopened — which is `/goal/back`, which needs the session. Retention is bounded (`_MAX_GOAL_SESSIONS`, oldest evicted first) because there is no "the learner closed the tab" signal to free them on. A dialogue lost to a restart or to that cap is **not** fatal: `/session/start` needs only the goal, which the client already holds, so starting still works and only editing is lost.
- **Mentor Agent is the only Sonnet call.** Everything upstream uses Haiku.
- **Curriculum size is decided by code, not by a prompt.** Under `CODEONBOARD_CURRICULUM=1` the planner is told to enumerate everything worth learning and is given no target number; `backend/agents/mentor/curriculum.py` then cuts by required-set closure, dependency closure, area coverage and a guard band. Overflow is demoted to `priority: optional` on the same spine, never discarded. Every sizing rule is a pure function, so it is testable without an API key — that is the point, not a side effect.
- **No source, no lesson.** Grounding is verified at plan time but *read* at lesson time, and the two can disagree. If **some** of a unit's anchors fail to load, Teaching degrades and teaches from the rest. If **all** of them fail, Teaching must **fail the lesson** — never render one. With no source the model has only the objective, and it will write a fluent, confident, entirely ungrounded lesson from it; nothing in the output looks wrong, which is why this is refused at the point of reading. See `learning-engine.md` §4.1.2.
- **`optional` means excluded from the default walk, not removed.** `/advance` steps over an optional unit, `resume_point()` skips it, the stop counter and `readiness()`'s denominator exclude it, and the rail collapses it — but it stays in the graph, in `path_order()`, and teaches and grades normally when reached from the rail. `optional` describes the *promised journey*, not the graph. A unit with no `priority` at all is **not** optional and stays on the walk. See `learning-engine.md` §6.3.
- **Progress is two measures, and neither is `completed / total`.** `backend/learning/progress.py` owns both. **Goal readiness** is evidence-weighted mastery of the `required` set — the planner's dependency-closed floor, which is by construction "the goal is not met without this". **Journey progress** is how much of the promised walk has been dealt with. Remedial warm-ups are excluded from *both* and reported as detours; `readiness()` delegates and the `readiness` wire key is retained as an alias for goal readiness. The invariant, tested in `tests/test_progress.py`: **goal readiness may fall only when evidence about the learner changes, never because the system changed the plan.** Before this, inserting a remedial prerequisite dropped the gauge from 0.50 to 0.33 — the system's decision to help looked like the learner losing ground. See `learning-graph.md` §5.
- **A learning unit is grounded by one *or more* verified anchors.** A flow crossing three files is anchored on all three. `nodes.file` / `line_start` / `line_end` hold a *derived display projection*; `lesson_brief["anchors"]` is the semantic truth. The invariant, asserted in tests and in the sanity script: the display columns always equal one member of `anchors`.
- **Interactive learning graph (Phase 3, future).** The current Mentor Agent will retire; its responsibilities split across a Planner Agent (owns and mutates the learning graph), a Teaching Agent (expands a node into the actual lesson), and a Grader Agent (classifies user responses). The current step JSON becomes the *lesson brief*, not the lesson itself. The Planner's learning graph is also the **user's understanding graph** — the same object, persisted across sessions and surfaced to the user as the product's centerpiece artifact (this is the project's X-factor). Strategic positioning: CodeOnboard complements AI code generation by training humans to understand, critique, and direct it — Grader scope expands to critique-of-AI-output tasks, and a new AI-Assisted Development Mode operationalizes this. See `docs/planning/phases/roadmap.md` for the full Phase 3 description and the deferred design decisions.
