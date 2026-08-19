# UI/UX Direction — A Learning Workspace

> **Status:** design proposal. No production code, styling, copy or component changed.
> **Baseline:** [`ui-baseline.md`](ui-baseline.md) — code audit (§1–§8) and live
> browser validation (§10). Every problem referenced here as `B-n` or `L-n` is
> evidenced there.
> **Purpose:** define the design language and the interaction model, concretely
> enough to become tokens and primitives — and to be argued with before anything
> is built.
> **Last updated:** 2026-08-19

---

## 0. The thesis

The product today is **a document that accumulates**. Every new fact — a gap, a
verdict, a reveal, a verification — is appended to one column, which reaches
2845px in a 634px viewport and puts the consequence of a click 2080px away from
the click.

The product should be **a workspace with a stable frame and one changing focus**.

That single change — from *append* to *replace within a frame* — resolves most of
the baseline's structural findings at once. It is not a restyle of `LessonPanel`;
it is a different model of what the lesson column *is*.

Three questions must be answerable at every instant, without scrolling:

| Question | Answered by | Position |
|---|---|---|
| What am I learning right now? | **Brief** | sticky top of the workspace |
| What just happened? | **Canvas** + brief's status strip | centre |
| What should I do next? | **Action bar** | docked bottom |

Everything else — history, gaps, source, evidence, the map — is *context*, and
context is summoned, not stacked.

### What is explicitly preserved

The baseline identified real strengths, and they are load-bearing here:

- The CSS-variable token architecture and the theme mechanism (§4.1)
- The palette's semantics and the one-accent rule (§4.2) — with one refinement, §5.7
- `understandingStyle` as the single state vocabulary across rail, map, overview
  and drawer (§4.4), and shape-plus-colour encoding (§4.5)
- The `--ui-scale` dial and relative type (§4.3)
- The honesty discipline: fractions over percentages, real progress over fake
  progress, evidence behind every claim (§4.6)
- The rail's restraint — four questions and no more (§4.8)
- `StartingProgress` (§4.7), essentially untouched
- **The withheld reveal** (§4.12) — the pedagogy is right; only its placement changes
- Copy centralization in `strings.ts` (§4.10)

### What is deliberately challenged

Six things survive today because that is how the code happens to be arranged, not
because they are right:

1. **The source pane opens by default**, permanently consuming 340px, although
   `CLAUDE.md` states code is "there to be referred to, not read end to end".
   → It becomes *on-demand*.
2. **The map is a second rendering of the route** — a 2300px timeline duplicating
   the rail, inside a 5.2-screen page. → The rail *is* the route; the map becomes
   a review surface about understanding, not a second map.
3. **Scope controls live in the session header**, where they starve the goal text
   and read as two grey buttons. → They move to the route, where their effect is.
4. **`Finish early` is a footer link on every lesson** — smallest control, largest
   consequence. → Moves into a session menu, with confirmation.
5. **The chapter overview silently replaces the lesson.** → It becomes an explicit
   layer with a persistent way back.
6. **Body prose is 13.5px** inside a 62ch measure. → Prose is the product; it gets
   a real reading size.

### Anti-goals

No gradients as decoration, no glassmorphism, no blur-for-blur's-sake, no
parallax, no animated backgrounds, no motion without an informational job, no
skeleton shimmer where a real progress statement exists. The instrument character
of the current palette is an asset; "modern" here means *calm, spacious, legible
and responsive*, not *effect-laden*.

---

## 1. Design principles

Seven principles. Each is stated as a rule that decides real UI questions.

### P1 — One primary thing at a time

**Rule:** the workspace canvas holds exactly one primary artifact per learner
phase. When a new artifact becomes primary, the previous one collapses to a
single line — it does not sit alongside.

Decides:
- The reveal does not coexist with the answer composer; it replaces it.
- The verification question does not coexist with the original question. *(This
  alone eliminates defect B — twin textareas, twin `Submit` buttons — structurally
  rather than by patching a condition.)*
- Gaps are not a block in the lesson flow; they are a property of the unit,
  surfaced in the brief and expanded on demand.

**Testable invariant:** the lesson workspace never exceeds **2× viewport height**
in any state. If a design pushes past it, something that should have collapsed did
not. (Today: 4.5×.)

### P2 — Hierarchy from size, weight and space before colour

Colour is fully committed to meaning in this product — signal is "you are here",
jade/brass/rust are verdicts. There is nothing left over to say "this matters more
than that". Today 99% of text is ≤16px across 11 sizes inside a 6.5px band, so
size cannot say it either.

**Rule:** hierarchy is carried by, in order: **position** (fixed zones), **size**
(a scale with perceptible steps), **weight**, **space around**, and *only then*
surface. Colour never carries hierarchy alone; it carries *meaning* alone.

Decides:
- Adjacent type levels differ by ≥2px below 20px, and by ≥1.2× above.
- The mono-uppercase micro-label stops being the answer to every level. It is
  reserved for **one** role: the eyebrow above a major zone. Sub-structure uses
  weight and space. (Today the same treatment marks six competing sections.)
- A "quiet" element is made quiet by being smaller and further away, not by being
  dimmer — which is what pushed the rail's chapter text to 3.6:1.

### P3 — Depth is surface, not shadow

The session view currently has **zero elevation**; its only two box-shadows are
semantic state markers. Everything is a 1px outlined rectangle at 4px radius,
which is the single strongest "dated" signal.

**Rule:** depth is expressed primarily by a **surface ladder** (`ink → trench →
slab → raise`), reinforced by radius, and only at the top two levels by shadow.
Dark theme leans on surface *lightness*; light theme leans on *shadow*, because
that is how each medium actually reads.

Decides:
- Cards get a surface and a larger radius, not a heavier border.
- Borders become a *secondary* device — used for separation within a surface, not
  as the definition of every box.
