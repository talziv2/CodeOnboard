# UI Concept — What the Redesign Actually Looks Like

> **Status:** design concept. No production code, styling, copy or component changed.
> **Builds on:** [`ui-baseline.md`](ui-baseline.md) (evidence) and
> [`ui-direction.md`](ui-direction.md) (principles + interaction architecture).
> **Purpose:** make the direction *picturable* — visual character, wireframes, state
> evolution, and the pre-session flow — so we can decide whether we like it before
> any code is written.
> **Last updated:** 2026-08-19

**One revision to `ui-direction.md` up front:** §4 below reverses that document's
recommendation of a permanently docked action bar. Working through the actual
layout showed a better answer — co-locating the primary action with its phase
artifact — which removes the need for a dock in the common case. `ui-direction.md`
§2.1 should be read as superseded by §2 and §4 here.

---

## 1. Visual character

### 1.1 The character in one paragraph

A **precision instrument with room to breathe.** The current product already has a
real identity — cold blueprint palette, serif for things asserted, monospace for
things measured, code as a first-class citizen, no vanity metrics. That identity is
not the problem. The problem is that it is rendered at uniform density in 1px
outlines at one radius, so every element shouts at the same volume. The redesign
keeps the instrument and gives it air, a wider dynamic range, and softer geometry —
so that the *one thing that matters right now* is unmistakable and everything else
recedes without disappearing.

It should read like a well-made technical tool that someone thought carefully
about — closer to a good editor, a good terminal, or a well-typeset manual than to
a SaaS analytics dashboard. Explicitly **not**: gradient meshes, glassmorphism,
glow, violet-and-cyan "AI" palettes, floating card soup, pill-shaped everything,
illustration, emoji, or decorative motion.

### 1.2 How that translates

| Dimension | Now | Redesign |
|---|---|---|
| **Surface hierarchy** | Two surfaces in practice (`ink` page, `slab` card), separated by a 1px border | A four-step ladder actually used: `ink` page → `trench` structural (rail, panels) → `slab` content cards → `raise` overlays. Depth comes from *surface*, not outline |
| **Whitespace** | Uniform ~16–24px gaps everywhere; density identical in rail, lesson, map | Deliberate rhythm: generous around the primary artifact (32–48px), tight within a group (8–12px). Space becomes the main hierarchy signal |
| **Typography** | 99% of text ≤16px across 11 sizes in a 6.5px band; one 23px outlier | Eight named steps with perceptible gaps; prose raised to 16px/1.7; micro-labels held at 11px but used **once per zone** instead of six times |
| **Borders** | The definition of every box | Rare and meaningful: separation *within* a surface, input affordance, and the one hairline light-theme cards need. Cards stop being outlined |
| **Elevation** | Zero in the session view; the only two shadows are state markers | Shadow only at the top two levels (popover, sheet, floating pane). Dark separates by lightness, light by shadow |
| **Radius** | Universal 4px | 3 / 6 / 10 / 14 / full — the ladder does more for perceived age than any other single change |
| **Density** | Flat and high everywhere | Varied by role: rail dense, lesson spacious, panels medium |
| **Emphasis** | Colour only (and colour is already spent on meaning) | Position → size → weight → space → surface. Colour carries *meaning*, never *rank* |
| **Icons** | 6 hand-rolled, three stroke weights, plus `✓`/`✕` text glyphs | One spec: 16px grid, 1.5px stroke, round caps/joins, outline only, no fills. ~14 icons. No text glyphs used as icons |
| **Interactive states** | Hover = colour; focus = nothing on buttons; disabled = opacity (~1.5:1) | Hover = one surface step + border warm; **focus = 2px signal ring, offset 2px, on everything**; disabled = muted surface + ≥3:1 text + `not-allowed` |
| **Colour** | `signal` used for tabs, links, buttons, pins, halos, borders, bar fills, chips | `signal` reserved for three roles only: **where you are**, **what to do next**, **something is live**. Semantic jade/brass/rust unchanged. Tag hues unchanged |

### 1.3 What will make it feel meaningfully newer — ranked

1. **Air around the one primary thing.** The largest single perceptual change, and it costs nothing but layout.
2. **Fewer lines.** Removing ~70% of the 1px borders and replacing them with surface steps is what breaks the wireframe look.
3. **A real primary action.** A solid `signal` fill, exactly one per screen. Today nothing looks like *the* action.
4. **The radius ladder.** 4px-everything reads as 2015; 6/10/14 reads as current — without becoming bubbly.
5. **Prose at 16px/1.7 in a 62ch measure.** The product is reading; it should look like it respects reading.
6. **Restraint in the accent.** Cutting `signal` from eight roles to three makes the remaining three actually mean something.
7. **200ms phase crossfades.** Not decoration — the mechanism that says *this replaced that*.
8. **One icon spec.** Small, but incoherent icons are a persistent low-grade signal of unfinished work.

Note what is *not* on this list: no new colours, no new fonts, no imagery, no
effects. The identity is preserved; the execution changes.

---

## 2. The core session screen

