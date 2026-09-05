# Frontend architecture

> App structure, routing, the derived view-model layer, and the state machines
> that decide what a learner sees.
>
> Parent: [overview.md](overview.md) · Index: [docs/README.md](../README.md) ·
> Implementation: [`frontend/`](../../frontend/README.md)

---

## 1. Stack and shape

Next.js 15 (App Router, `"use client"` throughout), React 19, TypeScript,
Tailwind CSS 4, Shiki for syntax highlighting, Vitest + Testing Library.

There is no client state library. The server is the authority for everything
about learning, so the client holds the fetched graph, the fetched lesson, and a
small amount of genuinely local UI state.

```
frontend/
├── app/            routes (App Router)
├── components/     rendering — one directory level per surface
├── lib/            the API client, and the derived view-model layer
└── test/           factories and setup for Vitest
```

---

## 2. Routing

| Route | Purpose |
|---|---|
| `/` | A signpost, not a destination: authenticated → `/sessions`, anonymous → `/login` |
| `/login` · `/signup` | Email + password. The Google button appears only when the server says the provider exists |
| `/forgot-password` · `/reset-password` | Development-only reset link flow |
| `/sessions` | **The dashboard** — "what was I working on", the question the product could not answer at all before accounts |
| `/new` | Repository entry → the six-question interview → the live planning screen |
| `/session/[id]/welcome` | The briefing, the route overview and the learner profile. Reachable again from the session header — a page to come back to, not a splash screen |
| `/session/[id]` | **The workspace**: route rail, lesson surfaces, code pane |

`Continue` on the dashboard goes to `welcome` for a session that was never opened
and to the workspace otherwise.

---

## 3. The API layer

`lib/api.ts` is the only module that talks to the network.

- `BASE = "/api"`, always. Every call goes through the Next rewrite, so the
  browser only ever talks to its own origin and the auth cookie is first-party.
  There is no `NEXT_PUBLIC_API_URL`.
- `credentials: "include"` is set in the **one** place every request passes
  through. Per-call would work until the call somebody adds next month forgets
  it — and that call would fail as "not signed in" rather than as a missing
  option.
- A 401 is thrown as `NotAuthenticatedError` and handled **centrally** through
  `setUnauthenticatedHandler`, so the app reacts in one place.
- An `AbortError` is rethrown as-is: an abort is the caller's decision, and
  collapsing it into a network failure would render "I changed my mind" as "the
  backend is down".
- `fail()` unwraps FastAPI's `detail` — string, or an object carrying the
  pipeline's error list — because raw JSON in a UI is useless.

`lib/auth.tsx` is the client's entire authentication model: one `GET /auth/me`
for the whole app, held in a provider. The cookie is `HttpOnly`, so nothing in
the client can read it — the server stays the authority and this is a cache of
one boolean's worth of state. `"loading"` is a real state, not a nicety: without
it every guarded page renders its signed-out branch for one frame and a returning
learner sees the login screen flash on every cold load.

---

## 4. The derived view-model layer

This is the part of the frontend worth understanding. `lib/` holds pure functions
that turn the server's payload into what a surface renders — and the reason they
exist as their own layer is that each of them replaced a set of flags computed in
a component from a different slice of the response, where **every defect was a
seam between them**.