- Only overlays (popover, sheet, floating pane) cast a shadow.

### P4 — Primary action is unmistakable, and singular

Today the "primary" button is a 15%-alpha tint, so no action anywhere looks like
*the* action — and after a wrong answer up to four buttons sit at equal weight.

**Rule:** exactly **one** primary action is visible per phase, rendered as a
**solid** fill. Everything else is secondary (surface + border) or tertiary (text).
If a phase seems to need two primaries, the phase model is wrong.

Decides:
- After a wrong answer: *Check my understanding* is primary; *Build a warm-up* and
  *Move on anyway* are secondary and tertiary respectively.
- The action bar holds the primary action in a fixed position, so it is never
  scrolled off — never again 2080px from the thing that produced it.

### P5 — Adaptation is narrated, never silent — and never alarming

The adaptive path is the product's stated X-factor, and today a warm-up appears,
a lesson is re-taught, or the path is pruned with no announcement at all.

**Rule:** every change the system makes to the plan produces exactly three things:
a **consequence sentence** at the moment it happens (phrased as a result of what
the learner did), a **visible change in the rail** with a persistent "new" marker
until seen, and an entry in the **session timeline**. Never a modal, never a toast
that disappears, never a red alert.

Decides:
- "Because you're unsure how `h()` behaves without coordinates, I've added a
  shorter stop before this one." — not "PREREQUISITE INSERTED".
- Every adaptation is *refusable* in the same breath: the notice carries "skip it".

### P6 — Context is summoned, not stationed

Fixed chrome currently takes 608px at every width, and the goal statement is
starved to 0px at 1024.

**Rule:** screen space is permanent only for what is useful in *every* phase.
Everything else opens on demand and closes cleanly, remembering its state.

Decides:
- Source pane: opens when a citation is clicked; docked at wide widths, an overlay
  sheet below. Not open by default.
- Gaps, attempt history, evidence: on-demand panels, not inline blocks.
- The header keeps identity, goal, one progress measure and a menu. Scope, start
  over and briefing move into that menu.

### P7 — Motion explains change; stillness is the default

**Rule:** motion is used only where something *moved, replaced, appeared or
changed value*, and its duration is proportional to the distance travelled. No
element animates on first paint merely to look alive.

Decides:
- The composer→feedback transform is animated because it is a replacement in
  place, and the animation is what tells the learner the feedback belongs to what
  they just wrote.
- The rail's warm-up insertion is animated because a row genuinely appears.
- Nothing about the lesson prose animates on arrival.

---

## 2. The learning interaction model

The most important section. This replaces the current block-stack outright.

### 2.1 The workspace frame

The lesson area is not a scrolling document. It is three zones:

```
┌─ BRIEF ───────────────────────────────── sticky, ~96–120px ─┐
│ Chapter · Stop 4 of 12          [2 gaps] [3 attempts] [⋯]   │
│ Understand the Session object                                │
│ Objective: explain what Session owns that a bare request…    │
│ requests/sessions.py · 1–80  ·  +2 more                      │
├─ CANVAS ────────────────────── scrolls, ONE artifact ────────┤
│                                                              │
│   (the single primary artifact for the current phase)        │
│                                                              │
├─ ACTION BAR ─────────────────────── docked, never scrolls ───┤
│ [answer composer, when the phase wants one]                  │
│ ● Primary        Secondary   tertiary            ⌘↵ hint     │
└──────────────────────────────────────────────────────────────┘
```

- **Brief** — the answer to *what am I learning right now*. Constant across every
  phase of a stop. Carries the counters (gaps, attempts) that today are inline
  blocks; each counter is a disclosure trigger, not content.
- **Canvas** — the answer to *what just happened*. Exactly one primary artifact.
- **Action bar** — the answer to *what should I do next*. Docked to the bottom of
  the workspace, so the primary action is always on screen. This is the structural
  fix for the y=2080 finding.

### 2.2 The phase model

Within one learning stop, the learner is in exactly one phase:

| Phase | Meaning |
|---|---|
| `STUDY` | Reading the lesson; question visible but unanswered |
| `FEEDBACK` | An answer has been graded; verdict and reveal are primary |
| `VERIFY` | A fresh, gap-specific question is outstanding |
| `RESOLVED` | Objective reached, or the learner chose to move on; ready to advance |

Two events operate at *route* level, not phase level, because they change which
node you are on: **warm-up inserted** and **return to route**.

The current UI has no phase concept — every block decides independently whether to
render, and their order is source order. That is the root cause of accumulation.

### 2.3 Phase specifications

#### `STUDY` — reading, not yet answered

| | |
|---|---|
| **Primary content** | The lesson setup prose, in the canvas, at reading size within a ~66ch measure |
| **Persists** | Brief (title, objective, anchors, counters) |
| **Collapsed / secondary** | Trace-path anchors become a compact inline strip under the brief, not a titled block. Prior attempts (on revisit) are a counter only |
| **Primary action** | `Submit answer` — solid, in the action bar, disabled until the composer has content |
| **Composer** | Lives in the action bar, collapsed to a single line ("Answer this stop…") and expanding on focus to 4–5 rows. It is never a separate block in the flow |
| **Secondary actions** | `Skip this stop` (tertiary) |
| **Feedback location** | n/a |
| **Transition in** | From arrival: brief crossfades, canvas content fades in (150ms). No slide |
| **Growth control** | Canvas holds prose only. On a revisit the reveal is available via a `Show explanation` disclosure rather than being rendered inline |

Note the change: **the question prompt moves out of the canvas into the action
bar**, adjacent to the composer. Today the prompt and the input are a block in the
middle of a 2500px column; the learner scrolls to find where to type.

