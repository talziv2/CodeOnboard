# Two surfaces: Lesson and Understanding

> **Status: DESIGN, not implemented.** Supersedes `ui-direction.md` §13, which
> rejected tabs on 2026-08-19 *on current evidence* and recorded the triggers that
> would justify revisiting. One of those triggers has now fired.
> **Blocks:** `L5` must not remove the legacy renderer until this is resolved.
> **Preserves:** the whole of `L1`–`L4` except block placement.

---

## 1. Updated recommendation

**Adopt the two-surface model.** Not because the earlier analysis was careless, but
because it made one real error and because its own stated exit condition has been
met.

### The trigger fired

§13 listed three triggers. The third was:

> *Testing showing the single canvas still fails to separate reading from being
> examined, after F3b's surface work has landed.*

F3b landed, then L3's frame, then L4's phase model, disclosures and single-primary
rule. The experiment §13 asked for has been run — and it worked, measurably:

```
feedback canvas height      1565px -> 1127px    -28%
primary actions in the row       2 -> 1
non-content chrome                  14.7%       gate was <= 25%
blocks open around the verdict    5 -> 0        all three collapsed to disclosures
```

And it is still reported as too busy. That is exactly the evidence §13 said it was
waiting for. Continuing to cite §13 now would be citing a document that told us to
stop citing it under these conditions.

### The error in the original argument

§13's reason 4 said tabs "relocate accumulation rather than solving it", and that
"collapse is the mechanism". The first half is true. The second half framed collapse
and separation as **alternatives**, and they are not — they are orthogonal axes:

| | accumulation *within* a purpose | mixing *between* purposes |
|---|---|---|
| collapse | solves | does not touch |
| separation | does not touch | solves |

L4 is the proof: it removed the accumulation and left the mixing. Reading and being
examined still share one column, so the learner still holds both frames at once. The
correct conclusion is **both**, which is what this proposal is — and it is why the
disclosure model is not optional here but load-bearing.

### The reason that dissolved

§13's reason 2 was its strongest: the withheld reveal makes the two tabs
non-independent, because the reveal is lesson content whose *timing* is controlled by
answering, and a re-teach rewrites the setup, so "Lesson is not a stable place to
return to."

That objection assumed **Lesson is static teaching content**. The revised model
states the opposite: Lesson evolves in response to what the learner demonstrates. On
that reading, the reveal is not an awkward orphan straddling two tabs — it is the
*first and most ordinary instance* of the thing Lesson is for. Re-teaching, gap-driven
material and adaptive additions are the same mechanism at higher intensity.

Reframing Lesson as a living surface does not dodge reason 2; it removes its premise.
What survives from it is one real requirement, addressed in §5: **answering must never
silently change a surface the learner is not looking at.**

### The reason that survives, and what it costs

§13's reason 3 — *answers here are grounded, and grounding means referring* — is
still true and is the durable cost of this model. Answering needs the objective, the
prose and the code. Three mitigations, in order of how much they cover:

1. **The brief moves above both tabs** (§4). It already carries the objective, which
   is the single most-needed reference while answering, and it is *stop* context
   rather than surface content. This is the largest part of reason 3, answered.
2. **The code column is unaffected.** It was never in either tab.
3. **The prose is one collapsed disclosure inside Understanding.** One click, no tab
   change, no scroll position lost.

### The cost that remains, stated plainly

§13's reason 1 measured how rare rich practice state is. Re-measured today, on 759
nodes rather than 723, it is **unchanged**:

| | |
|---|---|
| Nodes answered at all | 52 of 759 |
| Of those, exactly one attempt | 40 (77%) |
| Two attempts · three | 10 · 2 |
| Nodes that ever recorded a gap | **8** (max 3) |
| Verifications ever taken | **2** |
| Remediation rounds | **0** |

So the frequency argument holds on its own terms — and it was answering the wrong
question. It measured *how often the rich case occurs*; the complaint is about *what
is simultaneously present in the common case*. One attempt on one stop already puts
prose, question, answer, verdict, gap and explanation on screen together. That is the
common case, and it is the one that feels heavy.

