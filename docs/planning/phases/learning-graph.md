# Learning Graph — from route tracker to understanding model

**Status: written 2026-08-17. Product decisions taken 2026-08-17 (§11) — eight
resolved, OQ-5 deliberately still open. M1 done; M2 done (`6f57398`); M3 split
and M3a.1 done 2026-08-18. M3a.2 and M3b planned only.**

> **Gap-model cross-reference is current as of gap-model M8 (done 2026-08-18).**
> The phase moved fast while this document was being written: §2.4, §6.3 metric
> 20, §9 and §10 were corrected for M3, and the M3 split below was revised again
> for M7/M8. Detection, remediation, **closure (M6)**, derived state (M7) and
> learner intents (M8) are all in place. **M9 — gaps on the wire — is the one
> remaining gate**, and it blocks M3b only.

This document owns the *learner-facing understanding artifact*: the progress
model, the understanding profile, learning-pattern surfacing, and the UI that
carries them. It does **not** own the gap lifecycle — that is
[`gap-model.md`](gap-model.md), currently at M2, and §1.2 below states exactly
where the two phases touch.

**Labelling used throughout.** Every claim carries one of:

| marker | meaning |
|---|---|
| **[FACT]** | verified in this repository on 2026-08-17, with a file:line or a measurement |
| **[REC]** | design recommendation — a choice, defensible but not forced |
| **[ASSUME]** | working assumption that would change the design if wrong |
| **[OPEN]** | genuinely needs a product decision from the owner (collected in §11) |

---

## 1. Scope

### 1.1 The three questions, restated as engineering targets

| # | Learner question | What the system must be able to say | Hardest constraint |
|---|---|---|---|
| 1 | *Where am I?* | a defensible fraction of the **goal**, not of a node list, plus where detours happened | the denominator moves during a session (§5) |
| 2 | *What do I understand?* | strength and weakness **with denominators**, never a bare list of failures | ≤ 8 graded answers per session (§2.6) |
| 3 | *What patterns are emerging?* | repeated difficulty, intervention dependence, first-pass vs post-help | the actions that caused those patterns are **not persisted** (§4.1) |

### 1.2 Relationship to the gap-model phase — the seam

The gap-model phase already owns, and this plan must **not** re-invent:

| owned by gap-model | milestone | consequence here |
|---|---|---|
| `Gap` entity, status lifecycle, blocking rules | M1 ✅ / M2 ✅ | consume, never redefine |
| gap identity across re-grades (`refers_to`, id validation) | M3 ✅ | one misconception stays one gap — removes the duplicate-accumulation objection to collecting gap data early (§11 OQ-4) |
| gap **closure** (verification) | M6 | **nothing may render a gap to the learner before this** — until M6 a gap can only ever be `open` |
| derived `understanding_state` | M7 | **readiness inputs change under us** — §5.7 |
| `is_complete()` journey-completion predicate | M8 | this plan supplies the *fraction*, gap-model supplies the *boolean* |
| gauge relabel to *Verified understanding* | M9 | do the relabel once, here or there, not twice |
| attempt record gaining `kind`, `gaps_opened`, `gaps_resolved`, and the system's response | §18.9 | **this plan implements that record shape early** (M2 below) because it unlocks intervention metrics with or without gaps |

> **[REC] The single most important sequencing decision in this document:**
> implement §18.9's attempt-record shape *now*, flag-independent, and let the
> gap-model phase fill in its gap-specific fields later. It is additive JSON, it
> costs no schema version, and roughly half of the "learning patterns" capability
> depends on it. Postponing it until gap-model M5/M6 postpones question 3 entirely.

---

## 2. Current-state audit — verified facts

### 2.1 The model

**[FACT]** `LearningGraph` ([backend/learning/graph.py:157](../../../backend/learning/graph.py)) holds
`repo_url`, `goal`, `session_id`, `nodes: dict[id, LearningNode]`, `edges: list`,
`current_node_id`, `doc_context`, `areas: list[dict]`.

**[FACT]** `LearningNode` ([graph.py:79](../../../backend/learning/graph.py)) holds `title`,
`code_anchor(file, line_start, line_end, symbol)`, `concept_tags: list[str]`,
`lesson_brief: dict`, `understanding_state`, `visited`, `weak_spot`,
`user_override`, `cached_lesson`, `attempts: list[dict]`, `gap_state: GapState`.

**[FACT]** `lesson_brief` is the free-form payload carrying `objective`, `why`,
`kind`, `priority`, `area_id`, `anchors`, and `scope_locked`. It is **not**
exposed wholesale on the wire — `to_dict` cherry-picks four keys
([graph.py:404-427](../../../backend/learning/graph.py)).

**[FACT]** Attempt record is exactly `{answer, classification, gap_kind, rationale, at}`
([graph.py:212-221](../../../backend/learning/graph.py)). Append-only; a revisit adds rather than replaces.

**[FACT]** Edge kinds are `sequence`, `prerequisite`, `deeper`. `prerequisite` has
**two producers with different meanings** — planned `depends_on` edges from the
B3 planner ([curriculum.py:658-662](../../../backend/agents/mentor/curriculum.py)) and
remedial splices from the Mutator ([mutator.py:215](../../../backend/agents/mentor/mutator.py)).
The only discriminator is structural: a remedial node has **no outgoing sequence
edge**, because `insert_before` rerouted it away
([graph.py:258-261](../../../backend/learning/graph.py)). Both `_has_prerequisite`
and the frontend's `unlockTargetOf` already implement this rule
([graph-layout.ts:53](../../../frontend/lib/graph-layout.ts)).

### 2.2 Persistence

**[FACT]** SQLite, three tables, `SCHEMA_VERSION = 2`
([store.py:29](../../../backend/learning/store.py)). New fields are added as
nullable columns via a swallowed `ALTER TABLE`; five have been added that way
(`doc_context_json`, `attempts_json`, `symbol`, `areas_json`, `gaps_json`).
Nodes and edges are **replaced wholesale** on every save (delete + reinsert,
[store.py:186-202](../../../backend/learning/store.py)).

**[FACT]** There is **no event, history, or audit table.** Session state is a
snapshot plus the per-node `attempts` list.

**[FACT]** `gaps_json` is written **unconditionally** and the persistence path
never reads `CODEONBOARD_GAPS` — pinned structurally by a test
([flags.py:14-19](../../../backend/learning/flags.py)).

### 2.3 Assessment and adaptation

**[FACT]** The Grader maps `understood → understood`, `partial → partial`,
`confused → failed`; `off-topic` is deliberately absent and changes nothing
([grader/agent.py:53-57](../../../backend/agents/grader/agent.py)).

**[FACT]** `adaptation.decide(classification, gap_kind) → none | hint | reteach |
prerequisite | followup` — a pure table, gap outranks classification
([adaptation.py:42-88](../../../backend/learning/adaptation.py)).

**[FACT] The chosen action is never persisted.** `/respond` computes `adapted`,
returns it to the client, and drops it
([api.py:508-568](../../../backend/api.py)). Same for `state.last_mutation`. So
the system cannot answer "was this node ever re-taught?" after the response
round-trip ends.

**[FACT]** `reteach` **overwrites** `node.cached_lesson`
([respond.py:193](../../../backend/agents/teaching/respond.py)). The lesson that
misled the learner is gone; only the attempt text survives.

**[FACT]** A grading failure produces `classification="partial"` with rationale
`"grading failed; defaulted to partial"` ([grader/agent.py:116, 376](../../../backend/agents/grader/agent.py))
— indistinguishable from a genuine partial in every downstream metric.

### 2.4 Gaps — current reality

**[FACT]** M1, M2 and **M3** are done (M3 landed 2026-08-17, while this document
was being drafted). **Detection is complete; gap-model M4 — response — is next.**
Multi-gap detection ships behind `CODEONBOARD_GAPS`, default **off** in code.
`Gap` carries `id, kind, claim, objective_part, foundational, status,
verification_attempts, objective_key, origin_attempt, resolved_by, opened_at,
closed_at`.