#### `FEEDBACK` — an answer has been graded

The most important transition in the product.

| | |
|---|---|
| **Primary content** | A **feedback card** that appears *in place of the composer*, in the action zone — then the canvas swaps prose → reveal |
| **Persists** | Brief, unchanged except counters increment (with a highlight) |
| **Collapsed** | The setup prose collapses to a one-line disclosure at the top of the canvas: `Setup — what you read before answering ▸`. The learner's submitted answer collapses into the attempts counter |
| **Primary action** | Depends on verdict — exactly one, solid (see 2.4) |
| **Feedback location** | **Where the answer was.** The composer's box morphs into the verdict card: same x, same width, same position on screen |
| **Transition** | Composer → feedback card: 200ms crossfade + height settle. Canvas prose → reveal: 200ms crossfade, no movement. Both simultaneous |
| **Growth control** | Prose collapses as the reveal appears — the canvas swaps rather than grows. The reveal is the *only* long artifact on screen |

Why feedback goes where the answer was: it makes the response belong to the act.
Today the verdict renders below a 777px reveal that was itself inserted above it,
so the result of a click lands three viewport-heights away with `scrollTop`
unchanged. Morphing in place makes scroll management unnecessary rather than
merely automatic.

#### `VERIFY` — a fresh question about a specific gap

| | |
|---|---|
| **Primary content** | The verification question, in the **canvas**, as the sole artifact |
| **Persists** | Brief; the feedback card collapses to a one-line verdict chip in the brief's status strip (`Not yet — on `h()` and `None``) |
| **Collapsed** | Reveal collapses to a disclosure. **The original question and its composer are gone from the DOM, not merely below** |
| **Primary action** | `Submit` — the only `Submit` on screen |
| **Secondary** | `Not now` (tertiary), which returns to `FEEDBACK` |
| **Composer** | Action bar, same component, now bound to the verification |
| **Feedback location** | Same rule — the composer morphs into the verification verdict |
| **Transition** | Canvas crossfade 200ms; the gap chip in the brief marks itself "being checked" |
| **Growth control** | Guaranteed by phase exclusivity |

This is the design-level fix for defect B. There is one composer component, bound
to one phase, in one place. Two simultaneous answer inputs become unrepresentable.

#### `RESOLVED` — objective reached, or the learner moved on

| | |
|---|---|
| **Primary content** | A compact **stop summary**: what was demonstrated, what stays open, what changed on the route |
| **Persists** | Brief |
| **Collapsed** | Everything else — reveal, feedback, attempts — all disclosures |
| **Primary action** | `Next stop` — solid |
| **Secondary** | `Review this stop`, `Open the map` |
| **Transition** | Canvas crossfade; on advance, brief content crossfades and the rail's current-pin animates to the next row (320ms) |

### 2.4 Verdict branches — one primary each

The current verdict row can show four equally weighted buttons. Under P4:

| Verdict | Primary (solid) | Secondary | Tertiary |
|---|---|---|---|
| **Understood** | `Next stop` | `Review` | — |
| **Partial**, no gaps | `Next stop` | `Try a different angle` | `Build a warm-up` |
| **Partial**, gaps open | `Check my understanding` | `Next stop` | `Build a warm-up` |
| **Confused / off-topic**, warm-up inserted | `Start the warm-up` | `Skip it, continue here` | `Move on anyway` |
| **Confused / off-topic**, no warm-up | `Check my understanding` | `Build a warm-up` | `Move on anyway` |
| **Warm-up declined by backend** | `Check my understanding` | `Move on anyway` | — |

The rule that generates this: **the primary is whatever most directly closes the
gap between where the learner is and the objective.** Moving on is never primary
unless the objective is met.

### 2.5 Gaps — a property, not a block

Gaps stop being a stacked section. They become:

- A **counter in the brief**: `2 open` — a disclosure trigger, tinted brass, never
  a red alarm.
- Opening it slides out a **gap panel** (right-side, over the source column or as
  a sheet at narrow widths) listing each gap: the claim, whether it blocks, and
  two actions — `Check this` (→ `VERIFY` for that gap) and `Set aside`.
- When a gap is discovered, the counter increments with a single highlight pulse
  and the feedback card names it in prose.
- When a gap is resolved, the counter decrements and the panel shows the gap
  struck through with `Closed` for the remainder of the session — evidence that
  something was *fixed*, which today is invisible because the row simply vanishes.

This also removes the surface that currently renders at 1.97:1.

### 2.6 Warm-ups — a detour with a visible round trip

A warm-up is a *different node*, so it is a route event. The design makes the
round trip explicit, because today the learner is silently relocated.

1. **Offer** — in the feedback card: "This leans on something earlier. Want a
   shorter stop on `X` first?" with `Start the warm-up` primary.
2. **Insertion** — the rail row animates in beneath the current stop, indented,
   dashed connector, marked `added for you`. 320ms height + fade.
3. **On the warm-up** — the brief changes character: a `DETOUR` eyebrow replaces
   the stop counter, and carries a persistent **return affordance**:
   `Warm-up for “Use GraphProblem…” → back to it`. The learner always knows this
   is a side trip and how to leave it.
4. **Completion** — on finishing, an `AdaptationNotice` in the canvas: "That's the
   piece you were missing. Back to *Use GraphProblem for map-based search*." with
   `Return to the route` primary.
5. **Return** — the rail animates the current-pin back up to the original stop; the
   warm-up row remains, settled, as a record of the detour.

Warm-ups are excluded from journey progress today, which is correct and preserved.
The UI should say so once, in the detour brief: "Detours don't count against your
route."

### 2.7 The growth budget

Concrete, measurable rules that make P1 enforceable:

1. The canvas holds **one** primary artifact. Anything superseded becomes a
   one-line disclosure.