What reason 1 correctly predicts is the **switching cost**: roughly one deliberate
Lesson → Understanding move per stop, ~15 per session. §3 makes every one of those
learner-initiated and one click, and §5 argues the boundary is worth marking rather
than worth hiding.

---

## 2. Information architecture

### The brief belongs to neither tab

It sits **above the tab bar**, unchanged from L3: position, title, objective,
counters, collapsing when pinned. Three reasons:

- It is **stop context**, not surface content. Which stop this is and what claim the
  learner should be able to make are true in both tabs.
- The objective is the reference most needed *while answering*, and it must not be a
  tab away — see reason 3 above.
- Its counters (`N unresolved`, `N answers`) are Understanding state, so keeping them
  always visible makes them the **cross-surface awareness signal** for that side. No
  new mechanism needed.

### One tab bar, not two

The session already has a tab bar in the lesson column: `Lesson` · `Progress map`.
Adding `Lesson` · `Understanding` inside it produces two bars, one of which contains
a tab called `Lesson` nested under a tab called `Lesson`. That is not a styling
problem, it is an ambiguity.

**Merge into one bar: `Lesson` · `Understanding` · `Map`.** The map is already a
peer view of the session, not a child of the lesson, so this is more honest than the
current nesting as well as unambiguous.

### Lesson — "what should I read now?"

| Block | Source |
|---|---|
| `why_now` | lesson |
| setup prose | lesson (`setup`, or `walkthrough` on pre-B4 lessons) |
| trace path | node anchors |
| explanation | lesson `reveal`, unlocked by answering |
| takeaway · ownership | lesson, travelling with the explanation |
| **adaptive additions** | re-taught prose (**replaces**), gap-driven teaching, hints promoted from feedback |

Re-teaching **replaces** rather than appends — the panel already refetches the lesson
when `adaptation.retaught` is true, so this is existing behaviour, not new
machinery, and it is what stops Lesson growing without bound.

### Understanding — "what have I shown, what am I missing, what now?"

| Block | Source |
|---|---|
| current question + composer | lesson `prompt` |
| verification question | `/verify` |
| current verdict, key point, rationale | `respond` |
| open gaps | `result.gaps ?? node.gaps` |
| actions | `feedbackActions` |
| previous attempts | `node.attempts`, verification-filtered |
| resolved gaps | `result.resolved` + `checked.targeted` |

The name is right for this content. `Practice` implies drills; a stop asks once and
the answer is evidence that moves goal readiness. `Questions` is narrower than the
list above. `Understanding` matches the header's own `Demonstrated` measure and the
`understanding_state` vocabulary already on the wire.

---

## 3. State-transition walkthrough

The scenario asked for, transition by transition. **Active tab** is what the learner
is looking at; a bullet marked ● is a change they can see without switching.

Two rules govern the whole table, stated once:

- **R1 — tab selection changes only on a learner click, or on arrival at a different
  stop.** Never on a phase transition within a stop.
- **R2 — a change in the tab you are not looking at is announced in the tab you
  *are* looking at**, with a control that takes you there.

### T0 · arrive at the stop

- **Active:** `Lesson` (a new stop resets here — new material, nothing demonstrated)
- **Lesson:** `why_now` + setup prose open · trace path collapsed · explanation absent
- **Understanding:** the question and composer, ready; no history on a first visit
- **Auto-switch:** no — arrival at a new stop
- **Cross-surface signal:** the `Understanding` tab shows a quiet "1 question" marker
- **Expanded:** setup prose · **Collapsed:** trace path · **History:** none

### T1 · learner chooses to answer

- **Active:** `Understanding` — by clicking either the tab or the primary
  **"Answer this"** at the foot of Lesson
- **Lesson:** unchanged
- **Understanding:** question + composer expanded; the setup available as a collapsed
  **"The setup"** disclosure
- **Auto-switch:** **no** — the learner pressed a control that says where it goes
- **Returning to material:** objective in the brief · setup one click inside this tab
  · code in its own column, untouched
