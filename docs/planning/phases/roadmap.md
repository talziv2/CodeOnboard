# CodeOnboard — End-to-End Roadmap

## What this system does

A developer pastes a GitHub repo URL and describes their goal. CodeOnboard analyzes the codebase, extracts its structure, and generates a personalized step-by-step learning path — what to read, in what order, and why — calibrated to that developer's experience level and time. Each step links to real files and line ranges. In later phases, each step has audio narration and a short code walkthrough video.

---

## System layers

```
User
  │
  ▼
Layer 1 — UI (Next.js)
  Goal dialogue, learning path display,
  audio player + video player (Phase 4)
  │
  │ REST API
  ▼
Layer 2 — Backend (FastAPI)
  /goal, /onboard, /status endpoints
  Session management
  │
  ▼
Layer 3 — Orchestrator
  Phase 1: plain Python chain (runner.py)
  Phase 2+: LangGraph stateful graph
  │
  ├─── Phase 1 Agents          ├─── Phase 2 Agents
  │    Goal                    │    Documentation
  │    Code Structure           │    Prioritization
  │    Mentor                   │
  │
  ▼
Layer 4 — RAG pipeline
  Clone → AST chunk → embed → store → retrieve
  ChromaDB + nomic-embed-text-v1.5 (local, via sentence-transformers)
  │
  ▼
Layer 5 — LLM (Anthropic API)
  Haiku for loops, Sonnet for final synthesis
```

---

## Full agent roster

| Agent | Phase | Role | Model |
|---|---|---|---|
| Goal Agent | 1 | Dialogue → structured goal JSON | Haiku |
| Code Structure Agent | 1 | Clone + parse → module map + RAG store | Haiku |
| Mentor Agent | 1–2 | Goal + map + RAG → learning path (retired in Phase 3) | Sonnet |
| Documentation Agent | 2 | Extract README/docstrings, enrich steps / feed Teaching Agent | Haiku |
| Prioritization Agent | 2 | Filter irrelevant modules for the goal | Haiku |
| Planner Agent | 3 | Owns the learning graph; generates and mutates it from goal + signals | TBD |
| Teaching Agent | 3 | Expands a learning node into an actual lesson (walkthrough, examples, prompts) | TBD |
| Grader Agent | 3 | Classifies user responses (understood / partial / confused / off-topic) | Haiku |
| Multimedia Agent | 4 | Learning path text → TTS audio + video | External APIs |

---

## Phase 1 — Core pipeline

**Detail:** [`docs/planning/phases/phase1.md`](phase1.md)

**Goal:** Working end-to-end pipeline on one real repo before anything else.

- Goal Agent → Code Structure Agent → Mentor Agent
- Stack: Python + FastAPI + ChromaDB + sentence-transformers (nomic) + Anthropic API
- Output: JSON learning path with file + line references
- UI: repo URL input + goal dialogue + step list display

**Done when:**
- POST /onboard on `psf/requests` returns a coherent 5–8 step learning path
- Steps reference real files and line ranges that exist in the repo
- Works on `fastapi/fastapi` without breaking
- Token cost under $0.10/run

---

## Phase 2 — Quality and richness

**Prerequisite:** Phase 1 done and tested on both target repos

### Documentation Agent
- Extracts README, module-level docstrings, inline comments
- Aligns extracted content with the Phase 1 code map
- Enriches each learning step with real quotes from the codebase — not LLM-generated summaries
- Why: Phase 1 steps explain structure; Phase 2 steps explain *meaning*

### Prioritization Agent
- Takes full module map + goal, decides what to skip
- Critical for large repos — fastapi has 50+ modules, most irrelevant for most goals
- Runs before Mentor Agent, hands it a filtered map
- Side effect: reduces Sonnet input token count → saves budget + improves output quality

### LangGraph migration ✅ done
- `backend/pipeline/runner.py` keeps its public signature; internals delegate
  to a compiled LangGraph (`backend/pipeline/graph.py`)
- Three nodes: `code_structure` → (conditional) → `prioritization` → `mentor`
- Conditional edge after `code_structure` routes to END when no `module_map`
  (preserves the Phase 1 short-circuit)
