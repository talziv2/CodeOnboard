# Orchestration model — how work is sequenced, and where a responsibility goes

> Read with [`design-principles.md`](design-principles.md). Siblings:
> [`state-ownership.md`](state-ownership.md) ·
> [`design-history.md`](design-history.md)
>
> §1–§2 are **descriptive**: this is how it works today. §3 is an **open
> question**, marked as one. §4 is the placement test.

---

## 1. Planning is orchestrated by LangGraph

`backend/pipeline/graph.py`, entered by `runner.run_pipeline`. One compiled
`StateGraph`:

```text
START → repo_survey → documentation → goal_investigation → [reviewer] → mentor → END
             │                              │
             └─ no skeleton → END           └─ no dossier → END
```

- **`OnboardState` (`pipeline/state.py`) is the only channel between nodes.**
  `errors` uses an `operator.add` reducer, so a node that appends in place must
  roll back or the reducer double-counts (`_extract_new_errors`).
- **Both conditional edges end the run rather than degrade it** (DI-8): no
  skeleton means anchors cannot be verified; no dossier means a curriculum would
  be fabricated. A missing *survey* is not in that category — the run continues on
  a skeleton-derived module map.
- **The Goal Agent is deliberately not a node.** It is a multi-turn HTTP dialogue
  that finishes upstream, so `goal` is finalized input by the time `invoke()` is
  called. This one *is* recorded, in `pipeline/graph.py`'s header.

## 2. The learning loop is orchestrated by FastAPI handlers

`backend/api.py`. Request-scoped, no reducer, `OnboardState` rebuilt from the
database each time. `/respond` (`api.py:1415`) is the canonical sequence, and its
ordering is load-bearing:

```text
load_graph(session_id, user_id)      ownership at the persistence boundary
set_current · require cached_lesson  409 if there is no question yet
CAPTURE the question asked           BEFORE a reteach can overwrite cached_lesson
snapshot gap ids                     so "opened" is a delta, not a second report
run_grader                           observation: classification + gap_kind + gaps
record_attempt                       append-only, with question + question_source
adaptation.decide_all(...)           the decision — a pure table
dispatch: hint | followup | reteach | prerequisite
prune_ahead                          may demote; never overrides a user choice
record journey event · save_graph(user_id)
```

Two steps exist because of specific defects: the question is captured early
because a `reteach` in the same request replaces `cached_lesson` wholesale, and
every re-taught answer would otherwise be filed against the question that replaced
the one it answered; opened gaps are a before/after delta because asking the
Grader to report them too would be *a second source of the same truth* (DI-1).

**What the handler legitimately owns:** ordering, capture, dispatch, status codes,
and not losing a grade when a warm-up fails. **What it must not own:** a rule that
could be stated in a sentence and tested — that belongs in a pure module (DI-7).

## 3. That there are two orchestrators is an observation, not a decision — **[OPEN]**

The split above is real and accurately describes the code. **It is not a recorded
design decision.** The LangGraph migration was scoped to replacing `runner.py` for
the planning pipeline (`docs/planning/phases/roadmap.md`, "LangGraph migration");
nothing in the planning corpus considered LangGraph for the learning loop and
rejected it. The loop grew as handlers.

So a proposal to move the learning loop into LangGraph must be **evaluated, not
refused**. There is no prior argument to appeal to — only the criteria in §4 and
what the change would cost. Retracted claim **R3** in `design-principles.md` is
this mistake in its earlier form.

Points a serious evaluation would have to settle:

- **What state would the graph hold?** Today each request rebuilds `OnboardState`
  from the database, and the durable state is the persisted `LearningGraph`. A
  LangGraph loop wants a checkpointer, which means a second store of session state
  beside `nodes`/`edges` — a second authority for the same facts unless the
  checkpointer *is* the store (DI-1).
- **What does a reducer buy here?** `operator.add` on `errors` exists for a
  fan-in the loop does not have.
- **Would conditional edges express the branching better than `decide_all`?** The
  policy is already a pure table; moving branching into edges could either
  document it or scatter it.
- **Ownership and multi-user.** Every entry point currently passes `user_id` into
  `load_graph`. A checkpointed graph keyed on a thread id must not become a path
  that reads session state without an owner (D20).
- **What is the cost, in complexity and in tests?** The pure-function policy suite
  runs without an API key; that property must survive.

## 4. Placement — agent, node, or plain function?

Use the criteria, not the current shape.

| Make it | When |
|---|---|
| **A pure module in `learning/`** | It is a decision that can be stated as a rule and tested. This is the default for policy |
| **A plain function / handler step** | Control flow, capture, ordering, IO sequencing |
| **An agent** (`backend/agents/<name>/`) | It owns one job and one prompt, and can meet the four conventions: injected client, never raises at its caller, never calls another agent, one `MODEL` constant |
| **A LangGraph node** | It is a stage in a **multi-step run with durable intermediate state**, whose failure should be able to terminate the run through a conditional edge, and which benefits from a reducer or a checkpointer |

The LangGraph row is written as a *property test*, deliberately. Today only the
planning pipeline has those properties; if a future part of the system acquires
them, it qualifies. "It is not how the loop works today" is not an argument.

**The bar for a new agent is high** — a new prompt, a new failure mode, a new cost
line, and a new thing that can disagree with an existing agent. Eight exist and
two call no model at all: "agent" names a responsibility, not the presence of an
LLM call. Prefer extending an agent's contract to adding a ninth, and say why the
extension does not work if you propose one.

**Before proposing any model call**, ask in order and stop at the first yes:
*(a)* can Layer A compute it — files, symbols, exact ranges, imports?
*(b)* can a pure function decide it?
*(c)* is it already in the Dossier?
What survives is judgement and language. "This needs judgement" is a legitimate
finding (DI-6), not a failure — the requirement is that the ownership be explicit,
bounded and evaluable, and that a rule which *could* be stated and tested is.

## 5. Information flow constraints

- `OnboardState` is the only channel between pipeline nodes; no agent calls
  another.
- A value needed by a later planning stage is a field on `OnboardState`.
- A value needed by an **interactive** request must ride on the **persisted
  graph**, because that state is rebuilt from the database — this is why
  `doc_context` is stored on the graph.
- Model output crosses a trust boundary: a Pydantic model, `Literal` where the
  vocabulary is fixed, and a defined behaviour for a truncated or malformed
  response. Widening a `Literal` widens it in both languages.
- **Exhaustion is a result, not an exception** (D25): a partial with an honest
  `stop_reason`, `accepted: false` propagating into confidence, uncertainty in
  `open_questions`.

## 6. Cost is part of the design

How often does it run, per what, and against which measurement? Baseline ≈$0.405
warm for a 12-unit session (`docs/planning/phases/cost-optimization.md`). A
per-answer call costs very differently from a per-session one. Sonnet is currently
used only for one-shot synthesis over a large body of evidence — two modules;
Haiku everywhere else including every loop. Cost is a metric, not a design
constraint (D26): do not optimise a number nobody has measured, and do not add one
without saying what it will cost.