### 2.1 The frame

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ ◆ CodeOnboard   psf/requests · trace how a call becomes a response   7/12 ▸  ⚙ ⋯│  48px
├──────────────────┬───────────────────────────────────────────────┬──────────────┤
│ RAIL             │ BRIEF            (sticky)                     │ CONTEXT      │
│ 280px            │ ─────────────────────────────────────────────  │ 0px default  │
│ trench           │ CANVAS           (scrolls)                     │ opens on     │
│ always visible   │   · one primary artifact per phase             │ citation     │
│ collapsible      │   · action co-located with that artifact       │ click        │
│                  │ ink, measure-capped at 62ch, centred           │ trench       │
└──────────────────┴───────────────────────────────────────────────┴──────────────┘
```

Three things to notice:

- **The third column is closed by default.** Reclaiming 340px at every width is the
  single largest space win available, and it matches what `CLAUDE.md` already says
  about code being for reference.
- **The canvas is measure-capped and centred**, so surplus width becomes margin.
  Calm comes from the margins, not from the content stretching.
- **The brief is sticky; the canvas scrolls under it.** The answer to *what am I
  learning* never leaves.

### 2.2 Studying — the full picture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ ◆ CodeOnboard   psf/requests · trace how a call becomes a response   7/12 ▸  ⚙ ⋯│
├──────────────────┬──────────────────────────────────────────────────────────────┤
│ YOUR ROUTE    ⤢  │  CHAPTER 2 · STOP 4 OF 12              ⌀ 2 open   ⟳ 3   ⋯   │
│                  │                                                              │
│ ▸ The request    │  Understand the Session object                               │
│   lifecycle  3/3 │  Explain what Session owns that a bare request does not.     │
│                  │  ⟨⟩ requests/sessions.py 1–80  ·  +2 more                    │
│ ▾ Sending a      │ ─────────────────────────────────────────────────────────────│
│   request    1/4 │                                                              │
│   ● Understand   │   A Session is the object that owns everything a single       │
│     the Session  │   request cannot: the connection pool, the cookie jar and     │
│   ○ Adapters     │   the default headers…                                       │
│   ○ Connection   │                                                              │
│     pooling      │   ⟨⟩ Session.__init__  ·  sessions.py 1–80                    │
│   ○ Retry logic  │                                                              │
│                  │   …the practical consequence is that two calls through the    │
│ ▸ Reading the    │   same Session reuse one TCP connection.                      │
│   response   0/3 │                                                              │
│                  │  ┌────────────────────────────────────────────────────────┐  │
│                  │  │ QUESTION                                               │  │
│ ─────────────    │  │ What does sending through a Session change, and why?    │  │
│ 1 optional stop  │  │ ┌────────────────────────────────────────────────────┐ │  │
│ ⏱ session log    │  │ │ Answer this stop…                                  │ │  │
│                  │  │ └────────────────────────────────────────────────────┘ │  │
│                  │  │ ●━Submit answer━●   Skip this stop            ⌘↵      │  │
│                  │  └────────────────────────────────────────────────────────┘  │
└──────────────────┴──────────────────────────────────────────────────────────────┘
```

Key decisions visible here:

- **The question sits at the end of the prose**, where a reader naturally arrives.
  Read, then answer. It is a bounded card on `slab`, distinct from the prose.
- **Inline code citations** (`⟨⟩ Session.__init__`) sit in the prose as quiet
  affordances. Clicking one opens the context column. Today the only citation is a
  dashed link under the title.
- **The brief carries counters, not content.** `⌀ 2 open` and `⟳ 3` are disclosure
  triggers for gaps and attempt history. Those are two of today's inline blocks.
- **The rail is dense again.** Chapter title + `3/3` only; the chapter's purpose
  moves to the chapter overview and a tooltip. Today two-line descriptions consume
  47% of the rail.
- **`⏱ session log`** at the rail's foot — the adaptation timeline (§6.6).

---

## 3. The same screen, seven states

Only the canvas changes. The header, rail, brief and their positions do not. That
is the proposition being tested here.

### A. Studying
```
BRIEF   Stop 4 of 12 · Understand the Session object   ⌀2  ⟳3
CANVAS  [ setup prose ................................. ]
        [ QUESTION card + composer + ●Submit answer     ]
```
*Stable:* everything in the brief. *Primary:* the prose. *Action:* Submit answer.

### B. Answering
```
BRIEF   Stop 4 of 12 · Understand the Session object   ⌀2  ⟳3
CANVAS  [ setup prose ......................... dimmed 3% ]
        [ QUESTION card                                  ]
        [ ┌ composer, expanded to 5 rows ──────────────┐ ]
        [ ●━Submit answer━●  Skip            ⌘↵         ]
```
*Changes:* composer expands in place; prose steps back by one surface value — a 3%
shift, not a scrim. *Nothing moves.* *Stable:* brief, rail, prose position.

### C. Incorrect answer → feedback
```
BRIEF   Stop 4 of 12 · Understand the Session object   ⌀3↑ ⟳4
        └ status strip:  ⬤ Not yet — on connection reuse
CANVAS  [ ▸ Setup — what you read before answering      ]   ← collapsed to 1 line
        [ ┌─ FEEDBACK ─────────────────────────────────┐ ]
        [ │ ⬤ NOT YET                                  │ ]
        [ │ You've got the cookie jar right, but…      │ ]
        [ │ ── Because connection reuse tripped this   │ ]
        [ │    up, I've added a shorter stop first.    │ ]
        [ │ ●━Start the warm-up━●  Skip it  Move on    │ ]
        [ └────────────────────────────────────────────┘ ]
        [ EXPLANATION                                    ]
        [ …the full reveal, legitimately long………………      ]
```
*Changes:* the composer **morphs in place** into the feedback card (200ms). Setup
collapses to one line. The gap counter increments with a brass pulse.
**Crucially: the primary action lives inside the feedback card, above the long
explanation** — so it is never separated from the verdict by 777px of prose. The
explanation is supporting material the learner may scroll into.
*Stable:* brief identity, rail, canvas position of the feedback card (scroll-anchored).

### D. Warm-up inserted
```
RAIL    ▾ Sending a request  1/4
          ● Understand the Session       ← still current
          ┆ ⟡ Straight-line distance…    ← slides in, 320ms, dashed, "added for you"
          ○ Adapters
CANVAS  (unchanged from C — the offer is in the feedback card)
```
Then on accepting:
```
BRIEF   ⟡ DETOUR · warm-up for “Understand the Session”   ← eyebrow changes
        Straight-line distance and the locations dict
        ← back to “Understand the Session”                 ← permanent return path
CANVAS  [ warm-up setup prose ]
        [ QUESTION + composer + ●Submit answer ]
```
*Changes:* the brief's eyebrow changes character from `STOP n OF m` to `DETOUR`,
carrying a permanent return affordance. *Stable:* the entire frame; the rail still
shows the original stop above, so the round trip is legible.