- **Expanded:** question + composer · **Collapsed:** the setup

### T2 · submits a partial answer → feedback

- **Active:** `Understanding` (unchanged — the result of an action appears where the
  action was taken)
- **Lesson:** nothing yet
- **Understanding:** composer replaced in place by the verdict card — key point,
  rationale, one primary (`Check my understanding`), secondary, tertiary
- **Auto-switch:** no
- **Expanded:** verdict card · **Collapsed:** the setup, the previous question
- **History:** the attempt enters `Previous answers`, collapsed

The explanation unlocks at this moment but **lives in Lesson**, so:

- **Cross-surface signal:** the `Lesson` tab gains a dot, and the verdict card
  carries a line — *"The explanation is now available."* — with a **Read it** control.
  This is R2, and it reuses L4's consequence line rather than inventing a channel.

### T3 · a gap is discovered

- **Active:** `Understanding`
- **Understanding:** the gap is already *in* the key point ("you're working from: …"),
  so the gap list stays **collapsed** behind the brief's counter, which increments
  visibly
- **Lesson:** unchanged
- **Auto-switch:** no

### T4 · additional teaching arrives (re-teach, or gap-driven material)

- **Active:** `Understanding` — **unchanged, deliberately**
- **Lesson:** the new material appears; a re-teach **replaces** the setup, gap-driven
  material is added as its own section marked *new*
- **Understanding:** the verdict card's consequence line says which happened —
  *"This stop has been rewritten to answer that."* — with **Read it**
- **Auto-switch:** **no.** This is the case the instruction is really about. The
  learner is mid-diagnosis; throwing them into a document they did not ask for
  discards their place and their attention. Announce, offer, do not move.
- **Cross-surface signal:** dot on `Lesson` + the consequence line + its control
- **Expanded in Lesson when they go:** the new section · **Collapsed:** the previous
  explanation, into `Earlier explanation`

### T5 · a warm-up is inserted, and started

- **Active:** `Lesson`, because **the stop changed** — a warm-up is a different node
- **Auto-switch:** yes, and it is not a tab switch. `Start the warm-up` is a
  navigation to another stop, and every stop opens on `Lesson` (T0). Nothing
  surprising happens; the learner pressed a button that names the destination.
- **Lesson:** the warm-up's own material · **Understanding:** the warm-up's own
  question; the parent stop's history is not shown here because it belongs to that
  stop
- **Returning:** completing the warm-up returns to the parent stop, again on `Lesson`,
  with the parent's Understanding history intact

### T6 · verification requested

- **Active:** `Understanding`
- **Understanding:** the verification question **replaces** the verdict card in place
  — the single-composer invariant, which is now also a single-artifact rule within
  this tab; no model answer and no reveal, because none is sent (§18.7)
- **Lesson:** unchanged, and still holds the explanation the learner may re-read
- **Auto-switch:** no
- **Expanded:** the verification · **Collapsed:** the superseded verdict, into
  `Previous answers`

### T7 · verification resolved

- **Active:** `Understanding`
- **Understanding:** the check report — what closed, by name, struck through; the
  learner's own words, which are otherwise nowhere; primary `Next stop` if nothing
  is left open, `Check another` if something is
- **Lesson:** unchanged
- **Cross-surface signal:** the brief's `unresolved` counter decrements visibly
- **History:** the closed gap moves to a collapsed `Resolved` group; it is not
  deleted, because it is evidence

### T8 · next stop

- **Active:** `Lesson` — the stop changed (T0 again)
- **Auto-switch:** yes, same justification as T5: a new stop, from a button that says
  so. Tab state does not persist across stops, because "which surface was I on for
  the last stop" is not a preference worth restoring.

### Summary of automatic switches

| Trigger | Switches? | Why |
|---|---|---|
| Submitting an answer | **No** | Result appears where the action was taken |
| Explanation unlocking | **No** | Announce in place, with a control |
| Re-teach / gap material | **No** | The learner is mid-diagnosis |
| Verification requested or resolved | **No** | Same surface throughout |
| `Answer this` | Yes — learner pressed it | The control names its destination |
| `Read it` | Yes — learner pressed it | Same |
| Starting a warm-up · next stop | Yes — **the stop changed** | Not a tab switch; a new page |

