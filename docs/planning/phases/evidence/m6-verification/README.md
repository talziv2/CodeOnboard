# M6 — verification: live validation **NOT YET RUN**

**Status: BLOCKED, 2026-08-17.** The probe exists, is wired, and was executed —
it could not reach the API:

```
verification: question generation failed: Error code: 400 —
'Your credit balance is too low to access the Anthropic API.'
```

**No live evidence for M6 exists yet. Nothing in this directory should be read as
validation, and M6's acceptance criterion is unmet until this probe runs.**

The deterministic half of M6 *is* done: 33 tests in
`tests/test_gap_verification.py`, 1014 passing overall. What those tests cannot
reach is exactly what this probe is for.

## What is owed

**AC2** ([`gap-model.md` §4](../../gap-model.md#4-acceptance-cases--carried-from-the-original-defect))
requires two things and states plainly that the second cannot be asserted:

> the verification prompt is **not** the original prompt (asserted mechanically),
> and a learner still holding the misconception **cannot answer it correctly**
> (judged live — the one property no assertion can carry).

`scripts/verification_probe.py` tests the second as a **double dissociation**,
with both answers authored before any question was generated:

| answer | must be |
|---|---|
| `holding` — expresses the false belief | `resolved: false` |
| `corrected` — states the true model, in different words from the lesson | `resolved: true` |

Both halves matter. A question that fails everything is not a good question, it
is an impossible one — so `corrected` failing is as much a defect as `holding`
passing. Pre-authoring is what makes this evidence rather than a demo: the
answers cannot be tuned to a question that did not exist when they were written.

A third case probes the rule §18.7 calls the most important in the whole design:
with **two** gaps pending, an answer correct about the first and silent about the
second must close only the first.

Known limitation to read for, once it runs: a `holding` answer can be judged
unresolved for the *wrong reason* — "did not address the question" rather than
"asserted something false". The probe prints the rationale for every case so the
two can be told apart, and the distinction must be made by reading rather than
from the verdict alone.

**Also owed and also blocked:** the cost re-measurement M6's build row requires.
Verification adds model calls per gap, so Baseline 1 does not survive this step
([`gap-model.md` §7](../../gap-model.md#7-cost--this-phase-increases-it)).

## To run it

```bash
CODEONBOARD_GAPS=1 uv run python scripts/verification_probe.py
```

8 calls, ≈$0.02. `--dry-run` lists the cases without spending anything.

## One thing the blocked run did establish

Incidental, and not a substitute for the above: the failure path behaved
correctly. `teaching_verify.verify` returned `None`, appended the reason to
`state.errors`, and left every gap `open` with `verification_attempts` at 0 — so
an API outage during verification costs the learner nothing and closes nothing.
That is the behaviour
`test_a_generation_failure_returns_none_and_never_raises` asserts, observed
against a real failure rather than a mocked one.
