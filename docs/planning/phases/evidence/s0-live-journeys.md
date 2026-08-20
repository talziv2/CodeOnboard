# S0 — the seven canonical journeys, run live

Run against the real backend and the real model path: backend on `:8000` with
`CODEONBOARD_GAPS=1`, UI on `:3100` with `NEXT_PUBLIC_CODEONBOARD_UI=next`.

The `:3100` rig is `.ui-audit-fe`. Before trusting anything below, `diff -rq` was
run over `app/`, `components/` and `lib/` against `frontend/`: **byte-identical**.
Every observation is against the shipping code.

Two sessions: `a3234f41…` (auth goal, 13 stops, driven through J1–J5 and J7) and
`8c5a4027…` (request-lifecycle goal, generated fresh for J6).

**This file records what the `next` path does. It is deliberately separate from
`ui-surfaces.md`: none of it is an argument for or against the two-surface model.**

---

## Results

| | Journey | Result |
|---|---|---|
| J1 | answer → `understood` | structural PASS, **two real bugs** |
| J2 | answer → `confused`, gaps open | PASS |
| J3 | warm-up requested → inserted → returned | PASS, **one real bug** |
| J4 | verification → gap closed → resolved | PASS |
| J5 | scope shorter / deeper, re-teach | PASS |
| J6 | interview → review gate → generation → first lesson | PASS on every step; the long POST fails **through the rig's proxy only** |
| J7 | resume | PASS |

Negative checks, both per journey: no text below its WCAG threshold in the lesson
UI (0 failures in every state measured, alpha and ancestor opacity folded in), and
no superseded block left expanded.

---

## The four defects

### 1. The key point applies the misconception frame to a correct answer

`frontend/lib/feedbackSummary.ts:40`. `keyPoint()` composes
`"<verdict> — you're working from: <gap claim>"` from the leading open gap
**whatever the verdict is**. Observed twice, live:

```
verdict    understood
key point  "Understood — you're working from: requests only supports two
            built-in auth classes and does not provide an extension point
            for custom schemes."
```

The learner's answer had just said the opposite, correctly, and was graded
`understood` for saying so. The sentence asserts they believe the thing they just
refuted. The second sighting was on a different stop with a non-blocking gap, so
this is the general case and not one bad gap.

The ladder is right that a named gap beats a bare verdict word. It is wrong that
the frame survives a verdict which contradicts it.

### 2. `understood` offers no route to the gap it leaves open

`frontend/lib/feedbackActions.ts:100`:

```ts
// The objective is met: this is the one row where moving on is primary.
if (classification === "understood") {
  return { primary: "next" };
}
```

The comment's premise is false on live data. Same stop as above, on the wire:

```
classification (grading response)   understood
understanding_state (session)       partial
priority                            required
gaps                                1, blocking, open
action row offered                  Next stop →      ← the only action
```

`understanding_of()` demotes a stored `understood` to `partial` while a blocking
gap is unverified — that is M7 working exactly as designed. So the node is
`required`, reported `partial`, and the one mechanism that can close a gap
(`check` → verification, the only caller of `Gap.mark_verified`) **is not
offered**. The learner is told "Understood", shown `1 unresolved`, and given a
single button that walks away from it.

This also breaks the module's own documented invariant — *"moving on is never
primary unless the objective is met"* — because it reads `classification`, which
is the latest assessment, where the invariant means the derived state. The
320-case sweep asserted the invariant against the same wrong premise, so it
passed.

### 3. A declined warm-up is still offered

`FeedbackCardNext.tsx:106` derives `warmUpDeclined` from the **grading**
response:

```ts
warmUpDeclined:
  result.adaptation?.kind === "prerequisite" && result.mutation?.kind !== "prerequisite",
```

A decline that happens on the **retry** call is therefore invisible. Observed
live: the Mutator answered `no_useful_prerequisite`, `LessonPanel.handleRetry`
set the error line and returned without recording anything, and
`Build me a warm-up` stayed on offer. Everything else in the retry-declined
contract held — the verdict stayed up, the outcome was named, the routes forward
stayed reachable — so this is the one row of §3 that the live run falsified.

### 4. `remediation_rounds` is never incremented

`backend/learning/gaps.py:291`, read at `backend/learning/adaptation.py:195`:

```python
if remediation_rounds >= REMEDIATION_ROUND_CAP:
```

The field is declared, serialized, deserialized and read by the cap. Nothing
anywhere increments it. Verified live: a warm-up was inserted on stop 12 and the
node's `remediation_rounds` stayed `0`.

The cap cannot fire. It is also why an earlier sweep of 759 stored nodes found
"0 remediation rounds" and concluded warm-up insertion had never been exercised —
the counter was measuring nothing, not the absence of warm-ups.

---

## J3, which had never run before

