# `backend/learning/` — the learning model

The graph, what the learner has demonstrated, and every rule about what happens
next. **Everything here except `store.py` is pure** — no IO, no model calls — which
is what lets the whole policy be tested without an API key.

> Parent: [`backend/`](../README.md) ·
> Architecture: [docs/architecture/learning-engine.md](../../docs/architecture/learning-engine.md) ·
> Data model: [docs/architecture/persistence.md](../../docs/architecture/persistence.md)

---

## Modules

| File | Owns | Pure? |
|---|---|---|
| `graph.py` | `LearningGraph`, `LearningNode`, `CodeAnchor`, traversal, and `understanding_of()` — the **single owner** of "is this node understood" | ✔ |
| `gaps.py` | `Gap`, `GapState`, the lifecycle, the blocking rule, the caps | ✔ |
| `history.py` | What the learner did and what the system did about it — attempt-scoped vs journey-scoped | ✔ |
| `understanding.py` | The two dimensions: what the evidence shows, and what the learner decided | ✔ |
| `progress.py` | The two measures, and the invariant behind them | ✔ |
| `adaptation.py` | Which response a shortfall earns, and `prune_ahead` | ✔ |
| `retry.py` | Which retry *Ask me again* offers, and why not when it does not | ✔ |
| `scope.py` | `shorter` / `deeper` — moving units between priority buckets | ✔ |
| `reset.py` | `Start over` — restore the plan, discard the walk | ✔ |
| `contribution.py` | The `contribute_code` stage's state, and the deterministic checks on a change. `check_scope` is **path scope only**; `check_paths` is the same claim from paths alone and names what it did not look at | ✔ |
| `handoff.py` | What leaves for a coding agent: repository knowledge and learner state, in two namespaces that are never mixed | ✔ |
| `coverage.py` | Which survey subsystems the curriculum never touched — what the journey did *not* cover | ✔ |
| `patterns.py` | L2 observations over answers | ✔ |
| `gap_insight.py` | L2 observations over gap objects | ✔ |
| `flags.py` | `CODEONBOARD_TUTOR`. **Nothing in `store.py` may import this** | ✔ |
| `store.py` | SQLite persistence — and the ownership boundary | ✖ |

---

## The distinctions that matter

**Evidence versus decision.** `understanding_state` is what the Grader concluded
from an answer. `user_override` is what the learner decided about remediation. They
are separate channels, and every surface that blurred them has been closed: *Move
on anyway* and *mark understood* write only disposition. `mark_weak` is the
deliberate asymmetry — agreeing with a shortfall can only lower the claim being
made about the learner.

**Latest assessment versus derived state.** `mark_understanding()` writes an
*input*; `understanding_of()` owns the *conclusion*, combining it with the gaps. A
node cannot be `understood` while a blocking gap is unverified, whatever the last
answer scored. An AST test enforces that nothing re-derives this elsewhere.

**Two strengths of "settled".** `graph.is_settled` (strict: `understood` or an
explicit override) is the input to `is_complete()`. `progress.is_settled` (weaker:
visited, answered, or acted on) feeds the coverage measures. They answer different
questions and both are needed.

**Two producers of `prerequisite` edges.** Planned dependencies (dozens on a normal
graph) and remedial warm-ups. The structural tell is that `insert_before` reroutes
the incoming sequence edge, so a warm-up has **no outgoing sequence edge**.
`progress.remedial_ids` is the one place that is computed — a consumer that treats
every prerequisite edge as remedial reports a planned curriculum as a sequence of
failures.

---

## The invariant

> **Goal readiness may fall only when evidence about the learner changes. It must
> never fall because the system changed the plan.**

That is why remedial nodes are excluded from both sides of the fraction. Before
it, inserting a warm-up dropped the gauge from 0.50 to 0.33 — the system's decision
to help looked like the learner losing ground. `tests/test_progress.py` pins every
mutation against this rule.

---

## The flag contract

A flag gates **behaviour**, never **storage**. Nothing in `store.py` calls
`flags.py` or reads the environment, and
`tests/test_gap_model.py::test_the_persistence_path_reads_no_feature_flag` asserts
that structurally — which is what makes the round-trip guarantee true by
construction rather than by care.

`CODEONBOARD_TUTOR` is the flag this currently protects. It was written for
`CODEONBOARD_GAPS`, which has been removed: gap recording is unconditional, so
gap data cannot be switched off at all. The assertion is name-agnostic — it
checks for the *mechanism*, not for a list of variables — which is why it
survived the removal and why it will cover the next flag before it is added.

---

## `store.py`, and the two sides of it

`nodes` / `edges` are the **live** graph; `plan_nodes` / `plan_edges` are the
**original plan**. The contract:

> `save_graph` **never** writes a plan table. The only writers are
> `create_session` and `record_plan_lesson`.

That is what makes `reset.py` a *replacement* rather than an inversion of every
mutation — and why **anything not in the plan is gone by construction**, so a
state field added to `LearningNode` tomorrow is handled today without a line
changing.

`load_graph(session_id, user_id, db_path)` takes the owner as a **required**
parameter. This module is the one place in `learning/` that knows a user exists,
because it is the boundary.

---

## Tests

`tests/test_learning_graph.py`, `test_progress.py`, `test_understanding.py`,
`test_history.py`, `test_patterns.py`, `test_gap_insight.py`, `test_gap_model.py`,
`test_gap_adaptation.py`, `test_gap_verification.py`, `test_gap_understanding.py`,
`test_gap_remediation.py`, `test_gap_remediation_rounds.py`,
`test_gap_intents.py`, `test_adaptation.py`, `test_retry_dispatch.py`,
`test_scope.py`, `test_decision_is_not_evidence.py`, `test_learning_store.py`,
`test_plan_snapshot.py`, `test_session_reset.py`, `test_store_concurrency.py`,
`test_legacy_session_compatibility.py`, `test_question_traceability.py`,
`test_attempt_history.py`.
