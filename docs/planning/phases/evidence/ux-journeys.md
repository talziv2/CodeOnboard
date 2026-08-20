# UX regression journeys

The seven canonical learner journeys from
[`ui-implementation.md`](../ui-implementation.md) §6. Run at every 🔴 inspection
gate and before any merge. Results accumulate here rather than being re-derived,
so a regression shows up as a row that used to pass.

**How to run the probe.** Open the page, paste `scripts/ux-probe.js` into the
browser console. It measures contrast, duplicate answer inputs, ambiguous
duplicate button labels, the type-size census, radii, header fit and workspace
scroll. Two notes on trusting it:

- It disables transitions while reading. A background or non-compositing tab
  freezes transitioned values at their pre-transition state, which silently
  corrupts colour reads.
- It resolves colours through a 1×1 canvas rather than by scraping the computed
  string, because Tailwind v4 emits `oklab()` with negative components that
  digit-scraping turns into near-black — inventing failures on tinted chips that
  are actually fine.
- If the viewport reports a zero size it **skips** geometry rather than failing
  it. Colour checks remain valid in that state.

---

## Journeys

| # | Journey | What it asserts |
|---|---|---|
| **J1** | Normal successful lesson | One primary (`Next stop`); readiness rises; stop settled; rail pin advances |
| **J2** | Incorrect → feedback → retry | Key point above rationale; primary adjacent to verdict; no stranded action; one composer throughout; attempts accumulate |
| **J3** | Incorrect → warm-up → return | Consequence sentence; rail row marked; detour brief with return path; pending attempt renders without doubling; recovery state on return; warm-up excluded from journey progress |
| **J4** | Gap discovered → verification → resolved | Gap named in prose; counter increments; verification is the sole canvas artifact; exactly one `Submit`; counter decrements; closed gap retained struck-through |
| **J5** | Route changes dynamically | Scope shorter/deeper report honestly; "nothing to shorten" path works; readiness never falls because the plan changed; rail reflects the new route |
| **J6** | Questionnaire → generation → briefing → first lesson | All six goal-type paths reachable; back-past-Q2 clears goal type; real stages only; artifacts persist into the briefing; route→rail transition; first lesson loads |
| **J7** | Resume an existing session | Lands on the server's `resume_point`; optional stops skipped; no chapter re-introduction; reveal open on answered stops; gaps and attempt counts restored |

Two negative checks accompany every journey: **no text below 4.5:1**, and **no
expanded superseded state** (one composer, disclosures collapsed).

---

## Recorded runs

### M0 — 2026-08-19 · pre-redesign baseline

Session `cff533a5…` (aima-python), dark theme, stop 15 of 15 with three open gaps.
Recorded so later runs have something to regress against. Geometry figures are the
manually measured ones from [`ui-baseline.md`](../ui-baseline.md) §10, since the
inspection browser reports a zero-size viewport.

```
FAIL  contrast: 81 text runs >= 4.5:1  — 11 below
        1.97:1  11px  "Holding this stop back"      × 3   ← D1
        1.97:1  11px  "Set aside"                   × 3   ← D1
        3.61:1  10.5px "Every search call depends…"  × 4   ← D3 / F3 (rail chapter text)
        3.84:1  10px  "15–62"                              ← D3 (line range, signal-dim)
PASS  answer inputs: 1
PASS  no ambiguous duplicate button labels
PASS  distinct font sizes: 9  — 9.5 10 10.5 11 11.5 12 12.5 13 15
        9 of 9 are <=16px (band 9.5-15px)
INFO  radii: 4px×22  full×6  2px×5  segmented×2
SKIP  geometry (see ui-baseline.md §10.2–10.4 for measured figures)
```

Not visible in this snapshot but measured in `ui-baseline.md` §10.1 and reproduced
live: the **verification question at 1.00:1** and its **Submit label at 1.11:1**.
They only render once a verification has been requested, so they are the specific
thing D1's manual gate must re-check.

Known-failing at M0, expected to be fixed by:

| Finding | Milestone |
|---|---|
| Verification question 1.00:1, Submit 1.11:1 | **D1** |
| Gap card sublabel + `Set aside` 1.97:1 (1.64:1 light) | **D1** |
| Line range 3.84:1 | **D3** |
| Rail chapter text 3.61:1 | **D3** / **F3** |
| 9 of 9 type sizes ≤16px, band 9.5–15px | **F3** |
| One radius (4px×22) | **F3** |

### D1 — 2026-08-19 · gap and verification surfaces

Same session, a stop with three open gaps, then a wrong answer and a requested
verification so the verification surface actually renders.

```
FAIL  contrast: 118 text runs >= 4.5:1  — 5 below
        3.61:1  10.5px  rail chapter description  × 4     ← still D3 / F3
        3.84:1  10px   line range                        ← still D3
PASS  answer inputs: 1                                     (at this point in the flow)
PASS  no ambiguous duplicate button labels
PASS  header fits at 1280px
FAIL  header content zone 149px (>=240)                    ← S1, as predicted
INFO  workspace scroll: 2511px in 634px = 4x viewport      ← L3 / L4
```

**Cleared:** every gap-card and verification failure. Verification question
measured `rgb(221,229,234)` (chalk) where it had been `rgb(10,16,20)` on
`rgb(10,16,20)`. Light theme re-checked directly: gap card `rgb(243,248,250)` on
`rgb(231,238,243)` with dark text — a proper subtle card in both directions.

**Newly visible:** the app-wide primary button label is **4.44:1 in the light
theme** (`text-signal` on a 15% signal tint). Pre-existing and marginal, but D1
added two more instances of it by moving the verification submit onto the standard
treatment. F3's solid primary resolves it.

**Independent confirmation of two baseline numbers.** With the browser pane
fronted, geometry became readable and the probe reported a **149px** header
content zone and **4× viewport** workspace scroll — matching the 149px and 2521px
measured by hand in `ui-baseline.md` §10.2 and §10.3. Two methods, same numbers.

### D2 — 2026-08-19 · one composer

Wrong answer → `Check my understanding`, the state that previously showed two of
everything.

```
PASS  answer inputs: 1                    (was 2)
PASS  no ambiguous duplicate button labels (was FAIL: "Submit")
```

Also confirmed: focus moves to the verdict panel after grading
(`document.activeElement === verdict`).

**Not confirmed here:** the verdict scroll. The inspection browser reports
`document.hidden`, fires no animation frames, and makes `scrollTo` inert — direct
`scrollTop` assignment works, animated scrolling does not. The arithmetic and the
focus move are verified; the smooth-scroll path needs one manual check in a real
window. Recorded rather than assumed.

### D2b — 2026-08-19 · what happens after you answer a check

Found in manual testing of **J4**, which is exactly what J4 exists to catch:
*wrong answer → check → correct answer → Submit* left the learner unable to tell
whether anything had been processed.

Root cause was not a bug in either half on its own. `_respond_to_verification`
returns `classification: null` **by design** — a verification is evidence about
named beliefs, not a re-grade of the objective — and every label and action in the
panel keyed off `classification`.

Measured before, after a **correct** check answer:

```
verdict headline   ""                        ← t.lesson.verdict[null] ?? null
buttons            ["Build me a warm-up"]    ← the ONLY action, because
                                               null !== "understood" was true
learner's answer   absent                    ← cleared, and excluded from history
gaps               2 → 1                     ← the backend HAD closed one
resolved/unresolved never rendered anywhere
```

After:

```
headline           "Cleared"  in jade rgb(79,178,134)
buttons            ["Next stop →"]
WHAT THIS CLOSED   both gap claims, struck through
YOU WROTE          the learner's full answer
gaps               2 → 0
```

Verified live for the all-cleared path. The partly-cleared and nothing-closed
branches are covered by unit tests against the real reply shape rather than live,
because the session's gaps were exhausted by then — noted so it is not mistaken
for full live coverage.

No contrast regression in either theme; the new card introduces no failures.

**Design note.** The card names only what *closed*. What is still open is
deliberately not re-listed, because the gap list above is already the
authoritative and actionable copy — printing both is the accumulation this
redesign exists to remove. A closed gap is the half that is otherwise
unrecoverable, since it has left that list by the time the card renders.

### D3 — 2026-08-19 · focus and disabled, everywhere

Probe run on all four routes, both themes.

| Route | Contrast | Focus ring | Disabled |
|---|---|---|---|
| Landing | PASS | PASS 6/6 | PASS |
| Interview Q1 | PASS | PASS 6/6 | PASS |
| Interview Q2 | PASS | PASS 9/9 | PASS |
| Session · lesson | **PASS** both themes | **PASS 41/41** | PASS ≥3:1 |
| Session · map | 5 dark / 1 light remaining | **PASS 92/92** | PASS |
| Welcome | **PASS** both themes | PASS 2/2 | PASS |

Before D3 the app had **one** focus style in total — the source pane's drag
divider — and three inputs actively removed the browser's default. Now every
interactive element is covered by one root rule, with a single documented opt-out
(the divider, which fills instead; a full-height 8px handle sitting outside the
pane's bounds would have its outline half-clipped by the grid track).

Disabled measured live: `opacity: 1`, `cursor: not-allowed`, accent removed,
foreground on the new `--color-muted`. Previously `opacity: .3`–`.4` over
`graphite`, composited to roughly 1.5:1 — "absent" rather than "unavailable".

Cleared in this milestone: the rail's chapter description (3.56 dark / 2.98 light
→ 5.45 / 4.75, by dropping an alpha rather than changing the colour) and the source
pane's line range (3.84 → 9.69, `signal-dim` → `signal`, which is also the
semantically correct one since it marks the band under discussion).

**One token change.** Light `--color-signal` deepened `#056782` → `#04596f`, with
`--color-signal-halo` tracking it. Signal is used as ink **on a 15% signal tint**
— the primary button and the profile chips — and because the tint is made from
signal, foreground and background moved together, pinning that pairing at 4.44:1
on the first screen a learner sees. Only a darker signal separates them: 4.44 →
5.35 on the tint, 4.11 → 4.92 on the halo, 5.48 → 6.73 bare. This follows the
light theme's own documented rule that signal deepens rather than brightens.

**Deferred to F3, with numbers** — five items on the map's *current* stop card,
whose `signal-wash` background is lighter than `slab`:

```
4.20:1  9.5px  tag "risk"            (×2)
4.21:1  9.5px  tag "component"
4.33:1  9.5px  tag "graph-problem"
4.35:1  9.5px  status "Needs work"
```

All marginal, all on one surface, and all caused by the tag/status palette
meeting a background it was not validated against. The fix is systematic —
validate every tag and status hue against every surface it can land on — which is
F3's work, not an accessibility side-effect to be slipped in here. Light theme has
one such item left (4.17:1) after the signal change.

