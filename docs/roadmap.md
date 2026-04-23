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
  audio player + video player (Phase 3)
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
  │    Pedagogical              │
  │
  ▼
Layer 4 — RAG pipeline
  Clone → AST chunk → embed → store → retrieve
  ChromaDB + Voyage AI voyage-code-2
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
| Pedagogical Agent | 1 | Goal + map + RAG → learning path | Sonnet |
| Documentation Agent | 2 | Extract README/docstrings, enrich steps | Haiku |
| Prioritization Agent | 2 | Filter irrelevant modules for the goal | Haiku |
| Multimedia Agent | 3 | Learning path text → TTS audio + video | External APIs |

---

## Phase 1 — Core pipeline

**Timeline:** Weeks 1–5  
**Detail:** `docs/phase1.md`

**Goal:** Working end-to-end pipeline on one real repo before anything else.

- Goal Agent → Code Structure Agent → Pedagogical Agent
- Stack: Python + FastAPI + ChromaDB + Voyage AI + Anthropic API
- Output: JSON learning path with file + line references
- UI: repo URL input + goal dialogue + step list display

**Done when:**
- POST /onboard on `psf/requests` returns a coherent 5–8 step learning path
- Steps reference real files and line ranges that exist in the repo
- Works on `fastapi/fastapi` without breaking
- Token cost under $0.10/run

---

## Phase 2 — Quality and richness

**Timeline:** Weeks 6–10  
**Prerequisite:** Phase 1 done and tested on both target repos

### Documentation Agent
- Extracts README, module-level docstrings, inline comments
- Aligns extracted content with the Phase 1 code map
- Enriches each learning step with real quotes from the codebase — not LLM-generated summaries
- Why: Phase 1 steps explain structure; Phase 2 steps explain *meaning*

### Prioritization Agent
- Takes full module map + goal, decides what to skip
- Critical for large repos — fastapi has 50+ modules, most irrelevant for most goals
- Runs before Pedagogical Agent, hands it a filtered map
- Side effect: reduces Sonnet input token count → saves budget + improves output quality

### LangGraph migration
- Replace `runner.py` with a LangGraph stateful graph
- Enables: conditional routing (e.g. skip Documentation Agent if repo has no README), retries on failure, parallel execution of Code Structure + Documentation agents
- Keep `runner.py` working; migrate incrementally with tests

### Confidence indicator
- Surface to user: "Good README + inline docs (high)" vs "sparse comments only (medium)"
- Derived from Documentation Agent output

**Done when:**
- Learning path steps include direct quotes from actual docstrings/README
- Irrelevant modules are filtered for focused goals
- LangGraph graph replaces runner.py with no regression on Phase 1 tests

---

## Phase 3 — Multimedia

**Timeline:** Weeks 11–14 (if time permits)  
**Prerequisite:** Phase 2 done

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

**Risk:** Puppeteer + ffmpeg pipeline is the most technically uncertain part of the project. If time is short, TTS alone (without video) is already a strong differentiator.

**Done when (minimum):** Audio narration works for all steps  
**Done when (stretch):** Video walkthrough works for single-file steps

---

## Phase 4 — VS Code extension

**Timeline:** Weeks 14–16 (stretch goal only)  
**Prerequisite:** Phase 1–2 solid, time available

### What it does
- Sidebar panel showing the current learning step
- Clicking a step opens the referenced file and highlights the exact lines
- Inline Q&A: ask questions about highlighted code without leaving the IDE
- Progress tracking: mark steps complete

### Architecture
- VS Code extension (TypeScript) ↔ FastAPI backend via REST
- Extension stores session state locally (current step, completed steps)
- Q&A uses a new `POST /ask` endpoint: highlighted code + question → Haiku answers in context

**Risk:** Most impressive demo feature, most work. Only prioritize if Phases 1–2 are fully solid.

---

## Timeline

```
Month 1   Phase 1 — Core pipeline (Weeks 1–5)
          Goal + CodeStructure + Pedagogical + FastAPI + Next.js UI

Month 2   Phase 2 — Quality and richness (Weeks 6–10)
          Docs Agent + Prioritization + LangGraph migration

Month 3   Phase 3 — Multimedia (Weeks 11–14, if time allows)
          TTS audio + code walkthrough video

          Phase 4 — VS Code extension (Weeks 14–16, stretch only)
```

---

## Tech stack

| Component | Tool | Notes |
|---|---|---|
| Language | Python 3.12 | |
| Package manager | uv | Faster than pip, better lockfile |
| Backend | FastAPI | |
| Orchestrator | Plain Python → LangGraph (Phase 2) | Migrate only when branching is needed |
| LLM | Anthropic API | Haiku for loops, Sonnet for synthesis |
| Embeddings | Voyage AI voyage-code-2 | Code-specific, free tier: 50M tokens/month |
| Vector store | ChromaDB (local) | Free, no infra needed |
| Code parser | tree-sitter | AST-based, language-aware |
| UI | Next.js + Tailwind | |
| TTS (Phase 3) | ElevenLabs | Free tier: 10k chars/month |
| Video (Phase 3) | Puppeteer + ffmpeg | Free, self-hosted |
| IDE (Phase 4) | VS Code Extension API | TypeScript |

---

## Demo day target

1. Paste `https://github.com/psf/requests`, say "I want to understand how authentication works"
2. System runs (~20–30 seconds), returns a 6-step learning path
3. Each step: title, file link, line range, explanation, (Phase 2) docstring quote, (Phase 3) audio narration
4. Repeat with `fastapi/fastapi` to show it scales
5. (Stretch) Open VS Code, show extension highlighting the exact lines

---

## Risks

| Risk | Mitigation |
|---|---|
| tree-sitter setup complexity | Start Python only; add languages one at a time |
| Large repos hit token limits | Limit Code Structure Agent to top-level files first; go deeper on retrieval |
| Phase 3 video pipeline too complex | Ship TTS only if time is short |
| LangGraph migration breaks Phase 1 | Keep runner.py working; migrate with tests |
| Voyage AI / ElevenLabs API changes | Wrap behind thin adapter functions so swapping is one-file change |