| Module | Answers |
|---|---|
| `graph-layout.ts` | Turns edges into the order a learner walks them — "sequence first, else prerequisite", reproducing `next_in_path`. Prerequisites are detours, so they report the position of the stop they precede rather than consuming a number |
| `route-sections.ts` | The chapter level: `Journey → Area → Learning Unit`, projected from `areas` + each unit's `area_id`. Counts stops the way `backend/learning/progress.py` counts them, so the rail's `1/3` cannot disagree with the header |
| `lessonPhase.ts` | `STUDY` · `FEEDBACK` · `VERIFY` · `RESOLVED` |
| `lessonView.ts` | Which blocks the canvas shows, at what weight, for a phase. **One primary artifact per phase; everything superseded collapses to a disclosure** — reachable, not gone |
| `lessonSurfaces.ts` | Which **surface** each block belongs to. A total `Record`, so adding a block without placing it is a type error |
| `surfaceTabs.ts` | Two modes, each owning its tabs: `learn → Lesson · Understanding`, `route → Map · Analysis` |
| `feedbackActions.ts` | Which actions a verdict offers and which is primary: *the primary is whatever most directly closes the gap between where the learner is and the objective; moving on is never primary unless the objective is met* |
| `standing.ts` | How a stop should **read** in the rail, composed from four server facts — `understanding`, `disposition`, `attempted`, `visited` |
| `arrival.ts` | Whether to show a "you jumped here" notice, and what it says |
| `sessionLog.ts` | `journey_events` → the "what changed" list |
| `markdown.ts` | The parser for model-authored prose (see §6) |
| `materialSeen.ts` | The one fact the client owns (see §5) |
| `layout-bands.ts` | `wide` / `medium` / `narrow` at 1180px and 960px, and whether the source pane must overlay |
| `strings.ts` | **All** user-facing copy, plus `errorText` mapping backend `detail` slugs |
| `lessonIcons.ts` | The lesson's decorative emoji markers, one table. Keyed over `BlockName` for the blocks, so a new block with no marker is a type error; every glyph is `aria-hidden` at render (see §7) |

### The two surfaces

`Lesson` and `Understanding` are separated by **purpose**, not by content type:

- **Lesson** — *"what should I read now?"* — `setup`, the trace path, `reveal`,
  and the explanations a re-teach replaced.
- **Understanding** — *"what have I shown, what am I missing, what should I do
  now?"* — the question and composer, the verdict, the gap ledger, and previous
  answers.

The question lives on Understanding because being examined is not the same act as
reading. Only the code **locations** are mirrored into both, and deliberately not
the prose: mirroring the setup put the single longest thing on the page into both
surfaces at once, which is the accumulation the split existed to remove.

`Map` and `Analysis` are the other mode: the route is navigation; the two
progress measures, the outcome bands, the pattern layer and the session log are
interpretation of evidence. One view held all of it, and it was a map you had to
scroll past a dashboard to read.

---

### The phase boundary

`centreSurface(contribution, requested)` in `lib/contribution.ts` decides which of
three surfaces owns the centre column — `journey`, `ready`, `contribution` — and
**one bar or the other is mounted above it**, never both and never one hidden
with CSS:

| Surface | Chrome |
|---|---|
| journey / ready | `SurfaceTabs` — `Learn / Route`, then `Lesson / Understanding` |
| contribution | `ImplementationBar` — `Plan · Locate · Continue in Claude`, plus one labelled door back |

`Learn / Route` and `Lesson / Understanding` choose which view of a **stop** you
are reading. During the contribution phase there is no stop on screen, so they
name views that do not exist — and pressing `Understanding` there rendered the
understanding surface of whichever node happened to be current, which is the
learning phase appearing under implementation chrome. Both branches read the same
`surface`, so the chrome and the content cannot describe different phases.

**Which surface is showing is a fact about NAVIGATION, not about the session**,
and getting that wrong is the defect the function exists to prevent. The first
version derived it from `phaseOf(contribution) === "stage"` alone, which put the
contribution stage above the lesson branch: the moment a learner pressed *Start
implementing*, the route rail went inert — every stop they clicked still rendered
Locate. Selecting a stop is a **request** to see that stop, so an explicit request
outranks the session's own phase in both directions, and the phase is only the
default for a learner who has not asked for anything yet. `requested` is genuinely
client state — nothing server-side records which of two surfaces someone is
looking at, and nothing should. That is the narrow exception D22 already allows:
it decides what is on screen, never what is true about the learner.

The route rail keeps the whole journey in both phases, with the implementation
steps drawn below the chapters as a distinct section — the two are phases of one
journey, not competing navigation. `implementationRail()` feeds both the rail and
`ImplementationBar`, so the step each marks current is one fact.

---

## 5. The one fact the client owns

