# Session reset — the plan is persisted, not reconstructed

**Phase status: IMPLEMENTED, awaiting manual end-to-end validation.**
M1–M3 done on branch `feat/session-reset-m1` (commits `190c2cd`, `09d6743`,
`d68660a`), built in an isolated worktree because another stream was working in
the same backend files. 1374 backend tests, 595 frontend tests, `tsc` clean.

Three deviations from the plan below, each with its reason:

| # | planned | shipped |
|---|---|---|
| 1 | `history.RESET` in M1 | deferred to M2. It is unused until a reset exists, and `history.py` was being actively edited by the other stream — adding an unused constant would have bought only a merge conflict |
| 2 | `_write_plan` uses `INSERT` | `INSERT OR IGNORE`. A double call must be a no-op, not an `IntegrityError`: the plan already being written is not an error, and refusing to overwrite is the property that matters |
| 3 | "one transaction" | precise about DATA, not DDL. `create_session` calls `init_db` first, which opens its own connection for `CREATE TABLE IF NOT EXISTS`. All four data writes are in one transaction, asserted by `test_creation_is_one_transaction` |

Two things the plan did not anticipate, both recorded here because they cost time
to find:

- **`/lesson` serves a cached lesson through Teaching's own early return**, not by
  bypassing Teaching. So a test that mocks `run_teaching` to prove "no work
  happens" deletes the mechanism it is testing. The test asserts the consequence
  instead — the Anthropic client is never called.
- **The graph helpers do not write journey events; the endpoints do.** A fixture
  that calls `scope.shorten()` directly under-represents a real session's history,
  which is the thing a reset has to clear.

`Start over` currently re-runs the entire repository-analysis pipeline and
creates a new session: two to four minutes, a fresh Sonnet planning call, and a
**different curriculum** than the one the learner was looking at. That is not
what starting over means. A learner who asks to start over is asking to walk the
same path again from the beginning.

This phase splits one control into two:

| control | means | cost |
|---|---|---|
| **`Start over`** | the **same** learning path, restored to its post-planning state, with none of this learner's work | zero model calls, milliseconds |
| **`Rebuild learning path`** | what `Start over` does today — re-analyse the repository and plan a new route | 2–4 minutes, one Sonnet call, a different route |

**The semantics, in one sentence:** after `Start over` the learner sees the route
exactly as the planner produced it, and nothing they or the system did during the
previous walk survives.

**The architecture, in one sentence:** the original plan is **persisted at
creation and never modified**; the live graph stays as mutable as it is today;
`Start over` restores the live graph from the plan.

---

## 1. Why persist rather than reconstruct

An earlier draft of this phase reset by *inverting* every learning-time
mutation — deriving planned priorities from `journey_events`, recovering
pre-re-teach lessons from `superseded_lesson`, walking remedial prerequisite
chains to repair rerouted sequence edges, in a fixed order. It was rejected in
favour of a snapshot, for a reason that is not "less code":

**Reconstruction is a classification problem; a snapshot is a definition
problem.** Inverting mutations requires a complete and correct answer to *"which
of these bytes did learning write?"* — a question about history, answered from
evidence each mutation left behind. Every new learning-time behaviour adds a
case.

**The failure modes are asymmetric, and that decides it.** Under
reconstruction, a missed field means learner state **survives a reset and looks
like plan data** — silent, and in the dangerous direction. Under a snapshot, a
missed field means plan data is **lost at reset** — loud, immediate, and caught
by the single equality in §5. And a new *state* field on `LearningNode` needs no
reset code at all: restore constructs fresh nodes from plan rows, so anything not
in the plan lands on its dataclass default by construction.

Deleted from the design by this change: planned-priority stamping, the
`journey_events` priority derivation, `superseded_lesson` recovery, remedial
chain-walking and edge repair, the per-field clearing pass and its ordering
constraints, and the plan/state field frozensets. Six of the eight regression
risks the earlier draft carried stop existing.

