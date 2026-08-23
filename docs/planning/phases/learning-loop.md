# The learner loop: lesson → question → feedback → remediation → retry → state

**Status: complete. M0, M1, the decision gate (§3), M2 and M3 all shipped.**

An improvement pass over the interaction the product is actually made of. It
exists because a manual E2E run hit a dead end that turned out to be four
separate defects wearing one coat, and because fixing them independently would
have meant redesigning them again once re-assessment landed.

The question this pass has to be able to answer, for every node:

> What exactly are we trying to teach? What evidence would demonstrate that the
> learner understands it? What do we do when they don't? And what evidence later
> allows us to confidently say they recovered?

---

## 1 · The governing invariant

**A learner decision is never evidence of understanding.**

The two dimensions in `learning/understanding.py` already say this — what the
evidence demonstrates, and what the learner decided — and every defect M0 fixed
was a place where the second leaked into the first, or where the second was not
recorded at all so the first had to carry a meaning it does not have.

Corollaries, all now enforced:

- Moving on records a **disposition** and never touches `understanding_state`.
- Asserting understanding records a **disposition** and never touches
  `understanding_state`.
- Viewing remediation is not evidence and must never close a gap (M3).
- `Gap.mark_verified` keeps exactly one producer: a fresh verification answer.

---

## 2 · Milestones

| | | status |
|---|---|---|
| **M0** | Correctness — no new concepts | **done** |
| **M1** | Traceability — the question on the attempt | **done** |
| **M2** | One retry action, and re-assessment | **done** |
| **M3** | The re-teach loop — guide to changed material | **done** |
| **—** | **Objective-model decision gate** | **decided** — anchored re-assessment |
| **M4** | *(merged into M2 — the gate chose no schema change)* | — |
| **M5** | Re-assessment | **done** — shipped inside M2 |

### M0 · Correctness — shipped

Three defects, all found by manual E2E, all verified by execution before and
after. Measured across the 90 stored sessions in `data/sessions.db`: 63 nodes
carry an assessment, 34 are assessed with the objective unmet, and **"Move on
anyway" recorded a decision on 7 of those 34 before this change and on all 34
after** — so 79% of real shortfalls recorded nothing at all.

- **B · `continue_past` fired only where open blocking gaps existed.** An
  `off-topic` answer opens no gaps by policy; a `confused` or `partial` answer
  naming no false statement opens none either. So on the commonest failure the
  system sees, "Move on anyway" recorded nothing, the stop never became
  `is_settled`, and `is_complete()` was **permanently unreachable for the whole
  session** — silently. Now: unmet objective **and** at least one assessment.
  The old gap clause is kept as a second trigger so the widening is
  non-regressive by construction rather than by an argument about reachability.
- **C · the stop was invisible.** It classified `insufficient` with disposition
  `active` — the same dashed grey pin an unopened stop gets, and no caption. Now
  the pin reads three server-sent facts (`understanding`, `disposition`, the new
  `attempted`) through `lib/standing.ts`, with two shape channels carrying one
  bit each: the **dash** means "nothing has happened here", the **bar** means
  "the learner closed this". Neither depends on colour.
- **G · `mark_understood` wrote `understanding_state = "understood"`** on a
  gap-free node. §18.16.2 closed that door for gap-bearing nodes and left it open
  for exactly the population re-assessment is for. On an *assessed* node,
  measured: `classify` went `unresolved → strength` and goal readiness `0.0 →
  1.0`, on a button press. Now it records the assertion in the disposition
  channel only, and settlement comes from `SETTLING_OVERRIDES` instead of from a
  state write pretending to be evidence.

`mark_weak` deliberately still writes state: agreeing with a shortfall can only
lower the claim being made about the learner, so it is not the act the invariant
restricts, and its disposition stays `active`.

Tests: `tests/test_decision_is_not_evidence.py`, `frontend/lib/standing.test.ts`,
and the new block in `frontend/components/RouteRail.test.tsx`.

### M1 · Traceability — shipped

`record_attempt` gains `question` and `question_source`
(`lesson | reteach | verification | reassessment` — vocabulary in `history.py`).
Both are **omitted when unknown**, and the accessors return `None` rather than a
default: the same unknown-vs-absent rule `intervention_of` follows, and for the
same reason. Guessing "lesson" for a pre-M1 attempt would put a confident wrong
answer in the one record whose job is to say what actually happened.

Two orderings turned out to be load-bearing, and both are asserted:

