# UI Implementation Plan

> **Status:** in progress on `ui-redesign`. **M0, D1, D2, D2b, D3, F1, F2, F3a, F3b shipped; F3c next.**
> Per-milestone commits and measurements: [`evidence/ux-journeys.md`](evidence/ux-journeys.md).
> **Inputs:** [`ui-baseline.md`](ui-baseline.md) (evidence),
> [`ui-direction.md`](ui-direction.md) (principles), [`ui-concept.md`](ui-concept.md) (visual concept).
> **Purpose:** turn the concept into small, independently verifiable, independently
> revertable milestones — and decide where we stop and look before continuing.
> **Last updated:** 2026-08-19

---

## 0. Decisions locked before planning

| # | Decision | Consequence for the plan |
|---|---|---|
| 1 | **Inline action model (Option B)** | No docked bar is built. Three rules become testable invariants: action adjacent to the state that produced it; never below a long-form explanation; phase changes anchor visual position. Conditional dock (Option C) is **not** in scope — it enters only if L4's manual scenarios show stranded actions |
| 2 | **Auto-advance not assumed** | Resolved below in §1 from the real question set. Short answer: **no timed auto-advance anywhere**, and **no double-click path** — click selects, an adjacent confirm plus `Enter` commits, `↑`/`↓` navigate. Editable transcript stays |
| 3 | **Feedback leads with a key point** | A one-line verdict + sticking-point above the rationale. Implemented with a three-level fallback ladder (§2) because the wire has no such field today. **This is the only summary layer** — no second key point above the explanation |
| 4 | **No learning-engine semantics change** | §3 is a behaviour contract. Every milestone lists what must not change; the Python suite is the guard |
| 5 | **Pre-session is not "later"** | Landing and interview (`P1`, `P2`) land **immediately after the visual foundation**, before the shell and flow work, so the first thing a learner sees reflects the new direction early. Generation and briefing (`P3`, `P4`) stay later because their data dependencies genuinely require it (§9) |
| 6 | **Base branch is `master`** | Verified, not assumed — see §7. `main` is stale and is an ancestor of `master`. No new branching model is introduced |

### Two discoveries that shape everything below

**There is no frontend test tooling.** 49 Python test files; zero JS test
infrastructure, no `test` script, no runner. So "tested" cannot mean what it means
on the backend until we create the means. M0 addresses this narrowly (§4).

