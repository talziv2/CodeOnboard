# UI/UX Baseline — What the Frontend Is Today

> **Status:** analysis only. No production code, styling, copy or component changed.
> **Scope:** `frontend/` as it stands on `master` at commit `087dece`, plus the
> uncommitted welcome / briefing / progress work in the working tree.
> **Purpose:** an accurate description of the current UI/UX, to be used as the
> input to a subsequent document that defines a modern UI/UX *direction*.
> **Last updated:** 2026-08-19
> **Validated:** §1–§8 were written from the source. [§10](#10-live-validation)
> records a second pass against the **running application** and supersedes any
> earlier claim it contradicts. Numbers in §10 are measured, not estimated.

This document deliberately does **not** propose a redesign. It records what
exists, why it exists where the code says why, and where it is inconsistent.
Sections 1–8 are derived from reading the implementation; §10 corrects and
sharpens them against the real rendered product.

---

## 0. The shape of the thing

Four routes, twelve components, nine library modules, ~6,000 lines.

```
/                          → repo input → goal interview → pipeline progress → (redirect)
/session/[id]/welcome      → briefing paragraph + learner profile card
/session/[id]              → the learning session (rail + lesson/map + source pane)
```

There is no completion route: completion is a state *inside* `LessonPanel`,
which swaps its whole subtree for `CompletionScreen`.

---

## 1. Current visual language

### 1.1 The design system, such as it is

Tailwind v4 with **no `tailwind.config`** and **no component library**. The
entire design system is ~40 CSS custom properties in an `@theme` block in
[globals.css](../../../frontend/app/globals.css), consumed as ordinary Tailwind colour
utilities (`bg-slab`, `text-chalk`, `border-rule`).

This is the single best architectural decision in the frontend. A theme is a
*value swap*, not a second set of class names — no component branches on the
theme anywhere in the codebase. Three themes (dark / light / system) and four
text sizes work without a single conditional in a component.

### 1.2 Colour and surfaces

A named, semantic, non-generic palette described in-file as a "cold survey
instrument":

| Role | Tokens | Notes |
|---|---|---|
| Surfaces (dark→light) | `ink` → `trench` → `slab` → `raise` | `ink` is the page, `trench` the rail and source pane, `slab` cards and header |
| Structure | `rule` | 1px borders — the primary structural device in the whole app |
| Text (bright→dim) | `chalk` → `paper` → `graphite` | `graphite` carries nearly all metadata |
| Accent | `signal`, `signal-dim`, `signal-halo`, `signal-wash` | **One** accent, reserved for "you are here" and primary action |
| Semantic | `jade` (understood), `brass` (partial), `rust` (failed / error) | Never used decoratively |
| Code pane | `code-gutter`, `code-line`, `code-hot` | Deliberately quieter than prose |
| Tags | 8 tag families × 3 properties each | One fixed hue per concept kind |

The light theme is not an inversion and not white — it is a "blueprint paper"
re-point of the same variables, with contrast ratios documented in comments
against the *darkest* surface each colour lands on. This is more disciplined
than most production apps.

**Assessment:** the palette is a genuine asset. It is cold and instrument-like
by intent, and it is *legible*. What makes the app feel dated is not the hues —
it is that colour is the only expressive axis in use. There is no elevation, no
depth, no material, almost no shadow, and effectively one radius.

### 1.3 Typography and hierarchy

Three families:

- **Geist Sans** — body prose
- **Geist Mono** — labels, filenames, counts, timestamps, ranges, chips
- **`--font-display`** (system serif stack: Georgia / Iowan Old Style) — every heading

The serif display face against a cold technical palette is a real, distinctive
identity choice. It reads as "field notebook", and it works.

The **type scale does not exist as a scale.** Every size is a one-off arbitrary
value written `text-[calc(13.5rem/16)]`. Measured across the app, the distinct
sizes in use are:

```
9.5  10  10.5  11  11.5  12  12.5  13  13.5  14  14.5  15  16  17  21  22  23  25  26  27  30  38
```

Twenty-two sizes, many separated by half a point, with no names and no rule for
which to pick. The `calc(N rem/16)` form is a good idea — it keeps the design
number readable in the markup while staying relative, so the text-size dial and
the browser's own font setting both reach it. But there is no token layer above
it, so "caption" is `10rem/16` in one file and `10.5rem/16` in the next.

The dominant hierarchy device is a **mono, uppercase, wide-tracked micro-label**
(`font-mono text-[10rem/16] uppercase tracking-[0.16em] text-graphite`) above a
block, often paired with a hairline rule filling the remaining width. It exists
as `SectionLabel` in `LessonPanel`, and is then re-implemented inline — not
imported — in `SectionOverview` (3×), the welcome page (1×) and `MapView` (1×).
Same design, five copies.

**This device is used for almost every level of hierarchy**, which is why the
lesson column is hard to scan: `SETUP`, `TRACE PATH`, `OPEN GAPS`,
`CHECK UNDERSTANDING`, `REVEAL` and `YOUR ANSWERS` all present at identical
visual weight, so nothing tells the reader which of six sections wants their
attention *now*.

### 1.4 Cards, panels, borders, shadows, spacing, radii

- **Borders do all the work.** `border border-rule` is the app's only container
  treatment. Cards, panels, inputs, buttons, chips, the header, the rail, the
  drawer, the tab strip — all 1px `rule`.
- **Radii are effectively single-valued.** 56 uses of bare `rounded` (4px), 16
  `rounded-full` (pins and bars), 4 `rounded-md`, 5 `rounded-[2px]` (tag chips),
  two one-off `rounded-s/e-[3px]` on a segmented control. There is no small /
  medium / large radius language; there is 4px and circles.
- **Shadows: two, in the entire application.** Both on overlays (the settings
  popover, the floating source pane). Nothing else has any elevation at all.
- **Spacing** is flex + `gap-*`, chosen per instance (`gap-1` through `gap-9`,
  plus arbitrary `gap-[2px]`). No rhythm rule: section gaps are `gap-6` in
  `LessonPanel`, `gap-7` in `SectionOverview`, `gap-9` on the welcome page.

The combination — 1px hairlines, one small radius, no elevation, no fills — is
precisely what produces the "dated and rigid" impression. It reads as a
wireframe rendered in colour: every box is the same box.

### 1.5 Buttons and interactive controls

There is **no `Button` component**. Two variants exist and are pasted inline
roughly thirty times:

```
primary    rounded border border-signal-dim bg-signal/15 px-4 py-2 text-[13rem/16]
           font-medium text-signal transition hover:bg-signal/25 disabled:opacity-40

secondary  rounded border border-rule px-4 py-2 text-[13rem/16] text-graphite
           transition hover:border-signal-dim hover:text-signal disabled:opacity-40
```

Padding drifts by instance (`px-2 py-1`, `px-2.5 py-1`, `px-3 py-1.5`,
`px-4 py-2`, `px-5 py-2.5`, `py-3`), and the "primary" is never actually solid —
it is a 15%-alpha tint. The app therefore has **no visually dominant action
anywhere**; the strongest CTA on any screen is a tinted outline sitting at the
same weight as a chip.

One control breaks the vocabulary entirely — the verification submit button is
`bg-signal text-paper`, the only solid-filled button in the app (see §5.1).

Inputs and textareas are `bg-trench` + `border-rule`, with `focus:outline-none`
replaced by `focus:border-signal-dim` — a very quiet focus signal. **Buttons have
no focus-visible styling at all**; only the source-pane divider defines one. So
keyboard navigation falls back to the browser default ring, unstyled against
this palette.

### 1.6 Icons

Hand-rolled inline SVG, six total: `Chevron` (defined twice — once in
`LessonPanel`, once in `RouteRail`), `Check`, `GearIcon`, `DockIcon`,
`FloatIcon`. Plus two text glyphs used as icons: `✓` in `StartingProgress` and
`✕` as the source-pane close button.

The same "done" concept is a text `✓` on one screen and an SVG `<Check/>` on
another; the same chevron is two components. There is no icon system and no
consistent stroke weight (`1.3`, `1.5`, `2` all appear).

### 1.7 Navigation

There is no global navigation, no breadcrumb, and no back affordance except the
browser's.

- **Session header** — a single non-wrapping row carrying nine distinct groups
  (see §5.3, I1).
- **Tab strip** — `LESSON` | `MAP`, underline style, mono uppercase. A second,
  visually similar strip (`SUMMARY` | `MAP`) exists inside `CompletionScreen`
  with slightly different sizing and padding.
- **Route rail** — the left column, the primary way to move between stops.
- Cross-links: header → `/welcome`, rail → map tab, map / overview → jump to stop.

`/welcome` is reachable from the session header but has no link back — its own
header carries only the wordmark, the repo name and settings, so the only routes
out are `Begin` and browser back.

### 1.8 Sidebars and rails

`RouteRail` (16.75rem, fixed) is the strongest-designed component in the app and
carries an explicit doc comment stating its restraint rules: it answers four
questions and no more, and concept tags, line ranges and the state legend were
*deliberately removed* because "density was the problem".

It renders sections (collapsible — the chevron collapses, the title opens the
chapter overview), stops as timeline rows with a connector line and a state pin,
and a collapsed "optional stops" bucket. Tone is three-level: `current` (bold,
signal), `ahead` (paper), `done` (graphite at 80% opacity).

The state pin encoding — stroke colour + fill treatment + **border style** — is
shared through `understandingStyle()` across the rail, the section overview, the
map and the evidence drawer. Four classes distinguishable without colour
(`insufficient` is dashed specifically so it differs from `unresolved` by shape).
This is the most rigorous piece of visual design in the project.

`EvidenceDrawer` is a second sidebar (26rem, right, map tab only) that takes
layout space rather than overlaying — it squeezes the map when open.

### 1.9 Progress indicators

**Six different visual grammars for progress**, across five screens:

| Where | Form |
|---|---|
| Goal interview | Row of equal-width tick segments, filled left to right |
| Pipeline start | Thin bar (completed stages) + checklist with per-stage state dots + elapsed counter |
| Session header | Gradient-filled bar + `7/15 (47%)` fraction |
| Session header | `journey` as a bare text count |
| Rail section heads | `1/3` tabular numerals |
| Map headline | Large display-serif fraction + a discrete **track of stop ticks** |
| Map breakdowns | `StateStrip` — proportional stacked bar of the state mix |

Two of these diverge *on purpose*, and the reasoning is sound and documented in
the code: goal readiness is a fraction of mastery, journey progress is a discrete
track of stops, and rendering both as percentages made them read as competing
scores. That distinction should survive. The others are simply independent
inventions.

### 1.10 Feedback and status states

- **Verdict** — a mono uppercase word coloured by classification (jade / brass /
  rust), inside a `slab` card, with the rationale below.
- **Callouts** — three variants: signal-tinted (`takeaway`, `hint` / `followup`),
  slab (`ownership`), jade-tinted (`recovered`). All the same box, differing only
  in border and background tint.
- **Loading** — always `animate-pulse` on a line of mono text. Six occurrences,
  three different phrasings. No skeletons anywhere.
- **Errors** — always a bare `text-rust` paragraph, except the pipeline-failure
  screen which uses a scrollable `<pre>`. No toast, no inline field errors, no
  consistent placement: in `LessonPanel` the same `error` state renders in three
  different positions depending on which block happens to be mounted.
- **Empty states** — mostly handled (`patternsEmpty`, and a `hasEvidence` gate on
  the map analytics), with one plain-text fallback (`firstLesson`).

### 1.11 Responsive behaviour

**There is effectively none.** Three `md:` utilities exist in the entire
frontend — the welcome page grid and two map grids. Everything else is fixed.

The session page is `h-screen overflow-hidden` with a grid of
`16.75rem | minmax(0,1fr) | 21.25rem`. With the rail and a docked source pane
open, the lesson column gets `viewport − 38rem`: about 670px at 1280px wide,
about 415px at 1024px. Below that the header — a non-wrapping row of nine
`shrink-0` groups — overflows and is clipped by `overflow-hidden`.

There is no mobile layout, no tablet layout, and no breakpoint at which the rail
or the source pane collapses. The `--ui-scale` text dial makes this worse at the
`large` and `xlarge` steps, because the fixed columns are in rem and grow with
the setting.

### 1.12 Animation and transitions

- **57 bare `transition` utilities** — Tailwind's default (150ms; colour,
  background, border, opacity, transform, shadow). This is the app's entire
  motion language: hover colour changes.
