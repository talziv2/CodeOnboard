# Candidate A — the goal-directed contrast, measured

Raw output behind the numbers in
[`contribution-journey.md`](../../contribution-journey.md) §B6, §B14, §B19 and
§B21. **Appended, never edited** — a result that changed after the fact is not
evidence.

One JSONL line per run against the pinned `psf/requests` revision `e8d2c015`.

| File | Round |
|---|---|
| `candidate-a-runs-before-fixes.jsonl` | The first measurement, before any repair |
| `candidate-a-runs-fixes123.jsonl` | After the three contract fixes (§B13) |
| `candidate-a-runs-partial-overcorrect.jsonl` | The round where the correction went too far |
| `candidate-a-runs-xmlfix.jsonl` | After the transport repair at the shared tool-call boundary (§B18) |
| `candidate-a-runs.jsonl` | The final three-run pass (§B21) |

## What these settle, and what they do not

**Settled.** The demo's central claim holds on every run that produced a graph:
the same repository with a concrete contribution task plans a *smaller* journey
than an architectural one — core 7–12 against 14, journey 7–14 against 19, areas
4–5 against 8 — and `demoted_by_band` is **0 every time**, so no cap or band
produced the difference. The required set is simply smaller.

**Also settled, and less comfortable.** Generation succeeds roughly **one run in
three**, and four rounds of correct fixes did not move that. The learning path is
the reliable part; the investigation is not. This is why a presentation runs from
pre-generated checkpoints — see [`../../../presentation-runbook.md`](../../../presentation-runbook.md).

**Not settled by anything here.** Nothing in this directory measures the quality
of the implementation stages, the Plan call, or the handoff. Those shipped
unmeasured, and `contribution-handoff.md`'s appendix says so.