**Also recorded, not fixed:** the code pane's gutter line numbers measure 2.17:1
dark / 3.54:1 light. They sit inside the source pane, which `globals.css` treats
as a deliberately quieter tonal zone and which the probe excludes for that reason.
Changing them is a decision about the pane's character, so it belongs to F3.

### F1 — 2026-08-19 · token layer, zero visual diff

The gate for this milestone is that nothing changes, so it was measured rather
than asserted. `public/snapshot.txt` digests sixteen computed properties per
element — size, weight, line-height, tracking, colour, background, border, radius,
shadow, opacity, padding, margin, gap — across `main` and `header`, excluding the
source-pane code table because its DOM varies with whichever file is open.

Captured on the session route with `globals.css` at HEAD, then with F1 applied:

```
                elements   dark digest   light digest
before             274     1432160578    -429470264
after              274     1432160578    -429470264
                            identical      identical
```

The before-capture also asserts `--text-body` is absent, so the two runs are
genuinely pre- and post-F1 rather than the same state twice.

**Two things this milestone taught, both recorded in the file itself.**

Tailwind's own keys were the hazard, not the new values. `--text-xs`, `--text-sm`,
`--radius-sm` and `--radius-md` all have defaults that are in live use here —
12 × `text-sm`, 2 × `text-xs`, 68 × `rounded` (4px), 4 × `rounded-md` (6px) — so
defining the scale under those names would have silently moved existing type and
geometry. The scale is therefore role-named (`--text-micro` … `--text-display`,
`--radius-chip` … `--radius-panel`), which also reads better at the call site.

And `@theme` tree-shakes variables nothing consumes: the first attempt emitted
literally none of them, so they could not be inspected in the browser or
referenced from plain CSS. `@theme static` fixes that at the cost of a few unused
custom properties, which render nothing.

No spacing tokens were added. Tailwind already derives every step from one
`--spacing`, and the app's `gap-*` resolve off it; a second scale would just be a
way to disagree with the first. What was missing is a convention, which is
recorded as a comment beside the code that will follow it.

### F2a — 2026-08-19 · SectionLabel and ConceptTag

Two primitives, extracted at the current visual language. No typography, radius,
elevation or colour decision is pulled forward from F3.

| Route | before | after | verdict |
|---|---|---|---|
| Lesson dark | 274 · `1432160578` | 274 · `1432160578` | **identical** |
| Lesson light | 274 · `-429470264` | 274 · `-429470264` | **identical** |
| Chapter overview | 198 · `-1913074720` | 198 · `-1914201951` | 1 declared change |
| Map | 602 · `1884929408` | 603 · — | 1 declared change |

#### Intentional visual normalizations — the complete list

**1. Concept tags in the chapter overview: horizontal padding 5px → 6px.**
`SectionOverview` wrote `px-[5px]`; `LessonPanel` and `MapView` both wrote
`px-1.5` (6px). One of the three had drifted, so the chip is now 2px wider in the
overview only. Verified live: `paddingLeft` 5px before, 6px after. This is the only
pixel that moves anywhere in F2a.

#### Structural change with no visual consequence

**2. The map's journey heading gains one wrapper element.** Its copy put the label
text directly inside the `h3` with the font classes on the `h3` itself; the four
other copies wrapped the text in a span. The primitive follows the majority, so the
map's `h3` goes from one child plus a bare text node to two spans — hence 602 → 603
elements.

Measured after, against the `h3`'s own values before: font-size 10px, tracking
1.6px, colour `rgb(123,141,153)`, `text-transform: uppercase` — all unchanged,
because the properties simply moved from the `h3` to the span that now holds the
text. Layout unchanged too: the label measures 85px and the rule starts at
x=387 = 292 + 85 + the 10px flex gap, so the anonymous text item it replaced
occupied exactly the same space.

#### Not migrated, deliberately

`tagStyle` / `tagLabel` remain imported by `MapView` and `SectionOverview` because
both still use them outside chips — the by-concept breakdown rows, and the
understanding labels. `LessonPanel` no longer imports from `lib/tags` at all.

### F2b — 2026-08-19 · StatePin

| Route | before | after | verdict |
|---|---|---|---|
| Lesson (contains the rail) | 274 · `1432160578` | 274 · `1432160578` | **identical** |
| Map | 603 · `1145766918` | 603 · `1145766918` | **identical** |
| Chapter overview | 198 · `-1914201951` | 198 · `-1914201951` | **identical** |

**No normalizations. Zero pixels moved.**

Spot-checked live as well as by digest: the current pin carries
`rgba(91,200,232,0.16) 0 0 0 3px` and one child (the filled centre), non-current
pins carry neither, and border colours come through from `understandingStyle` —
rust for unresolved, jade for demonstrated, signal for current.

#### What the three copies disagreed about, preserved verbatim

`understandingStyle` was already shared — M3a.3 fixed that, after a stop could
read amber in the rail and "Needs work" on the map. The twenty lines wrapping it
were not, and they had drifted in every dimension the encoding does not cover:

| role | size | border | halo | inner dot |
|---|---|---|---|---|
| `rail` | 17px | 1.5px | 3px | yes, inset 3.5px |
| `map` | 15px | 2px | 4px | yes, inset 3px |
| `list` (chapter overview) | 13px | 1.5px | 3px | **none** |

The rail's pin being *larger* than the map's, two border widths, two halo widths,
and the chapter overview alone omitting the filled centre that marks where you are
all look like drift rather than intent — the last one arguably a bug in the
encoding, since "you are here" is shown two ways out of three.

None of it is reconciled here. That is a geometry decision and it belongs to F3.
What this milestone buys is that the values now sit in one table keyed by role, so
reconciling them later is an edit in one place rather than a hunt through three
files. `relative` is applied only to the two roles whose original had it, because
it exists to position the inner dot and the third role has no dot.

#### Not folded in, deliberately

MapView's `Pip` and EvidenceDrawer's inline dot. One is a button with its own
hover-scale behaviour, the other sits inside a text row; both are half a dozen
lines and both already read the shared encoding. Pulling them into a component
whose every difference is a parameter would be abstraction for its own sake.

### F2c — 2026-08-19 · Button

36 of 56 `<button>` elements adopt it; 20 stay outside. Split into three commits
so a bad group reverts alone, and ordered so that **any digest movement in the
first two is unambiguously a bug rather than a normalization.**

| Group | Sites | Result |
|---|---|---|
| 1 — `primary` md/lg/block, `secondary` md | 23 | **zero diff, 5 route states** |
| 2 — `chrome` sm/xs, `ghost` | 7 | **zero diff** |
| 3 — the drifted sites | 6 | exactly the 7 declared changes |

Groups 1 and 2 are zero-diff **by construction**, not only by measurement: the
migration tool rewrites a site only when its class list is an exact superset of a
variant+size pair and preserves leftovers verbatim, so for a site with no leftover
the emitted class string is a *permutation* of the original — and CSS resolves
conflicts by stylesheet order, not class order. The digests confirm what the
matching rule already guarantees.

```
lesson            274  1432160578    unchanged through groups 1 and 2
map               603  1145766918    unchanged
chapter overview  198  -1914201951   unchanged
landing            12  1759883667    unchanged — and equal to the pre-F1 baseline
welcome dark       67  -1757693035   unchanged — likewise
```

#### The complete normalization list — 6 sites, 7 property changes

Every one measured live, before and after.

| Site | Change | Verified |
|---|---|---|
| `session/[id]/page.tsx` `retryLoad` | `text-sm` 14px → **13px** | 13px, `8px/16px`, `mx-auto` kept |
| `welcome/page.tsx` `retryLoad` | `text-sm` 14px → **13px** | same combination, same markup |
| `LessonPanel` `notNow` | `px-3` → **`px-4`** | by shared combination (see below) |
| `LessonPanel` `Set aside` | 11px → **10.5px** | 10.5px, `4px/8px`, sans, `shrink-0` kept |
| `page.tsx` recents chip | `px-2.5` → **`px-2`**; 11px → **10.5px** | 10.5px, `4px/8px`, mono |
| `GoalDialogue` `Continue` | `py-2` → **`py-2.5`**; 13px → **13.5px** | 13.5px, `10px/20px`, weight 500 |

`notNow` is the one change not observed directly — reaching it needs an
outstanding verification, which costs live grading calls. It is the same
`secondary md` combination already verified rendering at 9 other sites, so its
padding follows arithmetically (`px-3` 12px → `px-4` 16px). Recorded as inferred
rather than presented as measured.

#### No additional drift found

The tool aborts a site if anything left over after subtracting the variant and
size is not a layout utility, and reports it. Across all three groups it reported
`UNRECOGNISED` only where expected — the chrome buttons refusing to be read as
ghosts — and kept exactly two layout leftovers, `mt-1` on the landing `Start` and
`shrink-0` on the header trio and `Set aside`. So the seven changes above are the
complete set.

#### The 20 controls that stay outside `Button`

Nine **clickable regions** (rail stop rows, rail chevron and section title, rail
optional toggle, trace-path steps, chapter-overview lesson rows, MapView unit rows
and journey cards, `Pip`, the file·lines link), four **segmented or icon controls**
(source pane `✕` and dock/float, settings gear and the theme/size `Choice`), two
**tab strips**, one **micro chip** (numbered evidence refs), the **interview answer
options** — which are answers, not buttons, and which P2 rewrites — and two that
resemble `ghost` but are not:

- `finishEarly` — `hover:text-chalk`, not `hover:text-signal`. Matching it would
  assert that ending the session early is *the thing to do*.
- `openMap` — base `text-signal`, not `text-graphite`. An accent link.

Both stay explicit until S1 or F3 decides otherwise.

### F2d — 2026-08-19 · Callout, and why Surface was dropped

Five tinted boxes in the lesson, one shape, three semantic tones: `signal` for
something the system wants noticed (takeaway, hint, follow-up), `jade` for
something closed or recovered, `neutral` for an aside carrying no verdict
(ownership). Only the eyebrow and the container are owned — the bodies differ
genuinely (a struck-through list of closed gaps, and paragraphs at three sizes) so
they stay as children.

Four adopt it unchanged; the fifth is isolated in its own commit.

Two confirmed live, since these boxes only render after an answer:

```
Take away      bg signal/0.06 · border signal-dim/0.4 · gap 6px · pad 12px/16px
               radius 4px · mt 4px preserved · eyebrow 9.5px rgb(91,200,232)
Yours to hold  bg slab · border rule · otherwise identical
```

#### Normalization — 1 site, 2 changes

| Site | Change | Δ |
|---|---|---|
| `recovered` | `gap-1` → `gap-1.5` | +2px internal gap |
| `recovered` | eyebrow 10px → 9.5px | −0.5px |

