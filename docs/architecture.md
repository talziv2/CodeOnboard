# High-Level System Architecture

## Components
- Chat / Web Interface
- Backend API
- GitHub Repository Connector
- Code & Documentation Parser
- Vector Database (RAG)
- Agent Orchestrator
- LLM Provider
- Session Memory

---

## Data Flow
1. User submits a task
2. Repository is parsed and indexed
3. Relevant information retrieved via RAG
4. Orchestrator activates agents
5. Agents generate a structured onboarding plan
6. User receives interactive guidance

---

## Design Principles
- Modular
- Scalable
- Repository-aware
- Learning-first

---

For the full end-to-end Mermaid diagram (all phases), see [`docs/diagram.md`](diagram.md).