- Two `transition-[width]` (progress bars, 500ms and 700ms `ease-out`) — the only
  deliberate timings in the codebase.
- `animate-pulse` for every loading state and two live indicators.
- One smooth scroll, in the source pane, with a documented rule: animate a short
  hop, jump for a long one.
- `prefers-reduced-motion` is honoured globally.

**Nothing animates when content changes.** No enter/exit transitions, no fade-in
on the verdict, no height animation when the rail inserts a warm-up, no crossfade
between lesson and section overview, no transition when the map tab replaces the
lesson. Every state change is an instant repaint. This is the single largest
contributor to the "static" feeling, and also the cheapest to change.

### 1.13 Consistent vs ad-hoc — summary

**Consistent (keep):** colour tokens and their semantics; the one-accent rule;
the understanding-state encoding shared across four components; tag chips; the
mono micro-label device; the two button variants in intent; reduced-motion; the
copy-centralization discipline.

**Ad-hoc (converge):** type sizes; radii and elevation; spacing rhythm; icons;
loading and error presentation; focus states; progress grammars; the duplicated
`SectionLabel` and `Chevron`; button padding.

**Actively wrong:** the gap list and verification block token usage (§5.1).

---

## 2. Current learner experience and flow

The real flow, derived from the code:

```
/  ──repo──▶  /  ──goal interview──▶  /  ──pipeline (2–4 min)──▶  /session/[id]/welcome
                                          │
                                          └─(failure)─▶ retry / different repo

/session/[id]/welcome ──Begin──▶ /session/[id]
                                     │
                      ┌──────────────┼──────────────┐
                      ▼              ▼              ▼
               SectionOverview   LessonPanel     MapView
                (layer over       (the loop)   (+ EvidenceDrawer)
                 the lesson)          │
                                      ▼
                               CompletionScreen
```

