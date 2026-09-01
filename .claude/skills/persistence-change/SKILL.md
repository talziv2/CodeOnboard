---
name: persistence-change
description: Change what CodeOnboard stores — a new field on a session, node or gap, a schema change, a migration, or anything in backend/learning/store.py, backend/auth/schema.py or backend/migrations/. Use before adding a column, bumping SCHEMA_VERSION, or writing anything that touches data/sessions.db.
---

# Changing what is stored

Reference: [`docs/architecture/persistence.md`](../../../docs/architecture/persistence.md),
decisions **D16** · **D17** · **D18** · **D19** · **D20**.

`data/sessions.db` holds every account and every session, is gitignored, has no
backup, and is the corpus behind `docs/planning/phases/evidence/`. **Nothing here
may delete it, migrate it in place, or point a test or script at it.**

---

## 1. Decide where the new value belongs — it may need no column at all

| The value is… | Put it in |
|---|---|
| Read only as part of a node's record (objective, kind, priority, `area_id`, anchors, origin) | `nodes.lesson_brief_json` — **no column** |
| Gap state, remediation counters, pending questions | `nodes.gaps_json` — one blob, written unconditionally |
| Session-scoped (areas, journey events, briefing, arrival) | a `sessions.*_json` column |
| Something a query filters or sorts by | a real column, plus an index if a listing uses it |

The rule: a value only ever read *as part of the record* goes into JSON that
already exists; a value that belongs to the session rather than to any one unit
earns a column. Adding a column nothing queries is cost with no benefit.

## 2. Prefer an additive nullable column to a version bump

Add it to `_ADDITIVE_COLUMNS` in `backend/learning/store.py`. `_add_missing_columns`
applies it on every `init_db`, asks first via `PRAGMA table_info`, and tolerates
exactly one error message. **Do not** widen that `except` — the blanket one it
replaced also swallowed `database is locked`, so the column was silently skipped,
`init_db` reported success, and the next `save_graph` failed on a column that did
not exist.

## 3. Bumping `SCHEMA_VERSION` is a last resort, and it is not a migration

```
SCHEMA_VERSION            = 3     what a NEW session is written at
SUPPORTED_SCHEMA_VERSIONS = {2,3} what this build can READ
```

Two different questions. `load_graph` treats a version mismatch as **missing** — it
returns `None` rather than migrating — so a bump makes every earlier session
*invisible*. That is what happened at the bump to 3: all 90 sessions in the
development database became unloadable.

If you must bump:

1. Add the new version to `SUPPORTED_SCHEMA_VERSIONS`, never replace the set.
2. **Revisit `load_plan`.** It keeps a strict `== SCHEMA_VERSION` check, so at the
   next bump a version-3 session with a real plan silently stops being resettable.
   The code names this; do not discover it in production.
3. Confirm `tests/test_legacy_session_compatibility.py` still passes.

## 4. Never write a plan table from `save_graph`

`plan_nodes` / `plan_edges` have exactly two writers: `create_session` (once, in
the same transaction as the session) and `record_plan_lesson` (physically unable to
overwrite). That is the whole of D16, and it is why `reset.py` needs no list of
fields to clear — **anything not in the plan is gone by construction**, so a state
field added to `LearningNode` tomorrow is handled today.

So: a new field is **plan** or it is **state**, and the answer is visible in the two
`CREATE` statements. If it is plan, it goes in `plan_nodes` *and* in the live table.
If it is state, it goes only in the live table — and adding it to a plan table is
how `Start over` starts restoring the walk instead of the plan.

## 5. Nothing is ever synthesised for a session with no plan

A version-2 session loads and resumes with its state exactly as it is, and
`Start over` is simply unavailable — `POST /reset` answers **409 `no_plan_snapshot`**,
not 404, and attempts no reconstruction. A plan rebuilt from a half-walked graph is
not the plan; it is wherever the learner had got to, relabelled. Absent is honest.

## 6. The flag gates behaviour, never storage

Nothing in `store.py` may read `CODEONBOARD_GAPS`. Gap data written flag-on must
survive a flag-off load, a flag-off re-save, and be restored exactly when the flag
returns. `tests/test_gap_model.py::test_the_persistence_path_never_reads_the_flag`
asserts this by inspecting the module, so the contract cannot rot quietly.

## 7. Ownership stays a required parameter

`load_graph(session_id, user_id, …)` and `save_graph(graph, …, user_id=…)` take the
owner explicitly. Do not add a default, an "internal" variant, or a helper that
omits it. `store.py` is the **only** module in `learning/` that knows users exist,
because it is the boundary — keep it that way.

## 8. Writing a migration

One exists: `backend/migrations/001_multi_user.py`. Match its shape.

- **Idempotent, every step**: `IF NOT EXISTS`, lookup-then-insert, or
  `UPDATE … WHERE column IS NULL`. The first run is the one most likely to be
  interrupted, so "run it again" has to be the correct response.
- **Dry run by default.** `uv run python -m backend.migrations.001_multi_user`
  reports what it would do.
- **A fresh installation must never need it.** `run_startup_checks` creates both
  halves of the schema before anything reads either.
- Never run a migration against `data/sessions.db` without being asked to, and say
  what it will change first.

## 9. Verify

```bash
uv run pytest tests/test_learning_store.py tests/test_plan_snapshot.py tests/test_session_reset.py tests/test_legacy_session_compatibility.py tests/test_migration.py tests/test_store_concurrency.py tests/test_first_run.py -q
```

Then the full gate via the `verify-change` skill. Persistence tests build a
database per test with `tmp_path` — if a new test needs a database, it does the
same. None of them may touch `data/sessions.db`.
