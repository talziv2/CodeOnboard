# Learning Engine — cost record

> **Append-only.** Each measurement is added as a new baseline or run; existing entries are
> never edited or replaced. The point of this file is the *history* — being able to compare
> the system before optimisation, each optimisation attempt, and the final result, and to
> judge not merely whether cost fell but whether the Learning Engine's behaviour and quality
> survived the fall.
>
> Corrections to a past entry go in a **Corrections** subsection under that entry, stating
> what was wrong and why, rather than rewriting the numbers.
>
> Related: [`../learning-engine.md`](../learning-engine.md) §14 item 16 (the acceptance
> criterion) and its decision log. Raw data lives beside this file as JSON.

## Index

| # | Entry | Date | Session cost (warm, 12 units) | vs $0.10 target |
|---|---|---|---|---|
| 1 | [Baseline 1 — pre-cost-optimization](#baseline-1--pre-cost-optimization) | 2026-08-15 | **$0.4053** | **4.1× over — not met** |

---

## Baseline 1 — pre-cost-optimization

**The system as it stood when the planned Learning Engine functionality was still
incomplete.** Recorded deliberately *before* any cost work, so that later optimisation has
something honest to be measured against. No prompt, model, pipeline or curriculum change
was made to chase the target — a measurement taken while tuning the thing measured is
worth nothing.

### Provenance

| | |
|---|---|
| **Date** | 2026-08-15 |
| **Commit** | `7c599d6` (`test: record the per-path cost measurement`) |
| **Harness** | [`scripts/measure_cost.py`](../../../../scripts/measure_cost.py) |
| **Raw data** | [`cost-measurement.json`](cost-measurement.json) |
| **Repository** | `psf/requests` |
| **Goal** | `understand_architecture`, focus "the request lifecycle", `code_depth: working`, familiarity "Skimmed the README or docs", background "5 years of Python, some Django" |
| **Units planned** | 16 |
| **Projection journey** | 12 units |

### Configuration and flags

| flag / setting | value at measurement | note |
|---|---|---|
| `CODEONBOARD_CURRICULUM` | **`0` is the shipped default**; scenarios ran against a flag-`1` graph | Both planners were measured; session-time scenarios used the B3 graph because multi-anchor units change lesson input size |
| Guard bands | `map` 5–18 (calibrated), `working` 8–22, `implementation` 10–28 | `map` ceiling had just been calibrated from 14 → 18 |
| Teaching model | `claude-haiku-4-5` | |
| Grader model | `claude-haiku-4-5` | |
| Planner model | `claude-sonnet-4-6` | both planners |
| Investigation model | `claude-haiku-4-5` | |
| Mutator model | `claude-sonnet-4-6` | |

### Repository state — **WARM**

This is the single most important caveat on the headline number.

| stage | state | consequence |
|---|---|---|
| `repo_survey` | **cache hit** (survey store, keyed repo + commit) | cost **$0.0000** in this run |
| `goal_investigation` | cold — investigates per session by construction | paid in full |
| repo clone | already on disk | no measurable cost either way |

The survey store's own record for `psf/requests` at this commit is **$0.130936**. A
first-ever session on a repository pays that, so the **cold-start estimate is ≈ $0.53**.

### Pricing used

From `backend/repo/explore.py::PRICING` — the repo's single source of truth, so this record
and the runtime agree by construction.

| model | input $/Mtok | output $/Mtok |
|---|---|---|
| `claude-haiku-4-5` | 1.00 | 5.00 |
| `claude-sonnet-4-6` | 3.00 | 15.00 |

Cache multipliers: **write ×1.25** (5-minute TTL), **read ×0.10**. Billed input =
`input + cache_write×1.25 + cache_read×0.10`.

### Planning-time cost — paid once per session

| stage | calls | model | uncached in | cache read | out | cost |
|---|---|---|---|---|---|---|
| `repo_survey` | 0 | — | 0 | 0 | 0 | **$0.0000** (cache hit) |
| `documentation` | 0 | — | 0 | 0 | 0 | $0.0000 (no LLM, by design) |
| `goal_investigation` | 20 | Haiku | 509 | 352,686 | 21,614 | **$0.1832** |
| `mentor` — legacy (flag=0) | 1 | Sonnet | 15,976 | 0 | 2,251 | **$0.0817** |
| `mentor` — B3 (flag=1) | 1 | Sonnet | 16,635 | 0 | 4,579 | **$0.1186** |

**Planning total with B3 planner: $0.3018.** With the legacy planner it would be **$0.2649**.

Wall time: investigation 154.2s, legacy planner 39.9s, B3 planner 75.0s.

### Planner comparison — preserved explicitly

Both planners ran against **the same dossier**, so this is a like-for-like comparison.

| planner | cost | input | output |
|---|---|---|---|
| legacy (pre-B3) | **$0.0817** | 15,976 | 2,251 |
| B3 objective-first | **$0.1186** | 16,635 | 4,579 |
| **difference** | **+$0.0369 (+45%)** | +659 | **+2,328** |

The increase is almost entirely **output tokens** — the price of over-generating objectives
carrying anchors, areas, priorities and dependencies. **This is what flipping
`CODEONBOARD_CURRICULUM` to `1` costs per session: about four cents.** Whether the
curriculum is worth that is a product judgement, not a measurement.

### Session-time cost — per unit / per answer

| scenario | gap_kind | calls | in | out | cost | vs happy path |
|---|---|---|---|---|---|---|
| happy path | — | 2 | 4,659 | 792 | **$0.008619** | baseline |
| hint | `no_attempt` | 3 | 5,180 | 797 | $0.009165 | **+$0.000546** |
| follow-up | `right_idea_wrong_altitude` | 3 | 5,163 | 851 | $0.009418 | **+$0.000799** |
| re-teach | `wrong_model` | 4 | 8,212 | 2,032 | $0.018372 | **+$0.009753** |
| prerequisite | `missing_prerequisite` | 3 | 10,073 | 965 | $0.027076 | **+$0.018457** |

Per-call detail:

| scenario | lesson (Haiku) | grade (Haiku) | adaptation |
|---|---|---|---|
| happy path | 1 call, $0.006882 | 1 call, $0.001737 | — |
| hint | 1 call, $0.006547 | 1 call, $0.001695 | 1 Haiku, $0.000923 |
| follow-up | 1 call, $0.006887 | 1 call, $0.001735 | 1 Haiku, $0.000796 |
| re-teach | 1 call, $0.007062 | 1 call, $0.001729 | **2** Haiku, $0.009581 |
| prerequisite | 1 call, $0.007032 | 1 call, $0.001777 | 1 **Sonnet**, $0.018267 |

**Component costs** (isolated): teaching ≈ **$0.0069/unit**, grading ≈ **$0.0017/answer**,
hint ≈ $0.0009, follow-up ≈ $0.0008, re-teach ≈ $0.0096 (as observed — see caveat 3),
prerequisite ≈ $0.0183.

### Planning time vs session time

| | cost | share of 12-unit session |
|---|---|---|
| **planning (once)** | $0.3018 | **74%** |
| **session (12 × happy path)** | $0.1034 | **26%** |
| adaptation (one of each, on top) | $0.0296 | ~7% |

`goal_investigation` alone is **45%** of the whole session.

### Projected session cost

| scenario | 12 units |
|---|---|
| every unit answered well | **$0.4053** |
| + one hint | $0.4058 |
| + one follow-up | $0.4061 |
| + one re-teach | $0.4150 |
| + one prerequisite | $0.4237 |
| one of **every** adaptation | $0.4348 |
| **cold start** (add ~$0.131 survey) | **≈ $0.53** |

At the measured planning size of 16 units: $0.3018 + 16 × $0.008619 = **$0.4397**.

### Baseline observations — not yet optimisation decisions

Recorded as findings. **No action was taken on any of them**, and none should be treated as
a decision until the planned functionality is complete and the system has stopped moving.

1. **The budget is a planning-time problem.** 74% planning vs 26% session. Optimisation
   aimed at lessons or adaptation targets the quarter of the bill that is already cheap.
2. **The investigation's cost is OUTPUT, not input.** Prompt caching there is already
   near-perfect — 352,686 cache reads against 509 uncached input tokens — while it writes
   **21,614 output tokens across 20 turns** (~59% of that stage's bill). The instinctive
   fix, "add caching", targets a problem that does not exist here.
3. **The planner call is the mirror image**: 16,635 input tokens with **zero** cache reads.
4. **Adaptation is economically irrelevant** at the cheap end — a hint costs half a tenth of
   a cent. Only the prerequisite path (Sonnet) is material, at ~2.1× a happy-path unit.

### Assumptions and limitations

1. **Warm survey.** The headline $0.4053 excludes the survey; cold start is ≈$0.53.
2. **One answer per unit.** The projection assumes every unit is answered once. A hint or
   re-teach invites another answer, and each re-answer is another grade *plus* another
   adaptation — so these are a **floor for a journey with any friction**, not an average.
3. **The measured re-teach included a parse-failure retry.** Its adaptation shows **2**
   Haiku calls, because `_generate_lesson` retries once on a bad parse. A clean re-teach
   should be ~1 call (≈$0.005), so $0.0096 is an observed instance, not the typical cost.
4. **One repository, one goal, one `code_depth`, single run.** No variance was measured;
   the calibration matrix showed planner output varying run to run, so planner cost varies
   too. This is a point estimate.
5. **List pricing**, no discounts, no batch API.
6. **Grader calls were real; only their verdicts were overridden** to force each scenario,
   so grading cost is measured rather than assumed.
7. **Investigation cost is inherently variable** — it is a budgeted agentic loop, and this
   run used 20 turns.

### Status against the target

| | |
|---|---|
| Target | **$0.10 / session** (`learning-engine.md` §14 item 16) |
| Measured (warm, 12 units) | **$0.4053** |
| Measured (cold start estimate) | **≈$0.53** |
| **Verdict** | **NOT MET — approximately 4.1× over (warm), 5.3× (cold)** |

`learning-engine.md` §14 item 16 is marked **explicitly open**. Cost optimisation is
**deferred to a dedicated phase** after the planned Learning Engine functionality is
complete, so that optimisation does not target prompts, outputs, model usage or pipeline
stages that are still changing.

---

<!-- Append the next entry below this line. Do not edit entries above it. -->

## Baseline 2 — after the gap model (M1–M6)

**Date:** 2026-08-18 · **Harness:** `scripts/measure_cost.py` ·
`CODEONBOARD_CURRICULUM=1`, **`CODEONBOARD_GAPS=1`** · `psf/requests`,
`understand_architecture`, `code_depth: working`, 12-unit projection.
Raw: [`m6-verification/cost-measurement.json`](m6-verification/cost-measurement.json)
and [`m6-verification/cost-verification.json`](m6-verification/cost-verification.json).

Required by [`gap-model.md` §7](../gap-model.md#7-cost--this-phase-increases-it):
verification adds calls per gap, so Baseline 1 could not survive M6 unchanged.

| | Baseline 1 | Baseline 2 | Δ |
|---|---|---|---|
| planning (B3) | $0.3018 | **$0.3170** | +5.0% |
| happy-path unit | $0.008619 | **$0.011942** | **+38.6%** |
| 12-unit warm session | $0.4053 | **$0.4603** | **+13.6%** |
| verification, per gap closed | — | **$0.0042** | new |

**Per stage:**

| stage | in | out | cache write | cache read | cost |
|---|---|---|---|---|---|
| `goal_investigation` | 595 | 15,136 | **60,054** | 336,396 | $0.1850 |
| `mentor` (B3) | 22,173 | 4,368 | 0 | 0 | $0.1320 |
| lesson (per unit) | 4,752 | 718 | 0 | 0 | $0.008342 |
| grade (per answer) | 2,770 | 166 | 0 | 0 | $0.003600 |
| verification question | 2,226 | 67 | 0 | 0 | $0.002561 |
| verification grading (1 gap open) | 858 | 151 | 0 | 0 | $0.001613 |
| verification grading (3 gaps open) | 957 | 289 | 0 | 0 | $0.002402 |

### What the gap model is actually responsible for

**Grading, and only grading: +$0.00186 per answer (+107%).** Input went
1,367 → 2,770 tokens. That +1,403 is `_GAPS_ADDENDUM` plus M3's open-gap
section, measured rather than estimated; output rose 74 → 166 because the call
now emits a `gaps` array. Over 12 units that is **+$0.022**, and it is the
honest price of detecting several misconceptions instead of one.

**Verification: $0.0042 per gap closed** — and the shape matters more than the
number. A cycle is one question ($0.00256) plus one grading ($0.00161), aimed at
**one** gap (§18.7), so a node with k open gaps costs k cycles. **Verification
scales with gaps detected, not with units taught.** Grading grows with how many
gaps are *open* (+49% from 1 to 3, because all of them are listed so silence
about any is visible); the question is flat.

Realistic additions to a 12-unit journey: 1 gap **+$0.004**, 3 gaps
**+$0.013**, 6 gaps **+$0.025**.

### What it is NOT responsible for — stated so it is not blamed later

**The lesson grew +1,460 input tokens (+21% cost) and no gap-model change
touches it.** Teaching's main prompt is untouched by M2–M6; output was 718 both
runs. Unattributed, and it is the larger of the two per-unit rises. Candidates:
the concurrent two-measure progress work, a different `render`/source slice, or
run variance. **This needs attributing before any per-unit optimisation, because
it is currently being carried in a total that looks like the gap model's.**

**Planning rose +5%** on a +33% planner input (16,635 → 22,173) against a
*smaller* output. Different dossier, not a gap-model change.

### One measurement defect fixed, with a consequence

`summarise()` now records `cache_write`, which `cost_of()` always billed. Baseline
1's figure had to be **reconstructed by arithmetic** as ~31,512; measured
directly here it is **60,054** — nearly double. Both baselines still reconcile to
their recorded totals, so neither number is wrong, but the reconstruction was a
coincidence of one run and must not be used as a comparison point. Cache write is
the **largest input line in the investigation**, so this mattered.

### Verdict against the target

$0.46 warm against a $0.10 target — **4.6× over**, up from 4.1×. The gap model
made the system more expensive on purpose: it detects several misconceptions,
remediates each, and verifies closure, and none of that was in Baseline 1.
[`cost-optimization.md`](../cost-optimization.md) §1.4's arithmetic is unchanged
by this and its conclusion is reinforced: ≤$0.10 is unreachable without at least
one Tier C decision.

**Not established:** one run, one goal, one repository, no repeats — the same
limitation Baseline 1 records. The Reviewer is still unmeasured, and it runs for
this goal type.
