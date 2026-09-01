---
name: change-the-tutor
description: Change the Tutor — the conversational assistant beside the lesson. Its context, its prompts, the Socratic ladder, the reveal, what a conversation may propose, the Chat pane, or anything under backend/agents/tutor/, backend/learning/tutor.py or frontend/components/tutor/. Use for "let the tutor see X", "make the hints better", "let it suggest Y", "add a tutor endpoint", or any edit that widens what a conversation can reach or do.
---

# Changing the Tutor

The Tutor is the one part of this system where a model talks to a learner with no
grading in between. Three properties make that safe, and each of them is one
careless widening away from being untrue.

Read first: `docs/planning/phases/tutor.md` §5 (the evidence boundary), §6 (the
ladder and the reveal) and §7 (the leakage architecture), and the module header of
whatever you are editing.

---

## 1. The three properties, and what breaks each

| Property | Held by | Broken by |
|---|---|---|
| **A conversation turn is not evidence** | `agents/tutor/` imports no writer; `/tutor/ask` writes only the transcript and the counters | importing `run_grader`, `mutate_graph`, `adaptation` or `record_attempt`; assigning to `understanding_state`, `gaps`, `attempts`, `visited` or `user_override` |
| **The assessment Tutor does not hold the answer** | `ScaffoldContext` is a TYPE with no `reveal`, `expected_answer` or `rationale` field | adding one of those fields; making `build_scaffold_context` read `cached_lesson["reveal"]`; merging the two builders behind a boolean |
| **Revealing spends the prompt and nothing else** | `tutor_state.revealed` → `retry.prompt_is_unanswered` → `retry.offer` | writing a second assessment path; letting `/respond` grade a revealed prompt |

`tests/test_tutor_boundary.py` and `tests/test_tutor_context.py` assert all three
structurally. **If one of them fails, do not adjust the test** — it is measuring
the thing the feature exists to guarantee.

---

## 2. "Let the Tutor see X"

The commonest request, and the one that needs the most care.

**Ask which mode.** EXPLAIN may see almost anything about this session. SCAFFOLD
may see only what a learner could work out for themselves from the code in front
of them.

For SCAFFOLD, the test is not "is this the answer" but **"could the learner now
answer by rewording it?"** Two things pass that look like they should not:

- **gap claims** — a recorded false belief is the learner's own assertion, and
  scaffolding around a known misconception is why gaps are recorded at all;
- **the objective** — it is the target, not the answer, and a scaffold that did
  not know the target would scaffold toward the wrong thing.

Two things fail that look like they should pass:

- **attempt rationales** — the Grader's account of why an answer fell short is
  the answer wearing a different hat. `_record_block` is deliberately unreachable
  from `build_scaffold_context`, and a test asserts it.
- **the journey outline** — it names later stops, and a hint that gestures at the
  next lesson is teaching ahead of the plan.

**Every cap lives in `context.py` and is a named constant.** Do not add a block
without one. `EXPLAIN_SOURCE_LINES` is the cost lever §10 names; halving it is a
one-constant change, and it is the first thing to reach for if the Tutor gets
expensive.

**Never number the source lines.** A model handed line numbers cites line
numbers, and a line a model chose is exactly the hallucinated range this project's
grounding rule exists to prevent. Citations name a `file` and a `symbol`; our code
resolves the range from `context.citable`.

---

## 3. "Let the Tutor do X"

It may not. It may **propose** X, if X is already an endpoint.

Add to `SUGGESTION_KINDS` in `learning/tutor.py` **only** when the action already
exists as a route the learner can reach another way, then write a validator in
`suggest.py` that refuses anything that route would refuse. The rule is symmetric
and both halves matter:

> Never offer what the endpoint would refuse. Never refuse what it would accept.

`_jump` is the worked example of the second half — `/jump` is unconditional by
design, so the validator checks existence and stops.

`shorter` is absent from the vocabulary on purpose. Demoting a journey on the
strength of a conversation is the system deciding the learner has had enough,
which is what `scope.py`'s "user overrides always win" refuses.

**A scaffold proposes nothing at all.** Offering an exit to somebody mid-thought
is telling them to give up; the reveal control is the one exit, and they reach for
it themselves.

---

## 4. The ladder and the reveal

- Rungs are **different kinds of help**, not the same help louder — orient,
  narrow, guide. Adding a fourth means naming a fourth kind.
- A rung is spent on SUCCESS ONLY. A failed generation leaves the learner with
  nothing new, and charging for it makes their budget pay for our outage. Same
  rule as `remediation_rounds`.
- An **off-ladder question spends no rung**. Asking is never blocked; only being
  written another hint is bounded.
- `can_reveal` is true from rung zero. The ladder bounds hints, not honesty.
- **The reveal's consequence is stated before the control, and in the control's
  own label** (`t.tutor.revealAction`). A consequence disclosed afterwards is not
  a choice, and this is the one place a learner can spend an assessment.
- `new_question()` resets the ladder, and it is called from exactly three places:
  `teaching/respond.reteach`, `teaching/verify.store`, `teaching/reassess.store`.
  A fourth question-issuing path needs a fourth call.

---

## 5. Assistance is metadata, never evidence

`history.ASSISTANCE` records how much help preceded an answer. It follows that
module's absent-means-unknown discipline: `None` means unrecorded, never
"they had none".

It **must not** change a grade, `understanding_state`, `understanding_of`,
readiness, or completion. What it may change is what the system OFFERS —
`retry.ASSISTED` keeps the offer open past `understood`. That asymmetry is
`understanding.py`'s, and `tests/test_progress.py` and
`tests/test_decision_is_not_evidence.py` are the guards.

---

## 6. The Chat pane

It is a **second Source pane**, sharing `components/panel/PaneShell.tsx`. Do not
build a parallel window system, and do not fork the shell.

`lib/panes.ts` owns one rule: **at most one pane may be docked and open**. Both
panes share `--source-width` because only one column ever exists. If you add a
third pane, it goes through the same reducer.

`lib/api.ts` types every server decision — `mode`, `can_hint`, `can_reveal`,
`remaining`, `offers`. **The frontend renders them; it never computes them.** A
client that inferred its own mode could ask for the answer key.

---

## 7. Verify

```bash
uv run python -m pytest tests/test_tutor_context.py tests/test_tutor_boundary.py tests/test_tutor_mode.py tests/test_tutor_suggest.py tests/test_tutor_api.py tests/test_tutor_store.py tests/test_tutor_reset.py tests/test_progress.py tests/test_decision_is_not_evidence.py tests/test_retry_dispatch.py -q
```

Then the full gate via `verify-change`, and the frontend suite plus a build if you
touched `frontend/`.

**If you changed a prompt or what a context contains, the tests are not enough.**
Re-run the leakage measurement and record it:

```bash
uv run python scripts/tutor_eval.py --eval leakage
```

The gate is **0 leaks in 30**, and it gates `CODEONBOARD_TUTOR` defaulting to on —
which it currently does not, on measured evidence
(`docs/planning/phases/evidence/tutor/`). Record any new number there through the
`measure-and-record` skill; do not quietly move the gate, and do not add a prompt
rule aimed at one failing case, which is tuning to the eval set rather than fixing
anything.