The insertion path had no precedent anywhere in the stored data. It took two
attempts to reach: the first candidate stop was declined
(`no_useful_prerequisite` — every candidate a peer, not a foundation), which is
a legitimate answer rather than a failure. On stop 12 it fired:

```
"Build me a warm-up"  →  Mutator inserts a prerequisite
rail                     new stop before stop 12, labelled "added after confusion"
lands on                 the warm-up, STUDY, composer present
answered correctly    →  "Understood", one action, key point = verdict word
                         (ladder level 3, no gaps — the fallback is reachable)
"Next stop →"         →  back to stop 12, STUDY, gap still open, "2 answers"
```

The return is not surprising navigation: the learner asked for the warm-up, and
coming back to the stop that caused it is the only sensible destination.

---

## J5, in full

**Scope, both directions, both declined by the backend** — and both reported,
in the menu where the control is:

```
POST /scope {"direction":"shorter"}  →  {"applied": false, "changed": 0}
menu shows                              "Everything left is required"
POST /scope {"direction":"deeper"}   →  {"applied": false, "changed": 0}
menu shows                              "Nothing further in this journey"
```

**Re-teach**, observed rendered rather than inferred. Three nodes were re-taught
live, each keeping its `superseded_lesson`. The consequence line appeared as the
third child of the feedback card:

```
key point     "Not yet — you're working from: Basic auth is handled by urllib3
               before the adapter sees the request…"
rationale     the Grader's own words, not collapsed
consequence   "This stop has been rewritten to answer that."
actions       Check my understanding | Move on anyway | Build me a warm-up
disclosures   Before you answer · This path crosses several places 6 ·
              Still unresolved 3 · Your answers (1)      — all five closed
contrast      0 failures
```

That is §3a's answer working on live data: one primary artifact, one consequence
line where five conditional lines used to be able to stack, and the trace path
collapsed even in the phase that produced it.

Automatic pruning (`adaptation.prune_ahead`) did not fire in any run — it needs a
demonstrated area with recommended units left ahead of it, and neither session
reached that. Its line is the same tested branch of `consequenceLine`.

---

## J6, and what actually failed

Every step passed on its own terms:

- **Interview** — 6 questions, options and free text, `Back` and per-question
  `Change` both live. Radio selection, `Continue` gating, and the draft-retention
  fix all behaved.
- **Review gate** — all six answers listed with a `Change` each, `Let's start`
  and `Back`, and nothing started until confirmed. Exactly the P2b contract.
- **Generation** — per-stage ticks, the live investigation counter
  ("Reading src/requests/api.py · 7 lookups so far"), and elapsed time.
- **Fresh session** — `moderate` in the header, derived from `code_depth:
  working` and not invented; both progress measures (`0/11 (0%)` goal readiness ·
  `0/14` journey); five rail sections that match the stated goal; first lesson
  rendered with one primary, the setup open, the trace path collapsed.

**What failed was the rig, not the product.** `POST /session/start` through
`.ui-audit-fe`'s `/__api` rewrite died at ~55s:

```
Failed to proxy http://localhost:8000/session/start [Error: socket hang up] ECONNRESET
```

The backend logged nothing, because nothing completed. The identical payload
posted straight to `:8000`:

```
http:200      real 2m38.602s      session 8c5a4027…, graph returned
```

The shipping app sets no `NEXT_PUBLIC_API_URL` and so fetches `:8000` from the
browser with no proxy in the path. The `/__api` rewrite exists only in the audit
rig. **Not a product defect** — but worth knowing that one request is held open
for two and a half minutes, and that anything placed in front of it needs a
timeout above that.

Incidentally this retires an earlier recorded finding: `t.starting.elapsed`'s
"usually two to four minutes" is **accurate**. Measured: 2m38s.

The briefing screen was not observed, because reaching the session by URL skips
it. Unverified rather than broken.

---

## J7

Reload on a graded stop. Same stop, same counters (`3 unresolved`, `1 answer`),
history intact with the verdict inside the collapsed attempt row, and the gap list
rendered **open** with all three `Set aside` controls — which is the view model's
STUDY rule, not a leak. The composer returns; the verdict card does not, because
`result` is component state and the record of it lives in history. Correct.

---

## Lower-severity, recorded not fixed

- **The loading label lands on the wrong button.** `FeedbackCardNext.tsx:111`
  maps `next`, `moveOn` and `startWarmUp` to `t.lesson.loadingShort` whenever
  `loading` is true, so while a warm-up is being built the *secondary* reads
  "Loading…" and the tertiary still reads "Build me a warm-up". Observed live.
- **A warm-up's transition prose names the previous stop, not the confusion.**
  The inserted warm-up opened "Now that you know how to use Session safely with
  context managers, you need to understand…" on a stop inserted because of a
  misconception about the auth extension point.
