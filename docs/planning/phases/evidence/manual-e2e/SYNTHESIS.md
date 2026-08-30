# Manual E2E round — synthesis

**Round complete 2026-08-18.** One session, `cff533a5`, `aimacode/aima-python`,
goal `use_library`, flags `CODEONBOARD_CURRICULUM=1` + `CODEONBOARD_GAPS=1`.
17 planned units + 2 inserted warm-ups; all rendered, 13 answered. **95 findings**
(F1–F95) recorded in [`README.md`](README.md), which remains the evidence of
record. This document is the analysis; it does not restate the walk.

**Labels:** **[FACT]** verified against source or stored state · **[REC]**
recommendation · **[OPEN]** needs a product decision.

**Scope limitation, stated once and load-bearing.** This is **one** session on
**one** repository with **one** reviewer, an expert deliberately probing (four
answers were intentionally wrong). Two consequences: the error *rate* here means
nothing, and — per **F41** — `aima-python` is close to a best case, because most
unanchored claims about a famous teaching repository happen to be correct.
**Everything below is a lower bound on the defect surface.**

---

## 1. Executive summary

**What the round demonstrated.** The system produced a curriculum a competent
engineer could learn from, and the reviewer did learn from it. It also
demonstrated, with reproducible evidence, that **the system cannot tell the
difference between teaching the repository and teaching what the model already
believes about the repository** — and that grading is measured against the
system's own generated objective rather than against the code.

**What worked.** Claims *inside* a unit's anchors were reliable in every observed
case (F41, F43, F54). Pedagogical-form selection works as designed and
`learning-engine.md` §14 item 11 was **verified live for the first time** — four
distinct `prompt_kind` values, correctly derived from `kind` (F56). Progress
measures did **not** inherit the `visited` conflation (F18). Gap *lifecycle*
semantics held: a passed warm-up could not launder itself into evidence, and only
verification closed a gap (F31 credit, F53). The Grader caught genuinely wrong
answers repeatedly. §9 collects the full list.

**The most important failures**, in descending order of consequence:

| | finding | why it is worst |
|---|---|---|
| 1 | **F90** | verification — *the only producer of `verified`* — closed a gap on an answer restating the misconception verbatim. The artifact the gap model exists to protect is corruptible |
| 2 | **F82 + F59** | the same Grader marked a **false** answer `understood` for matching a false objective, and a **true** answer `partial` for exceeding an oversimplified one |
| 3 | **F20** | a learner quoting the source verbatim was marked `wrong_model` and given a still-open **blocking** gap that records a true statement |
| 4 | **F71 / F79** | false *property* claims (complexity, optimality) survive even when the contradicting source is anchored |
| 5 | **F49** | three misconceptions in, one gap out — gap-model's founding defect, reproduced |

**Health of the learning experience: usable, not yet trustworthy.** A learner who
already knows the domain extracts real value and routes around the errors — that
is what happened here. A learner who does not would have been taught at least four
false things (F20/F29 `h` returns 0; F58 admissibility suffices; F71 deletion is
O(log n); F77 unhashable states fall back to identity hashing), told a correct
answer was wrong (F20, F59), told a wrong answer was right (F82), and had no way
to say so (F26).

---

## 2. Learning-path / curriculum quality

**[FACT] The macro-structure is sound; the ordering is not.** The arc — use the
abstraction, then understand what runs underneath — is right, and the reviewer
endorsed it independently. Three ordering defects, all one shape:

| defect | finding |
|---|---|
| *Write a minimal Problem subclass* precedes `GraphProblem` and borrows its **entire anchor** to teach itself | F11, F28 |
| *Choose between search algorithms* requires admissibility, defined three stops later | F48 |
| `best_first_graph_search` is first anchored at stop 10, after **four** units made claims about it | F44 |

**These are one pattern: the journey makes claims about a mechanism one to four
stops before it anchors that mechanism.** Confirmed a third time at F65
(`PriorityQueue` semantics used at stop 12, anchored at stop 14). The planner's own
`prerequisite` edges under-declare what units teach from (F28), so the sequence is
*consistent with its edges* while the edges are wrong.

**[FACT] Coverage is asymmetric, measurably (F92).** Of the search algorithms in
`search.py`, exactly **two** are ever anchored — `astar_search` (5 units) and
`breadth_first_graph_search` (2). `uniform_cost_search` is anchored **zero** times
while named in two objectives; DFS, IDS, bidirectional, depth-limited and greedy
are anchored zero times. The unit whose subject is the rest of the family —
*Survey the other available search algorithms* — **anchors none of the algorithms
it surveys.**