Every learning decision comes from the server — the retry offer, the reason there
is none, whether the objective is met. The single stated exception is
`materialSeen.ts`: **"have I looked at Lesson since it changed."**

It is the exception the rule allows for, because it is not a fact about
understanding and the server has no way to observe it. It exists because exactly
one outcome rewrites the Lesson surface — a `reteach` — and it happens while the
learner is on the Understanding tab looking at their verdict, so the system can
write remediation for this learner's misconception and they may never see it.

**Reading is guidance and never evidence**: it cannot close a gap, move a state,
or count toward readiness. It lives in `localStorage` for that reason.

---

## 6. Markdown, and who gets parsed

**Model-authored prose is markdown and is rendered as markdown.** Teaching is
asked for markdown in `setup` and `reveal`, and the models deliver it — bolded
leads, backticked identifiers, numbered steps, the occasional fence. Every such
string goes through `components/ui/Prose.tsx`: `Prose` for a block, `InlineProse`
for a single line whose element the caller already styles.

`lib/markdown.ts` is the parser: **pure, returns nodes, never HTML**, so
`dangerouslySetInnerHTML` never enters the picture. Two subset rules are
load-bearing:

- **`_` is never emphasis** — `line_start` and `__init__` are the vocabulary.
- **An unclosed delimiter stays literal** — prose that half-parses is worse than
  prose that does not.

**Learner-written text is never markdown.** Attempt answers and check answers stay
`whitespace-pre-wrap` exactly as typed. Interpreting a learner's asterisk as
emphasis rewrites what they said, and the one place their own words appear is the
one place fidelity beats polish.

---

## 7. Copy

The app is **English-only**: no locale selection, no translation layer, no
per-request language plumbing — agents write prose in English because that is the
only language their prompts describe.

All user-facing wording lives in `lib/strings.ts`, imported directly as `t`. It is
a plain module, not a React context: keeping copy out of the components is a
tidiness choice, not localization infrastructure.

Values that are **parsed** rather than read stay fixed keys — JSON keys,
`goal_type`, `depth`, `familiarity`, concept tags, edge kinds, Grader
classifications. The frontend switches on those, so they must not be reworded;
only the displayed label is chosen, via `tagLabel` / `stateLabel`.

**A block is named once.** A `Disclosure`'s summary row exists to say what is
inside it, and every block `LessonCanvas` collapses also carries its own eyebrow —
so opening one showed the name twice, four pixels apart. `SectionLabel` exports
`BlockTitle` for a block's own title and an `AlreadyNamed` context that `Disclosure`
wraps its contents in; `BlockTitle` renders nothing inside it. A *sub*-heading keeps
plain `SectionLabel` — `GapList`'s `Settled` divides the ledger's two halves and no
summary row has named it.

The context exists because the two halves of the fact live in components that do
not meet: the disclosure knows it has displayed the name, the title knows which of
its labels *is* the name. The alternative — a `heading={false}` prop from
`LessonPanel` — would mean deriving "is this block collapsed" a second time, from a
different input, when `LessonCanvas` already decides it from `surfaceBlocks`.

**Emoji are not copy, and they are not in `strings.ts`.** The lesson's attention
markers live in `lib/lessonIcons.ts` and reach the page through
`components/ui/Marker.tsx`, which renders every one of them `aria-hidden` and as a
*sibling* of the label rather than inside it. Both halves are load-bearing: a
glyph inside the label would enter the accessible name — a screen reader
announcing "open book, before you answer" — and would change the text content that
the suite's `getByText(t.lesson.…)` queries match, in a way that breaks the tests
without changing anything visible on the page.

A marker never carries information its label does not. Nothing in the product is
"the ✅ one"; the glyphs make a column of identical 11px mono eyebrows
distinguishable before it is read, and the screen says everything it said without
them. Two exceptions where the marker is a real second channel rather than
decoration: the **verdict** (paired with `VERDICT_COLOR`, because colour is the
channel a learner may not have) and the **gap statuses**, where `Resolved` and
`Ignored for now` must not blur.