The system never changes surface on its own initiative. Every switch is either a
click on a control that says where it goes, or arrival somewhere new.

---

## 4. Disclosure rules

The governing rule, one sentence: **within a surface, exactly one artifact holds full
attention — the one the learner's current state is about — and everything superseded
collapses to a labelled, counted disclosure.** This is L4's rule, applied twice.

### Lesson

| Block | Open when | Collapsed when |
|---|---|---|
| `why_now` | always (one line) | — |
| setup prose | no newer material exists | superseded by a re-teach or a newer section |
| trace path | never | always — it is a list of links, and the brief names the anchors |
| explanation | unlocked, and it is the newest material | a newer adaptive section exists |
| adaptive section | it is the newest, and unread | a newer one arrives |
| earlier explanations | never | always, grouped as `Earlier explanation (N)` |

**At most one section is expanded as "new".** Adaptive material does not append
indefinitely: a re-teach replaces, and superseded explanations group.

### Understanding

| Block | Open when | Collapsed when |
|---|---|---|
| current question / verification | it is the live artifact | a verdict supersedes it |
| current verdict | it is the live artifact | a new question supersedes it |
| open gaps | the learner is answering (STUDY) | a verdict is up — the key point already names the leading one |
| the setup | never | always, as `The setup`, so answering never needs a tab change |
| previous answers | never | always, as `Previous answers (N)` |
| resolved gaps | never | always, as `Resolved (N)` |

**Never nest the two axes for the current thing.** Material about the learner's
current state must be expanded in its own surface. Only superseded material is
allowed to be both behind a tab and behind a disclosure — otherwise discovery cost
compounds, which is risk R2 below.

---

## 5. Risks

**R1 · Silent change in the unattended surface.** §13's surviving objection. It is a
real failure mode: adaptation that happens where nobody is looking is the "adaptation
is invisible" problem in a new costume.
*Mitigation:* R2 of §3 — announce in the attended surface, with a control. Three
signals, deliberately redundant: a dot on the tab, a consequence line in the verdict
card, and the brief's counters. The consequence line already exists from L4.
*Residual:* a learner who never reads the verdict card and never looks at the tab bar
could miss it. Acceptable — they have also skipped the feedback.

**R2 · Two axes of hiding.** Behind a tab *and* behind a disclosure compounds to
"where is anything?".
*Mitigation:* the never-nest rule in §4. Current-state material is always expanded in
its surface.
*Measurable gate:* for every state in §3, the artifact the state is *about* is
expanded and reachable without opening a disclosure.

**R3 · Lesson becomes an accumulating document.** The user's own warning.
*Mitigation:* re-teach replaces (already the behaviour); adaptive sections group into
`Earlier explanation (N)`; at most one section expanded as new.
*Measurable gate:* the number of expanded sections in Lesson never exceeds two,
whatever the adaptation history.