**[FACT] Identity across re-grades holds, and it is measured.** On a re-grade the
open gaps are supplied with their ids; `GapOut.refers_to` names one or says
`new`; an id outside the supplied set is discarded whole rather than guessed at
([grader/agent.py:519-545](../../../backend/agents/grader/agent.py)). A matched
gap mints nothing and changes nothing — one misconception stays one gap. M3's
required measurement, 6 real nodes × 3 grades = 18 calls
([`evidence/m3-gap-identity/`](evidence/m3-gap-identity/README.md)): **29 matched,
1 `new`, 0 hand-judged duplicates, 0 invented ids, and 0 duplicates on the
verbatim identity floor.**

> **This retires the duplicate-gap risk as an argument for delaying gap
> collection.** An earlier draft of this document treated re-grade duplication as
> a live hazard; it was the stated price of refusing text-similarity merging, and
> M3 measured that price at zero.

**[FACT] Closure is still not implemented, and this is the real remaining
limitation.** `status` is only ever `open`; `resolved_by`, `closed_at` and
`verification_attempts` are never written by production code. Verification is
gap-model M6. **Consequence: a session's gap list grows monotonically and can
never shrink.** That is harmless as stored evidence and actively misleading as a
displayed list, which is why §11 OQ-4 collects gaps now but shows none until M6.

**[FACT] The flag changes runtime learning behaviour, not only data collection.**
Three call sites read it — the system prompt
([grader/agent.py:332](../../../backend/agents/grader/agent.py)), the user
message's open-gaps section ([:366](../../../backend/agents/grader/agent.py)),
and `_record_gaps` ([:434](../../../backend/agents/grader/agent.py)). The third
**overwrites `output.gap_kind`** with the dominant kind of the gaps found in that
answer, and that scalar flows `state.last_grade` → `/respond` →
`adaptation.decide()` → **which intervention fires** (hint / re-teach /
prerequisite / follow-up), and into the Mutator's `Diagnosis`. Measured direction
of the change: `gap_kind` agreement **47, 47, 48 of 48 flag-on against a baseline
of 45**, and the `missing_prerequisite` diagnosis — the one that triggers a
structural graph mutation — went **4/6 → 6/6**
([`evidence/m2-grader-gate/`](evidence/m2-grader-gate/README.md)). The change is
real and measured to be an improvement; it is not a no-op.

**[FACT]** Residual detection-quality limitation: 0–2 of 48 evaluation cases per
run still phrase a gap as an *omission* rather than a false claim (down from 15
in the first prompt revision). Acceptable for research data; a second reason not
to surface gap text to a learner yet.

**[FACT]** `objective_key()` (sha1 of case-folded, whitespace-normalised
objective, [gaps.py:114-128](../../../backend/learning/gaps.py)) is written onto
gaps and **read by nothing**.

**[FACT]** Gaps do not appear in `to_dict`, so they are not on the wire at all.

**[FACT] Measured 2026-08-17 against `data/sessions.db`: 0 gaps stored across all
62 sessions.** Every gap-derived capability therefore starts from zero live data.

### 2.5 Frontend

**[FACT]** `MapView.tsx` computes all aggregates **client-side** from the node
list: overall tally, `byTag` split into canonical "kinds" vs free-form "topics",
`byFile`, `weak` count, and renders the route
([MapView.tsx:91-131](../../../frontend/components/MapView.tsx)).

**[FACT]** All tallies are over **every node**, including `not_started`. On a
16-unit journey with 3 answers, "By kind of understanding" is ~80% grey — it
reports curriculum composition, not understanding.

**[FACT]** `RouteRail.tsx` already does area grouping, optional collapse, the
remedial-prerequisite indent and caption, and a state legend.

**[FACT]** `Attempt` in [api.ts:104](../../../frontend/lib/api.ts) declares
`{answer, classification, rationale, at}` — **`gap_kind` is on the wire but not
in the type**, so it is available for free.

**[FACT]** `user_override` is on the node but **not** in `to_dict`, so the UI
cannot distinguish a learner-asserted `understood` from an evidenced one.

### 2.6 Data volume — the constraint that shapes §7

**[FACT] Measured 2026-08-17 from `data/sessions.db`:**

| measurement | value |
|---|---|
| sessions | 62 |
| nodes | 574 |
| nodes carrying `priority` (B3 graphs) | 42 |
| nodes with ≥1 attempt | 29 |
| **total graded attempts, all sessions ever** | **40** |
| attempts per node | 1 → 20 nodes, 2 → 7, 3 → 2 |
| sessions containing any attempt | 6 |
| **most answers in a single session** | **8** |
| classifications | understood 12, partial 9, confused 9, **off-topic 10** |
| `gap_kind` | wrong_model 7, right_idea_wrong_altitude 6, missing_prerequisite 5, no_attempt 4, none 9, absent 9 |
| stored gaps | 0 |

Two consequences, and they are the backbone of this plan:

1. **A session's evidence base is single-digit.** Any claim about "how this
   learner reasons" rests on ≤ 8 observations, of which ~25% are `off-topic` and
   carry no signal. §7 is built around this.
2. **Off-topic is a quarter of all evidence.** It must be excluded from
   understanding aggregates and reported separately as engagement, or every
   profile is skewed by non-answers.

### 2.7 Planner-flag reality

**[FACT]** Code default is `CODEONBOARD_CURRICULUM=0` (pre-B3 planner: no `kind`,
`priority`, `area_id`, no `areas`, sequence edges only). **`run-dev.bat` sets it
to `1`**, so development runs on B3. 42 of 574 stored nodes are B3-planned.

**[REC]** Design for B3 as the target shape and make every metric **degrade
explicitly** on pre-B3 graphs (missing `priority` ⇒ treat as `required`; missing
`area_id` ⇒ one implicit area) rather than silently producing a different number.

---

## 3. Target product model

### 3.1 The two layers the vision asks for

| layer | what it is | today |
|---|---|---|
| **Learning Route** | the ordered walk: stops taken, current position, detours, what's ahead | exists and is good — rail + `buildRoute` |
| **Understanding View** | what has been *demonstrated*, where it is thin, how the pieces relate | does not exist; MapView is a route summary wearing its clothes |

**[REC] Do not build a concept/knowledge graph yet.** The repository has no
stable concept identity (§4.3) and single-digit evidence per session. The
correct intermediate representation is:

> **The objective is the unit of understanding.**

Justification, all **[FACT]**: `objective` is already the contract between
Planner, Teaching and Grader (CLAUDE.md; `LearningNode.objective()`); it already
has a stable hash (`objective_key`); gaps already attach to it via
`objective_part` and `objective_key`; and it is authored per unit rather than
free-typed like `concept_tags`. Everything the vision asks for at V1 — mastery,
partial understanding, repeated attempts, remediation provenance — is expressible
as *evidence about objectives*, without inventing a concept ontology.

Concepts (as entities, with `part_of` / `flows_into` relationships) become
worthwhile only when there is cross-session evidence to aggregate. That is M5.

### 3.2 The evidence spine

```
attempt  ──produces──▶  verdict (classification)      ─┐
   │                    diagnosis (gap_kind, gaps)     ├──▶ evidence about an OBJECTIVE
   └──causes───▶  system response (hint/reteach/       │
                  followup/prerequisite/prune)        ─┘
                            │
                            └── remedial node (its own objective, linked back)
```

Everything in §6 and §7 is an aggregation over that spine. **[FACT]** The middle
row — the system response — is exactly the row that is not persisted today.

---

## 4. Data gaps between current state and target

### 4.1 Missing: the intervention record — **cheap, high leverage**

