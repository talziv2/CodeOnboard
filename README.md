# CodeOnBoard

## Overview
CodeOnBoard is an AI-powered system designed to help developers onboard into unfamiliar open-source codebases efficiently.  
Instead of reading documentation passively, users specify a **task or goal**, and the system generates a **guided, step-by-step onboarding plan** tailored to that task.

The project focuses on **code understanding, learning, and contribution readiness**, rather than code generation.

---

## Motivation
Modern open-source projects are large, modular, and difficult to approach for newcomers.  
Existing tools optimize productivity for experienced developers but do not address the onboarding and learning phase.

CodeOnBoard aims to reduce:
- Time-to-understand a codebase
- Cognitive overload for new contributors
- Trial-and-error during onboarding

---

## Initial Target Repositories
The following repositories are used for scoping, experimentation, and demo:

- **FastAPI** – large, modular Python framework (https://github.com/fastapi/fastapi)
- 
- **Requests** – mature and compact Python library (https://github.com/psf/requests)

These provide a contrast between complex and lightweight architectures.

---

## Core Capabilities
- Task-driven onboarding
- Repository-aware reasoning (code + docs)
- Multi-agent orchestration
- Structured learning plans
- Interactive guidance

---

## High-Level Architecture
- Web UI (Next.js)
- Backend API (FastAPI)
- GitHub connector — shallow clone of a public repository
- Deterministic code index — tree-sitter AST → files, symbols, exact line ranges
- Budgeted exploration loop over that index
- Agent orchestrator (LangGraph)
- LLM provider (Anthropic)

There is no retrieval layer, no embedding model and no vector store. Repository
understanding is parsing plus tool-driven exploration; every citation resolves
against the repository itself, so a hallucinated line range is structurally
impossible.

---

## Roadmap
1. Repository ingestion & indexing
2. Task interpretation
3. Multi-agent orchestration
4. Learning plan generation
5. Interactive onboarding loop
6. Evaluation & demo

---

## Tech Stack
- Python 3.11+ with [uv](https://docs.astral.sh/uv/)
- FastAPI + uvicorn
- Anthropic API (claude-haiku-4-5, claude-sonnet-4-6)
- LangGraph (agent orchestration)
- tree-sitter (AST parsing)
- SQLite — one local file holding learning graphs, sessions and accounts
- Next.js + Tailwind (frontend)

---

## Running it

CodeOnboard is **self-hosted and local-first**: the backend, the frontend and
the database all run on your own machine, and it calls Claude with your own
Anthropic API key.

**→ [RUN.md](RUN.md) is the full setup guide.**

The short version:

```bash
uv sync
cp .env.example .env          # then paste your ANTHROPIC_API_KEY into it
cd frontend && npm install && cd ..
```

Then, in two terminals:

```bash
uv run uvicorn backend.api:app --reload    # terminal 1 — http://localhost:8000
```
```bash
cd frontend && npm run dev                 # terminal 2 — http://localhost:3000
```

Open <http://localhost:3000>. The database is created for you on first use —
there is no migration or seeding step.

**Prerequisites:** Python 3.11+, uv, Node.js 18.18+, and `git` on your `PATH`
(the backend shells out to it to clone the repository you want to learn).

---

## License

[MIT](LICENSE) — © 2026 Shira Zakov and Tal Ziv.