- `OnboardState.errors` uses an `operator.add` reducer so parallel nodes can
  append safely (unblocks the Documentation Agent below)
- Existing `tests/test_runner.py` passes unchanged; new `tests/test_graph.py`
  covers routing, mocked invocation, and the errors-reducer behaviour

### Confidence indicator
- Surface to user: "Good README + inline docs (high)" vs "sparse comments only (medium)"
- Derived from Documentation Agent output

**Done when:**
- Learning path steps include direct quotes from actual docstrings/README
- Irrelevant modules are filtered for focused goals
- LangGraph graph replaces runner.py with no regression on Phase 1 tests

---

## Phase 3 — Interactive learning graph

**Prerequisite:** Phase 2 done

This phase shifts the system from a static 5–8 step path to an **interactive, adaptive learning session**. The current Mentor Agent is retired and its responsibilities split across three new roles. The goal feel is *tutor*, not *documentation tour*.

The product centerpiece is the **user's understanding graph**: a persistent, repo-anchored map of what *this* user understands about *this* codebase. The Planner's internal learning graph and the user's understanding graph are the same object — the graph is surfaced to the user as the centerpiece artifact, not hidden inside the agent. This is the project's X-factor.

### Conceptual shift: lesson brief ≠ lesson
- The step JSON (title / file / line_range / why / understand / concepts) becomes the **lesson brief** — a planning artifact and a node in the learning graph.
- A separate Teaching Agent expands the brief into the actual lesson at delivery time, conditioned on session state.
- The same brief can be delivered as a high-level tour, a deep walkthrough, a simplified recap, or a prerequisite-first detour.

### The learning graph
- Initial graph generated from goal + prioritized module map.
- Mutates during the session: nodes added (prerequisites, deeper sub-topics), removed (skipped areas), reordered, or split into finer sub-nodes.
- Session state persists: visited nodes, demonstrated understanding, weak areas, skipped areas, requested depth level, learning preferences.

### Three new roles
- **Planner Agent** — owns the graph; decides what to teach next based on session state and signals.
- **Teaching Agent** — turns a node into an actual lesson (walkthrough, explanation, examples, architectural context, simplified explanations, active-learning prompts, "what to pay attention to," connections to prior concepts).
- **Grader Agent** — classifies user responses to active-learning prompts: understood / partial / confused / off-topic.

### The user's understanding graph (centerpiece artifact)

Same data structure as the Planner's learning graph — but persisted across sessions and surfaced to the user as the product's centerpiece.

**Node fields (MVP):**
- code anchor (file + line range)
- concept tags
- understanding state: `not-yet` / `partial` / `understood` (driven by Grader)
- coverage flag (visited / not)
- weak-spot flag (Grader marked the user as `confused` here)
- optional self-confidence (user-reported)

**Derived overlay:** one readiness gauge — `understood_count / goal_relevant_count`. Heuristic, not rigorous; communicates progress without overclaiming.

**Behaviors:**
- Persists per (user, repo) across sessions; users return to *their* graph.
- User can override the model on the graph itself (mark understood / weak / skip).
- On return, the system uses the graph to choose the resume point.

**Deliberately *not* in v1:** team-shared graphs, multi-user collaboration, repo dependency overlays, exportable reports. Single local user, repo-anchored, that's it.

### Signals the graph reacts to
Explicit (user-driven): understood, partially understood, confused, wants deeper explanation, wants examples, wants to skip, wants implementation details, wants higher-level architecture first.
Implicit (Grader-derived): understood / partial / confused / off-topic from free-text responses.

### Deferred decisions (intentionally open until designed)
- Specific active-learning prompt forms (predict-then-reveal / free-text recall / multiple-choice / find-this-function / something else).
- Concrete agent prompts and graph mutation rules.
- `OnboardState` extensions for session continuity.
- API shape: per-step endpoint, session lifecycle, persistence.
- Budget rethink: how the single-Sonnet rule changes when Mentor splits into three loop-driven roles.
- Staging order — smallest first cut toward this vision.
- Understanding-graph persistence layer (SQLite vs. JSON vs. something else) and identity model (anonymous local-only vs. login).
- Graph UI library (`react-flow` / `cytoscape` / `vis-network`) and layout strategy.

