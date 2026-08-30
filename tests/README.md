# `tests/` — the backend suite

> Parent: [root README](../README.md) ·
> Strategy: [docs/testing.md](../docs/testing.md)

```bash
uv run pytest tests/
```

**1801 passed, 1 skipped, 1 failed** on a used development database; ~86s. The one
failure and the skips are both expected — see §3.

---

## 1. What makes this suite fast

Almost the entire learning policy is written as **pure functions**. `progress.py`,
`understanding.py`, `adaptation.py`, `retry.py`, `scope.py`, `gaps.py` and
`curriculum.select()` all say so in their module docstrings, and it is the point
rather than a side effect: the rules that decide what a learner is told can be
tested exhaustively, deterministically, and **without an API key**.

Everything that needs a model is stubbed. Live-model behaviour is measured
deliberately by the harnesses in [`scripts/`](../scripts/README.md), whose output
is committed to `docs/planning/phases/evidence/`.

---

## 2. `conftest.py` — two suite-wide fixtures

**Ambient flags are neutralised for every test.** `CODEONBOARD_CURRICULUM` and
`CODEONBOARD_GAPS` are deleted from the environment, so a test that depends on one
has to say which and how.

This exists because of a real failure that is worth knowing: `test_mentor_dossier.py`
failed 14 tests on any full-suite run and passed all of them in isolation.
`backend/api.py` loaded `.env` at import time with `override=True`; the developer's
`.env` carries `CODEONBOARD_CURRICULUM=1`; so any test file importing the API
silently switched the planner for every test that ran afterwards. The fix was not
to pin the flag in the one file that broke — the failure was that **an ambient
value decided which code path ran, and nothing in the suite said so.**

**Every test runs as one fixed user by default.** Sixteen files drive session
routes, and every one now requires a signed-in caller. This is a **real user id
threaded through the real ownership checks**, not a bypass: `load_graph` still
filters on it and `save_graph` still stamps it. Only the cookie→user step is
stubbed. A module opts out with `pytestmark = pytest.mark.real_auth` when it
exercises authentication itself — `test_auth.py` and `test_ownership.py` do.

Persistence tests build a temp database per test; **nothing writes to
`data/sessions.db`**. `SESSIONS_DB_PATH` is a module-level indirection in
`backend/api.py` precisely so tests can point it elsewhere.

---

## 3. Skips, and the one known failure

A gate that silently passes on an empty set is worse than one that says it did not
run, so several tests skip when their fixture is absent:

| Test | Skips when |
|---|---|
| `test_skeleton.py` (`requires_requests`, `requires_fastapi`) | The fixture repository is not cloned |
| `test_tools.py` (one test) | `psf/requests` is not cloned |
| `test_gap_understanding.py::test_every_stored_gap_free_node_derives_its_stored_state` | `data/sessions.db` does not exist |

**On a fresh clone all of these skip and the suite is green.** Once you have used
the app, that last one starts running and **fails** with `no gap-free nodes to
check`: it looks sessions up under the fixed test user, so sessions belonging to a
real account are invisible to it. It is a defect in the gate, not in your
installation.

```bash
uv run pytest tests/ --deselect "tests/test_gap_understanding.py::test_every_stored_gap_free_node_derives_its_stored_state"
```

---

## 4. Three tests that guard the architecture rather than a feature

| Test | Guards |
|---|---|
| `test_route_authz_coverage.py` | Fails the build when a route declares neither an auth dependency nor membership of `PUBLIC_PATHS`. It catches the route somebody adds without reading the ownership rules |
| `test_gap_model.py::test_the_persistence_path_never_reads_the_flag` | Asserts **structurally** that nothing in the persistence path consults `CODEONBOARD_GAPS`, so the flag/storage contract cannot rot silently |
| `test_gap_understanding.py` (AST check) | Asserts nothing re-derives the understanding state outside `graph.understanding_of()` |

`test_progress.py` is the other one worth reading before changing anything nearby:
it pins **every** plan mutation against the rule that goal readiness may fall only
when evidence changes.

---

## 5. Map

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

Frontend tests live in `frontend/` beside the code they cover; run them with
`cd frontend && npm test`.