---

## 2. Decisions

| # | question | decision |
|---|---|---|
| **D1** | Reset in place, or fork the plan into a new session? | **In place.** The live `nodes` table is `PRIMARY KEY (node_id)` — global, not per session — so a copy must re-mint every node id. Worse, the Dossier is keyed by `session_id` (`backend/repo/dossier_store.py`), so a new session id starts with no goal-specific understanding and every later lesson, re-teach and warm-up silently falls back to the Skeleton. In place keeps `session_id`, the Dossier, the briefing, the URL and `_try_resume`'s matching intact |
| **D2** | Scope and priority changes — keep or undo? | **Undo all of them**, adaptive (`adaptation.prune_ahead`) and explicit (`scope.shorten` / `scope.deepen`) alike. Free under this architecture: `lesson_brief` is restored wholesale from the plan, so no producer needs special handling |
| **D3** | Regenerate lessons, or keep the original prose? | **Keep it, exactly.** Lessons are rendered lazily and do not exist at plan time, so the plan row carries a **write-once lesson slot** filled on first successful render (§4.3). Regenerating would cost a Haiku call per revisited stop and produce *different* prose — the opposite of "the same learning path" |
| **D4** | Archive the previous attempt? | **No.** Nothing consumes historical learner state: `/sessions` returns live summaries, and the ten `scripts/` probes read live sessions as fixtures. `Gap.objective_key`'s cross-session use is deferred until learner identity exists (LQ7). A partial snapshot is worse than none, an unexercised write path rots, and [`multi-user.md`](multi-user.md) would have to migrate any table added now. If it is ever wanted, the right shape is a fork — and the new plan tables are already keyed for one (§4.1) |
| **D5** | Confirm before resetting? | **Yes**, inline, in the pattern `Finish session` already uses: what survives (the route, the lessons, the briefing) above what does not (progress, answers, feedback, gaps, adaptations). Irreversible by D4, so the confirmation is the only guard |
| **D6** | Where does the learner land? | **Nowhere new.** Same `/session/{id}` URL, `current_node_id` = `path_head()`, stop 1's lesson. `/welcome` is not shown again: the briefing answers "what is this repository, and who are you as a learner", and a reset changes neither |
| **D7** | Does the tour replay? | **No.** `codeonboard:tour` is per browser, not per session, and deliberately so |
| **D8** | Backward compatibility for the 90 existing sessions? | **None.** All of it is development data. `SCHEMA_VERSION` goes 2 → 3 and pre-v3 rows become invisible through the documented no-silent-migration path. **No backfill, and no legacy reconstruction logic** — a session with no plan cannot be reset, and pretending otherwise is what the rejected design was made of. **The fixtures are preserved rather than discarded:** all 90 v2 sessions were copied to `data/sessions-fixtures.db` before the bump (via `VACUUM INTO`, not a file copy — WAL means committed pages can still be in `-wal`), and the seven measurement scripts that pin session ids now read that file. Consequence in §7 |
| **D9** | Two mirror tables, or a `plan_json` column? | **Tables** (§4.1). The write-once lesson slot needs a targeted update rather than a read-modify-write of a blob; the column list becomes the plan/state partition expressed in schema; and the composite primary key avoids repeating the live table's global-id mistake |

---

## 3. Plan versus live state

The rule is now structural rather than enumerated: **the plan tables hold the
plan. Everything else in the live graph is state.**

### Held in the plan (`plan_nodes` / `plan_edges`)

`node_id`, `title`, `file`, `line_start`, `line_end`, `symbol`,
`concept_tags`, `lesson_brief` (including `priority`), the original rendered
lesson, and every planned edge.

### Live-only, and reset