**`RespondResult` carries no short headline.** Available today: `classification`,
`gap_kind`, `rationale` (long prose), and `gaps[].claim` (the misconception in the
learner's own words). The example `Not quite — Graph is directed by default` is a
*correction*; what we store is the *misconception*. That gap is bridged in §2 rather
than by inventing text in the UI.

---

## 1. Questionnaire confirmation — resolved from the real question set

Read from `backend/agents/goal/questions.py`. There are exactly three option
questions and they are not alike:

| Question | Options | Length | Consequence of a mis-click |
|---|---|---|---|
| `familiarity` | 4 | 24–45 chars | Low — recalibrates pitch |
| `goal_type_raw` | 6 | 25–52 chars | **Highest** — routes `goal_type`, decides which follow-ups appear; going back past it clears the goal type |
| `code_depth` | 3 | **60–91 chars** | High — decides how much gets taught |

Everything else is free text (`primary_goal`, `background`, and every follow-up).

`code_depth`'s options are full outcome sentences — *"I'll be working in here — the
map, plus what I'd need to change things safely"*. A learner must read all three and
compare them. Advancing on first click is exactly wrong there. And `goal_type_raw`
routes the entire remainder of the interview.

**Proposal: no timed auto-advance on any question.** Instead, make selecting and
confirming feel like a single gesture:

- Clicking an option selects it with an unambiguous state, and the confirm affordance
  appears **adjacent to the selected row** — never a trip to the other side of the
  screen.
- `Enter` confirms the current selection. `↑`/`↓` move it. So the keyboard path is
  `↓ ↓ Enter` — two beats, faster than any timer.
- Free-text keeps `Continue` plus `⌘↵`, as today.

**Considered and rejected — auto-advance after a visible cancellable delay.** It
introduces a timer the learner does not control and reintroduces exactly the
jumpiness we want to avoid on the two consequential questions.

**Considered and rejected — double-click as a fast path.** Not a discoverable or
conventional interaction for a list of choices, and an undiscoverable shortcut earns
nothing. The four explicit affordances above are the whole interaction.

**Uniform across all three option questions** — deliberately. Making `familiarity`
behave differently from `code_depth` because its options are shorter would be a
worse experience than either behaviour applied consistently. If later testing shows
people want it, `familiarity` alone is the safest candidate; that is a follow-up, not
a launch decision.

---

## 2. Feedback key point — the fallback ladder

The feedback card renders, top to bottom:

```
⬤ NOT QUITE — you're assuming h() falls back to np.inf when locations is missing
   ↑ verdict word            ↑ the sticking point, one line

<rationale — the Grader's full reasoning, always present, never collapsed>

── <consequence sentence, when the system adapted>
●━Primary━●   Secondary   tertiary
```

The key point resolves through three levels, best available first:

1. **`headline`** — a short corrective sentence, if the Grader supplies one. Requires
   the optional backend milestone **B1**. Produces exactly the requested form:
   *"Not quite — `Graph` is directed by default."*
2. **Composed from the leading gap** — `classification` label + the blocking gap's
   `claim`, framed honestly as an assumption the learner is carrying rather than as a
   correction we did not compute. Real data, no backend change, ships in **L4**.
3. **Verdict word alone** — for pre-gap-model sessions with no gaps on the wire.

This mirrors how the codebase already handles schema evolution (`objective()`
falling back to `understand`), and it means L4 does not block on B1.

**Guard against shallow skipping, as required:** the rationale sits immediately
below the key point and is **never collapsed** in the `FEEDBACK` phase. Only the
*explanation/reveal* — a separate, longer artifact — sits further down. The key point
orients; it never substitutes.

**One summary layer only.** The key point at the top of the feedback card is the
single condensation in the flow. `ui-concept.md` §10.4 floated a second `Key point`
above the explanation as well; that is **dropped** and is not scheduled. It would
give the learner two places to feel finished, which is precisely the shallow-skipping
risk this design is trying to avoid. It returns only if testing shows a concrete need.

---

## 3. Behaviour contract — what must survive

This is the plan's most important table. Every one of these is live behaviour with a
documented reason, and several are non-obvious workarounds that a redesign would
plausibly delete by accident.

| Behaviour | Where it lives now | Must be preserved |
|---|---|---|
| **Retry declined** | `handleRetry`: `retry()` returns `{inserted:false}` | Declining is a real answer. Show `warmUpUnavailable` and **keep the verdict visible** so other routes forward stay reachable. Never silently reset the form |
| **Warm-up: refresh deliberately skipped** | `submitAnswer`: `if (res.mutation?.kind !== "prerequisite") onRespond()` | The graph refresh is skipped so the verdict stays readable. Do not "fix" this by always refreshing |
| **Pending attempt** | Synthesized `pending` attempt object | Consequence of the skip above. The just-graded answer must still appear, and must not double up once the refresh does run |
| **Warm-up cap** | `warmUpInserted` suppresses `canRequestWarmUp` | The Mutator caps one per node; never offer what would be declined |
| **Warm-up offer gating** | `canRequestWarmUp`: any non-`understood`, not just `prerequisite` | §18.11 — a `confused` learner must not get *fewer* options than a `partial` one |
| **Recovery detection** | `recovered` = failed attempt exists + latest is `understood` + warm-up title present | Drives the `RECOVERED` state. Recovery must never render in the failure colour |
| **Gap source preference** | `openGaps = result?.gaps ?? node.gaps ?? []` | The graph lags by one refresh on the warm-up path |
| **Verification answers excluded from history** | `.filter(a => (a.kind ?? "assessment") !== "verification")` | They carry no `classification`; including them blanks a row, inflates the count and corrupts `latest` |
| **No model answer with a verification** | Nothing is sent, nothing rendered | §18.7 — showing the answer beside the question is what made re-asking meaningless |
| **Re-teach refetch** | `if (res.adaptation?.retaught) getLesson()` | The on-screen lesson must become the corrected one |
| **Pruning notice** | `adaptation.pruned > 0` | Removal must be reported, not silent |
| **Reveal on revisit** | `revealed = Boolean(result) \|\| attempts.length > 0` | A returning learner is reading, not being tested |
| **No source, no lesson** | Teaching fails the lesson when all anchors fail | Never render an ungrounded lesson |
| **Chapter introduced once per visit** | `introduced` ref + `settled === 0` guard | Reload, resume mid-chapter and re-reading must not re-introduce |
| **Focus counter** | `focusKey` increments on every location request | Re-opening the same anchor must still scroll the pane |
| **Highlight file guard** | `highlightForOpenFile` only when `openFile === currentNode.file` | A node's range must never highlight lines in an unrelated file |
| **Multi-anchor range** | `viewingRange` set only for a chosen anchor | Step 2 of a flow must open the right lines, not the display range |
| **`optional` semantics** | Excluded from walk/counters, kept in graph | Still teaches and grades when reached from the rail |
| **Two progress measures** | `goal_readiness` + `stops_settled` | Two grammars, never two percentages. Readiness may fall only when evidence changes |
| **Scope adjust** | `setScope` → `{applied, changed}`, then reload | Must report "nothing to shorten/deepen" honestly |
| **Briefing independence** | Loads separately, may fail alone | A failed briefing is a missing paragraph, never a blocked session. `personalized` vs `generic` must stay labelled |
| **Real pipeline progress** | `sessionProgress` poll; `stages`/`done`/`activity`/`calls`/`seconds`; server elapsed preferred | No invented stages, no invented percentages, no timer-driven progress |
| **Resume** | Server `resume_point()` skips optional | Landing stop on resume must not change |

**Guard:** the existing Python suite covers the semantics — `test_adaptation*`,
`test_gap_*`, `test_mutator`, `test_progress`, `test_attempt_history`, `test_history`,
`test_pipeline_progress`, `test_briefing`, `test_grader_gaps`, `test_learning_graph`,
`test_curriculum`. Any milestone that needs a backend change states it explicitly;
most need none.

**Recorded suite baseline, measured at M0 on untouched `backend/` and `tests/`:**

```
14 failed, 1276 passed      all 14 in tests/test_mentor_dossier.py
```

This is **pre-existing** and not caused by any work in this plan — verified by
`git diff --stat master -- backend/ tests/` being empty at the time of measurement.
Mechanism: `CODEONBOARD_CURRICULUM` leaks to `"1"` when `test_calibration_harness.py`
is in the same run, which switches the planner and invalidates that module's fake wire
responses. `test_mentor_dossier.py` passes 22/22 alone;
`CODEONBOARD_CURRICULUM=1 pytest tests/test_mentor_dossier.py` reproduces exactly the
same 14 failures. The raw assignment is `scripts/calibrate_bands.py:436`
(`os.environ["CODEONBOARD_CURRICULUM"] = "1"` inside `main()`, which the harness test
invokes); that module's autouse `_contain_the_flag` fixture exists to contain it and
does not fully succeed.

**So the gate is: no NEW failures against this baseline** — not "green" — until the
leak is fixed. Fixing it is a one-file backend test-hygiene change, deliberately
**not** folded into any UI milestone; it should be its own `fix:` commit so it stays
isolated and reviewable.

---

## 3a. Carried-forward UX issue: feedback information architecture

**Raised 2026-08-19, after F3b was visually approved.** The practice surface fixed
the *separation* problem — lesson content versus interaction area now reads clearly.
It did not fix, and was never going to fix, **what is present immediately after an
answer**.

Recorded here as an explicit input to the L track rather than as a styling defect,
because the remaining problem is conceptual: which information and which actions
belong in the moment after an answer, what should be secondary or collapsed, and
how feedback, gaps, retry, warm-up and verification relate to one another.

**Do not solve this opportunistically in F3c or F3d.** Those milestones touch action
weight and contrast; neither should quietly re-scope the feedback state. When the L
track reaches it, revisit the feedback state **as a whole**.

### What is actually present after an answer — source-derived, not impressionistic

Inside the feedback branch of the practice well alone:

| | |
|---|---|
| Independent conditional sub-blocks | **16** |
| `<Button>` call sites (1–4 render at once) | **11** |
| Distinct copy strings referenced | **21** |
| Callouts | 2 |

And simultaneously present in the column around it: the full setup prose
(expanded), the trace-path anchor list, the gaps list with a per-gap `Set aside`
control, the attempts history, and below the well the explanation plus its
`takeaway` and `ownership` callouts.

So the learner who answers once can face: a verdict word, a rationale, a
consequence sentence, an adaptation callout, a re-taught notice, a pruned notice, a
warm-up status line, up to four actions — and around all of it, five other blocks
that were already on screen.

### Why this is L-track work and not F3 work

- The fix is **deciding what is primary**, which is what the phase model in `L1`
  exists to express. Sixteen conditionals in one branch is the same failure mode
  D2b exposed at a smaller scale: presentation keyed off many independent flags
  rather than off one derived state.
- The collapse discipline that would fix it — superseded artifacts to one line,
  gaps and history behind counters — is `L4` and `L5`, already planned.
- Restyling cannot reduce a count of sixteen.

### Specific questions for the L track to answer

1. After a *correct* answer, what should be on screen at all beyond the verdict and
   `Next stop`?
2. Should the adaptation notices (`retaught`, `pruned`, warm-up status) be part of
   the feedback, or belong to the adaptation channel in `A1`?
3. Should gaps remain visible during feedback, or collapse to the brief's counter
   the moment a verdict arrives?
4. Do `takeaway` and `ownership` belong beside the explanation, or are they a third
   thing competing with both the verdict and the reveal?
5. Is the attempts history ever wanted *during* feedback, as opposed to on demand?

### Status

**Answered in L4** — see `evidence/ux-journeys.md`. All five questions are resolved
in `lib/lessonView.ts`'s own doc, and the answers are asserted rather than described:
the block states per phase, the single consequence line, and the count of open blocks
are each a test. Measured result on the same stop and answer: the feedback canvas is
28% shorter and has one primary action instead of two.

`L5` is now closed, and not as originally written. The surfaces split had already
put the gap list and the history behind disclosures in Understanding, so panels
would have been a third home for material that had just found its second. What L5
actually did was delete the pre-redesign renderer, invert the flag's default to
`surfaces`, and fix a bug the split had introduced: the brief renders on both
surfaces, its counters pointed at blocks that live only in Understanding, and on the
Lesson tab they were live-looking buttons that did nothing. They now cross first.

---

## 4. Test strategy

Given zero frontend tooling, the proposal is deliberately narrow — enough to protect
the invariants, not a test pyramid.

**Layer 1 — Vitest + React Testing Library** *(added in M0)*
Covers what is pure logic and where regressions will actually happen:
- the phase derivation function (`lessonPhase.ts`)
- verdict → available-actions mapping (the branch table)
- render-order invariants: exactly one composer per phase; primary action never
  rendered after a long-form artifact; disclosures collapsed by default
- the feedback key-point fallback ladder
- `route-sections` / `graph-layout` pure functions (currently untested in JS)

**Layer 2 — browser probe** *(documented in M0, run manually at gates)*
A small script measuring what only a browser can: contrast ratios, geometry, the
responsive bands. This productizes the technique from the baseline's live validation
pass — it needs no browser driver and runs in the page.

Asserted properties:
- every text element ≥4.5:1 against its composited background
- exactly one `textarea` in the workspace
- primary action within one viewport of its phase artifact
- workspace non-content chrome ≤25% of scroll height
- header goal zone ≥240px at 1024px; no header overflow ≥960px

**Layer 3 — canonical journeys** *(§6)* — run at the gates listed per milestone.

**Hard scope limit on Layer 2.** The probe is a **single small measurement script** —
it reads computed styles and geometry from an already-open page and prints
pass/fail lines. It must not acquire: a driver, a browser launcher, fixtures, a
runner, an assertion DSL, retries, or reporters. If it starts wanting any of those,
that is the signal to adopt Playwright instead, not to keep building. Ceiling: one
file, ~150 lines. Anything beyond that is scope creep dressed as dependency
avoidance.

**Deliberately deferred:** Playwright/Puppeteer. The natural home for Layer 3
eventually, but a heavy dependency with no existing frontend e2e to extend. Revisit
once Track L lands and the journeys have stopped changing shape.

---

## 5. Milestones

Seven tracks. `D` defects · `F` foundation · `S` shell · `L` learning flow ·
`P` pre-session · `A` adaptation · `X` polish · `B` optional backend.

### Build order and dependencies

```
M0 ─┬─▶ D1 ─▶ D2 ─▶ D3                          defects — ship first, independent
    │
    └─▶ F1 ─▶ F2 ─▶ F3                          visual foundation
                     │
                     ├─▶ P1 ─▶ P2 ─▶ P2b        pre-session front half  ◀── moved up
                     │
                     ├─▶ S1 ─▶ S2               shell + responsive
                     │
                     ├─▶ L1 ─▶ L2 ─▶ L3 ─▶ L4 ─▶ L5   learning flow
                     │                           │
                     └───────────────────────────┼─▶ P3 ─▶ P4   pre-session back half
                                                 │
                                                 └─▶ A1 ─▶ X1

optional, unblocked, any time after their dependency:
   B1 (Grader headline)      after L4
   B2 (progress facts)       before or with P3
```

**Reading order below is build order.**

Why this order:

- `D1–D3` depend only on M0 and must not wait for anything cosmetic.
- `P1`/`P2` sit **immediately after `F3`** so the landing page and interview — the
  first thing any learner touches — reflect the new direction as soon as the
  foundation exists, rather than trailing the entire session redesign. They depend
  only on `F2`/`F3` and touch files (`app/page.tsx`, `GoalDialogue.tsx`) that no other
  track modifies, so they carry no merge risk against `S*` or `L*`.
- `P3`/`P4` stay late for a real reason, now verified (§9): `P3`'s concept needs
  progress data the backend does not currently expose, and `P4`'s route→rail
  transition needs the rail from `S2` and the `RouteItem` primitive to be settled.
- `S1`/`S2` before `L1–L5` so the frame the flow work lands inside is already correct.
- After `F3`, `P1→P2`, `S1→S2` and `L1→L5` are mutually independent and could be
  interleaved if useful; the sequence above is simply the lowest-risk single ordering.

🔴 = **stop and manually inspect before continuing.**

---

### M0 — Test and flag scaffolding
- **Goal.** Make later milestones verifiable and reversible. No user-visible change.
- **Files.** `frontend/package.json`, `vitest.config.ts`, `frontend/test/setup.ts`, `scripts/ux-probe.mjs`, `frontend/lib/flags.ts`
- **Behaviour.** None. Adds `CODEONBOARD_UI` flag plumbing (`legacy` default / `next`), following the project's existing `CODEONBOARD_CURRICULUM` / `CODEONBOARD_GAPS` pattern.
- **Visual.** None.
- **Data deps.** None.
- **Tests.** Runner installed; smoke test on `graph-layout` and `route-sections` pure functions.
- **Manual.** `npm run dev` still boots; `npm test` runs.
- **Must NOT change.** Any rendered output. Any Python.
- **Gate.** `npm test` green, `pytest tests/` green, app visually identical.
- **Commit.** 1.

---

### D1 — Fix the invisible gap and verification surfaces 🔴
- **Goal.** Make a shipped, unusable feature usable. **Highest priority in the plan.**
- **Files.** `frontend/components/LessonPanel.tsx` (lines ~468–518 only)
- **Behaviour.** None. Pure token correction.
- **Visual.** `bg-paper`→`bg-slab`; `text-ink`→`text-chalk`; `border-hairline`→`border-rule`; the verification question `text-ink`→`text-chalk`; the solid `bg-signal text-paper` submit → the standard primary treatment. Applies to both themes.
- **Data deps.** None.
- **Tests.** Probe assertion: every gap/verification text ≥4.5:1 in both themes.
- **Manual.** Session `cff533a5…`, node with open gaps: gap card legible, `Set aside` legible; request verification, **the question is visible**; repeat in light theme.
- **Must NOT change.** Gap ordering, `waive` behaviour, blocking/non-blocking labelling, verification request/submit semantics, the absence of a model answer.
- **Gate.** Measured ratios: question ≥7:1 (was 1.00), submit label ≥4.5:1 (was 1.11), gap sublabel and `Set aside` ≥4.5:1 (was 1.97 dark / 1.64 light).
- **Commit.** 1. **Cherry-pickable to `main` on its own.**
- **Why inspect.** It is the one milestone that changes a broken thing into a working thing; confirm by eye in both themes before moving on.

---

### D2 — One composer, one Submit
- **Goal.** Remove the duplicate-input defect without waiting for L4.
- **Files.** `LessonPanel.tsx`
- **Behaviour.** The original answer block no longer renders while a verification is outstanding — `{!result && !verification && …}`. `Not now` restores it. Interim: after grading, scroll the verdict into view and move focus to it.
- **Visual.** Only one input and one `Submit` on screen. No restyling.
- **Data deps.** None.
- **Tests.** RTL: with `verification` set, exactly one `textarea` and exactly one button labelled `Submit`.
- **Manual.** Wrong answer → `Check my understanding` → confirm one input, one `Submit`; `Not now` → original question returns with the answer field empty.
- **Must NOT change.** `requestVerification` / `respondToVerification` payloads; the excluded-verification-attempts filter; `answer` clearing on node change.
- **Gate.** RTL test passes; the mirroring behaviour is gone.
- **Commit.** 1. Cherry-pickable.

---

### D2b — What a check reports *(found in manual testing, shipped)*
- **Goal.** After answering a verification, say what happened. Added to the plan after J4 turned it up by hand.
- **Files.** `LessonPanel.tsx`, `lib/strings.ts`
- **Behaviour.** The result panel branches on `kind === "verification"` and reads `resolved` / `unresolved`, which were on the wire since M9 and rendered nowhere. Actions are chosen by what is left open rather than by `classification`, which is `null` on this path by design.
- **Visual.** A headline from what closed (Cleared / Partly cleared / Still open); a named list of closed gaps; the learner's own answer; a primary that moves on or checks again.
- **Data deps.** None. `resolved`, `unresolved`, `gaps` and `rationale` all already returned by `_respond_to_verification`.
- **Tests.** Six, covering all three outcomes against the real reply shape, including "the headline is never empty".
- **Must NOT change.** The attempts-history filter (it protects `latest`), the absence of a model answer beside a question, waive semantics, and the rule that a verification produces no adaptation.
- **Gate.** All-cleared path verified live; the other two branches unit-tested; no contrast regression in either theme.
- **Commit.** 1 — `d9cc50d`.
- **Lesson for L4.** Every branch in the result panel keyed off one nullable field, and a legitimate `null` silently disabled all of them. The phase model must not key presentation off a value that one real path leaves empty — this is exactly what `lessonPhase.ts` is for.

---

### D3 — Focus and disabled states
- **Goal.** Close the two remaining accessibility defects globally.
- **Files.** `globals.css`, then every component with an interactive element
- **Behaviour.** None.
- **Visual.** `:focus-visible` ring (2px `signal`, 2px offset) on every button, link, input and disclosure. Disabled becomes muted surface + `graphite` ≥3:1 + `not-allowed`, replacing `opacity-30/40`. Interview `Back` becomes **absent** on Q1 rather than invisible.
- **Data deps.** None.
- **Tests.** Probe: no interactive element has `outline: none` without a replacement; no disabled control below 3:1.
- **Manual.** Tab through landing, interview, session, map — the ring is always visible and never clipped.
- **Must NOT change.** Any layout or spacing. Which controls are disabled and when.
- **Gate.** Full keyboard traversal of all four routes with a visible ring throughout.
- **Commit.** 1–2.

---

### F1 — Token layer
- **Goal.** Add the new scales as tokens. Nothing consumes them yet.
- **Files.** `frontend/app/globals.css`
- **Behaviour.** None.
- **Visual.** **None** — purely additive. Existing utilities keep resolving as before.
- **Data deps.** None.
- **Tests.** Probe: rendered output byte-identical to pre-milestone (spot-check colours and sizes on three screens).
- **Manual.** Diff two screens before/after — no perceptible change.
- **Must NOT change.** Any existing token *value*. `--ui-scale`, `calc(N rem/16)` authoring, the theme mechanism, tag hues, `understandingStyle`.
- **Gate.** Zero visual diff.
- **Commit.** 1.

---

### F2 — Primitives
- **Goal.** Introduce the components and migrate call sites, **at current visual values**.
- **Files.** new `frontend/components/ui/*` (`Button`, `Surface`, `Callout`, `StatusChip`, `ConceptTag`, `StatePin`, `SectionLabel`, `Disclosure`); call sites across 9 components
- **Behaviour.** None.
- **Visual.** Intentionally near-zero. Small normalisations are expected where a call site drifted (six button paddings → one per size); each is listed in the commit message.
- **Data deps.** None.
- **Tests.** RTL per primitive: variant → class/attribute mapping; `Button` disabled semantics; `StatePin` renders all four understanding classes with distinct border styles.
- **Manual.** Every screen compared before/after; note deliberate normalisations.
- **Must NOT change.** `understandingStyle`/`tagStyle` outputs, shape-plus-colour encoding (dashed `insufficient` especially), `strings.ts` copy.
- **Gate.** No inline button class strings remain in `app/` or `components/` (excluding `ui/`); all screens inspected.
- **Commit.** 3–4 (one per primitive group), so a single bad migration reverts alone.

---

### F3 — Typography, spacing and geometry 🔴
- **Goal.** Apply the new type scale, spacing rhythm, radii and elevation ladder.
- **Files.** `globals.css`, `ui/*`, all components
- **Behaviour.** None.
- **Visual.** Large and deliberate: prose 13.5px→**16px/1.70/62ch**; 11 sizes→8; micro-label reduced to one per zone; radii 4px→3/6/10/14; surface ladder replaces most 1px borders; solid primary button appears.
- **Data deps.** None.
- **Tests.** Probe: distinct font sizes in the session ≤9; body computed 16px, line-height ≥1.65; measure 540–580px.
- **Manual.** All seven session states plus all four pre-session screens, both themes. Explicitly check the lesson is ~18–20% taller and that this reads as *calm*, not *sparse*.
- **Must NOT change.** Any semantic colour. `--ui-scale` behaviour at all four steps. Contrast must not regress anywhere.
- **Gate.** Side-by-side review of ≥8 screens in both themes; explicit sign-off that the prose size is right before Track L begins.
- **Commit.** 2–3.
- **Why inspect.** This is the milestone that decides whether the product *feels* new. If the prose size is wrong, we want to know here — before the flow work builds on it.

---

### P1 — Landing
- **Goal.** Air, a real primary, and an honest expectation of the wait — **without a number**.
- **Files.** `app/page.tsx`
- **Behaviour.** None. Adds one static line setting expectation.
- **Visual.** Per `ui-concept.md` §8.2, with one correction: **no fixed time promise.** We have no measured distribution across repository sizes or cached-vs-uncached runs, so "two to four minutes" would be exactly the kind of invented number the rest of this product refuses to print. Copy becomes *"Five short questions, then a few minutes while we read the repository — longer for large ones."* The one honest number is the question count, which is fixed at five core questions in `questions.py`.
- **Data deps.** `checkRepo` unchanged; recents unchanged.
- **Tests.** RTL: invalid repo shows the error; recents populate the field. Assert no hardcoded minute figure in the landing copy.
- **Manual.** Unreachable repo, server down, recents click-through.
- **Must NOT change.** Pre-interview `checkRepo` validation, recents persistence, `errorText` slug mapping.
- **Gate.** Both error paths legible; no time estimate anywhere in the copy.
- **Commit.** 1.

---

### P2 — Interview
- **Goal.** Conversational, not form-like — with §1's confirmation model.
- **Files.** `components/GoalDialogue.tsx`, new `components/goal/AnswerTranscript.tsx`, `components/goal/OptionList.tsx`
- **Behaviour.** Answered questions collapse into an editable transcript; `✎` calls the existing `goalBack` (repeatedly if needed) rather than a new endpoint. Options become a keyboard-navigable list: **click selects, `↑`/`↓` move, `Enter` confirms, adjacent confirm button.** No timed auto-advance, **no double-click path**.
- **Visual.** Full-width 44px option rows; unambiguous selected state; `Back` tertiary and absent on Q1; `2 of 6` as text plus the transcript; consistent upward transitions.
- **Data deps.** `goalStart`/`goalAnswer`/`goalBack` unchanged. **The transcript is built from `goalBack`'s returned answer plus locally retained answers** — no new backend field.
- **Tests.** RTL: click selects but does not advance; `Enter` confirms; `↑↓` move selection; `✎` on an earlier answer returns to it; going back past Q2 clears the goal type and the follow-ups change accordingly. Assert no `dblclick` handler exists.
- **Manual.** All six goal types through their follow-ups. Back from Q5 to Q2 and pick a different goal type — confirm the follow-ups and the transcript both update. Free-text `⌘↵`. Keyboard-only completion of the whole interview.
- **Must NOT change.** The five core questions and their order; option strings (`GOAL_TYPE_MAP` / `CODE_DEPTH_MAP` are keyed on them); the backend's rejection of out-of-vocabulary answers; `goalBack`'s ownership of goal-type clearing.
- **Gate.** All six goal-type paths complete; back-past-Q2 verified; interview completable by keyboard alone.
- **Commit.** 2–3.
- **Note.** Highest copy-sensitivity in the plan: the option strings are **parsed keys**, not labels. They must not be reworded.

---

### P2b — Review gate *(added after using P2)*
- **Why.** Three things surfaced by walking the shipped interview. A selection you had not confirmed was **lost by going back** — it lived in `answer` and nowhere else, so the server never knew about it. The running transcript beside each live question turned every question into a re-read of everything already said. And the last answer handed straight off to the pipeline, so a wrong answer cost a multi-minute run before it could be discovered.
- **Files.** `components/GoalDialogue.tsx`, new `components/goal/ReviewStep.tsx`, `components/goal/AnswerTranscript.tsx`, `lib/strings.ts`, **`backend/api.py`**.
- **Behaviour.** Answers are retained per question in a `drafts` ref keyed on question **text**, not index — index 6 is a different question per goal type, so keying on position would drop one follow-up's answer into another. The transcript moves to a **review step** shown only after the last answer; `onDone` fires when the learner starts, not when the interview ends. Two ways backwards: `Back` reopens the last question, `Change` reopens a specific one, both through the same `/goal/back` unwinding. Call count derives from what the **server** holds — `index - 1` answers mid-interview, `index` on the review — so reopening the last question from the review is one call and question 1 from a six-question review is six.
- **Backend change — outside what §1 anticipated.** `/goal/answer` did `del sessions[session_id]` the moment the goal was synthesised, because the client always started the pipeline immediately. With a gate in front, every `Back` and `Change` returned **404 `session_not_found`**. The delete is gone; retention is bounded at `_MAX_GOAL_SESSIONS` (64), evicted oldest-first, since there is no "learner closed the tab" signal to free them on. Four backend tests added.
- **The dead end that follows from it.** A backend restart, or that cap, can take the dialogue while the review is on screen. Not fatal: `/session/start` needs only the goal, which the client already holds, so **starting still works and only editing is lost**. On `session_not_found` the gate stays usable, the ways backwards are *removed* rather than left to fail again, and the copy says what is still possible. Mid-interview the same failure gets a different sentence, because there is no goal yet.
- **Cost.** Reopening and re-confirming re-runs the goal synthesis: one extra Haiku call per correction.
- **Must NOT change.** As P2, plus: `/goal/back` remains the only way backwards, and the server keeps ownership of goal-type clearing.
- **Gate.** Answers hidden at every question; gate reached without starting; every question and answer shown back; `Change` on the first row unwinding to question 1 with its answer restored; contrast clean in both themes.
- **Commit.** 1.

---

### S1 — Header
- **Goal.** Four zones; end goal-text starvation.
- **Files.** `app/session/[id]/page.tsx`, new `components/SessionHeader.tsx`, new `components/SessionMenu.tsx`
- **Behaviour.** Scope, `Briefing`, `Start over`, `Finish session` move into a `⋯` menu. `Finish session` gains a confirmation. `Hide source` is removed (the pane owns its own close).
- **Visual.** Goal zone gets `min-width: 240px` and wins over controls; journey measure becomes a compact track expanding on interaction.
- **Data deps.** `setScope`, `sessionStart(restart)` unchanged — same calls from a new location.
- **Tests.** RTL: menu contains all four actions; `Finish` requires confirmation. Probe: goal zone ≥240px at 1024px; no overflow ≥960px.
- **Manual.** 1600/1440/1280/1150/1024/960px: goal text always legible. Scope shorter/deeper still reports applied/not-applied honestly.
- **Must NOT change.** Both progress measures remain available with their two grammars. Scope semantics. Restart semantics.
- **Gate.** Probe passes at all six widths; scope round-trip verified.
- **Commit.** 1–2.

---

### S2 — Rail, source pane default, responsive bands 🔴
- **Goal.** Restore rail density; make the source pane on-demand; add the four bands.
- **Files.** `RouteRail.tsx`, `CodeViewer.tsx`, `lib/prefs.ts`, `app/session/[id]/page.tsx`, `globals.css`
- **Behaviour.** **`showCode` defaults to false**; the pane opens on citation click. At `<960px` it becomes an overlay sheet. Rail collapses to an icon strip `<1180px`, to an overlay `<960px`. Lesson column floor 560px — a panel that would breach it becomes an overlay.
- **Visual.** Chapter `why` moves out of the rail to the chapter overview and a tooltip.
- **Data deps.** `prefs.source` gains a persisted open/closed state; existing stored prefs must migrate without error.
- **Tests.** RTL: citation click opens the pane with the right file and range. Probe: lesson ≥560px at every band; rail/source obey the band rules.
- **Manual.** Multi-anchor unit — each `Step n of m` opens the correct file **and lines** (the `viewingRange` guard). Same-anchor twice still scrolls (`focusKey`). Dock/float, drag, keyboard resize, viewport re-placement all still work. Resume a session at 1024px.
- **Must NOT change.** `focusKey` semantics, `highlightForOpenFile` file guard, `viewingRange` behaviour, dock/float persistence, the short-hop-only smooth scroll rule.
- **Gate.** All four bands inspected; anchor-precision scenario passes.
- **Commit.** 2–3.
- **Why inspect.** Changes the default layout everyone sees, and touches the most gesture-heavy component in the app.

---

### L1 — Extract phase derivation (logic only)
- **Reads §3a.** The phase model is what replaces sixteen independent conditionals with one derived state.
- **Goal.** Introduce the phase concept with **zero render change**.
- **Files.** new `frontend/lib/lessonPhase.ts`; `LessonPanel.tsx` (compute only)
- **Behaviour.** None. The function derives `STUDY | FEEDBACK | VERIFY | RESOLVED` from existing state; nothing consumes it.
- **Visual.** None.
- **Data deps.** Reads existing `result`, `verification`, `attempts`, `node`, `graph`.
- **Tests.** RTL/Vitest — the heart of this milestone. A case per branch: fresh, revisit, understood, partial+gaps, partial-no-gaps, confused+warm-up-inserted, confused+warm-up-declined, verification outstanding, verification answered, waived, re-taught, pruned, pending-attempt path. Each asserts the derived phase **and** that it matches what the current UI renders.
- **Manual.** None needed — no visual change.
- **Must NOT change.** Anything rendered.
- **Gate.** Every branch in §3 has a passing test; zero visual diff.
- **Commit.** 1.

---

### L2 — Extract blocks into components (no visual change)
- **Goal.** Break up the 862-line file by *moving* code, not rewriting it.
- **Files.** new `components/lesson/*` — `LessonBrief`, `SetupProse`, `TracePath`, `GapList`, `VerificationBlock`, `AttemptHistory`, `AnswerComposer`, `RevealBlock`, `FeedbackCard`, `CompletionScreen`; `LessonPanel.tsx` becomes composition
- **Behaviour.** None.
- **Visual.** None — same markup, same order.
- **Data deps.** Props only; state stays in `LessonPanel`.
- **Tests.** RTL smoke per component. `AnswerComposer` gets the single-input invariant test.
- **Manual.** All seven states diffed before/after.
- **Must NOT change.** Render order, the `pending` attempt synthesis, `openGaps` preference, the verification-attempts filter, `revealed` logic, `recovered` logic.
- **Gate.** Zero visual diff across seven states; `LessonPanel.tsx` under ~250 lines.
- **Commit.** 3–4, one per component group.

---

### L3 — The Brief / Canvas frame 🔴
- **Goal.** Introduce the stable frame, still rendering today's blocks in today's order.
- **Files.** new `components/lesson/LessonWorkspace.tsx`; `LessonPanel.tsx`; `app/session/[id]/page.tsx`
- **Behaviour.** Brief becomes sticky. Gap and attempt counters appear in the brief as disclosure triggers **in addition to** the existing inline blocks — the inline blocks are not removed yet, so nothing is lost if the frame is wrong.
- **Visual.** Sticky brief; canvas scrolls beneath it; canvas measure-capped and centred.
- **Data deps.** None new.
- **Tests.** RTL: brief renders position, title, objective, anchors, counters in every phase. Probe: brief stays fixed while the canvas scrolls.
- **Manual.** All seven states; scroll behaviour with a long reveal; `--ui-scale` at `xlarge` (the sticky brief must not eat the viewport).
- **Must NOT change.** Any block's content or availability.
- **Gate.** Brief legible and stable in all seven states at all four text sizes.
- **Commit.** 1–2.
- **Why inspect.** First real layout change to the lesson; sticky elements interact badly with the text-size dial and need eyes.

---

### L4 — Phase-driven rendering, inline actions, feedback key point 🔴🔴
- **Owns §3a.** Revisit the feedback state as a whole here, not as styling.
- **Goal.** The centrepiece. Behind `CODEONBOARD_UI=next`; legacy path untouched.
- **Files.** `LessonWorkspace.tsx`, `FeedbackCard.tsx`, `AnswerComposer.tsx`, `lessonPhase.ts`, `lib/strings.ts`
- **Behaviour.**
  - The canvas renders one primary artifact per phase; superseded artifacts become collapsed disclosures.
  - The composer is **one instance**, bound to the current phase.
  - The primary action sits **inside** the feedback card, above the explanation.
  - Exactly one primary per phase, per the verdict branch table (`ui-direction.md` §2.4).
  - Feedback leads with the key point (§2, levels 2–3).
  - **Scroll anchoring**: the feedback card holds its visual position while the setup collapses above it.
- **Visual.** The largest interaction change in the plan.
- **Data deps.** All of §3. This is where the reconciliation workarounds must be carried across deliberately.
- **Tests.** RTL, extensive: one composer per phase; one primary per phase; primary never after a long-form artifact; disclosures collapsed by default; key-point ladder at all three levels; every §3 behaviour asserted through the new path.
- **Manual.** **All seven canonical journeys (§6), flag on and flag off**, both themes. Specifically: pending-attempt path (warm-up, no refresh); retry declined keeps the verdict up; re-teach swaps the prose; pruning is reported; verification excluded from history; reveal opens on revisit.
- **Must NOT change.** Every row of §3. The legacy path must remain byte-identical with the flag off.
- **Gate.** Journeys 1–7 pass on both paths; probe shows workspace non-content chrome ≤25%; no stranded primary action in any journey (this is the evidence that decides whether Option C is ever needed).
- **Commit.** 4–6 small commits behind the flag.
- **Why inspect twice.** Highest-risk milestone. Inspect after the phase switch lands, and again after the feedback card work.

---

### L5 — Gaps and history as panels; remove the legacy path ✅ 7adf9ec
- **Shipped, and narrower than written.** The panels were not built: S3 had already
  moved the gap list and the attempt history into Understanding as collapsed
  disclosures, so a panel would have been a third location for material that had
  just found its second. What shipped is the deletion (the legacy render arm and
  `FeedbackCard.tsx`, 594 lines), the flag default inverting to `surfaces`, and the
  counter-crossing fix described in §3a. `next` is deliberately retained.
- **Goal.** Complete the model; delete the old renderer.
- **Files.** new `components/lesson/GapPanel.tsx`, `HistoryPanel.tsx`; remove legacy branches; `lib/flags.ts`
- **Behaviour.** Inline gap list and inline attempt history are removed; counters open panels. Closed gaps are retained struck-through for the session. Flag removed; `next` becomes the only path.
- **Visual.** The lesson column loses its two longest non-content blocks.
- **Data deps.** `waive`, `requestVerification` per gap; `GapDetail.status` for closed rendering.
- **Tests.** RTL: panel lists open gaps, `Set aside` calls `waive` with the right id, `Check this` enters `VERIFY` for that gap, closed gaps render struck-through.
- **Manual.** Journeys 1–7 again with the flag gone. Waive a blocking gap and confirm readiness behaves as before.
- **Must NOT change.** `waive` semantics (never evidence), blocking/non-blocking distinction, gap ordering, readiness rules.
- **Gate.** Journeys pass; no legacy code remains; worst-case workspace measured against the pre-redesign 2845px.
- **Commit.** 2–3.

---

### P3 — Generation 🔴 ✅
- **Shipped.** Three additions, all from data the backend already streams: the
  confirmed goal stays on screen through the wait (the interview used to vanish the
  instant the pipeline started); the files the exploration reads accumulate into a
  list instead of being rendered once and discarded; and past five minutes the
  elapsed line stops promising "two to four minutes". Stage rows, the real activity
  target, `calls` and the server-preferred elapsed were already in place from P2's
  work. **Deviation:** the milestone says "the interview transcript stays visible" —
  what ships is the *synthesised goal*, because `onDone` hands the page the goal and
  not the answer list, and the review gate had already shown the answers and made
  the learner confirm them. The goal is the version they agreed to.
- **Verification status.** Two real runs on `psf/requests`, both completing to the
  briefing. Goal continuity and the server-preferred elapsed line confirmed on
  screen. The files-read list is unit-tested (accumulation across polls,
  distinctness, and `read_file`-only) but its LIVE check is still outstanding: the
  in-page watcher matched `files read` case-sensitively while the label renders
  through `text-transform: uppercase`, and `innerText` returns rendered text — so a
  list that was there could not have been seen. Same class of error as the
  runtime theme flip. Folded into P4's run rather than paying for a third.
- **Goal.** The wait becomes the thing the briefing grows out of.
- **Files.** `components/StartingProgress.tsx`, `app/page.tsx`
- **Behaviour.** The interview transcript stays visible above. Bar → discrete stage rows. **Explored file paths accumulate** into a persistent list. Past five minutes the copy changes to "taking longer than usual".
- **Visual.** Per `ui-concept.md` §8.4, **reduced** — see the data note.
- **Data deps.** ✅ **Resolved (§9).** `snapshot()` returns exactly `stages`, `stage`, `done`, `activity{tool,target}`, `turn`, `calls`, `seconds`, `finished`. So:
  - **Ships in P3, no backend change:** transcript continuity; discrete stage rows from `stages`/`done`/`stage`; the real activity target; **the accumulating file list, derived client-side by collecting successive distinct `activity.target` values** (real streamed data that is currently displayed once and thrown away); `calls`; honest elapsed with the existing server-preference rule.
  - **Deferred to B2:** survey shape ("84 files · 6 modules") and chapter titles appearing before completion. **Neither is on the wire and neither will be faked.** The concept's `84 files · 6 modules` line simply does not render until B2 exists.
- **Tests.** Existing `test_pipeline_progress` must still pass. RTL: stage rows reflect `stages`/`done`; activity renders the real target; elapsed prefers `snapshot.seconds`.
- **Manual.** A **full real run** on `psf/requests`. Then a second run to confirm the cached-survey path (a stage with nothing to stream). Hide the tab for 60s and confirm elapsed stays truthful. Force a pipeline failure and confirm the failure screen still works.
- **Must NOT change.** Poll interval semantics, stage names from the backend, the never-invent-progress rule, the failure path with its retained goal for retry.
- **Gate.** Two real runs inspected; hidden-tab elapsed correct; failure path works.
- **Commit.** 1–2.
- **Why inspect.** Only observable against a real multi-minute run, and the honesty rules here are the easiest in the project to violate by accident.

---

### P4 — Briefing and the route→rail transition 🔴 ✅
- **Shipped.** `RouteOverview` renders the route at chapter granularity from the
  SAME `splitJourney` the rail uses — one source, two views, so the two cannot
  disagree about which chapter a stop belongs to once `prune_ahead` and the scope
  control start moving units. The primary names the first lesson
  (`Start: <title>`) rather than saying "Start learning". `Change` on the profile
  card starts a NEW interview for the same repository, which is what "restart with
  different answers" means — the session menu's `Start over` re-runs the pipeline
  with the same answers, the one thing a learner who dislikes their profile does not
  want. The repo rides in `?repo=` and the landing prefills without auto-submitting.
- **The shared-element transition is NOT built, deliberately.** The milestone says
  it "will look cheap if it is even slightly wrong", and doing it properly across a
  route change needs the View Transitions API to hold both DOMs at once. What ships
  is a directional exit (the page leaves toward the leading edge, where the rail is
  about to be) plus the continuity that actually mattered: the rail arrives with the
  chapter containing the first stop already expanded, because `RouteRail` opens
  `section.containsCurrent` by default. So the chapter just read about is the
  chapter landed in, whether or not anything moved. Reduced motion navigates at
  once. Recorded as deferred with a reason rather than approximated.
- **Verified live** on a 16-stop, 6-chapter session: the route lists every chapter
  with the planner's own `why` and a per-chapter count, the primary reads
  `Start: Explain the Session–adapter relationship and mounting`, and the exit
  applies `opacity: 0; translateX(-2rem)` over `--motion-state`.
- **Goal.** Confirm understanding, show the route, and enter the workspace continuously.
- **Files.** `app/session/[id]/welcome/page.tsx`, `ProfileCard.tsx`, new `components/RouteOverview.tsx`
- **Behaviour.** The briefing shows the route at chapter granularity using the same `RouteItem` primitive as the rail. Primary action names the first lesson. `✎` on the profile leads to restart-with-different-answers. On `Start`, the chapter list animates into the rail position.
- **Visual.** Column widens 560→880px; two-card layout plus the route.
- **Data deps.** `getWelcome` unchanged. **Note:** the running dev backend predates this endpoint — a current backend is required to see the success state at all.
- **Tests.** `test_briefing` must still pass. RTL: briefing failure renders the fallback and the route/`Start` remain usable; `personalized` vs `generic` label renders from the flag.
- **Manual.** Success state (needs a current backend), failure state, and a session with no areas (pre-B3 graph → ungrouped). Reduced-motion: the transition becomes a crossfade with the rail already placed.
- **Must NOT change.** Briefing independence and failure isolation; the `personalized`/`generic` labelling; the route remaining reachable from the session menu.
- **Gate.** All three data states inspected; transition verified with motion on and reduced.
- **Why inspect.** A shared-element transition is the one thing in this plan that will look cheap if it is even slightly wrong.
- **Commit.** 2.

---

### A1 — Adaptation made visible ✅
- **Shipped, and one channel was already done.** The composed consequence sentence
  is L4's `consequenceLine` — one line, ordered by how much it changed the journey,
  and already asserted to be exactly one where several adaptations coincide. So A1
  added the other two: a **session log** on the Map tab, and a **rail mark** on the
  Map tab when the route's shape changed and the learner has not looked since.
- **The log is a pure function** (`lib/sessionLog.ts`) and the component only draws.
  Two sources, as §9 Q2 resolved: `journey_events` for route shape (the four frozen
  kinds) and the gaps themselves for the gap lifecycle. Gap-opened and gap-closed
  are rendered from gap data and deliberately NOT added to `JOURNEY_EVENT_KINDS` —
  a set called frozen that grows whenever a screen wants a row is not frozen.
- **Refusals, each tested.** An unknown kind is dropped rather than rendered as
  itself (it means this client is older than the server, and a row the learner
  cannot distinguish from a bug is worse than no row). An id the graph no longer
  knows gives a null subject, never a UUID. A gap with no timestamps contributes
  nothing rather than a guessed position in the chronology. A **waived** gap is not
  reported as cleared, because waiving is a decision and never evidence — saying
  "you cleared it" would contradict `understanding_of`.
- **The rail mark counts only shape changes**, because a mark on the rail claims the
  rail looks different; a gap opening changes what is outstanding. Stored per
  session in `localStorage`, so a change announced once is not forgotten on reload,
  and cleared by looking at the Map — which is where the whole route is legible.
- **Not done:** the detour brief's persistent return affordance. The warm-up already
  labels itself in the brief and `Next stop →` returns to the stop it unblocks
  (verified in S6's J3), so what is missing is a *persistent* control rather than a
  route back. Recorded rather than added late.
- **Goal.** The three-channel grammar.
- **Files.** new `components/lesson/AdaptationNotice.tsx`, `components/SessionLog.tsx`; `RouteRail.tsx`, `FeedbackCard.tsx`
- **Behaviour.** Every adaptation produces a composed consequence sentence, a rail mark with a `new` state until the rail is viewed, and a session-log entry. Multiple simultaneous adaptations compose into **one** sentence. Detour brief gains the persistent return affordance.
- **Visual.** Per `ui-concept.md` §6.
- **Data deps.** ✅ **Resolved (§9). No backend change needed.** `journey_events` is already returned by `LearningGraph.to_dict()` and already typed in the frontend as `SessionGraph.journey_events?: JourneyEvent[]`. Two sources compose the log:
  - **Route-shape changes** from `journey_events` — exactly four kinds exist today (`prune_ahead`, `scope_shorter`, `scope_deeper`, `remediation_inserted`, frozen in `JOURNEY_EVENT_KINDS`), each carrying `nodes[]` and an optional `cause{node_id, attempt_index}`.
  - **Gap lifecycle** from `GapDetail.opened_at` / `closed_at` / `status`, which the evidence drawer already reads.
  - **Not journey events, and must not be invented as such:** gap-opened, gap-closed, verification-requested and re-teach. They are rendered from the gap/attempt data above, not by adding kinds to the frozen set. Extending `JOURNEY_EVENT_KINDS` is a learning-engine decision, out of scope here.
- **Tests.** RTL: each adaptation kind produces exactly one notice; simultaneous kinds compose; rail marks appear and clear. `test_mutator`/`test_adaptation*` unchanged.
- **Manual.** Warm-up insert→return round trip. Re-teach. Prune. Scope change. Gap open→verify→close. Confirm none feels alarming and none repeats a pulse.
- **Must NOT change.** Any mutation semantics; warm-up cap; the deliberate refresh skip; pruning honesty.
- **Gate.** All five adaptation types produce all three channels; round trip legible.
- **Commit.** 2–3.

---

### X1 — Motion and final polish ✅
- **Shipped: the reduced-motion rule stopped being a blanket.** It was
  `transition-duration: 0.01ms` on everything — the common recipe, and too broad.
  `prefers-reduced-motion` exists for vestibular discomfort, which comes from things
  travelling and resizing, not from a colour settling; and zeroing every transition
  also removed the crossfades that carry meaning here, so state changed with no
  indication that it had. Calmer would have been fine. Abrupt is not the same thing.
  The rule now names what goes (all animation, and every transition of a property
  that moves or resizes) and what stays (opacity and the colour properties, capped
  at 100ms), via `transition-property` rather than a duration override — which is
  what makes it selective: an element transitioning `opacity, transform` keeps the
  first and loses the second, and no duration override can express that.
- **`scroll-behavior: auto`** is set explicitly rather than left animated: the source
  pane scrolls when a citation is clicked, which is motion the learner asked for, so
  it still happens — it just stops travelling.
- **Probe.** 7 tests reading the stylesheet directly (a jsdom render cannot evaluate
  a media query), asserting the allowlist contains no property that moves, that
  opacity and colour survive, that the cap is ≤100ms, and that the four motion
  duration tokens exist and are ordered by how much moves. Confirmed live that the
  browser parses both rules.
- **Goal.** Apply the motion language; close the loose ends.
- **Files.** `globals.css`, most components
- **Behaviour.** None.
- **Visual.** The transitions in `ui-concept.md` §6.2; loading and empty states unified; refined `prefers-reduced-motion` (drop transform/height, keep ≤100ms opacity).
- **Tests.** Probe: with reduced-motion, no transform/height transitions remain; information is still present.
- **Manual.** Every transition with motion on and reduced. Confirm nothing loops.
- **Must NOT change.** The code pane's short-hop-only scroll rule.
- **Gate.** Full journey pass in both motion modes.
- **Commit.** 2.

---

### B1 — Optional: Grader headline *(backend, strictly after L4)*
- **Goal.** Upgrade the feedback key point from ladder level 2 to level 1.
- **Decision point, not a scheduled milestone.** **L4 must ship and be judged good with the level-2 composed key point first.** Only then do we decide whether a real corrective headline improves the experience enough to justify a Grader prompt-and-schema change. B1 **must never block L4** and is not on the critical path.
- **Files.** `backend/agents/grader/*`, `backend/api.py`, `frontend/lib/api.ts`
- **Behaviour.** The Grader returns a short corrective `headline`. Additive and optional — the UI ladder already handles its absence, so no client change is required beyond reading the field.
- **Tests.** `test_grader_agent`, `test_grader_gaps` extended; absence still renders level 2.
- **Must NOT change.** `classification`, `gap_kind` derivation, `rationale`, gap semantics, the `CODEONBOARD_GAPS` contract.
- **Gate.** Old sessions with no `headline` render identically to before.
- **Commit.** 1–2.

---

### B2 — Optional: progress facts *(backend, before or alongside P3)*
- **Goal.** Let the generation screen state real repository facts and chapter titles as they become known.
- **Files.** `backend/pipeline/progress.py`, `backend/pipeline/explorer_nodes.py`, `backend/agents/mentor/agent.py`
- **Behaviour.** Add a `facts: dict` to `_Run` plus a `fact(run_id, key, value)` setter, surfaced through `snapshot()`. `repo_survey` records file/module counts; the planner records chapter titles. Must inherit the module's existing contract: **best-effort, never able to fail a run, keys not prose.**
- **Tests.** `test_pipeline_progress` extended: facts appear in the snapshot; a raising setter cannot break a run; a snapshot with no facts is unchanged in shape.
- **Must NOT change.** Stage vocabulary or order, the no-percentage rule, the in-memory/process-local design, `MAX_RUNS` eviction.
- **Gate.** A real run shows real counts; a run with the setter removed still renders P3 correctly.
- **Commit.** 1–2.

---

## 6. Canonical journeys — the UX regression set

Seven journeys, run at every 🔴 gate and before every merge to `main`. Each gets a
row in a checklist committed at `docs/planning/phases/evidence/ux-journeys.md`, so
results accumulate rather than being re-derived.

| # | Journey | Asserts |
|---|---|---|
| **J1** | **Normal successful lesson** — arrive, read, answer correctly, advance | One primary (`Next stop`); readiness rises; stop marked settled; rail pin advances |
| **J2** | **Incorrect → feedback → retry** — wrong answer, read feedback, answer again | Key point above rationale; primary adjacent to verdict; **no stranded action**; one composer throughout; attempts accumulate correctly |
| **J3** | **Incorrect → warm-up → return** — accept the warm-up, complete it, return | Consequence sentence; rail row animates in marked; detour brief with return path; **pending attempt renders without doubling**; recovery state on return; warm-up excluded from journey progress |
| **J4** | **Gap discovered → verification → resolved** | Gap named in prose; counter increments; verification is the sole canvas artifact; **exactly one `Submit`**; on success counter decrements and the closed gap is retained struck-through |
| **J5** | **Route changes dynamically** — scope shorter/deeper, pruning, re-teach | Each reports honestly; "nothing to shorten" path works; readiness never falls because the plan changed; rail reflects the new route |
| **J6** | **Questionnaire → generation → briefing → first lesson** — a full real run | All six goal-type paths reachable; back-past-Q2 clears goal type; real stages only; artifacts persist into the briefing; route→rail transition; first lesson loads |
| **J7** | **Resume an existing session** | Lands on the server's `resume_point`; optional stops skipped; **no chapter re-introduction**; reveal open on already-answered stops; gaps and attempt counts restored |

Two negative checks accompany every journey: **no text below 4.5:1**, and **no
expanded superseded state** (one composer, disclosures collapsed).

---

## 7. Branching, commits and rollback

**Verified topology** (`git branch -avv`, `git merge-base`), not assumed:

| Fact | Consequence |
|---|---|
| `master` is at `1d78013`, tracking `origin/master`, and carries **all 137 commits** of current work | **`master` is the base.** |
| `main` is at `7b7f1b0` and is an **ancestor** of `master` — 137 behind, 0 ahead | `main` is a stale historical branch. **Nothing targets it.** |
| `origin/HEAD → origin/main` | A leftover GitHub default-branch setting, not the working default. Ignored |
| Recent history is direct commits to `master`; the 15 merge commits are older PRs from other contributors | The working model is small commits on `master`. **No new branching model is introduced.** |

- Work happens on a single branch off `master` (`ui-redesign`), so the whole redesign
  can be abandoned or rewound without touching `master` — matching the user's
  rollback requirement without inventing a `main`-based PR flow.
- **`D1`, `D2` and `D3` are authored first, as isolated self-contained commits**,
  each touching only its own concern. Because they depend on nothing from `F*`
  onward, each cherry-picks cleanly onto `master` by SHA whenever wanted.
- One commit per milestone sub-step, using the repo's existing conventional-commit
  style (`feat:` / `fix:` / `refactor:` / `docs:`, lower-case subject, no trailing
  period). Milestones with 3+ commits are split so a bad migration reverts alone.
- Every commit: `pytest tests/` green and `npm test` green. No exceptions.
- `CODEONBOARD_UI` keeps the legacy lesson renderer alive through L4, so the riskiest
  milestone is revertable by an env var rather than a code revert. It is deleted in L5
  once the journeys pass on the new path.
- Milestones are ordered so behaviour stays testable throughout: L1 adds logic without
  render, L2 moves code without changing output, L3 changes layout without changing
  content, L4 changes rendering behind a flag, L5 removes the old path. **There is no
  point at which `LessonPanel` is rewritten wholesale.**

## 8. Risk register

| Risk | Milestone | Mitigation |
|---|---|---|
| A reconciliation workaround silently deleted | L4 | §3 contract + a per-row RTL test written in L1, before any rendering changes |
| Sticky brief + `xlarge` text eats the viewport | L3 | Explicit gate at all four text-size steps |
| Prose at 16px feels sparse rather than calm | F3 | Dedicated inspection gate with option (a) 15px as the documented fallback |
| Generation screen tempted into inventing data | P3 | Contract: render only what is on the wire; a follow-up adds fields properly |
| Route→rail transition looks cheap | P4 | Inspection gate; reduced-motion path must be equally acceptable |
| Interview option strings reworded | P2 | They are parsed keys — called out in the milestone and in the gate |
| Source-pane default change breaks anchor precision | S2 | The multi-anchor scenario is an explicit manual gate |
| Frontend test tooling becomes its own project | M0 | Two narrow layers only; Playwright explicitly deferred |

## 9. Resolved from the codebase

Both data questions are answered from source, not deferred to review.

### Q1 — Does `sessionProgress` expose survey shape and planned chapters? **No.**

`backend/pipeline/progress.py::snapshot()` returns exactly:

```python
{"stages", "stage", "done", "activity": {"tool", "target"} | None,
 "turn", "calls", "seconds", "finished"}
```

`STAGES` is the fixed six-key vocabulary (`clone`, `structure`, `survey`,
`documentation`, `investigation`, `plan`). The module's own docstring states its
constraints: *"This module emits KEYS, not prose"*, a percentage *"is deliberately
not computed here"*, and it is in-memory and process-local by design.

**So:** P3 ships with the transcript, discrete stage rows, the real activity target,
a **client-derived accumulating file list** from successive `activity.target` values,
call count and honest elapsed. Survey shape and pre-completion chapter titles are
**not available and are not faked** — they wait for B2.

### Q2 — Is `journey_events` exposed on `/session/{id}`? **Yes.**

`LearningGraph.to_dict()` includes `"journey_events": self.journey_events`
(`backend/learning/graph.py:718`), commented *"Plan-scoped history. On the wire so M3
can explain a journey…"*. The frontend already declares
`SessionGraph.journey_events?: JourneyEvent[]` and a `JourneyEvent` interface with
`kind`, `at`, `nodes`, `cause`, `origin`, `unlocks`.

Four kinds exist, frozen in `JOURNEY_EVENT_KINDS`: `prune_ahead`, `scope_shorter`,
`scope_deeper`, `remediation_inserted`.

**So:** A1 needs **no backend change**. Route-shape changes come from
`journey_events`; gap lifecycle comes from `GapDetail.opened_at`/`closed_at`/`status`.
Gap-opened, gap-closed, verification and re-teach are **not** journey events and will
not be added as such — extending that frozen set is a learning-engine decision,
outside this plan.

### Still genuinely open

1. **Prose size** — start at **16px / 1.70 / 62ch** as planned. Not locked; F3's manual gate is the decision point, with 15px as the documented fallback if it reads sparse.
2. **B1 in or out** — deliberately deferred until L4 has shipped and been judged with the level-2 key point. See B1.
3. **B2 in or out** — decide when P3 is reached; P3 is designed to be correct without it.
4. **Playwright after L5?** Recommended once the journeys stop changing shape. Not scheduled.

*(The second `Key point` layer above the explanation, previously open, is now
**dropped** — see §2.)*

---

## 10. Summary of the build order

```
M0  scaffolding                     1 commit, no visual change   ✅ 4679d4e
D1  invisible surfaces        🔴    isolated + cherry-pickable   ✅ 276459c
D2  one composer                    isolated + cherry-pickable   ✅ 9ca38ca
D2b what a check reports            found in manual J4 testing   ✅ d9cc50d
D3  focus + disabled                isolated + cherry-pickable   ✅ e731f90
F1  tokens                          additive, zero visual diff   ✅ be9ff00
F2  primitives                      5 commits, gated each      ✅ ecd80ec..5333864
F3a typography + measure      🔴    ✅ 30c142a
F3b surfaces + practice well  🔴    ✅ c6d3377
F3c action hierarchy          🔴    ✅ 5446a85
F3d systematic contrast       🔴    ✅ 397a07d   ← Foundation track approved
P1  landing                    ◀── pre-session lands here, not at the end
                                    ✅ 1ceed6c
P2  interview                  ◀──  ✅ c8a9182 (motion) + 5fa2207
P2b review gate                     ✅ 0d6e946   added after using P2
S1  header                          ✅ 5f75d88  goal 110px -> 843px
S2  rail + source + responsive 🔴    ✅ 6b45da8  source now on demand
S2b Show source made visible        ✅ a50c3eb + 8343adf  asked for at S2's gate
L1  phase logic (no render)          ✅ 99d5451  four phases named
L2  extract blocks (no visual)       ✅ 2ff5a86..fdce2c3  1057 -> 540 lines
L3  Brief / Canvas frame      🔴     ✅ 6fd2ed4
L3b brief collapse + left align     ✅ 7e2dc38
L4  phase rendering + feedback 🔴🔴   ✅ 3411ec0  §3a answered
    S0 journeys on `next`, live         ✅  closed L4's own gate; 4 defects fixed
    S1..S6 two-surface model            ✅  merged to master as ec00d54
L5  panels + remove legacy             ✅  7adf9ec  legacy deleted, -594 lines
P3  generation                🔴    ✅  goal continuity + files-read list + long-wait copy
P4  briefing + route→rail     🔴    ✅  route overview + named primary + Change
A1  adaptation visible              ✅  session log + rail mark (sentence was L4)
X1  motion + polish                 ✅  reduced-motion refined + probe

optional:  B1 Grader headline (after L4)   ·   B2 progress facts (with P3)
```

Base branch: **`master`** (verified — §7). Implementation begins at M0.

### Where this stands — the plan is complete

Every milestone in §5 has shipped. `L5`, `P3`, `P4`, `A1` and `X1` closed on branch
`ui-surfaces-l5`; everything before them is on `master` as of `ec00d54`.

Three things shipped narrower than written, each for a stated reason rather than for
lack of time:

1. **`L5`'s panels** were not built — S3 had already moved the gap list and the
   history into Understanding as disclosures, so a panel would have been a third
   home for material that had just found its second.
2. **`P4`'s shared-element transition** is deferred. The milestone says it "will look
   cheap if it is even slightly wrong", and doing it properly across a route change
   needs the View Transitions API; what ships is a directional exit plus the
   continuity that actually mattered — the rail arrives with the chapter containing
   the first stop already expanded.
3. **`P3`'s "interview transcript"** is the synthesised goal, because `onDone` hands
   the page a goal and not an answer list, and the review gate had already shown the
   answers and required the learner to confirm them.

Two things are built but currently inert on real data, which is worth knowing before
either is trusted:

- **`A1`'s gap rows.** The log renders route-shape changes from `journey_events`
  (verified live: two warm-up insertions, each naming the stop it unblocks) but
  contributes no gap rows, because `NodeGap` on the node wire carries no
  `opened_at`/`closed_at` — those live on `GapDetail`, which only the evidence
  drawer fetches. The code declines to guess a position in the chronology rather
  than inventing one, and a test pins that. Putting the timestamps on the node wire
  is R9/F101 work.
- **`P3`'s files-read list** is unit-tested but its live confirmation is still
  outstanding — see the note under P3.

The optional backend items `B1` (Grader headline) and `B2` (progress facts) remain
decision points, not scheduled work, exactly as written.

### Notes from walking a real session — the seven post-plan fixes

Seven notes came out of the first manual walk of a live session after the plan
closed. All seven are done, on `ui-surfaces-l5`, verified against the running app
at `127.0.0.1:3100`. Six were the rail; one was the source pane.

| # | Note | What changed |
|---|------|--------------|
| 1 | The current stop repeated its file path | Caption removed. The path is already in the lesson header and the source pane; three copies of `requests/adapters.py` on one screen was the complaint. Measured: the current row is now 37px against 52px for a two-line neighbour. |
| 2 | The rail is too narrow | `RAIL_REM.wide` 16.75 → 19.5. Measured live at **312px**. |
| 3 | Stops are too tight; chapters do not separate; no scrolling | Stop padding `py-[calc(5rem/16)]` → `py-[calc(9rem/16)]` (measured 9px), connector re-anchored to `bottom-[calc(-11rem/16)]` to keep the line joining the new spacing, chapter gap `mt-4` → `mt-7`. The list is its own scroll region: with every chapter expanded, `clientHeight` 612 against `scrollHeight` 1064. |
| 4 | No way to hide the rail | `Hide route` / `Show route` in the session bar, hidden in the narrow band where there is no track to give back. Persisted under `codeonboard:rail-hidden` (verified `0` → `1` → `0` across toggles) and deliberately **not** in `prefs`, which is display settings the learner sets from a menu. |
| 5 | **Bug** — collapsing the chapter you are in still showed your stop | `const visible = open ? section.stops : []`. This reverses an earlier deliberate decision ("show that one stop rather than hiding where the learner is"); the note is right and the old behaviour was wrong, because the chevron said closed while a row sat there, so the control looked broken. Where you are stays legible from the marked heading and its counter. |
| 6 | Open chapters are not distinguishable from closed ones | The heading tone became three levels rather than two: `text-signal` for the chapter being read, `text-chalk` for open-but-not-current, `text-graphite` for collapsed. |
| 7 | Source pane could not be undocked or resized, and froze the page | One root cause, three symptoms — see below. |

**Note 7 was a single branch.** An "overlay" rendering forced
`source={{...source, mode: "dock"}}`, pinned the pane to a fixed `max-w-[34rem]`,
and laid a `fixed inset-0 bg-ink/70` backdrop button over the page. So undocking
did nothing (the mode was overridden), resizing did nothing (the width was fixed),
and the rest of the screen was dead (the backdrop swallowed every click). The
branch is deleted. `dock` is always a third column; `float` is the draggable,
resizable window; and `setShowCode` opens in `float` when a dock would starve the
lesson below its floor. Verified live: no viewport-spanning element with live
pointer events, `role="dialog"` with **no** `aria-modal`, both mode controls
present, and all eight resize grips (four edges, four corners).

**Both components were untested, which is why this could regress silently.**
`components/CodeViewer.test.tsx` (15 tests) and `components/RouteRail.test.tsx`
(14 tests) now cover them; the frontend suite goes 361 → 390. The rail's two
behavioural guards were mutation-tested — restoring the old
`filter(s => s.node.id === currentNodeId)` and the old file caption fails exactly
those two tests and nothing else.

#### Two instrument traps, recorded so they are not paid for a third time

- **A frozen CSS transition reads as the wrong colour.** Note 6 measured as *not
  applied*: the heading class was `text-chalk` and `getComputedStyle` returned
  graphite. The Browser pane does not composite frames, so `visibilityState` stays
  `hidden`, no animation frames run, and the `color` transition sits at
  `currentTime: 0` — the **start** value — indefinitely. `getAnimations()` showed
  one running `CSSTransition`, and with `transitionProperty: none` the same node
  read `rgb(221, 229, 234)`. Any colour probe must suppress transitions first or
  read the class. This is the same shape as the `data-theme` trap recorded in
  `evidence/s6-surfaces-journeys.md`: a measurement that looks like a product bug.
- **Pointer gestures cannot be faked from page JS.** `setPointerCapture` with a
  synthetic `pointerId` throws, which aborts the handler before the drag is
  recorded, so a resize drag silently does nothing and the width "does not change".
  `left_click_drag` needs a screenshot, which needs a displayed pane. The resize is
  therefore verified by test rather than by live gesture — and in jsdom the same
  gesture needs `MouseEvent`, because jsdom's `PointerEvent` drops
  `clientX`/`clientY` and every delta comes out `NaN`.

### How it stood at the L-track gate

Foundation (`F1`–`F3d`) is approved and closed. The pre-session front half
(`P1`, `P2`, `P2b`) has shipped and been verified against the running backend.
`S1` and `S2` have shipped. The header regression is closed (goal zone 110px ->
843px at 1280px, overflow floor 1150px -> 657px), the source pane is on demand
rather than a default, and the layout has three named bands with a 560px floor
under the reading column. The L track is next, and it is where the carried-forward
feedback information architecture (§3a) gets resolved.

Three things are carried forward rather than fixed in place, each recorded with
numbers in `evidence/ux-journeys.md`:

1. **`goal_type` is re-invented by the model** — the highest-value item
   outstanding, and a **backend correctness bug, not a UI one**.
   `agent.py` derives it deterministically from `GOAL_TYPE_MAP` and routes the
   follow-ups correctly, but the final goal JSON's `goal_type` comes from the
   Haiku synthesis call, which is never given the value already derived.
   Measured over all six paths: five came back `understand_architecture`,
   including "Use it in my own project" and "Contribute code / open a PR". Same
   class of defect `CLAUDE.md` records removing twice for `depth` and
   `experience_level`, and higher-stakes — `goal_type` selects the investigation
   strategy and decides whether the Reviewer runs. Fix mirrors how `code_depth`
   is already handled: pass it into `_synthesize_goal` instead of asking for it.
2. **Feedback information architecture** → `L1`/`L4`/`L5`, per §3a. Not to be
   solved by styling inside `F3`.
3. **The syntax palette** — two token colours in dark and three in light sit
   under 4.5 on their own, punctuation among them at ~2640 glyphs. A
   syntax-colour decision rather than a contrast tweak, so it was recorded
   rather than silently repainted. Does not block progress.

Two smaller carries: the header regression (goal text starved at 1280px) is
`S1`'s to fix, and `t.starting.elapsed` still prints "usually two to four
minutes" — the same unmeasured claim `P1` removed from the landing — which is
`P3`'s screen.
