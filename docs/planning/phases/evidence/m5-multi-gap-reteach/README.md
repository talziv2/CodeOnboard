# M5 — is a multi-gap re-teach still a good *lesson*?

**Date:** 2026-08-17 · **Probe:** `scripts/reteach_probe.py` · **Node:**
`requests/architecture`, the AuthBase contract (`7ecc5fe3`, session
`a3234f41…`) · 3 re-teach calls per run.

[`gap-model.md` M5](../../gap-model.md#2-build-order) names this risk itself and
says no test covers it: *"re-teach quality with 3 gaps at once — a prompt
property no test asserts (LR3-class risk)"*. A re-teach can name all three
misconceptions, pass every structural check, and still be a worse lesson than
the one-gap version.

**Method.** The same real node and the same learner answer, re-taught three
times with **1, 2 and 3** target gaps. Only the number of misconceptions varies,
so the outputs are directly comparable and any degradation is attributable. The
gaps are the real ones the Grader opened on this node during the
[M3 probe](../m3-gap-identity/README.md), not written for this script.

**Verdict: the first run found a real defect. It was diagnosed, corrected
generally, and the correction holds across two repeats — but one weakness
remains and is recorded rather than tuned away.**

## What the first run showed

| targets | words | `setup`+`reveal` | "Misconception N" labels | claims uncovered |
|---|---|---|---|---|
| 1 | 405 | 310 | 0 | 0 |
| 2 | 525 | 387 | **2** | 0 |
| 3 | **611** | 436 | **3** | 0 |

Raw: [`v1-before-fix.json`](v1-before-fix.json).

Every misconception *was* corrected, accurately and with real line references —
so every assertion in `tests/test_gap_remediation.py` passed while the lesson
degraded. That is exactly the failure mode M5 predicted.

**Two defects, both mechanical:**

**1 · Format mirroring.** The target list reaches the model as a numbered list,
and the lesson came back numbered — literal `**Misconception 1:** … 2: … 3:`
headers, in *both* `setup` and `reveal`. The prompt already said "never a
numbered list of unrelated fixes" and was simply overridden by the shape of its
own input.

The 3-gap case made this vivid: it **found the shared root** — "`prepare_auth()`
is the orchestrator, not the handler" — stated it in the opening sentence, and
then abandoned it to enumerate anyway. All three claims share that root, so the
integrated lesson was available and was not written.

**2 · The re-teach path had no length budget at all.** The main teaching prompt
enforces "under 600 words" with `setup`+`reveal` ~250; `_RETEACH_SYSTEM` +
`_LESSON_KEYS` inherit neither. Length therefore grew with gap count —
405 → 525 → 611 — and the 3-gap lesson **breached the system's own 600-word
ceiling**. "Cover them all in the same budget" was unenforceable without a
number.

## The correction

Smallest change addressing both mechanisms, in `_RETEACH_SYSTEM`'s multi-gap
block only — general statements about output shape and budget, not tuned to this
node:

- Forbid the output shape by name: never "Misconception 1 / 2 / 3", no labelled
  section per misconception, and **never follow the listed order** — it is
  detection order, and mirroring it turns a lesson into a checklist.
- Make root-first the primary instruction, and name the observed failure:
  *"Naming the root and then enumerating anyway is the failure this rule exists
  to prevent."*
- State the budget concretely and decouple it from the count: **under 600 words,
  `setup`+`reveal` under 300, whether there is one misconception or four.** More
  to correct means less room for re-explaining what they already had right.

## After the correction — two runs

| targets | run 1 words | run 2 words | `setup`+`reveal` | "Misconception N" | uncovered |
|---|---|---|---|---|---|
| 1 | 313 | 323 | 214 / 208 | 0 / 0 | 0 / 0 |
| 2 | 325 | 359 | 223 / 272 | 0 / 0 | 0 / 0 |
| 3 | 412 | 351 | 302 / 244 | 0 / 0 | 0 / 0 |

Raw: [`v2-run1.json`](v2-run1.json), [`v2-run2.json`](v2-run2.json).

- **Enumeration is gone: 0 labels in all six cases**, against 2 and 3 before.
- **Every case is inside the 600-word ceiling**, and 5 of 6 inside the 300-word
  `setup`+`reveal` target (run 1's 3-gap case is 302 — marginal).
- **The length/count correlation is broken.** In run 2 the 3-gap lesson (351w)
  is *shorter* than the 2-gap one (359w), which is what the instruction asked
  for and what v1 could not do.
- **The 1-gap case was not degraded** by constraints written for the multi-gap
  case — it is ~90 words tighter and reads better for it.

**The 3-gap `setup` now integrates properly.** It states the learner's model as
a whole, then organises by the *code's* timeline — before the call / during /
after — and closes in prose: "The handler never sees the URL, never decides
anything, never touches the connection." That is a pedagogical spine, not the
detection order.

**The 2-gap case is the strongest result:** fully continuous prose, no
segmentation of any kind, both misconceptions corrected inside one argument
about what `prepare_auth()` owns.

## The weakness that remains

**The 3-gap `reveal` still segments into three labelled parts**, in both runs:

> **What the handler owns vs. does not own:** … **What the handler returns:** …
> **Where connection management lives:** …

This is milder than the v1 failure and not the same thing — the headings are
organised by *where responsibility lives*, which is this node's own objective
frame, and the order differs from the input order in both runs. It is a
structured explanation rather than a checklist of the list it was given.

But it is not the single continuous thread the prompt asks for, and it is
**stable across both runs**, so it is a property of the current prompt at three
gaps rather than a bad draw. Recorded rather than corrected: another prompt
revision aimed at it would be tuning against one node's output, and the
remaining cost is a `reveal` that reads as three well-ordered sections instead
of one flowing argument — a real but small loss, on the least-common case.

**Not established:** one node, one answer, one repo, one gap kind
(`wrong_model`), two repeats. This says the mechanism works and the defect is
fixed; it does not put a rate on quality across nodes. Four or more gaps are
untested — `ACTIVE_SET_MAX` collapses above three, so the reachable maximum for
a *targeted* re-teach is 3, but a **collapsed** re-teach targets every blocking
gap and can exceed it. That path is unprobed.

## Cost

9 re-teach calls at ≈$0.007 ≈ **$0.06**.