| field | on reset |
|---|---|
| `understanding_state`, `visited`, `weak_spot`, `user_override`, `attempts`, `gap_state` | gone with the node row — replaced by a fresh node built from the plan |
| remedial nodes and the edges they rerouted | gone with the wholesale edge replacement |
| `lesson_brief` mutations — `priority` by prune-ahead or scope, `scope_locked`, `remediates` | gone; the planned brief is restored verbatim |
| `cached_lesson` | set to the plan's lesson slot |
| `current_node_id` | → `path_head()` of the restored edges |
| `arrival` | → `None` |
| `journey_events` | → `[reset]` (§4.5) |

### Session-level, and preserved

`repo_url`, `goal_json`, `doc_context_json`, `areas_json`, `briefing_json`,
`created_at`. Every one is written once by the pipeline or by the first welcome
GET, and **nothing in the learning loop writes them** — so they need no snapshot,
and restore leaves them alone.

*Residual risk, recorded:* a future feature that mutates `areas` (or any other
session-level plan column) during learning would need it added to the plan.
Nothing does today.

### Outside the graph

| store | keyed by | on reset |
|---|---|---|
| `investigation` (Dossier) | `session_id` | **kept** — plan-side understanding, and the reason for D1 |
| `repo_survey` | `(owner/repo, commit, schema)` | kept |
| `codeonboard:tour` | browser | kept (D7) |
| `codeonboard:prefs`, `codeonboard:rail-hidden` | browser | kept — display settings |
| `codeonboard:rail-seen:{id}` | browser + session | cleared (§4.6) |

`progress.py`, `understanding.py`, `patterns.py` and `gap_insight.py` are pure
functions over the graph. They self-clear; there is nothing to reset.

---

## 4. Specifications

### 4.1 Schema (`SCHEMA_VERSION` 2 → 3)

```sql
CREATE TABLE IF NOT EXISTS plan_nodes (
    session_id        TEXT NOT NULL,
    node_id           TEXT NOT NULL,
    title             TEXT NOT NULL,
    file              TEXT NOT NULL,
    line_start        INTEGER NOT NULL,
    line_end          INTEGER NOT NULL,
    symbol            TEXT,
    concept_tags_json TEXT NOT NULL,
    lesson_brief_json TEXT NOT NULL,
    lesson_json       TEXT,                 -- write-once, §4.3
    PRIMARY KEY (session_id, node_id),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS plan_edges (
    session_id   TEXT NOT NULL,
    from_node_id TEXT NOT NULL,
    to_node_id   TEXT NOT NULL,
    kind         TEXT NOT NULL,
    PRIMARY KEY (session_id, from_node_id, to_node_id, kind),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);
```

Two properties are deliberate. The column list **is** the plan/state partition —
visible in `.schema` rather than asserted in a frozenset. And the primary key is
`(session_id, node_id)`, not the live table's global `(node_id)`, which is the
detail that makes forking a plan impossible today (D1) and is not repeated here.

No backfill (D8). Pre-v3 sessions become invisible to `load_graph`, which is the
store's existing documented behaviour for a version mismatch.

### 4.2 Writing the plan — one transaction, one caller

```
store.create_session(graph, db_path)   # sessions + nodes + edges + plan_* atomically
```

`/session/start` calls this instead of `save_graph` for a newly planned graph.
Every other call site keeps using `save_graph`, which **never touches the plan
tables**.

One transaction, not two, because a session that exists without a plan is a
session where `Start over` is impossible. That must be unrepresentable rather
than merely unlikely.

### 4.3 The lesson slot — write-once, on first successful render

Lessons are rendered lazily per stop, so `plan_nodes.lesson_json` is NULL at
creation and is filled by:

```
store.record_plan_lesson(session_id, node_id, lesson, db_path)
    UPDATE plan_nodes SET lesson_json = ?
     WHERE session_id = ? AND node_id = ? AND lesson_json IS NULL
```

Called from exactly one place — `_render_current_lesson`, after `run_teaching`
**succeeds**. Four properties, each load-bearing:

- `WHERE lesson_json IS NULL` makes overwriting physically impossible, and makes
  two stops rendering concurrently safe without a read-modify-write.
- **The API fallback lesson is never recorded.** A Teaching failure leaves the
  slot NULL so a later successful render fills it, rather than sealing "this
  lesson could not be generated" into the plan permanently. This is strictly
  better than today, where the fallback sits in `cached_lesson` until something
  overwrites it.
- A **re-teach never calls this** — and could not overwrite if it did. A node's
  first render can never *be* a re-teach: `/respond` 409s without a
  `cached_lesson`, so a graded answer implies a prior render.
- A remedial node is not in `plan_nodes`, so the UPDATE matches zero rows and is
  a harmless no-op. This is why it is an UPDATE and not an upsert.

So the guarantee is stated precisely: the plan record is **append-only, at most
one write per slot** — not written-once-and-sealed.

### 4.4 Restoring

```
store.load_plan(session_id, db_path) -> LearningGraph | None
```

Returns "the graph as planned": nodes with every state field at its dataclass
default and `cached_lesson` from `lesson_json`, plus the planned edges. Session
columns are read from the same row the live graph uses, so `repo_url`, `goal`,
`doc_context`, `areas` and `briefing` come across unchanged.

`reset(graph_or_session_id)` is then:

1. `plan = load_plan(session_id)` — 409 `no_plan_snapshot` if absent (unreachable
   for v3 sessions; see D8)
2. replace the live graph's `nodes` and `edges` with the plan's
3. `current_node_id = path_head()`; `arrival = None`; `journey_events = [reset]`
4. `save_graph`

No per-field clearing, no ordering constraints, no inversion.

### 4.5 `POST /session/{session_id}/reset`

No LLM, no clone, no pipeline. Returns
`{session_id, graph: to_dict(), discarded: {...}}` — the same graph shape
`GET /session/{id}` returns, so the client needs no second fetch. `discarded`
carries counts (attempts, gaps, remedial nodes) for the log line and for the
confirmation's aftermath; nothing is persisted (D4).

404 on an unknown session. Idempotent: resetting a pristine session returns the
same graph.

`history.RESET = "reset"` is added to `JOURNEY_EVENT_KINDS` and recorded on the
restored graph as the single boundary marker — the only trace, given D4, that the
previous attempt existed. Exactly one ever accumulates, because each reset
replaces the list. The current frontend drops journey events of unknown kind and
`unseenRouteChanges` filters to shape kinds, so it renders nothing and raises no
rail dot until copy is written for it. Intended for this phase.

**Known race, stated rather than discovered:** `save_graph` rewrites wholesale,
so a `/respond` that began before the reset lands after it and resurrects state.
Single-user, and the client disables input for the duration of a call that makes
no model requests. Not mitigated further here.

### 4.6 Frontend

**Menu.** `Start over` gains an inline confirmation (D5) in the pattern
`Finish session` uses. `Rebuild learning path` becomes a second, separately
confirmed item wired to the existing `sessionStart(force_new)` +
`RebuildingOverlay`, which is the progress surface a rebuild needs. (It was
`RestartingOverlay` while it belonged to the old combined action; renamed with the
split, since it now reports only the rebuild.)

**Session page.** The URL and `id` do not change, so React keeps every child
mounted and its state alive: `LessonPanel`'s answer text and verdict, `finished`,
the `introduced` sections ref, `dismissedArrivalAt`, the active tab, the evidence
drawer, the chapter overview. Resetting those field by field is a list the next
feature forgets — so a `sessionEpoch` counter is used as a React `key` on the
session body, discarding all descendant state by construction. Page-level state
the key does not cover (`finished`, `introduced`) is reset in the same handler,
and `codeonboard:rail-seen:{id}` is removed.

**Copy.** New strings under `t.session`; the existing `restart*` strings move to
the rebuild action. Nothing model-authored, nothing markdown.

---

## 5. Tests