**R4 · The switching cost is real and lands on the common case.** ~15 deliberate
switches a session, to benefit states that are currently rare (§1's table).
*Mitigation:* every switch is one click from a control that names its destination; the
objective never requires a switch; the setup never requires a switch.
*Honest counter-argument:* the boundary between reading and being examined is exactly
what the learner says is missing, so marking it is the point rather than the cost.
*Falsifiable:* if the flag comparison shows more time hunting and no reduction in
reported busyness, this model is wrong and §13 was right.

**R5 · The phase model could start driving navigation.** Phases and tabs map
suspiciously well, and it would be easy to let a phase transition select a tab.
*Mitigation:* R1 of §3, as a test — tab selection is a function of learner clicks and
`nodeId`, never of `phase`.

**R6 · Cementing this before the journeys are run.** Credits are restored; the seven
canonical journeys have still never run end to end on live data on any path.
*Mitigation:* run them on `next` (L4) **before** building this, so the comparison has
a measured baseline rather than an impression. Then run them again on `surfaces`. And
`L5` does not remove the legacy path until both have passed.

---

## 6. What survives from L1–L4

Almost all of it. The revision is confined to **where blocks are placed**, which is
one file plus an extension to one pure function.

| From | Status |
|---|---|
| `L1` `lessonPhase` — the four phases | **Kept whole.** Now drives Understanding's internal state, which is what it was always describing |
| `L2` ten block components | **Kept whole.** They are distributed across two surfaces instead of one column |
| `L2` `lib/verdict` | **Kept whole** |
| `L3` `LessonWorkspace` + brief | **Kept, and promoted** — the brief moves above the tab bar, which is what it was already behaving like |
| `L3` brief collapse-on-scroll | **Kept whole** |
| `L4` `Disclosure` | **Kept whole**, and used twice as much |
| `L4` `feedbackActions` + its 320-case sweep | **Kept whole** |
| `L4` `feedbackSummary` key point + consequence | **Kept whole**; the consequence line becomes the cross-surface announcement |
| `L4` `FeedbackCardNext` | **Kept whole** |
| `L4` `lessonView.lessonBlocks` | **Extended** — each block gains a surface (`lesson` \| `understanding`), and the state rules stay as they are |
| `L4` `LessonCanvas` | **Revised** — becomes two surface renderers driven by the same view model |
| `L4` tests | **Kept**; the render-level ones gain a surface assertion |

Net: one new component (the tab bar), one revised component, one extended pure
function. Nothing thrown away.

---

## 7. Implementation plan

Behind the existing flag, **widened to three values** so all three architectures stay
comparable — which matters, because this decision has already been revised once:

```
NEXT_PUBLIC_CODEONBOARD_UI = legacy | next | surfaces
  legacy    the renderer as it shipped
  next      L4's single canvas, unchanged and still comparable
  surfaces  Lesson / Understanding
```

| # | Step | Contents | Gate |
|---|---|---|---|
| **S0** | Run the journeys on `next` first | All seven canonical journeys, live, flag `next` | A measured baseline for the comparison, and L4's own gate finally closed |
| **S1** | `lessonSurfaces.ts` | Extend `lessonBlocks` with a surface per block; add `surfaceOf(block)`; tests per phase per surface | Pure, no render change. The never-nest rule (R2) and Lesson's two-expanded cap (R3) are assertions here |
| **S2** | The tab bar | Merge to one bar: `Lesson · Understanding · Map`; tab state a function of clicks and `nodeId` only | A test asserting tab selection never changes on a phase transition (R5) |
| **S3** | The two surface renderers | Reuse `LessonCanvas` twice, driven by S1 | Every block appears in exactly one surface; no block lost |
| **S4** | Cross-surface awareness | Tab dot, consequence-line announcement with `Read it`, brief counters | For every §3 transition, a change in the unattended surface is announced in the attended one (R1) |
| **S5** | Lesson's adaptive sections | `new` marking, `Earlier explanation (N)` grouping | Expanded sections never exceed two (R3) |
| **S6** | Journeys on `surfaces` | All seven again, both themes, all four text sizes | Compared against S0's baseline |

**S1–S6 are complete.** S0's baseline and S6's comparison are recorded in
`evidence/s0-live-journeys.md` and `evidence/s6-surfaces-journeys.md`. The headline:
on the same stop in the same state, what is on screen at once fell from **1747px in
one column to 1031px (Lesson) and 806px (Understanding)** — 54% less while
answering, 41% less while reading — with **zero contrast failures and zero expanded
disclosures across sixteen configurations** (both themes, all four text sizes, both
surfaces).

`L5` remains blocked and the legacy renderer stays, per the rule below: it comes out
only once the flag comparison has been made by a human, not by a measurement.

**S0 is the first thing to do, and it is not optional.** L4's gate — "journeys 1–7
pass on both paths" — has never been met, because the model calls were unaffordable
at the time. Building a third architecture on top of two unvalidated ones would be
building on an impression of an improvement.

`L5` stays blocked until S6, and the legacy renderer stays until then.
