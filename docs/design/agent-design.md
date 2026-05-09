# Agent Design & Orchestration

## Core Agents

### Interaction Agent
Collects user task, experience level, and preferences.

### Repository Ingestion Agent
Fetches repository structure, README, and documentation.

### Code Structure Agent
Builds a conceptual map of modules and dependencies.

### Documentation Agent
Summarizes relevant docs and comments.

### Task Mapping Agent
Links the user task to relevant code components.

### Pedagogical Agent
Creates a learning-oriented onboarding plan.

### Prioritization Agent
Orders steps by importance and dependency.

---

## Orchestrator Agent
- Controls agent execution flow
- Determines which agents to activate
- Aggregates outputs into a coherent plan
- Handles iterative refinement

---

## Example Flow
User Task → Orchestrator → Agents → Onboarding Plan → User Feedback
