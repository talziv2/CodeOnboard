---
name: change-learning-policy
description: Change how CodeOnboard decides what a learner has demonstrated or what happens next — retry behaviour, a new understanding state, gap lifecycle, readiness or journey progress, adaptation rules, scope, overrides, completion. Use for requests like "change how retry works", "add another learning state", "make waiving count differently", or any edit under backend/learning/.
---

# Changing the learning policy

"Change how retry works" is never a local change. The learning model is one
object with four channels that must stay separate, a wire contract the UI renders
verbatim, and three tests that guard the architecture rather than a feature.

Read first: `docs/architecture/learning-engine.md` §5–§9, and the module header of
whatever you are about to edit — `progress.py`, `understanding.py`,
`adaptation.py`, `retry.py`, `scope.py` and `gaps.py` each open with the decision
they hold and the defect it prevents. Those headers are the specification.

---

## 1. Find which channel the change belongs to

Four channels, deliberately independent. Putting a change in the wrong one is the
defect, not a style issue.

| Channel | Owns | Written by |
|---|---|---|
| **Evidence** — `understanding_state` | what the learner has *demonstrated* | `graph.understanding_of()` only |
| **Disposition** — `user_override` | what the learner *decided* about remediation | `continue_past`, `waive*`, `override` |
| **Gaps** — `nodes.gaps_json` | the specific false claims, and their lifecycle | `Gap.create` / `mark_verified` / `waive` |
| **Plan shape** — nodes, edges, `priority` | what the journey promises | planner, Mutator, scope |

Then decide **who computes it**: a rule that can be stated and tested is a pure
function in `backend/learning/`; only judgement and language belong to a model.

## 2. The rules that constrain the change

- **A learner decision is never evidence** (D8). `Move on anyway` and
  `mark_understood` write disposition only; settlement for an assertion comes from
  `SETTLING_OVERRIDES`. `mark_weak` is the one asymmetry, because agreeing with a
  shortfall can only lower the claim.
- **`understanding_of()` is the single owner** (D9). Never re-derive the state
  elsewhere — an AST test enforces it. `verified` is the only gap status that
  permits `understood`.
- **Readiness may fall only when evidence changes** (D7). If the change adds,
  removes, re-prioritises or re-classifies units, walk through whether a learner
  who answered nothing new can see their number drop. Remedial nodes are excluded
  from both measures and reported as detours.
- **A retry question never ships its own answer** (D10). The unit's own prompt is
  answerable exactly once, before its `reveal` has been shown; every later
  assessment comes from `/verify` or `/reassess`. A re-teach regenerates the whole
  lesson, so its new prompt arrives with a new `reveal` — it does not escape this.
- **Caps bound the system, not the learner** (D12). Reaching a cap removes a gap
  from the *active set* and writes nothing to it.
- **`optional` is off the walk, not out of the graph** (D6); no `priority` at all
  is **not** optional.

## 3. Adding a new state or a new option to a fixed vocabulary

This is the most error-prone version of the task, because the vocabulary is
parsed in two languages.

1. Extend the `Literal` / type in the backend and **every** place that switches on
   it — `understanding_of`, `progress`, `history.is_evidence`, `adaptation`,
   `retry`, `to_dict`.
2. Decide storage: a new value in an existing column needs no schema change; a new
   field does — use the `persistence-change` skill and prefer an additive nullable
   column. Old rows must still load (D18).
3. Extend the frontend: the value is a **fixed key** the UI switches on (D24), so
   add it to `lib/standing.ts`, `lib/tags.ts` or wherever it is mapped, and give it
   a label in `lib/strings.ts`. Never reword an existing key.
4. Ask what the state means for *settlement*, *completion* and *readiness* — three
   separate questions. A state that is neither settled nor unsettled makes
   `is_complete()` unreachable, which has happened.

## 4. Tell the frontend the decision, not the ingredients

If the change alters something the UI shows — whether a retry is offered, the
reason there is none, whether the objective is met, a progress number, which
action is primary — the **server** must send the decided value (D22). Add it to
`progress.summary()` or the endpoint's response, and render it. A component that
recomputes it is a seam, and every defect this rule exists to prevent was one.

## 5. Verify

Pure functions, so test exhaustively and without an API key:

```bash
uv run pytest tests/test_progress.py tests/test_understanding.py tests/test_learning_graph.py tests/test_adaptation.py tests/test_retry_dispatch.py tests/test_scope.py tests/test_decision_is_not_evidence.py tests/test_gap_understanding.py tests/test_gap_model.py -q
```

(`test_gap_understanding.py::test_every_stored_gap_free_node_derives_its_stored_state`
fails by design on a used database — `docs/testing.md` §5. Deselect it rather than
reading it as a regression.)

Then the full gate via `verify-change`, plus the frontend suite and build if the
wire changed. `tests/test_progress.py` pins every plan mutation against D7 — a
policy change that does not touch it deserves a second look.

For a substantial change, ask the **learning-engine-reviewer** agent to review the
diff before declaring it done.

## Completion criteria

- The change lives in one channel, and the other three are untouched.
- No new derivation of understanding state exists anywhere.
- You can state, in one sentence, the scenario in which readiness could fall, and
  it involves the learner answering something.
- The UI renders a decision the server made.
- The three architecture-guarding tests still pass for the right reason, not
  because they were edited.

## Common failure modes

- Making `mark_understood` write evidence "because that is what the learner
  meant".
- Adding a state and updating only the backend switch, so the rail renders the
  fallback silently.
- Excluding a node from a numerator and forgetting the denominator.
- Closing a gap from a second call site.
- Moving a rule into a prompt, where nothing can test it.
