# Gap model — multi-gap remediation and verification

**Phase status: M1 done 2026-08-16; M2–M4 done 2026-08-17. Detection (M1–M3) is
complete and the policy that reads it (M4) is written; M5 wires that policy into
the agents that actually remediate.**

| step | state |
|---|---|
| **M1** gap model + persistence, write-only | ✅ **done** — `backend/learning/gaps.py`, `flags.py`, additive `gaps_json` column, 20 tests. All 61 stored sessions load and round-trip byte-identical; 833 tests pass; no observable product behaviour change |
| **M2** Grader emits a gap list | ✅ **done, gate met.** `GapOut`, `GraderOutput.gaps`, derived scalar `gap_kind`, the §18.5 arbitration order as pure functions in `gaps.py`, a flag-gated prompt addendum, 31 tests (864 total). **Multi-gap detection validated live**: 5–6 of 48 cases carry 2–3 independent false claims — the AC1 shape on real sessions. Gate: classification **47/48, 48/48, 48/48**; `gap_kind` **47, 47, 48** against a baseline of 45. Evidence: [`evidence/m2-grader-gate/`](evidence/m2-grader-gate/README.md) |
| **M3** Gap identity across re-grades | ✅ **done, measured.** Open gaps are supplied with their ids; `GapOut.refers_to` names one or says `new`; an id outside the supplied set is discarded whole rather than guessed at. 15 tests (879 total). §3.2's required measurement, over 18 grades on 6 real nodes ([`evidence/m3-gap-identity/`](evidence/m3-gap-identity/README.md)): **29 matched, 1 `new`, 0 hand-judged duplicates, 0 invented ids** — and **0 duplicates on the verbatim identity floor**. The refusal to fuzzy-match costs nothing measurable |
| **M4** Adaptation policy → plan | ✅ **done.** `decide_all(classification, gaps) → Plan` in `backend/learning/adaptation.py`: §18.5 precedence picks the response, one mutation but many corrections, active set ≤ 3, overflow collapses to a single full re-teach. Pure, mutates nothing, **no API cost**. 43 tests (922 total). The compatibility invariant is asserted against the live `_ACTION_BY_GAP` table, parametrised over **every** (classification, kind) pair, so the two functions cannot drift; the `off-topic` + named-gap rule is re-asserted at the new entry point |
| M5 – M10 | not started |

**One narrowing against the build order, recorded because it is a design
choice.** M4 was sketched as `Plan{actions, active_set}`; what shipped is
`Plan{action, targets, active_set, deferred, collapsed}` — **one** action per
graded answer. §18.5 permits one structural mutation, and every remaining action
is a piece of writing the learner reads; issuing two at once is not twice the
teaching but two lessons competing for the same attention, which is what the
precedence order exists to prevent. The plural moved to `targets`, which is
where "one mutation, many corrections" actually lives.

**Two things the gate produced beyond a pass, both of which bind later steps.**

*The `no_attempt` / `missing_prerequisite` boundary was a real defect, and it is
fixed.* The two categories were described so that *"I can't answer, I don't know
what a decorator is"* matched **both verbatim**, and the baseline scored 4/6
there — i.e. production got it wrong a third of the time, costing prerequisite
insertion its clearest trigger. The discriminator is now stated (**does the
learner name the foundation they lack?**), which is exactly what separates a
hint from a warm-up. **6/6 in every run since, flag-on and flag-off.** This edits
`_SYSTEM_PROMPT`, so it changes the flag-off production path: it is a standalone
defect fix in the F1–F4 sense, gated on its own, not an M2 change.

*Classification agreement is noisy at ±2, and the baseline was a single run.*
Across sixteen runs it lands 46–48, mean ≈ 47, with different cases failing each
time. **M2's gate criterion — "no worse than the recorded 48/48" — was written
without that information.** Later steps that re-run this gate should read 47/48
as parity, not regression, and should not treat a 48 as evidence of improvement.