### E. Gap discovered
```
BRIEF   Stop 4 of 12 · Understand the Session object   ⌀3↑ ⟳4
                                                        └ pulses brass once
CANVAS  feedback card names it in prose:
        “You're carrying one assumption that isn't true: that a
         connected graph means None is impossible.”
```
Opening `⌀ 3` slides out a panel over the context column:
```
┌ OPEN GAPS ─────────────────────── 3 ─┐
│ ⌀ blocking                            │
│ Missing locations degrade A* to UCS    │
│ ●Check this   Set aside                │
│ ─────────────────────────────────────  │
│ ⌀ A connected graph can't return None  │
│ ●Check this   Set aside                │
└───────────────────────────────────────┘
```
*Changes:* a counter, a pulse, a sentence, and an on-demand panel. **No inline
block.** *Stable:* everything else.

### F. Verification
```
BRIEF   Stop 4 of 12 · Understand the Session object   ⌀3 ⟳4
        └ status strip:  ◌ checking — “connected graph ⇒ no None”
CANVAS  [ ▸ Setup                                       ]
        [ ▸ Your last answer — Not yet                   ]   ← feedback collapsed
        [ ┌─ A DIFFERENT ANGLE ────────────────────────┐ ]
        [ │ You create a GraphProblem where every room │ ]
        [ │ connects to every other room…              │ ]
        [ │ ┌ composer ───────────────────────────────┐│ ]
        [ │ ●━Submit━●    Not now                     │ ]
        [ └────────────────────────────────────────────┘ ]
```
*Changes:* a phase swap. The previous feedback collapses to one line. **The
original question and composer are gone from the DOM** — there is exactly one
composer and exactly one `Submit` on the screen. *Stable:* brief, rail, frame.

This is where the "stable frame, changing focus" idea earns its keep: compare with
today, where this state has two textareas 497px apart, two buttons both labelled
`Submit`, an invisible question at 1.00:1 contrast, and a 2845px column.

### G. Resolved / returning to route
```
BRIEF   Stop 4 of 12 · Understand the Session object   ⌀2↓ ⟳5
        └ status strip:  ✓ demonstrated
CANVAS  [ ┌─ CLEARED ───────────────────────────────────┐ ]
        [ │ ✓ That's cleared — you've got the failure   │ ]
        [ │   mode right now.                           │ ]
        [ │ ── Back to “Understand the Session object”.  │ ]
        [ │ ●━Return to the route━●   Review this stop  │ ]
        [ └─────────────────────────────────────────────┘ ]
        [ ▸ Setup   ▸ Explanation   ▸ Your answers (5)     ]
RAIL    current pin travels back up, 450ms; warm-up row settles as a record
```
*Changes:* counter decrements with a jade pulse; everything historical is a row of
one-line disclosures. *Stable:* frame; the rail keeps the detour visible as
evidence that something was worked through.

### What this demonstrates

Across all seven states: the header never changes, the rail changes only when the
route changes, the brief keeps its identity and gains a one-line status strip, and
the canvas holds exactly one primary artifact with its action attached. The
learner's eye never has to re-find anything.

---

## 4. Action bar: A vs B vs C

`ui-direction.md` recommended a permanently docked action bar. Having laid out the
states above, I no longer think that is right. Here is the honest comparison.

### The options

**A — Permanently docked action/composer.** A fixed bar at the bottom of the
workspace holding the composer and the primary action in every phase.

**B — Inline contextual.** The composer and action live in the flow, inside the
card for the current phase, positioned where that phase's content naturally ends.

**C — Inline, with a conditional dock.** B, plus a slim one-row bar that appears
only while the primary action is scrolled out of view, and retracts when it is not.

### Evaluation

| Criterion | A — docked | B — inline | C — inline + conditional |
|---|---|---|---|
| **Long-form reading** | Poor. Costs ~120px permanently — 19% of a 634px content height — and a persistent composer beside prose reads as a chat app, which this is not | **Good.** Full height for reading; the composer appears where reading ends | **Good.** Same as B |
| **Answering** | Good. Always in the same place | **Good.** Arrived at naturally, after the prose — which is the pedagogical order | Good |
| **Feedback** | Adequate. Feedback appears in the bar, but the bar is small; a rationale plus a consequence sentence plus three buttons is not a bar | **Good.** The card morphs in place and has room for verdict, rationale, consequence and actions | Good |
| **Retry / verification** | Adequate | **Good.** Phase swap replaces the card in place | Good |
| **Laptop height (720–800px)** | Worst case. On a 634px content height, 120px of dock leaves 514px of canvas | **Best.** Nothing reserved | Good; the dock appears only transiently |
| **Cognitive focus** | Split. Two loci — the canvas and the bar — always competing | **Single locus.** The thing you are reading and the thing you do next are the same card | Single locus, with a fallback |
| **Discoverability of next action** | **Best.** Guaranteed on screen | Good *if* the action is co-located with its artifact; poor if it is stranded after a long reveal | **Best.** Guaranteed, without the permanent cost |
| **Implementation cost** | Low | Low | Medium — needs an intersection observer and careful retract logic |

### Recommendation: **B, structured so that A's guarantee is not needed — with C as a later safety net.**

The discoverability worry that motivated A is real, but it is caused by *action
placement*, not by the absence of a dock. Today the verdict's buttons sit after a
777px reveal; that is what put them 2080px away. The fix is to **put the primary
action inside the feedback card, above the explanation** — as drawn in state C
above. Then the action is adjacent to the verdict by construction, and a dock has
nothing left to solve.