2. Disclosures render **collapsed by default**, always, including on revisit.
3. History (attempts), gaps and evidence never render inline — they are counters
   in the brief that open panels.
4. The action bar is `position: sticky; bottom: 0` within the workspace, so it
   occupies screen space but not document flow beyond its own height.
5. **Budget: 2× viewport height maximum** for the workspace in any phase. The
   long-form reveal is the only artifact permitted to approach it.

Against today's measurements this takes the worst state from 2845px to a target
of ≤1270px at 634px viewport, most of which is one reveal the learner wants.

---

## 3. Making adaptation visible

### 3.1 The three-channel grammar

Every adaptation uses all three channels — never fewer, never a fourth:

| Channel | Where | Lifetime | Job |
|---|---|---|---|
| **Consequence sentence** | Feedback card footer, or canvas `AdaptationNotice` | Until phase change | Say what changed and *why*, in terms of the learner's answer |
| **Route mark** | The rail | Persists until seen | Show *where* it changed |
| **Timeline entry** | Session timeline, on demand | Permanent | Keep the record |

### 3.2 Per-event design

| Event | Consequence sentence | Rail | Timeline |
|---|---|---|---|
| **Warm-up inserted** | "Because `h()`'s fallback tripped you up, I've added a shorter stop before this one." + `Start it` / `Skip it` | Row animates in, indented, dashed connector, `added for you` marker | `Added warm-up: …` |
| **Gap discovered** | Named in the verdict prose: "You're carrying one assumption that isn't true: …" | Current row gains a brass gap dot | `Gap opened: …` |
| **Gap resolved** | "That's cleared — you've got `h()`'s failure mode right now." | Gap dot decrements; on last one, a single jade pulse | `Gap closed: …` |
| **Verification needed** | "I'd rather not take the last answer as proof. One different question on the same idea." | Current row shows a hollow "checking" ring | `Verification requested` |
| **Re-teach** | "I've rewritten this lesson around the bit that misfired — the explanation below is the new one." | — (no route change) | `Lesson re-taught` |
| **Path pruned** | "You already showed you have this, so I've dropped 2 stops you don't need." | Rows fade out over 320ms, then collapse | `Pruned 2 stops` |
| **Scope changed** | "Shorter route: 4 stops moved to optional." | Affected rows animate into the optional bucket | `Scope: shorter` |
| **Return to route** | "Back to where you were." | Current-pin animates up | `Returned to route` |

### 3.3 Rules that keep it calm

- **Never a modal.** Adaptation never blocks.
- **Never a disappearing toast.** These are consequential; they live in the flow
  until the learner acts.
- **Never red.** Adaptation is the system helping. Brass for "something opened",
  jade for "something closed", signal for "the route changed". Rust stays reserved
  for genuine failure.
- **One notice at a time.** If grading produces a gap *and* a warm-up *and* a
  re-teach, they compose into **one** sentence with the primary consequence
  leading — not three stacked notices, which is exactly today's failure mode
  (`retaught` + `pruned` + warm-up status as three separate mono lines).
- **Always refusable.** Every notice that proposes work carries a dismissal.
- **Seen-state is tracked.** The rail's `new` markers clear once the learner has
  actually looked at the rail, not on a timer.

### 3.4 The session timeline

A new, small surface — on demand from the brief's `⋯` menu or the map. A reverse-
chronological list of route events with timestamps. It costs almost nothing (the
data already exists as `journey_events_json`) and it is what converts "the system
changed something" into "I can see everything the system has done for me." This is
the artifact that makes adaptation *feel* real rather than asserted.

---

## 4. Information hierarchy

### 4.1 Classification

| Element | Class | Notes |
|---|---|---|
| App identity | Always | Small; shrinks to a mark at narrow widths |
| Repo + goal | Always | **Guaranteed minimum width** — never starved below ~240px |
| Goal readiness (fraction) | Always | One measure in permanent chrome |
| Journey progress | Contextual | A compact segmented track; expands on hover/click to the full pair |
| Settings | Always | Icon |
| Session menu (`⋯`) | Always | Holds scope, briefing, timeline, start over, finish |
| Route rail | Always (collapsible) | Collapses to an icon strip, then to an overlay |
| Brief | Always | Sticky |
| Canvas | Always | One artifact |
| Action bar | Always | Docked |
| Source pane | **Contextual** | Opens on citation click. Docked wide, sheet narrow |
| Gaps | **On demand** | Counter → panel |
| Attempt history | **On demand** | Counter → panel |
| Evidence chain | **On demand** | From map or history |
| Map | **On demand** | A route, not a tab that replaces the lesson |
| Chapter overview | **Temporary** | An explicit layer with a persistent way back |

### 4.2 The header

Today: nine `shrink-0` groups; the goal — the only `flex-1` — is truncated to
149px at 1280 and 0px at 1024, and the row overflows below 1111px.

Proposed: **four zones**.

```
[ ◆ CodeOnboard ]  [ psf/requests · trace how a call becomes a response ]  [ 7/12 ▸ ]  [ ⚙ ⋯ ]
   fixed ~150px      flex, min 240px, truncates last                        ~90px      ~72px
```

- Scope controls, `Briefing`, `Start over`, `Finish session` → into `⋯`.
- `Hide source` → disappears; the source pane has its own close control, and it is
  no longer open by default.
- The journey measure becomes a 3px segmented track under the fraction, expanding
  on interaction. Both measures are preserved — the two-grammar distinction is
  documented and correct — but only one occupies permanent chrome.
- **The goal zone gets `min-width` and the right zone collapses into `⋯` first.**
  Content wins over controls; today it is the reverse.

### 4.3 The rail

Today 47% of its height is two-line chapter descriptions, with four of five
chapters collapsed.

