# `backend/pipeline/` — orchestration and shared state

One compiled LangGraph `StateGraph`, and the dataclass that is the **only** channel
between agents.

> Parent: [`backend/`](../README.md) ·
> Architecture: [docs/architecture/agents.md](../../docs/architecture/agents.md)

---

## Modules

| File | Owns |
|---|---|
| `state.py` | `OnboardState` — every field an agent may read or write |
| `graph.py` | The `StateGraph`: nodes, conditional edges, and error-reducer bookkeeping |
| `runner.py` | `run_pipeline(repo_url, goal, client, progress_id)` — the public entry point |
| `explorer_nodes.py` | `run_repo_survey` and `run_goal_investigation`, which wrap `backend/repo/` machinery |
| `progress.py` | Live progress for one in-flight run |

---

## The shape

```
START → repo_survey ──(skeleton ok?)──→ documentation → goal_investigation ──(dossier?)──┐
             │ no                                              │ no                      │
             ↓                                                 ↓                (reviewer goal type?)
            END                                               END                  yes ↓      ↓ no
                                                                                  reviewer → mentor → END
```

**One shape.** The RAG path and the flag that selected it were deleted; there is
nothing left to choose between.

Both conditional edges **end the run** rather than degrading it:

- **No skeleton, no onboarding.** A graph whose anchors could not be verified is
  worse than no graph.
- **No dossier, no plan.** Fabricating a curriculum from the module map is exactly
  the behaviour the architecture migration removed.

A missing **survey** is not in that category: a survey-less run still carries a
skeleton-derived `module_map` and continues.

**The Goal Agent is deliberately not a node here.** It runs upstream as a
multi-turn HTTP dialogue, so by the time `invoke()` is called the goal is finalized
input.

---

## `OnboardState`

Agents mutate it **in place** and the graph nodes return the fields they touched.
`errors` uses an `operator.add` reducer, so a node returning errors *extends* the
list rather than replacing it — and `_extract_new_errors` rolls the in-place
appends back before returning the diff, so the reducer stays the sole accumulator
and nothing is double-counted.

`client` rides on the state because **LangGraph nodes receive only the state** —
there is no way to pass an extra positional argument.

Fields, grouped by who writes them:

| Written by | Fields |
|---|---|
| The caller | `repo_url`, `goal`, `client`, `progress_id` |
| `repo_survey` | `repo_path`, `module_map`, `survey` |
| `documentation` | `doc_context` |
| `goal_investigation` | `investigation` (the Dossier, plus `accepted` / `stop_reason` / cost) |
| `reviewer` | `system_review` |
| `mentor` | `graph`, `learning_path`, `confidence`, `plan_report` |
| The interactive loop | `current_lesson`, `last_grade`, `last_mutation` (all transient — the durable effect is on the graph) |

`plan_report` exists because *"the curriculum genuinely needs N"* and *"the band
allowed N"* are different facts, and only the first can tell you whether a band is
set correctly.

---

## Progress reporting

`/session/start` blocks for two to four minutes and the run genuinely does clone,
index, survey, investigate and plan — so the client should at least be able to see
which of those it is doing.

The client invents a `progress_id`, sends it with the POST, and polls
`GET /session/progress/{id}` on a **separate** request while the POST is still in
flight. FastAPI runs sync endpoints in a threadpool, so the poll is served while
the pipeline thread works.

Two deliberate properties:

1. **Reporting can never fail a run.** Every public function is best-effort: an
   unknown id, a missing stage, a raising callback — all swallowed. Progress is a
   *view* of the work, never a participant in it.
2. **This module emits keys, not prose.** Stage keys and tool names are fixed
   vocabulary; the wording lives in `frontend/lib/strings.ts`. A percentage is
   deliberately not computed here either — the client decides how to draw what it
   is told.

In-memory and process-local by design: a run that outlives the request that
produced it has nothing left to report.

Stage reporting sits in the **node wrappers** rather than in the agents, because
the orchestration layer is what knows the run has moved on. The exception is
`repo_survey`, whose three substages are only visible from inside it.

---

## Tests

`tests/test_explorer_pipeline.py`, `tests/test_pipeline_progress.py`.
