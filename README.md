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
- Chat / Web UI
- Backend API
- GitHub Connector
- Code & Docs Parser
- Vector Store (RAG)
- Agent Orchestrator
- LLM Provider

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
- Python 3.14 + uv
- FastAPI + uvicorn
- Anthropic API (claude-haiku-4-5, claude-sonnet-4-6)
- nomic-embed-text-v1.5 via sentence-transformers (embeddings, runs locally)
- ChromaDB (vector store)
- tree-sitter (AST parsing)
- Next.js + Tailwind (frontend)

---

## Setup

### 1. Backend

```bash
# Install Python dependencies
uv sync

# Copy env file and fill in your keys
cp .env.example .env

# Run backend (exclude data/ to prevent false reloads when repos are cloned)
uv run uvicorn backend.api:app --reload 
```

Required env vars: `ANTHROPIC_API_KEY`, `GITHUB_TOKEN` (optional)

### 2. Frontend

```bash
# First time only — install Node dependencies
cd frontend && npm install

# Run frontend (in a separate terminal)
cd frontend && npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

> **Note:** `node_modules/` is gitignored. Run `npm install` after every fresh clone or pull.
> If you see `sh: next: command not found`, run `npm install` first.

### Running both together

You need **two terminals running at the same time**:
- Terminal 1: backend on `http://localhost:8000`
- Terminal 2: frontend on `http://localhost:3000`