The only one of the five that had drifted, and neither difference carries a story:
four sites agree against one. **Declared but not observed** — this box renders only
after a learner recovers from a failed stop via a warm-up, which the test session
is not in. An A/B on identical data confirms the migration moves nothing else.

#### Surface: proposed in the plan, dropped on the evidence

Eight sites share `rounded border border-rule bg-slab`. They also sit on **five
different element types** (`details`, `div`, `li`, `aside`, `button`) and disagree
on every padding and gap — `p-4`, `p-5`, `px-3.5 py-3`, `px-3 py-2`, `px-4 py-3`,
none — while one uses `rounded-md`, one flips its background on `open`, and one is
a clickable region already excluded from `Button`.

A component emitting three classes while taking element, padding, gap and layout
as props would be barely shorter than the markup it replaces and no more
consistent — the "component whose every difference is a parameter" that this
milestone's own brief warns against.

The real argument for it is that F3 will change the card treatment in one place
instead of eight. That is an argument for a **token**, not for a component, and F3
already has `--radius-card` and `--shadow-card` waiting. Recorded here so the
reversal is visible rather than quietly dropped.

---

## F2 gate — closed

New baselines, on **restored** session data (see the note below):

```
lesson dark        226  -1352415
lesson light       226   540869114
map                569  1329943391
chapter overview   189   449407977
```

Probe, both themes:

```
PASS  contrast: 90 text runs >= 4.5:1
PASS  answer inputs: 1
PASS  no ambiguous duplicate button labels
PASS  focus ring on all 38 interactive elements
PASS  1 disabled control(s) >= 3:1
FAIL  distinct font sizes: 11   — F3 owns this
FAIL  header content zone 0px   — S1 owns this
```

Both remaining failures are the milestones' own targets, not regressions.

**A measurement caveat worth recording.** The digests earlier in this log are not
comparable across the whole of F2, because the session's *data* changed partway
through: verifying the button normalizations meant submitting real answers, which
added attempts and closed gaps. Element counts moved 274 → 348 on the lesson and
603 → 594 on the map for that reason, not from any styling change. The database has
since been restored from `data/sessions.db.uibaseline-backup` and verified back to
its original shape — current node `58766f8b`, 20 attempts, 5 nodes with gaps,
progress 7/12 — and the four numbers above are the baseline F3 should compare
against. The post-F2 mutated state is kept at `data/sessions.db.post-f2` in case a
state with more evidence is useful later.

**Lesson for later gates:** a digest gate is only valid on fixed data. Any
milestone whose verification needs live grading should re-baseline afterwards
rather than comparing across the mutation.

---

### F3a — 2026-08-19 · typography and the reading measure

First milestone that deliberately changes how the product looks, so the gate is
rendered inspection rather than a digest.

199 size usages remapped across 18 files. **22 distinct sizes → 8 tokens.** On the
lesson screen, 11 sizes → **6** (11 · 12.5 · 14 · 16 · 18 · 22); on the map, 5.
The band that was 9.5–15px is now 11–16px for body-scale text.

Explicit `leading-*` was removed wherever a token applies, since the token carries
the line-height — two exceptions preserved, the map's big fraction and its
denominator, where `leading-none` keeps the numerals optically aligned.

#### The finding that mattered: `ch` is not a character

`.measure` was `62ch`, and the concept document predicted that gave 66–70
characters per line. Rendered and measured, it gave **90**.

```
Geist at 16px:  average English character  7.29px
                the "0" glyph (= 1ch)     10.61px
                ratio                      1.45×
62ch = 658px  ->  90 characters per line
```

`ch` is the advance width of `0`, which in this typeface is 1.45× a real
character. So the cap was 45% looser than intended, and 90 CPL is well outside
the comfortable 60–75 band.

This never showed before because **the column was narrower than the cap and did
the limiting itself** — prose sat at ~62 characters by accident. Raising prose to
16px without catching this would have traded that accident for a genuinely
too-wide line the moment the source pane is closed.

Corrected to **48ch**. Measured after, with the cap binding, every prose block
lands at exactly **70 CPL** regardless of its size — which is the point of a
`ch`-based cap:

```
16px -> 509px   18px -> 573px   14px -> 446px   12.5px -> 398px      all 70 CPL
```

With the source pane open at 1129px the column still constrains it to 62 CPL —
in range, at the low end. That is S2's floor to fix, and 48ch is now also the
reason the lesson column's floor is 560px: the measure plus its padding.

**Assessment on 16px:** keep it. The earlier worry was that 16px would read
sparse; the real problem was line *length*, not size, and it was there at 13.5px
too. 16px / 1.70 / 70 CPL is textbook. The 15px fallback is not needed.

#### Regression introduced, and left for S1

The header's minimum width moved **1111px → 1150px**, because the micro-label
collapse raised its labels from 10px to 11px.

| viewport | goal text before | after |
|---|---|---|
| 1600 | 469px | 430px |
| 1440 | 309px | 270px |
| 1366 | — | 196px |
| 1280 | 149px | **110px** |
| 1200 | — | 30px |
| 1150 | — | 0px, overflow begins |

1280 and 1366 still fit. This is a modest worsening of a failure that already
existed, in a header S1 rebuilds into four zones with an overflow menu — patching
it here would be doing S1's work inside F3a. Recorded rather than absorbed.

#### Other visible changes

- Concept chips 9.5px → 11px, so chip rows are wider and slightly taller.
- The app wordmark 15px → 14px, collapsed into `aside`. It loses a little
  presence; S1 owns the header's hierarchy and can revisit.
- The lesson's question prompt 13.5px → 18px (`lede`), which is the single
  largest promotion in the step and the one most worth an opinion.
- Lesson title 23px → 22px; welcome/completion/map headings 25–27px → 28px.

#### Probe

```
lesson, both themes   PASS contrast (87 runs) · PASS focus 34/34 · PASS disabled
                      PASS distinct font sizes: 6
map                   PASS focus 68/68 · PASS distinct font sizes: 5
                      FAIL 4 tag/status items 4.20–4.35:1  → F3d owns these
both                  FAIL header  → S1 owns this
```

No contrast regression: every size change was upward, and the four map items are
the ones already deferred to F3d, unchanged in ratio and now rendering at 11px
rather than 9.5px.

**Not touched in this step, deliberately:** letter-spacing. Micro labels still
carry five different `tracking-*` values (0.05 / 0.06 / 0.13 / 0.14 / 0.16em).
That is a second axis, and folding it in would have made the size change
impossible to judge on its own.

### F3b — 2026-08-19 · surfaces, radius, elevation, and the practice surface

The focal deliverable was not the radius ladder — it was giving the question a
surface of its own, after F3a showed that 18px type distinguishes it only by
degree.

#### The practice surface

Question, verification and feedback now live inside **one persistent region**. Only
its contents and its eyebrow change. Measured across a real answer:

```
                    before submit                after submit
eyebrow             "Check your understanding"   "Feedback"
position in column  y = 1317                     y = 1398
height              466px                        352px
contents            composer + Submit            verdict + 3 actions
```

The 81px shift is the gap list above growing from one entry to three — not the
feedback appearing somewhere else. Before F3b the verdict rendered at y=2027 while
the composer sat near y=1400, on the far side of a 777px explanation.

Getting there required reordering three top-level blocks so they are contiguous:
`attempts · PRACTICE {verification | question | verdict} · reveal`. The verdict
therefore now precedes the explanation, which also retires most of D2's interim
scroll hack.

#### Surfaces, chosen by measurement rather than feel

The first attempt used `trench` for the well. Measured separation from the page:

```
                 dark    light
trench           1.023   1.091     <- invisible in dark
slab             1.110   1.095     <- also what content cards use
raise            1.227   1.282     <- reads in both
```

`raise` read correctly but broke text on it: `graphite` measures **4.05:1** on
light `raise`, and D3 had deliberately excluded `raise` when tuning `graphite` and
`muted` "on the grounds that no control is ever drawn on it". The practice surface
made that untrue, and the probe caught three consequences — `Skip this stop`,
the `⌘↵` hint, and the disabled `Submit` at 2.63:1.

**A real palette tension, recorded for F3d:** in the light theme separation and
text contrast trade off directly, because any surface distinct enough to see
against a near-white page is dark enough to hurt mid-grey text.

```
#c6d5df (raise)   separation 1.28   graphite 4.05   <- fails AA
#d0dde4           separation 1.18   graphite 4.38
#d4e0e7           separation 1.15   graphite 4.52   <- chosen
#dbe5ec (trench)  separation 1.09   graphite 4.75   <- barely visible
```

Resolved with a purpose-made `--color-well` (dark `#1a252d`, light `#d4e0e7`),
trading a little separation for text that passes, plus two follow-ons:
`SectionLabel` gained a `raised` tone (paper: 8.94 / 6.63) and light `--color-muted`
deepened `#6f838f → #6a7d88` so disabled controls clear 3:1 on the well too
(3.7 / 3.4 / 4.0 / 3.2 on ink / trench / slab / well).

Nesting confirmed live — the field steps against the well in both themes, in
opposite directions, which is inherent to a palette that swaps values:

```
dark    page 10,16,20   ->  well 26,37,45    ->  field 12,19,24
light   page 231,238,243 -> well 212,224,231 ->  field 219,229,236
```

#### Radius and elevation

The universal 4px is gone. Live census: `3px ×5` chips, `6px ×10` fields and
buttons, `10px` cards and callouts, `14px` the practice well, plus full-round pins.