**[FACT]** Not persisted: which action fired, whether re-teach succeeded, hint
and follow-up text, whether prune-ahead fired and on what, whether a
prerequisite was declined and why (`no_useful_prerequisite` + rationale exists in
`last_mutation` and is discarded), whether the learner requested the warm-up or
the system chose it.

Unlocks (all of question 3): intervention rate, hint dependence, re-teach
dependence, first-pass vs post-intervention understanding, "the system offered
help N times and you needed it M times", decline visibility.

Cost: **additive keys on the existing attempt dict** — no column, no schema
version. §18.9 already specifies the shape.

### 4.2 Missing: lesson version history

**[FACT]** Re-teach overwrites. "How your understanding evolved" cannot show the
before/after pair that makes a re-teach legible.

**[REC]** Keep prior lesson bodies in `lesson_brief["lesson_versions"]` (append,
cap at 3) rather than growing `cached_lesson`, whose owner overwrites it — the
same reasoning gap-model §3.3 gives for `pending_verification`.

### 4.3 Missing: concept identity

**[FACT]** `concept_tags: list[str]` mixes a 7-value canonical vocabulary with
free-typed domain tags. Measured tag counts: `component` 425, `flow` 335,
`architecture` 251, `extension_point` 171, then `auth` 132, `dependency
injection` 84, `risk` 81, `test_coverage` 7, and a long tail of singletons
(`search`, `callable`, `caching`, `graph-search`, `delegation`…).

**[FACT]** No registry, no normalisation, no cross-node index. `auth` and
`authentication` are different concepts to this system.

