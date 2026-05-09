# Patterns & Utilities

Reference for the recurring tools and patterns used across this codebase.

---

## `@dataclass`

**What it is:** A Python decorator that auto-generates `__init__` and other boilerplate for classes that are pure data containers.

**When we use it:** For internal objects that hold state but need no validation — `GoalSession`, `Question`.

```python
@dataclass
class GoalSession:
    session_id: str
    repo_url: str
    goal_type: str | None = None
    answers: dict[str, str] = field(default_factory=dict)
```

`field(default_factory=dict)` creates a fresh dict per instance. Without it, all instances would share the same dict — a common Python bug with mutable defaults.

**vs Pydantic:** Use `@dataclass` for internal objects. Use `BaseModel` (see below) for anything that crosses a system boundary (LLM output, API request/response).

---

## Pydantic `BaseModel`

**What it is:** A base class that validates field types at runtime when an instance is created.

**When we use it:** For objects whose data comes from an untrusted source — LLM responses (`GoalOutput`), API request bodies (`StartRequest`, `AnswerRequest`).

```python
class GoalOutput(BaseModel):
    primary_goal: str
    goal_type: Literal["understand_system", "understand_component", "contribute_code", "debug_issue"]
    focus_area: str
```

If the LLM returns a wrong type or an invalid `goal_type` value, Pydantic raises a `ValidationError` immediately rather than letting bad data flow downstream.

---

## `Literal` type

**What it is:** A type annotation that constrains a field to a fixed set of string values.

**When we use it:** For enum-like fields where the set of valid values is small and known — `goal_type`, `depth`.

```python
from typing import Literal

goal_type: Literal["understand_system", "understand_component", "contribute_code", "debug_issue"]
```

Pydantic enforces this at runtime; a value not in the list raises `ValidationError`.

---

## Package `__init__.py` as a public surface

**What it is:** When a directory contains `__init__.py`, Python treats it as a package. We use `__init__.py` to re-export the symbols that callers should use.

**When we use it:** `backend/agents/goal/__init__.py` re-exports from `agent.py` and `questions.py` so callers import from one place:

```python
# clean — one import location
from backend.agents.goal import GoalSession, start_session, CORE_QUESTIONS

# avoid — leaks internal structure
from backend.agents.goal.agent import GoalSession
from backend.agents.goal.questions import CORE_QUESTIONS
```

This means internal files can be renamed or split without changing every caller.