- Chapter header: title + `2/3` only. The `why` line moves to the **chapter
  overview**, where the learner has room to read it, and to a tooltip.
- Current chapter auto-expands; others collapse to a single row with a state strip.
- Restore the density the rail's own doc comment asks for: the route should read
  as a route, not as a table of contents with abstracts.
- Add: `new` markers for adaptations (§3), and a compact `session timeline` entry
  point at the foot.

### 4.4 The map

Today: 3283px, 5.2 screens, of which a 2300px journey timeline duplicates the rail.

- **Remove the route timeline from the map.** The rail is the route. The map keeps
  what only it can say: the two measures at full size, the three outcome bands
  (needs work / worked through / set aside), patterns, and the breakdowns.
- It becomes a **review surface** — roughly 1.5 screens — and is reachable as an
  overlay/route rather than a tab that evicts the lesson.

---

## 5. Visual system evolution

Concrete enough to become tokens. Names are proposals.

### 5.1 Typography scale

The problem is flatness, not variety. Eight steps, perceptible gaps, **prose
raised to a real reading size**.

| Token | Size | Line height | Use |
|---|---|---|---|
| `text-micro` | 11px | 1.4 | Mono uppercase eyebrow — the *only* micro-label role |
| `text-xs` | 12.5px | 1.5 | Metadata, counts, file paths |
| `text-sm` | 14px | 1.55 | Secondary body, captions, rail stops |
| `text-body` | **15.5px** | **1.7** | **Lesson prose** (from 13.5px) |
| `text-lg` | 18px | 1.5 | Sub-headings, callout titles |
| `text-xl` | 22px | 1.35 | Brief title, panel titles |
| `text-2xl` | 28px | 1.25 | Lesson title, map headline |
| `text-display` | 36px | 1.15 | Landing wordmark, completion |

- Keep the `calc(N rem/16)` authoring form — it is what makes `--ui-scale` and the
  browser's own font setting both work. Only the *values* become named.
- Keep three families and their roles. Serif for asserted things, mono for factual
  things, sans for prose — that identity is a strength.
- Measure widens to **66ch** at the new body size.
- **Cap mono-uppercase usage at one level.** Sub-structure uses `text-lg` at
  weight 500 instead.

### 5.2 Spacing

4px base. `space-1` 4 · `space-2` 8 · `space-3` 12 · `space-4` 16 · `space-5` 24 ·
`space-6` 32 · `space-7` 48 · `space-8` 64.

Rules: zone padding `space-5`; card padding `space-4`; gap between sibling blocks
`space-5`; gap within a block `space-3`. This replaces the current per-file drift
(`gap-6` / `gap-7` / `gap-9` for the same relationship).

### 5.3 Radii

| Token | Value | Use |
|---|---|---|
| `radius-xs` | 3px | Tag chips |
| `radius-sm` | 6px | Inputs, small buttons, status chips |
| `radius-md` | 10px | Buttons, cards, callouts |
| `radius-lg` | 14px | Panels, sheets, the source pane |
| `radius-full` | 9999px | Pins, tracks, counters |

The jump from a universal 4px to a 6/10/14 ladder is, on its own, the largest
single contributor to "modern" available here.

### 5.4 Surfaces and elevation

| Token | Dark | Light | Shadow | Use |
|---|---|---|---|---|
| `elev-0` | `ink` | `ink` | none | Page ground |
| `elev-1` | `trench` | `trench` | none | Rail, action bar, docked panels |
| `elev-2` | `slab` | `slab` | `0 1px 2px rgba(0,0,0,.28)` dark / `0 1px 3px rgba(16,42,58,.10)` light | Cards, feedback card |
| `elev-3` | `raise` | `slab` + border | `0 12px 32px rgba(0,0,0,.42)` / `0 12px 28px rgba(16,42,58,.16)` | Popovers, sheets, floating source pane |

Dark separates by lightness, light separates by shadow. Borders drop from "every
box" to: `elev-2` gets a hairline only in light theme (where surfaces are close
together); `elev-1` and `elev-3` rely on surface and shadow.

### 5.5 Buttons

| Variant | Fill | Text | Border | Use |
|---|---|---|---|---|
| `primary` | **solid `signal`** | `ink` | none | The one action per phase |
| `secondary` | `elev-2` | `chalk` | 1px `rule` | Alternatives |
| `tertiary` | none | `graphite` → `chalk` | none | Dismissals, "move on anyway" |
| `danger` | none | `rust` | 1px `rust/40` | Destructive, confirmed |

Sizes `sm` (28px) / `md` (36px) / `lg` (44px). Radius `radius-md`. Padding from the
spacing scale — ending today's six different paddings for one variant.

**On the one-accent rule:** filled signal for actions and outlined-signal-with-halo
for the current pin are distinct treatments of one hue, so the reservation holds.
Both mean "the learner's locus" — one is *where you are*, the other *what to do*.
They never appear in the same role.

### 5.6 States

- **Disabled:** never opacity alone. `elev-1` surface + `graphite` text (≥3:1) +
  `cursor: not-allowed` + `aria-disabled`. Today `Back` at `opacity: .3` composites
  to ~1.5:1 and reads as absent rather than unavailable.
- **Focus:** `outline: 2px solid signal; outline-offset: 2px` on `:focus-visible`,
  on **every** interactive element. Today only the source-pane divider has one.
- **Hover:** one step up the surface ladder, plus border → `signal-dim`. 120ms.
- **Loading:** buttons keep their width and swap the label for a small spinner —
  no layout shift. Content areas use a real statement ("Writing your lesson…"),
  never shimmer, consistent with the honesty discipline.

### 5.7 Chips, callouts, inputs

- **ConceptTag** — keep exactly as is. Measured 5.22–8.54:1; the per-tag hue system
  works and is a differentiator.
