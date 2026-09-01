---
name: verify-in-browser
description: Check a CodeOnboard change on the rendered page — layout, contrast, initial scroll and fold state, focus, navigation, and what a learner can actually see and press. Use after any change to frontend/, and whenever a defect could only exist on screen. Includes the free fixture-database path that walks the UI without spending money.
---

# Verifying on the rendered page

More than a third of this repository's recorded defects were **only** findable by
looking at the page: text below 4.5:1 contrast, a brief that arrived folded, a
surface that opened part-scrolled, a chapter gap of 0px because `first:mt-0` on an
only child cancels itself, a tour ring around a rectangle that was not on screen,
duplicate answer boxes. There is no Playwright layer and none is planned; the unit
suites assert what a learner *can* see and press, not how it looks when it gets
there.

So: for anything visual, reason about the code **and then look**.

---

## 1. Get a page up without spending money

The application path (`/new` → interview → `POST /session/start`) runs a clone, an
exploration and a Sonnet call — two to four minutes and real money per session.
That is the wrong shape for looking at a screen.

**Prefer the fixture database.** It writes a graph directly — nodes, real
`psf/requests` anchors, cached lessons, attempts, gaps — so the app behaves as it
would on a real session, and **a cached lesson on every node is what keeps it
free**: `/lesson` only calls Teaching when `cached_lesson` is empty.

```bash
uv run python scripts/seed_ux_fixture.py --db data/ux-fixture.db
```

```bash
uv run python -m uvicorn scripts.ux_fixture_app:app --port 8107
```

Then point the Next server at it with `API_ORIGIN=http://localhost:8107` and open
the frontend. It **refuses to run against `data/sessions.db`**, deliberately.

Use the real backend only when the change is about planning, grading or anything
that must call a model — and say so first.

## 2. Open it

`.claude/launch.json` defines `backend` (port 8000) and `frontend` (port 3000);
start the frontend with `preview_start {name: "frontend"}`. On Windows
`run-dev.bat` starts both and **verifies each over HTTP** before reporting — a
held port is not a healthy service, which is the defect it was written to fix.

Two dev servers on this repo share `.next` and quietly corrupt each other's view
of it — the page renders, it is simply the wrong page. Set `NEXT_DIST_DIR` for the
second one.

## 3. Look, in this order

1. **Console and network** — `read_console_messages`, `read_network_requests`. A
   hydration warning or a failed `/api/*` call explains most "it looks broken".
2. **Structure and text** — `read_page`. Prefer it over a screenshot for
   *what is there*: labels, headings, controls, whether the objective is on
   screen. This is also how you confirm a fixed key is rendering a label and not a
   raw token.
3. **The pixels** — a screenshot for spacing, alignment, weight, and anything the
   accessibility tree cannot express.
4. **Drive it** — click, type, submit. The states that break are the ones after an
   action: a verdict landing, a gap ledger opening, a re-teach replacing the
   lesson under a learner who is on the other tab.

## 4. Run the probe for the things only measurement answers

`scripts/ux-probe.js` measures six things a page can be wrong about while looking
fine: composited contrast of every visible text run, duplicate answer boxes and
button labels, how many distinct font sizes and their spread, the radius census,
header overflow and the width left for the goal statement, and workspace scroll
height against the viewport.

Execute its contents in the page with `javascript_tool` (or paste it into the
console). It disables transitions while it reads — a background tab freezes
transitioned values at their pre-transition state, which silently corrupted the
first baseline pass.

It is deliberately capped at one file that reads an already-open page and prints
pass/fail. **Do not grow it** a driver, fixtures, a runner or an assertion DSL; if
it wants those, the answer is Playwright, not a bigger probe.

## 5. Check the states, not just the page

Walk the ones that have broken before:

- **Initial state** — does anything arrive folded, part-scrolled, or with the
  wrong tab active? Both surfaces start at the top.
- **Both renderers** — `NEXT_PUBLIC_CODEONBOARD_UI` is `surfaces` (default) or
  `next`.
- **Both themes** — theme is persisted and corrected by a blocking boot script
  before first paint. Use `resize_window { colorScheme }`.
- **The three layout bands** — 1180px and 960px, and whether the source pane must
  overlay. `resize_window` across them.
- **Reduced motion** — it means less movement, not less feedback.
- **Focus and disabled states** — a visible focus ring, and disabled controls that
  read as disabled.

## 6. Report what you saw

Screenshot or probe output for the claim being made. If something could not be
checked — a state the fixture does not reach, a flow needing a live model — say so
rather than implying it was verified.

## Completion criteria

The page was opened, the changed surface was driven through its states, the
console is clean, and any visual claim is backed by a screenshot or a probe
result. Pair this with `verify-change` for the suites; neither replaces the other.

## Common failure modes

- Approving a layout change on code inspection alone.
- Starting a real session and spending money to look at a screen.
- Pointing the fixture seeder at `data/sessions.db`.
- Reading colours in a background tab.
- Checking only the state the page opens in.