- `/respond` snapshots the prompt **before** grading, because a `reteach` later
  in the same request replaces `cached_lesson`. Reading it after would file every
  re-taught answer against the question that *replaced* the one it answered — a
  record that is not merely missing but actively wrong.
- `_respond_to_verification` snapshots `pending_verification.question` **before**
  `grade_verification` clears it. The question stays spent — re-showing it would
  be the defect §18.7 removed — it is now merely also recorded.

`history.lesson_was_retaught` separates provenance from recency: ANY landed
re-teach, not the last answer's, since nothing ever puts the original lesson
back. The frontend's `materialIsNew` keeps the narrower recency question, which
is a different thing and must go stale on the next answer.

Surfaced in `AttemptHistory` and the evidence-drawer timeline, badged only for
the three non-original sources. **No surface substitutes the node's current
prompt for a missing one** — after a re-teach that is a different question, so
substituting would be a confident lie rather than an honest gap. Verified live
against real pre-M1 sessions: attempts render "You wrote" with no question block
and nothing invented.

Tests: `tests/test_question_traceability.py` (14).

### M2 · One retry action

One learner-facing action — *Ask me again* — with the mechanism chosen by the
backend from the learning state. The learner should not have to know whether
their answer contained a false statement.

#### The finding that rewrote this milestone