### Stage 1 — Repository (`/`, step `repo`)

**Sees:** a centred column — serif wordmark, tagline, a mono uppercase label, a
monospace URL input, up to four recent-repo chips from localStorage, a Start
button. The settings gear floats top-right.
**Actions:** type or paste a URL, click a recent chip, submit.
**After:** `POST /repo/check` runs *before* the interview — a deliberate choice
so five questions aren't spent on an uncloneable repo. On failure, an inline rust
paragraph; on success the form is replaced by the interview.
**Stays visible:** wordmark, tagline, settings. The form is swapped, not
augmented.

### Stage 2 — Goal interview (`/`, step `goal`)

**Sees:** a tick bar (one segment per question, filled to the current index),
`question N of M`, the question in large serif, then either a set of option chips
or a textarea, then Back / Continue and a hint line.
**Actions:** pick an option or type; Enter submits free text; Back un-answers
server-side and restores the previous text.
**After:** the same layout re-renders with the next question. No transition.
**Notable:** the hint line explains *why* Continue is disabled rather than
leaving the user to guess — a genuinely good detail. Options are the whole input
when a fixed vocabulary applies, because the backend rejects anything else.
**Weakness:** no view of previous answers, and the tick bar is the only sense of
position. Once past a question its content is gone unless you go Back.

### Stage 3 — Pipeline (`/`, step `starting`)

The two-to-four-minute wait. `StartingProgress` polls `/session/progress/{id}`
every 900ms, against a run id generated client-side and sent with
`/session/start`.

**Sees:** repo name; a bar measuring *stages completed* (never a fake
percentage); a checklist of pipeline stages with three states (done ✓ jade /
active pulsing ring / pending hollow ring); a live activity line under the active
stage naming real tool calls ("Reading requests/sessions.py") with a lookup
counter; and an elapsed counter that prefers the server's own elapsed time over
the local tick, because browsers throttle timers in hidden tabs.
**After:** redirect to `/welcome`.

This screen is the best interaction design in the product. It is explicit about
what is measured, it degrades to rotating descriptions of real work when a stage
has nothing to stream, and it never invents a progress number.

### Stage 4 — Welcome (`/session/[id]/welcome`)

**Sees:** header (wordmark, repo, settings); a label and serif heading; then a
two-column grid — a briefing paragraph marked *personalized* or *generic* (the
honesty rule again) with a bulleted notes list carrying file paths, and a
`ProfileCard` aside showing the derived learner profile as chips, a definition
list, and the route size.
**Actions:** Begin. That is the only action on the page.
**Loading:** the two halves load independently — the profile is immediate
(derived from the graph already built), the briefing costs one Haiku call and can
fail into a missing paragraph without blocking the page or the button.
**Weakness:** no route back to the session other than `Begin` or browser back;
and no way to *act* on disagreeing with the profile, which is the page's stated
purpose — the only path is Start Over in the session header, one page away.

### Stage 5 — The session shell (`/session/[id]`)

**Persistent chrome:** the header (always) and the rail (always). The centre
column swaps between three contents; the source pane is a third grid track that
appears and disappears, changing the grid template.

**Visible in every state below:** wordmark, repo + goal + depth, both progress
measures, the scope controls, the source toggle, the welcome link, start over,
settings, and the entire rail. That is a great deal of permanent chrome for a
screen whose job is to show one lesson.

### Stage 6 — Chapter introduction (`SectionOverview`)

Auto-opens **once per visit** when the learner arrives in a section with nothing
settled behind it, tracked in a `useRef` set so reloading, resuming mid-chapter
or re-reading a finished one never re-introduces. Esc closes it.

**Sees:** chapter label, `chapter 2 of 5`, `1/4`; serif title; the area's
purpose; a "why now" quote block relating it to the previous chapter; a
`BY THE END` list of unit objectives; and a `LESSONS` list — every stop with its
pin, title, state label, filename and concept tags.
**Actions:** click any lesson (jumps, and lands on the lesson itself, which is
what makes the list a way in rather than a table of contents), Continue, Close.
**Important:** it is a *layer over the lesson column*, not a route. It never
moves the session pointer; closing returns the learner exactly where they were.
**Weakness:** it appears with no transition, in place of the lesson, and the only
signal that it is a layer rather than a destination is the copy. A learner
mid-lesson who clicks a section title in the rail sees their lesson vanish.

### Stage 7 — The lesson loop (`LessonPanel`) — the core

This is where the complexity lives. Blocks render in this fixed vertical order:

| # | Block | Condition |
|---|---|---|
| 1 | Header: `STOP 4 OF 12` (or `WARM-UP`), serif title, file·lines button, concept tags | always |
| 2 | `RECOVERED` banner (jade) | recovered after a warm-up |
| 3 | `why_now` italic quote | split lessons |
| 4 | `SETUP` / `WALKTHROUGH` prose | always |
| 5 | `TRACE PATH` — numbered anchor list | more than one anchor |
| 6 | `OPEN GAPS` — named misconceptions + per-gap *waive* button | gaps present |
| 7 | `VERIFICATION` — new question + textarea + Submit / Not now | verification requested |
| 8 | `YOUR ANSWERS` — collapsible attempt cards | ≥ 1 attempt |
| 9 | `CHECK UNDERSTANDING` — prompt + textarea + Submit / Skip stop | **`!result`** |
| 10 | `REVEAL` + `TAKEAWAY` callout + `OWNERSHIP` callout | answered, split lesson |
| 11 | **Verdict panel** — verdict, rationale, adaptation callout, retaught / pruned notices, warm-up status, 1–4 action buttons | `result` present |
| 12 | `Finish early` link | always |

**Initial state:** blocks 1, 3, 4, 5, 9, 12. The reveal is withheld — that
withholding *is* the active-learning mechanism, and it is correctly implemented
(it also opens on revisit, since a returning learner is reading, not being
tested).

**After submitting an answer:** block 9 disappears; blocks 10 and 11 appear
*below* where it was; block 8 gains a card; block 6 may appear *above* the prose
the learner just read. The page grows downward and upward at once, with no scroll
management and no transition.

**Actions offered in the verdict panel, by classification:**

