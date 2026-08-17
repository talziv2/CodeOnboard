# The `wrong_model` / `right_idea_wrong_altitude` boundary

**Date:** 2026-08-18 · **Probe:** `scripts/altitude_boundary_probe.py` ·
**Raw:** [`altitude-boundary.json`](altitude-boundary.json), [`r2/`](r2),
[`fixed-r1/`](fixed-r1), [`fixed-r2/`](fixed-r2), [`gate/`](gate),
[`ac1-after/`](ac1-after) · ≈$0.25 in model calls.

**The question.** *If a learner's claim is false regardless of abstraction
level, should it ever be classified `right_idea_wrong_altitude`?*

**The answer: no — and the Grader was doing it anyway, reproducibly.** A general
defect was found, corrected with one clause, and the correction is measured
below. **It was not aimed at AC1**, and AC1 was not the evidence for it.

## The definitions already said no

Neither definition needed changing; both already require the claim be true
somewhere:

| where | wording |
|---|---|
| base prompt (the scalar) | "**the substance is right** but pitched at the wrong level" |
| addendum (per gap) | "true of the implementation **but false as a statement about responsibility**, or the reverse" |

So the principle was already the intended one. What neither said is what to do
when **neither reading is true** — and that silence is where the defect lived.

## Evidence 1 — the existing corpus: 1 of 28

Every `right_idea_wrong_altitude` gap the phase ever recorded (28 distinct
claims across M3, M5, M6, M9 and M10 evidence), judged by hand:

- **The FastAPI `api_route` family (≈9 claims)** — *legitimate*. The coarse claim
  ("`get()` leads to `add_api_route()`") is **true**; the error is eliding the
  decorator factory between them. Several are phrased as exactly that:
  *"omitting that `api_route()` is a decorator factory"*.
- **The `prepare_content_length` family (≈8)** — *legitimate*. True of the
  implementation; wrong in scope as an answer about what the auth parameter does.
- **The remaining (≈10)** — *legitimate*: real implementation facts offered
  instead of the contract, e.g. *"identified `HTTPBasicAuth` setting
  `r.headers['Authorization']` as the answer to what the auth handler owns"*.
- **One outlier** — AIMA's *"`solution()` collects both the states and actions"*.
  False at every level: `solution()` returns actions only.

**1 of 28 is a borderline judgement, not a measurement**, and the corpus is
dominated by a handful of repeated scenarios. It could not answer the general
question, which is why the probe exists.

## Evidence 2 — the controlled probe

Nine authored claims against real nodes with real objectives, ground truth fixed
before any output was seen:

- **FALSE_EVERYWHERE (5)** — no reading at any altitude makes them true.
- **TRUE_WRONG_LEVEL (4)** — correct implementation facts offered as the answer
  to a responsibility question.

| | before | after |
|---|---|---|
| false-at-every-level → `wrong_model` | 5/10 | **8/10** |
| **…leaked into `right_idea_wrong_altitude`** | **3/10** | **0/10** |
| true-but-wrong-level → altitude | 1/8 | 1/8 |

Two runs each. **The leak was reproducible**: F1 ("`solution()` returns states
too") leaked 2/2 before the fix and 0/2 after; F2 ("the parent pointer is
attached by the frontier") leaked 1/2 before, 0/2 after.

**Why it matters beyond tidiness:** `right_idea_wrong_altitude` is
**non-blocking**. A flatly false belief classified that way never holds a node
back from `understood` and is never put to a verification question. The learner
keeps the false belief and the system reports mastery — the exact failure the
whole gap model exists to prevent.

### A structural finding, recorded rather than acted on

Three of the four TRUE_WRONG_LEVEL cases produced **no gap at all**, in every
run, before and after. That is consistent behaviour, not a bug: the addendum
defines a gap as "a statement the developer MADE that is FALSE" and says
explicitly that "if what they said is true, it is not a gap". A true statement
offered at the wrong altitude is therefore excluded from the gaps list by
construction — which means `right_idea_wrong_altitude` is reachable mainly for
claims that are false *as scoping assertions* ("the final step is X"), which is
what the 28-item corpus is made of.

There is a real tension there — a kind whose definition describes statements the
gap rules exclude — but it is a design question about what gaps are for, not a
classification error, and nothing in the evidence shows it costing a learner
anything. Left as-is.

## The correction

One clause, in the addendum's per-gap definition only. It states no new concept
— it turns the existing requirement into a decision rule and names the failure:

> `right_idea_wrong_altitude` — what they said is **TRUE** of the implementation
> but false as a statement about responsibility, or the reverse. **IT HAS TO BE
> TRUE AT SOME LEVEL. Before choosing it, find the reading that makes the
> statement correct; if there is none — if the claim is wrong about the code
> however you look at it — it is `wrong_model`, no matter how close to the right
> area it sounds.**

The base prompt's scalar definition was left alone: it already reads "the
substance is right", and the leak was in the gaps list. Flag-off behaviour is
untouched.

## The required gates, after the correction

### 48-case calibration gate

| | baseline | M10 (pre-fix) | **after** |
|---|---|---|---|
| classification | 48/48 | 46/48 | **47/48** |
| `gap_kind` | 45/48 | 46/48 | **47/48** |
| `missing_prereq` | 4/6 | 6/6 | **6/6** |

**The side-effect check that mattered most: all six `wrong_altitude` cases still
classify as `right_idea_wrong_altitude`, and all six agree.** The correction
sharpened the boundary without collapsing the kind — the risk was that
everything would be pushed to `wrong_model`, and it was not.

The single failure is `requests/risk` × `concise`, a case documented as unstable
since M6 and which also failed the pre-fix M10 gate. Not attributable here.

### AC1, re-run

| | pre-fix | after |
|---|---|---|
| `psf/requests` | PASS 2/2 | **PASS 2/2** |
| `aimacode/aima-python` | PASS 1/4 | **PASS 2/3** |

And the *nature* of the AIMA shortfall changed. Before, it failed two ways:
detection (3/4) **and** misclassification as non-blocking (2 of 3 detections).
Now, when the second claim is detected it is `wrong_model` in **3/3** — the
classification half is fixed, and what remains is purely **detection variance**
on a subtle claim (2/3).

**AC1 is still not clean on AIMA, and the M10 record stands.** The remaining
failure is a different, honest limitation: the Grader sometimes does not notice
the second misconception at all.

## Recommendation

**Keep the correction.** It fixes a reproducible defect with a real consequence,
it is one clause restating an existing rule, it improved the gate on both axes,
and it left the legitimate altitude cases untouched.

**Do not read it as making AC1 pass.** AIMA moved from 1/4 to 2/3 as a
side-effect of a general fix; the residual detection variance is unaddressed and
should stay recorded as M10's qualification.
