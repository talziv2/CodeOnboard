---
name: design-a-change
description: Work out what a change to CodeOnboard should be, before implementing it. Use when the request is "design it first", "should X live in the learning graph", "should this be derived or persisted", "should the Orchestrator decide this", "would another agent help", "review this design", or any feature whose shape is not yet settled. Produces a design with alternatives and trade-offs; writes no code.
---

# Designing a change

CodeOnboard is designed before it is built, and the repository works that way: a
phase document argues the change, records the alternatives it rejected, and marks
milestones shipped; only then is there code. `docs/planning/phases/tutor.md` is the
current example, and it opens by saying that no production code, prompt, model,
flag, schema or migration is changed by it.

So when a request is about *what the behaviour should be*, do not start editing.
Design it, put the design in front of the user, and implement only what they
accept.

---

## 1. Recognise which kind of design question this is

| The question is about | Take it to |
|---|---|
| Progression, readiness, understanding, gaps, verification, retry, override, adaptation, resume, reset, node semantics | agent **learning-system-designer** |
| Who owns a responsibility, agent boundaries, LangGraph vs plain function, whether a model is needed, structured outputs, orchestration cost | agent **orchestration-designer** |
| Both — a learning behaviour that also needs a new model call or moves a responsibility | **both**, in one message so they run concurrently, then reconcile |
| "Why is it this way, and what was rejected?" | agent **architecture-historian** — usually *before* the designers |
| Where a thing goes on screen, and what a surface is for | `docs/architecture/frontend.md` + the **frontend-flow-reviewer**'s semantics |

If the question is really "is this implementation correct?", it is not a design
question — use **/review-changes**.

## 2. Establish the current model before proposing anything

Read, do not assume:

- **`.claude/reference/design-principles.md`** — DI-1…DI-12, each classified
  ① fundamental / ② current decision / ③ implementation property, plus §8's
  retracted claims.
- **`.claude/reference/state-ownership.md`** (families, transitions) and
  **`orchestration-model.md`** (placement, the two orchestrators) — whichever the
  question needs.
- The design record that owns this area (`design-history.md` §1 routes to it) —
  **including its rejected alternatives**. Most proposals have been considered
  before, and the reason one lost is usually the answer.
- `design-history.md` §2 — the responsibilities that have already moved, and what
  each move cost. If the proposal would move one back, say so.

The most common outcome of this step is that the asker's framing is wrong — the
behaviour already exists under another name, or the thing they call a UI change is
a learner-state change. Correcting the framing is often the whole deliverable.

## 3. Answer the placement questions before the design questions

1. Which **state family** does this fact belong to? (§3)
2. Which **kind of transition** is it — graph, learner-evidence,
   learner-disposition, UI? (§5)
3. **Derived or persisted?** Recomputable from stored data without loss, for every
   past session?
4. Who is the **single authority**? Would this make it computable twice?
5. Does it need a **model** at all?

## 4. Produce the design, in this shape

1. The current model, with citations
2. Where the behaviour belongs — family, authority, transition kind
3. The state transition: before → after, what is written and by whom
4. Invariants affected (DI-*, D*): preserved · at risk · violated — **each with
   its class** (① fundamental / ② current decision / ③ implementation property).
   A ③ is never grounds to refuse a design; a ② is a position to argue with
5. Alternatives — at least two real ones, including the naive one and "do nothing"
6. Trade-offs — what each buys and gives up, and the failure each would allow
7. Effects on persistence, API and frontend; old sessions must still load
8. Recommendation, and why it beats the runner-up
9. Implementation implications — modules, which skill implements it, which
   reviewer verifies it

Label claims `[FACT]` (verified here, with a file:line) · `[REC]` · `[ASSUME]` ·
`[OPEN]`. Never present an assumption as a fact.

## 5. Stop and put it to the user

**A design is a decision, and the decision is theirs.** Present it, name the
`[OPEN]` questions explicitly, and wait. Do not begin implementing a recommendation
because it is obviously right.

If the design is rejected on the grounds that it conflicts with the learning
model, say which invariant and offer the nearest design that works. "No" without an
alternative is not a design.

## 6. Where the design gets written down

- **A small change** — the design lives in the conversation, and its conclusion
  goes in the commit body, which in this repository already opens with the failure
  and the reasoning.
- **A change worth a record** — one that moves a responsibility, adds a state, or
  will be argued about again — belongs in `docs/planning/phases/`, in the house
  format: status line, what it supersedes, what it depends on, the thesis, the
  alternatives, numbered milestones, acceptance cases. Use `sync-documentation`,
  and **do not retcon it later** — record what shipped and where it diverged.

Only after the user accepts: implement with `change-learning-policy`,
`change-agent-or-prompt`, `persistence-change` or `api-endpoint`, verify with
`verify-change`, and review with **/review-changes**.

## Completion criteria

- The current model is stated with citations, and any wrong framing is corrected.
- Placement is explicit: family, authority, transition kind, derived vs persisted.
- At least two real alternatives, with trade-offs, one of them previously tried if
  the record has one.
- Every affected invariant named, classified, and marked preserved/at risk/violated.
- Nothing was refused on the strength of a ③ property or of "that is not how it
  works today".
- Readiness, resume/reset and explicability each considered explicitly.
- The user has the decision, and no code was written.

## Common failure modes

- Answering with an implementation because the change looks small.
- Proposing something the record already rejected, without saying so.
- Treating a UI phase as learner state.
- Adding a second place that derives a fact that already has an owner.
- Persisting something derivable, or deriving something whose history would be
  lost.
- Presenting one option as though there were no alternatives.
