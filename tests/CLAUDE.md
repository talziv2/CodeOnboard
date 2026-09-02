# Working in `tests/`

> Strategy: [`docs/testing.md`](../docs/testing.md) · Map and rationale:
> [`tests/README.md`](README.md)

```bash
uv run pytest tests/
```

Expected: **1945 passed, 1 skipped, 1 failed**, ~76s. The failure
(`test_gap_understanding.py::test_every_stored_gap_free_node_derives_its_stored_state`)
is a development gate that predates accounts and fails on any used database. Do
not fix it as part of unrelated work.

---

## Two suite-wide fixtures you are writing against

Both live in `conftest.py`, and both exist because of a real failure.

**Ambient flags are deleted for every test.** `CODEONBOARD_CURRICULUM`,
`CODEONBOARD_GAPS` and `CODEONBOARD_TUTOR` are removed from the environment, so
**a test that depends on one must set it explicitly**.

*Deleted means unset, not off.* Each flag then reads the default the repository
ships — `0` for the first two and **`1` for `CODEONBOARD_TUTOR`, which defaults
on** — so the suite exercises the configuration a fresh clone actually runs rather
than a fourth one that exists only in tests. A test wanting the Tutor absent sets
`CODEONBOARD_TUTOR=0` and says so.

This exists because `test_mentor_dossier.py` failed
14 tests on any full run and passed all of them alone: importing `backend.api`
loaded the developer's `.env`, which switched the planner for everything that ran
afterwards. The lesson was not "pin the flag in that file" — it was that an
ambient value decided which code path ran and nothing in the suite said so.

**Every test runs as one fixed signed-in user.** This is a **real user id threaded
through the real ownership checks**, not a bypass: `load_graph` still filters on
it and `save_graph` still stamps it. Only the cookie→user step is stubbed. A
module that exercises authentication itself opts out with
`pytestmark = pytest.mark.real_auth` — `test_auth.py` and `test_ownership.py` do.

## Rules

- **Nothing may touch `data/sessions.db`.** Build a database per test with
  `tmp_path`; `SESSIONS_DB_PATH` is a module-level indirection in `backend/api.py`
  precisely so tests can point elsewhere. That file is the irreplaceable
  development corpus behind `docs/planning/phases/evidence/`.
- **Every model is stubbed.** A test asserts wiring and policy, never model
  quality. If a change can only be proven by a live model, it belongs in
  `scripts/` — see the `measure-and-record` skill.
- **Test behaviour, not implementation.** The learning policy is pure functions
  (`progress`, `understanding`, `adaptation`, `retry`, `scope`, `gaps`,
  `curriculum.select`), so cover the rules exhaustively and deterministically —
  that is the point of the purity, not a side effect.
- **A skip that means "the fixture is absent" is correct.** A gate that silently
  passes on an empty set is worse than one that says it did not run. Do not
  weaken a skip condition to make a suite look greener.
- Frontend tests live beside the code in `frontend/`, are behavioural rather than
  snapshot-based, and build payloads from `frontend/test/factories.ts`.

## Six tests that guard the architecture rather than a feature

Read them before changing anything nearby, and be suspicious of a change that
edits one to pass.

| Test | Guards |
|---|---|
| `test_route_authz_coverage.py` | A route that declares neither an auth dependency nor `PUBLIC_PATHS` membership fails the build |
| `test_gap_model.py::test_the_persistence_path_never_reads_the_flag` | Structurally: nothing in the persistence path reads `CODEONBOARD_GAPS` |
| `test_gap_understanding.py` (AST check) | Nothing re-derives the understanding state outside `graph.understanding_of()` |
| `test_progress.py` | Every plan mutation, against the rule that goal readiness may fall only when evidence changes |
| `test_tutor_context.py` | Structurally, three ways: the scaffold context has no field that could hold the answer, its rendered prompt contains none, and its builder never reads the keys |
| `test_tutor_boundary.py` | A conversation is not evidence — no tutor module imports a writer, and `/tutor/ask` leaves `to_dict()` byte-identical |

`test_admin_scripts.py` and `test_calibration_harness.py` are unit tests **of the
measurement harnesses** — a wrong instrument produces wrong evidence, which is
worse than none.
