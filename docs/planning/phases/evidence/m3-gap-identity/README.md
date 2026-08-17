# M3 — does explicit-id matching keep one misconception one gap?

**Date:** 2026-08-17 · **Probe:** `scripts/gap_identity_probe.py` ·
**Raw data:** [`gap-identity.json`](gap-identity.json) · 6 real nodes × 3 grades
= **18 grading calls**, `CODEONBOARD_GAPS=1`.

[`gap-model.md` §3.2](../../gap-model.md#32-gap-identity-and-matching-across-re-grades)
refuses text-similarity merging — *"a heuristic that silently merges two
distinct misconceptions is worse than a duplicate"* — and accepts a known price:
the model can over-report `new` and duplicate a gap. It requires that price be
**measured during M3, not assumed away**. This is that measurement.

**Result: the strategy holds. Zero duplicates, zero invented ids.**

| §3.2 metric | value |
|---|---|
| reported gaps matching an existing id | **29** (9 verbatim + 20 paraphrase) |
| reported gaps declared `new` | **1** |
| `new` gaps that are in fact semantic duplicates *(hand-judged)* | **0** |
| referenced ids outside the supplied set, rejected by our code | **0** |

## Method

Three grades of one real node, in order, against the same accumulating gap list.
Unlike `grader_eval.py` — which isolates every case so grades cannot influence
one another — this probe depends on exactly that influence.

1. **OPEN** — the `wrong_model` answer from the Grader evaluation set, already
   known to contain 2–3 independent false claims. Gaps open.
2. **VERBATIM** — the *same answer again*. Every gap it reports must match an id
   it was just shown, so **any `new` is a certain duplicate**. No hand judgement
   is required or used. This is the identity floor: fail it and the strategy is
   broken outright.
3. **PARAPHRASE** — the same false claims restated so that almost no content
   words survive. This is the real test, because matching can no longer be done
   on surface text. `new` reports here get the hand judgement §3.2 asks for.

The paraphrases live in the probe and were authored **before any probe output
was seen**, for the same reason the Grader evaluation's labels were: one written
after watching what matches is a paraphrase tuned to pass. Each asserts exactly
the original's false claims — no more, so that a legitimate `new` cannot be
mistaken for a duplicate.

## Per-node

| node | opened | verbatim (m/n/r) | paraphrase (m/n/r) | duplicates |
|---|---|---|---|---|
| `requests/component` — auth parameter forms | 1 | 1 / 0 / 0 | 1 / 0 / 0 | 0 |
| `requests/risk` — response.text encoding | 2 | 1 / 0 / 0 | 1 / **1** / 0 | 0 *(judged)* |
| `requests/architecture` — AuthBase contract | 2 | 2 / 0 / 0 | **3** / 0 / 0 | 0 |
| `fastapi/architecture` — app/router two layers | 2 | 2 / 0 / 0 | 2 / 0 / 0 | 0 |
| `fastapi/flow` — decorator chain | 2 | 2 / 0 / 0 | 2 / 0 / 0 | 0 |
| `fastapi/synthesis` — declaration vs runtime | 1 | 1 / 0 / 0 | 1 / 0 / 0 | 0 |

## The identity floor: clean

**0 certain duplicates.** Across six verbatim re-grades the model matched 9 of
the 10 open gaps by id and declared `new` **zero** times. The one gap not
re-reported is `requests/risk`, where an identical answer surfaced one of its
two gaps rather than both — detection variance, and the correct outcome either
way: [§18.5](../../learning-engine.md#185-arbitration-policy) says an
unreported gap stays open and is not touched, which is what happened.

## The hand judgement

One `new` gap, on `requests/risk`. Open gaps at the time:

> - `charset_normalizer` is called during `.text` access and causes performance overhead that the proposed change removes.
> - Removing `charset_normalizer` means responses are decoded twice instead of once, making the change slower.

The new claim:

> - Without `charset_normalizer`, you would still get the right characters, just slower.

**Judged genuinely new, not a duplicate.** Both open gaps are claims about
*performance*; this one is a claim about *correctness* — that the output stays
right. Correcting "it is not actually slower" would leave "the characters still
come out correct" standing, which is precisely §18.5's separability test. It is
also the more dangerous of the two falsehoods, since removing
`charset_normalizer` produces mojibake rather than slowness. Grade 1 did not
surface it and the paraphrase grade did; that is detection variance between
calls, not a failure of identity.

## Observed, harmless, recorded anyway

`requests/architecture` reported **3 matches against 2 open gaps** — the model
split the paraphrase into three entries, two of them pointing at the same id.
The final gap count stayed **2**.

This is the shape of over-reporting that costs nothing: matching *creates*
nothing, so a duplicated reference is absorbed. It is recorded because the same
behaviour would matter if a later step ever counted **reports** rather than
**gaps** — M4's active set must count gaps.

## What this does not establish

- **`verified` gaps.** The M3 invariant *"a `verified` gap never reopens under a
  new id"* cannot be exercised yet: nothing writes `verified` before M6. What is
  in place is the precondition — `_open_gaps_section` offers **open gaps only**,
  so a settled gap is never a matching candidate, pinned by
  `test_settled_gaps_are_never_offered_for_matching`.
- **Adversarial rewording.** The paraphrases are faithful restatements, which is
  the realistic case (a learner repeating a misconception in their own words).
  A learner who half-corrects a misconception into a *related but different*
  false claim is the harder case, and it is genuinely ambiguous whether that
  should match or open a new gap. Not probed, and not decided.
- **Volume.** Six nodes, one repeat. Enough to refute "the model over-reports
  `new`" as a live concern; not enough to put a rate on it.

## Cost

18 grading calls at ≈$0.0017 each ≈ **$0.03**.