The *design* this builds lives in
[`learning-engine.md` §18](learning-engine.md#18-outstanding-gaps--multi-gap-remediation-and-verification),
and the *policy* it implements is
[§18.16](learning-engine.md#1816-gap-policy--lq6lq10-revision-3-approved-2026-08-16),
approved 2026-08-16. That document is the completed Learning Engine phase and
stays the source of truth for the design; this one owns the build.

The problem in one line: **one answer can contain several independent
misconceptions, the Grader already detects them all, and everything downstream
can carry only one.** See §18.1 for the traced loss points.

---
## 1. The sequencing constraint that sets the order

> **Blocking must land AFTER closure exists.**

If `understanding_state` starts requiring verified gaps before verification is
built, a flag-on session accumulates blocking gaps with no mechanism to close
them, and no node can ever reach `understood`. So detection, policy, remediation
and verification all land *before* the derived state that gives gaps their teeth.

Everything ships behind **`CODEONBOARD_GAPS=0`** (default off), the pattern
`CODEONBOARD_CURRICULUM` established: the two models coexist rather than one
replacing the other mid-phase.

## 2. Build order

| # | Step | Invariant after this step | What could regress |
|---|---|---|---|
| **M1** ✅ | **Gap model + persistence, write-only.** `Gap` dataclass, `LearningNode.gaps`, additive nullable `gaps_json` column via the existing swallow-the-error `ALTER TABLE` idiom. `SCHEMA_VERSION` does not move. Nothing reads it | All 813 tests pass **unchanged**. No observable behaviour change. A graph saved and reloaded is identical | Store round-trip; the 61 existing sessions must still load |
| **M2** ✅ | **Grader emits a gap list.** `GraderOutput.gaps: list[GapOut]` (`kind`, `claim`, `objective_part`, `foundational`). Scalar `classification` kept; scalar `gap_kind` **derived** from the highest-precedence gap. Ids minted by our code on persist, never by the model | `/respond`'s `gap_kind` equals what the single-gap Grader produced. Gaps are recorded but **inert** — nothing blocks, nothing is remediated per-gap | **Classification calibration.** A prompt change can shift the verdict distribution. Gate: re-run the 48-case evaluation and require classification agreement ≥ the recorded 48/48 |
| **M3** ✅ | **Gap identity across re-grades** (§19.3.2). Re-grade mode shows open gaps *with their ids*; the model references an id or declares `new`. Code validates membership | A gap id never changes. A `verified` gap never reopens under a new id. An id the model invents is rejected and the gap stays as it was | Duplicate gaps if the model over-reports `new`. Bounded by the queue cap; measured, not assumed |
| **M4** ✅ | **Adaptation policy → plan.** `decide_all(classification, gaps) → Plan{actions, active_set}`. §18.5 precedence, active set ≤ 3, collapse to one re-teach above 3 | With exactly one gap, `decide_all` produces exactly what `decide` produces today — asserted directly against the existing table | The B5 adaptation tests; the `off-topic` + named-gap rule must survive intact |
| **M5** | **Remediation becomes gap-scoped.** Re-teach receives *every* open gap of its kind and is instructed in the plural; the Mutator's `Diagnosis` (step G) gains the specific `Gap` it must unblock, recorded as `lesson_brief["remediates"]` | With one gap, both produce the same shape as today. The warm-up decline path stays reachable | Re-teach quality with 3 gaps at once — a prompt property no test asserts (LR3-class risk) |
| **M6** | **Verification.** `teaching.verify(node, gaps, source) → VerificationPrompt` stored on `node.pending_verification`, **separate from `cached_lesson`**, carrying **no `reveal`**. Grader verification mode returns per-gap `resolved` + any new gaps. Per-gap and per-node counters persisted | A gap moves to `verified` **only** here. Silence about a gap leaves it `open`. Caps stop the system proposing without closing anything | Cost: this adds calls per gap. The Baseline-1 cost record must be re-measured (§19.7) |
| **M7** | **Derived `understanding_state`.** `understood` ⟺ latest assessment reaches the objective **and** every blocking gap is `verified`. **Blocking takes effect here — after M6 made closure possible** | On any graph with `gaps == []`, every derived value **equals the stored value**. This is the compatibility gate, run over all 61 stored sessions | `prune_ahead` (reads `understood`), `resume_point` (reads `understood`), `readiness()` (reads state), `mark_understanding` (currently assigns) |
| **M8** | **Learner intents + resume + completion.** `continue`, `waive`, `waive_remaining`; `/advance` records `continue` when leaving a node with open blocking gaps; `resume_point()` per §18.16.3; `is_complete()`; `mark_understood` migration | A refresh **never** records `continue`. Resume returns to unfinished remediation. `is_complete()` is reachable by walking the journey | `resume_point` stranding a learner; `/advance` recording `continue` on nodes without blocking gaps |
| **M9** | **API + frontend.** `/respond` returns `gaps`; `POST /session/{id}/verify`; waive endpoints; the gauge relabelled *Verified understanding*; completion screen shows both measures with waived gaps **named** | Existing response keys unchanged; an un-updated client keeps working | The B6 route rail; the stop counter; the completion screen's `understood` count drops legitimately and needs its "N waived" context |
| **M10** | **Acceptance + live E2E** (§19.5). Both named acceptance cases, on real repositories | AC1 and AC2 both observed live, not simulated | — |

M1–M3 are detection; M4–M6 are response; M7 gives it teeth; M8–M9 are agency and
surface. Each step is independently revertable.

## 3. Area specifications

### 3..1 Grader schema and prompts

```python
class GapOut(BaseModel):          # what the model returns
    kind: GapKind                 # existing five-value enum, unchanged
    claim: str                    # the misconception in one sentence
    objective_part: str           # the clause it violates
    foundational: bool            # observed, not decisive

class GraderOutput(BaseModel):
    classification: Classification
    rationale: str
    gaps: list[GapOut] = []       # defaulted — an omission is not a parse failure
    gap_kind: GapKind = "none"    # RETAINED, derived from gaps for compatibility
```

Prompt changes: report **every** distinct misconception, not the dominant one;
two misconceptions about different claims are two gaps even when they share a
`kind`; `no_attempt` and `off-topic` report **no** gaps. `blocking` is never
asked for — it is derived from `kind` in code.

`gap_kind` stays on the wire so `/respond` consumers and every pre-M2 test keep
working; it is the highest-precedence gap's kind, which is exactly what the
single-gap Grader used to return.

### 3..2 Gap identity and matching across re-grades

Identity is **ours**. The model never mints an id.

- **First detection:** each `GapOut` gets a fresh id at persist time.
- **Any later grade of the same node:** the open gaps are supplied *with their
  ids*, and the model must, for each gap it reports, either **reference one of
  those ids** or explicitly declare it **new**.
- **Validation:** a referenced id not in the supplied set is rejected — the gap
  it claimed to be is left untouched, and the report is dropped rather than
  guessed at.
- **No fuzzy matching.** Deliberately no text-similarity merge: a heuristic that
  silently merges two distinct misconceptions is worse than a duplicate. The
  known failure mode is the model over-reporting `new`, producing a duplicate;
  it is bounded by the queue cap and must be **measured** during M3, not assumed
  away.

**What M3 must record** (measurement only — no fuzzy merging is added now):

| metric | how |
|---|---|
| reported gaps matching an existing id | counted from the validated re-grade output |
| reported gaps declared `new` | same |
| `new` gaps that are in fact **semantic duplicates** of an open gap | judged by hand over a focused validation set, not by a heuristic |

The third number is the one that decides whether the explicit-id strategy works.
It cannot be computed automatically without the similarity matching this design
deliberately refuses, so it is a **hand-judged count over a fixed, recorded set**
— the same standard as the Grader evaluation's authored expectations. If it is
near zero the strategy holds; if it is not, that is evidence for a *separate*
design decision, not a licence to add fuzzy merging quietly.

**Recorded 2026-08-17** — `scripts/gap_identity_probe.py`, 18 grades over 6 real
nodes, [`evidence/m3-gap-identity/`](evidence/m3-gap-identity/README.md):
**29 matched · 1 `new` · 0 hand-judged duplicates · 0 invented ids.** The probe
grades each node three times against one accumulating gap list — the answer, the
*same answer again*, then a full paraphrase. The verbatim pass is the identity
floor and needs no judgement: any `new` there is a certain duplicate, and there
were none. **The strategy holds; fuzzy matching stays refused.**

### 3..3 Persistence and migration

One additive nullable `gaps_json` column on `nodes`; `SCHEMA_VERSION` unchanged.
Counters (`verification_attempts` per gap, `remediation_rounds` per node) live
inside the same payload — nothing queries them. `pending_verification` rides in
the existing node JSON, not `cached_lesson_json`, whose owner overwrites it.

`mark_understood` migration (§18.16.2): honoured unchanged on nodes with **no**
gap records; not offered on gap-bearing nodes; read as `waive_remaining` if found
in stored data; removed once no live session predates the gap model.

### 3..4 Derived `understanding_state`

One function owns it, as `objective()` and `readiness()` already do. The
compatibility gate is exact: **for every stored graph with no gaps, the derived
value equals the stored value.** `mark_understanding` stops assigning and becomes
a recorder of the latest assessment; the state is computed from that plus the gap
list.

`readiness()` is **untouched** — node-weighted, `partial` = 0.5. Explicitly *not*
gap-weighted: the number of detected gaps is not a reliable measure of how much of
an objective is understood, and adopting it as a weight would need separate
evidence and design (decision recorded 2026-08-16).

### 3..5 Round caps and their persistence

`gap.verification_attempts` (cap 2) and `node.remediation_rounds` (cap 4), both
persisted. Reaching a cap sets nothing on the gap — it only removes the gap from
the active set, so the system stops proposing. A deliberate return to the node
resets both. **A cap never writes `verified` and never writes `waived`.**

### 3..6 `continue`, `waive`, `waive_remaining`, resume, completion

All three are `user_override` actions — the existing explicit-intent channel.
`continue` is recorded by `/advance` **only** when the node being left has open
blocking gaps, and is withdrawn by a new attempt on that node. `resume_point()`
follows §18.16.3 exactly; `is_complete()` is "every non-optional node settled",
where settled is `understood` or an explicit override — **never plain `visited`**.

### 3..7 API and frontend

`/respond` gains `gaps` (open list) alongside every existing key.
`POST /session/{id}/verify` returns a fresh verification prompt; its answer posts
to `/respond` with `kind="verification"`. Waive endpoints are per-gap and
per-node. The header gauge is relabelled **Verified understanding** and
`is_complete()` drives the completion screen, which reports both measures and
names each waived gap with an offer to verify it now.

### 3..8 Feature-flag compatibility (`CODEONBOARD_GAPS`)

**The flag gates behaviour. It never gates storage.** That single rule makes the
whole contract true by construction, and it is what M1 implements: the
persistence path does not read the flag at all.

| scenario | required behaviour |
|---|---|
| written flag-on, loaded flag-off | gap data **loads and round-trips intact**. It is inert for current-session logic — nothing blocks, nothing is remediated per-gap — but nothing is deleted, truncated, or rewritten |
| written flag-off, loaded flag-on | the node simply has no gaps yet; the session behaves as a fresh gap-model session from that point |
| re-enabling the flag | restores **exactly** the gap state that was persisted, byte-for-byte through the JSON round-trip |
| pre-gap sessions (no `gaps_json`) | load unchanged under either setting, with `gaps == []` |
| saving flag-off a graph that carries gaps | gaps are written back **unchanged** — a flag-off save must never be a silent data loss |

The last row is the trap worth naming: a flag-off session that loads a gap-bearing
graph, modifies something unrelated, and saves would destroy the gap data if
persistence were conditional. It is not, and tests 21–24 in [§5](#5-tests-and-live-validation) pin it.


## 4. Acceptance cases — carried from the original defect

These are the reason the phase exists. Both are **live** criteria; neither may be
satisfied by a unit test alone.

**AC1 — two misconceptions, one resolved, the other survives.**
The original trace (`Node.expand` / `solution()`, AIMA `search.py`): one answer
containing (A) child metadata is filled in later by the search algorithm, and
(B) `solution()` returns states *and* actions.

Required, in order:
1. Both detected and persisted as **two distinct gaps** — distinct ids, distinct
   `claim` text — even though both are `wrong_model`.
2. Remediation addresses one of them.
3. A **fresh** verification question closes that one: it becomes `verified`.
4. **B remains `open`, blocking, and visible by name.** It must not be silently
   dropped, must not be inferred resolved from an answer that never mentions it,
   and must not be closed by the round cap.
5. The node is **not** `understood`, and says why.

**AC2 — verification is a new question, not the original.**
After remediation has revealed the correct reasoning, the learner is tested with
a question targeting the diagnosed weakness through a *different application*.
Required: the verification prompt is **not** the original prompt (asserted
mechanically), and a learner still holding the misconception cannot answer it
correctly (judged live — the one property no assertion can carry).

## 5. Tests and live validation

**Deterministic, no API key** — the ten from §18.12 plus:

11. Two `wrong_model` gaps with different claims stay two gaps through save →
    load → re-grade.
12. A referenced gap id outside the supplied set is rejected and changes nothing.
13. A cap being reached writes neither `verified` nor `waived`.
14. `waive_remaining` waives every open blocking gap and the node stays `partial`.
15. `/advance` records `continue` **only** when open blocking gaps exist.
16. A refresh (`GET /session/{id}`) records no override of any kind.
17. A new attempt withdraws a prior `continue`.
18. `is_complete()` is true with waived gaps present, and `readiness()` is
    simultaneously below 1.0 — the §18.16.3 target state, asserted directly.
19. Every stored graph with no gaps derives exactly its stored
    `understanding_state` (run over all 61 sessions).
20. `mark_understood` on a gap-bearing node behaves as `waive_remaining`.
21. A graph saved with gaps under the flag **on**, loaded with it **off**, still
    carries every gap with identical fields and statuses.
22. That flag-off graph, modified elsewhere and **saved again flag-off**, still
    carries its gaps unchanged — the silent-data-loss guard.
23. Re-enabling the flag restores exactly the persisted gap state.
24. The persistence path never reads `CODEONBOARD_GAPS` (asserted structurally,
    so the contract cannot rot).

**Live** — AC1 and AC2 end to end on `psf/requests` and `aimacode/aima-python`,
plus the M2 calibration gate: the 48-case Grader evaluation re-run, requiring
classification agreement no worse than the recorded 48/48.

## 6. What could regress, collected

| Risk | Where | Guard |
|---|---|---|
| Grader calibration shifts | M2 prompt change | Re-run the 48-case evaluation as a gate |
| Stored sessions derive a different state | M7 | Golden test over all 61 stored graphs |
| `prune_ahead` becomes rarer | M7 | Expected and correct — `understood` is genuinely harder. Stated so it is not read as a bug |
| `resume_point` strands a learner | M8 | Fallback to `current_node_id` is unchanged |
| `continue` recorded too eagerly | M8 | Fires only with open blocking gaps; test 15 |
| Route rail / stop counter | M9 | The two defects B6 found both lived here; a browser pass is required, not optional |
| Duplicate gaps from over-reported `new` | M3 | Measured during M3; bounded by the queue cap |
| **B3 guard-band calibration** | — | **Unaffected.** Nothing here touches curriculum proposal or selection |

## 7. Cost — this phase increases it

Verification adds model calls per gap, on top of remediation. Baseline 1 is
frozen and **will not survive this phase unchanged**; it must be re-measured after
M6, per session path, before any optimisation decision. Recorded here so the
increase is a known consequence rather than a surprise in the cost record.
Optimisation remains deferred.
