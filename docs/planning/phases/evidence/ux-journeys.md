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