Two supporting rules make B safe:

1. **Scroll anchoring on phase change.** When the composer morphs into the feedback
   card and the setup collapses above it, the card must stay visually put. The
   content above changes height; the scroll position compensates. Without this rule
   B fails and A starts looking necessary again.
2. **The primary action is never below a long-form artifact.** Long artifacts
   (explanation, source) always come *after* the action, never between the verdict
   and its action.

**Add C only if testing shows a real problem.** It is a genuine improvement over
both, but it introduces a transient element that will look cheap if it is janky,
and it should not be built before we know it is needed.

**The explicit tradeoff:** B gives up the absolute guarantee that the next action
is on screen. In exchange it gives up nothing of the reading experience, keeps one
locus of attention, and costs no permanent vertical space on the laptop screens
that are the primary target. Given that this product's core activity is *reading
carefully and then committing to an answer*, I would not spend 19% of the canvas
on a guarantee that correct action placement provides for free.

---

## 5. The scrolling principle, refined

`ui-direction.md`'s "≤2× viewport" was a useful forcing function and a bad rule. A
long lesson *should* be long. Replacing it with a distinction:

### Legitimate scrolling — content the learner chose

- Lesson setup prose and the explanation/reveal
- The source file in the context column
- The chapter overview's objectives and lesson list
- The map's review content
- The session log

Legitimate scrolling scales with how much there is to learn. It is not a defect,
and at 16px/1.7 there will be *more* of it than today. That is the correct trade.

### Illegitimate scrolling — interaction history left expanded

- A composer that has been answered
- A verdict that has been superseded
- Setup prose still expanded after the explanation has landed
- Attempt history rendered inline
- The gap list rendered inline
- Duplicate controls for the same intent
- Adaptation notices from earlier phases

Every measured pathology in the baseline is in this second list. Today's 2845px
worst case is roughly 1,050px of legitimate content and 1,800px of expanded dead
state.

### The invariants that replace the cap

1. **One interactive input in the DOM per phase.** (Kills the twin composers.)
2. **Superseded artifacts occupy one line each**, collapsed by default, always —
   including on revisit.
3. **The primary action is within one viewport of its phase's primary artifact**,
   and never separated from it by a long-form artifact.
4. **History, gaps and evidence never render inline** — they are counters that open
   panels.
5. **Soft budget:** non-content chrome ≤25% of the workspace's scroll height. A
   diagnostic, not a gate.

A lesson may legitimately be four screens of prose. It may never be four screens
of things the learner has finished with.

---

## 6. Adaptation, made visible

Three coordinated channels (`ui-direction.md` §3), here made concrete. The design
intent is *quietly intelligent* — the feeling of a good tutor noticing something,
not a game rewarding you.

### 6.1 Warm-up added

**Workspace** — inside the feedback card, below the rationale, separated by a short
rule (not a boxed callout, which would read as an alert):

```
    ── Because connection reuse tripped this up, I've added a
       shorter stop on it before this one.
    ●━Start the warm-up━●    Skip it    Move on anyway
```

**Rail** — the row slides in beneath the current stop over 320ms: indented one
level, joined by the existing dashed prerequisite connector, tagged `added for
you`, with a single 600ms signal pulse on the marker and then stillness.

```
  ● Understand the Session
  ┆ ⟡ Straight-line distance…   added for you      ← new
  ○ Adapters
```

**Log** — `14:22 · Added warm-up “Straight-line distance…” before “Understand the Session”`

### 6.2 Gap discovered

**Workspace** — named in the verdict prose, not in a separate block: *"You're
carrying one assumption that isn't true: that a connected graph means `None` is
impossible."*

**Brief** — `⌀ 2 open` → `⌀ 3 open`, with one brass highlight sweep across the
counter (200ms). No badge, no bounce.

**Rail** — the current row gains a small brass dot at its right edge. Persistent
while gaps are open; it is a state, not an alert.

### 6.3 Gap resolved

**Workspace** — a `CLEARED` card, jade-toned: *"That's cleared — you've got the
failure mode right now."*

**Brief** — counter decrements; one jade pulse. On the last gap closing, the
counter transforms into `⌀ all clear` and holds for the rest of the stop.

**Panel** — the closed gap stays listed, struck through, labelled `Closed`. This is
deliberate: today the row simply vanishes, so *fixing* something looks identical to
it never having existed. Keeping the record is what makes progress feel real.

### 6.4 Verification required

**Workspace** — the phase swap itself is the announcement, preceded by one sentence
in the feedback card: *"I'd rather not take that as proof. One different question on
the same idea."*

**Brief** — the status strip shows `◌ checking — "connected graph ⇒ no None"`, the
hollow ring being the one shape the state vocabulary already reserves for
"no evidence either way".

### 6.5 Returning to the original route

**Workspace** — *"Back to `Understand the Session object`."* with
`●Return to the route` primary.

**Rail** — the current pin travels from the warm-up row back up to the original
stop over 450ms. The travel is the point: it is the one moment where the learner
literally sees the route move them back.

### 6.6 The session log

Reached from the rail's foot or the `⋯` menu. Reverse-chronological, one line per
event, using the same icons as the rail:

```
┌ SESSION LOG ──────────────────────────────────┐
│ 14:31  ✓  Gap closed — “connected graph ⇒ …”  │
│ 14:28  ◌  Verification requested              │
│ 14:22  ⟡  Warm-up added before “Understand…”  │
│ 14:22  ⌀  Gap opened — “missing locations …”   │
│ 14:05  ✎  Lesson re-taught around the misfire  │
│ 13:58  ⤓  2 stops pruned — already demonstrated│
└───────────────────────────────────────────────┘
```

The data already exists as `journey_events_json`. This surface is what converts
"the system changed something" into "I can see everything it has done for me" — and
it is cheap.

