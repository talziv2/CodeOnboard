# `frontend/` — the Next.js application

> Parent: [root README](../README.md) ·
> Architecture: [docs/architecture/frontend.md](../docs/architecture/frontend.md)

```bash
npm install
npm run dev      # http://localhost:3000
npm test         # Vitest — 54 files, 861 tests
npm run build    # also the type check
```

The backend must be running on `http://localhost:8000` (or wherever `API_ORIGIN`
points). There is no linter and no separate typecheck script.

---

## Layout

| Directory | Owns |
|---|---|
| `app/` | Routes (App Router). `/login` `/signup` `/forgot-password` `/reset-password` `/sessions` `/new` `/session/[id]` `/session/[id]/welcome` |
| `components/` | Rendering, one subdirectory per surface: `lesson/`, `goal/`, `auth/`, `tour/`, `ui/` |
| `lib/` | The API client, and the **derived view-model layer** |
| `test/` | `factories.ts` (server payloads) and `setup.ts` |

`app/page.tsx` is a signpost, not a destination: authenticated → `/sessions`,
anonymous → `/login`.

---

## The three things to understand first

**1. Every request goes through `/api/*`.** `next.config.ts` rewrites it to
`API_ORIGIN`, server-side, per request. The browser only ever talks to its own
origin, so the auth cookie is **first-party**: `SameSite=Lax` behaves, CSRF has no
cross-site case, and CORS stops being load-bearing. There is no
`NEXT_PUBLIC_API_URL` — that value was baked into the browser bundle at build
time, which both published the API's address and made it impossible to change
without a rebuild.

**2. The frontend renders learning decisions; it does not compute them.** The
retry offer, the reason there is none, whether the objective is met, and every
progress number arrive from the server. This is not a style preference: when four
such flags were derived in the panel from four different slices of the grading
reply, **every defect was a seam between them** — a scaffold whose only usable
button was unreachable, an exhausted gap offered and refused as an error, and one
flag derived two different ways and wrong on one of them.

The single stated exception is `lib/materialSeen.ts` — *"have I looked at Lesson
since it changed"* — which is not a fact about understanding and is not observable
server-side. **Reading is guidance and never evidence.**

**3. `lib/` is a layer, not a folder of helpers.** Each module is a pure function
from the server's payload to what a surface renders: `graph-layout` (edges → the
walk order), `route-sections` (chapters), `lessonPhase` / `lessonView` /
`lessonSurfaces` / `surfaceTabs` (what is shown, at what weight, on which
surface), `feedbackActions` (which action is primary), `standing` (how a stop
reads in the rail), `arrival`, `sessionLog`, `markdown`, `layout-bands`.

---

## The two surfaces

`Lesson` and `Understanding` are separated by **purpose**:

- **Lesson** — *"what should I read now?"*: setup prose, the trace path, the
  reveal, and the explanations a re-teach replaced.
- **Understanding** — *"what have I shown, what am I missing, what should I do
  now?"*: the question and composer, the verdict, the gap ledger, previous answers.

The question lives on Understanding because being examined is not the same act as
reading. Only the code **locations** are mirrored into both — mirroring the setup
prose put the single longest thing on the page into both surfaces at once, which
is the accumulation the split existed to remove.

`Map` and `Analysis` are the other mode: the route is navigation, and the
measures, bands, patterns and session log are interpretation of evidence.

---

## Copy

The app is **English-only** — no locale selection, no translation layer. All
user-facing wording lives in `lib/strings.ts`, imported as `t`, plus `errorText`
which maps backend `detail` slugs to readable sentences. It is a plain module, not
a context: keeping copy out of components is tidiness, not localization
infrastructure.

**Model-authored prose is markdown** and goes through `components/ui/Prose.tsx`.
`lib/markdown.ts` is the parser: pure, returns nodes, never HTML. Two subset rules
are load-bearing — **`_` is never emphasis** (`line_start` and `__init__` are the
vocabulary) and **an unclosed delimiter stays literal**.

**Learner-written text is never markdown.** Answers stay `whitespace-pre-wrap`
exactly as typed.

Values that are **parsed** rather than read — `goal_type`, `depth`, `familiarity`,
concept tags, edge kinds, Grader classifications — are fixed keys and must not be
reworded; only the label is chosen, via `tagLabel` / `stateLabel`.

---

## Environment

| Variable | Default | Notes |
|---|---|---|
| `API_ORIGIN` | `http://localhost:8000` | Read by the Next **server** at request time |
| `NEXT_PUBLIC_CODEONBOARD_UI` | `surfaces` | `surfaces` or `next` — the lesson renderer |
| `NEXT_DIST_DIR` | `.next` | Set it for a second dev server on this repo: two servers sharing `.next` quietly corrupt each other's view of it, and neither failure announces itself |

---

## Tests

Vitest + jsdom + Testing Library, **behavioural rather than snapshot-based**: build
a server payload from `test/factories.ts` and assert what a learner can see and
press.

The heaviest files guard exactly the seams the `lib/` layer removed —
`lesson/retryLoop.test.tsx`, `lesson/surfacesNav.test.tsx`,
`lesson/surfacesAwareness.test.tsx`, `lesson/nextCanvas.test.tsx`,
`LessonPanel.test.tsx`, `RouteRail.test.tsx`, `MapView.test.tsx`.

`AGENTS.md` (referenced by `CLAUDE.md`) carries one rule: this Next.js version has
breaking changes, so read `node_modules/next/dist/docs/` rather than trusting
recall.