Elevation is applied **selectively**, not to everything: `shadow-card` on things
that are genuinely standalone panels (the profile card, the map's panels), and
deliberately **not** on list items — gap rows, attempt cards, unit rows — because
elevating every row is the card-soup failure the brief warned about. Overlays use
`shadow-overlay`, replacing two hardcoded shadow values.

#### Probe

```
lesson, both themes   PASS contrast · focus 40/40 · disabled · 6 type sizes
                      FAIL header content zone 110px      -> S1
map                   FAIL 4 tag/status items 4.20-4.35:1 -> F3d
```

#### Not built, deliberately

**The `Read · Answer · Understand` stage indicator.** Treated as optional per the
brief: the surface, the eyebrow that changes with state, and the in-place
transition were implemented first, so the question of whether a stage indicator
adds orientation or just makes the lesson feel like a wizard can be judged against
a version that does not have one.

---

## F3d — systematic contrast cleanup

The four map items F3b deferred turned out to be the small half of this. Resolving
them properly meant computing every tag against every surface a chip actually
lands on, and then measuring the rendered page rather than the stylesheet — which
found three failures no amount of stylesheet reading could have.

### The tag × surface matrix

The deferred items were reported on one surface. Computing all eight tags against
all five surfaces (`ink`, `trench`, `slab`, `well`, `signal-wash`) found more, and
showed the deferred four were symptoms rather than the fault:

```
DARK  before   risk/signal-wash 3.92   risk/slab 4.21   component/signal-wash 4.21
               freeform/signal-wash 4.33   rust(status)/signal-wash 4.35
LIGHT before   freeform/signal-wash 4.17
```

`risk` failed on `slab` too, so `signal-wash` was not the cause. The cause is that
a chip's own translucent fill lightens the surface under its ink in dark and
darkens it in light, so the composite is always worse than the bare pairing —
`graphite` is 4.67 bare on `signal-wash` but was 4.21 inside a chip there. The
values had been validated against `ink` alone.

Fixed at the token, not the surface: `signal-wash` was left alone (collapsing its
tint to fix `risk` would have cost the "you are here" signal and still left it at
4.23). Changed instead:

```
dark   --color-rust / --tag-risk-text   #d4634f -> #e07762    worst composite 4.54
dark   --tag-component-text             #7b8d99 -> #8899a5    worst 4.71
dark   --tag-freeform-text              #7b8d99 -> #8899a5    worst 4.85
light  --tag-component-text             #445c6a -> #3f5764    worst 4.82
light  --tag-freeform-text              #4b6675 -> #3f5764    worst 5.08
```

Each chip's `-bg` rgb was moved to track its new text value, since the fill and
the ink are the same colour by convention here and my arithmetic assumed it.
`--color-graphite` was NOT retuned: bare on `signal-wash` it is 4.67 and passes.
Only the chip composites failed, so only the chip tokens moved — D3's grey tuning
stands.

Result, computed over the full matrix: **8 tags × 5 surfaces + 7 semantic inks +
the gutter, zero below 4.5 in both themes.** Weakest is `risk`/well 4.54 dark and
`graphite`/well 4.52 light.

### The code gutter, decided rather than nudged

It was 2.17 dark and 3.54 light. Quiet was the intent, but line numbers are not
decoration in this product: every citation is `file:line`, so the learner reads
them to find what the lesson refers to. That makes them content, and content
meets 4.5. Set *to* the floor rather than above it, which preserves three distinct
tiers in the pane:

```
dark    code-hot 12.49  >  code-line 6.94  >  gutter 4.53   (was 2.17)
light   code-hot 13.16  >  code-line 6.83  >  gutter 4.73   (was 3.54)
```

### Three failures only the rendered page could show

The stylesheet matrix was clean while the running app was not. Measuring computed
colour against the *composited* ancestor chain, with ancestor `opacity` folded in:

**1. The hot gutter number — 3.87 dark.** Raising the cold gutter to 4.53 left
`signal-dim` on the tinted hot row *below* it: the line under discussion had the
least legible number in the pane. Now `signal` — 8.62 dark, 5.56 light.

**2. The rail's finished rows — 3.93 dark, 3.28 light.** `tone === "done"` carried
`opacity-80`, which made them the worst text in the rail, and the fade was the
entire cause. It was also the third signal for one fact: the pin already encodes
state and the title is already `graphite` where a live stop is `paper`. Removed;
done rows are 5.45 / 4.75 and still plainly quieter than a live row.

**3. The `.code-cold` veil — the largest single defect in the app.** It carried
`opacity: 0.82` (0.9 light), and its own note in `globals.css` claimed cold code
held ~5.7:1 dark and ~5:1 light. That had measured `--color-code-line`, the colour
a token inherits *only* when the grammar gave it none. Against the palette that
actually renders:

```
dark   cold tokens  11 colours, 4 below 4.5  (4059 of 8040 glyphs)
       worst 2.99 comments (3.88 unveiled) · 3.34 punctuation ×2640 (4.38 unveiled)
light  cold tokens  11 colours, 5 below 4.5  (4326 of 8040 glyphs)
       worst 3.13 comments (3.67 unveiled) · 3.28 punctuation ×2640 (3.85 unveiled)
```

Light had no headroom for a fade at all — its tightest *passing* token is 4.75
unveiled, so any veil pushes it under. The fade is removed and the class dropped
from the markup. The band is now carried by four devices, none subtractive,
measured on a real stop:

```
row tint vs pane                 1.122
2px inset rule                   full signal
gutter number vs cold gutter     2.138
code-hot vs code-line            1.799
```

### What remains, and why it is not fixed here

The syntax palette itself is below floor for two colours in dark and three in
light, independent of the veil:

```
dark    comments    #60757f  3.88   ×309     punctuation #6b7d88  4.38  ×2640
light   comments    #5b7887  3.67   ×309     punctuation #5a7484  3.85  ×2640
        strings     #2b7566  4.28   ×484
```

Punctuation is the most common token in the pane, so this is ~3000 glyphs dark and
~3500 light. It is a **syntax-colour decision, not a contrast tweak** — the values
come from Shiki's dual-theme output, and overriding them means choosing different
token colours, which changes how code reads. Recorded rather than silently
repainted. Open question for the next visual gate.

### Probe — four views, both themes, after the fixes

```
                        UI CHROME below 4.5      SYNTAX TOKENS below 4.5
lesson      dark        0                        4 combos / 3010 nodes
lesson      light       0                        8 combos / 3519 nodes
map overlay dark        0                        0
map overlay light       0                        0
welcome     dark        0                        0
welcome     light       0                        0
landing     dark        0                        0
landing     light       0                        0
```

Every remaining failure is a syntax token. All UI chrome passes in both themes.

### Two measurement traps, recorded so they are not re-hit

**Flipping `data-theme` from the console does not re-resolve utilities under
`next dev`.** Doing so reported 9 light "chrome failures" showing *dark* token
values on light surfaces — `text-paper` was not matching at all and the element
was inheriting. `--color-paper` read correctly as `#2c4653` on the very same
element, which is what made it look like a product bug. The theme must be switched
the way the app switches it: set `localStorage['codeonboard:prefs']` to
`{"theme":"light"}` and reload, so the boot script applies it before paint. Re-run
that way, light chrome is clean.

**`bg-signal/[0.07]` computes to `oklab(... / 0.07)`.** Scraping it with a numeric
regex yields the oklab components as if they were sRGB and reports the hot row as
*darker* than the pane (1.009 separation, i.e. "the band is invisible"). Composite
it through a 1×1 canvas instead — the same trap the earlier probe work hit, in a
new place.

---

## P1 — Landing

Four changes, one of which is a correction to the plan's own copy.

### The expectation line, and the number it does not contain

`ui-concept.md` §8.2 proposed *"Five short questions, then two to four minutes
while we read the repository."* The plan already rejected the minutes as
unmeasured. Checking `questions.py` showed the other half was wrong too:

```
CORE_QUESTIONS                                     5
+ follow-up, use_library / understand_system /
  understand_component / understand_architecture /
  contribute_code                                 +1  -> 6 total
+ follow-ups, improve_existing_system              +2  -> 7 total
+ follow-ups, debug_issue                          +2  -> 7 total
```

So a learner answers **six or seven**, never five, and which one is not known
until Q2 is answered. "Five short questions" would have been an invented number of
exactly the kind the rest of the product refuses — worse than vague, because it is
specific and false. Shipped copy:

> Six or seven short questions, then a few minutes while we read the repository —
> longer for large ones.

The question span is honest and the wait is described by its shape. Two tests pin
this: one rejects any digit-or-word plus a time unit anywhere in the landing copy,
the other rejects the phrase "five questions" specifically and requires the
six-or-seven span.

### Vertical placement, measured rather than chosen

`justify-center` centres inside the *padded* box, so bottom padding is the dial.
The first guess moved the centre from 50% to 46% — too small to read as
deliberate. Simulated across viewport heights before committing to a value:

```
pb        720px      900px      640px     content fits
16vh      46.4%      45.6%      47.0%     yes
24vh      42.4%      41.6%      43.0%     yes
28vh      40.4%      39.6%      41.0%     yes   <- chosen
```

Rendered result: **41.8%** in both themes at 1280x720, page does not scroll.
Applied to the `repo` step only — the interview, progress and failure states are
taller, and pushing those up would crowd them. Verified: with the interview
showing, padding is back to a symmetric 64px and the page still does not scroll.

### Order

The concept's sketch puts the expectation *below* the action, and recents below
that. Rendered order now matches:

```
LABEL "Repository to read" | INPUT | BUTTON "Start" | P expectation | DIV recents
```

A returning user looks for recents; a new one should not have to step over them to
reach the button.

### The mark

A filled 8px square turned 45° above the wordmark — the one piece of ornament in
the product, and a geometric primitive rather than a picture. Left inline in
`page.tsx`: the concept plans it beside the wordmark in the session header too,
and extracting a primitive before that second call site exists would be the
speculative kind. Note for whoever measures it next: Tailwind v4 `rotate-45` sets
the `rotate` property, not `transform`, so `getComputedStyle().transform` reads
`none` — check `.rotate`, or the 11.3px (8·√2) bounding box.

### Gate

```
                                    dark    light
error text on the landing           6.37    5.42     (real backend, unreachable repo)
tagline / label / expectation       5.57    5.18
Start (ink on signal)               9.91    6.73
wordmark                           15.01   14.39
below 4.5                              0       0
content centre                      41.8%   41.8%
```

Verified live: unreachable repository returns a mapped sentence rather than a raw
slug; a recents chip fills the field and clears a standing error; a valid
repository still advances to the interview. The server-down path was seen
incidentally earlier in this session — the audit copy without its proxy env
rendered *"Couldn't reach the server. Check the backend…"* at 6.37 — and is
covered by test in both themes rather than re-verified by stopping the backend.

Tests: 10 new in `app/page.test.tsx`; suite 44 passed, typecheck clean.

### Not changed

`checkRepo` validation, recents persistence and the `errorText` slug mapping are
untouched, per the milestone's must-not-change list. One thing noticed and left
alone: `t.home.serverUnreachable` ("Couldn't reach the server.") and
`t.errors.server_unreachable` (the same thing plus how to fix it) are two strings
for one condition, and which one appears depends on whether the thrown value was
an `Error`. Recorded, not merged — it is copy consolidation, not P1's job.

---

## P2 — Interview

### What changed

The interview was one question at a time with no record of the rest, so `Back` was
the only way to check an earlier answer — and checking it meant leaving the
question you were on. Now:

- **`components/goal/OptionList.tsx`** — full-width 44px rows, driven by the
  keyboard. Choosing and confirming are separate: click selects and nothing else,
  arrow keys move the selection, Enter confirms. Semantics are a radio group rather
  than a listbox, because exactly one answer is possible and arrow keys should both
  move and select. Selection is carried by a filled-versus-hollow dot as well as by
  colour, so it survives a monochrome reading.
- **`components/goal/AnswerTranscript.tsx`** — answered questions collapse into an
  editable list. `Change` steps back through `/goal/back` once per question; there
  is no new endpoint and no new backend field.
- **The tick bar is gone**, replaced by "Question N of M" as text plus the
  transcript. Declared change: the ticks said the same thing as the counter, while
  the transcript says it more usefully — it shows what the answers *were*.
- **`Back` is tertiary** (`ghost`), not an outline. The transcript's `Change` is the
  specific way back; this is the general one, and it should not carry Continue's
  weight.

### Why Change loops instead of jumping

`goalBack` un-answers exactly one question, and the backend owns what that *means*:
crossing question 2 clears `goal_type`, which is what makes the follow-ups
recompute. A client that jumped straight to question 2 would leave the server
believing in a goal type the user had abandoned, and the interview would finish
with answers to questions that no longer applied. So stepping from question 4 to
question 1 is three sequential calls. Verified live below.

### The gate — all six goal-type paths

Driven against the real backend at the API level rather than through the UI:
completing an interview in the UI hands off to `sessionStart`, and six pipeline
runs is real money and six sessions for no extra coverage of the thing under test.

```
goal type selected at Q2                questions   total       final goal_type
Use it in my own project                    6        6           understand_architecture  X
Understand the architecture ...             6        6           understand_architecture  ok
Improve or extend the codebase safely       7        6 -> 7      understand_architecture  X
Contribute code / open a PR                 6        6           understand_architecture  X
Debug an issue I'm hitting                  7        6 -> 7      debug_issue              ok
Understand how it works (reading/...)       6        6           understand_architecture  X
```

All six complete. The counts are **6, 6, 7, 6, 7, 6** — which is the independent
confirmation of P1's copy, and `total` honestly moves 6 to 7 for exactly the two
types with a second follow-up.

The right-hand column is a **backend defect found by this walk, not fixed here** —
see below.

### The gate — back past question 2, live

From question 4 of 7 (having chosen "Debug an issue I'm hitting"), pressing
`Change` on the first transcript entry:

```
before                Question 4 of 7, transcript = 3 entries
change controls       3, labelled "Change your answer to: How familiar..." etc.
after                 Question 1 of 6      <- total reverted, so goal_type was cleared
restored selection    "Starting fresh — never looked at it"   (the original answer)
transcript            0 entries, section gone
Back                  absent again on Q1
focus                 landed on the restored option
goalBack calls        3
```

The 7 to 6 revert is the observable proof that the server cleared `goal_type` on the
way past question 2 — the thing the loop exists to preserve.

### The gate — keyboard only

Verified live to question 2 (focus lands on the first option on arrival, ArrowDown
selects without advancing, Enter advances, transcript appears, `Back` appears), and
end-to-end in tests: ArrowDown+Enter, then ArrowUp+Enter, then typed free text and
Enter completes the interview and calls `onDone`.

### Contrast — every interview state, both themes

```
                                    dark    light
question prompt / options           10.97   8.50
selected option (signal on 15%)      7.61   5.32
Continue (ink on signal)             9.91   6.73
progress text / key hint             5.57   5.18
transcript: question, Change         5.57   5.18
below 4.5, all four states              0       0
option rows                         44px, full width, both themes
```

States measured: no selection, selection made, and transcript present.

### The motion, and why it animates position only

`rise` moves each question up 8px on arrival. It **does not touch opacity**, and
that is the point. A fade has to start from `opacity: 0`, which makes the content
invisible until the animation runs — and while an animation is in its active phase
it owns the property regardless of `animation-fill-mode`, so there is no fill-mode
setting that makes a stalled fade safe. First written with `both`, then with no
fill mode, and measured both times: in this pane the animation sits at
`currentTime: 0` indefinitely and the entire question rendered at `opacity: 0`.
Animating only `translateY` makes the worst case "the question is 8px low".

Note the honest limitation: this environment cannot show the animation *playing*,
only its start and end states. What was verified is that a stalled animation leaves
the content readable.

### Two more measurement traps

**A stalled animation poisons computed styles for its whole subtree.** Inside
`div.rise`, Continue reported `background: transparent` and `color: muted` — an
exact match for the `:disabled` treatment — while `button.disabled` was `false` and
`matches(":disabled")` was `false`. It looked like a real styling bug for several
rounds. What settled it: cloning the same button with the same classes onto `body`
rendered it correctly. The fix for measurement is to freeze animations as well as
transitions before reading — the earlier probes only froze transitions.

**A dev server serves partial CSS if the page loads while Tailwind is compiling.**
After clearing `.next` and restarting, the first page load got a sheet with 78
rules; re-fetching the same href with `cache: "reload"` returned the full 49,698
bytes containing every missing utility. The symptom is identical to "this class does
not work". Check the loaded sheet against the served file before believing a styling
failure.

### Not changed

The five core questions and their order, the option strings (they are parsed keys),
the backend's rejection of out-of-vocabulary answers, and `goalBack`'s ownership of
goal-type clearing. One test pins that a rejected answer never enters the
transcript, because the vocabulary check lives on the server.

Tests: 13 new in `components/GoalDialogue.test.tsx`; suite 57 passed, typecheck
clean, production build succeeds.

---

## Found while doing P1/P2 — recorded, not fixed

Three things outside the milestone that should not be silently absorbed.

### 1. goal_type is re-invented by the model after being determined in Python

**Severity: high.** `backend/agents/goal/agent.py:150` sets
`session.goal_type = GOAL_TYPE_MAP[chosen]` from the user's own selection, and that
value correctly routes the follow-up questions — the 7-question paths above prove
it. But the final goal JSON's `goal_type` is produced by the Haiku synthesis call,
which is given the raw Q&A text and a list of permitted values, and is **not given
the value already derived**. Measured: five of six goal types came back as
`understand_architecture`, including "Use it in my own project" (should be
`use_library`) and "Contribute code / open a PR" (should be `contribute_code`).

This is the pattern `CLAUDE.md` records having already removed twice: `depth` "was
previously invented by Haiku from answers that never mentioned it", and
`experience_level` "was the same kind of invention and has been removed". Note the
contrast inside the same function — `code_depth` *is* passed into
`_synthesize_goal` as a parameter, `goal_type` is not.

It matters more than either of those did: `goal_type` selects the investigation
strategy and decides whether the Reviewer runs. Suggested fix, matching how
`code_depth` is already handled: pass `session.goal_type` into `_synthesize_goal`
and set it on the result rather than asking the model for it.

Not fixed here because P2's must-not-change list explicitly protects the backend's
goal logic, and this wants its own change with its own tests.

### 2. The generation screen still promises "two to four minutes"

`t.starting.elapsed` renders "{n}s elapsed · usually two to four minutes". The
elapsed seconds are real; the estimate is the exact unmeasured claim P1 removed from
the landing, one screen later in the same flow. It belongs to **P3**, which owns the
generation screen — flagged so P3 does not have to rediscover it.

### 3. A next build in frontend/ broke the dev server on :3000

Running `npx next build` while a `next dev` was serving the same `.next` left :3000
returning HTTP 500. The build output itself is correct. Restarting that dev server
clears it. This is the same class of collision the `.ui-audit-fe` copy exists to
avoid — the lesson is that the copy has to be used for *builds* too, not just for
serving.

---

## P2b — the review gate, and three bugs found by using it

Three changes asked for after using P2, plus what they turned up.

### 1. A selection you had not confirmed was lost by going back

Reported. Reproduced, then fixed. Choosing an option put it in `answer` and nowhere
else; the server was never told, so stepping back and coming forward again cleared
it. The learner had made a decision and the interview forgot it.

Answers are now retained per question in a `drafts` ref, keyed on the question's
**text** rather than its index — index 6 is a different question depending on the
goal type, so keying on position would drop the previous follow-up's answer into a
new follow-up and put words in the learner's mouth. A test pins exactly that: a
draft recorded against one follow-up must not reappear on another.

A ref rather than state, because nothing renders from it and reading it inside an
async submit or a multi-step unwind must not see a stale closure.

Verified live: after unwinding six questions from the review, walking forward again
needed only Enter at each step — every question came back pre-filled.

### 2. The answers are no longer shown during the interview

They were beside every live question, which turned each question into a re-read of
everything already said. The transcript now appears only on the review step.

### 3. The last answer no longer starts anything

Answering the final question used to hand straight off to the pipeline. It now opens
a gate: the answers are shown back, and `onDone` fires only when the learner starts.
Everything downstream is decided by these answers and the next thing that happens is
a multi-minute run, so a wrong answer was expensive to discover.

Two ways backwards, deliberately. `Back` reopens the last question — what someone
who just mistyped wants. `Change` on a row goes to that specific answer — what
someone scanning the summary wants, without stepping through everything between.
Both run through the same `/goal/back` unwinding, so the server's rule about
clearing the goal type applies either way.

The call count is derived from what the SERVER holds, which differs by position:
mid-interview the current question is unanswered (`index - 1` answers), on the review
every question is answered (`index`). So reopening the last question from the review
is one call, reopening question 1 from a six-question review is six, and
mid-interview at question 4 it is three — the case verified by hand in P2.

### The backend change this required

`/goal/answer` did `del sessions[body.session_id]` the moment the goal was
synthesised. The dialogue was disposable because the client always started the
pipeline immediately. With a gate in front of that, every `Back` and `Change` on the
review returned **404 session_not_found**.

The delete is gone. Retention is bounded instead — insertion order is dict order, so
dialogues past `_MAX_GOAL_SESSIONS` (64) are evicted oldest-first. A `GoalSession` is
a repo URL, a few answers and a goal type, so the cap is about not leaking
indefinitely rather than memory pressure; there is no "the learner closed the tab"
signal to free them on.

Four backend tests added: a finished dialogue survives and hands back its last
question, unwinding from a finished dialogue walks 7 down to 1 and then refuses with
`at_first_question`, the store stays at the cap, and the oldest entry is the one
evicted.

### The dead end that made visible, and how it now behaves

Restarting the backend mid-interview wiped the in-memory dialogues, and the review
step became a dead end: answers on screen, `Change` returning "That session no longer
exists", no way forward but redoing the interview. The retention cap makes the same
state reachable without a restart.

It is not fatal, and the fix is to say so. `/session/start` needs only the goal, which
the client is already holding at the review step, so **starting still works** — it is
only editing that is lost. On `session_not_found` the gate now stays usable, the ways
backwards are **removed** rather than left to fail again (a disabled button still says
"this is a thing you could do"), and the message says what is still possible:

> These answers can no longer be changed — the interview behind them has expired. You
> can still start with them as they are, or reload to answer again.

Mid-interview the same failure gets a different sentence, because there is no goal yet
and there is nothing to do but begin again. Four tests cover both.

### Verified live, on a fresh interview

```
answers shown during the interview            no, at all 6 questions
review reached after the last answer          yes, session not started
summary rows                                  6, every question with its answer
a one-character answer renders                yes ("x" in row 3)
Change on row 1 from the review               6 goalBack calls -> Question 1 of 6,
                                              original answer restored, answers
                                              hidden again, no error
walking forward again                          Enter alone at every step (drafts)
```

Contrast on the review step, both themes, zero below 4.5:

```
                                dark    light
"Let's start" (ink on signal)   9.91    6.73
headings / answers              8.50+   8.50+
eyebrow, note, question text    5.57    5.18
```

### Note on cost

Reopening the last question from the review and re-confirming it runs the goal
synthesis again — one extra Haiku call per correction. Cheap, but it is a real call
and not obvious from the UI, so it is written down here and in `GoalDialogue`.

### One thing that was not a bug

Free-text rows in the reported screenshot rendered as a single small glyph. Checked
by driving a fresh interview with a one-character answer: it renders correctly. The
glyph was the short input itself, not a display fault.

Frontend suite 68 passed; backend `pytest tests/` 14 failed / 1280 passed — the same
14 pre-existing `test_mentor_dossier.py` failures as the standing baseline, no new
ones. Note `pytest` with no path collects the cloned demo repos under `data/repos/`
and dies with 578 collection errors; the documented command is `pytest tests/`.

---

## S1 — Header

### The starvation, measured before

Nine children in one flex row, at 1280px:

```
identity   82px
context   110px   <- 84 characters of "repo · goal · depth"
demonstrated 258px
stops taken  127px
scope        253px
hide source   93px
briefing      74px
start over    86px
settings      28px
```

The controls took **919px**; the goal — the one thing that says what this session
is *for* — got 110px. At 1024px the context zone measured **0px** and the header
overflowed; the floor was **1150px**. `flex-1 min-w-0` means "take what is left",
and with seven controls ahead of it there was nothing left.

### Four zones, and a floor instead of a truncation tweak

```
identity │ context ─────────── │ progress │ controls
shrink-0 │ flex-1, min-w-15rem │ shrink-0 │ shrink-0
```

The fix is `min-w-[15rem]` on context — a width it can no longer be pushed below —
paid for by moving four control widths behind one 28px `⋯`. Measured after:

```
width   context zone   truncated   header overflows
1600px       1163px       no            no
1280px        843px       no            no
1150px        713px       no            no
1024px        587px       yes           no
 960px        523px       yes           no
 700px        263px       yes           no
 640px        240px       yes           YES  <- floor
```

Goal at 1280: **110px → 843px**, and the full 84-character goal now fits without
truncating at all down to 1150px. Floor: **1150px → 657px**. Below that the zone
holds its 240px and the header overflows instead of collapsing the goal to
nothing, which is the behaviour worth having at a width nobody uses.

### What moved, and what deliberately did not

Into the `⋯` menu: **scope** (shorter/deeper, with its live stop count and its
result note), **Briefing**, **Start over**, **Finish session**. Ordered by
consequence, quietest first. Only `Finish session` is confirmed, and the
confirmation says what survives rather than asking "are you sure" — the real
question is whether the work already done is lost, and it is not.

`Hide source` is gone from the header. The pane already owned its own close
(`aria-label="Hide source"` on its `✕`), so a header copy was a second control for
the same thing. `Show source` appears in the menu **only while the pane is
closed** — without that half, closing the pane would be one-way whenever the
lesson has no citation to click. Verified as a round trip: the pane closes by its
own control, the menu then offers `Show source`, using it restores the pane and
closes the menu, and with the pane open the item is gone again.

`Finish session early` at the foot of the lesson is **kept**. The header item is
the same action reached from the session level; the in-lesson one is reached in
context, at the end of a lesson, which is a different moment and a different
question. Restructuring the lesson's own affordances is L-track work.

### The state that had to move

`done` lived inside `LessonPanel`, which meant only a lesson could end the
journey. It is now `finished` on the page, because two things end it: the walk
running out, and the menu. `LessonPanel`'s old `onFinish` (leave to the landing)
became `onLeave`, and `onFinish` now means "end the journey" — one prop per idea
rather than one name for two.

### Gate

```
menu holds all four actions                      yes (12 unit tests + live)
Finish requires confirmation                     yes, and backing out is clean
scope round-trip                                 "Make it shorter" -> honest
                                                 "Everything left is required",
                                                 count unchanged at 15
both progress measures, both grammars            7/12 (58%) "7 of 12 required
                                                 objectives demonstrated"
                                                 15/15   "15 of 15 stops taken"
labels collapse, numbers never                   display:none -> block on
                                                 hover/focus-within; both
                                                 fractions keyboard-reachable
goal zone >= 240px at 1024px                     587px
no overflow >= 960px                             none
contrast, header + menu + confirm, both themes   0 below 4.5
```

Frontend suite 80 passed (12 new in `SessionMenu.test.tsx`), typecheck clean.

### Note

The two progress numbers keep their `title` sentences, which is what carries the
measure for anyone who never hovers or tabs — the labels collapsing is a density
decision, not a decision to hide what the numbers mean.

---

## S2 — Rail, source pane default, responsive bands

### The source pane is no longer a default

`showCode` started `true`, so every session opened with a file beside it whether
or not the lesson had sent anyone there — roughly a third of the width spent on
something nobody had asked for. It now opens **on a citation click**, and its
state is a persisted preference rather than page state: the learner who works
with code beside them keeps it, the learner who does not never sees it.

`SourcePrefs` gains `open: boolean`, default `false`. Migration is by
construction — `readSource` already resolves each field independently, and the
new one is read as `s.open === true`, so an older prefs blob (or a corrupt one)
resolves to closed rather than to `undefined`. Verified against a real stored
preference: the key appears alongside `mode`, `dockWidth` and `float`, and
survives a reload in both directions (closed stayed closed; a stored `true`
reopened the pane on load).

### Three bands

```
wide    >= 1180   full rail (16.75rem), source docked
medium  >=  960   rail collapses to a 3.5rem icon strip, source still docked
narrow   <  960   both become overlays; the lesson has the whole window
```

Measured, with the source open:

```
viewport   rail    lesson   source    rail form      source form
1440px     268px   1172px   —         full           closed by default
1180px     268px    572px   340px     full           docked   <- tightest case
1100px      56px    704px   340px     icon strip     docked
1024px      56px    628px   340px     icon strip     docked
 900px       —      900px   544px     overlay        sheet
```

The 1180px row is the tightest the layout gets: 268 + 572 + 340 = 1180 exactly,
and 572 clears the 560px lesson floor by 12px. Below 1180 the rail collapses
first, which is what buys the lesson its room back — 704px at 1100.

### Why the floor rule is a pure function

`sourceMustOverlay(band, viewportWidth, dockWidthRem, rootFontPx)` decides from
the inputs, never from the lesson's measured width. Measuring the lesson and
reacting to it is the obvious implementation and it oscillates: pane pops out,
lesson grows past the floor, pane docks again, lesson shrinks. Nine unit tests
cover the boundaries, the dragged-wide pane pushing itself out at a width that
was fine, the collapsed rail buying room the full rail did not, the text-size
dial moving the thresholds (the columns are in `rem`), and the stability property
stated directly.

### The rail

**Compact strip** in the medium band: one pin per stop in order, each carrying
the stop's title and state as its accessible name and tooltip, chapters divided
by a rule rather than a heading — at 56px a heading is a truncated word. Its own
control opens the map.

**Overlay** in the narrow band, opened from a `Your route` control in the tab
strip. It is the *full* rail, not the strip, with a backdrop; jumping closes it,
because the thing it navigates to is underneath it. Verified: opens at 272px,
backdrop present, closes on jump.

**Chapter `why` removed** from the rail. Two clamped lines under every section
heading was the largest block of prose there, and it repeated text the chapter
overview already opens with. It is a tooltip on the section title here and a
paragraph there — the same information at the density each surface is for.
Nothing is lost: `SectionOverview` already rendered `area.why`, and the rail's
title button is what opens it.

### Anchor precision — the scenario that had to keep working

Verified live at 1440px on a multi-anchor unit. Clicking *Step 2 of 4 —
`GraphProblem`, lines 1179–1215* opened the pane, added the third grid track, and
highlighted **exactly 1179–1215** — the anchor's range, not the node's display
range. That is the `viewingRange` guard, and it is now pinned by three tests:
each step opens its own file at its own lines, a step never falls back to the
node's range, and clicking the same step twice fires twice so `focusKey` can
still re-scroll.

### Gate

```
all four bands inspected                 yes — 1440 / 1180 / 1100 / 1024 / 900
lesson >= 560px at every band            yes, tightest 572px at 1180
rail obeys the band rules                full / strip / overlay, all confirmed
source obeys the band rules              docked / docked / sheet, all confirmed
citation opens the right file AND lines  yes, 1179–1215 on step 2 of 4
same anchor twice still asks twice       yes (focusKey preserved)
prefs migrate without error              yes, both directions
contrast, whole page, both themes        0 chrome failures (9832 nodes)
```

Frontend suite 92 passed — 9 new for the band rules, 3 for anchor precision.

### A measurement trap, recorded

**`resize_window` does not fire a `resize` event.** It sets the viewport through
the devtools metrics override, so `window.innerWidth` reports the new width
immediately while every React listener still holds the old one. The first
medium-band reading showed a full 268px rail and a 492px lesson — an apparent
failure of the whole band system — and dispatching `new Event('resize')` by hand
produced the correct 56 / 704 / 340 straight away. A real window drag fires the
event normally, so this is instrumentation only; probes that resize must dispatch
it before reading.

### Not changed

`focusKey` semantics, the `highlightForOpenFile` file guard, `viewingRange`
behaviour, dock/float persistence and the short-hop-only smooth scroll rule are
all untouched. The overlay sheet forces `mode: "dock"` for its render only — a
floating window inside a full-width overlay is two ways of being out of flow at
once — and does not write that back to the stored preference.

---

## S2b — `Show source` becomes a visible control

Requested after inspecting S2: opening the source should not be behind the
overflow menu. Agreed, and for the reason given — lessons cite code throughout,
the pane now starts closed, so the way to open it has to be findable without
already knowing the menu holds it. It was also the wrong category: everything else
in that menu is session management (scope, briefing, start over, finish), while
opening the code beside a lesson is part of reading the lesson.

### Where it went, and why not the header

The brief said "upper lesson/session bar". Measured both candidates at 1280px
before choosing:

```
                     available space        cost of a ~109px control
session header       0px — fully allocated  goal 844px -> ~735px, and S1's
                     (goal is what is left  overflow floor 657px -> ~766px
                      after the other three)
lesson bar           829px empty            none
```

The header has no slack by construction: its context zone is `flex-1` with a
240px floor, so anything added there comes straight off the goal — the exact
metric S1 existed to fix. The lesson bar had 829px doing nothing, sits directly
above the prose that does the citing, and its right edge is the edge the pane
opens against. So the control is right-aligned there.

### Behaviour

- Visible whenever the pane is closed, on the lesson tab, with a file to show.
- **No `Hide` counterpart.** The pane owns its own close, and this disappears
  while the pane is open.
- Removed from the `⋯` menu entirely — one control per action, not two. The menu
  is back to exactly four session actions.
- Citation → source is untouched.

### Verified live

```
pane closed        Show source visible, 93px, right-aligned in the lesson bar
click it           pane opens, tracks 268 / 672 / 340, control disappears
pane's own close   control returns
menu contents      Make it shorter | Go deeper | Briefing | Start over |
                   Finish session          (no Show source, no Hide source)
citation           "search.py · lines 1006–1058" -> pane opens, highlights
                   exactly 1006–1058, control hidden while open
```

### The header-width check S1 earned

```
viewport   goal zone   header overflows   Show source   lesson bar overflows
1280px       844px          no              visible          no
1180px       744px          no              visible          no
1100px       664px          no              visible          no
 900px       464px          no              visible          no   (beside "Your route")
 700px       264px          no              visible          no   (353px of 700 used)
```

Goal zone at 1280 is 844px — the same as before this change, because the control
costs the header nothing. S1's 657px overflow floor is unchanged: at 700px the
lesson bar is using 353 of 700 and the header still does not overflow. In the
narrow band `Show source` and `Your route` coexist in the same bar without
crowding it.

Contrast: 5.57 dark, 5.18 light, both clear of 4.5.

Sized `sm` rather than `xs` — 93x29px instead of 84x25px — because `xs` read as
cramped beside the 37px tabs. Stepped through the `Button` primitive's own scale
rather than padded with a `className`: the primitive's note says wanting different
padding is the signal to use a different size, and Tailwind resolves conflicting
utilities by stylesheet order rather than class order, so an appended `px-4` would
have been a coin toss against the size's own `px-2`. The bar does not grow — its
37px height is set by the tabs — and at 700px the strip uses 362 of 699 with no
overflow.

### One pre-existing observation, not introduced here

The control's border measures 1.47 against the bar. That is `--color-rule`, which
every `chrome` button in the app uses, and the token was tuned as a *divider*
rather than as a control outline — so the same figure applies to the `⋯` button
and every other bordered control, and has since F2. The text carries the control
at 5.57 / 5.18 and the button sits among same-size siblings in the same bar, so it
reads as a peer control. Raising `--color-rule` as a component boundary would
touch every bordered control in the app and belongs in a deliberate pass, not in
this adjustment.

---

## L1 — The phase model

### Why a phase at all

§3a counted the feedback state rather than describing it: sixteen independent
conditional sub-blocks in one branch, eleven `<Button>` call sites of which one to
four render at once, twenty-one distinct copy strings, and around them the setup
prose, the trace path, the gap list, the attempt history and the reveal with two
callouts. Restyling cannot reduce a count of sixteen. What makes it reducible is
noticing that presentation is keyed off many independent flags rather than off one
state — the same failure D2b exposed at a smaller scale, where a working backend
produced a silent UI because two flags disagreed about who was rendering.

### Four phases, and the collapse

```
STUDY     nothing graded on screen — fresh arrival AND revisit
FEEDBACK  an assessment verdict is on screen
VERIFY    a verification question is outstanding and unanswered
RESOLVED  a verification has come back
```

The branch table asserts every situation the plan enumerates, and the finding is
in the rows that agree: `understood`, `partial` with gaps, `partial` without gaps,
`confused` with a warm-up inserted, `confused` with one declined, re-taught,
pruned, waived, off-topic and the pending-attempt path are **ten rows and one
phase**. Those variants are content within a state, not states.

`RESOLVED` is kept separate from `FEEDBACK` on purpose. A check arrives as
`result`, so a model that only asked "is there a result" would render the verdict
branch — which is silent, because the backend returns `classification: null` on a
check by design. That is exactly the D2b bug, and a test asserts the phase is not
`FEEDBACK` there.

Reveal is deliberately NOT folded in: a revisit has attempts and no result, so it
is `STUDY` with the reveal already open. Reveal is orthogonal to phase.

### The signature

`result` and `verification` are typed `unknown`, which is honest rather than lazy.
`{ kind?: string | null }` is a weak type, so TypeScript rejects any literal
without `kind` — which is every assessment, the common case — and adding an index
signature to fix that then rejects `RespondResult`, because interfaces are not
assignable to indexed types. The module reads one optional field off an opaque
reply, and the parameter now says so.

### Zero visual diff

Three substantive lines in `LessonPanel.tsx`: the import, the computed value, and
`data-lesson-phase` on the root. Nothing renders from the phase yet — L4 is where
rendering keys off it. The attribute is the one rendered addition, declared: it is
how the agreement is asserted, since reading the phase off the DOM is the only way
to catch the derivation drifting from the render rather than testing the pure
function against itself.

```
lib/lessonPhase.test.ts        24 tests — the branch table
LessonPanel.test.tsx (added)    5 tests — STUDY / FEEDBACK / VERIFY / RESOLVED
                                          each asserting the phase AND the blocks
suite                          119 passed, typecheck clean
```

The agreement tests check the phase against what is on screen: STUDY has one
composer and no verdict, FEEDBACK has the verdict and no composer, VERIFY has the
question and still exactly one composer, RESOLVED reports without being mistaken
for a re-grade.

---

## L2 — The blocks become components

Ten components moved out of `LessonPanel`, in four commits, by relocating markup
rather than rewriting it. 133 tests passed throughout with no existing assertion
changed, which is the check that "moved" is true.

```
LessonPanel.tsx      1057 -> 540 lines   (JSX: 130)
LessonBrief            55   SetupProse       29   TracePath        47
GapList                58   AttemptHistory  102   AnswerComposer   67
VerificationBlock      59   RevealBlock      48   CompletionScreen 115
FeedbackCard          311
lib/verdict.ts         —    the verdict colours and FAILED, shared
```

### Not reaching the ~250-line target, and why

The plan's target assumed the file was mostly JSX. It was not: of the remaining
540 lines, 60 are imports and **350 are the state machine** — three effects, six
async handlers and the derivations. Only 130 lines are markup, and every block in
it is now a named component.

Turning that state machine into a hook is a rewrite, not a move, and it is exactly
what L4's phase-driven rendering will restructure. Doing it here would have
obscured that diff for no gain, so it was not done.

### Where the knowledge went

Each component's doc carries the rule that block exists to protect, so the next
person reads it where the code is rather than in a plan:

- `AnswerComposer` — the single-composer invariant, and that it shares `answer`
  state with `VerificationBlock`, which is why rendering both put two mirrored
  textareas under two Submits that did different things (D2).
- `VerificationBlock` — nothing sent, nothing revealed (§18.7); `Not now` clears
  the verification rather than cancelling into a two-composer state; its reply
  carries `classification: null`, which is why it lands in RESOLVED.
- `TracePath` — each step hands over ITS file and ITS range, because before
  `viewingRange` step 2 of a flow opened the right file at the node's range.
- `AttemptHistory` / `GapList` — both render what they are handed and know none of
  the assembly rules (the verification filter, the `pending` synthesis, the
  gap-source preference), which stay in the panel where the sharp edges are.
- `FeedbackCard` — the two scars: a check is not a re-grade, and "Try again" is
  not offered while a gap is open.

`FeedbackCard` takes **nineteen props**. That is not a design; it is the same
finding as sixteen conditionals, stated a second way. Its doc carries §3a's five
questions so L4 finds them at the code.

---

## L3 — The Brief / Canvas frame

### What it is

`LessonWorkspace` pins the brief and lets the canvas scroll under it. `sticky`
inside the existing scrollport rather than a second scroll container — two nested
scrollers is what made the source pane's `scrollIntoView` and `offsetTop` both
lie, and one scrollport with a pinned child has neither problem.

The brief now carries the four things worth keeping on screen: position, title,
**objective**, and counters. The objective is the point of the change — it is the
standard the answer is marked against, and being at the top of a long column it
scrolled away first.

### Two measured corrections

**The sticky brief pinned 24px too low, and content scrolled through the gap.**
With a plain `top-0` it pinned at y=110 while the scrollport top was 86, leaving a
transparent 24px strip; padding does not clip, so canvas content really was
visible above the pinned header. The cause is that Chrome resolves sticky offsets
against the scroll container's **content** box, so `top: 0` means "24px down"
whenever the container has top padding. Fixed with `-top-6` to move the pin plus
`-mt-6 pt-6` to extend the box over the strip. Verified pinned flush at 86 at
scroll positions 0, 400, 1200 and the bottom, with the title on screen at all of
them.

**The counters did not scroll anywhere.** `scrollIntoView({behavior:"smooth"})`
moved nothing — it needs an animation frame loop — and no alignment option can
know that part of the scrollport is covered by a pinned header, so even
`block:"center"` would have been wrong. Replaced with rect arithmetic that
subtracts the brief's real height, read at call time so the text-size dial cannot
stale it, and carrying the same short-hop-only smooth rule the source pane uses
(a rule that is on §3's must-not-change list). Verified through the
reduced-motion path, which is instant and therefore measurable here: both
counters land their block 12px below the pinned brief, which is exactly the
clearance set.

### Nothing was removed

The counters are triggers, not replacements: the gap list and attempt history are
still inline exactly where they were, and the counters scroll to them. That is
deliberate — if the frame is wrong, nothing has been lost, and L4 is where the
inline copies give way. §3a's questions 3 and 5 (should gaps collapse to a counter
when a verdict lands; is history ever wanted during feedback) stay open.

### Measurements

```
lesson column 1171px at 1440 viewport
canvas         736px, centred, 182px margins either side
brief pins at  86px = the scrollport top, at every scroll position

brief height vs the lesson viewport, all four text sizes:
  small    167px / 822px   20.3%
  medium   184px / 814px   22.6%
  large    207px / 803px   25.7%
  xlarge   229px / 793px   28.8%

brief rows at medium: position 19 · title 37 · objective 47 · anchors 21 ·
                      tags 23 · padding 36
```

The objective is clamped to two lines at every size, which is what stops it being
the row that grows.

### The open question for the gate

**28.8% of the reading area at `xlarge` is the number to judge.** On a 900px-tall
window that is 229px of 793px; on a 768px laptop the same brief would be about a
third of the column. The plan flagged this milestone for inspection precisely
because "sticky elements interact badly with the text-size dial", so it is put
forward rather than decided unilaterally.

If it reads as too heavy, the fix that costs no content is to collapse the brief
once it is pinned — position and title only while scrolled, the full brief when
at the top. That is a scroll listener and a second layout state, which is why it
is not in L3 on spec.

Tests: 138 passing — 14 block smoke tests, 5 brief-across-phases tests, and the
existing 119 unchanged.

---

## L3b — three adjustments from the manual inspection

### 1. The brief collapses once it is pinned

The full brief is right at the top of a lesson and too much standing rent for the
whole scroll. It now keeps what orients while scrolled — position, title, and the
counters, which are navigation — and gives back the objective, the anchor list and
the tags, which are read once before starting. Returning to the top restores it.

Measured with transitions frozen, at all four text sizes:

```
size      expanded   collapsed   saved    % of lesson viewport
small       176px       94px      82px    21.4%  ->  11.4%
medium      194px      104px      90px    23.8%  ->  12.8%
large       218px      117px     101px    27.1%  ->  14.6%
xlarge      241px      129px     112px    30.4%  ->  16.3%
```

At `xlarge` the pinned brief roughly halves, from 30.4% of the reading area to
16.3%. Title and both counters survive at every size; the objective goes to zero
height and is `aria-hidden` while collapsed, so a screen reader does not read a
region the sighted user cannot see.

The animation is on `grid-template-rows`, `1fr` to `0fr`, with F3's
`--motion-layout` and `--ease-emphasis`. No measurement and no layout read, and —
the reason for choosing it — **a stalled transition holds its STARTING value**, so
an environment that never animates leaves the brief expanded rather than leaving
content present-but-invisible. That is the failure direction to want, and it is
the same trap the `rise` keyframe hit by animating opacity from zero.

Note the expanded brief grew slightly (184px → 194px at medium): the counters are
bordered controls now, which is change 3.

### 2. The canvas is left-aligned, not centred

`mx-auto` removed. The cap stays at 46rem, because the reason for it stands —
prose at 48ch inside a 1170px column leaves the cards around it sprawling to twice
the width of the text they belong to. The brief's content is capped to the same
46rem so the two share a left edge, verified: canvas left 296px, brief content
left 296px, column left 296px.

### 3. The counters are controls

`chrome` buttons at `xs` rather than bare coloured text, which did not read as
clickable. `chrome` specifically, so they stay session furniture and do not
compete with the lesson's own primary action: 1px border, 6px radius, 25px tall,
11px mono. The unresolved one keeps a rust dot, because `chrome`'s text is
`graphite` and trading away every trace of "something is open" for the sake of
variant consistency would be the wrong trade.

Contrast 5.18 light and 5.57 dark, both clear of 4.5. The dot is `aria-hidden`.

### Verified across the bands

```
band            column   canvas   left edges aligned   pins flush   collapse saves
wide   1440px    1171px    736px          yes             yes           90px
medium 1100px    1043px    736px          yes             yes           90px
narrow  900px     899px    736px          yes             yes           90px
```

Counters present and the position row does not wrap at 900px.

### A measurement note

Setting `scrollTop` programmatically does **not** fire a scroll event in this
pane, so the collapse appeared not to work at all until the event was dispatched
by hand — the listener was correct the whole time. And because a stalled
transition freezes at its start, the collapsed height is only measurable with
transitions frozen. Two more instances of the same underlying gap: no frame loop.
Real scrolling in a real browser fires the event and runs the transition.

Tests: 143 passing, six new — expanded carries everything, collapsed keeps
position/title/counters and hides the rest from assistive tech, the region is not
hidden while expanded, the counters are buttons with a border treatment, and a
counter with nothing to report is absent rather than zero.

---

## L4 — Phase-driven rendering, and §3a answered

Behind `NEXT_PUBLIC_CODEONBOARD_UI=next`. The legacy path is in the else branch and
verified untouched.

### The answer, in one sentence

The canvas shows **one primary artifact per phase, and everything that phase has
superseded collapses to a disclosure.** Superseded is not gone: every block stays
reachable, which is what makes the decision safe to be wrong about.

### §3a's five questions

1. **After a correct answer?** The verdict with its key point, the rationale, and
   the explanation — the explanation because it is the payoff for answering, and
   withholding it at the one moment it is earned would be perverse. Not the setup
   prose, not the trace path, not the history.
2. **Adaptation notices — feedback or A1's channel?** Feedback, but as **one**
   consequence line. `retaught`, `pruned` and three warm-up outcomes were five
   conditional lines that could stack, all describing the same event from different
   angles. Ordered by how much they changed the journey; the first that applies is
   the only one said. Nothing is lost by choosing — a re-taught stop shows its new
   prose, a pruned journey is shorter in the rail, an inserted warm-up appears in
   the route.
3. **Gaps during feedback?** Collapsed to the brief's counter, because the key point
   already leads with the blocking gap's claim. They stay **open in STUDY**, where
   they are not superseded — they are what the learner is answering about.
4. **`takeaway` and `ownership`?** They travel with the explanation. The second
   `Key point` above the reveal stays dropped: two places to feel finished is the
   shallow-skipping risk this design exists to avoid.
5. **History during feedback?** No. A record is consulted, not read. Collapsed in
   every phase, counted in the brief.

### Measured, live, same stop and same answer on both paths

The grading call was stubbed in the page so the real components could be driven into
`FEEDBACK` without a model call — the Anthropic credits are exhausted, and stubbing
the network exercises more of the real thing than a test render does anyway.

```
                          legacy (:3000)      next (:3100)
canvas height                 1565px             1127px      -28%
primaries in the action row        2                  1
actions in the row                 3                  3
blocks stacked in the card         4                  varies by content
non-content chrome                 —              14.7%      gate: <= 25%
```

The two primaries in legacy are the finding, not a detail: `Next stop →` and `Check
my understanding` were **both** solid, so the row said nothing about what to do — and
one of the two was moving on while a gap was still open. The same three actions on
the next path are `Check my understanding` (primary), `Next stop →` (secondary),
`Build me a warm-up` (tertiary), which is exactly §2.4's "Partial, gaps open" row.

### What FEEDBACK looks like now, verified in the browser

```
phase                       FEEDBACK
disclosures, all closed     "Before you answer" · "Still unresolved 1" · "Your answers (1)"
composer                    gone
key point                   "Partly there — you're working from: a connected graph
                             cannot return None"
rationale                   still shown, never collapsed
hint                        shown
primaries                   1
actions                     Check my understanding | Next stop → | Build me a warm-up
verdict before reveal       yes
```

The three disclosures are precisely the blocks that used to sit open around the
verdict.

### The key point ladder

Three levels, best available first, each tested with the levels above it removed so
the fallback is known to be reachable rather than theoretical:

1. `headline` from the Grader — read defensively, so **L4 does not block on B1** and
   B1 needs no frontend change when it lands.
2. Composed from the leading gap — blocking first, since a blocking gap is by
   definition the one standing between the learner and the objective. Framed as an
   assumption the learner is *carrying*, not as a correction nothing computed.
3. The verdict word alone, for sessions with no gaps on the wire.

The rationale sits immediately beneath and is **never collapsed**. The key point
orients; it does not substitute, which is the guard against shallow skipping.

### The action table as a pure function

Six rows plus the check path, so `feedbackActions` is a pure function with a test per
row and an exhaustive sweep over all 320 input combinations. The sweep earned its
keep twice:

- **`next` became primary with a gap still open**, by falling through the tail. The
  no-route-available case is now reached explicitly and offers the warm-up, or
  moving on when there is genuinely nothing more direct.
- **The check path offered a warm-up without consulting the gate at all** — the
  exact "never offer what would be declined" contract. Fixed by giving the module
  one honest gate, `warmUpAvailable`, computed by the panel as
  `canRequestWarmUp || (isCheck && !warmUpInserted)`; on a check the panel's own flag
  is false by construction while a warm-up is still deliberately reachable while
  something is unresolved.

Invariants asserted across every combination: exactly one primary, no action offered
twice, at most three actions, a warm-up never offered after one was declined, and
**moving on is primary only when the objective is met**.

### The contract, carried across deliberately

Every row of §3 that touches this path was preserved and, where it is observable,
asserted:

- **Pending attempt.** Verified as a test that the just-graded rationale appears
  **twice** on the `mutation.kind === "prerequisite"` path — once in the card, once
  in the collapsed history — because the graph refresh is deliberately skipped there
  so the verdict stays readable, and the answer is synthesised into the history to
  compensate. A test asserting "appears once" would have looked more correct and
  broken the contract.
- **Retry declined.** The verdict stays up, the outcome is reported
  ("No warm-up could be built for this."), routes forward remain reachable, and the
  warm-up is never offered again.
- **Warm-up cap and §18.11.** Encoded in `warmUpAvailable`, never re-derived.
- **A check is not a re-grade.** `isCheck` drives the plan; `classification` is null
  there by design and is never inferred from.
- **"Try again" is not offered while a gap is open.** `feedbackActions` returns
  `check` instead — a new question about the same misconception rather than a re-ask
  of the one the reveal just answered (§18.7).
- **Reveal on revisit.** Still open with no result on screen; tested.
- **Verification excluded from history.** Unchanged; the learner's own words are
  shown in the card because they would otherwise be nowhere.
- **Re-teach and pruning** are both still reported, now inside the one consequence
  line.

### Both paths, side by side

`"Your answers"` renders as a `<summary>` on :3100 and a `<span>` on :3000 — the
disclosure wrapper is the next path's, and its absence is the legacy path's. That is
the cheap check that the flag is doing what it claims.

Tests: **207 passing.** 12 for the view model, 19 for the action table including the
320-combination sweep, 14 for the key point and consequence line, and 19 render-level
tests on the next path.

### Not done, and why

- **Scroll anchoring** as its own mechanism. The existing verdict scroll already
  lands the card at a third of the scrollport, measured clear of the pinned brief
  (271px vs 104px), and the setup collapsing above it makes the card's position
  *more* stable rather than less. Adding a second mechanism would be two things
  fighting over the same scrollTop.
- **`Review` as the secondary on the understood row.** §2.4 lists it; there is no
  handler for it and the reveal is already open directly below. Recorded rather than
  invented.
- **The seven canonical journeys** end-to-end on live data, both flags. Blocked on
  the exhausted API credits: answering, grading and re-teaching all need the model.
  The stub covers the render and the transitions; it cannot prove the backend
  contract end to end.