### 6.7 Rules that keep it calm

One notice at a time, composed into a single sentence when several things happen at
once. Never a modal. Never a disappearing toast. Never rust for adaptation — brass
opened, jade closed, signal route-changed. Every proposal refusable in the same
breath. One pulse, then stillness — nothing repeats or loops. `new` markers clear
when the rail is actually looked at, not on a timer.

---

## 7. Proposed visual-system values

Proposals for review, not commitments.

### 7.1 Lesson prose — size, leading and measure together

Evaluated as one decision, since changing size alone is meaningless.

| Option | Size | Leading | Measure | Chars/line | Assessment |
|---|---|---|---|---|---|
| Current | 13.5px | 1.72 | 62ch (~459px) | ~65 | CPL is fine; the *type* is two steps too small for sustained reading |
| a | 15px | 1.65 | 64ch (~540px) | ~68 | Safe, modest gain |
| **b (recommended)** | **16px** | **1.70** | **62ch (~560px)** | **~66–70** | Comfortable, calm, squarely in the 60–75 optimum |
| c | 17px | 1.60 | 60ch (~575px) | ~64 | Generous but starts to feel large-print in a dev tool |

**Recommendation: 16px / 1.70 / 62ch.** Rationale: 66–70 CPL sits in the middle of
the comfortable range; 1.70 leading at 16px gives 27px of rhythm, which is what
makes a long explanation feel calm rather than dense; and 62ch caps the measure so
surplus width becomes margin instead of over-long lines.

**Consequence, stated plainly:** the same lesson becomes roughly 18–20% taller than
today. That is legitimate content scrolling (§5) and it is the trade being
deliberately made. Anyone uncomfortable with it should prefer option (a) rather
than narrowing the measure, because narrowing below ~60ch trades one readability
problem for another.

### 7.2 Type scale

| Token | Size | Leading | Weight | Role |
|---|---|---|---|---|
| `text-micro` | 11px | 1.40 | 500 | Mono uppercase eyebrow — one per zone, tracking 0.12em |
| `text-xs` | 12.5px | 1.50 | 400 | Metadata, counts, file paths, timestamps |
| `text-sm` | 14px | 1.55 | 400/500 | Rail stops, captions, secondary body |
| `text-body` | **16px** | **1.70** | 400 | Lesson prose |
| `text-lg` | 18px | 1.50 | 500 | Callout titles, question text, sub-heads |
| `text-xl` | 22px | 1.35 | 500 | Brief title, panel titles |
| `text-2xl` | 28px | 1.25 | 500 | Chapter titles, map headline |
| `text-display` | 36px | 1.15 | 500 | Landing wordmark, completion |

Eleven sizes → eight, with every adjacent pair separated enough to be seen. Serif
for `text-xl` and above, sans for prose, mono for `text-micro` and `text-xs`
factual values. Keep the `calc(N rem/16)` authoring form — it is what makes
`--ui-scale` work.

### 7.3 Spacing

4px base. `1`=4 · `2`=8 · `3`=12 · `4`=16 · `5`=24 · `6`=32 · `7`=48 · `8`=64.

Applied: zone padding `5`/`6`; card padding `4`/`5`; between sibling blocks `5`;
within a group `2`/`3`; around the canvas's primary artifact `6`/`7`. Ends today's
per-file drift where the same relationship is `gap-6`, `gap-7` and `gap-9`.

### 7.4 Radii

`xs` 3px (tag chips) · `sm` 6px (inputs, small buttons, status chips) · `md` 10px
(buttons, cards, callouts) · `lg` 14px (panels, sheets, source pane) ·
`full` (pins, tracks, counters).

### 7.5 Surfaces and elevation

| Level | Dark | Light | Border | Shadow | Use |
|---|---|---|---|---|---|
| `elev-0` | `ink` #0a1014 | #e7eef3 | — | — | Page |
| `elev-1` | `trench` #0c1318 | #dbe5ec | — | — | Rail, panels, inputs |
| `elev-2` | `slab` #131c23 | #f3f8fa | light only, 1px | `0 1px 2px rgba(0,0,0,.28)` / `0 1px 3px rgba(16,42,58,.10)` | Content cards |
| `elev-3` | `raise` #1a252d | #f3f8fa | 1px `rule` | `0 12px 32px rgba(0,0,0,.42)` / `0 12px 28px rgba(16,42,58,.16)` | Popover, sheet, floating pane |

Dark separates by lightness; light by shadow. No new colour values — the existing
tokens, finally used as a ladder.

### 7.6 Buttons

| Variant | Fill | Text | Border | Use |
|---|---|---|---|---|
| `primary` | **solid `signal`** | `ink` | — | The one action per phase |
| `secondary` | `elev-2` | `chalk` | 1px `rule` | Alternatives |
| `tertiary` | — | `graphite` → `chalk` | — | Dismissals, "move on anyway" |
| `danger` | — | `rust` | 1px `rust`/40 | Destructive, always confirmed |

Sizes: `sm` 28px / `md` 36px / `lg` 44px. Radius `md`. Horizontal padding `4`
(`sm`: `3`). One padding per size, ending today's six.

*On the accent-reservation rule:* filled `signal` for actions and outlined
`signal` + halo for the current pin are two treatments of one hue in two roles that
never co-occur — *what to do* and *where you are*. The reservation holds.

### 7.7 Inputs

`elev-1` surface, 1px `rule`, radius `sm`, `text-body`, padding `3`. Placeholder
`graphite`. Focus: 2px `signal` ring at 2px offset — **replacing** today's
`focus:outline-none` plus a barely-visible border tint. Collapsed composer 44px;
expanded 5 rows. One component, two states.

### 7.8 Disabled and focus

**Disabled:** `elev-1` surface, `graphite` text at ≥3:1, `cursor: not-allowed`,
`aria-disabled`. Never opacity alone — today's `opacity: .3` on `Back` composites to
~1.5:1 and reads as absent rather than unavailable.