- `understood` → Next stop
- `partial` → Next stop, Build a warm-up
- `confused` / `off-topic` → Start warm-up (if one was inserted) or Move on
  anyway, plus Build a warm-up
- any adaptation of kind `hint` / `followup` / `reteach` → **Check my
  understanding** (asks a *new* question about the leading gap — deliberately not
  "try again", because the reveal has already given away the original answer), or
  plain Try again when there are no open gaps

That is up to four buttons in one wrapped row, two of them tinted-primary and
indistinguishable in weight, all at the very bottom of a long column.

Requesting a warm-up can also be declined by the backend, in which case the panel
stays up and an error line explains why — a deliberate choice over silently
resetting the form.

### Stage 8 — The map tab

Replaces the lesson column entirely; the rail stays. Contents in order: a
headline with repo name and the two measures; **the journey as the visualization**
— the route as a vertical timeline of cards with pins, dashed connectors for
adaptive inserts, tags and state; then up to three outcome panels (`NEEDS WORK` /
`WORKED THROUGH` / `SET ASIDE`); then `PATTERNS` (deterministic observations with
numbered evidence buttons); then a collapsed `MORE BREAKDOWNS` block with
by-concept and by-file `StateStrip` rows.

Clicking any unit opens `EvidenceDrawer`, which takes a 26rem column and squeezes
the map rather than overlaying it. Esc closes.

Analytics are gated on `understanding.assessed > 0`, with a comment recording
that 60 of 69 stored sessions had no evidence and were being shown 1875px of
empty dashboard.

### Stage 9 — Completion

Reached by advancing past the last stop, or via the `Finish early` link. Renders
*inside* `LessonPanel`, replacing everything — but the session header and rail
remain, still showing live session controls. Two tabs (Summary / Map), a headline
count, an "another pass" list of still-unresolved units, and New session / Home
buttons.

**Weakness:** `Finish early` is a small grey text link at the bottom of every
lesson that immediately and irreversibly swaps the screen for the completion
view, with no confirmation. It is the least prominent control with the largest
consequence.

---

## 3. Main screens and components — a working map

### Pages

| File | Purpose | Owns |
|---|---|---|
| [app/page.tsx](../../../frontend/app/page.tsx) | Entry funnel | `Step` machine (repo / goal / starting / failed), repo URL, recents, progress id, retained goal for retry |
| [app/session/[id]/welcome/page.tsx](frontend/app/session/[id]/welcome/page.tsx) | Pre-session orientation | graph + briefing, independently loaded |
| [app/session/[id]/page.tsx](frontend/app/session/[id]/page.tsx) | Session shell | **All session state** — graph, tab, source visibility, viewed file / range, focus key, overview layer, evidence node, scope busy + note, restart |
| [app/layout.tsx](../../../frontend/app/layout.tsx) | Root | fonts, theme boot script, `data-theme` |

### Components

| Component | Purpose | Displays | Talks to | Reusable? |
|---|---|---|---|---|
| **`LessonPanel`** (862 ln) | The learning loop | Lesson prose, gaps, verification, attempts, answer form, reveal, verdict, actions — **and** `CompletionScreen` | `getLesson`, `respond`, `advance`, `retry`, `requestVerification`, `respondToVerification`, `waive`; calls back to the page for file open / advance / refresh | Page-specific. Contains a second page-sized component inside it |
| **`MapView`** (663 ln) | Progress + understanding | Two measures, route timeline, outcome bands, patterns, breakdowns | Pure props; emits node click and evidence open | Used twice — session map tab and completion tab |
| **`RouteRail`** (384 ln) | Where am I / what's behind / what's next | Sections, stops, pins, optional bucket | Pure props | Page-specific, but the cleanest component |
| **`CodeViewer`** (400 ln) | Source pane shell | File header, dock/float toggle, close; drag and resize | `getFile`; `prefs` for geometry | Reusable in principle |
| **`CodeLines`** (130 ln) | Code body | Line table, gutter, highlight band, syntax tokens | `lib/highlight` (Shiki) | Yes — memoised, cleanly separated |
| **`SectionOverview`** (240 ln) | Chapter introduction | Chapter meta, purpose, why-now, objectives, lesson list | Pure props | Page-specific |
| **`EvidenceDrawer`** (232 ln) | Why a unit has its state | Objective, state, attempts, interventions | `getEvidence` | Map tab only |
| **`GoalDialogue`** (176 ln) | The interview | Tick bar, question, options / textarea, back / continue | `goalStart`, `goalAnswer`, `goalBack` | Landing page only |
| **`StartingProgress`** (171 ln) | The wait | Stage checklist, activity line, elapsed | `sessionProgress` (polls) | Landing page only |
| **`SettingsMenu`** (193 ln) | Theme + text size | Popover with two segmented controls | `lib/prefs` only | **Yes** — used on all three pages |
| **`ProfileCard`** (99 ln) | Who the system thinks it teaches | Goal chips + definition list + route size | Pure props | Welcome page only |

### Shared primitives — the gap

The only genuinely shared UI primitives are `SettingsMenu`, `CodeLines`, and the
style *functions* in `lib/tags.ts` (`tagStyle`, `understandingStyle`,
`stateStyle`, and their label counterparts). There is **no** `Button`, `Card`,
`Panel`, `Chip`, `SectionLabel`, `Callout`, `Spinner`, `EmptyState` or `Icon`
primitive. `Panel` and `SectionLabel` exist but are private to one file each and
re-implemented inline elsewhere.

### Library modules

| Module | Role |
|---|---|
| `lib/api.ts` (664 ln) | Every endpoint and every wire type; error unwrapping; `server_unreachable` translation |
| `lib/strings.ts` (675 ln) | **All** user-facing copy, 17 top-level groups, plus `errorText` slug mapping |
| `lib/tags.ts` | Tag and state → style / label. The single visual vocabulary |
| `lib/prefs.ts` | Theme, text size, source-pane geometry; localStorage; the pre-paint boot script |
| `lib/graph-layout.ts` | Graph → ordered `RouteStop[]`; `isStation`, `spineLength` |
| `lib/route-sections.ts` | Stops → sections; `isSettled`; the optional split |
| `lib/highlight.ts` | Shiki dual-theme tokenizing |
| `lib/source-pane.ts` | Floating-pane placement maths |
| `lib/code-theme.ts` | Syntax colour pair generation |

---

## 4. UX strengths — what to preserve

1. **The token architecture.** CSS-variable theming with zero component-level
   branching. Three themes and four text sizes for free. Do not disturb this.
2. **The palette's semantics.** One accent reserved for "you are here"; jade /
   brass / rust semantic-only; a tag hue per concept kind. A real visual
   identity, not a default.
3. **The `--ui-scale` dial.** Root font-size multiplication, with type authored in
   relative `calc()` so the browser's own setting compounds rather than being
   overridden. Genuinely well-engineered accessibility.
