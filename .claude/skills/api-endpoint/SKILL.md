---
name: api-endpoint
description: Add or change a FastAPI endpoint in backend/api.py (or backend/auth/routes.py) so it satisfies CodeOnboard's four-layer ownership boundary, error conventions and frontend contract. Use whenever a route is added, its path or method changes, its response shape changes, or a new error condition is introduced.
---

# Adding or changing an endpoint

A route is the one place in this codebase where forgetting a single line makes
another learner's session readable. Four independent layers exist because
forgetting is the failure mode — this is the order to satisfy them in.

Reference: [`docs/architecture/backend-api.md`](../../../docs/architecture/backend-api.md),
decisions **D20** and **D22**.

---

## 1. Decide what the caller must prove

| Dependency | Use for |
|---|---|
| `owned_session` | A session route whose handler wants the graph. The chokepoint — prefer it |
| `current_user` | A route that needs the caller but loads the graph itself, part-way through |
| `owner_id` | A route that writes rather than reads a graph and needs only the id |
| `optional_user` | Behaves differently when signed in but does not require it |
| *(none)* | Only if the path is genuinely public — see step 4 |

All four live in `backend/auth/deps.py` and are declared in the signature, never
called as helpers inside the body. That is what lets
`tests/test_route_authz_coverage.py` enumerate `app.routes` and fail the build.

```python
@app.post("/session/{session_id}/thing")
def session_thing(session_id: str, body: ThingRequest,
                  user: CurrentUser = Depends(current_user)) -> dict:
    graph = _load_session_or_404(session_id, user.user_id)
    ...
```

## 2. Never load a graph without naming the owner

`learning_store.load_graph(session_id, user_id, SESSIONS_DB_PATH)` takes the owner
as a **required positional argument**. Use `_load_session_or_404` in `api.py`, or
`Depends(owned_session)`. There must be no code path that produces a
`LearningGraph` without a caller having said whose it is.

Saving is the same: `learning_store.save_graph(graph, SESSIONS_DB_PATH, user_id=...)`.

## 3. **404, never 403**

A session that belongs to somebody else and a session that does not exist answer
**identically, byte for byte**. A 403 confirms which ids are real. `load_graph`
returns `None` for both cases on purpose — do not add a branch that distinguishes
them, and do not include the id or the owner in the message.

## 4. If the route really is public

Add it to `PUBLIC_PATHS` in `backend/api.py` **and** to `PUBLIC` in
`tests/test_route_authz_coverage.py`, where each entry carries the reason it is
safe. That list is an allow-list precisely so it fails closed: adding to it should
feel like a decision, because it is one.

## 5. Choose the status code from the existing conventions

| Status | Means |
|---|---|
| `401 not_authenticated` | No valid cookie, or the route declares no auth |
| `404 session_not_found` / `node_not_found` | Not yours, or not there — indistinguishable |
| `409` | Well-formed, but the session's **state** refuses it (`no_plan_snapshot`, `generation_already_running`, `no_pending_reassessment`, …) |
| `400` | A bad value in a well-formed body — an unsupported signal, direction, action or intent |
| `422` | FastAPI's own validation. Free; do not hand-roll it |

`detail` is a **slug**, lowercase with underscores, not a sentence. It is a fixed
key the frontend switches on (D24).

## 6. Close the loop in the frontend

Any new slug needs an entry in `t.errors` in `frontend/lib/strings.ts`, or the
learner sees a raw backend token. Prefer `errorTextOr` at any call site where a
transport failure could surface an unworded string.

If the route returns a **learning decision** — whether a retry is offered, why
there is none, whether the objective is met, any progress number — the server must
send the decision itself, not the ingredients (D22). A component that recomputes it
is a seam, and every defect this rule exists to prevent was one.

## 7. Verify

```bash
uv run pytest tests/test_route_authz_coverage.py tests/test_ownership.py tests/test_security.py -q
```

Then the full gate via the `verify-change` skill. If the route is reachable from
the UI, also run the frontend suite and build — a payload change breaks the seam
between them, and only running both finds it.