Glyph choice is constrained by the theme swap, and most candidates fail: an emoji
is a colour image with no `currentColor` to follow, so one that is mostly white
disappears on the light page and one that is mostly near-black disappears on
`ink`. `lessonIcons.ts` records which candidates were rejected on which ground.

---

## 8. Component map

| Directory / file | Owns |
|---|---|
| `SessionHeader` · `SessionMenu` · `SettingsMenu` | The header, the two progress numbers, and the session actions — *Make it shorter*, *Go deeper*, *Start over*, *Rebuild learning path*, *Finish session* |
| `RouteRail` · `SectionOverview` · `RouteOverview` | The chapter rail and its overviews |
| `MapView` · `MapLegend` | The route drawn as a map, with a key and "you are here" |
| `AnalysisView` · `EvidenceDrawer` · `SessionLog` | Interpretation of evidence, and the per-unit evidence chain |
| `LessonPanel` | The workspace's largest component: fetches the lesson, submits answers, holds the pending-question state |
| `lesson/` | The blocks — `SetupProse`, `TracePath`, `RevealBlock`, `AnswerComposer`, `VerificationBlock`, `FeedbackCardNext`, `GapList`, `AttemptHistory`, `EarlierExplanations`, `ArrivalNotice`, `CompletionScreen`, `SurfaceTabs` |
| `CodeViewer` · `CodeLines` | The source pane. Shiki highlighting, opened on a citation |
| `GoalDialogue` · `goal/` | The interview, its transcript and the review step |
| `StartingProgress` · `RebuildingOverlay` | The live planning screen and the re-plan overlay |
| `SessionCard` · `ProfileCard` | Dashboard and welcome cards |
| `auth/` | `AuthForm`, `AuthShell` |
| `contribution/` | The `contribute_code` phase — `ReadyGate` (the derived gate and the quiet override), `ContributionStage` (Plan · Locate, and the fallback steps), `HandoffStep`, `ImplementationBar`, `ScopeCard` |
| `tour/` | The first-run tour |
| `ui/` | `Button`, `Callout`, `Prose`, `ProseCode`, `ConceptTag`, `StatePin`, `Disclosure`, `SectionLabel` (+ `BlockTitle`), `PracticeSurface`, `Marker` |

---

## 9. Build flags and theming

`NEXT_PUBLIC_CODEONBOARD_UI` selects the lesson renderer:

- `surfaces` (**default**) — `Lesson · Understanding` plus the `Map · Analysis`
  mode.
- `next` — the earlier single phase-driven canvas, kept as the baseline the
  surfaces arrangement is measured against.

A third, `legacy`, was deleted once it had been measured twice: keeping a third
arrangement alive meant every behaviour change had to be made twice or
consciously not made twice, which is how one derived flag came to be computed two
different ways and stayed wrong on one of them.

Theme is a persisted preference. `app/layout.tsx` renders the default and a
**blocking** boot script corrects it from `localStorage` before first paint —
otherwise every load flashes the default theme before the chosen one. The `<html>`
element carries `suppressHydrationWarning` because React is told the script owns
that attribute.

`NEXT_DIST_DIR` exists for one reason: two dev servers on this repo at once share
`.next` and quietly corrupt each other's view of it. Neither failure announces
itself — the page renders, it is simply the wrong page.

---

## 10. Tests

54 test files, 861 tests, run with `npm test` (Vitest + jsdom). They are
behavioural rather than snapshot-based: `frontend/test/factories.ts` builds server
payloads, and the tests assert what a learner can see and press.

The heaviest are the ones guarding the seams this architecture removed —
`lesson/retryLoop.test.tsx`, `lesson/surfacesNav.test.tsx`,
`lesson/surfacesAwareness.test.tsx`, `lesson/nextCanvas.test.tsx`,
`LessonPanel.test.tsx`, `RouteRail.test.tsx`, `MapView.test.tsx`.

There is no separate lint or typecheck script; `npm run build` type-checks the
app. See [testing.md](../testing.md).