**Done when:**
- A user can run an onboarding session that streams one lesson at a time, sends signals (got it / deeper / confused / skip / etc.), and the next lesson is conditioned on those signals.
- Free-text responses are graded and the classification influences the next lesson.
- The graph demonstrably mutates during a session on at least one target repo.
- The user's understanding graph persists across sessions: closing the app and returning loads the same graph, in the same state, with the system able to suggest a sensible resume point.
- The graph is visible to the user as the central UI artifact — not hidden inside the agent.

---

## Phase 4 — Multimedia

**Prerequisite:** Phase 3 done

### Audio narration (TTS)
- Each learning step text → ElevenLabs TTS API → MP3
- Stored at `data/audio/{session_id}/step_{n}.mp3`
- Served via FastAPI static files
- UI: audio player in each step card

### Code walkthrough video
- Puppeteer renders the referenced file + highlights the relevant line range
- ffmpeg merges rendered frames + audio → MP4 per step (~30–60 seconds)
- Stored at `data/video/{session_id}/step_{n}.mp4`
- UI: video player in each step card

**Risk:** Puppeteer + ffmpeg pipeline is the most technically uncertain part of the project. TTS alone (without video) is already a strong differentiator.

**Done when (minimum):** Audio narration works for all steps  
**Done when (stretch):** Video walkthrough works for single-file steps

---

## Phase 5 — VS Code extension

**Prerequisite:** Phase 1–3 solid

### What it does
- Sidebar panel showing the current learning step
- Clicking a step opens the referenced file and highlights the exact lines
- Inline Q&A: ask questions about highlighted code without leaving the IDE
- Progress tracking: mark steps complete

### Architecture
- VS Code extension (TypeScript) ↔ FastAPI backend via REST
- Extension stores session state locally (current step, completed steps)
- Q&A uses a new `POST /ask` endpoint: highlighted code + question → Haiku answers in context

**Risk:** Most impressive demo feature, most work. Phases 1–2 must be fully solid before starting.

---

## Tech stack

| Component | Tool | Notes |
|---|---|---|
| Language | Python 3.12 | |
| Package manager | uv | Faster than pip, better lockfile |
| Backend | FastAPI | |
| Orchestrator | Plain Python → LangGraph (Phase 2) | Migrate only when branching is needed |
| LLM | Anthropic API | Haiku for loops, Sonnet for synthesis |
| Embeddings | `nomic-ai/nomic-embed-text-v1.5` via sentence-transformers | Runs locally, no API key, ~550 MB one-time download |
| Vector store | ChromaDB (local) | Free, no infra needed |
| Code parser | tree-sitter | AST-based, language-aware |
| UI | Next.js + Tailwind | |
| TTS (Phase 4) | ElevenLabs | Free tier: 10k chars/month |
| Video (Phase 4) | Puppeteer + ffmpeg | Free, self-hosted |
| IDE (Phase 5) | VS Code Extension API | TypeScript |

---

## Demo day target

1. Paste `https://github.com/psf/requests`, say "I want to understand how authentication works"
2. System runs (~20–30 seconds), returns a 6-step learning path
3. Each step: title, file link, line range, explanation, (Phase 2) docstring quote, (Phase 4) audio narration
4. Repeat with `fastapi/fastapi` to show it scales
5. (Stretch) Open VS Code, show extension highlighting the exact lines

---

## Risks

| Risk | Mitigation |
|---|---|
| tree-sitter setup complexity | Start Python only; add languages one at a time |
| Large repos hit token limits | Limit Code Structure Agent to top-level files first; go deeper on retrieval |
| Phase 4 video pipeline too complex | Ship TTS only if time is short |
| LangGraph migration breaks Phase 1 | Keep runner.py working; migrate with tests |
| ElevenLabs API changes (Phase 4) | Wrap behind thin adapter functions so swapping is one-file change |
