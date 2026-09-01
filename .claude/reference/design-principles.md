# Design principles — and how much weight each one carries

> The principles a design change should be argued against. **Every one is
> classified**, because the difference between a principle and today's
> implementation is the difference between guidance and dogma.
>
> Siblings: [`state-ownership.md`](state-ownership.md) ·
> [`orchestration-model.md`](orchestration-model.md) ·
> [`design-history.md`](design-history.md)
> Implementation invariants (D1–D26): `docs/architecture/decisions.md`

| Class | Meaning | How a designer treats it |
|---|---|---|
| **① Fundamental** | The product stops being itself without it | Constrains the design. Breaking it needs an argument about what CodeOnboard *is*, not an engineering trade-off |
| **② Current decision** | Deliberate today, revisitable on evidence | Argue against it freely. Say what changed and what the old reason cost |
| **③ Implementation property** | True today, not a rule | **Never** cite as a reason to refuse a design |

§8 below lists claims that were wrongly written as invariants and have been
retracted. Read it — a retracted claim is the kind most likely to be repeated.

---

## DI-1 · One authority per fact — ①

Every fact has exactly one **authority**: the place that decides it. Anything else
holding that fact must be *derived from* the authority, not independently
reimplemented.

*Evidence:* `understanding_of()` (`graph.py:200`) is the sole owner of the state
question, with an AST test enforcing it. `retry.offer()` exists because the
decision was spread across four frontend flags and **every defect was a seam
between them**. `progress.py` owns readiness; `LearningGraph.readiness()` survives
only as a delegating alias (`graph.py:814`).

**What this does *not* say.** It does not forbid a second computation. The
cached progress columns are written *from* `summary()`; `route-sections.ts` counts
stops *the way `progress.py` counts them*. A replica is fine when its lineage runs
back to the authority. What is forbidden is a second **independent** derivation,
which will eventually disagree.

*Design test:* if this fact were wrong, is there exactly one place to fix it?

## DI-2 · Evidence and intent are distinct channels — ①

What the evidence demonstrates and what the learner decided are separate facts and
are never collapsed into one variable.

*Evidence:* `understanding_state` vs `user_override`; settlement for an assertion
comes from `SETTLING_OVERRIDES` (`graph.py:169`), not a state write.

**The strength is ② and separable.** Today a learner decision carries **zero**
evidential weight, and `mark_weak` is the one permitted asymmetry because agreeing
with a shortfall can only lower the claim. A future design could decide that
self-report is weak evidence — that is a legitimate product question. What may not
change is that the two remain **separately recorded and separately weighted**, so
the system can always say which of the two a claim rests on.

*Established by:* pressing *mark understood* on a node whose only answer was graded
`confused` turned it into a strength and moved readiness 0% → 100%.

## DI-3 · Derive what can be recomputed; persist what recomputation would lose — ①

*Design test:* can this be recomputed from what is stored, without loss, for every
past session? Then derive it. If recomputation would silently lose a fact, persist
it — once, with a named owner.

*Evidence:* `understanding_of()` is derived from stored parts. Gaps are persisted
rather than folded from `attempts`, because "this was later closed" is not a fact
about the attempt that opened it, and a fold loses a gap silently the first time it
is wrong.

**The specific placements are ②.** *Gaps persisted, understanding derived,
readiness derived-and-cached* are answers to this test given today's data, not
rules. Re-run the test; do not quote the answers.

## DI-4 · Provenance is recorded, not inferred — ①

When the system does something to a learner's route, it records **that it did
it**. Later readers must not have to reconstruct intent from shape.

*Evidence:* the Mutator writes `lesson_brief["origin"]` (`mutator.py:470`), and
`progress.remedial_ids` treats the declared value as authoritative.

**The structural inference is ③, and is a compatibility fallback only.** A warm-up
having no outgoing sequence edge while carrying an outgoing prerequisite edge is
how `remedial_ids` classifies the 62 sessions written before `origin` existed. It
is load-bearing for those sessions and **both halves are required** — the last
stop of every journey also lacks a sequence edge. Do not design new behaviour on
top of it, and do not treat topology as a provenance channel.

*Established by:* the route rail captioning nearly every planned stop "added after
confusion", because `prerequisite` edges have two producers meaning different
things.

## DI-5 · Route position and demonstrated mastery are different concepts — ①

Where a learner is on the route and what they have demonstrated are independent,
measured separately, and neither is `completed / total`.

**The rule, stated exactly** (D7): *goal readiness may fall only when evidence
about the learner changes; it must never fall because **the system** changed the
plan.*

**The carve-outs are part of the rule, not exceptions to it.** Legitimate falls,
per `learning-graph.md` §5.3: a re-answer graded worse; a gap opening; and **the
learner's own scope decision** — their action, and the UI should say the journey
grew. Illegitimate: remedial insertion, skip accounting, any denominator change
the learner did not ask for. The subject is **goal readiness**; journey progress
moves whenever the promised walk changes, including when the learner changes it.

*Established by:* remedial insertion dropped the gauge 0.50 → 0.33, so the
system's decision to help looked like the learner losing ground.

## DI-6 · Model output crosses a boundary before it becomes state — ①

A model's output is a **proposal**. Something owned by our code — validation,
grounding, sizing, or a decision — stands between it and authoritative state.

*Evidence:* a model names file+symbol and `anchors.resolve` derives the range;
the planner is given no target number and `curriculum.select()` cuts; `Gap.create`
mints ids and no model-supplied id is accepted.

