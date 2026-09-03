---
name: measure-and-record
description: Run a live-model measurement harness from scripts/ and record its result as evidence — grader evaluation, verification and gap probes, curriculum sanity, band calibration, cost measurement, or the multi-user HTTP smoke. Use when a claim about model behaviour, curriculum shape or cost needs proving, and whenever writing anything into docs/planning/phases/evidence/.
---

# Measuring, and recording what it showed

The unit suites stub every model. Nothing in `tests/` can tell you whether a
prompt got better, whether a verification question is genuinely new, whether the
guard bands sit where curricula actually land, or what a session costs. That is
what `scripts/` is for: instruments, run deliberately, whose output is committed
as evidence.

**They spend real money on the user's own API key. Never run one unless asked, and
say what it will cost first.**

---

## 1. Pick the instrument

| Question | Script |
|---|---|
| Does the Grader agree with judgements authored **before** it ran? | `grader_eval.py` + `grader_eval_cases.py` |
| Is a prompt-faithful answer marked down? | `grader_probe_prompt.py` |
| Is a verification question a new application or a paraphrase? | `verification_probe.py` |
| Does one misconception stay one gap across re-grades? | `gap_identity_probe.py` |
| Is a multi-gap re-teach still a good lesson? | `reteach_probe.py` |
| Is `right_idea_wrong_altitude` used for a claim false at every level? | `altitude_boundary_probe.py` |
| Does the diagnosis change which warm-up is chosen? | `validate_prereq_diagnosis.py` |
| The gap model's stated acceptance cases, live | `m10_acceptance.py` |
| Is the objective-first planner structurally sound and sized? | `sanity_curriculum.py` |
| Are the guard bands where curricula actually land? | `calibrate_bands.py` |
| What does a session cost, and which part drives it? | `measure_cost.py` |
| The whole adaptive loop, live, in-process (~$0.10–0.20) | `smoke_session.py` |
| Real HTTP, real cookies, two isolated accounts | `smoke_multiuser.py` |

## 2. Dry run first

Most accept `--dry-run`, which makes **no API calls** and shows what would be
measured:

```bash
uv run python scripts/measure_cost.py --dry-run
```

Use it to confirm the cases, the repository and the flags are what you meant
before spending anything.

## 3. Run it correctly

- **State the cost and get agreement** before the live run.
- **Say which configuration it ran under**, or it is not evidence. There is far
  less to pin than there was: `CODEONBOARD_CURRICULUM` and `CODEONBOARD_GAPS` have
  been removed, so the planner and the gap model are no longer variables — every
  run gets both. `CODEONBOARD_TUTOR` is the only flag left, and it defaults on.
  Note that `.env` **fills gaps and does not win**, so a variable set on the
  command line takes precedence. Evidence already on file that names the old flags
  is still valid for the configuration it names; do not restate it as current.
- **Never point one at `data/sessions.db`.** `smoke_multiuser.py` and
  `seed_ux_fixture.py` refuse it; anything new should too.
- Run the backend **without `--reload`** for anything that drives
  `/session/start` — a reload mid-request kills it.
- If a harness itself changed, `tests/test_admin_scripts.py` and
  `tests/test_calibration_harness.py` are its unit tests. A measurement
  instrument that is wrong produces evidence that is wrong, which is worse than
  no evidence.

## 4. Author the expectation before you look

The one property that makes this corpus credible: **`grader_eval_cases.py` is
committed separately from its results, so "the expected judgement came first" is
checkable in git history.** Keep that discipline — write the cases, the predicted
outcome and the pass condition, commit them, *then* run.

Where a claim cannot be asserted mechanically, test it as a **double
dissociation**: an answer that still holds the misconception must fail, and one
that does not must pass, with both authored before any question was generated.

## 5. Record it

Committed output goes in `docs/planning/phases/evidence/<name>/`, with the raw
JSON and a short `README.md` beside it carrying:

- **Date, script, cost, number of calls, and the flags it ran under.**
- **The verdict in one line** — what passes, what does not.
- **What the measurement demanded**, quoted from the phase document that asked for
  it, with a link.
- **What it does *not* settle.** This is the part that makes the record worth
  keeping.

Label claims the way the corpus already does: **`[FACT]`** verified here with a
file:line or a query, **`[REC]`** a recommendation, **`[OPEN]`** needs a decision.

Then update the phase document in `docs/planning/phases/` that scheduled the
measurement — record what shipped, and where it diverged from the plan. Do not
rewrite the original plan to match the outcome; the divergence is the interesting
part. See the `sync-documentation` skill.

## Completion criteria

- The cost was stated and agreed before the run.
- The configuration is recorded, flags included.
- The expectation was authored first and is visible in history.
- The evidence directory has raw output **and** a README that says what the result
  does not settle.
- The phase document reflects it.

## Common failure modes

- Running a live harness to "check" a change nobody asked to measure.
- Reporting a result without saying which flags produced it.
- Recording only the number that supports the change.
- Editing the expected cases after seeing the output.
- Treating one run as a measurement — several of these are recorded across two or
  three runs precisely because one is not.
