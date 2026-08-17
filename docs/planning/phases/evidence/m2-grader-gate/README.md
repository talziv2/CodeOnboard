# M2 calibration gate — the 48-case Grader evaluation

**Date:** 2026-08-17 · **Harness:** `scripts/grader_eval.py` · **Cases:**
`scripts/grader_eval_cases.py`, unchanged — still the labels authored in
`7922190` before any Grader output was seen.

The gate [`gap-model.md` M2](../../gap-model.md#2-build-order) requires: *re-run
the 48-case evaluation and require classification agreement ≥ the recorded
48/48.* Baseline: [`../grader-evaluation.json`](../grader-evaluation.json),
2026-08-15, classification **48/48**, `gap_kind` **45/48** — **one run, no
repeats.**

**Verdict: gate met, and `gap_kind` improved.** Shipped prompt (v6), three
flag-on runs: classification **47, 48, 48**; `gap_kind` **47, 47, 48** against a
baseline of 45; one run clean on both. The `missing_prereq` diagnosis went
**4/6 → 6/6 in every run**, flag-on and flag-off.

## Two changes were measured, and they are separable

| | change | affects |
|---|---|---|
| **M2** | `_GAPS_ADDENDUM`, appended only when `CODEONBOARD_GAPS=1` | flag-on only |
| **standalone defect fix** | the `no_attempt` / `missing_prerequisite` boundary in `_SYSTEM_PROMPT` | **flag-off too — this is the production path** |

The second is not part of M2 and is reported separately below. It follows the
F1–F4 pattern: a current-behaviour defect, found while gating something else,
fixed on its own rather than bundled.

## Results

| run | classification | `gap_kind` | `missing_prereq` | ≥2 gaps | gaps | omission-phrased |
|---|---|---|---|---|---|---|
| **baseline** (2026-08-15) | **48/48** | **45/48** | 4/6 | — | — | — |
| v1 flag-on *(discarded)* | 46/48 | 35/48 | 0/6 | 17 | 42 | **15** |
| v2 flag-on *(discarded)* | 48/48 | 42/48 | 0/6 | — | — | — |
| [v3 flag-on r1](v3-flagon-r1.json) | 47/48 | 42/48 | 1/6 | 5 | 14 | 0 |
| [v3 flag-on r2](v3-flagon-r2.json) | 47/48 | 42/48 | 1/6 | 6 | 16 | 0 |
| [v3 flag-on r3](v3-flagon-r3.json) | 48/48 | 44/48 | 3/6 | 7 | 17 | 2 |
| *— boundary fix added —* | | | | | | |
| [v4 flag-off](v4-flagoff.json) | 46/48 | 44/48 | 5/6 | — | — | — |
| [v4 flag-on](v4-flagon.json) | 46/48 | 45/48 | 4/6 | 5 | 15 | 0 |
| [v5 flag-off r1](v5-flagoff-r1.json) | 48/48 | 47/48 | 6/6 | — | — | — |
| [v5 flag-off r2](v5-flagoff-r2.json) | 47/48 | 47/48 | 6/6 | — | — | — |
| [v5 flag-on r1](v5-flagon-r1.json) | 47/48 | 47/48 | 6/6 | 5 | 14 | 0 |
| [v5 flag-on r2](v5-flagon-r2.json) | 47/48 | 46/48 | 6/6 | 5 | 15 | 0 |
| [v5 flag-on r3](v5-flagon-r3.json) | 47/48 | 47/48 | 6/6 | 5 | 15 | 1 |
| **[v6 flag-off r1](v6-flagoff-r1.json)** | **48/48** | **47/48** | 6/6 | — | — | — |
| **[v6 flag-off r2](v6-flagoff-r2.json)** | 46/48 | 45/48 | 6/6 | — | — | — |
| **[v6 flag-on r1](v6-flagon-r1.json)** | 47/48 | 47/48 | 6/6 | 6 | 14 | 0 |
| **[v6 flag-on r2](v6-flagon-r2.json)** | **48/48** | **47/48** | 6/6 | 6 | 16 | 2 |
| **[v6 flag-on r3](v6-flagon-r3.json)** | **48/48** | **48/48** | 6/6 | 5 | 13 | 0 |

v6 is shipped. v1 and v2 were discarded before their JSON was preserved — their
figures come from the run reports, and what they got wrong is recorded below
because it is the substance of the finding, not because the raw rows survive.

## The measurement finding that reframes the gate

**Classification agreement is noisy at ±2, and the baseline is a single draw
from that distribution.** Across sixteen runs it lands 46–48, mean ≈ 47. The
baseline's 48/48 sits at the top of the range, not at a floor.

The gate was written ("no worse than the recorded 48/48") without that
information, because the baseline never had repeats. It is stated here so a
future step does not read a 47 as a regression, or a 48 as proof of anything.
Failures are also *different cases each run* — the signature of variance, not of
a systematic shift. This is the same discipline `cost-optimization.md` §8.4
asks for, arrived at independently.

## What the gate establishes

**Multi-gap detection works, on real sessions.** 5–6 cases per run carry 2–3
genuinely independent false claims, each a paraphrase of something the developer
actually asserted. From `requests/architecture`, `wrong_model`:

> - The auth handler inspects the URL and environment to decide whether credentials are needed.
> - The auth handler opens the connection and reads the server's challenge.
> - The auth handler returns a fresh Request object that replaces the original one.

Three separate false beliefs, one `kind`, one answer; correcting any one leaves
the other two standing. Under the scalar `gap_kind` two of them had nowhere to
live. **This is the AC1 shape, reproduced on a real session rather than
authored** — and it is the claim the whole phase rests on.

**No over-generation.** ~40 of 48 cases record zero gaps. An answer that is
merely thin, vague or misaltitude contains no false statement, and correctly
produces none.

**Harness change, measurement only.** `grade()` now also returns the gaps the
call opened and the report gained a GAP MULTIPLICITY section; the isolated node
is discarded. Without it the run is blind to M2's central claim, because the
scalar `gap_kind` reports the highest-precedence gap and says nothing about how
many there were.

## The three failure modes found, and what fixed each

Every prompt revision here was driven by a named mechanism, not by score-chasing
against the 48 cases.

**1 · v1: omissions reported as gaps.** v1 asked for "EVERY distinct
misconception" and returned 42 gaps — **all 15 `missing_prerequisite` ones were
omissions** ("the developer does not mention the fix", "no explanation of how
the dependency tree is built"). An omission is not a false claim, and
[§18.3](../../learning-engine.md#183-gap-representation) defines a gap as *a
claim the learner made that is false*.

Not cosmetic: `missing_prerequisite` is highest-precedence, so the fabrications
captured the derived scalar in 10 cases; it is the one kind that triggers a
**structural graph mutation**; and it is **blocking**, so under M7 each would
have prevented `understood` permanently. v1 also downgraded a `concise` answer
from `understood` to `partial` on a fabricated gap — the exact boundary the
baseline protects.

*Fixed* by leading with the definition and naming the failure: "NOT 'a
foundation went unmentioned'". Omission-phrased gaps: 15 → 0–2.

**2 · v3: the scalar bled toward `no_attempt`.** Answers of the form *"I can't
answer this, I don't know what a decorator is"* slid from `missing_prerequisite`
to `no_attempt` (4/6 → 1/6). **The root cause was in the base prompt, not the
addendum**: `no_attempt` was described as *"they did not try: 'I don't know',
blank…"* and `missing_prerequisite` as *"a foundation is genuinely absent"* —
and such an answer matches **both descriptions verbatim**. The baseline's 4/6
was already a coin-flip; reasoning about false statements tipped a coin on edge.

*Fixed* in the base prompt by naming the discriminator — **does the learner name
the foundation they lack?** — which is exactly the distinction the two
adaptation responses turn on (a hint versus a warm-up). Result: **6/6 in every
subsequent run, flag-on and flag-off.** This is the standalone defect fix, and
it improves production: flag-off `gap_kind` 45 → 45–47 with `missing_prereq`
4/6 → 6/6.

**3 · v4: the fix over-corrected into classification.** Legitimising "naming the
foundation" made the model read such an answer as a substantive `partial` rather
than a non-attempt. *Fixed* by separating the axes: "This does NOT make it an
attempt … `gap_kind` records WHY they fell short, never how well they did."

**4 · v5: no gaps found → read as a non-answer.** The last corner of the same
bleed. A correct-but-misaltitude answer (`AuthBase defines __call__ and raises
NotImplementedError…`) contains no false statement, so the "false statements"
framing pushed it to `off-topic`/`no_attempt` where the answer is plainly about
the right code at the wrong level. *Fixed* by one general statement: "AN EMPTY
`gaps` LIST IS NOT EVIDENCE THAT THE ANSWER WAS A NON-ANSWER."

Each fix is a statement about the *mechanism* observed, general enough to cover
cases outside the eval set. Nothing was re-worded to move a specific case, which
[§14.1](../../learning-engine.md#141-grader-calibration--evaluation-2026-08-15)
is explicit that this harness is not for.

## Cost

Sixteen 48-case runs at ≈$0.08 each ≈ **$1.30**, against the ~$15 experiment
budget `cost-optimization.md` §7.3 sanctions. The gate itself is ≈$0.08 —
"where a gate is cheap the correct move is to re-run it rather than argue about
whether it was affected", and that is what happened here five times over.