- **StatusChip** — extracts `understandingStyle`: stroke + fill + border-style, so
  the four classes stay distinguishable without colour.
- **Callout** — one primitive, four tones (`info` signal / `success` jade /
  `caution` brass / `problem` rust), one structure: tone bar + optional eyebrow +
  body. Replaces the three ad-hoc box variants.
- **Inputs** — `elev-1` surface, `rule` border, `radius-sm`, `text-body`, focus
  ring per 5.6. The composer is a single component with collapsed and expanded
  states.

### 5.8 Themes

Both themes are already well-built; the work is applying the new tokens
consistently and **fixing the inverted-token surfaces** (§10.1 of the baseline).
The light theme's "blueprint paper" character is preserved — it is not a wash-out
and should not become one.

---

## 6. Motion

### 6.1 Tokens

| Token | Duration | Easing | Use |
|---|---|---|---|
| `motion-micro` | 120ms | `ease-out` | Hover, focus, chip state |
| `motion-state` | 200ms | `cubic-bezier(.2,0,0,1)` | Crossfades, phase swaps |
| `motion-layout` | 320ms | `cubic-bezier(.2,0,0,1)` | Insertion, height, panel open |
| `motion-route` | 450ms | `cubic-bezier(.3,0,0,1)` | Rail current-pin travel |

### 6.2 Where motion is required

| Transition | Motion | Why |
|---|---|---|
| Answer → feedback | Composer morphs to feedback card in place, 200ms crossfade + height | Ties the response to the act — the core fix |
| Canvas prose → reveal | 200ms crossfade, no movement | Signals replacement, not addition |
| Feedback → verification | 200ms canvas crossfade | Shows the question changed |
| Warm-up inserted | Rail row 0→h, 320ms, single marker pulse | A row genuinely appeared |
| Gap opened / closed | Counter highlight, 200ms | A value changed |
| Path pruned | Rows fade 200ms, then collapse height 320ms | Removal must be seen, not just happen |
| Next stop | Brief crossfade 200ms; pin travels 450ms | Movement along the route |
| Panel / sheet open | Slide 12px + fade, 200ms | Establishes it as a layer |
| Progress change | Width/segment fill 320ms | Value change |

### 6.3 Where motion is deliberately avoided

Lesson prose on arrival · rail on every re-render · long code-pane scrolls (the
existing short-hop-only rule is correct and stays) · progress bars on first paint ·
anything purely decorative · staggered list entrances · attention-seeking loops
after the first pulse.

### 6.4 `prefers-reduced-motion`

The current global override kills *all* duration, including opacity. Refine:
**remove transform, height and travel; keep opacity crossfades at ≤100ms.** Fades
do not trigger vestibular responses and carry the "this replaced that" information
that would otherwise be lost. Where movement is removed, its information is
replaced by a static marker (e.g. the inserted rail row shows its `added for you`
badge immediately rather than pulsing).

---

## 7. Responsive behaviour

Desktop-primary, degrading properly. Current floor: 1111px.

| Band | Rail | Lesson | Source | Header |
|---|---|---|---|---|
| **≥1440 wide** | 280px expanded | Fluid, 66ch measure centred | Docked 380px when open | Full four zones |
| **1180–1439 standard** | 280px expanded | Fluid | Docked 340px when open; auto-closes if lesson would drop below 560px | Full |
| **960–1179 compact** | 56px icon strip; expands on hover/click as an overlay | Full remaining width | **Overlay sheet** from the right | Journey track → `⋯` |
| **<960 narrow** | Overlay drawer via a route button | Full width | Overlay sheet, full height | Identity + goal + `⋯` only |

Rules:
- **The lesson column has a floor of 560px.** If a panel would breach it, that
  panel becomes an overlay instead of a column. This is the rule that prevents
  today's 292px lesson beside 608px of chrome.
- The source pane being closed by default reclaims 340px at every width — the
  single largest space win available, and consistent with how the product says
  code should be used.
- The action bar stays docked at every width; it is the last thing to be sacrificed.
- Below 960 the brief compresses to title + counters, with the objective behind a
  disclosure.
- No mobile-first rewrite is proposed. Graceful degradation to ~820px is the goal;
  below that, an honest "best on a wider screen" is acceptable.

---

## 8. Primitives

Only where there is real, counted duplication today.

| Primitive | Replaces | Justification |
|---|---|---|
| `Button` | ~30 inline copies, 6 paddings, 2 variants | The single largest consistency win |
| `Surface` | ad-hoc `rounded border border-rule bg-slab` | Carries the new elevation ladder |
| `Callout` | 3 ad-hoc tinted boxes | One structure, four tones |
| `StatusChip` | inline `understandingStyle` usage in 4 files | Already one vocabulary; needs one component |
| `ConceptTag` | inline tag spans in 3 files | Identical markup three times |
| `StatePin` | pin markup duplicated in rail, overview, map, drawer | Four copies of the same 20 lines |
| `SectionLabel` | 5 copies (1 exported, 4 inline) | Trivially extractable |
| `Disclosure` | `<details>` usage + new collapse rules | The mechanism P1 depends on |
| `AnswerComposer` | the two textarea blocks | **Makes twin inputs unrepresentable** |
| `FeedbackCard` | the verdict block | Owns the morph-in-place transition |
| `AdaptationNotice` | scattered mono status lines | The §3 consequence channel |
| `RouteItem` | rail `Stop` + overview row + map card | Three renderings of one concept |
| `Panel` / `Sheet` | drawer + float pane + new panels | One layer model, one motion |

Deliberately **not** proposed: a `Layout` abstraction, a `Text` component, a
`Stack`/`Box` system, an icon framework. Tailwind already covers those, and the
baseline's problem was never a shortage of abstraction — it was six copies of four
specific things.

