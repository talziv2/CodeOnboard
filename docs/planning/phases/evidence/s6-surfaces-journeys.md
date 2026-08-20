# S6 — the journeys on `surfaces`, against S0's baseline

Same rig, same backend, same sessions as S0: `.ui-audit-fe` on `:3100`, backend on
`:8000` with `CODEONBOARD_GAPS=1`, sessions `a3234f41…` and `8c5a4027…`. The rig was
`diff -rq`'d against `frontend/` before measuring — byte-identical, as at S0.

The comparison S0 exists to make is the one line below.

---

## The measurement

Same stop, same state, same session. Stop 3 revisited, one prior answer, STUDY:

| | on screen at once |
|---|---|
| `next` — one column | **1747px**, three expanded (prose + question + explanation) |
| `surfaces` — Lesson | **1031px**, explanation expanded, prose collapsed beneath |
| `surfaces` — Understanding | **806px**, question expanded, setup and history collapsed |

**−54% while answering. −41% while reading.**

Lesson is not half the canvas, and the reason matters: `setupInLesson` collapses
the prose once the explanation exists, which is supersession *within a surface*.
The single column could not do it, because there the verdict was the newer thing and
the prose stepped back for that instead — so the explanation and the prose were open
together.

Stop 13 in FEEDBACK, the busiest real state in either session — three gaps, three
answers, two re-teaches:

```
Understanding   776px, 0 expanded disclosures, composer gone, verdict expanded
                collapsed: The setup · Still unresolved 3 · Your answers (3)
Lesson        1529px, 0 expanded disclosures, explanation expanded
                collapsed: Before you answer · This path crosses… · Earlier explanations (2)
```

L4's own measurement of that state on the single canvas was 1127px with the same
information. Understanding is now 776px of it, and the rest is one click away rather
than below the fold.

---

## The seven journeys

| | Journey | Result |
|---|---|---|
| J1 | answer → verdict | PASS — tab held, dot raised on Lesson, `Read it` offered |
| J2 | wrong answer, gaps open | PASS — key point keeps the frame, three actions |
| J3 | warm-up stop | PASS on the surfaces half — renders on both, arrival resets to Lesson |
| J4 | verification → resolved | PASS — `Cleared`, all three gaps closed, counter gone |
| J5 | scope, re-teach | PASS — decline reported in the menu, consequence line intact |
| J6 | fresh session, first lesson | PASS — the first-visit case, setup expanded as material |
| J7 | resume | PASS — lands on Lesson, `Earlier explanations (2)` survives the reload |

### What the live run proved that the tests could not

**R1 and R5 hold at the same time, which is the whole design.** One submit from
Understanding on stop 13: the tab stayed put through STUDY → FEEDBACK, and a dot
appeared on Lesson because the stop had been re-taught. Announced, not navigated to.

**`Read it` closes the loop.** Clicking it landed on Lesson, cleared the dot on
arrival, and the `Rewritten` notice was there — so the promise the dot made was
kept by what the learner found.

**S5's group is real, not a fixture.** `Earlier explanation (1)` was already
present on arrival, from a re-teach recorded during S0, and became `Earlier
explanations (2)` when this answer caused another. It then survived a reload, which
is what proves the marking reads the attempt history rather than live state.

**Both sides of Lesson's supersession, on real data.** Stop 13 (answered): the
explanation expanded, `Before you answer` collapsed. Stop 1 of the fresh session
(never answered): the setup expanded as plain material with no explanation to
supersede it, 566px.

---

## Negative checks: 16 configurations

2 themes × 4 text sizes × 2 surfaces, every one on stop 12's warm-up:

```
                  Lesson   Understanding
dark   small       856px      661px
dark   medium      979px      762px
dark   large      1130px      885px
dark   xlarge     1183px      910px
light  small       856px      661px
light  medium      979px      762px
light  large      1130px      885px
light  xlarge     1183px      910px
```

