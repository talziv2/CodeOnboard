# Agent Design

Reference for how agents are structured, what patterns they follow, and how they
fit together. All Phase 1 agents live under `backend/agents/`.

---

## Shared conventions

Every agent follows the same contract:

| Convention | Detail |
|---|---|
| **Package layout** | Each agent is a sub-package: `agents/<name>/agent.py` + `agents/<name>/__init__.py` |
| **Entry point** | A single `run(state, client=None) → OnboardState` function |
| **State I/O** | Reads from and writes to `OnboardState` (defined in `backend/pipeline/state.py`) — never passes data between agents any other way |
| **LLM client** | Injected as a parameter (`client: anthropic.Anthropic \| None = None`), not instantiated at module level — keeps unit tests simple |
| **Output validation** | LLM responses are validated through a Pydantic `BaseModel` before being written to state |
| **Error handling** | Errors are appended to `state.errors` and the function returns early — never raises |
| **Model** | `claude-haiku-4-5` for all agents except Pedagogical (uses `claude-sonnet-4-6`) |

---

## Agents

### Goal Agent  `backend/agents/goal/`

Runs a short multi-turn dialogue with the user to understand why they are looking
at the repo. Calls Haiku **once** at the end to synthesise the full Q&A into a
structured `GoalOutput` Pydantic object.

- Input: `repo_url` from `OnboardState`
- Output: `state.goal` (validated `GoalOutput` dict)
- LLM calls: 1 (synthesis only)
- See [`docs/goal-agent.md`](../goal-agent.md) for full detail.

### Code Structure Agent  `backend/agents/code_structure/`

Clones the repo, parses all Python files into AST chunks (tree-sitter), and calls
Haiku once to summarise the module map. Validates each entry through a `ModuleEntry`
Pydantic model before writing to state.

- Input: `state.repo_url`
- Output: `state.repo_path`, `state.module_map`
- LLM calls: 1
- See [`docs/design/code-structure-agent.md`](code-structure-agent.md) for full detail.

### Pedagogical Agent  `backend/agents/pedagogical/`  _(Phase 1 Part 3 — pending)_

Turns the goal + module map + RAG results into an ordered learning path. The only
agent that uses `claude-sonnet-4-6` — called once.

- Input: `state.goal`, `state.module_map`, RAG retrieval
- Output: `state.learning_path`, `state.confidence`

---

## `backend/agents/__init__.py` — public surface

Re-exports the entry points callers need:

```python
from backend.agents import run_code_structure, start_session, process_answer
```

The pipeline runner (`backend/pipeline/runner.py`) imports from here, never from
individual agent sub-packages.

---

## Pipeline flow (Phase 1)

```
OnboardState
    │
    ▼
Goal Agent          → state.goal
    │
    ▼
Code Structure Agent → state.repo_path, state.module_map
    │
    ▼
Pedagogical Agent    → state.learning_path, state.confidence
    │
    ▼
FastAPI response     → { learning_path, module_map, confidence }
```

All three agents run sequentially in `backend/pipeline/runner.py`.
No LangGraph in Phase 1 — plain Python function chain.
