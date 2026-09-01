# Working in `backend/`

> Architecture: [`docs/architecture/backend-api.md`](../docs/architecture/backend-api.md) ·
> Idioms: [`docs/reference/patterns.md`](../docs/reference/patterns.md) ·
> Invariants: [`docs/architecture/decisions.md`](../docs/architecture/decisions.md)
>
> The root [`CLAUDE.md`](../CLAUDE.md) maps each file here to the invariants that
> govern it, and each kind of request to the skill that handles it. Read that row
> first. `agents/` and `tests/` have their own scoped files that load beside this
> one.

---

## Where a responsibility belongs

| Kind of change | Goes in | Procedure |
|---|---|---|
| A rule that can be stated and tested — sizing, which response a shortfall earns, whether a gap blocks | `learning/`, as a **pure function** | skill `change-learning-policy` |
| Judgement or language — prose, a question, a classification | a prompt in `agents/<name>/` | skill `change-agent-or-prompt` |
| Something the AST already knows — files, symbols, ranges, imports | `repo/skeleton.py`, never a model | — |
| HTTP concerns — routing, status codes, request parsing | `api.py` | skill `api-endpoint` |
| Reading or writing a row | `learning/store.py` or `auth/schema.py` | skill `persistence-change` |

Two mistakes this table exists to stop: putting policy in a prompt where nothing
can test it, and putting IO in a module whose header promises purity.

`backend/api.py` is a single module rather than a router package, and everything
in it is HTTP concern — routing, status codes, parsing, orchestration of pieces
already written. Authentication is the exception and lives in its own router,
because it is a self-contained surface with its own throttling and cookies.

---

## The ownership boundary, in one paragraph

Every route declares `current_user` / `owned_session` / `owner_id` /
`optional_user`, **or** is listed in `PUBLIC_PATHS` with a stated reason.
`store.load_graph(session_id, user_id, …)` takes the owner as a **required**
argument, so no code path anywhere produces a `LearningGraph` without a caller
having named whose it is. A session that is not yours answers **404, never 403** —
byte for byte identical to one that does not exist. Four layers hold this up
because forgetting is the failure mode, and
`tests/test_route_authz_coverage.py` fails the build if you skip the first.

## Persistence, in one paragraph

`save_graph` must **never** write `plan_nodes` / `plan_edges` — only
`create_session` and `record_plan_lesson` do, which is what makes `Start over`
restore the plan rather than a contaminated copy of the walk, and why
anything not in the plan is gone by construction. Prefer an additive nullable
column in `_ADDITIVE_COLUMNS` to a `SCHEMA_VERSION` bump: a bump makes earlier
sessions **invisible**, not migrated. Nothing in `store.py` may read
`CODEONBOARD_GAPS` — the flag gates behaviour, never storage.

## Errors

| Status | Means |
|---|---|
| `401 not_authenticated` | No valid cookie, or the route declares no auth |
| `404 session_not_found` / `node_not_found` | Not yours, or not there — indistinguishable on purpose |
| `409` | Well-formed, but the session's *state* refuses it |
| `400` | A bad value in a well-formed body |
| `422` | FastAPI's own validation — free, do not hand-roll it |

`detail` is a lowercase slug, not a sentence: it is a fixed key the frontend
switches on, and it needs a matching entry in `frontend/lib/strings.ts`.

## Startup refuses rather than degrades

`auth_config.enforce()` runs **before** the database is touched — a deployment
with an insecure setting should not get as far as touching data — then
`run_startup_checks` creates both halves of the schema, refuses to start if any
session has no owner, and fails rows left `generating` by a process that died.
Keep new startup work in that order, and keep it refusing.

## Style

Modules open with a header — a `#` block or a docstring — naming the decision the
module holds and the defect that decision prevents. That is the house style and
it is why this codebase is readable; match it rather than describing what the code
does. `docs/reference/patterns.md` covers the recurring idioms: `@dataclass` for
internal objects, Pydantic `BaseModel` at every trust boundary, `Literal` for
fixed vocabularies, and `__init__.py` as a package's public surface.