4. **One vocabulary, one encoding.** `understandingStyle` / `understandingLabel`
   are shared by rail, overview, map and drawer, so a unit cannot be amber in one
   place and "needs work" in another. This was a deliberate fix (M3a.3) and it
   must survive any redesign.
5. **State encoded by shape, not only colour.** Dashed vs solid borders, fill vs
   half-fill, distinct pin geometry.
6. **Honesty as a design principle, everywhere.** The progress bar counts
   completed stages rather than faking a percentage; the map headline is a
   fraction rather than "47% ready"; the briefing says whether it is personalized
   or generic; the evidence drawer distinguishes "no record" from "nothing
   happened"; every claim has an evidence path.
7. **`StartingProgress`.** The right answer to a long wait: show real work.
8. **The rail's restraint.** Explicitly stripped back to four questions. It works,
   and its density discipline should be the model for the rest of the app.
9. **The source pane.** Dock or float, with drag, resize, viewport re-placement,
   keyboard resize, persisted geometry, and performance-aware gesture handling
   (CSS variable during the drag, React state on release).
10. **Copy centralization.** All wording in `strings.ts`; parsed keys kept
    strictly separate from displayed labels.
11. **Keyboard and a11y touches.** Esc closes overview / map / drawer / settings;
    `aria-current="step"`; `sr-only` state text; `aria-live` on the progress list;
    labelled evidence buttons; global reduced-motion.
12. **The withheld reveal.** Explanation gated on committing to an answer, but
    opened on revisit. Correct pedagogy, correctly implemented.

---

## 5. UX/UI weaknesses

### 5.1 Confirmed defects — wrong, not stylistic

**a) The gap list and verification block use undefined and inverted tokens.**
In [LessonPanel.tsx:468–518](../../../frontend/components/LessonPanel.tsx#L468) six
elements use `bg-paper`, `text-ink` and `border-hairline`:

- `--color-hairline` **does not exist**. Tailwind emits nothing for
  `border-hairline`, so those elements fall back to a `currentColor` border.
- `bg-paper` is the *dim text* colour (`#b9c6ce` dark / `#2c4653` light) and
  `text-ink` is the *page background* colour. Used as surface and ink they are
  inverted: in the dark theme these render as a **light card with dark text** in
  an otherwise dark app; in the light theme, a **dark card**. Wrong in both.
- The verification Submit is `bg-signal text-paper` — the only solid-filled
  button in the product.

This shipped in the committed `M9` gap-surface work, so it is live. The two most
important surfaces in the product — "what you still don't understand" and "prove
that you now do" — are the two that look foreign.

**b) Two answer boxes can be on screen at once, bound to the same state.**
`onCheckUnderstanding` sets `verification` **and** clears `result`. Block 9
renders on `!result`; block 7 renders on `verification`. Both therefore mount,
both render a textarea with `value={answer}`, and both show a Submit button — one
calling `submitAnswer` (re-answering the original question), one calling
`onSubmitVerification`. Typing in either mirrors into the other. Compounding it,
the verification question renders **above** the attempts list while the button
that requested it sits at the very bottom of the page, so the learner clicks and
the result appears off-screen upward.

### 5.2 Visual / cosmetic problems

| # | Problem | Why it reads as dated |
|---|---|---|
| V1 | One radius (4px), no elevation, two shadows in the whole app | Everything is the same flat outlined box; no depth, no grouping by material |
| V2 | Hairline borders as the only container device | Wireframe aesthetic; boxes within boxes at identical weight |
| V3 | No solid primary button anywhere | No action ever looks like *the* action |
| V4 | 22 undeclared type sizes, many half a point apart | Hierarchy is fuzzy; nothing snaps to a rhythm |
| V5 | The mono-uppercase micro-label used for every hierarchy level | Six sections at identical weight in one column; nothing draws the eye |
| V6 | Motion is only a 150ms hover colour change | Static; nothing acknowledges a change |
| V7 | Ad-hoc icons, two glyph/SVG duplicates, three stroke weights | Small but pervasive incoherence |
| V8 | Buttons have no focus-visible style | Keyboard use falls back to an unstyled browser ring |
| V9 | Loading is always pulsing mono text; no skeletons | Long waits look broken rather than pending |
| V10 | Errors have no consistent placement or container | Failure feels unhandled |
| V11 | Spacing rhythm differs per file (`gap-6` / `7` / `9`) | Pages don't feel like one product |

### 5.3 Interaction / UX problems

| # | Problem | Nature |
|---|---|---|
| I1 | The session header carries nine groups in one non-wrapping row: wordmark, repo·goal·depth, demonstrated bar + fraction, journey count, scope label + two buttons + note, source toggle, welcome link, start over, settings | **Structural.** Global chrome carries per-session controls, journey-altering controls and app settings at one weight |
| I2 | Scope controls (`shorter` / `deeper`) sit in the header and silently re-plan the journey; the only feedback is a mono note, also in the header | **Structural.** A journey-wide action presented as two small grey buttons, with its consequence rendered in the rail, where nobody is looking |
| I3 | The verdict's action buttons sit at the bottom of a long scroll while their results (verification question, gap list, reveal) insert far above | **Structural.** Action and consequence are not co-located |
| I4 | Up to four equally weighted buttons in the verdict row | **Structural.** No recommended path |
| I5 | `Finish early` — smallest control, largest consequence, no confirmation | **Structural** |
| I6 | Nothing scrolls or takes focus after a state change | **Structural**, but cheap to fix |
| I7 | The chapter overview replaces the lesson with no transition and no "layer" affordance | Mostly cosmetic; the model is right, the presentation doesn't communicate it |
| I8 | Rail mutations (a warm-up spliced in) happen silently | **Structural.** The system's adaptation — the product's core claim — is invisible at the moment it happens |
| I9 | The welcome page has no route back to the session | Minor structural |
| I10 | The evidence drawer squeezes the map instead of overlaying it | Cosmetic |
| I11 | The interview shows no previous answers | Minor structural |
| I12 | No responsive behaviour below ~1100px; the header clips | **Structural** |
| I13 | Two visually similar but differently styled tab strips | Cosmetic |

---

## 6. Flow and state complexity — where it accumulates

This is the area with the most structural risk.

### 6.1 The accumulation problem

`LessonPanel` is a **single scrolling column that only ever grows**. Consider a
realistic hard path — the learner answers, is judged `confused`, a gap is
recorded, a warm-up is offered, and they request a verification.

On screen simultaneously: the stop header and tags; the recovered banner where
applicable; the why-now quote; the full setup prose; a trace-path list; a named
gap list with per-gap waive buttons; a verification question with its own
textarea and two buttons; the attempts list; **the original answer form with its
own textarea and two buttons**; the reveal, plus a takeaway callout and an
ownership callout; and the verdict panel with its rationale, an adaptation
callout, possibly a "re-taught" notice, a "pruned" notice, warm-up status copy,
and up to four buttons. Then the finish-early link.