**Contrast failures: 0 in all sixteen.** **Expanded disclosures on arrival: 0 in all
sixteen.** Heights are theme-independent, as they should be, and scale monotonically.

### One phantom, caught and named

The first light-theme pass reported **6 failures, worst 1.65:1** on the anchor
citation. It was measurement error, and the same one that manufactured nine phantom
light failures earlier in this project: flipping `data-theme` at runtime does not
give a trustworthy reading, and the auditor's background fallback resolved to white
when every ancestor was transparent.

Re-measured the reliable way — `localStorage['codeonboard:prefs']` set to light,
then a reload — the citation is `rgb(4,89,111)` on `rgb(231,238,243)`, which is
**6.73:1**. The auditor now falls back to the page's own background rather than to
white, and the light sweep is clean.

Recording it because it is the second time this exact trap has cost a measurement,
and the fix is procedural: **theme changes go through prefs and a reload, never
through the attribute.**

---

## Closed after S6

- ~~**The brief renders inside each surface**~~ — **closed as not needed.** Both
  surfaces render into one scroll container that React reuses, so the brief is not
  remounted by a tab switch: its collapsed state survives and the scroller is the
  same DOM node either side. All three of §2's reasons are satisfied where it is,
  and lifting it would cost L3's collapse-on-scroll, which the brief only has
  because it lives inside the scrollport. The check did find a real bug, though —
  `scrollTop` carried across switches and clamped, so leaving Lesson at 500px landed
  on Understanding at 190px, below its composer. Both surfaces now start at the top.
- ~~**§4's row for collapsing the superseded question**~~ — **implemented.** The
  question-text-only node exists (`questionEcho`), so `The question you answered`
  collapses beneath the verdict and the composer still renders only while the
  question is open. Understanding stayed 776px: collapsing something changes nothing
  about the count this milestone is measured on.

## Still open

- ~~**The warm-up's transition prose names the previous stop**~~ — **fixed.** It was
  a wiring bug: `_previous_unit_section` handed Teaching the structural predecessor
  under the instruction *"the unit they just finished"*, which for a warm-up is false
  twice — the learner got stuck on the stop AFTER it, and a warm-up's position in the
  walk is an accident of where it was spliced. `_unblocks` now reads the stop off the
  `prerequisite` edge, and the system prompt carries the exception rather than a
  competing rule. Verified live: *"Now that you know how to use Session safely with
  context managers…"* became *"Understanding how prepare_auth treats any non-tuple
  callable as a valid auth handler will unblock you to build custom auth handlers…"*
- **`off-topic` leaves `understanding_state = not_started`** while an attempt is
  recorded, so the brief shows `1 answer` on a stop the system reports as never
  started. Documented as deliberate (`agents/grader/agent.py`): an off-topic answer
  is evidence of neither understanding nor misunderstanding.
- **Nothing re-assesses an objective with a fresh question.** A verification closes a
  gap without crediting the stop, and the UI now says so — but the mechanism that
  would let the stop be re-credited does not exist, and re-asking the original
  question after the explanation has been shown is the memory test §18.7 removed.
- **J3's remediation path** — insertion and decline — was exercised live on `next`
  during S0 and is untouched by the surfaces layer, which sees a warm-up as an
  ordinary stop. What was re-checked here is that it renders on both surfaces and
  that arriving at it resets the tab.
- ~~**The Shiki syntax palette**~~ — **fixed.** Five colours were below the floor
  (dark comment 3.88 and punctuation 4.38; light comment 3.67, punctuation 3.85 and
  string-punctuation 4.28). All five lifted hue-preserving, the recession ordering
  preserved in both themes, and measured on the rendered pane: **4337 tokens, 11
  distinct colours, 0 failing** in dark and in light. Pinned by
  `lib/code-theme.test.ts`, which asserts the floor *and* the ordering — because the
  cheapest way to pass a contrast floor is to flatten everything toward the
  foreground, which would pass and destroy the palette.