**Focus:** `outline: 2px solid var(--color-signal); outline-offset: 2px` on
`:focus-visible`, on **every** interactive element. Today only the source-pane
divider has one.

### 7.9 Content widths

Lesson prose 62ch (~560px) · canvas cards match the prose measure · brief full
canvas width · panels 380–420px · source pane 380px docked · pre-session column
560px, widening to 880px at the briefing.

---

## 8. The pre-session flow

Equal attention, as asked. The governing idea: **one column that deepens**, not
five pages.

### 8.1 The continuity device

A single centred column persists from landing to first lesson. Context the learner
has supplied accumulates at its top as compact, editable one-liners; the active
thing is always below them, large. Nothing ever "navigates" — the column's contents
change.

Then the payoff: **the route preview shown at the briefing physically becomes the
rail.** On `Start`, the chapter list animates from centre-column to left-rail
position while the workspace frame fades in around it. That shared-element move is
what makes "the system built me a route" and "I am in the workspace" one continuous
thought instead of two pages.

```
LANDING          INTERVIEW           GENERATING          BRIEFING          SESSION
┌──────────┐    ┌──────────┐        ┌──────────┐        ┌────────────┐   ┌──┬───────┐
│          │    │ ▪ repo   │        │ ▪ repo   │        │ ▪ repo     │   │▪ │       │
│  ◆       │    │ ▪ ans 1  │        │ ▪ profile│        │ ▪ profile  │   │▪ │       │
│  input   │ →  │ ▪ ans 2  │   →    │──────────│   →    │ briefing ¶ │ → │▪ │ lesson│
│          │    │ ┌──────┐ │        │ ✓ stage  │        │ ▪ chapters │   │▪ │       │
│          │    │ │ Q 3  │ │        │ ◐ stage  │        │ ●Start     │   │▪ │       │
└──────────┘    └──────────┘        └──────────┘        └────────────┘   └──┴───────┘
   560px           560px               560px               880px          rail+canvas
                                                       chapters ─────────────┘
                                                       animate into the rail
```

### 8.2 Landing

**Now:** wordmark 38px, tagline, mono label, 46px input, recents as bordered chips,
tinted `Start`. Functional and plain; no sense of what is about to happen.

**Proposed:**

```
                          ◆
                     CodeOnboard

        Build a real understanding of an unfamiliar
          codebase, one anchored concept at a time.


        ┌──────────────────────────────────────────┐
        │ github.com/psf/requests                  │
        └──────────────────────────────────────────┘
              ●━━━━━━━ Start ━━━━━━━●

        Five short questions, then two to four
        minutes while we read the repository.

        RECENT   psf/requests   fastapi/fastapi
```

Changes: more air (the block sits at ~40% height, not centred); input at `lg`
(44px) with `radius-md`; a solid primary; and — most importantly — **the
expectation is set before the wait exists**. A 2–4 minute wait that was announced
is a different experience from one that is discovered.

### 8.3 Goal interview

**Now (measured):** the tick bar is 2px; option chips and the `Back` button are
pixel-identical (13px/400, graphite, 1px `rule`); disabled `Back` sits at
`opacity: .3` ≈ 1.5:1; every question looks the same; previous answers are
invisible; and `Continue` is required even for single-select.

That is a form, and the user's diagnosis is right: it feels static.

**Proposed:**

```
        psf/requests                                    2 of 6
        ─────────────────────────────────────────────────────
        ✓ Familiarity      Looked at some code but confused  ✎
        ✓ Goal             Understand a component            ✎
        ─────────────────────────────────────────────────────


           How deep into the implementation
           do you want to go?


           ┌─────────────────────────────────────────────┐
           │  Just the map — where things live           │
           ├─────────────────────────────────────────────┤
           │  Working knowledge — enough to use it     ✓  │  ← selected
           ├─────────────────────────────────────────────┤
           │  Implementation — how it actually works     │
           └─────────────────────────────────────────────┘

           Back                                    ⌘↵ to continue
```

The specific decisions:

- **Answered questions collapse upward into a transcript.** One line each, with a
  `✎` to revisit. This fixes the invisible-history problem, and it is the device
  that makes the interview feel conversational: the column accumulates *what you
  said*, not what you were asked. Growth is ~28px per question — legitimate
  context, not dead state.
- **Options become full-width rows**, 44px minimum, left-aligned, stacked not
  wrapped. Wrapped chips of unequal width read as a tag cloud; a stack reads as a
  choice.
- **Selected state is unambiguous:** `signal`-tinted surface + 1px `signal-dim`
  border + a trailing check. Unselected is `elev-1` with no border until hover.
  Never again identical to a navigation control.
- **Single-select auto-advances** ~250ms after selection, with the choice visibly
  settling into the transcript. No `Continue` for fixed-vocabulary questions —
  which removes the most form-like element in the flow. Free-text keeps `Continue`
  and `⌘↵`.
  *Decision to confirm:* auto-advance is the single biggest "conversational" win,
  but it removes a beat for reconsidering. Mitigated by the editable transcript and
  `Back`. Worth a prototype.
- **Action hierarchy:** for single-select there is no primary button at all — the
  options *are* the action. For free-text, `Continue` is primary and `Back` is
  tertiary text. `Back` is **absent** on Q1 rather than present-but-invisible.
- **Progress:** `2 of 6` as plain text, plus the transcript itself. No filling bar
  — a bar implies a percentage, and the honesty discipline in this product says
  don't imply measurements you don't have.
- **Transitions:** always upward, always the same. Answer settles into the
  transcript (200ms); question leaves upward with a fade (150ms); next question
  arrives from 8px below with a fade (200ms). One consistent direction of travel
  builds the feeling of progress better than any bar.