M2 was planned with four mechanisms, two of which reused the unit's own
`cached_lesson.prompt`. **Both are memory checks, and the code says so
explicitly.** Teaching's contract for `reveal` is *"The explanation — now you may
answer it"*, and `lessonView` opens it on `revealed = Boolean(result) ||
attempts.length > 0` — that is, **after any graded answer, including
`off-topic`**. So by the time a retry is offered, the answer to the unit's prompt
is on screen, one tab away.

A re-teach does not escape this. It regenerates the whole lesson, so its new
prompt arrives with a new `reveal` that answers it. The re-taught prompt is a
genuinely better question and it is shipped with its own answer.

So the rule this milestone actually needs is sharper than "don't re-ask":

> **The lesson's own prompt is answerable exactly once — before its reveal has
> ever been shown. Every later assessment comes from a freshly generated question
> that ships no answer.**

That is enforceable structurally rather than by a flag, because M1 records which
question each attempt answered. And it is what makes *recovery requires new
evidence* true rather than aspirational.

#### The dispatch that follows

Two mechanisms, both fresh, both shipping no answer:

| condition | mechanism | anchored to |
|---|---|---|
| open blocking gap with verification budget | `/verify` | the gap `claim` |
| objective unmet, no eligible gap, budget left | `/reassess` | the objective |
| otherwise | not offered, with the reason | — |

`/verify` already exists and already obeys the rule — *"There is no `reveal`, no
`expected_answer` and no `takeaway` — not omitted for brevity but excluded by
design"*. `/reassess` is the same act one level up.

**Consequence: M2 cannot ship without re-assessment.** A no-gap shortfall — which
is 27 of the 34 real unmet stops in `data/sessions.db` — has no other route. So
the decision gate moves ahead of M2 rather than after M3: it decides what a
re-assessment targets, and building the dispatch around a mechanism whose target
is undecided would mean building it twice.

Also in scope, and now expressible: **close the revisit back door.** The composer
for the unit's own prompt is offered only while no graded assessment exists on
the node. After that the prompt is spent, a revisit reads read-only, and the one
route to new evidence is the retry action.

Bug A is fixed by construction rather than by patching the row: `feedbackActions`
stops deriving the offer from `canAnswerAgain` / `checkAvailable` / `warmUpDeclined`
and renders what the backend computed.

### M2 — shipped

**Backend.** `backend/learning/retry.py` is the whole dispatch, pure and testable
without a key like every other module in `learning/`. `POST /reassess` +
`backend/agents/teaching/reassess.py` generate the objective-scoped question
against the four anchors §3 names. `GapState` gains `pending_reassessment` and a
`reassessments` counter capped at 2, spent on ISSUE. `retry` is on every reply
that reports state, and `/lesson` also carries `pending` so a reload restores an
outstanding question instead of costing the learner one they never answered.

**Frontend.** `feedbackActions` stopped deciding and started rendering:
`canAnswerAgain`, `checkAvailable` and the `openGapCount` reasoning are gone, and
`check` + `answerAgain` collapse into one `askAgain`. `SpentPrompt` replaces the
composer once the prompt is spent — the question stays on screen, plainly marked,
with the retry where the composer was. Where there is no retry the REASON is said,
because a control that is simply absent leaves the learner unable to tell "nothing
left to do" from "something is broken".

**A defect the census found, not the code review.** Running `offer()` over all 968
stored nodes showed a stop with no `cached_lesson` being offered a re-assessment —
a second question about material never shown once. Guarded, and the numbers then
cross-check exactly: 27 `reassess` + 7 `verify` = the 34 assessed-and-unmet stops
counted independently in M0.

| offer, over every stored node | |
|---|---|
| never taught | 697 |
| prompt still live (`answer`) | 178 |
| objective met | 59 |
| `reassess` | 27 |
| `verify` | 7 |

**Live, against real data and one real model call.** On a stop whose objective was
"narrate the complete journey of an authenticated API call … and identify what I
own versus what the library owns", originally asked as *"at which anchor does the
Authorization header get added … show the code line that proves it"*, `/reassess`
produced:

> Suppose a caller invokes `requests.get(url)` with no auth parameter, but the
> Session has `auth=('user','pass')` set. Walk through the code: does the
> Authorization header end up in the PreparedRequest handed to urllib3, and if so,
> explain which function adds it and when that happens relative to when urllib3
> receives the request.

Same claim, different application, no answer shipped, and it demands the ordering
and ownership the objective is about rather than a line citation. Reloading the
page restored it with exactly one composer, one Submit, and the retry correctly
withdrawn as `already_asked`.

Tests: `tests/test_retry_dispatch.py` (26),
`frontend/components/lesson/retryLoop.test.tsx` (12), and
`frontend/lib/feedbackActions.test.ts` rewritten against `RetryOffer`.


### M3 · The re-teach loop — shipped

**Exactly one outcome rewrites Lesson**: `reteach`, reachable only from a
`wrong_model` lead gap or from overflow collapse. A hint and a follow-up render
in the verdict card; a prerequisite is a different stop; the first graded answer
merely unlocks material that was always authored. So "remediation the learner
never sees" was precisely scoped, and so is the fix.

**Both signals had the wrong lifetime, in opposite directions.** The tab dot was
React state and died on reload — and a change forgotten on refresh is a change
the learner never saw. The `Rewritten` callout was derived from the last
attempt's `retaught` flag and never cleared at all, sitting there until the next
answer. One forgot too fast, one never forgot. `lib/materialSeen.ts` gives both
the same pair of facts: installed at T, last looked at S, in `localStorage` keyed
by node — mirroring `railSeenAt`, which had solved this already.

**"Have I looked at that tab" is the one fact the frontend owns**, and the
exception is stated rather than assumed: it is not a fact about understanding and
the server cannot observe it. Everything else still comes from the backend.

**Naming what changed, with no new field and no model call.** A re-teach
regenerates every field, so there is no diff to highlight — "mark the new
section" is not implementable as stated. What is available is the *reason*:
`response.gaps_addressed` has recorded the corrected gaps since gap-model M2, and
the claims were already on the wire; the two had simply never been joined.
Checked against real data: **all 13 re-taught stops in `data/sessions.db` can name
what changed**, none degrades to "something changed".

**Read, then answer — as weight, never a gate.** While rewritten material is
unread the primary action is *Read what changed* and the retry sits one place
down, enabled. The argument is sharper than tidiness: the fresh question is built
to be fatal to exactly the misconception the unread correction explains, so
sending the learner straight at it sets them up to fail something they were just
given the means to get right. Nothing is disabled and nothing is hidden — blocking
would be the system deciding they may not know something. And reading records
nothing about understanding: it cannot close a gap, move a state, or count as
evidence.

**Bug D, resolved by argument rather than by another signal.** The tab dot
conflated "the reveal unlocked" with "your material was rewritten". Both mean
*worth a look*, and `SurfaceTabs` argues a dot carries exactly one bit; a second
dot type would be more chrome for the same bit. The two are distinguished where
the learner arrives — the callout says which, and now says what it corrects.

Tests: `frontend/lib/materialSeen.test.ts` (14), the M3 block in
`feedbackActions.test.ts`, and two in `surfacesAwareness.test.tsx` through the
real panel and real tab bar.


### Found while checking the UI

**"The warm-up worked" was claimed where no warm-up existed.** Recovering on stop 2
of a healthy 16-stop aima-python graph announced *"You got this one after studying
'Identify the public entry points and return type' first"* — that was simply stop 1.

`LessonPanel` looked for **any** `prerequisite` edge into the node. The
objective-first planner emits one for every `depends_on`, so that graph had **29
prerequisite edges and zero warm-ups**, and the test matched the ordinary stop
before this one. The system invented a causal story about how the learner
recovered, and would have done so on essentially every recovery in every
objective-first graph.

Pre-existing, and M2 is what made it visible: before the retry existed, a gap-free
stop had almost no route back to `understood`, so the callout rarely fired. Making
recovery routine made the false claim routine.

`origin` is the authoritative answer and had been on the wire all along —
`api.ts` even documents *"planned for an ordinary stop; anything else is a
warm-up"*. Now `graph-layout.remedialUnlockFor`, with an ABSENT origin returning
null rather than falling back to the structural guess: the claim is an optional
flourish, and declining to make it beats making a false one.

Tests: six in `graph-layout.test.ts`, including a planned dependency and a warm-up
pointing at the same node.

---

## 3 · The objective-model decision gate — DECIDED

**Decision: neither atomic nodes nor `objective_parts`. Anchored re-assessment,
plus a recorded `probes` line.** Rationale and evidence below.

### The evidence

Measured over `data/sessions.db`: **968 unique objectives, 90 sessions, mean
journey 10.8 stops.**

**Objectives are compound, overwhelmingly.** Median 42 words (mean 45.6, p90 70,
max 131). 92% carry at least one compound marker; 56% carry two or more —
em-dash asides (54%), lists of three (61%), semicolons (28%), boundary negation
(26%), multiple sentences (14%).

**But the compounds are mostly internally DEPENDENT**, which is the finding that
decides it. Read directly from samples across every `kind`:

- *selection sets* — "BFS when all steps cost the same, UCS when they differ but
  you have no heuristic, A* when you can estimate remaining cost". The claim **is
  the choice**; knowing each alternative separately is not it.
- *contract + boundary* — "the state/action/path_cost fields are yours to
  inspect, **but** `expand()` and `child_node()` are internal machinery you do not
  call". The boundary is the claim.
- *mechanism + consequence* — "`memoize` caches `h` on the Node, **so** a stateful
  heuristic serves stale values". The consequence is only meaningful given the
  mechanism.

**Questions already under-cover their objectives.** Of four sampled
objective/question pairs on answered nodes: one covered fully, two covered part
of an enumerated claim (a two-failure-mode `risk` objective was asked about one
mode only), and one asked about a different subject entirely. Lexical overlap
between objective and prompt has a median of 0.17 — weak corroboration only,
since a good question is *supposed* to rephrase rather than echo, so the read
samples carry this point and the number does not.

### Why not atomic nodes

- It destroys the highest-value objectives. Selection sets, contract boundaries
  and mechanism→consequence pairs are exactly the `architecture`, `synthesis` and
  `risk` units the planner is instructed to prefer — *"prefer objectives that
  build judgement over objectives that build recall"*. Split, they build recall.
- **Atomicity is model-judged with no code check.** This codebase refuses that
  shape on principle — `depth`, curriculum size and gap `blocking` are all
  decided in code precisely because a model asked to self-assess makes the
  property unpredictable for no gain. "Is this one claim?" has no such check.
- At mean 10.8 stops today, a 2–3× split is a different product.

### Why not `objective_parts`

- **The one thing it uniquely buys is per-part accumulation, and accumulation is
  semantically WRONG for the compounds this curriculum actually contains.**
  Crediting "knows BFS" and "knows UCS" from two different answers is not the
  claim "can choose between them". For internally dependent compounds, assembling
  a pass from fragments credits precisely the thing that is not the knowledge.
- It costs **two model judgements where one suffices** — enumerate the parts, then
  judge coverage per part — and both are exactly as fallible as the single
  judgement it replaces.
- Two concrete costs are documented in the code it would touch: the planner is
  already overflowing its token budget on implementation-depth runs (the
  `understand` field was *removed* for that reason), and the Grader's output shape
  is what a 48-case calibration was measured against.
- The demonstration rule it implies — full part coverage — would sharply lower
  readiness given that questions under-cover today. More honest, but it fixes the
  *measurement* of an under-covering question rather than the question.

### What was chosen, and why it is enough

`/verify` already solves "same knowledge, different question" for gaps, with one
mechanism: **the thing under test is named, and the same name goes to both the
question generator and the grader.** It needs no decomposition of anything —
`Gap.claim` is the anchor, the generator is told the belief must be *fatal* to the
question, and the grader is asked per-id with silence defaulting to unresolved.

Re-assessment is that pattern one level up. The anchor is the objective, which is
already the Grader's marking standard and already the same for both questions. M1
supplied the input that was missing: **the previous question is now on record**,
so a retry can be told what not to repeat.

So a re-assessment question is generated against four things:

1. **the objective** — unchanged marking standard, so A and B are marked the same;
2. **the questions already asked** — must not repeat or paraphrase them;
3. **the recorded shortfall** — the previous answer and the Grader's rationale;
   the question must be one that a learner still holding that shortfall gets
   *wrong*, which is `/verify`'s own rule;
4. **the source** — grounded, or refused (§4.1.2).

And it ships **no `reveal` and no `expected_answer`**, which is what makes it
evidence rather than recall.

This is strictly stronger than the status quo and claims nothing it cannot
deliver. It does not promise "every part was covered"; it promises that the
second question is marked by the same standard, does not repeat the first, and
cannot be passed while still holding the recorded shortfall.

### The one thing borrowed from `objective_parts`

The generator returns a one-line **`probes`** — what this question was aimed at —
stored on the attempt beside `question`. It is *not* a decomposition asserted up
front; it is a record of what was aimed at, which makes coverage **auditable after
the fact**. If the data later shows objectives genuinely under-covered across
whole sequences, `probes` is the evidence that would justify parts — and it is
the same field a parts model would need anyway. Cost: one string.

### Deferred, and now evidenced

Sampling turned up an original question whose subject did not match its
objective at all (a "four vertical layers" objective asked about a base class
raising `NotImplementedError`). Teaching is already instructed that *"answering it
well must require the objective's claim, not a detail beside it"*, and nothing
checks it. That is a defect in the FIRST question, not in the retry, so it is out
of this pass — but it is the strongest available argument for a future coverage
check, and `probes` is what would measure it.


## 4 · The `next_step` architecture — arrived at, under a different name

Proposed as a deferred idea and largely delivered by M2/M3, which is the right
outcome: the constraint was that it must be a **pure function of the learning
state with no facts of its own**, and holding to that is what kept it small.

What shipped is `backend/learning/retry.py` — pure, no IO, no model calls, tested
without a key like every other module in `learning/`. It answers "what now" from
gaps and their budgets, `remediation_rounds`, `reassessments`, and which questions
have been answered. `feedbackActions` renders it; the four frontend flags it
replaced are gone.

The frontend keeps exactly one fact, and only because the server genuinely cannot
know it: **have I looked at Lesson since it changed** (`lib/materialSeen.ts`).
That is documented as an exception at both ends rather than left as drift.

What was NOT built is the ordered `next_step` *list* on the wire. It turned out to
be unnecessary: the ordering is a rendering decision — which of at most four
actions leads — and it depends on the one client-side fact. Putting the list on
the wire would have meant sending `materialUnread` to the server so it could send
the order back. So the server sends the *offer* and the client decides the
*weight*, which is the same separation stated more honestly.

The test that the constraint held: nothing in `retry.py` needed a fact that lived
nowhere else. The one time it wanted one — "has this stop ever been taught" — the
fact was already there (`cached_lesson`), and the census caught the missing guard.

---

## 5 · Deferred

- **A question that does not cover its objective.** Sampling for the decision gate
  turned up an original prompt whose subject did not match its objective at all
  (a "four vertical layers" objective asked about a base class raising
  `NotImplementedError`). Teaching is already instructed that answering well *"must
  require the objective's claim, not a detail beside it"*, and nothing checks it.
  A defect in the FIRST question, not in the retry — out of this pass, and the
  strongest argument for a future coverage check. `probes` is what would measure it.
- **`probes` has no reader.** Recorded on every re-assessment, deliberately unread,
  exactly as `objective_key` was before it. It exists so coverage across a sequence
  of questions becomes measurable after the fact — and so that the evidence for or
  against `objective_parts` can be gathered rather than argued.
- **`weak_spot`** is written, persisted and on the wire, and read by no UI decision
  since M3a. Vestigial; left alone in this pass because removing it is churn with
  test breakage and no correctness gain.
- **`REASSESSMENT_CAP = 2` is a guess.** It is the smallest number that is not one,
  and the reasoning is stated (without a cap the measure degrades from mastery to
  persistence). Whether two is right is an empirical question `probes` and the
  attempt record can now answer.