**This is not "a model may never decide".** A model *may* own a decision — the
requirement is that the ownership is **explicit, bounded and evaluable**, and that
what it decides is judgement rather than a rule that could be stated and tested.
Where our code can state the rule, it should, because that is what makes the
policy testable without an API key — but "this needs judgement" is a legitimate
finding, not a failure.

*Design test:* is there a point where a model's output becomes truth with nothing
of ours in between? That is the defect. Whether the thing in between is a
validator or a policy table is a design choice.

## DI-7 · Testable policy lives in a testable place — ①

A rule that can be stated in a sentence and tested belongs in a pure module, not
in a request handler and not in a prompt.

*Evidence:* `/respond` calls `adaptation.decide_all` for the decision;
`progress.py`, `understanding.py`, `adaptation.py`, `retry.py`, `scope.py` and
`gaps.py` are pure, which is what makes the learning policy testable without an
API key.

**"The Orchestrator never decides" is ③ and was wrong.** A handler decides plenty
— which branch runs, when to answer 409, what to capture and when. Its ordering is
genuinely load-bearing (the question is read *before* a re-teach can replace
`cached_lesson`; opened gaps are a delta so the Grader is not asked for a second
copy of the same truth). The real line is *policy* versus *control flow and
capture*, not "decides" versus "does not". Where policy should live is settled by
testability, not by which file it is in.

## DI-8 · Refuse rather than fabricate — ①

When an input is absent, the system produces nothing rather than something
plausible.

*Evidence:* all anchors unreadable ⇒ the lesson **fails** rather than being
written from the objective (D3); a session with no plan answers 409 and
reconstructs nothing (D17); both planning conditional edges end the run; a schema
version mismatch reads as *missing* (D18).

*Design test:* what does this do when its input is absent? "Something plausible"
is the wrong answer everywhere in this system — it is the failure the product
exists to be better than.

## DI-9 · The system can explain what it did to the route — ①

Every change the system makes to a learner's journey leaves enough behind to
answer *"why did my route change?"*

*Evidence:* `attempts` is append-only and carries `question` and
`question_source`; `origin` records provenance and `progress.unlocks()` records
what a warm-up was for; the superseded lesson is kept when a re-teach replaces it;
`record_journey_event` (`graph.py:480`) records what the system did.

**The specific columns are ②.** The requirement is the *capability*, not this set
of fields.

## DI-10 · The learner is not asked to do our bookkeeping — ②

*Evidence:* `retry.py` dispatches between verification and re-assessment behind a
single *Ask me again* — "a learner asked to choose between them is being asked to
diagnose themselves before they are allowed another go."

**Revisitable.** This is a product stance about *this* audience. An expert mode, a
teacher view, or a debugging surface that exposes gap kinds and caps would not
violate anything fundamental. What would remain true is that the *default* path
does not require the learner to understand our vocabulary.

## DI-11 · A cap bounds the system, not the learner — ①

Reaching a cap stops the system *offering*; it writes nothing to the learner's
record, and a learner who names the thing still gets a question (D12).

*Why fundamental:* the alternative is the system marking its own homework because
it ran out of ideas. Asking is a different act from being nagged.

## DI-12 · Prefer changes that are inert for existing data — ②

Where a change can be made so that data written before it existed keeps working
without a compatibility branch somebody must remember, prefer that.

*Evidence:* `understanding_of` returns the stored value untouched when no blocking
gap exists — "no arithmetic that could drift"; `DEFAULT_PRIORITY` makes both
progress measures defined on every pre-B3 graph; fourteen additive nullable
columns.

**Revisitable, and conditional.** This is strong *today* because there is a
91-session development corpus that is also the evidence behind
`docs/planning/phases/evidence/`, and because there is no migration tooling beyond
one script. A change that genuinely needs a migration should have one — the repo
already has `001_multi_user.py`, idempotent with a dry run, and
`SUPPORTED_SCHEMA_VERSIONS` exists precisely so a version can move without
orphaning readers. Do not cite this to refuse a migration; cite it to ask whether
one is needed.

---

## 8. Retracted — claims that are not invariants

These were written as design invariants in an earlier draft and are wrong or
overstated. They are kept here because a retracted claim is the kind most likely
to be repeated.

**R1 · "Provenance lives in topology, not labels."** Backwards. Explicit `origin`
is authoritative and the structural rule is a legacy fallback (see DI-4). Encoding
this would have discouraged the very thing the code is moving toward.

**R2 · "The Orchestrator sequences and captures; it never decides."** Too
absolute; handlers decide control flow legitimately. Replaced by DI-7, which draws
the line at testable policy.

**R3 · "Nothing in the learning loop is a LangGraph node, and that is a design
decision rather than an omission."** **Unsupported by the record.** The LangGraph
migration was scoped to replacing `runner.py` for the *planning* pipeline
(`roadmap.md` §"LangGraph migration"); nothing anywhere considered and rejected
LangGraph for the learning loop. It is an accurate description of the code and an
**open question**, not a decision. See `orchestration-model.md` §3.

**R4 · "A second derivation is a defect even when it agrees."** Contradicted by
the cached progress columns and by the client's stop counter, both legitimate
replicas. Replaced by DI-1's authority-and-lineage form.

**R5 · "Prefer an additive column to a version bump" as a rule.** It is a default,
not a rule — see DI-12.

---

## How to use these in a design

State, for each principle the change touches: **preserved · at risk · violated**,
and its class. A ① that is violated needs an argument about what the product is. A
② that is violated needs an argument about what changed since it was decided —
`design-history.md` §2 has what each earlier arrangement cost. A ③ is never a
reason to refuse anything.
