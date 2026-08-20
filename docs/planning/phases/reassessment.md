# Re-assessing an objective

**Status: proposal. Nothing here is implemented.** It exists because S0 found a dead
end, S6 confirmed it, and the honest message now shipping in the verdict card
(`checkClearedNotCredited`) describes the dead end rather than removing it. The
decision this asks for is not "should the message be nicer" but "should a stop the
learner has answered short of ever become creditable again".

---

## 1. The dead end, stated exactly

Goal readiness is binary per stop and has no partial credit
(`progress.goal_readiness`, Model A′):

```
goal_readiness   = demonstrated required stops / all required stops
is_demonstrated  = classify(node) in (STRENGTH, RECOVERED)
classify         = UNRESOLVED unless understanding_of(node) == "understood"
understanding_of = the stored state, demoted to `partial` while any blocking gap
                   is unverified — and returned UNCHANGED when none is
```

Follow the last line. A stop whose latest assessment was `failed` takes the first
branch of `understanding_of` the moment its blocking gaps are all verified — or
immediately, if it never had any — and that branch returns **the stored value**.
`failed`. Forever.

So the stop contributes **zero to goal readiness, permanently, with nothing the
learner can do about it.** Not "a low score": no score, no route.

And the vocabulary for the outcome that is unreachable already exists.
`understanding.RECOVERED` is defined as *"fell short, then got there"* and
`is_demonstrated` counts it in full, with the comment *"the measure is what the
learner can demonstrate NOW, not whether they managed it on the first attempt."*
The system has a name and a full-credit rule for recovery, and no mechanism that can
produce one.

### Why re-answering is not the answer — and the back door that already exists

The only thing that writes a new assessment is answering the stop's own question.
After a wrong answer the reveal has been shown, so re-asking it tests recall — which
is precisely why §18.7 removed "Try again", and why `feedbackActions` returns `check`
instead of `answerAgain` wherever a gap is named.

**But the retry is reachable anyway, by navigating.** `revealed` is
`Boolean(result) || attempts.length > 0`, and a revisit has no `result` — so
`lessonPhase` returns `STUDY`, the composer comes back, and the explanation is open
above it. S6's J7 measured exactly this: reloading a graded stop showed phase STUDY
with one composer. Leave a stop and return to it and you may answer it again, with
the answer visible.

So the position today is not "no route". It is worse than that in one specific way:
**the action row forbids the retry and the navigation permits it.** The design
decided that re-asking after the reveal is a memory test and removed the button; the
walk then hands the same thing back to any learner who happens to click away and
back, and only to them. A rule that holds for the learner who reads the interface and
not for the one who wanders is not a rule.

That is the strongest argument for this proposal, and it does not depend on the
counts below. Either re-answering after the reveal is acceptable — in which case the
button should come back and §18.7 was wrong — or it is not, in which case the back
door is a hole and something else has to produce the assessment. What is not
defensible is both at once.

**The surfaces split has already changed this, and in the right direction.**
Measured on a stop answered twice: Understanding shows phase `STUDY`, one composer,
and **no explanation** — the reveal is on Lesson, one deliberate click away, along
with the `Rewritten` notice. Under `next` the same revisit put the composer directly
below the explanation, so the answer was on screen while the question was being
answered. Now re-answering with the explanation in view takes a decision rather than
a scroll.

That weakens §18.7's concern for `surfaces` specifically without removing it, and it
is a reason to decide the question now rather than inherit whichever behaviour falls
out of the layout.

### How big it is, measured

Across the 804 stored nodes in `data/sessions.db`, 746 were never assessed and 29
are credited. Of the **29 that were assessed and are not credited**:

| | |
|---|---|
| offered a new attempt in the action row — `answerAgain` is live | 12 |
| creditable by verifying an open gap — stored `understood`, demoted by M7 | 2 |
| **offered nothing that leads to credit** | **15** |

"Offered nothing" is the accurate phrase, not "no route": every one of the fifteen
can still be re-answered by navigating away and back, per the back door above. What
they are not offered is any *stated* way forward.

Of the fifteen:

- **7 are `off-topic` answers.** The Grader deliberately records no grasp signal
  either way for these (`agents/grader/agent.py`), so the stop reads `not_started`
  while carrying an attempt. Real, and a separate question from this one — already
  listed in the S6 evidence as its own open item.
- **8 answered short of the objective with no invitation to retry** — 5 `partial`,
  3 `confused`. These are the case this document is about: the learner engaged, fell
  short, read the explanation, and the stop offers `Next stop →` or a warm-up and
  nothing that could credit it.

The eight matter more than the count suggests, because of what is *not* among them:
**none has an open blocking gap.** Gap verification — the mechanism the shipped
message in `917d0ec` points at — is irrelevant to all eight. Whatever the Grader
saw, it named no misconception, so there is nothing for a check to target and nothing
for a warm-up to unblock.

A note on why `check` is not a route even where gaps do exist: verifying a gap
removes M7's demotion, it does not write an assessment. A stop stored `partial` with
its gaps verified returns `partial` from `understanding_of` and stays uncredited. The
two nodes in the second row above are creditable only because their stored state is
already `understood` — verification lets the stored value through rather than
producing a new one.

---

## 2. Options

### A · Let a verification upgrade the state

When a verification closes every blocking gap, lift `failed`/`partial` to
`understood`.

**Reject.** It collapses the M6/M7 separation the design states in as many words —
`verification.py`: *"It does not touch `classification` or `understanding_state`. A
verification answer is evidence about specific false beliefs, not a re-assessment of
the objective."* A gap is narrower than an objective; closing one is not making the
claim. This is loss point 5 with the sign flipped, and it would also do nothing for
all eight of the stops below, none of which has a gap to close.

### B · Re-assessment: a fresh question about the same objective

A new **assessment** prompt for the same objective, in a different scenario and a
different form, graded by the Grader as an assessment — so `classification` moves,
`understanding_of` updates, and `RECOVERED` becomes reachable.

Every part already exists:

| need | what does it today |
|---|---|
| generate a prompt from an objective | `teaching.agent` — that is what a lesson's `prompt` is |
| generate a *fresh* one, deliberately not the original | `teaching_verify.verify` does exactly this, scoped to a gap |
| pick a different question shape | `_FORM_BY_KIND` already has seven forms |
| grade it as an assessment | `run_grader`, unchanged |
| name the outcome | `understanding.RECOVERED`, unchanged |

**Recommend.** It is the mechanism the vocabulary was written for.

### C · `failed` decays to `partial` once its cause is verified

Narrow the first branch of `understanding_of`: when the stored state is `failed` and
every blocking gap is `verified`, return `partial` instead of `failed`.

Honest on its own terms — the specific thing that failed is demonstrably closed, so
`failed` is stale — and it costs nothing but a condition. But `partial` earns no
readiness, so it fixes the **label** and not the **measure**, and it helps only the
three-node case. Worth shipping beside B; not worth shipping instead of it.

### D · Nothing, and keep the message

Legitimate, and it is what ships today. The cost is that a required stop can be
permanently uncreditable, which makes the product's centrepiece measure describable
as strict *and* unfair in the same breath.

---

## 3. What B needs decided

These are the questions I should not answer alone.

**When is it offered?** Only in the dead end, or wherever an objective is unmet?
The narrow reading — unmet objective, no *open* blocking gaps, budget remaining —
keeps it from becoming the "Try again" §18.7 deleted. The wide reading makes it a
general second chance, which is a different product.

**How many times?** A cap is needed or the measure degrades from mastery to
persistence. `VERIFICATION_ATTEMPT_CAP` is 2 per gap and `REMEDIATION_ROUND_CAP` is
4 per node; re-assessment is neither remediation nor gap verification, so it
probably wants its own counter rather than borrowing one whose meaning it would
blur. **2 per node** is the proposal.