That is up to **twelve distinct blocks, three textareas' worth of input
affordance, and as many as nine buttons**, in one column, at similar visual
weight, ordered by markup position rather than by what the learner should do
next.

The blocks are individually well-reasoned — nearly every one carries a comment
explaining a real pedagogical decision behind it. The problem is not any single
block; it is that **nothing composes them.** There is no notion of "which phase
of the loop is this learner in", so every block independently decides whether to
render, and their vertical order is fixed by source order rather than by
relevance.

### 6.2 State transitions are invisible

| Event | What the learner perceives |
|---|---|
| Answer graded | The form vanishes; two large blocks appear below; a gap list may appear above the prose. Instant, no motion, no scroll |
| Warm-up inserted | A new row appears in the rail, indented, labelled "added after confusion" — but the eye is in the lesson column. Nothing announces it |
| Re-teach | The lesson prose is silently replaced with corrected text (a `getLesson` refetch) — possibly mid-paragraph. A small mono "retaught" line appears in the verdict panel, far below |
| Path pruned | A one-line mono notice in the verdict panel; the rail silently loses rows |
| Scope changed | The rail re-renders wholesale; feedback is a mono note in the header |
| Gap waived | The row disappears from the list; nothing else moves |
| Verification requested | The question is inserted far above the button that requested it, and the original form re-mounts alongside it (§5.1b) |
| Chapter entered | The lesson column is replaced entirely by the overview |
| Session finished | The whole panel is replaced by completion; the header and rail remain, still showing live session controls |

The pattern is consistent: **the system's most intelligent behaviours — adapting
the graph, re-teaching, pruning — are its least visible.** The adaptive learning
graph is the product's stated X-factor, and it currently changes without ever
being seen changing.

### 6.3 State ownership is split in a way the UI has to paper over

`LessonPanel` holds `result`, `verification`, `answer`, `lesson` and `done`; the
session page holds `graph`. They can disagree, and the code manages this
explicitly:

- After a warm-up insert, the graph refresh is *deliberately skipped* so the
  verdict stays readable — which leaves `node.attempts` one behind, patched with
  a synthesized `pending` attempt object.
- `openGaps` prefers `result.gaps` over `node.gaps` for the same reason.
- Verification attempts are *filtered out* of the attempts list because the copy
  for them doesn't exist yet, with a comment noting this as deferred M9 work.

These are correct workarounds for a real timing problem, but they mean the panel
reconciles two sources of truth on every render — exactly the kind of thing that
makes a redesign risky if the reconciliation isn't carried across.

---

## 7. Technical UI architecture

**Framework:** Next.js 15.3 (App Router), React 19.2, TypeScript. Every page and
component is `"use client"` — there is no server-component or server-data usage
at all. Shiki 4 is the only runtime dependency beyond React and Next.

**Styling:** Tailwind v4 via `@tailwindcss/postcss`, configured entirely in CSS
(`@theme` in `globals.css`). No config file, no plugins, no CSS modules, no
styled-components, no `clsx` / `cva`. Class strings are template literals with
ternaries.

**Design tokens:** all in [globals.css](../../../frontend/app/globals.css) — surfaces,
text, accents, semantic colours, tag hues (dark and light), code-pane colours,
`--font-display`, `--ui-scale`, `--source-width`. Plus `.measure` (62ch), `.tok`
and `.code-cold` for the syntax layer, and the reduced-motion block.

**Component hierarchy:**

```
RootLayout (fonts, theme boot script)
├── Home
│   ├── SettingsMenu
│   ├── GoalDialogue
│   └── StartingProgress
├── WelcomePage → SettingsMenu, ProfileCard
└── SessionPage
    ├── header → SettingsMenu
    ├── RouteRail
    ├── centre: SectionOverview | LessonPanel | MapView
    │   └── LessonPanel → AttemptCard, SectionLabel, Chevron, CompletionScreen → MapView
    └── CodeViewer → PaneHeader, DockDivider | FloatShell → CodeLines
```

**State management:** `useState` and `useEffect` only. No Redux / Zustand / Jotai,
no React Query, no Context — `strings` is a plain module import by explicit
design. The session page is the single owner of session state and passes
callbacks down; refresh is manual (`loadGraph()` after every mutating call).
Preferences go through localStorage, a pre-paint boot script and direct `<html>`
attribute writes. `StartingProgress` polls; nothing else does.

**Does this architecture make a visual redesign easy or hard?**

*Easy:*

- Colour, theming and type scaling are already centralized. Re-tuning the whole
  palette, adding elevation tokens, or introducing a real type scale means
  editing one file.
- No CSS specificity problems, no cascade to fight, no component library to
  override.
- Copy is fully extracted, so wording changes never touch layout.
- The shared style functions in `lib/tags.ts` mean state-encoding changes
  propagate to all four consumers at once.

*Hard:*

- **No primitive layer.** Introducing a `Button` means touching ~30 call sites
  across 9 files. Same for cards, callouts, chips and section labels.
- **Arbitrary type values everywhere.** Moving to a named scale is mechanical but
  wide — every component.
- **`LessonPanel` is an 862-line monolith** holding the lesson, the gap surface,
  the verification surface, the attempt history, the answer form, the verdict,
  all adaptation UI, *and* the completion screen. Any flow redesign is a rewrite
  of this file — and it is also where the trickiest state reconciliation lives.
- **No layout primitives and no breakpoints.** Responsiveness is not a refactor,
  it is new work: the session grid, the header, the rail and the source pane all
  need collapse behaviour that does not exist in any form today.
- **No animation infrastructure.** No motion tokens, no transition components, no
  library. Adding motion means adding the concept as well as the code.

---

## 8. Overall assessment

### What design language does the product have today?

**A cold technical instrument, drawn in hairlines.** A dark blue-black ground,
one cyan accent used only for presence and action, semantic jade / brass / rust,
monospace for everything factual and a serif for everything asserted. It is
coherent, distinctive, and clearly *authored* — not a Tailwind default, not a
dashboard template. The metaphor (survey instrument, blueprint, field notebook)
is real and is carried consistently through the palette, the token naming and the
copy.

It feels dated for a specific and narrow reason: **the visual system has exactly
one structural device — the 1px outlined rectangle at 4px radius — and exactly
one motion device — a 150ms hover colour change.** Everything else it needs
(depth, weight, grouping, emphasis, response) it does with colour alone, and
colour is already fully committed to meaning. Nothing is left over to say "this
box matters more than that one", or "something just changed".

The intelligence in this product is almost entirely in decisions the UI does not
show: it adapts, prunes, re-teaches, re-plans and diagnoses — and it does all of
it silently, in flat boxes, with no motion.

