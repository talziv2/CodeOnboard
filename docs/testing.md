# Testing architecture

> What each suite covers, what to run before a PR, and the two results that look
> like failures and are not.
>
> Index: [docs/README.md](README.md) · See also
> [`tests/`](../tests/README.md), [`scripts/`](../scripts/README.md)

---

## 1. What to run before a PR

```bash
uv run pytest tests/
```

```bash
cd frontend && npm test
```

```bash
cd frontend && npm run build
```

That is the whole gate. There is no linter and no separate typecheck script:
`npm run build` type-checks the frontend, and the backend has no configured
formatter or type checker.

**Measured on this repository at the time of writing** (Windows, Python 3.11):

| Suite | Result | Wall clock |
|---|---|---|
| `pytest tests/` | 1945 passed, 1 skipped, **1 failed** — see §5 | ~76s |
| `npm test` | 48 files, 783 tests, all passing | ~14s |
| `npm run build` | succeeds, 11 routes | ~30s |

---

## 2. The strategy in one paragraph

Almost the entire learning policy is written as **pure functions** — no IO, no
model calls, no mutation beyond the graph passed in. `progress.py`,
`understanding.py`, `adaptation.py`, `retry.py`, `scope.py`, `gaps.py` and
`curriculum.select()` all state this in their module docstrings, and it is the
point rather than a side effect: it means the rules that decide what a learner is
told can be tested exhaustively, deterministically, and **without an API key**.

Everything that does need a model is either stubbed (the unit suites) or lives in
`scripts/` as a measurement harness that is run deliberately and whose output is
committed as evidence.

---

## 3. Backend suite

`pytest`, configured in `pyproject.toml` with `pythonpath = ["."]`. No plugins
beyond pytest itself.

### Two suite-wide fixtures, both in `tests/conftest.py`

**Ambient flags are neutralised for every test.** `CODEONBOARD_CURRICULUM` and
`CODEONBOARD_GAPS` are deleted from the environment by an autouse fixture, so a
test that depends on one has to say which and how.

This exists because of a real failure: `test_mentor_dossier.py` failed 14 tests on
any full-suite run and passed all of them in isolation. `backend/api.py` loaded
`.env` at import time with `override=True`; the developer's `.env` carries
`CODEONBOARD_CURRICULUM=1`; so any test file importing the API silently switched
the Mentor's planner for every test that ran afterwards. The fix was not to pin
the flag in the one file that broke — the failure was that *an ambient value
decided which code path ran, and nothing in the suite said so.*

**Every test runs as one fixed user by default.** Sixteen test files drive session
routes, and every one of those routes now requires a signed-in caller. Teaching
all sixteen to register and carry a cookie would bury what each is actually
testing.

This is a **real user id threaded through the real ownership checks**, not a
bypass: `load_graph` still filters on it and `save_graph` still stamps it. What is
stubbed is only the cookie→user step. A module opts out with
`pytestmark = pytest.mark.real_auth` when it needs to exercise authentication
itself — `test_auth.py` and `test_ownership.py` both do.

### Coverage by area

| Area | Files |
|---|---|
| Repository understanding | `test_chunker`, `test_skeleton`, `test_anchors`, `test_tools`, `test_explore`, `test_survey`, `test_investigation`, `test_structure`, `test_cloner`, `test_repo_identity`, `test_repo_layout_migration` |
| Agents | `test_goal_agent`, `test_documentation_agent`, `test_reviewer_agent`, `test_mentor_dossier`, `test_curriculum_planner`, `test_curriculum`, `test_briefing`, `test_teaching_agent`, `test_teaching_forms`, `test_grader_agent`, `test_grader_gaps`, `test_mutator`, `test_prerequisite_diagnosis` |
| Orchestration | `test_explorer_pipeline`, `test_pipeline_progress` |
| Learning model | `test_learning_graph`, `test_progress`, `test_understanding`, `test_history`, `test_patterns`, `test_gap_insight`, `test_scope`, `test_decision_is_not_evidence`, `test_attempt_history`, `test_question_traceability` |
| Gap model | `test_gap_model`, `test_gap_adaptation`, `test_gap_verification`, `test_gap_understanding`, `test_gap_remediation`, `test_gap_remediation_rounds`, `test_gap_intents`, `test_gap_api` |
| Adaptation and retry | `test_adaptation`, `test_adaptation_api`, `test_retry_dispatch` |
| Persistence | `test_learning_store`, `test_plan_snapshot`, `test_session_reset`, `test_migration`, `test_legacy_session_compatibility`, `test_store_concurrency`, `test_dossier_session` |
| API and auth | `test_session_api`, `test_sessions_api`, `test_goal_api`, `test_auth`, `test_ownership`, `test_google_oauth`, `test_password_reset`, `test_route_authz_coverage`, `test_security`, `test_cors`, `test_first_run`, `test_env_precedence` |
| Harness self-checks | `test_calibration_harness`, `test_admin_scripts` |