**[REC]** Do **not** aggregate understanding by free-form tag and present it as a
strength profile. Canonical `kind` is safe (fixed vocabulary, model chooses from
a list, already the Grader's rubric selector). Free-form tags stay a "topics
touched" display, as today.

### 4.4 Missing: remediation provenance chain

**[FACT]** Derivable today: *that* node P is remedial and *which* node it unlocks
(topological rule, §2.1). **Not** derivable: which attempt caused it, which gap
it addresses, whether the return attempt succeeded.

**[REC]** Write it explicitly at insertion: `lesson_brief["origin"] =
"system_remediation" | "learner_request" | "planned"`, plus
`lesson_brief["remediates"] = {node_id, attempt_index, gap_ids: []}`. §18.11
already sanctions `origin`; §18.5/M5 already names `remediates`. Keep the
topological rule as the fallback for the 62 existing graphs.

### 4.5 Missing on the wire (backend knows, frontend cannot see)

**[FACT]** `objective`, `user_override`, `gap_state`, `lesson_brief["why"]`,
attempt `gap_kind` (present but untyped). No backend change needed beyond
`to_dict` — this is the cheapest capability in the whole plan.

### 4.6 Missing: grading-failure marker

**[FACT]** §2.3. A grading failure silently scores 0.5 in `readiness()`.

**[REC]** `attempt["graded"] = False` on the fallback path; exclude those
attempts from every understanding metric and count them as system errors.

---

## 5. Progress percentage — the specific investigation

### 5.1 What `readiness()` does today

**[FACT]** [graph.py:358-382](../../../backend/learning/graph.py):

```
weight   = {understood: 1.0, partial: 0.5}        # failed and not_started → 0
core     = [n for n in nodes if priority != "optional"]
earned   = Σ weight(n.state) over ALL nodes       # including optional
readiness = min(earned / len(core), 1.0)
```

### 5.2 Six defects, four of them verified by execution

**[FACT] D1 — inserting a remedial prerequisite *lowers* the number.** Executed
2026-08-17 on a 2-node graph with one node understood:

| event | readiness |
|---|---|
| baseline | **0.50** |
| system inserts a remedial prerequisite | **0.33** |
| learner skips the blocked node | 0.33 |
| learner completes an optional unit | 0.67 |

The Mutator marks its warm-up `priority: "required"`
([mutator.py:402](../../../backend/agents/mentor/mutator.py)) — deliberately, so
"make it shorter" cannot take away a remediation — which places it in the core
denominator. **The gauge falls at the exact moment the system decides to help.**
This is the single worst defect in the current model and it directly answers the
brief's question "may the percentage decrease when the system discovers a missing
prerequisite": today it does, and it should not.

**[FACT] D2 — skipping is punitive and permanent.** `override(id, "skip")` sets
`visited` but leaves `understanding_state = "not_started"`
([graph.py:243-244](../../../backend/learning/graph.py)), so the node sits in the
denominator scoring 0 forever. Verified above.

**[FACT] D3 — reading everything and answering nothing gives 0%.** `/advance`
marks `visited` without grading ([api.py:435](../../../backend/api.py)). A learner
who walks the whole journey without answering finishes at 0% under a label that
says "Readiness" — which is *semantically correct* for verified understanding and
*experientially wrong* as the only number on screen.

**[FACT] D4 — the denominator moves for non-evidence reasons.** `prune_ahead`
([adaptation.py:99](../../../backend/learning/adaptation.py)) and
`scope.shorten/deepen` ([scope.py:59,83](../../../backend/learning/scope.py))
demote/promote units, changing `len(core)` mid-session. Pinned by
`test_pruning_ahead_raises_readiness_rather_than_lowering_it`.

**[FACT] D5 — `partial` from a grading failure scores 0.5** (§2.3, and the
docstring admits it).

**[FACT] D6 — every unit weighs the same.** A dependency-closed `required` unit
and a "included if there is room" `recommended` unit are identical to the
formula.

### 5.3 The invariant to design to

> **[REC] Progress may fall only when evidence about the learner changes.
> It must never fall because the system changed the plan.**

Falls that are legitimate: a re-answer graded worse; a gap opening under
gap-model M7; the learner choosing "deeper" (their own action, and the UI should
say the journey grew). Falls that are bugs: remedial insertion (D1), skip
accounting (D2), any denominator change the learner did not ask for.

This invariant is mechanically testable and should be a test file of its own.

### 5.4 Recommended model — two numbers, no invented weights

**[REC]** Replace one ambiguous gauge with two crisply-defined ones. This avoids
inventing a `required = 1.0 / recommended = 0.6` weighting, which would be
exactly the unjustifiable constant [LD14](learning-engine.md#151-accepted-ld)
warns against.

**A · Goal readiness** — *"how much of what this goal actually requires have I
demonstrated?"*

```
promised(n)  = origin(n) == "planned"           # excludes remedial + learner warm-ups
core(n)      = promised(n) and priority(n) == "required"
              (pre-B3: no priority ⇒ required)

numerator    = Σ w(state(n)) for n in core
denominator  = |core|
w            = {understood: 1.0, partial: 0.5, failed: 0, not_started: 0}
```

Justification for using `required` as the denominator, **[FACT]**-based: `select()`
defines `required` = the model's required set **plus its dependency closure plus
one promoted unit per area** ([curriculum.py:169-190](../../../backend/agents/mentor/curriculum.py)).
That set is *by construction* "the goal is not met without this". A fraction over
it is a goal-readiness claim, not a node count. Calibration data shows core is
9–18 units against journeys of 11–24, so it is a substantial majority, not a
token subset.

**B · Journey progress** — *"how far along the planned walk am I?"*

```
settled(n)   = visited or attempts or user_override
numerator    = |{n : promised(n) and priority(n) != "optional" and settled(n)}|
denominator  = |{n : promised(n) and priority(n) != "optional"}|
```

This is deliberately a *coverage* measure, not a mastery measure — it is what
makes D3 tolerable: the learner who read everything sees "Journey 16/16 · Goal
readiness 0%", which is honest in both directions.

**Optional units:** excluded from both denominators (unchanged intent), and
**excluded from the goal-readiness numerator too** — today's "optional credit,
capped at 1.0" is what produced the 0.67 in the D1 table above, a number that
means nothing. Optional work is reported as its own line: "2 optional units
completed".

**Remedial units:** excluded from both. Reported as *detours*, with their own
counter and their own outcome ("3 warm-ups, 2 unblocked the unit that needed
them"). This is what fixes D1.

**[DECIDED 2026-08-17 — OQ-2]** The alternative considered was letting a
completed warm-up add credit to the node it unlocks: more rewarding, less honest,
since the blocked objective has not been demonstrated. **Decision: no credit.**
Remedial detours are represented separately, and the progress number moves when
the learner re-answers the unit the warm-up unblocked.

**Skips (D2):** a skipped node is `settled` for journey progress and scores 0 for
goal readiness, but the UI must state it: "3 stops skipped" beside the readiness
number. Silence here is what makes a low number feel arbitrary.

### 5.5 Behaviour under every mutation, stated

| event | goal readiness | journey progress | correct? |
|---|---|---|---|
| remedial prerequisite inserted | **unchanged** | unchanged | yes — fixes D1 |
| warm-up completed | unchanged | unchanged; detour counter +1 | §5.4 / OQ-2 |
| return attempt on the blocked unit succeeds | **rises** | rises | yes |
| `prune_ahead` demotes recommended → optional | unchanged (core untouched) | denominator shrinks ⇒ **rises** | yes — the journey genuinely got shorter |
| `scope: shorter` | unchanged | rises | yes, learner-initiated |
| `scope: deeper` | unchanged | **falls** | acceptable — learner asked for more; UI must say "journey extended to N stops" |
| skip | unchanged | rises | yes, with the skip count shown |
| re-answer graded worse | **falls** | unchanged | yes — evidence changed |
| gap-model M7 re-derives a node out of `understood` | **falls** | unchanged | yes, and the UI must name the gap that caused it |

Note that **`scope: shorter` and `prune_ahead` cannot inflate goal readiness**
under this model, because they only ever touch `recommended`
([scope.py:59-80](../../../backend/learning/scope.py),
[adaptation.py:146-148](../../../backend/learning/adaptation.py)). That is a real
improvement over today, where shortening the journey raises the headline number.

### 5.6 Where it is computed

**[REC]** A new pure module `backend/learning/progress.py`, no IO and no model
calls, in the style of `scope.py` / `adaptation.py`. Reasons: testable without an
API key (the project's stated standard), one source of truth for the header, the
map, the completion screen and any future report, and it stops the frontend
recomputing aggregates from raw nodes (§2.5).

`readiness()` stays on `LearningGraph` as a **deprecated alias** for goal
readiness during M1 so `/scope`'s response key and the 6 call sites keep working.

### 5.7 Coordination with gap-model M7

**[FACT]** M7 makes `understanding_state` derived, so a node with an open
blocking gap cannot be `understood`. **[ASSUME]** M7 lands after this plan's M1.
Consequence: goal readiness will step down once for existing sessions when M7
ships. gap-model §3.4 already records the decision that `readiness()` stays
node-weighted, not gap-weighted — this plan does not disturb that.

---

## 6. Metric catalogue

Format per the brief: question → source → exists today → calculation →
uncertainty → fact or inference.

Legend for column 6: **FACT** = safe to state plainly; **FACT-WITH-DENOM** = safe
only if the denominator is shown; **INFERENCE** = must be phrased as a reading of
evidence and be inspectable.

### 6.1 Available from data that exists today (no backend writes)

| # | Metric | Question | Source | Calculation | Uncertainty | Claim type |
|---|---|---|---|---|---|---|
| 1 | **Goal readiness** | how far toward the goal? | `understanding_state`, `lesson_brief.priority`, origin | §5.4 A | `partial` conflates genuine partial with grading failure (D5) until §4.6 | FACT-WITH-DENOM |
| 2 | **Journey progress** | how far along the walk? | `visited`, `attempts`, `user_override`, `priority` | §5.4 B | says nothing about mastery — must never appear without metric 1 | FACT |
| 3 | **Assessed coverage** | how much of this is actually evidenced? | `attempts` per node | `|{n : any attempt with classification != off-topic}| / |promised non-optional|` | none | FACT |
| 4 | **State mix** | what's understood / partial / weak / untouched? | `understanding_state` | counts over promised non-optional nodes | today's version counts *all* nodes and reads as mostly grey (§2.5) | FACT |
| 5 | **First-pass understanding rate** | how much did I get right without help? | `attempts[0].classification` | `|{n : attempts[0] == understood}| / |{n : ≥1 non-off-topic attempt}|` | attempt 0 may follow an *un-recorded* hint until M2 — so it is "first answer", not strictly "no help"; label accordingly | FACT-WITH-DENOM |
| 6 | **Recovery rate** | when I got it wrong, did I get there? | `attempts` sequence | `|{n : an early failed/partial attempt followed by a later understood}| / |{n : any early shortfall}|` | denominators of 2–3 are common; suppress below 3 | FACT-WITH-DENOM |
| 7 | **Attempts per assessed unit** | how hard did each unit fight back? | `len(attempts)` | mean and max over assessed nodes | 27 of 29 answered nodes have ≤2 attempts (§2.6) — low spread | FACT |
| 8 | **Why answers fall short** | what kind of shortfall recurs? | `attempts[].gap_kind` (**already on the wire**) | count by kind, over non-`none` non-absent values | 9 of 40 stored attempts predate the field | FACT-WITH-DENOM |
| 9 | **Understanding by kind of understanding** | flows vs components vs architecture | canonical `kind` / `concept_tags[0]`, `understanding_state` | per-kind tally **over assessed nodes only** | per-kind denominators are 1–4 in a real session — the reason §7 sets thresholds | FACT-WITH-DENOM |
| 10 | **Understanding by area** | which part of the system is thin? | `lesson_brief.area_id` + `graph.areas` | per-area tally over assessed nodes | empty on pre-B3 graphs — fall back to file | FACT-WITH-DENOM |
| 11 | **Detours taken** | where did I need to step back? | topological remedial rule (§2.1) | count + list, with the unit each unlocks | cannot say *why* the detour happened until M2 | FACT |
| 12 | **Needed a second pass** | which units were rough? | `weak_spot` + attempt history | list, split into "still weak" vs "recovered" | **`weak_spot` is sticky by design** — presenting it as *current* weakness is wrong (§10 R4) | FACT, if split |

### 6.2 Unlocked by M2 instrumentation (small additive persistence)

| # | Metric | Question | Source (new) | Calculation | Uncertainty | Claim type |
|---|---|---|---|---|---|---|
| 13 | **Intervention rate** | how often did the system have to step in? | `attempt.response.action` | `|attempts with action != none| / |attempts|` | conflates "system offered" with "learner needed" | FACT-WITH-DENOM |
| 14 | **Intervention mix** | what kind of help? | same | counts by hint / reteach / followup / prerequisite | — | FACT |
| 15 | **Unassisted vs assisted understanding** | did I get it, or did the system get it for me? | `attempt.response` on the *preceding* attempt | partition understood nodes by whether any prior attempt triggered an intervention | this is the honest version of metric 5 | FACT-WITH-DENOM |
| 16 | **Remediation effectiveness** | did stepping back work? | `remediates` link + return attempt | `|detours whose blocked unit later reached understood| / |detours|` | denominators of 1–3; suppress below 3 | FACT-WITH-DENOM |
| 17 | **Declined remediations** | did the system look and find nothing? | persisted `no_useful_prerequisite` + rationale | count + reason | — | FACT |
| 18 | **Grading reliability** | how much evidence is trustworthy? | `attempt.graded` | count of fallback grades | — | FACT (internal / debug surface) |

### 6.3 Requiring new domain modelling (M4+)

| # | Metric | Question | Source (new) | Uncertainty | Claim type |
|---|---|---|---|---|---|
| 19 | **Objective mastery index** | which *claims* can I make? | `objective_key` promoted to a first-class index | objectives are per-session text; identical text across sessions is the only match | FACT-WITH-DENOM |
| 20 | **Cross-node repeated difficulty** | is the same misunderstanding recurring? | gaps grouped by `kind` + `objective_key`; **within one node, repetition is already exact** — gap-model M3 keeps one misconception as one gap across re-grades | needs gaps enabled (now on in dev per OQ-4) and ≥3 gaps. **0 stored at the time of writing**; the corpus starts accumulating from the OQ-4 decision. Cross-*node* identity is still unsolved — `objective_key` differs per unit, so this remains an inference | INFERENCE |
| 21 | **Shared-cause hypothesis** | do these mistakes have one root? | clustering over gap `claim` text | genuinely uncertain; §7 Level 3 | INFERENCE — hypothesis only |
| 22 | **Cross-session profile** | how has this learner changed? | learner identity (deferred, LQ7) | blocked | INFERENCE |

---

## 7. Pattern detection — strategy and thresholds

### 7.1 The hierarchy

```
L0  RAW EVIDENCE          attempts, verdicts, gap kinds, interventions
      │                   shown verbatim, attributable to one moment
      ▼
L1  DETERMINISTIC         counts and rates with denominators
    AGGREGATE             "2 of 3 flow units needed a second attempt"
      │
      ▼
L2  REPEATED PATTERN      a named, pre-defined template fires on a threshold
                          "Flow units have needed more attempts than component units"
      │
      ▼
L3  HIGHER-LEVEL          "you find cross-component reasoning harder than
    INFERENCE             local reasoning" — a claim about the person
```

### 7.2 Evidence thresholds

**[REC]** These are the gates. They are deliberately strict because §2.6 measured
the ceiling at 8 answers per session.

| level | may be shown when | phrasing | dismissible |
|---|---|---|---|
| **L0** | always | plain statement of what happened, with timestamp and node | n/a |
| **L1** | denominator ≥ 2 | "2 of 3 …" — **denominator always visible**, never "2 flow questions wrong" | n/a |
| **L2** | ≥ 3 supporting observations, across ≥ 2 distinct nodes, **and** a contrast group with ≥ 2 observations | "**Observed:** flow units have taken more attempts (3 of 4) than component units (0 of 5)." Descriptive, past tense, about *answers*, never about the person | yes |
| **L3** | ≥ 8 non-off-topic attempts in the session, ≥ 3 shortfalls, spanning ≥ 2 kinds or areas, **and** at least two L2 patterns pointing the same way | "**One reading of this:** …" — explicitly a hypothesis, with the evidence listed underneath | yes, and dismissal is recorded |

**[FACT]** Against measured data, the L3 gate would have fired in **at most 1 of
62 sessions** (the two 8-answer sessions, and only if ≥3 fell short). That is the
correct outcome — it means the product does not psychoanalyse anyone on four
data points.

### 7.3 Does the first version need an LLM? No.

**[REC] Deterministic aggregation only, for L0–L2.** Reasons, in order of weight:

1. **Volume.** ≤ 8 observations per session. An LLM given four data points and
   asked for "learning patterns" will produce fluent, confident, unfalsifiable
   prose — the same failure mode `learning-engine.md` §4.1.2 refuses for
   ungrounded lessons, applied to the learner instead of the code.
2. **Reproducibility.** A pattern that appears and disappears between page loads
   destroys trust in an artifact whose entire value is being trustworthy.
3. **Cost.** The project runs at <$0.10/run on a ~$7/month budget. A per-view
   analysis call is a per-view cost.
4. **Testability.** Deterministic templates are pure functions — the standard
   this codebase already holds `select()`, `decide()` and `prune_ahead()` to.

**[REC] The one place an LLM eventually earns its keep** is L3 *shared-cause
clustering over gap claims* — "these three false statements may share one root" —
because that is genuine semantic judgement over text. It requires gaps to be
enabled, ≥3 gaps to exist, and its output must be labelled a hypothesis. **Not in
this phase.**

### 7.4 The L2 pattern templates (V1 set)

Each is a pure function `(graph) → Pattern | None`. Six is enough; adding more is
cheap once the harness exists.

| template | fires when | example output |
|---|---|---|
| `kind_contrast` | one canonical kind's shortfall rate exceeds another's, both denominators ≥ 2, ≥ 3 total observations | "Flow units have taken more attempts than component units (3 of 4 vs 0 of 5)." |
| `recurring_gap_kind` | one `gap_kind` accounts for ≥ 3 shortfalls across ≥ 2 nodes | "Three answers fell short the same way: right idea, wrong altitude." |
| `area_thin` | an area's assessed units are ≥ 2 and none reached `understood` | "Nothing in *Request lifecycle* has been demonstrated yet (0 of 3 assessed)." |
| `intervention_dependence` (M2) | ≥ 3 attempts required an intervention out of ≥ 5 | "3 of 5 answers needed the system to step in." |
| `recovers_after_help` (M2) | ≥ 3 units understood only after an intervention | "You reached 3 of 4 objectives after a second pass rather than on the first." |
| `first_pass_strength` | ≥ 4 assessed units, ≥ 75% understood first time | "Most units landed on the first answer (4 of 5)." — strengths matter as much as weaknesses |

**[REC]** Every pattern card carries an **"evidence" expander** listing the exact
attempts it was computed from, each a link to that node. A claim the learner
cannot audit is a claim the product should not make.

---

## 8. UI information architecture

### 8.1 Verdict on the current screen

| current element | verdict |
|---|---|
| overall progress % | **keep the position, change the number** — one gauge doing two jobs (§5.2 D3) |
| "By kind of understanding" | **keep the idea, fix the denominator** — restrict to assessed units, show untouched separately |
| "Where in the repository" | **demote.** Files are incidental; **areas** are the curriculum's own grouping and already exist in the rail. File view becomes a collapsed secondary |
| "Topics touched" | **keep as-is** — correctly presented as a low-commitment display, not a profile |
| the route | **keep, enrich** — add evidence markers per stop; the rail already handles areas/optional/remedial correctly |

### 8.2 Proposed structure

The brief's four-part structure is broadly right; one change: **insights must sit
below the profile and must be able to render nothing.**

```
HEADER (always)     Goal readiness 46%   ·   Journey 9/16   ·   [shorter | deeper]

MAP TAB
┌─ 1 · WHERE AM I ────────────────────────────────────────────────┐
│  readiness bar + journey bar side by side, each labelled        │
│  “7 of 15 core objectives demonstrated · 9 of 16 stops taken”   │
│  next stop · 3 skipped · 2 detours taken · 4 optional available │
└──────────────────────────────────────────────────────────────────┘
┌─ 2 · WHAT I'VE SHOWN ───────────────────────────────────────────┐
│  by kind of understanding  (assessed only, denominators shown)  │
│  by area                   (assessed only)                      │
│  ── not yet assessed: 7 units ──   [expand]                     │
└──────────────────────────────────────────────────────────────────┘
┌─ 3 · WHAT'S EMERGING ───────────────────────────────────────────┐
│  0–3 pattern cards, each with an evidence expander              │
│  empty state: “4 answers so far — not enough to see a pattern”  │
└──────────────────────────────────────────────────────────────────┘
┌─ 4 · THE ROUTE ─────────────────────────────────────────────────┐
│  today's list, plus per stop: attempts ●●, help given ◆,         │
│  “added after: <the claim that caused it>”                      │
└──────────────────────────────────────────────────────────────────┘

NODE DETAIL (drawer, from any stop)
  objective · attempts timeline with the system's response inline ·
  gaps (when enabled) · lesson versions (when re-taught)
```

### 8.3 Progressive disclosure rules

**[REC]**

1. Section 1 is the only section that renders unconditionally.
2. Section 2 renders once **≥ 2** units are assessed; below that it shows the
   assessed units as raw evidence instead of a profile.
3. Section 3 renders only when ≥ 1 L2 pattern fires; otherwise a one-line honest
   empty state that names the count. **Never a placeholder chart.**
4. Everything numeric shows its denominator inline. No bare counts.
5. Nothing above L0 is shown without an expander to its evidence.

### 8.4 Two wording rules

**[REC]** These prevent the exact over-claim the brief warns about:

- Statements are about **answers and units**, not about the learner. "Three flow
  answers fell short" ✅. "You struggle with flows" ❌ (that is L3, gated).
- Anything the learner asserted rather than demonstrated is visually distinct
  from anything they demonstrated. `user_override` must reach the wire for this
  to be possible (§4.5), and gap-model §18.16.2 makes the same demand for waived
  gaps.

---

## 9. Milestones

Ordered by dependency and value. M1 is deliberately small; M2 is the leverage
point; M3 delivers the vision's question 3; M4–M5 are architecture.

### M1 — Progress semantics (no new data)

**Unlocks:** a headline number that does not fall when the system helps; an
honest "read everything, answered nothing" state; one source of truth for every
progress display.

| area | change |
|---|---|
| backend | new pure module `backend/learning/progress.py`: `goal_readiness()`, `journey_progress()`, `assessed_coverage()`, `state_mix()`, `detours()`, `skipped()`, `optional_completed()`. Origin classification helper: explicit `lesson_brief["origin"]` when present, topological rule as fallback. Mutator and `/retry` start **writing** `origin` |
| persistence | **none.** `origin` is a `lesson_brief` key — the LD6 rule |
| API | `to_dict` gains a `progress` object (the metrics above) plus per-node `objective`, `user_override`, `origin`. `readiness` key **retained**, equal to goal readiness, so no client breaks |
| frontend | header shows two numbers; `MapView` reads `graph.progress` instead of recomputing; `Attempt` type gains `gap_kind` |
| migration | existing 62 graphs: no `origin` ⇒ topological fallback; no `priority` ⇒ all core. Both paths tested |
| tests | new `tests/test_progress.py`: the §5.5 table row by row; **the §5.3 invariant as an explicit test** ("no plan mutation lowers goal readiness"); pre-B3 degradation; empty graph; all-optional graph. Existing `test_adaptation.py::test_pruning_ahead_raises_readiness…` and the three readiness tests in `test_learning_graph.py` are re-pointed, not deleted |

**Risk:** the readiness number visibly changes for existing sessions. Acceptable
and desirable — but worth one line in the UI the first time it is seen.

### M2 — Learning-event instrumentation

**Unlocks:** metrics 13–18; every intervention-related pattern; the honest
version of "first-pass understanding".

| area | change |
|---|---|
| backend | **`backend/learning/history.py`** owns the vocabulary and the accessors. `/respond` writes `attempt["kind"]`, `attempt["graded"]` and `attempt["response"] = {action, text?, retaught?, superseded_lesson?, remediation_node_id?, declined_reason?}` via `graph.record_response`. Plan-shape changes go to `graph.journey_events` instead — see the ownership split below. `lesson_brief["remediates"]` was **already delivered by gap-model M5**, so M2 does not rebuild it |
| **ownership split (revised during the review, 2026-08-17)** | The original design put `pruned` on the attempt. It does not belong there: `scope.shorten/deepen` fire at `/session/{id}/scope`, **which takes no answer**, so half of all plan mutations have no attempt to hang from. Test applied: *could this have happened without a learner answering something?* A hint could not (attempt-scoped); a scope change routinely does (plan-scoped) |
| persistence | attempt envelope rides in `attempts_json` (no change). Plan history needs **one additive nullable column**, `sessions.journey_events_json` — the same justification `areas_json` was given: it belongs to the **session**, not to any one node, and the only other session payloads are owned by other producers. `SCHEMA_VERSION` unmoved. Still no table: nothing queries it |
| API | attempts on the wire gain `response`, `kind`, `graded`. Additive |
| frontend | attempt timeline in the node drawer shows what the system did after each answer; pattern inputs become available |
| migration | pre-M2 attempts have no `response` — every consumer treats absent as "unknown", **never as "no intervention"**. Enforced in code: `intervention_of` returns `None` (not `"none"`) and `instrumented()` is the only supported denominator, so a metric cannot include an un-instrumented attempt by omission. Measured over the real database: **40 stored attempts, 0 instrumented, and a load/save/reload leaves every one byte-identical** |
| tests | `tests/test_history.py`, 40 tests: unknown-vs-none in six forms; grading failures excluded from evidence but not from the progress measures; assessment vs verification kinds; each of the five actions round-tripping; declined reasons kept; superseded lessons kept; journey events with no attempt; store round trip; and two structural tests pinning the gap-model seam |

**[REC]** Also here: `lesson_brief["lesson_versions"]` on re-teach (§4.2), capped
at 3. It is three lines and it is the only thing that makes "how your
understanding evolved" showable.

### M3 — split into M3a.1 · M3a.2 · M3b (revised 2026-08-18)

The original single M3 was split for a reason that is structural rather than
stylistic: **its gap-derived half has no data on the wire.** `to_dict` carries no
gaps and will not until gap-model M9, so bundling would either block the profile
behind another phase or render analytics from data the frontend cannot see.

| step | scope | dependency |
|---|---|---|
| **M3a.1** ✅ | the understanding model, the profile, Needs Work / Worked Through / Set Aside, the Evidence Drawer | M1 + M2 + gap-model M7/M8 only |
| **M3a.2** | the three deterministic L2 pattern templates | none — deferred by choice, not by blocker |
| **M3b** | gap-derived insight (repeated gaps, foundational vs not, verification performance) | gap-model **M9** |

#### The state model — two dimensions, not five states

**Decided 2026-08-18 on evidence, after reviewing the final gap-model M8
semantics.** The alternative considered was a fifth mutually-exclusive
understanding state, *deliberately set aside*. It is wrong, and M8 makes the
reason observable rather than theoretical:

> A learner can waive a gap, later pass verification on it, and end with a node
> that is genuinely `understood` while `user_override` still records
> `waive_remaining`. **A single variable would have to report either
> "demonstrated" or "waived", and would be wrong about the other.**

So understanding and disposition are orthogonal:

| dimension | values | changed by |
|---|---|---|
| **understanding** — what the evidence demonstrates | `strength` · `recovered` · `unresolved` · `insufficient` | evidence only. Never by a decision about remediation |
| **disposition** — what the learner decided | `active` · `continued` · `waived` · `skipped` · `asserted` | explicit intent only. Never changes what was demonstrated |

**Needs Work is the conjunction**, and that is what satisfies the product rule
*preserve the truth about unresolved understanding without presenting it as an
active task*: a continued or waived node keeps `unresolved` — the truth survives
— and moves to a third **Set aside** band rather than being hidden or nagged
about.

#### What M3a.1 shipped

| area | change |
|---|---|
| backend | `backend/learning/understanding.py` — `classify`, `disposition_of`, `is_needs_work`, `is_set_aside`, `node_summary`, `profile`, `evidence`. Pure; `understanding_of` remains the single owner of state and is never re-derived |
| API | `understanding` on the session payload; `understanding` + `disposition` per node so every surface renders one classification; `GET /session/{id}/evidence/{node_id}` for the drawer (own endpoint — the timeline carries answer text and superseded lesson bodies) |
| persistence | **none.** Entirely derived |
| frontend | `MapView` gains the profile (by area, pips per unit) and the three bands; new `EvidenceDrawer`; **`weak_spot` rendering replaced in `RouteRail`, `SectionOverview`, `MapView` and the completion screen** — it is sticky, so it captioned mastered units "⚑ marked weak" forever |
| tests | `tests/test_understanding.py`, 36 tests |

**The defect it removes, measured:** across the 68 stored sessions there are **5
recovered nodes**, every one of which rendered as a current weakness. Verified in
the browser on `aimacode/aima-python` session `6844db10…` — goal readiness 100%,
five of five understood, three carrying `weak_spot=True`: **"marked weak" now
appears zero times.**

One of those five had `weak_spot=False` — a `partial → understood` recovery,
invisible to the sticky flag entirely. That is why the discriminator is the
attempt history rather than `weak_spot`.

#### Deferred, still

`state_matches_latest_answer` reports *that* gap-model M7 is holding a unit back
although its latest answer reached the objective; it cannot report *why* without
gaps on the wire. The drawer says so plainly rather than inventing a reason.
**OQ-5 remains open** and is revisited when M3a.2 introduces cards worth
reacting to.

### M3a.2 — deterministic patterns ✅ (2026-08-18)

`backend/learning/patterns.py`, three templates, thresholds as named constants.
**No prose in the backend**: templates return numbers and the sentence is
composed in `strings.ts`, so every phrasing decision — the part that can
over-claim — is reviewed in one file.

| template | fires when | evidence |
|---|---|---|
| `kind_contrast` | two canonical kinds each have **≥2 assessed** units; the leading kind has **≥2** units that did not land on the first answer; and its rate strictly exceeds the other's | the units that needed a second answer, each pointing at the first answer that fell short |
| `recurring_shortfall` | one `gap_kind` accounts for **≥3** shortfall attempts across **≥2 distinct objectives** | those exact attempts |
| `area_evidence` | an area has **≥2 assessed** units and **none** demonstrated | the assessed units in that area |

**Three definitional corrections, reported before implementing rather than made
silently.** None was caused by M9 — the templates read `classify`, `kind`,
`area_id`, `first_answer` and `attempts[].gap_kind`, none of which M9 touched.
They were imprecision in the definitions recorded in §7.4:

1. **`kind_contrast`'s "shortfall rate" was undefined**, and "≥3 total
   observations" was redundant (two denominators of ≥2 already implies ≥4). The
   recorded example — *"taken more attempts"* — settles the reading: it counts
   units that **did not land on the first answer**, so a `recovered` unit counts.
   Added an explicit **≥2 supporting units** floor so one rough unit cannot
   become a claim about a whole kind of understanding.
2. **`area_thin` implied an obligation the M8 disposition model forbids.**
   Renamed `area_evidence`; threshold unchanged. A waived unit still counts as
   not demonstrated — evidence truth survives the decision — but the sentence
   reports the aggregate ("0 of 3 assessed objectives demonstrated in *X*")
   and never "you still need to work on this". Where units were set aside, the
   card says so, so the count is not misread as outstanding work.
3. **`recurring_gap_kind` needed an explicit exclusion list.** Only the three
   misconception kinds count. `none`, `no_attempt` (engagement, not
   understanding) and absent (9 of the 40 stored attempts predate the field) are
   excluded.

**Not a shared-cause claim.** Three `wrong_model` shortfalls are three answers
of the same category. Whether they share one misconception needs cross-node
concept identity, which does not exist — so the wording says "fell short the
same way", never "share the same misconception".

**Tests:** `tests/test_patterns.py`, 31 — every template at its threshold and one
observation below it, single-objective repetition rejected, off-topic and
ungraded answers unable to manufacture anything, waived units truthful without
becoming tasks, unknown instrumentation inert, and every rendered pattern
resolving to a real attempt.

### M3b — gap-derived insight (not started)

**Unlocks:** vision questions 2 and 3 at L1/L2.

| area | change |
|---|---|
| backend | `backend/learning/insight.py` — the six L2 templates as pure functions returning `Pattern{id, template, statement, evidence: [{node_id, attempt_index}], confidence_level}`; thresholds from §7.2 as named constants |
| **gap surfaces** | **none.** Per OQ-4, gaps are collected from M1 onward but reach no UI until gap-model **M6** makes closure possible. If M6 has landed by the time M3 starts, the gap-derived templates (metric 20) come into scope; if it has not, M3 ships without them and says so |
| persistence | none for patterns (recomputed). **No dismissal persistence** — OQ-5 is deferred, and the interaction itself is undecided (§11) |
| API | `GET /session/{id}/insights` (or `insights` inside the session payload — one fetch is simpler, and the computation is microseconds over ≤ 30 nodes) |
| frontend | `MapView` restructured into the four sections of §8.2; profile denominators; pattern cards with evidence expanders; node detail drawer |
| migration | patterns simply do not fire on evidence-poor graphs; no data migration |
| tests | `tests/test_insight.py`: each template fires exactly at its threshold and not one observation below; off-topic attempts never contribute; a 4-answer session produces no L2 pattern; evidence lists resolve to real attempts |

### M4 — Objective identity and cross-node aggregation

**Unlocks:** metrics 19–20; "the same objective needed three attempts across two
sessions"; the first thing a team-lead view could report on.

| area | change |
|---|---|
| backend | promote `objective_key` from a gap field to a graph-level index: `objective_key(node)` on `LearningNode`, an `objectives()` aggregation over one graph, and — behind the same discipline as gaps — a cross-session query keyed `(repo_url, objective_key)`. **Concept-tag normalisation** (case/whitespace/singular) for display only |
| persistence | **first real schema decision of this plan.** A cross-session objective query wants a column, so this is where LD6's "no column unless we query by it" finally says yes: `nodes.objective_key TEXT` (additive, nullable, backfillable from `lesson_brief`) |
| API | objective-level rollup in the session payload |
| frontend | "objectives you can now make" list — arguably the most compelling single artifact in the product |
| dependency | **gap-model M6/M7**, because "demonstrated" should mean verified by then |
| tests | key stability across re-wording, backfill correctness, cross-session grouping on a fixture DB |

### M5 — Knowledge model (architectural; not scheduled)

Concept entities, `part_of` / `flows_into` / `depends_on` relationships,
learner-level (not session-level) profile. **[FACT]** Blocked on learner identity
(LQ7, deferred through Phase 3) and on having more than 40 lifetime attempts to
model. Recorded so the earlier milestones can be checked against it: nothing in
M1–M4 forecloses it, because objectives are a strictly coarser grouping than
concepts and a concept layer can be introduced *above* the objective index.

### Interleaving with gap-model

```
gap-model:   M1 ✅ M2 ✅ M3 ✅ ── M4 ── M5 ── M6 ── M7 ── M8 ── M9 ── M10
                                          │      │
learning-graph:  M1 ── M2 ──────────────  M3 ────┼──────────── M4
                  ▲                        ▲     ▲              ▲
       independent of gaps   gap panel only if  closure    needs verified
       (collection on in dev)   M6 has landed    exists         state
```

**[REC]** Learning-graph M1 and M2 are safe to run in parallel with gap-model
M4–M5 — they touch `progress` and `attempts[].response`; gap-model touches
`gaps[]` and `decide_all`. The one shared file is `/respond` in `api.py`, and the
one shared decision is the gauge relabel (gap-model M9): **do it in
learning-graph M1** and record it there, so it happens once.

**Gap-collection dependency (OQ-4).** `CODEONBOARD_GAPS=1` is on in the
development environment from M1 onward, with the code default left at `0`.
Collection is therefore independent of every learning-graph milestone; only
*display* is gated, on gap-model **M6**.

---

## 10. Risks and misleading interpretations to avoid

| # | Risk | Guard |
|---|---|---|
| **R1** | **Over-claiming from single-digit evidence.** The measured ceiling is 8 answers/session | §7.2 thresholds; L3 disabled in this phase; denominators always visible |
| **R2** | **Off-topic pollution.** 25% of stored attempts are `off-topic` and mean nothing | excluded from every understanding metric by construction; reported separately as engagement |
| **R3** | **Grading-failure partials** scored as half-understanding (D5) | `attempt.graded` in M2; until then, the limitation is stated in the doc and the code comment, as today |
| **R4** | **`weak_spot` presented as current weakness.** It is sticky by design ([graph.py:92-95](../../../backend/learning/graph.py)) and survives recovery | split the display: "needed a second pass" vs "still open". Never render sticky history as present state |
| **R5** | **Free-form concept tags treated as a taxonomy.** `auth` ≠ `authentication` to this system | profile aggregates use the canonical `kind` only; free-form stays "topics touched" |
| **R6** | **Planned vs remedial prerequisites conflated.** This defect already shipped once and made a planned graph read as a sequence of failures ([graph.py:21-38](../../../backend/learning/graph.py)) | explicit `origin`, topological fallback, and a test that a fully-planned B3 graph reports **zero** detours |
| **R7** | **Gap-dependent UI with zero gap data.** 0 gaps existed across 62 sessions when this was written; collection starts with OQ-4 | every gap surface degrades to absent, not to "0 gaps found" — which would read as "you have no misconceptions" |
| **R7b** | **Showing un-closable gaps.** Until gap-model M6 a gap can only ever be `open`, so any list of them grows and never shrinks — "here are 6 things you got wrong, with no way to resolve any of them" | OQ-4: collect from M1, display nothing until M6. The gate is a milestone, not a judgement call |
| **R7c** | **Assuming the gap flag is inert.** It also rewrites the scalar `gap_kind`, which selects the intervention (§2.4) | recorded in §2.4 and §11 OQ-4; anyone reading a flag-on session's adaptation history must know the diagnosis path differed |
| **R8** | **Two sources of truth for progress.** Frontend recomputes today | metrics move to `progress.py`; `MapView` stops computing anything but layout |
| **R9** | **Asserted vs demonstrated understanding blurred.** `user_override` sets `understood` directly ([graph.py:239](../../../backend/learning/graph.py)) | expose `user_override`; render it distinctly; gap-model §18.16.2 makes the same demand and this is the same fix |
| **R10** | **A number that moves for invisible reasons.** The single biggest trust risk | §5.3 invariant, tested; every legitimate fall is accompanied by a stated cause in the UI |
| **R11** | **Scope creep into a knowledge graph.** The brief explicitly warns against assuming one is needed | M5 is unscheduled and gated on learner identity |

---

## 11. Product decisions — **decided 2026-08-17**

Eight of the nine are resolved. **OQ-5 remains open by explicit choice** and is
restated as an open question below, not as a decision.

| # | Question | Decision | Status |
|---|---|---|---|
| **OQ-1** | One headline number or two? | **Two** — Goal Readiness and Journey Progress, as separate measures | ✅ decided |
| **OQ-2** | Does a remedial warm-up move the progress bar? | **No.** Completing a warm-up does not raise Goal Readiness; remedial detours are represented separately | ✅ decided |
| **OQ-3** | May Goal Readiness fall? | **Yes — on evidence only.** It may decrease when new evidence about the learner's understanding justifies it, and **never** because the system mutated or expanded the plan | ✅ decided |
| **OQ-4** | `CODEONBOARD_GAPS` | **Enable now in the development environment only; code default stays `0`.** Collect the data; expose no gap in the Learning Graph or UI until gap-model **M6** provides verification and closure | ✅ decided |
| **OQ-5** | Pattern-card interaction | **No learner action in V1** — no dismiss, no "doesn't apply", no "not useful". Revisit when L3 interpretations arrive | ✅ decided 2026-08-18 |
| **OQ-6** | `weak_spot` presentation | **Distinguish recovered historical difficulty from currently unresolved weakness. Do not destroy the historical flag** | ✅ decided |
| **OQ-7** | Map as automatic default view | **No.** Opening the map stays learner-initiated; no stop-count trigger | ✅ decided |
| **OQ-8** | Cross-session aggregation | **No.** The Learning Graph and understanding profile stay session-scoped; multiple sessions on one repository remain independent journeys | ✅ decided |
| **OQ-9** | Assessment / team-lead export | **Out of scope for V1**, but metrics stay server-side so it can be added later without redesigning the learning model | ✅ decided |

### OQ-4 in full — what was decided and what it implies

**Decision.** `CODEONBOARD_GAPS=1` in the development environment
(`run-dev.bat`, local `.env`). `flags.gaps_enabled()` keeps its `0` default, so
the shipped default, the test suite's default path, and every stored session
written so far are unchanged.

> **Enabling the flag changes runtime adaptation behaviour. It is not
> data-collection-only.**
>
> `_record_gaps` overwrites the scalar `gap_kind` with the dominant kind of the
> gaps found in that answer, and that scalar selects the intervention through
> `adaptation.decide()` — hint, re-teach, prerequisite insertion or follow-up —
> and is carried into the Mutator's `Diagnosis`. A flag-on session can therefore
> receive a *different* intervention than the same session flag-off. The measured
> direction is an improvement (`gap_kind` 47–48/48 against a baseline of 45;
> `missing_prerequisite` 4/6 → 6/6), but the behaviour is different, and any
> later analysis comparing flag-on and flag-off sessions must account for it.
> See §2.4 for the three call sites.

**What made this safe to do now:** gap-model M3 is complete and measured at zero
duplicates, which was the one substantive objection; blocking (M7) does not
exist, so no learner can be stranded by an open gap; and persistence never reads
the flag, so the decision is reversible.

**What is still incomplete, and what it costs:** gaps cannot be closed until M6,
so stored gap lists grow monotonically. That is why **display is gated on M6**
(R7b) — the data is research-grade from today, learner-facing only later.

### OQ-5 — decided 2026-08-18: no learner action in V1

**Decision.** M3a.2 pattern cards carry **no dismiss, no "this doesn't apply",
no "not useful"** control. The learner can inspect the evidence behind a
pattern; there is nothing else to do with it.

**Why.** These are deterministic, evidence-backed *observations*, not
diagnoses — "3 of 4 flow objectives needed a second answer" is a count the
learner can audit. Offering a rebuttal would imply the card is an opinion,
which is the over-claiming the whole hierarchy exists to prevent. It would
also cost a persistence column to answer a question we cannot yet inform.

**When to revisit.** With **L3 interpretations or learner-trait statements** —
where the system genuinely infers rather than counts, and disagreement becomes
meaningful. Recorded there rather than closed for good.

---

## 12. Recommended first milestone

> **Ship M1 — the progress model — and nothing else.**

**Authorised 2026-08-17** on the strength of OQ-1, OQ-2 and OQ-3, which are the
three decisions M1 needs. OQ-4 does not gate it: enabling gap collection in the
development environment is a configuration change made alongside M1, not part of
it.

**Why this is the smallest coherent unit.** It changes one thing the learner sees
(the number) and fixes the one defect that makes the current number actively
misleading: **verified, executed, 2026-08-17 — inserting a remedial prerequisite
drops readiness from 50% to 33%.** A progress gauge that falls when the system
decides to help is worse than no gauge.

**Why nothing in it gets thrown away.**

- `progress.py` is a pure module in the established style — it is the same object
  M3's insights read from and the same object a future report would read from.
- `origin` on `lesson_brief` is a key in a payload that already exists, is already
  sanctioned by §18.11, and is needed by every later milestone.
- The `to_dict` additions (`objective`, `user_override`, `origin`, `progress`) are
  additive and were going to be needed regardless.
- The §5.3 invariant test outlives every formula change.
- No schema version moves; no column is added; the 62 stored sessions load
  unchanged.

**What it deliberately does not do:** no new persistence, no pattern detection, no
LLM, no MapView restructure beyond reading the new numbers, no gap surface.

**Definition of done.** The §5.5 table holds row by row as tests; a fully-planned
B3 graph reports zero detours; a pre-B3 graph produces a defined number; the
header reads e.g. `Goal readiness 46% · Journey 9/16`; and `readiness` on the wire
still exists and still equals goal readiness.