---

## 9. Before → after

**1. Normal lesson**
*Now:* one 2521px column at 634px viewport; title, tags, prose, trace path, gaps,
attempts, prompt+textarea, reveal, finish link — the input somewhere in the middle.
*Then:* sticky brief (title, objective, anchors, counters); canvas holds the setup
prose alone at 15.5px/66ch; the question and composer sit in the docked action bar
with one solid `Submit answer`. Roughly 1 viewport of content, nothing off-screen
that matters.

**2. Answering**
*Now:* scroll to find the textarea; the prompt is a block above it; a `Skip stop`
button sits beside `Submit` at equal weight.
*Then:* the composer expands in place in the action bar; the prompt is directly
above it; `Submit answer` solid; `Skip` tertiary. `⌘↵` hint retained. The canvas
dims very slightly to focus the composer — a 3% surface shift, not a scrim.

**3. Incorrect answer**
*Now:* form disappears; verdict renders at y=2080 below a newly-inserted 777px
reveal; gaps appear *above* the old form position; `scrollTop` stays 0 — the
learner sees nothing change.
*Then:* the composer morphs in place into a feedback card (200ms): `Not yet`, the
rationale, and one consequence sentence naming the gap. Canvas swaps prose →
reveal. Setup collapses to one line. Brief's gap counter increments with a pulse.
Primary action `Check my understanding` sits where `Submit` was, in the action bar.
**Nothing moved off-screen; the response is where the action was.**

**4. Retry / different angle**
*Now:* `Try again` clears the form and re-asks the question whose answer the reveal
just gave away — or, with gaps, `Check my understanding` inserts a question 780px
above the button pressed.
*Then:* a phase change. Canvas crossfades to the new question; feedback collapses
to a verdict chip in the brief; the composer rebinds. One question, one composer,
one `Submit` — ever.

**5. Warm-up inserted**
*Now:* a rail row silently appears while the learner's eye is in the lesson; a mono
line in the verdict panel says `WARM-UP ADDED`.
*Then:* the feedback card carries the consequence sentence with `Start the warm-up`
primary and `Skip it` secondary. The rail row animates in, indented, dashed, marked
`added for you`. On the warm-up the brief switches to a `DETOUR` eyebrow carrying a
permanent `← back to “Use GraphProblem…”`. The round trip is legible throughout.

**6. Gap discovered**
*Now:* a light-grey card (10.97:1 against the page) with a 1.97:1 sublabel and a
1.97:1 `Set aside` button, stacked above the answer form.
*Then:* the gap is named in the feedback prose; the brief's counter goes `1 open` →
`2 open` with a brass pulse. Opening it slides out a gap panel with proper contrast
throughout, each gap offering `Check this` and `Set aside`.

**7. Verification**
*Now:* an invisible question (1.00:1) with an invisible `Submit` (1.11:1), rendered
above the attempts list, coexisting with the original composer, two buttons both
labelled `Submit`, both bound to the same state.
*Then:* a `VERIFY` phase. The question is the sole canvas artifact at `text-lg` in
proper contrast; the composer is the one in the action bar; `Submit` is the only
one on screen; `Not now` returns. The brief's gap chip shows `being checked`.

**8. Gap resolved / return to route**
*Now:* the gap row vanishes; nothing marks the recovery; the learner is silently on
another node.
*Then:* the counter decrements with a jade pulse; the gap panel keeps the closed
gap struck through as evidence of progress; an `AdaptationNotice` says "That's
cleared — back to *Use GraphProblem for map-based search*" with `Return to the
route` primary; the rail's pin travels back (450ms) and the warm-up row settles
into the record.

---

## 10. Prioritized plan

Six stages. Stage 0 is independent and should ship first regardless of everything
else; Stages 1–2 are the foundation the rest depends on.

### Stage 0 — Confirmed defects *(independent, ship first)*
- Fix the inverted/undefined tokens on the gap and verification surfaces
  (`bg-paper` / `text-ink` / `border-hairline` / solid `bg-signal` + `text-paper`).
- Make `verification` and the original composer mutually exclusive; eliminate the
  duplicate `Submit` label.
- Scroll/focus the verdict into view after grading — a stop-gap until Stage 4
  makes it unnecessary.

*Depends on: nothing. Small, and it un-breaks a shipped feature.*

### Stage 1 — Token foundation
Type scale · spacing · radii · surface + elevation ladder · focus ring · disabled
treatment · motion tokens. All in `globals.css`.

*Depends on: nothing. Blocks Stages 2–6.*

### Stage 2 — Primitives
`Button`, `Surface`, `Callout`, `StatusChip`, `ConceptTag`, `StatePin`,
`SectionLabel`, `Disclosure`. Mechanical migration of ~30 button sites.

*Depends on: Stage 1. Blocks Stages 3–5.*

### Stage 3 — Shell and hierarchy
Header rebuild (four zones, `⋯` menu, goal `min-width`) · rail density · source
pane closed by default · responsive bands and the 560px lesson floor · map loses
its duplicate route timeline.

*Depends on: Stage 2. Independent of Stage 4 — can proceed in parallel.*

### Stage 4 — The learning flow *(the centrepiece)*
Brief / canvas / action bar · the phase model · `AnswerComposer` · `FeedbackCard`
with morph-in-place · verification as a phase · gaps as counter + panel · history
as a panel · the growth budget.

*Depends on: Stage 2. Largest single piece; also where `LessonPanel`'s state
reconciliation must be carefully carried across (baseline §6.3).*

### Stage 5 — Adaptive route UX
`AdaptationNotice` · the three-channel grammar · rail insertion/prune animation and
`new` markers · detour brief and return affordance · session timeline.

*Depends on: Stages 2 and 4.*

### Stage 6 — Motion and polish
Apply the motion tokens across the transitions in §6 · refine
`prefers-reduced-motion` · loading and empty states · a full focus/contrast audit.

*Depends on: everything.*

### Dependency summary

```
Stage 0 ─────────────────────────────────────▶ (independent, immediate)

