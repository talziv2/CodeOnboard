# `backend/` — the Python application

The FastAPI app, the agents, the repository-understanding layer, the learning
model, and the account layer.

> Parent: [root README](../README.md) ·
> Architecture: [docs/architecture/backend-api.md](../docs/architecture/backend-api.md)

```bash
uv run uvicorn backend.api:app --reload    # http://localhost:8000
```

---

## What lives where

| Package | Owns | README |
|---|---|---|
| `api.py` | The HTTP surface. Routing, status codes, request parsing, and orchestration of pieces written elsewhere. Nothing in it decides learning policy | — |
| [`agents/`](agents/README.md) | Eight agents, each with one job and one prompt. Two of them call no model | ✔ |
| [`repo/`](repo/README.md) | Cloning, the tree-sitter index, the grounding oracle, the six tools, the exploration loop, the survey and the Dossier | ✔ |
| [`learning/`](learning/README.md) | The learning graph, gaps, understanding, progress, adaptation policy, retry dispatch, scope, reset — and the SQLite store | ✔ |
| [`pipeline/`](pipeline/README.md) | One compiled LangGraph `StateGraph`, and `OnboardState` — the only channel between agents | ✔ |
| [`auth/`](auth/README.md) | Users, identities, cookie sessions, throttling, optional Google sign-in, and the startup refusals | ✔ |
| `migrations/` | `001_multi_user.py`. Idempotent, with a dry-run mode. A fresh installation never needs it | — |

---

## The three boundaries worth knowing

**1. The learning engine knows nothing about users.** `learning/`, `agents/` and
`repo/` contain no reference to one. `learning/store.py` is the single exception,
because it *is* the ownership boundary: `load_graph(session_id, user_id, …)` takes
the owner as a **required** parameter, so there is no code path that produces a
graph without a caller having named whose it is.

**2. Agents never call each other.** They read and write `OnboardState`
(`pipeline/state.py`) and nothing else. The pipeline decides the order.

**3. Policy is code; prose is a model.** Where a rule can be stated and tested —
curriculum size, which response a shortfall earns, whether a gap blocks, which
*form* a question takes, which retry is offered — it is a pure function in Python.
The model supplies judgement and language. That split is what lets almost the whole
learning policy be tested exhaustively without an API key.

---

## Conventions every module here follows

- **The Anthropic client is injected.** No agent constructs one from the
  environment when a caller supplied one.
- **No agent raises at its caller.** Failures append to `OnboardState.errors` and
  leave the field they would have written as `None`.
- **`.env` fills gaps; it does not win.** `api.py` calls plain `load_dotenv()`, so
  a variable set on the command line beats the file. It was `override=True` once,
  which silently discarded exactly what the person typing it asked for.
- **`SESSIONS_DB_PATH` is an indirection** in `api.py`, so tests can point
  persistence at a temp database.

---

## Startup

`api.py`'s lifespan handler runs two things before the process serves anything,
and their severities differ on purpose:

1. `auth.config.enforce()` — **configuration before the database**. A deployment
   with an insecure setting should not get as far as touching data. Missing
   `ANTHROPIC_API_KEY` is a refusal everywhere; in production, insecure cookies, a
   missing signing key, a leftover localhost origin and half-configured Google are
   refusals too.
2. `auth.startup.run_startup_checks(db_path)` — creates both halves of the schema,
   **refuses to start** if any session has no owner (that session is unreachable
   forever, and the person who notices is a learner whose work has vanished),
   quietly deletes orphaned dossiers, and fails sessions left `generating` by a
   process that died.

The first is a refusal because a warning would not be read. The second's sweep is
quiet because an orphaned dossier is unreachable derived data and "absent" is a
supported state for every consumer.

---

## Tests

`uv run pytest tests/` — see [`tests/`](../tests/README.md) and
[docs/testing.md](../docs/testing.md).