- **`off-topic` leaves `understanding_state = not_started` with an attempt
  recorded.** Deliberate (`agents/grader/agent.py:581` — no grasp signal either
  way), but the brief then shows `1 answer` on a node the system reports as never
  started. Six nodes in one session.
- **After a successful verification the node keeps its assessment state.** J4's
  node closed its gap (`verified`) and stayed `failed`, because verification is
  evidence about beliefs and not a re-assessment (`verification.py:20`). The UI
  says "Cleared" and drops the counter; nothing says the node is still not
  credited toward readiness.
- **The Shiki syntax palette.** 242 token spans between 3.46 and 4.40 against
  their background, all `class="tok"` inside the source pane, none in the lesson
  UI. This is the already-deferred issue, unchanged.

---

## Four false alarms, recorded so they are not re-found

All four were measurement error, and each was chased to the source before being
dismissed:

1. "The gaps disclosure vanishes on resume" — it renders **open**, without a
   `<details>` wrapper, per the STUDY rule. I was counting `<details>`.
2. "A declined scope change is silent" — the note renders inside the menu; my
   selector had picked the innermost button row and filtered the note out.
3. "Clicking a radio option selects the wrong one" — reading `aria-checked`
   synchronously after `.click()` sees the DOM before React flushes.
4. "0 remediation rounds across 759 nodes proves J3 never ran" — the counter is
   never incremented (defect 4), so it proved nothing either way.

---

# The fixes

Made in isolation, before any surfaces work. Nothing here anticipates the two-surface
model: every change is one the single-canvas `next` path needed anyway.

A regression test per defect, each confirmed to fail without its fix. Frontend
**217 passing** (was 207 before S0), backend **+11**.

## What the four turned into

Two of them were bigger than the symptom, in the same direction: the UI was
disagreeing with a backend that was already right.

### 1. The key point no longer frames a correct answer as a misconception

`keyPoint()`'s ladder gained one rule: **the verdict vetoes the frame.** On
`understood` with gaps open it says what is true instead —
`"Understood — 3 things you said earlier still need checking"` — which is also
what the primary action now offers, so the sentence and the button agree.

