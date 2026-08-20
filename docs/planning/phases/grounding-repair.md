# Grounding Repair — making the next E2E a validation run

> **Status: PLANNING ONLY.** No production code, prompt, schema, flag or
> migration is changed by this document.
> **Evidence of record:** [`evidence/manual-e2e/SYNTHESIS.md`](evidence/manual-e2e/SYNTHESIS.md)
> and the 95 findings in [`evidence/manual-e2e/README.md`](evidence/manual-e2e/README.md),
> plus **F96–F109** in [§11](#11-second-pass-findings--remediation-flow-route-order-briefing-f96f109),
> recorded from a continued run on the same session.
> **Depends on:** `learning-engine.md` (complete), `gap-model.md` (closed — this
> document **reopens** part of it), `learning-graph.md` (M3b shipped, unvalidated).
> **Last updated:** 2026-08-19

**What this phase is.** The manual E2E round did its job and found that several
components produce confident output without the evidence needed to be right, and
that grading is measured against the system's own generated objective rather than
against the repository. This phase repairs those contracts so that the **next**
E2E round is a validation run rather than a second defect-discovery run.

**What this phase is not.** It is not a feature phase, not a UI phase, and not a
re-plan of the curriculum. It does not touch goal elicitation, the Dossier, the
Survey, or planner sizing. Where the E2E found a product question rather than a
defect, it is recorded in [§9](#9-open-decisions) and **not** silently decided.

**Labelling.** **[FACT]** verified in this repository against code or stored state
· **[REC]** a recommendation · **[DECISION]** proposed contract, needs sign-off ·
**[OPEN]** genuinely undecided product question.

---

## 1. Current state and evidence

### 1.1 What the E2E proved

One session, 17 planned units + 2 warm-ups, 13 answered, 95 findings. Four
results are load-bearing for this plan:

| # | result | evidence |
|---|---|---|
| 1 | **Grading measures conformity to the generated objective, not the repository.** A false answer matching a false objective was graded `understood`; a true answer exceeding an oversimplified objective was graded `partial` and given a gap | F82, F59, and **F85** — the same claim graded both ways in one session, each verdict tracking a different unit's objective |
| 2 | **Anchor coverage predicts *mechanism* accuracy. Nothing predicts *property* accuracy.** Three controlled comparisons establish the first; a false O(log n) claim made with the contradicting source anchored establishes the second | F27, F54, F41 / **F71** |
| 3 | **Verification is corruptible.** A gap was marked `verified` by an answer that restates it | **F90** |
| 4 | **The system has no representation for its own error**, so its analytics attribute system defects to the learner | F26, F95 |

**[FACT] A fifth result matters for how we fix, not what.** Most components
obeyed their contracts: Teaching built exactly the objective it was given (F2),
the Mutator followed §18.5's one-mutation cap (F31), the Grader applied its stated
standard (F82). **The contracts carried the defects.** Per-component prompt
patching will therefore not work; the fixes belong at the boundaries.

### 1.2 Prior claims this round invalidates — explicit reopening

**Nothing below is downgraded to protect a milestone's status.**

| claim | status | why |
|---|---|---|
| **gap-model M6 — "AC2 validated live"** (double dissociation: holding fails, corrected passes) | **REOPENED** | F90: a holding answer passed. AC2 must be re-run after R3 |
| **gap-model M2 addendum — "true statements are excluded from the gaps list"** | **REOPENED** | F20 and F59 both recorded true statements as gaps. The rule exists in the prompt and is not enforced |
| **gap-model limitation #1 — AC1 detection variance, "not blocking until a real learner session shows it materially affecting learning"** | **BAR MET** | F49 (3 misconceptions in, 1 gap out) plus F50 (the re-teach then adopted an undetected error) |
| **gap-model limitation #3 — `right_idea_wrong_altitude` is "nearly unreachable"** | **CONTRADICTED** | F59/F60: it fired on a true statement, i.e. via the route the limitation assumed closed |
| **learning-graph M3b — gap-derived insight** | **UNVALIDATED, one template uncomputable** | F31/F74: `remediation_closure` counts warm-ups carrying `remediates`; the commonest gap kind can never produce one |
| **learning-graph M3a.2 patterns + metric 20** | **INPUTS UNSAFE** | F95: five of this session's grading events were defective in four directions; the templates read them as learner difficulty |
| **learning-engine §14 item 12** — "every anchor on every unit resolves … display columns equal one member of `anchors`" | **HOLE** | F34: Mutator-created nodes carry `anchors: None`, so the invariant is vacuous on every remediation node |
| **learning-engine §14 item 16 — cost** | **STILL OPEN, and this phase adds to it** | R2/R3 send source to grading; see [§8](#8-cost) |
| **learning-engine §14 item 8** (return to the failed node) | **HOLDS** | observed working in this round; not reopened |
| **learning-engine §14 item 11** (`prompt_kind` ≥ 4 values) | **NEWLY CONFIRMED** | F56 — first live verification in the project record |

### 1.3 Two corrections to `SYNTHESIS.md`, found by reading the code

The synthesis is evidence plus strong recommendations. Two of its recommendations
do not survive contact with the implementation:

**[FACT] C1 — F90 cannot be fixed by prompt wording, because the wording is
already correct.** `verification._SYSTEM`
([verification.py:62-106](../../../backend/agents/grader/verification.py)) already
says: *"What is required is that the reasoning they DO show is incompatible with
holding it"*, and `resolved: false` — *"Use this when the answer still shows the
belief."* The model violated an explicit, well-written instruction. **The
safeguard must be structural.** This changes R3 from "instruct better" to "make
the schema unable to express an unevidenced resolution".

**[FACT] C2 — the Grader cannot be handed source without plumbing.**
`/respond` builds `OnboardState` **without `repo_path`**
([api.py:836](../../../backend/api.py)) before calling `run_grader`. Teaching gets
its path from `_render_current_lesson`, which calls `clone_repo` (a no-op when
already cloned). R2 therefore includes a small plumbing step, not just a prompt
change.

**[FACT] C3 — the natural home for plan-time checks already exists.**
`curriculum.ground()` ([curriculum.py:503-563](../../../backend/agents/mentor/curriculum.py))
already holds the `Skeleton`, the dossier evidence and every objective's anchors,
and already resolves and filters. `ObjectiveWire.depends_on` and `order()` supply
the prerequisite closure and the walk. R1 needs no new infrastructure.

---

## 2. Scope

### 2.1 Required before the next E2E

Anything whose absence would make the next round re-discover a known systemic
defect rather than validate a fix.

- **R0** instrumentation and evidence preservation
- **R1** plan-time grounding invariants
- **R2** grounded grading (assessment + verification)
- **R3** verification integrity
- **R4** property-claim safeguard
- **R5** gap-detection correctness
- **R6** remediation linkage
- **R7** walk and state correctness
- **R8** learner recovery (`disputed`)
- **R9** remediation flow and gap-specific resolution ([§11.7](#r9--remediation-flow-and-gap-specific-resolution))

R8 is in the gate for a reason that is not UX: without it the next round has **no
honest way to record a system error**, which is exactly the measurement the round
exists to take.

R9 is in the gate for a related reason: the next round cannot exercise verification
at all from the screen where it matters ([F98](#112-symptoms-1--2--the-warm-up-and-retry-flow)),
so R3's integrity fixes would go unvalidated. The same section's **C9** lost-update
defect can silently erase the evidence every other milestone depends on.

### 2.2 Important, may follow later

- Re-render or re-phrase corrective lessons once their gaps close (F35–F37) — see [OQ-4].
- Curriculum scope/coverage rebalancing (F92) — a product decision, [OQ-5].
- `remediates` widening beyond one gap per mutation (§18.5's cap) — [OQ-6].
- Cross-unit consistency checking over units sharing an anchor (F12, F16, F46).
- Persisting and surfacing an audit view of verification closures beyond R0's storage.

### 2.3 Explicitly out of scope for this phase

- Rail copy and state vocabulary (F38), area-introduction behaviour, gap-surface polish, drawer conditions. **Except** where a UI defect changes what the learner is *taught or graded on* — F19's rail/walk order disagreement is in scope (R7) because it caused a false `why_now` claim and an orphaned required stop.
- Prose line-citation validation (F63, F70). Mitigated by preferring anchor-relative references; not gated.
- Any cost optimisation. This phase **adds** cost and hands the number to `cost-optimization.md`.
- Multi-language work, planner sizing, the Dossier, the Survey.

---

## 3. Root-cause architecture

### 3.1 The six causes and the contract each violates

| cluster | root cause | contract that is wrong | findings |
|---|---|---|---|
| **A. Ungrounded grading** | Grader and verification grader receive the objective as *"the marking standard"* and **no repository source** | the marking standard is a generated artifact, not the code | F20, F59, F82, F85, F90, F49 (partly) |
| **B. Per-unit, claim-blind anchoring** | anchors are chosen for a unit with no check that they cover what the unit claims, and no memory of what the walk has already anchored | "a unit is grounded" means "≥1 anchor resolves", not "its claims are covered" | F1, F11, F21, F27, F28, F39, F43, F44, F45, F58, F65, F75, F79, F92 |
| **C. Property claims are prior-driven** | complexity/optimality/termination are *conclusions about* code; the model states the textbook conclusion | no contract distinguishes describing code from concluding about it | F57, F58, F61, F67, F71, F77, F79, F81, F86, F89 |
| **D. One payload, no self-comparison** | `setup`/`reveal`/`takeaway`/`objective` generated together, never compared | none — nothing owns intra-lesson consistency | F2, F7, F33, F51, F55, F57, F62, F83, F86 |
| **E. Assessment ⊄ objective** | Teaching writes one question from a multi-clause objective; the Grader marks the whole objective | B1's contract says objective is shared; it does not say the question must cover it | F31/F32, F56, F80, F87 |
| **F. State records conclusions, not learner recovery** | `visited` written by one endpoint; rail orders by area, walk by chain; no "system was wrong" state | the graph models the plan and the verdict, not the learner's history | F17, F18, F19, F26, F35, F36, F38, F94 |

### 3.2 The causal chains, by component

```
Planner ──────────────► Teaching ──────► Grader ──────► Gap Model ──► Mutator ──► Analytics
   │                        │               │              │             │            │
 objective names `h`    anchors lack     no source;    gap opened    warm-up      "component
 outside its anchors    the claimed      objective IS  on a TRUE     built for    objectives
 (F1, F22)              mechanism        the standard  claim         a fabricated need more
                        (F21, F44)       (F23)         (F20, F59)    gap (F73)    attempts"
                            │               │              │             │          (F95)
                            └──► "h returns 0" ──► correct answer ──► blocking ──► no `remediates`
                                  (F20, F29)        marked wrong       gap open      (F31, F74)
                                                          │
                                                    no dispute path (F26)
```

**Chain 1 — one false proposition, seven surfaces.** *"Missing `locations` makes
A\* degrade to UCS"* originates in a planner objective (F22), is confabulated
independently by Teaching where `h` is unanchored (F20, F29), enters the Grader's
rubric, produces a blocking gap on a **true** learner claim (F20), then appears in
a later unit's lesson (F79) where a **wrong** answer matching it is graded
`understood` (F82), is graded a misconception two stops later (F85), and is
finally "verified" as resolved by an answer that restates it (F90). **No surface
can check another.**

**Chain 2 — anchor borrowing → perceived misordering.** Per-unit anchors let stop 3
borrow stop 4's entire anchor (F11) → declared prerequisites under-specify actual
dependence (F28) → the rail groups by area while the walk follows the chain (F19)
→ the learner follows the rail → `why_now` asserts a transfer that never happened
(F10) → the skipped stop is orphaned permanently (F17).

**Chain 3 — inference becomes curriculum.** The Grader infers list semantics from
the word "append" (F68) → blocking gap on a claim never made → learner requests a
warm-up → the warm-up is well-built *for the stored gap* (F73) → carries no
`remediates` (F74) → contradicts the unit it unlocks (F75) → **a misconception the
learner never held is a numbered stop in the curriculum** (F94).

### 3.3 What each component receives today

| component | repository source | consequence |
|---|---|---|
| Planner (`curriculum.py`) | Dossier + Skeleton; anchors resolved in `ground()` | writes objectives naming symbols the unit will not anchor (F1, F22) |
| Teaching (`teaching/agent.py`) | **every anchor, in order** (`_read_node_source`) | correct inside anchors, confabulates outside; cannot decline (F71b) |
| Re-teach (`teaching/respond.py`) | unit anchors + answer + rationale + gaps | same, and can adopt a learner's error (F50) |
| **Grader** (`grader/agent.py`) | **none** | objective-conformity is the only available standard (F23) |
| **Verification** (`grader/verification.py`) | **none** | cannot notice an answer restating the gap (F25, F90) |
| Mutator (`mentor/mutator.py`) | candidate chunks | writes nodes with `anchors: None` + deprecated `understand` (F34) |

---

## 4. Design decisions

### D1 — Grading is graded against source; the objective becomes a *lens*, not the standard

**[DECISION]** Both graders receive the unit's anchor source. Precedence is stated
in the prompt and enforceable in the schema:

1. **The repository is the standard.** A claim true of the anchored source is
   never a gap, even when the objective does not ask for it (F59).
2. **A claim false of the anchored source is a gap, even when it matches the
   objective** (F82).
3. **The objective decides *relevance*, not *truth*** — it still selects what the
   answer was supposed to address, which is what keeps `off-topic` meaningful.
4. When the answer concerns code **outside** the anchors, the Grader must mark on
   the objective alone and **say so** in a new output field (see D2).

**Which source.** The unit's own anchors, exactly as `_read_node_source` assembles
them for Teaching — not the whole file, not the dossier. Rationale: it is the same
evidence the lesson was built from, so a mismatch between lesson and source becomes
*detectable* rather than invisible; and it bounds the token cost to something
already paid once per unit.

**Alternatives considered.**

| option | why not |
|---|---|
| Send the whole file | unbounded cost; and it would let the Grader mark on material the lesson never taught |
| Send the dossier slice | goal-scoped, not claim-scoped; F58's missing evidence (`best_first_graph_search`) is in neither |
| Keep the Grader sourceless and fix objectives only (R1 alone) | R1 cannot fix F82 — the objective *was* the defect, and nothing downstream could contradict it |

**[FACT] Cost is real and per-answer.** See [§8](#8-cost).

### D2 — The Grader must state what it graded against

**[DECISION]** `GraderOutput` gains `grounded_in: "source" | "objective_only"` and,
when a gap is opened, a required `contradicted_by` field naming the anchored
symbol/line range whose behaviour the claim contradicts — or the explicit value
`objective_only`.

This is the enforcement half of D1: a gap that cannot name what the learner
contradicted is a gap the Grader inferred rather than observed (F68). It is also
the instrument R5 needs to *measure* false-positive rate without human review.

### D3 — Verification cannot resolve a gap without quoted contradicting evidence

**[DECISION]** `GapVerdict` gains `contradicting_span: str` — a **verbatim
substring of the learner's answer** that is incompatible with the gap's claim.
`mark_verified` is only reachable when:

- `resolved is True`, **and**
- `contradicting_span` is non-empty, **and**
- the span is literally present in the answer (deterministic check in Python), **and**
- the span is not a restatement of the claim (see below).

**[FACT] This is deliberately not a prompt fix (C1).** The prompt already says the
right thing and was ignored. Making the schema unable to express an unevidenced
resolution is the only enforcement available that does not cost a second call.

**The restatement check.** Deterministic string similarity is brittle. **[REC]**
The first cut is the span requirement alone — in F90 the answer contained **no**
span incompatible with the claim, so the requirement is sufficient for that case.
A similarity guard is a follow-up only if R3's re-run shows spans being fabricated.

**Alternative considered:** a second adversarial call ("does this answer assert the
claim?"). Rejected as the default — it doubles verification cost for a case the
schema can catch — but retained as the fallback if D3 fails its gate.

### D4 — Three plan-time grounding invariants, enforced in `ground()`

**[DECISION]** All three are computed against the `Skeleton` that `ground()`
already holds.

| # | invariant | on violation |
|---|---|---|
| **G1** | every symbol named in an objective must resolve within **that unit's own anchors** | drop the anchor-less symbol reference, or demote the unit and record it |
| **G2** | a unit's anchors must lie within the symbols of the unit itself or of its `depends_on` closure | record and flag; do not auto-drop (a legitimate synthesis unit spans everything) |
| **G3** | a symbol a unit makes claims about must be anchored **on that unit or on an earlier unit in `order()`** | reorder if the dependency is expressible; otherwise demote to `optional` and record |

**[DECISION] Forward *reference* is legal; forward *dependence* is not.** A unit
may name a symbol it does not anchor when it does so to point ahead ("…so that
`GraphProblem` can later supply `h`"). It may not **make a claim about that
symbol's behaviour**. G1 is therefore scoped to symbols the objective makes a
behavioural claim about, and G3 is the rule that operationalises the distinction:
naming is free, depending is not.

**[FACT] G1 needs a symbol recogniser, and that is the honest weak point.** The
objective is prose; extracting "symbols it makes claims about" is not free.
**[REC]** Use the Skeleton as the dictionary: tokenise the objective, keep tokens
that resolve to a known qualified symbol, ignore everything else. This under-fires
(it will miss "the heuristic") rather than over-fires, which is the correct
direction for a gate that can demote units. G3 then catches most of what G1 misses,
because it works from anchors rather than prose.

### D5 — Property claims are constrained, not forbidden

**[DECISION]** Teaching is instructed that complexity, optimality, termination and
absolute qualifiers ("always", "never", "silently", "guarantees") may only be
asserted when the anchored source *states or exhibits* them; otherwise describe the
mechanism and stop. Enforcement is **detection, not prevention**: a deterministic
lint flags property vocabulary in `reveal`/`takeaway`/`expected_answer`, and the
flagged set is what the eval harness reviews.

**[FACT] This cannot be made deterministic.** No static rule decides whether
"O(log n)" is true. F71 shows the model asserting a complexity contradicted by the
anchored source; F77 shows it asserting a false property of *Python*, where no
anchor could ever help. **[REC]** Accept a model-backed gate here, and set the bar
by measurement rather than by aspiration — see [§6](#6-testing-strategy).

### D6 — A gap must be attributable to something the learner wrote

**[DECISION]** `GapOut` gains `learner_span: str` — a verbatim substring of the
answer that expresses the claim. A gap whose span is absent from the answer is
**dropped in code**, exactly as an invalid `refers_to` id is dropped today (§3.2's
existing discipline).

Addresses F68 directly, and it is the same enforcement shape as D3 — the round
found two independent cases (F68, F90) where the model asserted something about an
answer that the answer did not contain, and in both the evidence needed to catch it
was already in the prompt.

### D7 — Multi-gap recall is a measured property, not a prompt hope

**[DECISION]** `gap-model.md`'s AC1 is re-armed with a **standing eval set** rather
than a one-off acceptance run: answers carrying *N* known independent
misconceptions, scored on recall per misconception. The existing
`scripts/grader_eval.py` + `grader_eval_cases.py` harness is extended rather than
replaced.

**[FACT] Source will not fix this.** In F49 the correct condition (*"admissible"*)
was already in the objective the Grader held. This is recall, and recall is
measured or it is not known.

### D8 — Attempts carry an attribution, and analytics ignore un-attributed events

**[DECISION]** `attempt["attribution"]` with a closed vocabulary:

| value | meaning |
|---|---|
| `learner_gap` | genuine misunderstanding |
| `defective_question` | the question or objective was wrong/ambiguous |
| `grader_false_positive` | wrong answer accepted |
| `grader_false_negative` | correct answer rejected |
| `grounding_defect` | expected model contradicted the repository |
| `unknown` | not yet classified — **the default** |

**[DECISION] `unknown` is excluded from every learner-facing metric**, in the same
way M2's `instrumented()` excludes un-instrumented attempts. This is the invariant:
**a metric may never treat an unclassified attempt as learner difficulty.**

**How attribution is set.** Three sources, in order of trust: (1) a learner dispute
(R8) sets it directly; (2) D2's `grounded_in: "objective_only"` plus a later
contradiction flags candidates; (3) manual labelling during E2E. **[REC]** No model
call. Auto-classification is explicitly deferred — the E2E showed the model is not
a reliable judge of its own errors.

### D9 — Every warm-up records what it remediates, or records that it is unaimed

**[DECISION]** `lesson_brief["remediates"]` is **always** written: a list of gap
ids, or `[]` with a sibling `remediates_reason` (`"no_prerequisite_gap"`,
`"learner_request_unaimed"`). Removes the silent hole at F31/F74 and makes M3b's
`remediation_closure` computable — it can then count *aimed* warm-ups and report
unaimed ones separately instead of counting nothing.

**[DECISION] The one-gap cap (§18.5) is not changed here.** It is a deliberate
policy and widening it is [OQ-6]. What changes is that "no gap was designated" stops
being indistinguishable from "the field was never written".

### D10 — Jump is a detour, not a skip

**[DECISION]** A forward `jump` does not remove intervening stops from the journey.
`resume_point()` and completion return to unfinished **`required`** stops; `visited`
gains a companion meaning rather than being overloaded:

- `visited` keeps its current meaning (advanced through) — the progress measures already depend on it not changing;
- studying a stop from the rail records a **`studied`** marker on the node, which `resume_point()` consults so a returning learner is not sent back to a lesson they completed (F18).

**[DECISION] The rail must present the walk order.** `buildSections` groups by area
across the whole route; when the planner interleaves areas the two orders disagree
(F19). Either the rail renders sections in walk order (repeating an area header when
the walk returns to it), or the planner is required to emit contiguous areas.
**[REC] the first** — it is a render change over the same data and does not
constrain the planner. See [OQ-3].

### D11 — `disputed` is a first-class gap status

**[DECISION]** `Gap.status` gains `disputed`. Semantics:

- set only by an explicit learner action;
- **non-blocking** — it does not withhold `understood`, so the learner is unblocked immediately;
- **not evidence** — it does not count as `verified` and never supports mastery;
- **retained and reported separately** in `gap_insight`, because a disputed gap is a labelled instance of F20/F59/F68 and is the single most valuable signal the system can collect about itself;
- sets `attempt["attribution"]` on the originating attempt (D8).

**[FACT] The lifecycle currently has no state for "the system was wrong" (F26).**
Every existing affordance presumes learner fault: verification closes only by
asserting the falsehood, waiving records *"you chose not to pursue this"* and caps
the stop, and `mark_understood` cannot override the block.

---

## 5. Milestones

Ordered so that no downstream behaviour is repaired while its upstream contract is
still wrong.

### R0 — Instrumentation and evidence preservation *(no behaviour change)*

| | |
|---|---|
| **Goal** | be able to tell system error from learner error, and audit a verification closure, before changing any grading behaviour |
| **Components** | `backend/learning/history.py`, `backend/learning/gaps.py`, `backend/agents/grader/verification.py`, `backend/learning/store.py` |
| **Changes** | `attempt["attribution"]` vocabulary (D8, default `unknown`); persist the verification **question** on the attempt (F91); `gap_insight` and the progress/pattern modules exclude `unknown` from learner-facing metrics |
| **Invariants** | no metric counts an `unknown`-attribution attempt as learner difficulty; every stored session loads and round-trips byte-identically |
| **Tests** | attribution round-trip; every existing metric re-asserted against a fixture where all attempts are `unknown` (expect: they report *insufficient evidence*, not zero); verification question survives save/load |
| **Migration** | additive JSON on the attempt envelope, as M2 established. **No `SCHEMA_VERSION` bump.** Pre-R0 attempts read as `unknown` |
| **Done when** | the full corpus loads unchanged; a stored session can answer "was this attempt the learner's fault?" with `unknown` rather than silently with `yes` |

### R1 — Plan-time grounding invariants *(deterministic, upstream of everything)*

| | |
|---|---|
| **Goal** | a unit may not make claims whose evidence it does not anchor, or depend on a symbol first anchored later |
| **Components** | `backend/agents/mentor/curriculum.py` (`ground()`, `order()`, `dependency_closure()`), `backend/repo/anchors.py` |
| **Changes** | G1/G2/G3 (D4) with the Skeleton-as-dictionary symbol recogniser; violations recorded in the plan report, not silently dropped |
| **Invariants** | **no unit's objective makes a behavioural claim about a symbol anchored neither on it nor earlier in `order()`**; grounding still never admits an ungrounded unit (LD13 unchanged) |
| **Tests** | synthetic `Skeleton.from_chunks` fixtures (the `test_anchors.py` pattern) — **no `aima-python`**: forward reference permitted, forward dependence rejected, symbol anchored later triggers reorder-or-demote, symbol in the same file but outside the anchor range rejected (**F45**, missed by two lines), symbol seventy lines outside rejected (**F39**) |
| **Migration** | plan-time only; existing graphs unaffected. Under `CODEONBOARD_CURRICULUM=0` the checks do not run |
| **Done when** | replaying the E2E's own objectives through `ground()` flags F1, F22, F39, F44, F58 and F92's survey unit, and passes the units the round found correct (F41, F43, F54, F56) |

### R2 — Grounded grading

| | |
|---|---|
| **Goal** | the repository, not the objective, decides truth |
| **Components** | `backend/agents/grader/agent.py`, `backend/agents/grader/verification.py`, `backend/api.py` (the C2 plumbing), `backend/agents/teaching/agent.py` (`_read_node_source` reuse) |
| **Changes** | D1 precedence + anchor source in both grading calls; D2 `grounded_in` / `contradicted_by`; set `state.repo_path` in `/respond` via `clone_repo` |
| **Invariants** | a claim true of the anchored source is never a gap; a claim false of it is a gap regardless of the objective; when the answer concerns unanchored code the Grader says `objective_only` rather than guessing |
| **Tests** | **deterministic:** source is present in the user content; `objective_only` is set when the node has no readable anchors; a Teaching failure to read source does not silently degrade grading. **Model-backed:** the F59 case (correct refinement beyond the objective → **not** a gap), the F82 case (false answer matching a false objective → **is** a gap), and the existing 48-case Grader eval re-run to confirm no regression on the M2 gate band |
| **Migration** | none — additive prompt/schema. Flag-off behaviour is unchanged because `CODEONBOARD_GAPS` does not gate source |
| **Done when** | F59 and F82 both invert on the stored answers, and the 48-case eval is within the recorded band (classification ≥46/48, `gap_kind` ≥45) |

### R3 — Verification integrity

| | |
|---|---|
| **Goal** | a gap cannot be closed by an answer that preserves it |
| **Components** | `backend/agents/grader/verification.py`, `backend/learning/gaps.py` (`mark_verified` precondition) |
| **Changes** | D3 `contradicting_span`, verified as a literal substring in Python before `mark_verified` is reachable |
| **Invariants** | **`verified` implies a stored, verbatim span from the answer that contradicts the claim**; a failed span check resolves nothing and charges no verification attempt (the existing "grading hiccup must not cost the learner" rule) |
| **Tests** | **deterministic:** fabricated span rejected; empty span rejected; span present but `resolved: false` changes nothing; a rejected verdict leaves `verification_attempts` untouched. **Model-backed:** the F90 answer must now fail; gap-model **AC2's double dissociation re-run** on ≥2 nodes |
| **Migration** | pre-R3 `verified` gaps carry no span. **They are not retro-invalidated silently** — `gap_insight` reports them as `verified_legacy` so the one false closure in the corpus cannot be counted as evidence |
| **Done when** | AC2 passes again with the span requirement in place, and the stored F90 answer is rejected |

### R4 — Property-claim safeguard

| | |
|---|---|
| **Goal** | stop asserting guarantees the source does not support |
| **Components** | Teaching prompts; a new deterministic lint over generated lesson fields |
| **Changes** | D5 instruction + property-vocabulary lint feeding the eval harness |
| **Invariants** | none enforceable in code — **stated plainly**; the lint is a detector, not a gate |
| **Tests** | **model-backed only.** A standing probe set of units whose anchored source contradicts the textbook answer — F71 (`__delitem__` is O(n), not O(log n)), F58 (admissibility vs consistency under a no-reopen explored set), F79 (all-`inf` frontier orders by `Node.__lt__`, not by cost). Scored as: does the lesson assert the textbook property, hedge, or describe the mechanism? |
| **Migration** | none |
| **Done when** | the three probe cases stop asserting the false property in ≥ the agreed proportion of runs — a number to be **set from a baseline measurement**, not chosen in advance |

### R5 — Gap-detection correctness

| | |
|---|---|
| **Goal** | gaps record what the learner actually claimed, and false ones are structurally rarer |
| **Components** | `backend/agents/grader/agent.py`, `backend/learning/gaps.py`, `scripts/grader_eval*.py` |
| **Changes** | D6 `learner_span` with a code-level drop; D7 standing multi-gap recall set; the M2 addendum's "true statements are not gaps" rule re-expressed as a **precedence rule against source** (D1) rather than an unenforced instruction |
| **Invariants** | **a gap whose `learner_span` is absent from the answer is dropped in code**; a claim true of the anchored source is never recorded as a gap |
| **Tests** | **deterministic:** span-absent gap dropped; span present but paraphrased still dropped (verbatim rule); dropping a gap does not disturb the others (the existing `refers_to` discipline). **Model-backed:** the F68 answer produces no gap; the F20 answer produces no gap; multi-gap recall on the F49 answer (3 misconceptions) measured, not asserted |
| **Migration** | pre-R5 gaps have no `learner_span`; they are retained and reported, never retro-dropped |
| **Done when** | F20 and F68 produce zero gaps on their stored answers, and the multi-gap recall number is **recorded** (a measurement, not a threshold, on first run) |

### R6 — Remediation linkage

| | |
|---|---|
| **Goal** | every warm-up says what it is for, and passing one means something |
| **Components** | `backend/agents/mentor/mutator.py`, `backend/api.py` (`/retry`), `backend/learning/gap_insight.py` |
| **Changes** | D9 always-written `remediates` / `remediates_reason`; Mutator-created nodes gain a real `anchors` list, closing §14 item 12's hole (F34) |
| **Invariants** | `lesson_brief["remediates"]` is present on **every** node with a remedial `origin`; the display-anchor invariant (`file`/`line_start`/`line_end` equal one member of `anchors`) holds for Mutator-created nodes too |
| **Tests** | `remediates` present for both aimed and unaimed paths; `remediates_reason` set exactly when the list is empty; `gap_insight.remediation_closure` counts aimed warm-ups and reports unaimed separately; the display-anchor invariant asserted on a mutated graph |
| **Migration** | pre-R6 warm-ups have neither field; `gap_insight` treats absent as `unknown`, never as unaimed |
| **Done when** | replaying the E2E's two warm-ups yields `remediates_reason: "no_prerequisite_gap"` rather than silence, and M3b's template is computable |

### R7 — Walk and state correctness

| | |
|---|---|
| **Goal** | the journey the learner is shown is the journey the system walks, and no required stop is silently lost |
| **Components** | `backend/learning/graph.py` (`next_in_path`, `resume_point`, `is_complete`), `backend/api.py` (`/jump`), `frontend/lib/route-sections.ts` |
| **Changes** | D10 — jump as detour; `studied` marker; rail renders walk order |
| **Invariants** | **a `required` stop cannot be permanently unreachable by the walk**; `resume_point()` never returns a stop the learner has already completed; **rail order equals `path_order()`** |
| **Tests** | jump forward past a required stop → completion still returns to it; jump past an `optional` stop → it stays stepped over (§6.3 unchanged); a stop studied from the rail and answered is not re-offered by `resume_point()`; a frontend test asserting section order equals walk order on an interleaved-area graph (**F19**) |
| **Migration** | `studied` is additive on the node; pre-R7 graphs have it absent, read as unknown and falling back to today's behaviour |
| **Done when** | the E2E's own graph (2 orphaned stops, one `required`) resolves to a complete-able journey on replay |

### R8 — Learner recovery

| | |
|---|---|
| **Goal** | the learner can say the system is wrong, and the system can record it |
| **Components** | `backend/learning/gaps.py`, `backend/learning/graph.py`, `backend/api.py`, `frontend` gap surface |
| **Changes** | D11 `disputed` status + a dispute action; sets `attempt["attribution"]` (D8) |
| **Invariants** | `disputed` is non-blocking, is never evidence, is never produced by a model, and is reported apart from `verified` and `waived` |
| **Tests** | disputing a blocking gap unblocks the node without conferring `understood`; a disputed gap never counts toward mastery or toward `gap_outcomes`' verified column; disputing sets the originating attempt's attribution |
| **Migration** | additive status; `understanding_of` treats unknown statuses conservatively today, so pre-R8 sessions are unaffected |
| **Done when** | the two false gaps still open in session `cff533a5` (F20, F59) can be recorded as disputed, and the session's analytics stop attributing them to the learner |

---

## 6. Testing strategy

### 6.1 Deterministic first, and most of it can be

| fix | deterministic? | how |
|---|---|---|
| R1 G1/G2/G3 | **yes, fully** | synthetic `Skeleton.from_chunks` fixtures; no API key, the bar this project already uses for sizing logic |
| R3 span requirement | **yes** for the substring and precondition; model-backed for the verdict quality | Python check before `mark_verified` |
| R5 `learner_span` drop | **yes** | substring check in the parse path |
| R6 `remediates` presence | **yes** | structural assertions on a mutated graph |
| R7 walk semantics | **yes** | graph-level tests, no model |
| R8 `disputed` semantics | **yes** | status transition tests |
| R0 attribution exclusion | **yes** | metric tests over an all-`unknown` fixture |
| R2 precedence | **no** — delivery is testable, judgement is not | 48-case eval + the F59/F82 inversions |
| R4 property claims | **no** | probe set, scored proportionally |
| R5 multi-gap recall | **no** | standing eval set (D7) |

### 6.2 Regression cases mapped to findings

Each is a stored answer from session `cff533a5`, replayed:

| finding | regression assertion |
|---|---|
| **F20** | the `np.inf` answer produces **no** gap and is not `wrong_model` |
| **F59** | the consistency refinement produces **no** gap |
| **F82** | the "A\* becomes UCS, result correct" answer **is** marked short |
| **F85** | the *same* claim receives the *same* verdict at both stops |
| **F90** | the restating verification answer **fails** to resolve |
| **F68** | no gap is opened whose text is absent from the answer |
| **F49** | recall over the 3-misconception answer is measured and recorded |
| **F17/F18/F19** | orphaned required stop reachable; rail order equals walk order; a rail-studied stop is not re-offered |

### 6.3 Avoiding overfitting to `aima-python`

**[FACT] This is a real risk and the round itself proved it (F41):** the model's
prior knowledge of `aima-python` masks grounding defects.

1. **Deterministic tests use synthetic skeletons only** — the `test_anchors.py`
   fixture pattern. No test in R1, R6, R7, R8 may reference `aima-python`.
2. **The stored E2E answers are regression fixtures, not the eval set.** They prove
   specific defects do not return; they do not measure quality.
3. **Model-backed gates run on ≥2 repositories**, at least one of which is **not**
   `aima-python` and preferably not a famous teaching repository.
4. **The property probe (R4) is constructed from cases where the textbook answer is
   wrong for the implementation** — that construction is repo-specific by nature, so
   the probe set must be rebuilt per repository rather than reused.

---

## 7. Re-validation gate

### 7.1 What must be true before the next manual E2E

| # | condition |
|---|---|
| 1 | R0–R8 shipped, with their deterministic tests green and the full suite passing |
| 2 | **gap-model AC2 re-run and passing** with R3's span requirement — the double dissociation on ≥2 nodes |
| 3 | The 48-case Grader eval re-run and within the recorded band, **with source present** |
| 4 | Multi-gap recall (D7) **measured and recorded** — a baseline, not necessarily a pass |
| 5 | The eight regression cases in §6.2 all invert or hold |
| 6 | The corpus's one false `verified` gap is marked `verified_legacy` and excluded from M3b |
| 7 | A cost measurement appended to `evidence/learning-engine-cost.md` as **Baseline 3** |

### 7.2 What must be re-run from earlier milestones

- **gap-model M6 / AC2** — reopened by F90.
- **gap-model M2 gate** (classification + `gap_kind` bands) — the prompt and inputs both change under R2/R5.
- **gap-model M10 AC1** — re-armed as a standing recall measurement (D7) rather than a one-off.
- **learning-graph M3b thresholds** — cannot be calibrated until R3 and R6 produce trustworthy `verified` and `remediates` populations.
- **learning-engine §14 item 12** — re-asserted including Mutator-created nodes (R6).

### 7.3 What the next E2E must do differently

1. **A second repository**, chosen for *low model prior knowledge* — not `psf/requests`, not `fastapi`, not another canonical teaching repo. This is the single most important change: F41 showed `aima-python` flatters the system.
2. **Two passes: probing and naive.** The completed round was an expert deliberately hunting defects, which is the right way to find them and the wrong way to measure frequency. The next round needs one straightforward pass answering honestly.
3. **Attribution recorded live** (D8) for every non-`understood` outcome, so the round produces a *rate* rather than a census.
4. **The walk taken in order at least once**, so `why_now`, resume and completion are exercised as designed (this round never called `/advance` until stop 12).
5. **Disputes used** whenever the reviewer believes the system is wrong — that is now the primary instrument.

---

## 8. Cost

**[FACT] Baseline (learning-engine, 2026-08-15):** planning $0.3018 (**74%** of a
session), session-time teaching+grading $0.0086 per unit, adaptation a rounding
error. Gap-model Baseline 2 added ≈13.6% warm plus ≈$0.0042 per gap closed.

**Correctness-required cost added by this phase:**

| change | shape | expected magnitude |
|---|---|---|
| R2 — anchor source into assessment grading | input tokens on a Haiku call, once per answer | the same source Teaching already reads; input-side on the cheaper model. **Must be measured, not estimated** |
| R2/R3 — anchor source into verification grading | same, per verification | verifications are rare (2 this session) |
| R3 — `contradicting_span` | a few output tokens per gap | negligible |
| R5/D6 — `learner_span` | a few output tokens per gap | negligible |
| R1, R6, R7, R8, R0 | **no model calls at all** | **zero** |

**[REC] Three commitments.**

1. **Measure, do not estimate.** Append **Baseline 3** to
   [`evidence/learning-engine-cost.md`](evidence/learning-engine-cost.md) using the
   existing `scripts/measure_cost.py`, before and after R2/R3.
2. **Correctness cost is not negotiable against the $0.10 target.** `cost-optimization.md`
   §0 already forbids "loosening exit criteria so investigations stop earlier"; a
   grader that cannot see the code is the same trade in a different place. This
   phase **raises the baseline on purpose**, and hands the number to that phase.
3. **Optional cost is kept out.** The rejected second adversarial verification call
   (D3 alternative) and any auto-attribution model call (D8) are explicitly not
   taken, and are the first things to reach for only if a gate fails.

---

## 9. Open decisions

| # | question | alternatives | recommendation |
|---|---|---|---|
| **OQ-1** | How strictly should G1 fire, given the symbol recogniser under-fires? | (a) prose-symbol extraction only; (b) G3 only, from anchors; (c) both, with G1 advisory | **(c)** — G3 enforcing, G1 advisory in the plan report until its false-positive rate is known |
| **OQ-2** | What happens to a unit that violates G3? | reorder · demote to `optional` · drop · flag only | **reorder where `depends_on` allows, otherwise flag** — dropping a unit to satisfy an ordering rule loses taught material |
| **OQ-3** | Rail order vs planner contiguity (D10) | rail renders walk order, repeating headers · planner emits contiguous areas | **rail renders walk order** — a render change, no constraint on planning |
| **OQ-4** | Should a corrective lesson re-render once its gaps verify? | re-render (a Teaching call per closure) · phrase corrections impersonally · keep a pre-correction version | **phrase impersonally** — free, and it removes F35 without a new call |
| **OQ-5** | What is this journey's actual scope? (F92: two of ~8 algorithms ever anchored) | narrow the goal translation · require the planner to cover named families | **product decision, not a defect** — needs an explicit call before the next E2E chooses a goal |
| **OQ-6** | Widen §18.5's one-mutation-per-answer cap? | keep · allow N structural mutations · allow one but always designate a gap | **keep the cap; always designate** (D9) — the cap is deliberate, the silence was not |
| **OQ-7** | Should `disputed` gaps feed a review queue? | discard after unblocking · retain for analytics · surface to the developer | **retain for analytics** now; a review surface is a later product question |
| **OQ-8** | Does `CODEONBOARD_GAPS` stay on in dev given three false positives? | on · off until R5 | **on** — the false positives are the most valuable evidence and are invisible with it off |

---

## 10. What this phase explicitly does not change

- Planner sizing, band calibration, `depth`/`code_depth`, the goal interview.
- The Dossier, the Survey, exploration budgets or exit criteria.
- `optional` semantics (§6.3), the progress measures (`learning-graph.md` §5), or the two-dimension understanding model (M3a.1).
- The one-mutation-per-answer cap (§18.5) — [OQ-6].
- Lesson prose style, rail copy, drawer conditions, the state vocabulary (F38).
- Cost optimisation of any existing stage.

---

## 11. Second-pass findings — remediation flow, route order, briefing (F96–F109)

> **Same session.** The evidence below comes from a continued manual run on
> `cff533a5` — the session §5's R8 already names. It has since grown from 17 nodes
> to **18** (a second learner-requested warm-up at 20:37:34), which is what makes
> the `prerequisite_exists` branch reachable for the first time; **F52** could only
> report that it had *not* fired.
>
> **This section does not repair anything.** It adds fourteen findings, four
> design decisions (**D12–D15**), one milestone (**R9**), two amendments to **R7**,
> and three open questions (**OQ-9–OQ-11**).
>
> **Method.** Every `[FACT]` below was checked against code or against stored state
> in `data/sessions.db`, and two were checked by replaying the real persisted graph:
> the rail order in §11.3 by re-running `buildRoute` → `splitJourney` →
> `buildSections` over the stored nodes/edges/areas, and the lost update in §11.4 by
> driving `store.save_graph` directly.

### 11.1 The six reported symptoms, and how they collapse

| # | reported symptom | classification | root cause |
|---|---|---|---|
| 1 | "Build warm-up" sometimes does nothing | **state-management bug** | **C7** + F52's discarded reason |
| 2 | Retry flow lost after requesting a warm-up | **state-management bug** | **C7** |
| 3 | Stop 13 rendered above stop 12 | **UI rendering + information design** | **C8** — already known as F19 |
| 4 | Lesson screen overloaded | **design/UX** | **C7** (append-only panel) |
| 5 | Briefing screen stopped working | **persistence bug** + swallowed error | **C9** |
| 6 | No way to fix a specific gap | **missing surface, not missing engine** | **C7** |

**[FACT] Four of the six are one defect.** Symptoms 1, 2, 4 and 6 are all
consequences of **C7** below. Symptom 5 is a different mechanism in the same
family — read-modify-write over a whole graph. Symptom 3 is independent and
predates every mutation in the run.

Three causes extend §3.1's six:

| cause | contract violated |
|---|---|
| **C7 — the remediation state machine is component state.** `LessonPanel` derives every post-answer affordance from `result`, the reply to the last `POST /respond`, and clears it whenever the node pointer moves. The authoritative half of that state is on the node and is partly not on the wire at all | *"The Planner's learning graph is also the user's understanding graph — the same object, persisted across sessions"* (`roadmap.md`). A remediation state that a remount destroys is not persisted |
| **C8 — the walk order and the chapter order are two independent orderings.** `curriculum.order()` is topological over `depends_on` with model order as tiebreak and **ignores `area_id`**; `buildSections()` renders chapters by `area.order`. The stop *number* comes from one, the vertical *position* from the other | learning-engine.md §4.3's `Journey → Area → Learning Unit` hierarchy assumes one order |
| **C9 — every write is a full-graph overwrite with no version check.** `store.save_graph` upserts the session row then `DELETE`s and re-inserts every node and edge. FastAPI runs the `def` handlers in a threadpool, so any two overlapping requests silently discard one side's writes | *"Written once and cached on the session"* (`session_welcome` docstring) — a contract the race breaks |

---

### 11.2 Symptoms 1 & 2 — the warm-up and retry flow

#### The trace, from stored state

```
node e5d80393  "Understand PriorityQueue as the frontier mechanism"

20:36:09  POST /respond    → partial · gap_kind=wrong_model · action=reteach, retaught=True
                             opened gap 738303e5 "the reinsertion operation uses
                             frontier.append(child), placing the new node at the end…"
                             UI: verdict · "Rewritten around what you said"
                                 · [Check my understanding]  · [Build me a warm-up]

20:37:34  POST /retry      → warm-up be9608bc inserted (origin=learner_request)
                             handleRetry: setResult(null); setAnswer(""); onAdvance()
                             → LessonPanel remounts on be9608bc

20:38:40  POST /respond    → understood on the warm-up
          POST /advance    → next_in_path follows the prerequisite edge back to e5d80393
                             → LessonPanel remounts on e5d80393, result = null

STORED FINAL STATE of e5d80393:
    attempts       = 1        (no second attempt was ever recorded)
    visited        = 0
    understanding  = partial
    gap 738303e5   = open, verification_attempts = 0
```

**F96 — [FACT] The affordance that makes a warm-up worth taking is destroyed by
taking one.** `canAnswerAgain` is `adaptation !== undefined && ["hint","followup",
"reteach"].includes(adaptation.kind)` where `adaptation = result?.adaptation`;
`canRequestWarmUp` is `result !== null && …`. A `useEffect` on `[sessionId, nodeId]`
calls `setResult(null)`. The warm-up round trip moves the node pointer twice by
design, so **`/retry` is the one action guaranteed to erase the state that
authorised it.** Nothing reconstructs it from `node.attempts`, whose latest
assessment carries `response.action = "reteach"` — the exact fact
`canAnswerAgain` needs.

**F97 — [FACT] On return, the original question is re-asked with its own answer
printed above it.** Because `result === null`, the `{!result && …}` branch renders
`lesson.lesson.prompt` as a live input. But
`revealed = Boolean(result) || attempts.length > 0` is **true**, so `reveal`,
`takeaway` and `ownership` are all on screen above it. This is precisely the memory
check §18.7 removed "Try again" to prevent — reintroduced through the return path
rather than through a button.

**F98 — [FACT] The one action the design says is correct here is unreachable.**
`POST /verify` needs nothing from the client but `node_id`: it reads `node.gaps`
and `node.gap_state.remediation_rounds` from persistence and picks
`plan.active_set[0]`. It is gated in the UI behind
`canAnswerAgain && openGaps.length > 0`. So the backend can serve a fresh,
gap-aimed question for `738303e5` at any time, and the screen that should offer it
cannot.

**F99 — [FACT] `canRequestWarmUp` offers a warm-up in a state where the cap
guarantees refusal.** The offer is suppressed only via
`warmUpInserted = result?.mutation?.kind === "prerequisite"` — *this* answer's
mutation. On a second wrong answer at the same node the mutation is `none`, the
offer reappears, and `_has_prerequisite` then declines with `prerequisite_exists`.
Two nodes in this session are now permanently in that state:

| node | warm-up | spliced | `_has_prerequisite` |
|---|---|---|---|
| `0ba8f6d3` "Use GraphProblem for map-based search" | `ceb9b6e7` | 20:01:42 `learner_request` | **True, permanently** |
| `e5d80393` "Understand PriorityQueue as the frontier mechanism" | `be9608bc` | 20:37:34 `learner_request` | **True, permanently** |

This closes the gap F52 left open. F52 established that three materially different
refusals collapse to one string, and recorded that *for the 17-node graph the cap
had not fired*. It now can, it is the **commonest** of the three on a node that has
already been remediated, and `t.lesson.warmUpUnavailable` — *"We couldn't build a
warm-up for this one"* — is the wrong sentence for it. The right one,
`t.lesson.warmUpExists`, already exists in `strings.ts` and is reachable only from
the `/respond` path.

**F100 — [FACT] `remediation_rounds` is never incremented.** It is read by
`decide_all` and by `/verify` ([api.py](../../../backend/api.py)), persisted by the
store, and asserted in `test_gap_model.py` and `test_gap_verification.py` — but no
line in `backend/` writes to it. It is `0` on every node of this session.
`REMEDIATION_ROUND_CAP = 4` is dead code, and the per-node remediation loop is
currently unbounded. This is the *node*-level cap; the per-gap
`VERIFICATION_ATTEMPT_CAP` does increment, via `record_failed_verification` (F53).

**F101 — [FACT] `pending_verification` is persisted but is not on the wire, and
"Not now" orphans it.** `GapState.pending_verification` round-trips through
`gaps_json` and gates `POST /respond {kind:"verification"}` with a 409
`no_pending_verification`. It appears in `understanding.evidence()` — the drawer
endpoint — but **not** in `LearningGraph.to_dict()`. The frontend keeps the question
in a `verification` state variable, so a reload or the warm-up detour removes it
from the screen while the server still holds it. `t.lesson.notNow` calls
`setVerification(null)` and never tells the server. There is no endpoint to clear it.

**F102 — [FACT] `LessonPanel` uses the naive prerequisite test that two modules
document as wrong.**

```ts
const warmUpEdge = graph.edges.find(e => e.kind === "prerequisite" && e.to_id === nodeId);
```

`graph.py`'s module docstring and `graph-layout.ts`'s `unlockTargetOf` both spell
out why this is invalid under the objective-first planner, and `page.tsx` passes a
correctly-derived `isPrerequisite` into the panel — which this computation
bypasses. Measured on this graph: **14 of 18 nodes** have an incoming
`prerequisite` edge, and on the two that carry a *real* warm-up, `find()` returns a
**planned** dependency edge first. So the `recovered` banner — *"The warm-up worked
— you got this one after studying 'X' first"* — fires on stops that never had a
warm-up and names the wrong unit on the two that did. Same class as F19 and F34:
a consumer that cannot tell PLANNED from REMEDIAL.

#### What is working, and should not be touched

**[FACT]** Warm-up creation is sound end to end when it fires. Both warm-ups were
generated, spliced with `insert_before`, marked `priority: required`, recorded as
`remediation_inserted` journey events with the correct `origin` and `unlocks`,
persisted, and rendered in the rail as indented detours attributed to the right
anchor. `/advance` correctly follows the prerequisite edge **back** to the original
stop rather than past it. The defect is entirely in *when the action is offered*,
*what it says when it declines*, and *what survives the return*.

---

### 11.3 Symptom 3 — route order (extends F19, R7, OQ-3)

**F103 — [FACT] The inversion is quantified, and it is not caused by adaptation.**
Replaying `buildRoute` → `splitJourney` → `buildSections` against the stored graph
reproduces exactly what the rail renders:

```
CHAPTER 1 · The Problem contract
    Stop 1     Map the Problem contract
    Stop 3  ←  Write a minimal Problem subclass
CHAPTER 2 · Graphs and maps as input data
    Stop 2  ←  Understand the Graph data structure
    warm-up    Understand how GraphProblem.h uses the locations dict
    Stop 4     Use GraphProblem for map-based search
    Stop 5     Use pre-built maps
CHAPTER 3 · Calling search functions and reading results
    Stop 6     Call astar_search and read the result
    Stop 7     Choose between search algorithms
    Stop 8     Extract information from a returned Node
CHAPTER 4 · How best-first search works behind the call
    Stop 9     Trace the A* runtime flow end-to-end
    Stop 10    Understand the heuristic contract for A*
    Stop 11    Understand explored-set semantics
    warm-up    See how PriorityQueue.append uses heapq.heappush
    Stop 13 ←  Understand PriorityQueue as the frontier mechanism
CHAPTER 5 · Risks, constraints, and extension points
    Stop 12 ←  Recognise the risk of mutable or unhashable states
    Stop 14    Recognise the risk of missing or incomplete graph definitions
    Stop 15    Synthesise: own a working search integration
```

The dependency chain visits areas in the order
`a1 a2 a1 a2 a2 a3 a3 a3 a4 a4 a4 a5 a4 a3 a5 a5`. **Four** inversions follow
mechanically. Removing both warm-ups leaves all four in place: this was visible on
the very first render, before any answer was graded.

**F104 — [FACT] The displayed number is not stable, and nothing explains the
change.** `countsAsStation` excludes `priority: "optional"`, and `prune_ahead` runs
on **every graded answer**, demoting `recommended` units to `optional`. In this
session `90d19b10` "Survey the other available search algorithms" left the spine,
so the two stops behind it renumbered 15→14 and 16→15 and the total dropped 16→15,
mid-session. The `t.lesson.pruned` copy that would explain it is rendered only
inside the verdict bubble that F96 destroys.

**F105 — [FACT] Ordering is deterministic across the layers in practice, with two
latent hazards.** `path_order()` and `buildRoute` agree, and edges round-trip
through SQLite unchanged, so this is a rendering contradiction rather than a
persistence bug. But `load_graph` has **no `ORDER BY`** on the node or edge query,
so `nodes` dict order and `edges` list order are whatever SQLite returns; and both
`next_in_path` and `graph-layout.ts`'s `outgoing()` return the **first** matching
edge. Any node that ever acquires two outgoing `sequence` edges — or any graph with
two path-heads — becomes order-of-storage dependent. Not what this run hit; worth
closing while R7 is open.

**Answers to the questions this symptom was raised to settle:**

| question | answer |
|---|---|
| what caused the reordering | **C8.** Both orderings are individually correct; their coexistence is undesigned |
| is it intentional | No document states which order the learner is looking at. **OQ-3** already proposes rail-renders-walk-order; F103 quantifies the cost of not deciding |
| stable planned order, or execution order | **Neither today.** The number is the dependency-walk position, recomputed on every load, and it moves when `priority` changes (F104) |
| can dynamic insertion produce confusing order | Warm-up insertion is well behaved — no number consumed, indented, anchor captioned. **Scope control and prune-ahead** do renumber silently |
| deterministic between backend, persistence, frontend | Yes in practice; see F105 for the two latent hazards |

**[REC]** Classify symptom 3 as **expected behaviour with broken information
design**, not a logic bug — with the exception of F102 and F104, which are real
defects in the same area.

---

### 11.4 Symptom 5 — the briefing (C9)

**F106 — [FACT] The message the learner saw has exactly one producer, and it is
not the agent's graceful-degradation path.**

```tsx
try   { setBriefing((await getWelcome(id)).briefing); }
catch { setBriefingFailed(true); }        // status and detail discarded
```

`t.welcome.failed` — *"Couldn't write the briefing — your route is still ready."* —
renders **only** from that catch, i.e. a non-2xx response or a request that never
landed. The "no grounded material" outcome has its own separate copy,
`t.welcome.unavailable`. So the report is evidence of a **thrown request**, and
`build_briefing`'s own fallbacks were never reached.

**F107 — [FACT] The briefing was never persisted for this session, so every visit
re-ran generation.** Stored state:

| session | created | last updated | `briefing_json` |
|---|---|---|---|
| `cff533a5` | 18:32:38 | 21:03:05 | **NULL** |
| `99b8d319` | 20:03:06 | 21:04:52 | 1719 bytes |
| `cf84cc2c` | 19:05:14 | 19:05:24 | 2279 bytes |

An hour of use — 15 graded answers, two warm-ups, two scope changes — and the
column is still empty, on a session whose welcome page is the landing screen after
`/session/start`. **C9 explains it, and the race is near-deterministic:**

1. The welcome page mounts and fires `GET /welcome`. It loads the graph
   (`briefing = None`) and begins `clone_repo` + survey load + one Haiku call —
   seconds long.
2. The learner clicks *Start learning*. The session page mounts and fires
   `GET /session/{id}` and `GET /session/{id}/lesson`. `/lesson` loads its own
   snapshot — still `briefing = None` — renders the first lesson, and saves.
3. Whichever `save_graph` lands second wins with a stale snapshot. When that is
   `/lesson`'s, the briefing is destroyed.
4. **The loss is invisible on the first visit**, because the page renders from the
   HTTP response rather than from the database. It surfaces only on the next visit
   — which re-runs generation, and re-exposes the learner to whatever transient
   path failed at ~21:03.

Driven directly against the stored graph:

```
A = load_graph(sid)      # e.g. GET /welcome
B = load_graph(sid)      # e.g. GET /lesson, moments later
A.briefing = {...}
B.nodes[cur].attempts.append({...})
save_graph(B); save_graph(A)
    → B's recorded attempt present?  False        # silently destroyed
    → 8 concurrent load+save on the 12 MB db: 0.18 s, no lock errors
```

No `OperationalError`, no 500, no log line. **This is not a briefing bug — it is a
general lost-update defect that can destroy gaps, attempts or a spliced warm-up.**
`/welcome` is merely the worst offender, because its window is the longest and it
writes nothing but a briefing while clobbering everything else.

**F108 — [FACT] Three layers swallow the actual error, and one uncaught path sits
outside its own handler.**

- The frontend discards the status code and FastAPI's `detail`, with no retry and
  no console log. Every cause renders as the same sentence.
- `session_welcome` logs only inside the survey `try`. Its uncaught raisers —
  `_new_client()` (`KeyError` on a missing key → 500) and
  `learning_store.save_graph` (→ 500) — log nothing.
- **`_ground_notes` sits outside `build_briefing`'s `try`.** It calls
  `Path.resolve()` and `.exists()` on **model-supplied** path strings, which is the
  one input to this endpoint that varies run to run and can raise past every
  handler.

**Ruled out empirically** (replayed against a copy of `data/sessions.db` with a
stubbed client): session-state poisoning — `GET /welcome` on the stored
`cff533a5` returns **200** with `available: true`; material shortage — the README
is present in `doc_context`; SQLite lock contention at this scale; and any
route/profile problem — the same `_load_session_or_404` served `getSession`
successfully on the same page load, which is why the rest of the screen looked
right.

**Not concluded.** The exact exception is **not determinable** from the available
evidence, because the frontend threw the status away and the backend logs nothing
on the paths that can raise. Ranked: `_ground_notes` on an invented path (varies
run to run, matches the intermittency), then a `save_graph` failure, then a
transient network or `--reload` restart mid-flight. **Making it knowable is part of
the fix, not a follow-up.**

**[FACT] A latent defect in the same handler.** `graph.briefing = briefing` runs
unconditionally, including when `build_briefing` returned `available: false` after
a transient model failure. That negative result is then cached permanently and no
reload will ever retry it. This run did not hit it; it converts one bad minute into
a permanently degraded session.

**Existing coverage.** `tests/test_briefing.py` covers the agent well — no
material, unparseable output, unresolvable citation, unclonable repo, 404 — and
`test_welcome_writes_the_briefing_once_and_reads_it_back` asserts exactly the
contract C9 breaks, but single-threaded, so it passes. Nothing covers a concurrent
write, a `save_graph` failure, an `available:false` being cached, `_ground_notes`
raising, or any frontend error handling — there is no frontend test harness at all.

---

### 11.5 Symptom 6 — gaps are visible, and only waivable

#### What exists today

**[FACT] Representation and association are complete.** A `Gap` lives in
`node.gap_state.gaps` — explicit state, not derived from `attempts` — carrying
`id`, `kind`, `claim`, `objective_part`, `status`, `verification_attempts`,
`origin_attempt` and `resolved_by`. Association to the question that produced it is
bidirectional: `origin_attempt` indexes into `attempts`, and the causing attempt
carries `response.gaps_opened` / `gaps_addressed`.

**[FACT] Several gaps can be open on one stop, and they are individually
addressable throughout:**

```
58766f8b "Synthesise: own a working search integration"        (current stop)
    8cd5ff59  wrong_model  verified   "If locations are missing, A* simply behaves like…"
    efcdadd0  wrong_model  open       "Since the warehouse is connected, there is no
                                       need to check for None."
0ba8f6d3 "Use GraphProblem for map-based search"
    2c1c6595  wrong_model  open       "h() returns the road distance from Sibiu to Bucharest…"
    3e91c1b9  wrong_model  open       "When a graph has no locations dictionary, h() returns 0."
```

`efcdadd0` is the gap that prompted this symptom.

**[FACT] What each action can actually reach:**

| action | gap-specific? | can it close one gap? |
|---|---|---|
| `POST /verify` | targets exactly one — `plan.active_set[0]`, precedence-ordered, cap-filtered | **Yes. The only thing that can** |
| `POST /respond {kind:"verification"}` | graded against `pending_verification.targets`; returns `resolved` / `unresolved` | **Yes** — `gap.mark_verified()` |
| `POST /respond` (assessment) | re-grades the whole objective; may open new gaps | **No.** Never closes an existing gap |
| `POST /retry` (warm-up) | diagnosis carries `plan.targets[0]`; the warm-up records `remediates` (D9) | teaches toward one gap; closes none |
| `POST /waive` | accepts `gap_id` | never evidence — stops the asking, not the obligation |

So **retrying the original question cannot resolve the specific gap, and neither
can a warm-up.** Only a verification can. That is coherent, and it is the one
action the UI hides (F98).

**F109 — [FACT] `Set aside` is the only per-gap action, and that is an oversight
rather than a decision.** The gap list renders one control per gap,
`t.lesson.waiveOne`. §18.10 describes this surface as *"the product's most honest
surface"* and specifies naming rather than counting — which it does — but no
document proposes that waiving be the only thing a learner can do with a named
misconception. Three concrete wire gaps stand between today and gap-specific
remediation:

1. `POST /verify` takes only `node_id`. The **system** picks the gap by precedence;
   the learner cannot name one.
2. `pending_verification` is not in `to_dict()` (F101), so after a reload the UI
   cannot know a question is outstanding or which gap it belongs to.
3. `to_dict()` sends only `id · kind · claim · blocking` per gap, while
   `_gaps_payload` on `/respond` and `/waive` also sends `status`,
   `verification_attempts` and `exhausted`. After a reload the UI cannot tell an
   exhausted gap from a fresh one, so it would offer a check the backend refuses
   with `nothing_to_verify`.

Everything else the engine needs already exists.

---

### 11.6 The recommended flow

Left: what the code and the design docs intend. Right: what a learner gets. They
agree for four steps and part company at exactly one point.

| # | intended | actual |
|---|---|---|
| 1 | answer graded; `decide_all` picks one action from the leading gap's kind | same |
| 2 | gaps recorded by name; intervention filed on the attempt | same |
| 3 | learner reads the correction, or asks to step back | same — but the warm-up offer also appears where refusal is certain (**F99**) |
| 4 | warm-up spliced; `next_in_path` routes **back** to the stop | same, correctly persisted |
| 5 | **back on the stop: a fresh, gap-aimed question via `/verify`** | **remount clears `result`; the verify button disappears. The *original* question returns, with its `reveal` above it** (**F96**, **F97**) |
| 6 | verification graded against the gap; resolved → `verified` → the stop can reach `understood` | unreachable from this screen; the stop stays `partial` with `attempts = 1` |
| 7 | unresolved → one more check (cap 2), then the system stops proposing, gap stays open | per-gap cap works (F53); the per-node cap is dead (**F100**) |
| 8 | learner may set a gap aside at any point — never evidence, reversible | reachable, and the **only** per-gap action (**F109**) |

#### D12 — Every action on the lesson screen is derived from persisted state

**[DECISION]** `LessonPanel` reconstructs its phase on mount from
`node.attempts`, the latest assessment's `response.action`, `node.gaps` and
`pending_verification`. The `/respond` reply becomes an **optimistic update**, not
the source of truth.

*Rationale.* This is the whole of C7. It fixes F96, F97 and F98, is a precondition
for D14, and it restores the property `roadmap.md` already claims — that the graph
*is* the learner's state. Extracted as a pure function
`lessonPhase(node, lesson, result) → {phase, primaryAction}` so it is testable
without a browser, in the spirit of `curriculum.py`'s sizing rules.

Phases: `reading | answering | feedback | remediation | resolved`.

#### D13 — One primary action per moment, chosen by the system

**[DECISION]** The learner is never asked to choose between competing remediation
routes. Precedence:

| state | primary action |
|---|---|
| open blocking gaps | **Check this gap** → `/verify` with that `gap_id` |
| no gaps, hint/follow-up/re-teach outstanding | **Answer again** |
| nothing outstanding | **Next stop** |

Warm-up and *Set aside* remain available and quiet. If a gap is holding progress
back, the next meaningful action must be obvious — and `decide_all`'s precedence
order already encodes which gap that is, so the UI must not re-derive it.

**Corollary — never offer what will be refused.** Suppress the warm-up offer when
the node already carries a remedial warm-up, from a wire field
(`node.has_remediation`) computed by the **same structural test**
`_has_prerequisite` uses — not recomputed in the panel (F102). When the Mutator
does decline, return the reason and say the true thing (F52's table).

**Corollary — never re-ask a question whose answer is on screen.** Once `reveal`
has been shown, the original prompt is history, not an input (F97). Re-assessment
goes through `/verify`.

#### D14 — An open gap is an active object, not a ledger row

**[DECISION]** The precedence-leading open blocking gap is **promoted** into an
active card directly under the lesson, holding whatever the learner should do now —
the hint, the follow-up, the verification question, or the gap's claim with its
check. Everything historical collapses above it. Remaining gaps stay listed as a
counted line.

Three interaction models were considered:

| | learner sees | primary action | history | return to lesson | multiple gaps | trade-offs |
|---|---|---|---|---|---|---|
| **A · Phases** — the body is *replaced*, not appended; one of `reading→answering→feedback→remediation→resolved` owns the column | one question, one verdict, one action; never a question beside its answer | phase-determined, single, fixed position | collapsed `<details>` rows + evidence drawer | resolving the last gap advances to `resolved`; lesson returns with `reveal` intact | queue inside the remediation phase, "1 of 2", precedence order | **largest diff** — effectively a re-render of `LessonPanel`; replacing content risks hiding something the learner wanted to re-read |
| **B · Active gap card** *(recommended)* — panel structure kept; one focus object under the lesson | the misconception in their own words, with one obvious way to clear it | **Check this gap** → the question replaces the card contents in place | collapsed sections above the card; drawer unchanged | never left it — the card resolves to "Cleared" and promotes the next gap, or becomes *Next stop* | precedence-ordered, one promoted, remainder counted — matches `ACTIVE_SET_MAX` | **smallest diff that fixes symptoms 2, 4 and 6 at once**, and reuses the backend but for §11.5's three wire additions. Still one scrolling column, so it *manages* the overload rather than removing it |
| **C · Remediation mode** — an open blocking gap becomes its own destination, like the chapter overview; lesson column temporarily replaced | unmistakably a different mode; zero competition for attention | the targeted question; everything else is a link out | entirely out of the mode, into the drawer | explicit button, and automatic when the last blocking gap clears | sequential with visible progress — **most legible for 2+ gaps** | adds a mode, its navigation and its copy. Modes strand people, and the strongest property of today's design is that a learner is always "on a stop" |

**[DECISION] Build B, designed so C is a later promotion of the same card rather
than a rewrite.** B answers all three learner questions at every moment — *what am
I learning* in the collapsed lesson header, *what just happened* in the card's
eyebrow, *what next* in the single primary button — without adding a mode, hiding
the lesson, or redesigning the backend. A is the right end state for the panel but
depends on B's content model existing first. **[OPEN → OQ-11]** whether C is needed
at all depends on how common 3+-blocking-gap stops turn out to be.

#### D15 — A briefing is written once, honestly, and its failures are visible

**[DECISION]** Four changes, and the third is the general one:

1. `session_welcome` writes the briefing through a **targeted**
   `store.save_briefing(session_id, briefing)` that touches one column — removing
   the app's worst clobber window outright.
2. The briefing is persisted **only when `available` is true**, so a transient
   failure is retried on the next visit rather than cached forever.
3. `save_graph` gains `updated_at`-based optimistic concurrency, **or** the hot
   writers (`/lesson`, `/respond`) narrow to targeted updates. As it stands, any
   two overlapping requests can silently destroy gaps, attempts or a warm-up
   (F107) — which also makes every measurement this phase adds unreliable.
4. `_ground_notes` moves inside `build_briefing`'s `try`; the handler's `save`
   is wrapped so a persistence failure logs and still returns the briefing; and
   the frontend keeps the status and `detail`, logs them, and offers a retry.

*Rationale for 3 being in this phase rather than deferred:* R0 exists to make
system error distinguishable from learner error. A silent lost update is a system
error that erases its own evidence.

---

### 11.7 Milestone R9, and two amendments to R7

#### R9 — Remediation flow and gap-specific resolution

| | |
|---|---|
| **Goal** | the learner returning from a warm-up is offered the action that can actually close the gap, and a named gap is resolvable by name |
| **Depends on** | R0 (attribution), R3 (verification integrity — R9 exposes verification far more widely, so its integrity must land first) |
| **Components** | `backend/learning/graph.py` (`to_dict`), [`backend/api.py`](../../../backend/api.py) (`/verify`, `/retry`, a verification-dismiss route), [`backend/agents/mentor/mutator.py`](../../../backend/agents/mentor/mutator.py), `frontend/components/LessonPanel.tsx`, `frontend/lib/api.ts`, `frontend/lib/strings.ts` |
| **Changes** | **wire (additive):** `pending_verification`, full `_gaps_payload` shape per node, `has_remediation` per node, `reason`/`rationale` on `/retry`, optional `gap_id` on `/verify`, a dismiss route. **behaviour:** D12 phase reconstruction, D13 single primary action, D14 active gap card, `remediation_rounds` incremented (F100), `warmUpEdge` replaced with `buildRoute`'s `isPrerequisite` (F102) |
| **Invariants** | **no post-answer affordance depends on `result`**; a node with `has_remediation` is never offered a warm-up; a question whose `reveal` has been shown is never presented as an input; a pending verification survives reload and node change; `/verify` with an explicit `gap_id` targets that gap or refuses; **the per-node remediation loop is bounded** |
| **Tests** | see §11.8 |
| **Migration** | every wire field additive; an un-updated client keeps working and simply does not render them (the M9 pattern). `remediation_rounds` already persists, and pre-R9 nodes read `0` |
| **Done when** | replaying `cff533a5`'s `e5d80393` — reteach → learner warm-up → pass → return — offers *Check this gap* for `738303e5`, and a second warm-up request on `0ba8f6d3` is refused **with the reason shown** |

#### R7 amendments

- **Invariant added:** `load_graph` orders its node and edge queries deterministically, and `path_order()` is stable across a save/load round trip (**F105**).
- **Invariant added:** for every adjacent pair the rail renders, layout order and stop numbering agree (**F103**) — this is the acceptance test for whichever branch of **OQ-3** is chosen.
- **Test added:** a fixture built from `cff533a5`'s stored graph asserting the above over all 15 stops. It currently fails on four pairs.
- **Note:** F104 (silent renumbering by `prune_ahead` / scope control) is a *new* item in R7's scope, and needs **OQ-9** decided first.

---

### 11.8 Testing strategy additions

**[FACT] There is no frontend test harness.** `frontend/package.json` has
`dev` / `build` / `start` and no test runner. Symptoms 1, 2, 4 and 6 are all
frontend state bugs, so §6.1's "deterministic first" cannot currently apply to
them. **[REC]** add Vitest scoped to `frontend/lib/` only — `lessonPhase`,
`buildRoute`, `buildSections` are all pure — before R9. Component tests are not
proposed; the extraction in D12 is what makes them unnecessary.

| test | asserts | finding |
|---|---|---|
| `lessonPhase` on a node with one `reteach` attempt + one open gap | `remediation`, primary = *Check this gap* | F96, F98 |
| `lessonPhase` on a node with `has_remediation` | no warm-up offer | F99 |
| `lessonPhase` on a node with `pending_verification` | restores the question, **not** the original prompt | F101 |
| `lessonPhase` on a node with attempts, no gaps, nothing outstanding | primary = *Next stop* | D13 |
| `lessonPhase` on a node whose `reveal` has been shown | the original prompt is history, never an input | F97 |
| warm-up banner on a graph with planned `prerequisite` edges | fires on the **remedial** node only, and names it | F102 |
| section order vs stop numbering over `cff533a5`'s graph | agree for every adjacent pair | F103 |
| `/retry` on a remediated node | 200 with `reason: "prerequisite_exists"`, and the client renders `warmUpExists` | F99, F52 |
| `/retry` on a declined node | 200 with `reason: "no_useful_prerequisite"` **and** the model's `rationale` | F52 |
| `/verify` with an explicit `gap_id` | targets that gap, not the precedence leader | F109 |
| `/verify` with an exhausted `gap_id` | refused, `gap_not_verifiable` | F109 |
| verification dismiss | clears `pending_verification` server-side | F101 |
| N warm-ups / verifications on one node | `remediation_rounds` increments and the cap fires | F100 |
| `to_dict()` additions | every pre-R9 key unchanged (the `test_gap_api.py` pattern) | R9 migration |

**Regression tests that would have caught F107 / F108:**

```python
def test_a_concurrent_save_cannot_erase_the_briefing(tmp_path):
    # two snapshots; briefing on one, a node change on the other;
    # save in BOTH orders; assert both survive.

def test_an_unavailable_briefing_is_not_cached(tmp_path):
    # build_briefing returns available:False → graph.briefing stays None →
    # the next GET calls the model again.

def test_a_note_citing_an_unusable_path_does_not_fail_the_request(tmp_path):
    # _ground_notes raises OSError → 200 with the note, minus its citation.

def test_a_save_failure_still_returns_the_briefing(tmp_path):
    # save_graph raises → 200, and the failure is logged.
```

The first is the one that matters:
`test_welcome_writes_the_briefing_once_and_reads_it_back` already asserts the
broken contract, and passes only because it is single-threaded.

---

### 11.9 Re-validation gate additions

Added to §7.1, *what must be true before the next manual E2E*:

- **Every post-answer affordance survives a reload and a node change.** Checked by replaying `cff533a5`'s warm-up round trip.
- **No offered action can be refused by a guard the UI could have consulted.**
- **A named gap has a resolution route, not only a waiver.**
- **The briefing is written once and read back** — verified with a concurrent write, not only single-threaded.
- **Rail order and stop numbering agree** for every adjacent pair (R7's amended invariant; it currently fails on four pairs).

Added to §7.3, *what the next E2E must do differently*:

- **Deliberately answer one stop wrongly twice**, and request a warm-up after the second — the path F99 makes unreachable-in-practice today.
- **Reload the page mid-remediation**, with a verification outstanding.
- **Open the briefing screen twice**, with a lesson render in between.

---

### 11.10 Open decisions added

| # | question | alternatives | recommendation |
|---|---|---|---|
| **OQ-9** | Is the stop number a **stable planned position** or the **current walk position**? | (a) freeze at plan time, mark demoted stops as skipped; (b) recompute and *say* the journey got shorter; (c) number within the chapter — "Chapter 4 · stop 3 of 5" | **(b)**, and surface `t.lesson.pruned` somewhere that survives a remount. A frozen number would drift from the rail; per-chapter numbering loses the single global progress figure |
| **OQ-10** | Should the learner **choose** which gap to work, or only accept the system's precedence pick? | learner picks freely · system picks, learner may defer · system picks, no choice | **system picks, learner may defer** — precedence exists because a foundational gap must land first, and a free choice invites working the easy one. `Set aside` already covers deferral |
| **OQ-11** | Is a dedicated remediation mode (D14 option C) needed? | build now · build after B if 3+-gap stops are common · never | **defer — measure it.** The active-set cap is 3; if real sessions cluster at 1–2 blocking gaps, C is cost with no benefit |

**Amends [OQ-3].** F103 quantifies it: four inversions on a 15-stop journey, present
from the first render. The recommendation stands (rail renders walk order) and the
acceptance test is now R7's amended invariant.

---

### 11.11 What §11 explicitly does not conclude

- **The exact exception behind symptom 5.** The frontend discarded it and the backend logs nothing on the paths that can raise. D15's instrumentation is what makes it knowable; until then `_ground_notes` is the best-supported candidate, **not a confirmed one**.
- **Whether the planner's area interleaving is itself worth fixing.** Whether `a5` belongs at walk position 12 is a curriculum-quality question, adjacent to **OQ-5**. §11 established only that the two orderings disagree — not which is correct.
- **Any change to `optional` semantics, the progress measures, `decide_all`'s precedence, or the one-mutation-per-answer cap.** D12–D15 are about *reaching* the existing engine, not changing it.
