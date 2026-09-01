---
name: verify-change
description: Run the right CodeOnboard checks for the change that was just made, and read the results correctly. Use after editing anything under backend/, frontend/, tests/ or scripts/, and before reporting work as done. Knows the one test that fails by design, which suites a change category actually needs, and which failures are expected.
---

# Verifying a change to CodeOnboard

There is **no CI**. Nothing runs these unless you do, so a change reported as done
without them is a change nobody has checked.

Run every command from the repository root unless it says otherwise.

---

## 1. Pick the suites the change actually needs

| What you changed | Run |
|---|---|
| `backend/learning/`, `backend/repo/`, `backend/pipeline/` | backend |
| `backend/agents/` (code) | backend |
| `backend/agents/` (**prompt text only**) | backend — then say plainly that the suite stubs every model, so it covers the wiring and proves nothing about prompt *quality*. Only a `scripts/` harness can, at real cost: `measure-and-record` |
| `backend/api.py`, `backend/auth/` | backend, and confirm `test_route_authz_coverage.py` and `test_ownership.py` ran |
| `backend/learning/store.py`, `backend/migrations/` | backend, and confirm `test_learning_store`, `test_plan_snapshot`, `test_session_reset`, `test_legacy_session_compatibility`, `test_migration` ran |
| `frontend/lib/`, `frontend/components/`, `frontend/app/` | frontend tests **and** build — plus the `verify-in-browser` skill if anything about the change is visual |
| `frontend/lib/strings.ts` only | frontend tests **and** build (a slug the tests assert on may live there) |
| Anything touching a wire payload | **both** — the seam between them is exactly what breaks |
| `docs/`, `README.md`, `*.md` | nothing; instead verify every command, path, port and env var you wrote is real |
| `run-dev.bat` | nothing automated exists — run it and read its report |

When in doubt, run both. They cost ~85 seconds together.

---

## 2. Backend

```bash
uv run pytest tests/
```

Expected on this machine: **1801 passed, 1 skipped, 1 failed**, ~70s.

**The one failure is expected and is not yours:**

```
tests/test_gap_understanding.py::test_every_stored_gap_free_node_derives_its_stored_state
AssertionError: no gap-free nodes to check
```

It is a development gate that predates user accounts — it looks sessions up under
the fixed test user, so sessions belonging to a real account are invisible to it.
It appears only once the app has actually been used. It is a defect in the gate,
documented in `docs/testing.md` §5. **Do not fix it as part of unrelated work**,
and do not report it as a regression. To see the rest cleanly:

```bash
uv run pytest tests/ --deselect "tests/test_gap_understanding.py::test_every_stored_gap_free_node_derives_its_stored_state"
```

**Skips are also expected.** `test_skeleton.py` and one test in `test_tools.py`
skip without `data/repos/psf/requests` or `data/repos/fastapi/fastapi`. A gate that
silently passes on an empty set is worse than one that says it did not run — do not
"repair" a skip by weakening its condition.

**Any other failure is yours.** Two specific readings:

- A failure in `test_progress.py` usually means goal readiness now falls because
  the plan changed rather than because evidence changed. That is D7, and the fix is
  in the change, not the test.
- A failure in `test_route_authz_coverage.py` means a new route declares no auth
  and is not on `PUBLIC_PATHS`. Fix the route, or add it to `PUBLIC` in that test
  **with the reason it is safe** — it is meant to feel like a decision.
- A file that passes alone and fails in the full run is the ambient-flag failure
  `tests/conftest.py` exists to prevent. Pin the flag in the test; do not reorder
  the suite.

---

## 3. Frontend

```bash
cd frontend && npm test
```

```bash
cd frontend && npm run build
```

Expected: **50 files, 793 tests**, ~15s; then a successful build, ~30s.

`npm run build` **is the type check** — there is no `tsc` script and no linter, so
skipping it means shipping type errors. Run both, always, for any frontend change.

---

## 4. What these suites cannot verify

Three things, and each has its own route:

- **Anything on screen.** Contrast, initial fold and scroll state, focus, spacing
  that cancels itself, an element ringed off-screen. More than a third of this
  project's recorded defects were only findable by rendering the page → the
  **verify-in-browser** skill.
- **Model quality.** Every model is stubbed here, so a green run says nothing
  about whether a prompt got better → the **measure-and-record** skill, which
  spends real money and must be asked for first (`smoke_session.py` alone is
  ~$0.10–0.20).
- **Invariants no test pins yet.** For a substantial change, run
  **/review-changes** to route the diff to the specialist reviewers.

Never run a `scripts/` harness as part of a gate. They are instruments, run
deliberately; most accept `--dry-run`, which makes no API calls.

---

## 5. Report honestly

State the actual numbers. If the expected failure appeared, say it appeared and
that it is the known one. If a suite was not run, say which and why. Never report
"tests pass" from a partial run.