Stage 1 ──▶ Stage 2 ──┬──▶ Stage 3 ──┐
                      │              ├──▶ Stage 6
                      └──▶ Stage 4 ──┴──▶ Stage 5 ──┘
```

### Suggested checkpoints

- After Stage 0: re-run the contrast probe; all gap/verification text ≥4.5:1.
- After Stage 2: no inline button class strings remain.
- After Stage 3: header intact at 960px; goal text never below 240px; lesson column
  never below 560px.
- After Stage 4: the workspace measures ≤2× viewport in the worst state (today
  4.5×); exactly one composer and one `Submit` exist in the DOM in every phase.
- After Stage 5: every adaptation produces all three channels.

---

## 11. Open questions for review

1. **Docked action bar vs inline composer.** Docking guarantees the primary action
   is never off-screen, but costs ~120px of vertical space permanently and is
   unusual for long-form reading. Worth prototyping both.
2. **Should the reveal ever be skippable?** It is the longest artifact (777px
   measured). A `Key point` summary with the full reveal behind a disclosure would
   shrink the worst case further — but may undercut the pedagogy.
3. **Chapter overview: sheet or canvas phase?** §4.1 calls it temporary; it could
   equally be a fifth phase. Sheet is proposed, but the auto-open on chapter entry
   argues for a phase.
4. **Map as overlay or route?** An overlay preserves session context; a route
   suits deep review and is linkable.
5. **How long do `new` markers persist?** Proposed: until the rail is looked at.
   That needs a definition of "looked at" that isn't a timer.
6. **Body at 15.5px** raises the lesson from ~4 to ~5 screens of prose at the same
   word count. Right trade for readability, or should the measure narrow instead?

---

## 12. What this document does not do

It does not specify component APIs, file layout, exact token values in code, or
copy. Those belong to the implementation plan, which should not start until this
direction has been argued with.

---

## 13. Rejected for now: Lesson / Practice as two tabs

Raised 2026-08-19, after F3a made the question 18px and that still did not feel
categorically different from the prose around it. **Not rejected on principle —
rejected on current evidence.** Recorded with the triggers that would justify
revisiting.

### The proposal

Two tabs inside the lesson workspace: **Lesson** for the teaching content, and a
practice tab for questions, answers, feedback, retries and verification. Its
appeal: questions get their own intentional space instead of being distinguished
from prose by font size, and the practice tab can retain history without the
lesson tab growing without bound.

### Why not now

**1. What 723 real nodes contain.** The rich practice state the tab exists to
house has essentially never occurred:

| | |
|---|---|
| Nodes answered at all | 51 of 723 |
| **Of those, exactly one attempt** | **40 (78%)** |
| Two attempts · three | 9 · 2 |
| Nodes that ever recorded a gap | **8** (max 2) |
| Verifications ever taken | **2** |
| Remediation rounds | **0** |

Caveat: these are dev sessions, mostly abandoned, and `CODEONBOARD_GAPS` defaults
off, so gaps are under-recorded. It is what the product has produced so far, not a
forecast. But the cost of tabs falls on the common case — at least one forced
switch per stop, ~15 a session — to benefit a case that is currently rare.

**2. The withheld reveal makes the two tabs non-independent.** The reveal is
lesson content whose *timing* is controlled by answering, so neither tab can own
it cleanly. In Lesson, submitting an answer silently changes a tab the learner is
not looking at — the "adaptation is invisible" failure in a new costume. In
Practice, the Lesson tab is permanently less than what the learner needs. And a
re-teach rewrites the setup itself, so "Lesson" is not a stable place to return
to. Tabs promise two stable rooms; this content model does not have two.

**3. Answers here are grounded, and grounding means referring.** Answering needs
the prose, the objective and the code. Code is a separate column either way, but
the prose and objective would be one tab away exactly when they are most needed.
The single canvas can collapse prose to a line and expand it in place beside the
composer.

**4. It relocates accumulation rather than solving it.** Whatever discipline stops
the practice tab accumulating — one primary artifact, superseded content collapsed
to a line, history behind a counter — is the same discipline that stops the single
canvas accumulating. Tabs add a navigation axis without adding the mechanism.
Collapse is the mechanism.

### What was done instead

F3b gives the active question its own **practice surface**, with
question → answer → feedback happening inside that one region, so the distinction
is carried by surface, grouping and state transition rather than by 2px of type.

### Triggers that would justify revisiting

- **Multiple questions per objective.** If a stop ever asks three or four
  questions, the practice tab becomes a genuine place and this decision flips.
- **Materially richer gap and verification history** once `CODEONBOARD_GAPS=1` is
  the default — the 8-nodes-ever figure is the weakest part of the case against.
- **Testing showing the single canvas still fails** to separate reading from being
  examined, after F3b's surface work has landed.

### Naming, if it is ever revisited

- **"Practice"** — reject. Implies drills and rehearsal; a stop asks once and the
  result is evidence that moves goal readiness, not warm-up repetition.
- **"Check understanding"** — reject. Already means two different things in the
  product: the lesson's question section and the verification CTA.
- **"Demonstrate"** — grounded in `demonstrated`, the header's own measure, and in
  `objective` as "the claim the learner should be able to make". Names the act.
- **"Evidence"** — grounded in the evidence drawer and the rule that every state be
  explainable from persisted evidence. Names the record.

Best pairing: `Demonstrate` for the act, `Evidence` for the history — which is
close to what the single-canvas model already has as a counter and a panel.
