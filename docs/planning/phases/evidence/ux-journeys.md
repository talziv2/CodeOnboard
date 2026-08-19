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