**Did it build knowledge progressively?** Within its actual scope (GraphProblem +
best-first + A\*), yes — each unit used what the previous established, and the
deepening from API to runtime is genuine. Against the stated scope ("the search
algorithms in AIMA"), no.

**Recurring vs isolated.** Recurring: anchors reaching outside the unit (9
instances), claims preceding their anchor (3), assessment not covering the
objective (4 — F31/F32, F56, F80, F87), internal contradiction (7). Isolated: the
`EightPuzzleCustom` example that cannot run (F76), though its neighbouring error
(F77) belongs to a recurring class.

---

## 3. Lesson-content quality

**[FACT] The strongest predictor of accuracy is whether the claim's evidence was
in the unit's anchors.** Three controlled comparisons within one session:

| comparison | anchored | unanchored |
|---|---|---|
| `GraphProblem.h`'s fallback (F27) | stop 5: *"returns `np.inf`"* ✅ | stop 2: *"it returns 0"* ❌ |
| `Node` construction (F54) | stop 9: `depth` / `path_cost` mechanics ✅ | stop 7: *"`result()` … becomes the action"* ❌ |
| `romania_problem` (F41) | — | correct **by luck** — the model knew the repo |

F41 is the control that matters most: an unanchored claim that was exactly right.
**Nothing in the output distinguishes F41 from F20.** This is why "the lessons look
good" is not evidence of grounding, and why the observed error rate understates the
risk on any repository the model does not already know.

**[FACT] Anchoring is necessary and not sufficient — the round's own thesis had to
be revised.** F57 (a `takeaway` saying A\* visits "the cheapest nodes first") and
**F71** (deletion + reinsertion "both are O(log n)") are false claims made *with the
contradicting source anchored*. F71 is decisive: `PriorityQueue.__delitem__` does a
linear scan plus `heapq.heapify` on the very lines the unit was handed.

**The distinction that explains the data (F71b):**

| claim type | anchored | unanchored |
|---|---|---|
| **mechanism** — what is called, in what order, what is stored | **reliable** (F41, F43, F54, F56) | **confabulated** (F20, F29, F45, F65, F75) |
| **property / guarantee** — complexity, optimality, termination, "always", "silently" | **still wrong** (F57, F71) | wrong (F58, F61, F67, F77, F79, F81, F86, F89) |

A property is a *conclusion about* code; the model reaches for the textbook
conclusion and does not notice the implementation that violates it. **F77 extends
this past the repository entirely** — that a class with `__eq__` and no `__hash__`
falls back to identity hashing is false about *Python*, and no anchor could ever
have supplied the correction.

**Internal contradictions — seven, three of them in the `takeaway`.** F2, F7, F33,
F51 (Grader rationale), F55, F57 (one clause contradicting the next), F62, F83,
F86. The pattern: **the compressing fields drop the distinction the unit was built
on** — `path()` "returns the state chain" (F55), "visit the cheapest nodes first"
(F57). Detecting these needs **no repository access**: a self-consistency pass over
one JSON payload, and the cheapest check the round surfaced.

**Cross-lesson contradictions.** F12 and F16 (two units, same anchor,
irreconcilable accounts of `Problem`), F46 (a later unit dismantling a correct
distinction an earlier one taught), F75 (a warm-up denying the behaviour of the
unit it unlocks). Nothing compares a unit's claims against what earlier units
taught.

**Locally correct, globally wrong.** F2 is the template: Teaching built *exactly*
the objective it was given, as B1 requires. The defect was upstream. Most content
failures in this round have that shape.

---

## 4. Grading quality

**[FACT] Five distinct failure modes, all on real answers:**

| # | finding | failure |
|---|---|---|
| 1 | F20 | gap opened on a **true** claim, inherited from a confabulated `expected_answer` |
| 2 | F49 | **multi-gap miss** — 3 separable misconceptions, 1 gap |
| 3 | F59 | a **correct refinement penalised** for exceeding the objective |
| 4 | F68 | a misconception **attributed** that the learner never expressed |
| 5 | F82 | **false positive** — a wrong answer graded `understood` |

**[FACT] The systemic cause is one architectural fact.** `_build_user_content`
([grader/agent.py:367-383](../../../../../backend/agents/grader/agent.py)) sends the
objective labelled **"the marking standard"**, the `expected_answer` as a
*"calibration reference"*, the question, open gaps and the answer — and **no
source, no anchors, no `repo_path`** (F23). The verification grader is the same
(F25). Therefore:

- an oversimplified objective is not merely uncorrectable, it is **enforced** (F59);
- an answer matching a false objective is graded correct **by construction** (F82) — the Grader said so: *"which is exactly what the objective requires"*;
- **F82 and F59 are exact duals**, and **F85** closes it: the *same claim* about missing `locations` was graded `understood` at stop 16 and `wrong_model` at stop 17, minutes apart, each verdict tracking that unit's objective.

**"Source should win on conflict" is not a mis-set priority — it is
unimplementable as the call is currently constructed.**

**Two failures source would *not* have fixed**, which matters for sizing the remedy:

- **F49** (multi-gap miss): the correct condition (*"admissible"*) was already in the objective the Grader held. Detection recall, matching gap-model's own limitation #1.
- **F68** (attribution) and **F90**: in both, the answer and the claim it should have been compared against were *both already in the prompt*. A comparison the model had everything to make was not made.

**When grading was right, it was right for good reasons.** Stop 5 (two genuine
misconceptions recorded), stop 8 (BFS hop-vs-cost, correctly identified and well
corrected), stop 17 (both planted errors caught). Those rationales track substance
rather than wording.

---

## 5. Gap model and verification

**Detection and lifecycle split cleanly, and only one of them is broken.**

**[FACT] Detection: of 5 gaps opened, 2 record true statements and 1 records a
claim never made.**

| stop | gap | verdict |
|---|---|---|
| 2 | *"missing `locations` → `h()` returns `np.inf`"* | **true** — false gap (F20), still open, **blocking** |
| 5 | two `h`-related claims | genuine (deliberate wrong answer) |
| 8 | *"BFS guarantees shortest path with weights"* | genuine, **verified** (F53) |
| 11 | *"the heuristic must be consistent…"* | **true** — false gap (F59), non-blocking |
| 15 | *"…placing the new node at the end"* | **never stated** (F68), **blocking** |

Three false positives, three different mechanisms: confabulated rubric (F20),
objective-conformity enforcement (F59), inference-as-attribution (F68).

**[FACT] F60 — two recorded gap-model positions are contradicted.** The M2 addendum
excludes true statements from the gaps list; two got in. Limitation #3 holds
`right_idea_wrong_altitude` to be "nearly unreachable … because the addendum
excludes true statements" — it fired **on a true statement**, i.e. via exactly the
route assumed closed.

**Lifecycle behaved as designed, with one catastrophic exception.**

*Working:* `verified` is the only status permitting `understood` (F26);
non-blocking altitude gaps do not withhold mastery (F59); a passed warm-up closes
nothing (F31 credit); `verification_attempts` accounting is correct (F53); per-gap
discrimination correctly left the un-addressed `None` gap open (F90).

*Broken:* **F90.** `grade_verification` marked a gap `verified` on an answer that
restates it. `mark_verified` is documented as the sole producer of `verified`,
"which is what keeps the artifact meaningful", and M6's AC2 was accepted on a
double dissociation — *holding fails, corrected passes*. **The holding answer
passed.** The corpus went from 0 verified gaps across every database to 2, **one
false**, and nothing downstream can tell them apart. **F91** compounds it: the
verification question is not persisted, so a closure cannot be audited.

**[FACT] A learner cannot truthfully recover from a false gap (F26).** Every
affordance presumes learner fault: verification closes only by asserting the
falsehood; *Set aside* records *"you chose not to pursue this"* and permanently caps
the stop; doing nothing leaves it blocking; `mark_understood` cannot override the
block. **The lifecycle has no state for "the system was wrong."**

---

## 6. Adaptation and remediation

**[FACT] Remediation is a three-link chain, and this round broke each link
independently** (the reviewer's frame, adopted):

| link | broken | sound |
|---|---|---|
| learner evidence → gap | F20, F59, F68 | stop 5, stop 8 |
| gap → warm-up | F31/F32 (warm-up tested a different method) | F73 (well-built *for the stored gap*) |
| warm-up → evidence of closure | F31 (nothing links them) | F53 (genuine verification) |

**[FACT] Neither warm-up carries `remediates` (F31, F74).** `/retry` passes no
diagnosis; `Diagnosis.from_node` attaches a gap **only** when `decide_all` selects
`prerequisite`, and `wrong_model` — the commonest kind observed — selects
`reteach`. Learner-requested warm-ups for `wrong_model` gaps are therefore
**structurally unaimed**, and the code says so: *"aimed by the answer rather than"*
by a gap. A **designed** consequence of §18.5's one-mutation cap, not a generation
bug.

**Consequence for shipped analytics:** M3b's `remediation_closure` template counts
warm-ups carrying `remediates`. This session produced **two warm-ups and zero
links**. The template is **uncomputable in practice** for the commonest gap kind —
a different problem from the data-poverty M3b recorded.

**[FACT] Corrective lessons are permanent and second-person (F36, F37).** `reteach`
replaces `cached_lesson` outright. The reasoning — a returning learner should not
meet the version that misled them — is sound; the unexamined half is that the
*correction* is equally permanent and addressed to a state that expires. Stop 5
greets the learner forever with *"You just assigned the wrong responsibility"*,
including after they demonstrably corrected it (F35), and F37: the two unanchored
errors in that re-teach are now what the node renders on every visit.

**A fabricated misconception became curriculum.** F73/F94: the stop-14 warm-up
exists because of F68, occupies a numbered position in `path_order()`, and its
`setup` states the invented belief as the learner's own.

---

## 7. Navigation and UI

**[FACT] Presentation: the rail and the walk disagree (F19).** `buildSections`
buckets every stop by `area_id` and emits buckets in area order; `/advance`
follows the `sequence` chain. With interleaved areas — which this graph has
throughout — the two differ. **This induced the navigation later mistaken for a
user detour**: the reviewer followed the order the UI showed. The module's own
docstring ("the stops keep the order `buildRoute` produced") is true within a
section and false across sections.

**[FACT] State: a forward jump orphans stops permanently (F17).** `next_in_path`
re-enters the chain at the current node; nothing returns. Two stops were orphaned,
one of them **`required`** (stop 13). Compounding: `visited` is set only by
`/advance` (F18), so a stop studied and answered from the rail reads `visited=0`
forever, and `resume_point()` would return a learner to a lesson they completed.

**[FACT] The state model has no vocabulary for learner recovery (F38).** After a
correct re-answer the rail still reads *"◇ 2 unresolved"*. The count is accurate and
the derived state correct — but one caption covers both "never demonstrated" and
"latest answer reached the objective, checks pending". The distinguishing signal is
**already on the wire** (`attempts`, `state_matches_latest_answer`), and the
drawer's `pendingVerification` copy exists behind a condition that excludes this
case. With **F26** this is one theme twice: *the model represents what the system
concluded, never what the learner has since done.*

**Correct and worth recording:** frontend wiring is right (Continue → `advance`,
rail → `jump`, F10); the area introduction fires exactly as specified (F17); the
progress measures use `is_settled`, not `visited`, so they do not inherit F18.

**Warm-ups occupy canonical positions (F94)** — stops 4 and 14 in `path_order()`.
The data to separate them exists (`origin`, `progress.detours()`); the ordering
does not use it.

---

## 8. Source grounding and architectural boundaries

**[FACT] What each component receives:**

| component | source context | consequence |
|---|---|---|
| **Planner** | Dossier + Skeleton (not audited here) | writes objectives naming symbols the unit will not anchor (F1, F22) |
| **Teaching** | **every anchor of the unit, in order** — and no way to say "that is not in front of me" | correct inside anchors, confabulates outside (F71b) |
| **Re-teach** | unit anchors + answer + rationale + gaps | same, and it can adopt a learner's error (F50) |
| **Grader** | **nothing from the repository** | conformity to the objective is the only available standard (F23 → F20, F59, F82, F85) |
| **Verification grader** | **nothing from the repository** | cannot notice an answer restating the gap (F25 → F90) |
| **Mutator** | candidate chunks; writes nodes with `anchors: None` and deprecated `understand` (F34) | new nodes are born pre-B3 |

**The boundary that matters.** CLAUDE.md's guarantee — *"the model names a `file` +
`symbol`; our code derives the line range, so a hallucinated range is structurally
impossible"* — is **true of anchors and only of anchors**. It does not cover
(a) prose reasoning past the anchors (F21 family), (b) prose line citations, which
are unvalidated and were wrong in two of four cases under an undeclared reference
frame (F63, F70), or (c) the grading calls, which receive no anchors at all.

**Deterministically preventable:**

- objective/prose symbols must resolve within the unit's anchors (F1, F11, F21, F27, F39, F43, F45, F58, F65, F79) — **range-aware**, since F45 missed by two lines and F39 by seventy;
- a unit's anchors must lie within its own or its prerequisite closure's symbols (F28);
- a symbol a unit makes claims about must be anchored on that unit **or an earlier one** (F44, F65) — fires 5× on this journey; would have caught F20, F22, F29, F40;
- prose line citations must match the code they quote (F63, F70);
- an answer restating a gap's claim must not resolve it (F90);
- warm-ups must carry `remediates` (F31, F74).

**Requires model-level safeguards:**

- **property claims** — complexity, optimality, termination (F57, F58, F67, F71, F77, F79); no static rule decides whether "O(log n)" is true;
- **detection recall** — the second and third misconception in one answer (F49);
- **attribution discipline** — omission vs misconception (F68, F72);
- **internal consistency** across fields of one payload (F2, F7, F55, F57, F83) — model-level, but needing **no repository access**, which makes it the cheapest of these.

---

## 9. What the system got right

Collected deliberately, because a defect census mis-describes a system that mostly
worked.

**Grounding, where it applied.** Every claim inside a unit's anchors was correct in
every case checked (F41, F43, F54, F56, F88, and the warm-up at F75 whose anchored
half was flawless). The `anchors.resolve` guarantee held: **no hallucinated line
range ever appeared in an anchor** — only in prose (F63, F70), which is outside the
guarantee's scope.

**Design decisions that held under pressure.**

- **Only verification closes a gap.** A passed warm-up closed nothing, even though the warm-up was unaimed (F31 credit). The blocking rule (`verified` is the only status permitting `understood`) held throughout, including for a learner who asked to move on (F26 mitigation).
- **Non-blocking kinds behave as specified.** F59's false altitude gap did not withhold mastery.
- **Progress semantics are honest.** `journey_progress` uses `is_settled`, not `visited`, so F18's conflation does not reach the numbers (F18 checked-and-clean). The M1 invariant held: no plan mutation lowered demonstrated coverage.
- **Per-gap verification discrimination works for silence.** In F90 the un-addressed `None` gap correctly stayed open.
- **`verification_attempts` accounting is correct** and `gap_insight` compensates for it (F53).

**Behaviours verified live for the first time.**

- **§14 item 11 met** — 4 distinct `prompt_kind` values across a real journey, correctly derived from `kind` (F56). No prior live verification exists in the project record.
- **M6's `verify` → `grade_verification` path ran end to end** and produced one genuine closure (F53) — the milestone M3b was blocked on.
- **F1's return-to-the-failed-node behaviour** (learning-engine §14 item 8) worked: the warm-up advanced back to the parent unit.

**Content quality that was genuinely good.** The `None`-handling teaching at stop 17
(*"'no path exists' (a domain fact)" vs "'search succeeded' (a code fact)"*); the
states-not-Nodes distinction at stop 3 (F14, load-bearing for stops 9–10); the
`solution()`/`path()` unit (F54); the `expected_answer` discipline at stop 1 (F4)
and stop 3 (F14), where the graded field carried the careful version.

**Correct behaviour under a wrong contract.** Teaching built exactly the objective
it was given (F2); the Mutator declined to designate a gap because policy said
`reteach` (F31); the Grader applied its stated criterion faithfully (F82); the
frontend wired Continue and rail clicks correctly (F10). **Most components obeyed
their contracts. The contracts carried the defects.**

**Three reviewer concerns that did not materialise**, recorded so the system is not
blamed for them: the `expected_answer` did describe real runtime behaviour (F4);
the semantic condition on inherited defaults was present in all three fields (F14);
and `heapq.heappush` was never described as producing sorted order (F75 credit).

---

## 10. Root-cause clusters

Ninety-five findings reduce to **six** causes.

### A. The objective is the marking standard, and nothing can falsify it

- **Symptoms:** F20, F49 (partly), F59, F82, F85, F90.
- **Root cause:** the Grader and the verification grader receive the objective as *"the marking standard"* and **no repository source** (F23, F25). The objective is generated upstream by the planner and is never checked against code.
- **Learner impact:** correct answers marked wrong; wrong answers marked right; a gap closed on an answer that restates it.
- **Severity: P0.**
- **Deterministic?** Partly. Supplying source is deterministic; *using* it correctly is model-dependent. But F68 and F90 needed no source at all — the comparison was available in the prompt.

### B. Anchors are chosen per unit, with no memory of the journey

- **Symptoms:** F1, F11, F21, F27, F28, F39, F43, F44, F45, F58, F65, F75, F79, F86, F92.
- **Root cause:** anchor selection is per-unit and claim-blind; nothing checks that a unit anchors what it talks about, nor that a symbol was anchored earlier in the walk.
- **Learner impact:** confabulated mechanism claims, presented indistinguishably from grounded ones (F41).
- **Severity: P0** via the F20 chain; **P1** elsewhere.
- **Deterministic? Yes** — three checkable rules (§8).

### C. Property claims are prior-driven, anchored or not

- **Symptoms:** F57, F58, F61, F67, F71, F77, F79, F81, F86, F89; the A\*/UCS conflation across **seven surfaces**.
- **Root cause:** complexity, optimality and termination are *conclusions about* code. The model states the textbook conclusion and does not check the implementation that violates it — F71 did this with the contradicting source anchored.
- **Learner impact:** the most durable false beliefs, because they sound like understanding rather than detail.
- **Severity: P0.**
- **Deterministic? No.** Model-level safeguard only.

### D. One payload, written in one pass, with no self-comparison

- **Symptoms:** F2, F7, F33, F51, F55, F57, F62, F83, F86.
- **Root cause:** `setup`/`reveal`/`takeaway`/`objective` are generated together and never compared; the compressing fields drop the distinction the unit exists to teach.
- **Learner impact:** the retained summary is the most likely to be wrong.
- **Severity: P1.**
- **Deterministic? No, but cheapest** — one payload, no repository access.

### E. Assessment does not cover the objective

- **Symptoms:** F31/F32, F56, F80, F87.
- **Root cause:** Teaching writes one question from a multi-clause objective; the Grader marks against the whole objective. Neither side reconciles the scopes.
- **Learner impact:** passing proves less than the record claims — including for remediation, where passing gave no evidence about the triggering misconception.
- **Severity: P1.**
- **Deterministic?** Partly — clause coverage is checkable, the judgement is model-level.

### F. State represents what the system concluded, never what the learner has since done

- **Symptoms:** F17, F18, F19, F26, F35, F36, F37, F38, F94.
- **Root cause:** `visited` is written by one endpoint; the rail orders by area while the walk orders by chain; the gap lifecycle has no "system was wrong" state; `reteach` output is permanent and second-person.
- **Learner impact:** doing the right thing produces no visible change (F38); a corrected learner is told they were wrong forever (F35); required stops are silently orphaned (F17).
- **Severity: P1** (F17 and F26), **P2** (the rest).
- **Deterministic? Yes**, all of it.

### Causal chains worth naming

1. **The A\*/UCS chain.** Planner objective encodes "A\* degrades to UCS" (F22) → stop 2 lacks the `h` anchor and confabulates "returns 0 → UCS" (F20) → the Grader inherits the false `expected_answer` → a correct answer is marked `wrong_model` and a **blocking gap on a true claim** opens → the learner has no dispute path (F26) → the same proposition then reaches stop 16's lesson (F79), where a **wrong answer matching it is graded `understood`** (F82) → stop 17 grades the same claim a misconception (F85) → verification closes that gap on an answer restating it (F90). **One false proposition, seven surfaces, six components, no surface able to check another.**
2. **The anchor-borrowing chain.** Per-unit anchors → stop 3 borrows stop 4's anchor (F11) → dependency inversion (F28) → rail order differs from walk order (F19) → the learner jumps → `why_now` asserts an untaken transfer (F10) → the stop is orphaned (F17).
3. **The fabricated-gap chain.** The Grader infers list semantics from the word "append" (F68) → blocking gap → the learner requests a warm-up → the warm-up is well-built *for the stored gap* (F73) → carries no `remediates` (F74) → contradicts the unit it unlocks (F75) → **a misconception the learner never held becomes a numbered curriculum stop** (F94).

---

## 11. Recommended fixes

### P0 — can teach the learner something false

**P0-1. Give both graders the unit's anchor source, with an explicit precedence
rule.**
*Change:* pass `_read_node_source(...)` into `_build_user_content` and
`verification._user_content`; instruct that **source outranks the objective and the
calibration reference on conflict**, and that **a claim true of the repository is
never a gap even when the objective does not ask for it**.
*Addresses:* F20, F59, F82, F85; partially F49.
*Where:* `backend/agents/grader/agent.py`, `backend/agents/grader/verification.py`.
*Deterministic?* Delivery yes, use no.
*Trade-off:* **this is the round's main cost item** — anchor source on every graded
answer and every verification. Belongs in
[`cost-optimization.md`](../../cost-optimization.md)'s accounting before it ships.

**P0-2. Refuse to resolve a gap on an answer that restates its claim.**
*Change:* in `grade_verification`, require the verdict to identify what the answer
asserts *instead of* the gap claim; reject resolution when the answer's proposition
matches the claim. A cheap first cut is a same-claim check before `mark_verified`.
*Addresses:* **F90** — the single most damaging finding.
*Where:* `backend/agents/grader/verification.py`.
*Deterministic?* **Partly yes**, and this is the point: the answer and the claim
were both in the prompt. No new context required, therefore **no token cost**.

**P0-3. Plan-time anchor checks (three rules, all range-aware).**
*Change:* reject or flag a unit when (a) a symbol named in its `objective` does not
resolve within its own anchors; (b) its anchors are not within its own or its
prerequisite closure's symbols; (c) a symbol it makes claims about is anchored
**only later** in `path_order()`.
*Addresses:* F1, F11, F21, F27, F28, F39, F43, F44, F45, F58, F65, F79, F92 —
rule (c) alone fires 5× here and would have caught F20, F22, F29, F40.
*Where:* `backend/agents/mentor/curriculum.py` + `backend/repo/anchors.py`.
*Deterministic?* **Yes, fully testable without an API key** — which the phase
already treats as the bar for sizing logic.
*Trade-off:* may reject legitimate forward references — see [OPEN-1].

**P0-4. Constrain property claims.**
*Change:* instruct Teaching that complexity, optimality, termination and
"always/silently" claims may be made **only** when the anchored source states or
directly exhibits them; otherwise describe the mechanism and stop.
*Addresses:* F57, F58, F61, F67, F71, F77, F79, F81, F86, F89 — cluster C entire.
*Where:* Teaching prompts.
*Deterministic?* **No.** Partially testable by flagging property vocabulary in
prose for review.
*Trade-off:* lessons lose some explanatory reach; F71 shows what that reach is
currently worth.

### P1 — breaks learning flow or mastery semantics

**P1-1. A dispute path for gaps.** *Addresses:* F26, and it is the highest-value
signal the system could collect — a disputed gap is a labelled instance of F20/F59/F68.
*Where:* gap lifecycle + `/respond` surface. *Deterministic?* Yes. See [OPEN-2] for
what a dispute should *do*.

**P1-2. Self-consistency pass over the lesson payload.** *Addresses:* F2, F7, F33,
F51, F55, F57, F62, F83, F86. *Where:* Teaching, post-generation. *Deterministic?*
No, but **needs no repository access** — the cheapest fix in the round, and the only
one that works unchanged on a language the system cannot parse
([`multi-language.md`](../../multi-language.md)).

**P1-3. Link every warm-up to a gap, or state that it is unaimed.** *Change:*
`Diagnosis.from_node` should record the gap it is aimed at even when the policy
action is `reteach`, or `/retry` should record `remediates: []` explicitly with a
reason. *Addresses:* F31, F74, and it unblocks M3b's `remediation_closure`.
*Where:* `mutator.py`, `api.py`. *Deterministic?* Yes.

**P1-4. Do not orphan stops on a forward jump; do not conflate `visited` with
studied.** *Addresses:* F17, F18. *Where:* `graph.py` (`next_in_path`,
`resume_point`), `/jump`. *Deterministic?* Yes. See [OPEN-3].

**P1-5. Retry-reason classification on every attempt.** *Change:* record whether an
extra attempt was learner misunderstanding, a defective question, a grader
false positive/negative, or an incorrect expected model. *Addresses:* **F95** —
five of this session's grading events were defective in four different directions,
and M3a.2's shipped templates and M3b's gap analytics would read all of them as
evidence about the learner. *Where:* `learning/history.py` + the Grader envelope.
*Deterministic?* Partly. **This is a prerequisite for analytics already shipped**,
not an enhancement.

**P1-6. Separate remediation from the canonical path.** *Addresses:* F94, F73.
*Where:* `path_order()` / rail. *Deterministic?* Yes — `origin` is already on the wire.

### P2 — quality and UX

**P2-1. Vocabulary for "your last answer reached this".** F38 — one string and one
condition; the signal is already on the wire.
**P2-2. `why_now` must not assert transfer from an uncompleted unit.** F10 — the
predecessor's state is already loaded.
**P2-3. Rail order must equal walk order** (or say it is grouped). F19.
**P2-4. Validate prose line citations, or forbid them in favour of anchor-relative
references.** F63, F70 — stop 17 already shows the good form (F88 credit).
**P2-5. Phrase corrective lessons about the misconception, not the learner.** F36,
F37 — makes durability harmless without a re-render.
**P2-6. Persist the verification question.** F91 — a closure should be auditable.

---

## 12. Open product/design decisions

**[OPEN-1] Should an objective be allowed to name symbols outside its unit's
anchors?** *Alternatives:* forbid (catches F1/F21/F58, may block legitimate forward
references like "…so that `GraphProblem` can later supply `h`"); allow with a
required forward-reference marker; allow but require the symbol be anchored
*somewhere earlier* in the walk. **Recommendation: the third** — it is the rule that
fires 5× here and it permits forward reference while forbidding forward *dependence*.

**[OPEN-2] What should a dispute do to a gap?** *Alternatives:* delete it; mark it
`disputed` and non-blocking, retaining it as a signal; trigger a grounded re-check
against the anchors. **Recommendation: `disputed` + non-blocking + retained.** It
unblocks the learner immediately, keeps the evidence, and does not require a
model call to be trustworthy.

**[OPEN-3] Is a forward rail jump an instruction to skip, or a detour the walk
should later undo?** `optional` already answers a related question (stepped over,
kept in the graph). **Recommendation: treat it as a detour** — return to unfinished
`required` stops before completion, since F17 orphaned a `required` unit here.

**[OPEN-4] Should a corrective lesson be re-rendered once its gaps are verified?**
*Alternatives:* re-render (another Teaching call per closure); phrase corrections
impersonally so durability is harmless; keep a pre-correction version and swap back.
**Recommendation: the second** — free, and it removes the defect F35 exposed.

**[OPEN-5] What is this journey's actual scope?** F92 shows a path that is
*GraphProblem + best-first + A\** while its goal says "the search algorithms in
AIMA". **Recommendation: a product call, not a bug** — either narrow the goal
translation or require the planner to cover the algorithm families it names. The
reviewer's proposed structure (README §"Journey-level assessment") is the concrete
target if the broader reading is chosen.

**[OPEN-6] Does `CODEONBOARD_GAPS` stay on in dev given three false-positive
gaps?** The flag also rewrites the scalar `gap_kind` that selects the intervention.
**Recommendation: keep it on** — the false positives are the round's most valuable
evidence and are invisible with the flag off.

---

## 13. Evaluation of the learning journey itself

| dimension | assessment |
|---|---|
| **Coverage** | **Weak against the stated goal, strong against the actual one.** Two of ~8 search algorithms ever anchored; UCS named twice and grounded never (F47, F92) |
| **Ordering** | **Three real inversions**, all the same shape — claims precede their anchor by 1–4 stops (F28, F44, F48, F65) |
| **Granularity** | **Mostly right, one imbalance.** A dedicated unit on `PriorityQueue.append` internals while UCS and BFS get no runtime treatment (reviewer's point 3, supported by F92) |
| **Redundancy** | **Low and mostly healthy** — `Problem` revisited at stops 1, 3, 17 with different altitudes. The exception is harmful: stops 1 and 3 give *contradictory* accounts of the same anchor (F12, F16) |
| **Prerequisite handling** | **Declared edges under-specify actual dependence** (F28). Prerequisite closure is not enforced against anchors |
| **Kind balance** | **Good**: 6 `component`, 3 `architecture`, 2 `flow`, 2 `extension_point`, 2 `risk`, 1 `synthesis`. Kind→form mapping verified working (F56) |
| **Did warm-ups improve the path?** | **No.** Warm-up 1 tested `path_cost` for a gap about `h` (F32); warm-up 2 repaired a misconception the learner never had (F73). Neither carried `remediates` (F31, F74). Both added *nearby* content and neither produced evidence about the failure that triggered it |

**Pedagogically, the journey is better than its defects suggest.** The
API→runtime progression is genuinely good, the `kind` mix is well judged, and the
questions — where the objective was sound — tested transfer rather than recall
(stop 1's omit-`actions` vs omit-`path_cost`; stop 9's trace-both-outputs). The
failures are concentrated in **scope, ordering and grounding**, not in the choice
of what to teach.

---

## 14. Final verdict

### The 3–5 conclusions that matter

1. **Grading is measured against the system's own objective, not the repository.**
   F82 and F59 are duals; F85 shows the same claim graded both ways in one session,
   each verdict tracking a different unit's objective. Everything else in §4 follows
   from this.
2. **Anchor coverage predicts mechanism accuracy, and nothing predicts property
   accuracy.** Three controlled comparisons (F27, F54, F41) establish the first;
   F71 — a false complexity claim with the contradicting source anchored —
   establishes the second. **These need different fixes**, and conflating them was
   the round's own analytical error until F71 forced the revision.
3. **Verification, the artifact everything else depends on, is corruptible (F90).**
   `verified` is the only status permitting `understood`; one of the two verified
   gaps now in existence is false; and the question that closed it is not persisted
   (F91).
4. **The system has no representation for its own error.** No dispute path (F26),
   no retry-reason classification (F95), no state for "the learner has since
   corrected this" (F38). Consequently **its analytics will attribute its own
   defects to the learner** — and M3a.2's templates are already shipped.
5. **Most components obeyed their contracts; the contracts carried the defects.**
   Teaching built exactly the objective (F2); the Mutator followed §18.5 (F31); the
   Grader applied its stated standard (F82). This is why per-component fixes will
   not work and the three checks in P0-3 will.

### Must be fixed before this phase can be called complete

- **P0-2** (F90) — the phase cannot claim a working verification loop while a
  holding answer passes it. gap-model M6's AC2 must be re-run.
- **P0-1** (F23/F25) — grading with no source is the common cause of F20, F59, F82.
- **P0-3** (F44 rule (c) at minimum) — deterministic, testable without an API key,
  and it retires the largest family of content defects.
- **P1-5** (F95) — analytics that read system defects as learner difficulty are
  already live; this is a correctness issue for shipped features, not a nice-to-have.

### Safely deferred

Every P2; **P1-1** and **P1-6** (real, but the learner can work around them);
**F76/F77** (one broken example, though F77's class is covered by P0-4);
**F92 / [OPEN-5]** — a scope decision, not a defect. **M3b threshold calibration
must wait**: with 2 verified gaps of which 1 is false, and 0 `remediates` links,
its templates still have no trustworthy population.

### Is the manual E2E criterion closeable?

**Yes as an exercise, no as a pass.**

The criterion — *real sessions exercising the verify and waive flows* — **is
satisfied**: the flows ran end to end, produced the corpus's first verification
data, and surfaced 95 findings including five distinct grading failure modes.
`learning-graph.md` can record the round as **performed**.

But it **cannot be recorded as passed**, for three reasons stated plainly:

1. **F90 invalidates the data it was run to collect.** M3b's `verification_outcomes`
   would count a false closure as a real one.
2. **gap-model's own reopening bar is met.** Limitation #1 required *"a real learner
   session showing it materially affecting learning"* — F49 supplies it, and F50
   shows the corrective text then absorbing the undetected error. F60 additionally
   contradicts limitation #3 and the M2 addendum.
3. **Coverage is one session, one repo, one expert learner, four deliberately wrong
   answers.** F41 shows why `aima-python` flatters the system. A second round on a
   repository the model does not know — and by a learner who is not hunting for
   defects — is needed before any rate claim is defensible.

**[REC] Record the round as complete, the criterion as *performed, not passed*, and
gate closure on P0-1, P0-2, P0-3 and P1-5 plus a re-run on a second repository.**
