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
- Voyage AI voyage-code-2 (embeddings)
- ChromaDB (vector store)
- tree-sitter (AST parsing)
- Next.js + Tailwind (frontend)

---

## Setup

```bash
# Install dependencies
uv sync

# Copy env file and fill in your keys
cp .env.example .env

# Run backend
uvicorn backend.api:app --reload

# Run frontend (Week 5+)
cd frontend && npm run dev
```

Required env vars: `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`, `GITHUB_TOKEN` (optional)
