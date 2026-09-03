---
name: investigate-behaviour
description: Trace why CodeOnboard behaves the way it does across the five layers — browser, view model, wire, learning policy, stored row. Use for "why is readiness wrong", "why did this stop not update", "why was that gap not offered", a failing test whose cause is unclear, or any bug whose layer is not yet known. Locates the cause before anything is changed.
---

# Investigating a behaviour

Most defects in this repository were **not** in the layer where they were
observed. The Map's evidence chips looked like a Map bug and were a key-uniqueness
bug. A backend suite failing looked like a test bug and was an import rewriting
the environment. A password field showing `Internal Server Error` looked like an
auth bug and was a dead backend proxied through Next.

So the rule is: **locate before you fix.** A patch applied at the layer where the
symptom appeared is the most common way a real cause survives.

---

## 1. State the observation precisely

Write down, in one sentence each:

- What was expected, and **which layer is entitled to decide it**. Most learning
  facts are the server's (D22); if the expectation is about a number, a retry
  offer or whether an objective is met, the browser is a witness and never the
  authority.
- What actually happened — the exact number, label, state or error slug.
- Whether it reproduces, and under **which flags**. This used to be the first
  thing to check and the answer surprisingly often: `CODEONBOARD_CURRICULUM` and
  `CODEONBOARD_GAPS` were `1` in the developer's `.env` and deleted by
  `tests/conftest.py`, so the app and the suite ran different code. **Both flags
  are gone**, which closes that gap — `CODEONBOARD_TUTOR` is the only one left and
  it defaults on in both. Still worth one look, because it is cheap: an `.env`
  that sets `CODEONBOARD_TUTOR=0` and a bundle built without
  `NEXT_PUBLIC_CODEONBOARD_TUTOR` disagree in a way nothing on screen explains.

## 2. Bisect the five layers, outermost first

Do not read code in order. Ask at each boundary: *is the value already wrong when
it arrives here?* The first boundary where it is wrong is where to look.

| # | Layer | How to see the value | Wrong here means |
|---|---|---|---|
| 1 | **Rendered page** | `verify-in-browser` skill; `read_page`, `read_console_messages`, `read_network_requests` | Rendering, layout, state that only exists on screen |
| 2 | **View model** | `frontend/lib/*` — run the relevant `*.test.ts` with a factory payload | A seam: something derived in the client that the server should have sent |
| 3 | **Wire** | the JSON in the network panel, or `curl http://localhost:8000/…` with the cookie | The server is already wrong — stop looking at the frontend |
| 4 | **Learning policy** | pure functions, no key needed: `progress.summary()`, `understanding_of()`, `adaptation.decide_all()`, `retry`, `scope`, `graph.path_order()` / `resume_point()` | A rule is wrong, or is being asked the wrong question |
| 5 | **Stored row** | `store.load_graph(session_id, user_id)` — **read only** | The value was wrong when it was written, or is not being written at all |

Layer 4 is the one to reach for early when the symptom is a number or a state,
because it needs no server, no key and no browser:

```bash
uv run python -c "from backend.learning import progress; help(progress.summary)"
```

Reproduce a suspect graph in a test rather than against the real database.
`tests/` has factories and fixtures for every shape; `data/sessions.db` is the
irreplaceable development corpus and is **read-only** during an investigation —
never write to it, never migrate it, never delete it.

## 3. Ask the four questions that have most often been the answer

1. **Is something derived twice?** The canonical defect class. Grep for the
   concept in `frontend/lib/` *and* in `backend/learning/`. If both compute it,
   they will eventually disagree — `route-sections.ts` counting stops differently
   from `progress.py` is the shape.
2. **Is a decision being read as evidence?** An override, a skip, a page view or a
   `waived` gap that has moved `understanding_state` (D8, D9).
3. **Did the plan change rather than the evidence?** If a progress number fell,
   check whether a node was inserted, re-prioritised or excluded. Readiness may
   fall **only** when evidence changes (D7).
4. **Is a key or an id non-unique?** Node ids are global; plan rows are keyed
   `(session_id, node_id)`; gap ids are minted by `Gap.create`. A list keyed on a
   pair that repeats renders the wrong row without erroring.

## 4. Confirm the cause before proposing a fix

State the cause as a claim with a file and line, then **prove it**: a failing test
that captures it, a value printed at the boundary, or the exact input that
produces it. A cause that has not been demonstrated is a hypothesis, and this
repository's history is full of plausible hypotheses that were the wrong layer.

Then check the cause against the invariant that governs it
(`docs/architecture/decisions.md`, routed by file in the root `CLAUDE.md`; the
higher-level design invariants are in `.claude/reference/design-principles.md`). If
the current behaviour *is* the invariant, the bug is in the expectation — say so
rather than removing the rule. If the code is self-consistent and it is the
*intended model* that is unclear, this is a design question, not a defect: take it
to the `design-a-change` skill.

## 5. Only then decide what changes

- Write the failing test first, at the layer where the cause is.
- If the fix belongs in a different layer from where the symptom appeared, say
  that explicitly in the summary — it is the most useful sentence in the report.
- If the fix would change a documented invariant, stop and raise it; that is a
  design decision, not a bug fix.
- Verify with the `verify-change` skill, and with `verify-in-browser` if the
  symptom was ever visual.

## Completion criteria

The investigation is done when you can say: **the value is correct at layer N and
wrong at layer N+1, because of this line, and here is the input that shows it.**
Anything less is a guess, and should be reported as one.

## Common failure modes

- Patching the layer where the symptom was seen.
- Trusting a test suite that neutralises the flags the app actually runs with.
- Reading `data/sessions.db` and then writing to it.
- Concluding "the frontend is wrong" without looking at the wire payload.
- Treating a green `pytest` run as evidence about anything a model produced.