### Three tests worth knowing about individually

- **`test_route_authz_coverage.py`** fails the build when a route declares neither
  an auth dependency nor membership of `PUBLIC_PATHS`. It is the layer that
  catches the route somebody adds without reading the ownership rules.
- **`test_gap_model.py::test_the_persistence_path_never_reads_the_flag`** asserts
  *structurally* — by inspecting the module — that nothing in the persistence path
  consults `CODEONBOARD_GAPS`, so the flag/storage contract cannot rot silently.
- **`test_gap_understanding.py`** contains an AST check that nothing re-derives
  the understanding state outside `graph.understanding_of()`.

### Fixtures and test databases

Persistence tests build a temp database per test via `tmp_path`; nothing writes to
`data/sessions.db`. `SESSIONS_DB_PATH` is a module-level indirection in
`backend/api.py` precisely so tests can point persistence somewhere else.

Frontend payloads come from `frontend/test/factories.ts`.

---

## 4. Frontend suite

Vitest with jsdom and Testing Library, configured in `frontend/vitest.config.ts`.
The tests are **behavioural rather than snapshot-based**: they build a server
payload from a factory and assert what a learner can see and press.

The heaviest files guard exactly the seams the derived view-model layer was
introduced to remove — `lesson/retryLoop.test.tsx`,
`lesson/surfacesNav.test.tsx`, `lesson/surfacesAwareness.test.tsx`,
`lesson/nextCanvas.test.tsx`, `LessonPanel.test.tsx`, `RouteRail.test.tsx`,
`MapView.test.tsx`.

---

## 5. Two results that look like failures and are not

### Skipped backend tests

Several tests skip when their fixture is absent, and the skip is deliberate — *a
gate that silently passes on an empty set is worse than one that says it did not
run.*

| Test | Skips when |
|---|---|
| `test_skeleton.py` (`requires_requests`, `requires_fastapi`) | `data/repos/psf/requests` or `.../fastapi/fastapi` is not cloned |
| `test_tools.py` (one test) | `psf/requests` is not cloned |
| `test_gap_understanding.py::test_every_stored_gap_free_node_derives_its_stored_state` | `data/sessions.db` does not exist |

On a **fresh clone** all of these skip, and the suite is green.

### The one known failing test

Once you have actually used the app, `test_every_stored_gap_free_node_derives_its_stored_state`
starts running and **fails** with `AssertionError: no gap-free nodes to check`.

It is a development gate that re-checks stored sessions against the current model,
and it predates user accounts: it looks sessions up under the fixed test user, so
the ones belonging to your real account are invisible to it and it concludes there
was nothing to check. **It is a defect in that gate, not in your installation.**

To run everything else:

```bash
uv run pytest tests/ --deselect "tests/test_gap_understanding.py::test_every_stored_gap_free_node_derives_its_stored_state"
```

---

## 6. There is no automated end-to-end suite

There is no Playwright or Cypress layer, and adding one is not planned. What
exists instead is a set of **deliberate harnesses** in `scripts/`, each of which
spends real money and is run on purpose:

| Script | What it exercises |
|---|---|
| `smoke_session.py` | The whole adaptive loop against live models on `psf/requests`, in-process. ~$0.10–0.20, 30–60s warm |
| `smoke_multiuser.py` | A **real HTTP server**, a real cookie jar, two isolated accounts, and a session outliving the process. Refuses to run against `data/sessions.db` |
| `grader_eval.py` | The Grader against cases authored **before** it ran (`grader_eval_cases.py` is committed separately, so "the expected judgement came first" is checkable in git history) |
| `sanity_curriculum.py`, `calibrate_bands.py` | Is the objective-first planner structurally sound, and are the guard bands set where curricula actually land |
| `m10_acceptance.py`, `verification_probe.py`, `gap_identity_probe.py`, `reteach_probe.py`, `altitude_boundary_probe.py` | The gap model's acceptance cases and its named risks |
| `measure_cost.py` | What a session actually costs, and which part drives it |
| `seed_ux_fixture.py` + `ux_fixture_app.py` | A throwaway database rich enough to walk the UI without spending anything |

Their committed output lives in `docs/planning/phases/evidence/`. Most accept
`--dry-run`, which makes no API calls.

`tests/test_admin_scripts.py` and `tests/test_calibration_harness.py` keep the
harnesses themselves honest.

---

## 7. Manual verification

Some behaviour is only observable in a browser. The procedure used for this
documentation pass, and a reasonable one to repeat, is in the root README's
first-run walkthrough: register, start a session on `psf/requests`, answer the
first question **wrongly on purpose**, and check that a gap ledger appears, that
*Check me on this* asks a genuinely different question, that clearing it does not
by itself mark the stop demonstrated, and that goal readiness moves only when the
objective is answered.

`scripts/ux-probe.js` measures the handful of things only a rendered page can
answer; paste it into the browser console on any CodeOnboard page.