### What should definitely be preserved

The token architecture and the theme mechanism. The palette semantics and the
one-accent rule. The single understanding vocabulary shared across four
components. Shape-plus-colour state encoding. The `--ui-scale` dial and relative
type. The honesty discipline (fractions over percentages, real progress over fake
progress, "personalized or generic", evidence behind every claim). The rail's
restraint. `StartingProgress`. The withheld reveal. The source pane's dock/float
behaviour. Copy centralization.

### The eight most important problems, ranked

> Re-ranked after live validation — see [§10.8](#108-revised-ranking). Problem 3
> moved to the top because the rendered result is not "foreign-looking", it is
> **invisible**.

| # | Problem | Type | Fix cost |
|---|---|---|---|
| 1 | The verification question renders at **1.00:1 contrast** (ink on ink) and its Submit label at **1.11:1** — the gap/verification surface is not merely mis-styled, it is unreadable | **Defect — blocks the feature** | Low |
| 2 | `LessonPanel` accumulates up to twelve co-visible blocks and nine buttons with no compositional model — the lesson loop has no notion of "which phase am I in" | **Interaction / flow redesign** | High |
| 3 | The system's adaptations (warm-up inserted, re-teach, prune, scope change) are invisible at the moment they happen — the product's core claim never shows itself | **Interaction / flow redesign** | Medium–high |
| 4 | Two answer textareas mount together bound to the same state, with **two buttons both labelled "Submit"**, and the verification question inserted ~780px above the button that requested it | **Interaction — a bug** | Low–medium |
| 5 | The session header does not overflow at common widths — it **starves** the goal statement (469px → 0px as the viewport goes 1600 → 1024) while the scope controls keep 239px | **Interaction / IA redesign** | Medium |
| 6 | No motion on any content change; nothing scrolls, focuses or acknowledges a transition — the verdict lands at y=2080 in a 634px viewport with `scrollTop` still 0 | **Visual polish, high impact** | Low–medium |
| 7 | **99% of text is ≤16px across 11 sizes inside a 6.5px band**, one radius, and no elevation anywhere — there is no mechanism left to express relative importance | **Visual polish** | Medium (wide but mechanical) |
| 8 | No responsive behaviour; the header overflows below **1111px** and the side panels take 68% of the screen at 900px | **New work** | Medium |

Runners-up, in order: inconsistent loading / error / empty presentation; missing
focus-visible styles; no shared primitives (`Button`, `Card`, `Callout`,
`SectionLabel`, `Chip`); the unconfirmed `Finish early`; the chapter overview's
missing layer affordance; six progress grammars where two are justified.

### Split: polish vs. redesign

**Primarily visual polish** — achievable without changing any flow, and
collectively responsible for most of the "dated, rigid, static" impression:
tokens for radius, elevation, type and motion; a real primary button; a shared
primitive layer; enter transitions and change acknowledgement; consistent
loading, error and empty states; focus rings; icon consolidation; and fixing the
inverted-token block (#3).

**Requires genuine interaction/flow redesign** — cannot be reached by restyling:
the lesson loop's phase model (#1); making adaptation visible (#2); the header
and IA split (#5); co-locating actions with their consequences (#4, and part of
#6); responsive collapse of the three-column shell (#8).

The encouraging finding is that these are largely separable. The polish tier can
land first, on the existing structure, without touching `LessonPanel`'s logic —
and it will move the perceived age of the product further than its size suggests.
The flow tier is where `LessonPanel` gets decomposed, and that work should be
specified before it is started, because that file is also where the state
reconciliation between the panel and the session graph lives.

---

## 9. What this document does not do

It does not propose a target design language, a component API, a motion spec, a
layout system, or a migration order. That is the next document.

---

## 10. Live validation

A second pass, run against the application actually running in a browser. Where
this section contradicts §1–§8, **this section wins**.

### 10.0 Method, and its one limitation

- Backend: the already-running instance on `:8000`. Frontend: an isolated copy
  of `frontend/` at `.ui-audit-fe` (git-excluded, `node_modules` junctioned)
  serving on `:3007`, proxying the API through its own origin. This was
  necessary because three dev servers were sharing one `.next` directory and
  clobbering each other's build output — the session route returned HTTP 500 on
  both existing frontends.
- Data: real persisted sessions from `data/sessions.db` (backed up first), plus
  **live grading calls** against the real Grader to reach the post-answer states.
  Session `cff533a5…` (aima-python; 18 nodes, 5 areas, 20 attempts, 54 gaps,
  26 prerequisite edges) carried nearly every state.
- Measurements are `getComputedStyle` + `getBoundingClientRect` on the live DOM
  at 1280×720, with transitions disabled during reads. Contrast ratios are
  WCAG 2.x, computed with correct alpha compositing.

**Limitation, stated plainly: no screenshots.** The browser pane in this
environment does not composite frames (`document.visibilityState === "hidden"`),
so image capture was impossible and *motion could not be observed at all*. Every
claim below is from measured geometry, computed colour and DOM state in a real
browser against real data — not from looking at pictures. Claims about animation
in §1.12 remain code-derived and unverified. A later pass with a visible browser
would still be worth doing for aesthetic judgement, which this method cannot
supply.

### 10.1 The two claimed defects — both confirmed, one far worse

**Defect A is not cosmetic. It is a functional failure.**

Measured on the live gap and verification surfaces:

| Element | Foreground | Background | Ratio | Verdict |
|---|---|---|---|---|
| **Verification question** (601×84px of real text) | `rgb(10,16,20)` | `rgb(10,16,20)` | **1.00:1** | **Invisible** |
| **Verification Submit label** | `rgb(185,198,206)` | `rgb(91,200,232)` | **1.11:1** | **Invisible** |
| Verification textarea (light box in a dark app) | ink | `rgb(185,198,206)` | 10.97:1 | Legible, foreign |
| Gap card "Holding this stop back" | graphite | paper | **1.97:1** | Fails AA |
| Gap card **"Set aside"** — the only gap control | graphite | paper | **1.97:1** | Fails AA |
| Gap card border (`border-hairline` → `currentColor`) | chalk | paper | 1.37:1 | Invisible |
| Gap card vs page | paper | ink | 10.97:1 | Glaring light panel |
| *Same, light theme* | — | — | **1.64:1** | Fails AA |
| Adjacent normal card, for comparison | chalk | slab | 13.52:1 | Correct |

The verification question is a 601×84px element containing three lines of real
text, painted ink-on-ink with every ancestor transparent up to `main`. Directly
beneath it, in legible graphite, sits the help line *"Answering this is the only
thing that clears the gap — moving on leaves it open."*

**So the learner is told, legibly, that answering the question is the only way
to clear the gap — above an invisible question and an invisible Submit button.**
The gap model is the product's most distinctive claim, and at present its
primary surface cannot be used.

**Defect B confirmed exactly, plus one detail the code read missed.** After
clicking *Check my understanding*:

- Two textareas mount simultaneously, at y=1307 and y=1804 — 497px apart, with
  identical `"Write your answer…"` placeholders.
- Typing into one mirrors verbatim into the other (both bound to `answer`).
- **Two buttons on screen both labelled exactly `Submit`**, doing different
  things, plus a `Not now`. The code inspection predicted the shared state but
  not the duplicate label.
- The requested question appears ~780px **above** the button that requested it,
  and the scroll position does not move.

### 10.2 Layout: the header starves rather than overflows

The baseline said the header "overflows and is clipped". Measured, it is worse
in a more interesting way — at common widths it fits, by consuming the one
element that says what the learner is doing:

| Viewport | Goal statement width | Header overflow | Lesson column |
|---|---|---|---|
| 1600 | 469px | no | 992px |
| 1440 | 309px | no | 832px |
| 1280 | **149px** (truncated) | no | 672px |
| 1150 | **19px** | no | 542px |
| 1024 | **0px** | **yes** (1111 > 1024) | 416px |
| 900 | 0px | yes | 292px |

Nine top-level groups, all `shrink-0` except the repo/goal text, which is the
only `flex-1 truncate`. At 1280 — an ordinary laptop — "Make it shorter / Go
deeper" holds 239px and "DEMONSTRATED 7/12 (58%)" holds 248px, while the goal
the learner chose is truncated to 149px. **The hard floor is 1111px**, which
confirms the baseline's "~1100px" estimate almost exactly.

The rail (268px) and source pane (340px) are fixed at every width: 608px of
chrome. At 1280 the lesson gets 672px — barely half the screen. At 900px the
side panels take **68%** of the viewport.

### 10.3 Accumulation, measured

The lesson column on one ordinary stop, at 1280×720 (viewport 634px tall):

| State | Column height | Ratio to viewport |
|---|---|---|
| On arrival (already answered once) | 2521px | 4.0× |
| After submitting a wrong answer | 2371px | 3.7× |
| After requesting verification | **2845px** | **4.5×** |

Block structure after a wrong answer, top to bottom: header (107px) → why-now
(81) → setup prose (445) → trace path, 4 anchor buttons (133) → **gaps, 3 "Set
aside" buttons (244)** → attempts (101) → **reveal (777)** → **verdict, 3 buttons
(202)** → finish-early (41).

Two things the code review inferred but could not prove:

1. **The verdict lands at y=2080** — more than three viewport-heights down — and
   `scrollTop` stays at `0`. Nothing scrolls, nothing focuses. The learner
   submits an answer and, without scrolling, sees no change at all.
2. Grading **inserts content above the answer form as well as below it** (the gap
   list grew from 1 to 3 entries at y=886, above the form at y=1128), so the
   reveal and verdict are pushed further from the button that produced them. The
   reveal alone is 777px — larger than the viewport.

### 10.4 Typography — a better articulation than §1.3

The source census counted 22 arbitrary sizes across all files. On a single live
session screen (excluding the code pane) there are **12 distinct sizes — and 11
of them fall between 9.5px and 16px. 99% of text elements are ≤16px.** There is
exactly one outlier: the 23px lesson title.

That is the more useful framing. The problem is not variety; it is that the type
system is **flat**: everything is small, and the steps between levels (9.5 / 10 /
10.5 / 11 / 11.5 / 12) are below the threshold of perception. The app has, in
practice, one body size and one heading.

### 10.5 Radii, elevation and colour — confirmed, with one correction

Live census of the session view: `4px` on 24 elements, `rounded-full` on 6 (pins
and bars), `2px` on 5 (tag chips), and the two-half segmented control. One
radius, as claimed.

**Correction to §1.4:** the session view contains **zero elevation shadows**. The
only two `box-shadow` values present are semantic state markers — the signal halo
on the current pin, and the inset signal bar on the highlighted code line. The
two shadows §1.4 counted are on overlays that are closed by default. So in the
default working view there is no elevation at all.

**Correction in the palette's favour:** an automated contrast sweep initially
flagged the concept-tag chips. Recomputed with correct alpha compositing they are
fine — `synthesis` 8.54:1, free-form 5.22:1. The tag system holds up, and §4's
judgement that the palette is an asset is confirmed rather than weakened. The one
genuine non-defect shortfall found anywhere in the palette is the rail's chapter
description (`text-graphite/75` on trench, 10.5px) at **3.6:1**, below AA.

### 10.6 New findings the code review did not surface

1. **In the goal interview, an answer option and the Back button are pixel-identical**
   — both 13px/400, graphite, 1px rule border, same padding. A choice that
   changes the answer and a control that navigates backwards are the same object
   visually.
2. **Disabled state is opacity alone.** `Back` renders at `opacity: 0.3` and
   `Continue` at `0.4`. Applied to graphite on ink, disabled `Back` composites to
   roughly `rgb(44,54,60)` — about 1.5:1 against the page. Disabled controls do
   not read as disabled; they read as absent.
3. **The rail spends 47% of its height on chapter headers.** With four of five
   sections collapsed, 286px of the 611px scroll area is two-line chapter purpose
   text and 161px is actual stops. The rail's own doc comment says density was
   the problem it was designed to solve; the collapsed state re-introduces it in
   a different form.
4. **The map is a 5.2-screen scroll** — 3283px in a 634px viewport, of which the
   journey timeline alone is 2300px (70%). The two headline measures occupy 73px
   at the very top.
5. The source pane correctly vacates its grid track on the map tab, exactly as
   documented (columns go `268 | 672 | 340` → `268 | 1012`).

### 10.7 What could not be validated

- **All motion claims (§1.12).** The pane does not composite; transitions could
  not be observed. §1.12 remains code-derived.
- **The successful briefing state.** The running backend predates the
  `/session/{id}/welcome` endpoint (the briefing work is uncommitted), so it
  returns 404 and the welcome page was only observable in its *failure* state:
  "Couldn't write the briefing — your route is still ready." That degraded state
  is honest and legible, but sparse — the whole page is 444px of content in a
  720px viewport. The success state still needs a look.
- **The pipeline progress screen** (`StartingProgress`), which needs a live
  2–4 minute run. Not exercised.
- **Aesthetic judgement generally.** Measurement can establish that hierarchy is
  flat and that a surface is invisible; it cannot say whether a screen is
  handsome.

### 10.8 Revised ranking

The §8 table has been updated in place. The one substantive change: the
gap/verification token defect moves from #3 to **#1**. It was ranked as cosmetic
because the code read it as "wrong colours". Rendered, it is a feature that
cannot be operated — and it is the feature the gap model exists to deliver.

Everything else in §8 survived validation. The two headline structural problems —
the lesson column's lack of a phase model, and the invisibility of the system's
adaptations — were confirmed with numbers rather than revised.