### 8.4 Generation — the wait as part of the product

The current `StartingProgress` is the best-designed thing in the product: real
stages, real tool calls, a bar that counts *completed stages* rather than guessing,
an elapsed counter that prefers the server's own timing. **This is an evolution, not
a replacement.**

The problem is not honesty — it is *continuity and payoff*. Today it is a separate
screen that vanishes, and everything it showed is thrown away.

**Proposed:**

```
        psf/requests                                    1m 48s
        ─────────────────────────────────────────────────────
        ✓ Familiarity      Looked at some code but confused
        ✓ Goal             Understand a component
        ✓ Depth            Working knowledge
        ─────────────────────────────────────────────────────

        Building your route

        ✓  Read the repository        84 files · 6 modules
        ✓  Gathered documentation
        ◐  Following your goal        ⟨⟩ sessions.py
           ├ requests/sessions.py
           ├ requests/adapters.py                    ← accumulates, real
           └ requests/models.py
        ○  Planning the route

        Usually two to four minutes.
```

The design moves:

1. **Same column, same transcript.** The profile stays visible while the system
   works. The learner is watching something being built *from what they said* — the
   single most important perceptual change, and it costs nothing.
2. **Real artifacts appear and persist as stages complete.** `84 files · 6 modules`
   is real survey output. The accumulating file list is the exploration's real tool
   calls — already streamed today, but discarded. They stay, because they are the
   first evidence that the route is grounded in this repository.
3. **By the end, the screen has already become the briefing.** The chapters appear
   under `Planning the route` as they are known. There is no page swap — the
   briefing is what this screen *grew into*. This is the direct answer to "can
   useful information appear before the process is complete": yes, and it is the
   mechanism that makes the whole flow continuous.
4. **Discrete stage pips, not a bar.** The current bar is honest (stages completed)
   but *looks* like a percentage. Four explicit stage rows with `✓ / ◐ / ○` say the
   same thing without the implication. Consistent with the product's existing
   two-grammars principle.
5. **Expectation, then honesty if exceeded.** "Usually two to four minutes." If it
   passes five, the line changes to "Taking longer than usual — still working."
   Never a fabricated estimate.
6. **Motion:** exactly two things move — a stage flipping to `✓`, and new content
   fading in. One small live indicator on the active stage. No shimmer, no skeleton,
   nothing that exists to occupy the eye.

Explicitly not done: no invented percentages, no invented stages, no progress that
advances on a timer, no technical detail beyond named files the learner could
themselves open.

### 8.5 Briefing / Welcome

**Purpose:** confirm the system understood, and show where the learner is going. Not
a splash screen — the last state of the build, and a page they can return to.

**Now:** a separate route with its own header, a briefing paragraph, a notes list, a
profile card, and a `Begin` button. In the state I could actually observe (the
running backend predates the endpoint) it was 444px of content in a 720px viewport
— sparse, with no connection to the route that had just been built.

**Proposed:** the column widens from 560px to 880px and gains the route.

```
        psf/requests                                          ⚙
        ─────────────────────────────────────────────────────────────
        Here's what I found, and where we'll go

        ┌───────────────────────────────────┐  ┌──────────────────┐
        │ WHAT YOU'RE ABOUT TO READ         │  │ YOUR PROFILE     │
        │                          tailored │  │                  │
        │ requests wraps urllib3 behind a   │  │ Understand a     │
        │ small, deliberate API. Almost     │  │ component        │
        │ everything you care about passes  │  │ New to it        │
        │ through Session.send…             │  │ Working knowledge│
        │                                   │  │                  │
        │ · Session owns the pool and jar   │  │ GOAL             │
        │   requests/sessions.py            │  │ trace how a call │
        │ · Adapters do the transport       │  │ becomes a resp…  │
        │   requests/adapters.py            │  │                ✎ │
        └───────────────────────────────────┘  └──────────────────┘

        YOUR ROUTE                              16 stops · 6 chapters
        ▸ 1  The request lifecycle                            3 stops
        ▸ 2  Sending a request                                4 stops
        ▸ 3  Reading the response                             3 stops
        ▸ 4  Adapters and transport                           2 stops
        …

        ●━ Start with “Map the Session object” ━●      Review my answers
```

Decisions:

- **Emphasis order:** the briefing paragraph first (it is the thing only this system
  can give them), then the route, then the profile. The profile is *checkable*, not
  celebrated — and it carries a `✎` that actually leads somewhere, unlike today
  where disagreeing with it means finding `Start over` on another page.
- **The route is rendered with the same `RouteItem` primitive as the rail**, at
  chapter granularity only. Chapters expand to show stops on demand. Showing all 16
  stops here would pre-empt the journey.
- **The primary action names the first lesson.** "Start with *Map the Session
  object*" tells the learner exactly what happens next; `Begin` does not.
- **Page or transition?** Both, and that is deliberate: it is the final state of the
  build *and* a standalone route reachable from the session `⋯` menu, rendering the
  same content. Continuity for first-time use; permanence for reference.
- **How much before the first lesson:** roughly 1.2 screens. Paragraph, two or three
  grounded notes with real file paths, chapter list, profile. Not every objective,
  not every stop.

### 8.6 The transition into the workspace

On `Start`, over ~450ms:

1. The briefing card and profile fade out (150ms).
2. The chapter list **moves** from the centre column to the rail's position,
   scaling down to rail type as it goes (300ms, `motion-route` easing).
3. The workspace frame — header bar, canvas, brief — fades in around it (200ms,
   overlapping).
4. The first stop's brief and prose arrive.

The learner never sees a blank page or a page swap. The route they were just shown
is the route they are now standing in. Under `prefers-reduced-motion` this becomes a
120ms crossfade with the rail already in place — the information is identical, only
the movement is removed.

### 8.7 Consistency, with permission to be more spacious

