# `scripts/` — measurement harnesses and admin tools

Nothing here is part of the running application. These are the instruments that
measure it, plus a handful of one-off administrative tools.

> Parent: [root README](../README.md) ·
> Strategy: [docs/testing.md](../docs/testing.md)

**Most spend real money.** Almost every harness accepts `--dry-run`, which makes
no API calls and shows what would be measured. Committed output lives in
[`docs/planning/phases/evidence/`](../docs/planning/phases/evidence/).

---

## Why these exist beside 1800 unit tests

The suites use `TestClient` and stubbed models: in-process, the same Python
objects, no sockets and no live judgement. Everything they prove is real, and none
of it proves that a *browser-shaped client talking to a real server* gets the same
answers, or that a *live model* actually produces the behaviour the policy assumes.

These fill exactly those two holes, deliberately and on purpose rather than on
every commit.

---

## End-to-end smoke

| Script | What it proves |
|---|---|
| `smoke_session.py` | The whole adaptive loop against live models on `psf/requests` — plan, teach, grade a deliberately weak answer, remediate, advance. ~$0.10–0.20, 30–60s warm |
| `smoke_multiuser.py` | What `TestClient` cannot: a **real HTTP server**, real cookie attributes as a browser stores them, two genuinely isolated accounts, and a session outliving the process. **Refuses to run against `data/sessions.db`** |

```bash
uv run python scripts/smoke_multiuser.py --base http://127.0.0.1:8100
```

---

## Grader and gap-model evaluation

| Script | Question |
|---|---|
| `grader_eval.py` + `grader_eval_cases.py` | Does the Grader agree with expectations **authored before it ran**? The cases file is committed separately, so "the expected judgement came first" is checkable in git history rather than asserted |
| `grader_probe_prompt.py` | Is a *prompt-faithful* answer marked down? |
| `m10_acceptance.py` | The gap model's stated acceptance cases, live |
| `verification_probe.py` | Is a verification question actually a **new application**, or a paraphrase? |
| `gap_identity_probe.py` | Does explicit-id matching keep one misconception one gap across re-grades? |
| `reteach_probe.py` | Is a multi-gap re-teach still a good *lesson*? |
| `altitude_boundary_probe.py` | Is `right_idea_wrong_altitude` ever used for a claim that is false at every level? |
| `validate_prereq_diagnosis.py` | Does the diagnosis actually change which warm-up is chosen? Runs the real generator twice against the real repository |

---

## Planner and cost

| Script | Question |
|---|---|
| `sanity_curriculum.py` | Is the objective-first planner structurally sound and roughly sized? |
| `calibrate_bands.py` | Are the guard bands set where curricula actually land? This is what moved `map`'s ceiling from 14 to 18 |
| `measure_cost.py` | What does a session cost, and which part drives it? |
| `gate_stage4.py`, `gate_mutation_probe.py` | Migration gates: can the explorer path stand without retrieval, and does the Mutator still need it? |

---

## UI fixtures

| Script | Use |
|---|---|
| `seed_ux_fixture.py` | Seed a **throwaway** database with a session rich enough to walk the UI |
| `ux_fixture_app.py` | Serve the app against that database instead of the real one |
| `ux-probe.js` | Paste into the browser console; measures the handful of things only a rendered page can answer |
| `sync-ui-audit.sh` | Refresh the git-excluded `.ui-audit-fe` inspection copy |

```bash
uv run python scripts/seed_ux_fixture.py --db data/ux-fixture.db
uv run python -m uvicorn scripts.ux_fixture_app:app --port 8107
```

`SESSIONS_DB_PATH` is a module constant in `ux_fixture_app.py` rather than
configuration, deliberately: there is exactly one database in production, and an
environment variable that can point the app at another one is a way to lose a
learner's work.

---

## Administration

| Script | Use |
|---|---|
| `set_password.py` | Set a password from the console. **The only recovery path safe to expose outside a laptop**, since no email verification ships |
| `adopt_legacy_sessions.py` | Move the pre-accounts sessions off the inert legacy user onto a real account |
| `migrate_repo_layout.py` | Move checkouts from `data/repos/<name>` to `data/repos/<owner>/<name>` |

---

## Keeping the instruments honest

`tests/test_admin_scripts.py` and `tests/test_calibration_harness.py` are unit
tests **of these scripts**. A measurement harness that is wrong produces evidence
that is wrong, which is worse than no evidence.

The harnesses that measured the **superseded** architecture were moved out to
[`project-archive/rag-migration/harnesses/`](../project-archive/rag-migration/harnesses/);
the ones here all measure the system as it stands.
