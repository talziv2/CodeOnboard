# M10 — the Gap Model's acceptance cases, run live

**Date:** 2026-08-18 · **Harness:** `scripts/m10_acceptance.py` ·
**Raw:** [`acceptance.json`](acceptance.json), [`aima-r1/`](aima-r1),
[`aima-r2/`](aima-r2), [`grader-gate/`](grader-gate) ·
`CODEONBOARD_GAPS=1`, real model calls, real repositories.

**Verdict: AC1 and AC2 both observed live on both repositories — but AC1 is
reproducible on `psf/requests` and only intermittently reproducible on
`aimacode/aima-python` (1 of 4 samples).** The distribution is reported below
rather than the passing run, because reporting the pass alone would be choosing
the sample that agrees.

| | `psf/requests` | `aimacode/aima-python` |
|---|---|---|
| AC1 | **PASS** (2/2 samples) | **PASS 1/4 samples** |
| AC2 | **PASS** | **PASS** |

## AC1 — two misconceptions, one resolved, the other survives

Both repositories, all five required steps, one real Grader call → real re-teach
→ real verification question → real verification grading.

The passing shape, on `psf/requests`:

1. **Two distinct gaps** from one answer, both `wrong_model`, distinct ids and
   distinct claims — "a tuple is sent straight through as separate body fields"
   and "the auth handler opens the connection to read the challenge".
2. **Remediation addressed both**, in one re-teach (`collapsed=False`).
3. **A fresh question**, mechanically not the original prompt, aimed at one gap.
4. **One closed, one survived.** The verification answer demonstrated the tuple
   correction and said nothing about connection management; the connection gap
   stayed `open`, `blocking`, and nameable.
5. **The node was not `understood`**, and the reason was available:
   `gaps_blocking: 1`, `gaps_verified: 1`.

`aima-python` produced the same shape on the run recorded in `acceptance.json`.

### Where AIMA is not reproducible, and why

Four samples on the AIMA node, all with the same authored answer:

| sample | gaps detected | second gap's kind | AC1 |
|---|---|---|---|
| neutral prompt, run 1 | 2 | `right_idea_wrong_altitude` (non-blocking) | FAIL |
| neutral prompt, run 2 | 2 | `right_idea_wrong_altitude` (non-blocking) | FAIL |
| neutral prompt, run 3 | 1 | — | FAIL |
| neutral prompt, run 4 | 2 | `wrong_model` (blocking) | **PASS** |

Two independent causes, and neither is a loss of gap data:

- **Detection of the second claim is 3/4.** The `solution()` misconception is
  subtler than the first: the learner describes the parent-chain walk correctly
  and is wrong only about what is *returned*.
- **When detected, it is classified `right_idea_wrong_altitude` in 2 of 3.**
  That kind is **non-blocking**, so the survivor cannot satisfy AC1's
  requirement that it be "open, **blocking**, and visible by name". The claim is
  arguably flatly false rather than mis-pitched — `solution()` does not return
  states at any altitude — but the reading is defensible within the Grader's own
  definitions, and **it was not tuned**: forcing a kind to make an acceptance
  case pass is exactly what the case exists to prevent.

**What held in every single run, including the failures:** no gap ever
disappeared. Whatever was detected was persisted, named, survived the
verification of the other gap, and remained visible afterwards. AC1's
"must not be silently dropped" clause never failed.

### One harness finding, recorded because it nearly produced a false negative

The first AIMA attempt used the node the phase actually came from
(session `9d432157`, node `63644c89`) and detected **one** gap. That is not the
product failing: that node's stored lesson is the **re-teach it later received**,
and its prompt resolves misconception B inside the question — *"how would
`solution()` be able to extract `node.action` for every step?"*. The replacement
node's stored prompt gives B away too (*"how does `solution()` produce the
ordered list of actions"*).

So the question was **neutralised** — the repository, source, objective and
answer are all real and unchanged; only the prompt stops asserting the thing
under test. Two misconceptions cannot be measured through a question that has
already corrected one of them. The substitution is in the harness, commented,
and is the reason AIMA is measurable at all.

## AC2 — verification is a new question

**PASS on both repositories**, both halves:

- **Mechanically** not the original prompt (`identical_to_original: false`).
- **A learner still holding the misconception cannot answer it.** The
  authored `still_holding` answer was graded against the generated question and
  was **not** resolved on either repo. AIMA's rationale names it exactly: *"the
  answer demonstrates the exact false belief being tested — that depth and
  path_cost are set by the search algorithm after node creation"*.

Both `still_holding` answers were authored before any question existed.

## The deferred limitations, validated rather than tuned

### The >3 blocking-gap collapsed re-teach — probed for the first time

Five blocking gaps on one node:

```
plan: action=reteach  collapsed=True  targets=5  active=3  deferred=2
lesson: 471 words (budget 600)   "Misconception N" labels: 0
```

Mechanically correct: it collapses rather than fanning out warm-ups, targets
**all five** (not just the active three, because the lesson is being given
again in full), stays inside the word budget, and does not scale length with
gap count.

**The residual weakness from M5 persists and is more pronounced.** The `reveal`
is four bolded sections — *"What values `solution()` returns:"*, *"When values
are set:"*, *"What `child_node()` does:"*, *"What `expand()` returns:"*.

**Judged, and deliberately not changed.** All five claims are corrected, the
sections are organised by *what the code does* rather than by the input list,
and at five corrections signposting is arguably the right shape — an
unbroken narrative correcting five separate false beliefs would be harder to
read, not easier. The M5 concern was that sectioning replaced teaching; here it
structures it. Changing this would be tuning without evidence of harm, which
M5's own evidence warns against.

## The M2 calibration gate, re-run

Required by §5. [`grader-gate/`](grader-gate):

| | baseline | now |
|---|---|---|
| classification | 48/48 | **46/48** |
| `gap_kind` | 45/48 | **46/48** |
| `missing_prereq` | 4/6 | **6/6** |

46/48 is the **bottom of the measured band**, not a new failure mode: M6
recorded classification as noisy at ±2 across sixteen runs (46–48, mean ≈ 47),
and gap-model.md says later re-runs should read 47/48 as parity. This is one
below parity, and both failures are cases already documented as unstable —
`requests/architecture` × `wrong_altitude` and `requests/risk` × `concise`.
`gap_kind` is *above* baseline and the `missing_prereq` boundary fix holds at
6/6.

## Cost

~26 model calls: 4 AIMA samples × ~4, 2 requests runs × ~5, one collapsed
re-teach, plus the 48-case gate. ≈ **$0.20**.