The pre-session screens use the *same* tokens — type scale, spacing, radii,
surfaces, buttons, focus rings — with two deliberate differences:

- **One column, 560px, centred**, versus the session's three zones. Pre-session is
  a conversation; the session is a workspace.
- **Looser vertical rhythm:** `space-7`/`space-8` between blocks rather than
  `space-5`. There is only one thing to do at a time, and the extra air is what
  makes it feel calm rather than empty.

No new colours, no new type, no separate visual language. Same instrument, fewer
dials on display.

---

## 9. Preserve vs change

### Preserve

**Identity and palette**
- The `@theme` CSS-variable architecture and the value-swap theme mechanism
- Every existing colour value: `ink`/`trench`/`slab`/`raise`/`rule`,
  `chalk`/`paper`/`graphite`, `signal` family, `jade`/`brass`/`rust`, code-pane trio
- The one-accent rule (tightened from eight roles to three, not abandoned)
- All eight concept-tag hue families in both themes — measured 5.22–8.54:1, they work
- The light theme's "blueprint paper" character; it must not become a white wash-out
- The three-family type pairing and each family's role: serif asserts, mono measures,
  sans explains

**Structure and semantics**
- `understandingStyle` as the single state vocabulary across rail, overview, map,
  drawer — and shape-plus-colour encoding, including dashed `insufficient`
- The two progress measures and their two grammars (fraction for mastery, discrete
  track for the journey)
- `optional` meaning excluded-from-the-walk, not removed
- The rail's four-questions restraint (restored, in fact)

**Behaviour and craft**
- The `--ui-scale` dial and `calc(N rem/16)` relative authoring
- The withheld reveal — gated on committing to an answer, open on revisit
- The honesty discipline throughout: real stages not fake percentages, fractions not
  calibrated-sounding scores, "tailored or generic" labelling, evidence behind every
  claim, "no source, no lesson"
- `StartingProgress`'s real-work reporting, real tool-call streaming, and
  server-preferred elapsed time
- The source pane's dock/float, drag, keyboard resize, viewport re-placement, and
  its CSS-variable-during-drag performance approach
- The code pane's short-hop-only smooth scroll rule
- Copy centralization in `strings.ts`, with parsed keys separate from labels
- Esc-to-close everywhere; `aria-current`; `sr-only` state text; `aria-live` on
  progress; global `prefers-reduced-motion`

### Change

**Defects (not taste)**
- The gap and verification surfaces' inverted/undefined tokens — 1.00:1 question,
  1.11:1 submit, 1.97:1 controls, 1.64:1 in light
- Twin composers bound to one state and two buttons both labelled `Submit`
- Missing focus-visible on every button
- Disabled-by-opacity at ~1.5:1

**Structure**
- Accumulating column → stable frame + one changing focus, driven by a phase model
- Feedback below everything → feedback morphs in place, with its action attached
- Gaps, attempt history, evidence as inline blocks → counters that open panels
- Source pane open by default → opens on citation click
- Nine-group header → four zones, with the goal guaranteed a minimum width
- Scope, briefing, start-over, finish → into a `⋯` menu
- `Finish early` as a footer link → menu item with confirmation
- Map duplicating the route as a 2300px timeline → a review surface; the rail is the route
- Chapter overview silently replacing the lesson → an explicit layer with a way back
- Fixed three-column shell → four responsive bands with a 560px lesson floor

**Visual system**
- Eleven type sizes in a 6.5px band → eight steps with perceptible gaps
- Prose 13.5px → 16px/1.70/62ch
- Mono-uppercase micro-label at six hierarchy levels → one per zone
- Universal 4px radius → 3/6/10/14/full
- No elevation → a four-level surface ladder, shadow at the top two only
- Borders as the definition of every box → borders rare and meaningful
- 15%-tint "primary" → solid `signal` fill, exactly one per phase
- Four equal buttons after a wrong answer → one primary, one secondary, one tertiary
- Per-file spacing drift → one spacing scale
- Six hand-rolled icons at three stroke weights plus text glyphs → one 16px/1.5px spec

**Pre-session**
- Five discrete pages → one column that deepens, with shared-element continuity
- Form-like interview → transcript + full-width options + auto-advance on single-select
- Identical-looking option chips and `Back` → clearly distinct roles
- Wait as a screen that vanishes → wait as the thing the briefing grows out of, with
  real artifacts accumulating
- Stage bar that looks like a percentage → discrete stage rows
- Briefing disconnected from the route → briefing shows the route, which animates
  into the rail
- `Begin` → `Start with "<first lesson>"`

**Adaptation**
- Silent graph mutations → the three-channel grammar (sentence, rail mark, log)
- Three stacked mono status lines → one composed consequence sentence
- Gap rows that vanish when resolved → closed gaps retained, struck through
- No record of what the system did → the session log

---

## 10. Open questions before implementation

1. **Auto-advance on single-select** (§8.3) — the biggest conversational win, but it
   removes a beat for reconsidering. Prototype both.
2. **Action bar B vs C** (§4) — recommend B now, add the conditional dock only if
   testing shows stranded actions.
3. **Prose at 16px** (§7.1) — makes lessons ~18–20% taller. Accept, or take 15px?
4. **Does the explanation need a `Key point` summary** above the full reveal? It is
   the longest artifact and a two-line summary would help scanning — but it risks
   letting the learner skip the reasoning.
5. **Chapter overview: sheet, or a fifth canvas phase?** The auto-open on chapter
   entry argues for a phase.
6. **How long do rail `new` markers persist?** "Until the rail is looked at" needs a
   definition that is not a timer.
7. **Should the session log be a panel or a route?** Panel keeps context; route is
   linkable and has room.

---

## 11. What this document does not do

No component APIs, no file layout, no token values in code, no copy. Those belong to
the implementation plan, which should not begin until this concept has been argued
with and the §10 questions have answers.