**Does the reveal leak the answer?** This is the real risk and it deserves the
sharpest version of itself: the explanation has already explained the objective, and
a second question about that objective is closer to the thing it explained than a
gap-scoped question is. The mitigation is that the *form* must differ — a stop first
asked as `predict-then-reveal` re-asked as `critique` or `locate` demands applying
the claim rather than restating it, and those forms are already specified to be
answerable only from the code. Whether that is enough is a judgement, and it is
falsifiable: if re-assessed stops pass at a much higher rate than first attempts,
the question is testing recall.

**Waived gaps: in or out?** A waived gap keeps a node off `understood` by design
(*"waiving buys that the system stops asking"*), so re-assessment could not credit
such a node even if offered. Out, on that reading — but it means a learner who
waived has closed a door they may not have known was a door.

**Does a re-assessment overwrite the history or append to it?** Append, on the M2
pattern. `classify` reads `evidence[:-1]` to decide `RECOVERED` versus `STRENGTH`,
so the earlier failure must survive or every recovery would read as a first-time
success — which would make `RECOVERED` unreachable a second way.

---

## 4. Shape, if B is approved

Smallest version that is honest:

```
POST /session/{id}/reassess     → a fresh assessment prompt for the current stop's
                                  objective, in a form the stop has not used
POST .../respond {kind:"reassessment"}
                                → graded by the Grader as an ASSESSMENT
```

- `GapState` gains `reassessments: int`, capped at 2, incremented when a prompt is
  issued rather than when it is answered — an unanswered question has still been
  spent, exactly as `pending_verification` is.
- The form is chosen by our code from the forms the stop has already used, never by
  the model. Same rule as `_FORM_BY_KIND`: which shape a question takes is a
  decision we are willing to state and test.
- The action appears in `feedbackActions` in one place — the row where the objective
  is unmet, nothing is open to check, and budget remains. That row currently returns
  `{primary: "next"}`, which is the dead end.
- `understanding_of` is **untouched**. That is the point: a re-assessment produces a
  real assessment, and the existing derivation does the rest.

Gate: a stop that failed, was re-assessed, and passed reports `RECOVERED` and moves
goal readiness — and the same stop re-assessed twice without passing reports the cap
and stops offering.

---

## 5. Risks

**R1 · It becomes a retry.** The whole reason §18.7 removed "Try again". Mitigated
by the narrow offer condition and the form change; falsified by pass-rate
comparison.

**R2 · The measure becomes persistence.** Mitigated by the cap. Note that
`RECOVERED` counting in full is a deliberate existing decision, not something this
introduces.

**R3 · Cost.** One extra Haiku call per re-assessment, bounded by the cap. Within
the $0.10/run target.

**R4 · It is more machinery for a case that is rare.** Eight nodes across every
session ever recorded — fifteen if the `off-topic` seven are folded in, which they
should not be without deciding that question on its own terms. The counter-argument
is that the eight sit in exactly the sessions where a learner engaged and fell short,
which is the population the product exists for; and that 746 of 804 nodes are
unassessed says more about how little the journeys have been walked than about how
rare falling short is.

---

## 6. Recommendation

**B, capped at 2, offered only in the dead end, with C alongside it** — because C is
two lines and makes `failed` stop being a permanent verdict on a node whose cause is
closed, which is worth having whether or not B ships.

**And close the back door either way.** Whichever of A–D is chosen, the revisit
composer needs a decision, because it currently makes the choice for us: today a
learner who navigates away and back can re-answer with the explanation on screen,
which is the thing §18.7 removed a button to prevent. Three coherent positions, and
any of them beats the present one:

1. It is fine — restore `answerAgain` to the action row and record that §18.7's
   concern was overstated.
2. It is not fine — a revisit shows the stop read-only until something re-assesses
   it, which is B.
3. It is fine but should be *counted* — a revisit answer is recorded as evidence of
   a different weight, which needs the evidence model to gain a notion of weight it
   does not have.

This is the smallest thing in the document and the only part that is a live
inconsistency rather than a missing feature.

If none of it ships, the message from `917d0ec` should be widened: it speaks only on
the check path, and **not one** of the eight routeless stops has a gap, so not one of
them will ever reach it. The honest minimum is that the same sentence appears
wherever an objective is unmet and nothing on offer can change that — which is a
one-condition change, and does not need this proposal decided first.