**The acceptance assertion is one equality:**

> after a reset, `to_dict()` of the live graph equals `to_dict()` of a graph built
> purely from the plan.

Reached by building a graph, simulating a full session against it — attempts,
gaps at every status, a re-teach, a waiver, an override, a `prune_ahead`
demotion, a scope change in both directions, and a spliced warm-up — then
resetting.

| area | cases |
|---|---|
| plan immutability | after that whole simulated session, `plan_nodes` and `plan_edges` are **byte-identical** except for filled lesson slots |
| write-once | a second `record_plan_lesson` for the same node changes nothing; a re-teach does not touch the plan; the API fallback lesson is never recorded; a remedial node's render is a no-op |
| atomicity | `create_session` writes session, nodes, edges and plan in one transaction; no path produces a session without a plan |
| restore | remedial nodes gone; planned edges and `path_order()` restored; `priority` back to planned for both producers; `scope_locked` and `remediates` gone; `cached_lesson` is the original prose after a re-teach |
| field coverage | every `LearningNode` field is either written by the plan round-trip or at its dataclass default after reset — the guard against a new **plan** field silently failing to persist |
| graph state | `current_node_id` == head; `arrival` None; `journey_events` == `[reset]` |
| persistence | the reset graph round-trips through `save_graph` / `load_graph` unchanged |
| API | 404 unknown session; second reset is a no-op; response shape matches `GET /session/{id}` |

All of it runs without an API key.

---

## 6. Build order

| step | content |
|---|---|
| **M1** | Store — `SCHEMA_VERSION` 3, the two tables, `create_session`, `record_plan_lesson`, `load_plan`; `/session/start` and `_render_current_lesson` repointed. `history.RESET`. **No reset yet** — this milestone only makes the plan exist |
| **M2** | `reset()` + `POST /session/{id}/reset` + the acceptance test |
| **M3** | Frontend — `resetSession`, the confirmation, the epoch key, `Rebuild learning path` moved onto the existing overlay, strings |

M1 before M2 deliberately: the plan has to be written before anything can restore
from it, and M1 is independently verifiable (create a session, assert the plan
matches the live graph, walk it, assert the plan did not move).

---

## 7. What could regress

| # | risk | guard |
|---|---|---|
| 1 | A plan write and a live write land in different transactions → a session that cannot be reset | §4.2, one `create_session`; test |
| 2 | Something overwrites a plan lesson slot with a re-taught or fallback lesson | `WHERE lesson_json IS NULL`; the one-caller rule; byte-identity test |
| 3 | A new `LearningNode` **plan** field is added and never reaches `plan_nodes` → silently lost at reset | the field-coverage test in §5 |
| 4 | `save_graph` grows a plan-table write | it has one caller set today; the byte-identity test fails if it does |
| 5 | Frontend keeps the previous verdict / answer on screen after a reset | the epoch key, not a field-by-field reset |
| 6 | **The `SCHEMA_VERSION` bump orphans the probe fixtures.** `scripts/m10_acceptance.py`, `reteach_probe.py` and `verification_probe.py` pin session ids (`431af315…`, `a3234f41…`) that become unreadable | Accepted per D8. Copy `data/sessions.db` aside before migrating and point those scripts' `DB` constant at the copy |
| 7 | `Rebuild learning path` loses the progress surface in the move | it reuses `RebuildingOverlay`, whose eight tests stand unchanged |

## 8. Cost

Zero model calls and no clone for a reset. One `SCHEMA_VERSION` bump, two new
tables, no `ALTER TABLE`. Storage duplication is ~1.5 KB per node — measured
against the live database: `lesson_brief` averages 626 B and `cached_lesson`
931 B across 968 nodes, so the plan side adds ~1.5 MB to a 16 MB file, and ~25 KB
to a fifteen-stop session. `Rebuild learning path` costs exactly what `Start
over` costs today, and is now the only thing that does.