Level 1 (the Grader's own headline) still outranks the veto: that sentence is
about *this* answer. Level 2's frame is retained for every verdict that does not
contradict it, verified live — a wrong answer on the same stop still reads
`"Not yet — you're working from: …"`.

### 2. `understood` with a gap open now offers the only thing that can close it

`backend/learning/adaptation.py` already said this, in a comment nobody had
contradicted:

> `understood` earns no response … An answer that reaches the objective while
> leaving a blocking gap open is not re-taught — it is **VERIFIED (M6)**, which is
> a different act with a different producer.

So the fix is the UI agreeing with the policy, not new policy. Three parts:

- The `understood` row consults `openGapCount`. With something open it returns
  `check` primary, `next` secondary — and deliberately **no warm-up**, because
  this answer reached the objective and stepping back would be the system
  disagreeing with its own grade.
- **A check is offered on the strength of open gaps, not of `canAnswerAgain`.**
  That flag means "the system invited another attempt at the same question" — true
  only for `hint`, `followup` and `reteach`, and false for `understood`. Gating
  verification on it made the correct action unreachable exactly when it was
  correct. This is F98, reached from the `next` path.
- The module's stated invariant was rewritten, because it was the actual root
  cause: *"the objective is met"* is not `classification === "understood"`. The
  320-case sweep had asserted the invariant against the same wrong quantity as
  the code, which is why it passed while the bug shipped.

**The sweep then earned its keep again.** With `checkAvailable` able to be false
for its own reasons, a `partial` answer with two gaps open fell through to the
"nothing named" row and made `next` primary again — the exact defect the sweep
caught the first time. That row's condition now says what its comment always
claimed (`openGapCount === 0`).

### 3. A declined warm-up is recorded where the decline happens

`warmUpDeclined` was inferred from the *grading* response, which cannot see a
refusal that happens on the *retry* call. The panel now records it — node-scoped
and kept for the node's lifetime, because both refusals
(`no_useful_prerequisite`, `prerequisite_exists`) are facts about the stop's
surroundings, not about the attempt that asked. It also feeds `canRequestWarmUp`
and `warmUpAvailable`, so no branch can offer it.

The check path was the other half: it read `warmUpAvailable && !warmUpInserted`
and never consulted `warmUpDeclined` at all. The sweep's "never offered after a
decline" test had `!i.isCheck` in its filter, which is how that survived.

### 4. `remediation_rounds` — and the two other things wrong with the cap

Incrementing the counter was not enough to make `REMEDIATION_ROUND_CAP` fire.
Three separate defects, all invisible while the counter sat at zero:

1. **Nothing incremented it.** Now charged on `/respond` for a remediation that
   *landed*, and on `/retry` for a warm-up that was actually spliced. A round is
   an **applied remediation of any kind**, not only a structural one: `decide_all`
   picks the action from gap precedence, so a node whose leading gap earns
   `followup` every time could be remediated forever and never reach a cap that
   only counted warm-ups. Declines and failures cost nothing — that would spend
   the learner's budget on the system's own failures.
2. **`/respond` never passed it to `decide_all`.** `/verify` always did; the path
   that *spends* the budget never read it, so the cap was unreachable from the
   only place that could reach it.
3. **A capped gap fell out of the plan entirely.** `eligible = []` ran before
   `blocking` was computed, so a gap deferred by the node cap appeared in neither
   `active` nor `deferred` — contradicting the comment three lines below it
   (*"A capped gap belongs here rather than nowhere, so the count the learner is
   shown stays truthful"*). Unreachable until the counter began incrementing,
   which is how it survived. Caught by the test asserting the cap's documented
   behaviour rather than its code.

`nothing_to_verify`, `source_unavailable`, `verification_unavailable` and
`no_pending_verification` were all unmapped in `errorText` and would have
rendered as raw slugs. `nothing_to_verify` became materially easier to reach the
moment the cap could fire, so naming them is part of this fix rather than an
aside.

## And a fifth, found by the re-validation itself

Re-validating fixes 1–3 walked straight into it: request a check on one stop, move
to another, and Submit does nothing. Forever.

- **`verification` was never cleared on a node change.** `lessonPhase` reads it,
  so the *next* stop opened in `VERIFY` carrying the previous stop's question. Its
  Submit posted `kind: "verification"` for a node with nothing pending and the
  backend answered `409 no_pending_verification`.
- **`VerificationBlock` took no `error` prop at all**, while `AnswerComposer`
  always had one — so that 409, and every other way a check can fail, was
  *silent*. A dead button with no message.

Both fixed. Clearing the stale question is the honest minimum, not the whole
answer: the server still holds `pending_verification`, and carrying it back when
the learner returns needs it on the wire (F101, R9).

This is the one finding I would not have got from the journeys as written. It
needs two stops and an abandoned check — a sequence no single journey walks.

## Live re-validation

Backend restarted on the new code; the `:3100` rig re-synced and confirmed
byte-identical to `frontend/` again.

**Defects 1 + 2**, on stop 13 — three open blocking gaps, answered correctly:

```
key point     "Understood — 3 things you said earlier still need checking"
actions       Check my understanding  |  Next stop →
brief         3 unresolved · 2 answers
wire          understanding_state: partial · priority: required · 3 blocking gaps
readiness     0.0909, unchanged — the node is not credited
check clicked a real verification question was generated, no error
```

One story, across all four surfaces named in the request. Before the fix the same
state read *"Understood — you're working from: <a misconception>"* over a single
`Next stop →`, while readiness silently declined to move.

**Defect 4**, stop 12: `remediation_rounds` **0 → 1** on a re-taught wrong answer,
and **still 1** after the declined retry.

**Defect 3**, same stop: `Build me a warm-up` → declined → the action row becomes
`Check my understanding | Move on anyway`. The offer is gone, the verdict stayed
up, the outcome is named, both routes forward remain reachable.

Contrast in the post-decline FEEDBACK state: **0 failures**.

The message is still the generic *"We couldn't build a warm-up for this one"*
where `prerequisite_exists` was the actual reason. `t.lesson.warmUpExists` exists
and `/retry` does not return a reason. That is F52/F99 and stays recorded.

## Two things left alone, deliberately

- **The loading label lands on the wrong button.** Still true, still recorded. It
  is in the same file as fix 3 and I left it, so the diff stays auditable.
- **`tests/test_mentor_dossier.py` fails 14 tests on a full run.** Pre-existing:
  reproduced with every one of my backend changes stashed, so **red at HEAD**.
  Every test file that imports `backend.api` triggers it; each of the 14 passes
  alone. An import-order isolation defect that has nothing to do with the
  redesign, and its own task.

## Relationship to `grounding-repair.md`

Three of these were already catalogued there, against the pre-redesign frontend:
**F100** (the counter) is defect 4, **F98** (verification unreachable where it is
correct) is the root of defect 2, and **F99/F52** (a warm-up offered where refusal
is guaranteed) is the neighbour of defect 3. R9 bundles them behind R0 and R3.

What is fixed here is the `next` path's share of them — `feedbackActions`,
`feedbackSummary` and `FeedbackCardNext` did not exist when that document was
written, and its testing section still records "there is no frontend test
harness", which the L track has since made untrue. R9's remaining scope — the
wire additions (`pending_verification`, `has_remediation`, `/retry` reasons,
`gap_id` on `/verify`), D12/D14, and F102 — is untouched.
