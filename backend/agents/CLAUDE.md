# Working in `backend/agents/`

> Roster and orchestration: [`docs/architecture/agents.md`](../../docs/architecture/agents.md) ·
> Grounding: [`docs/architecture/repository-understanding.md`](../../docs/architecture/repository-understanding.md) ·
> Procedure: the `change-agent-or-prompt` skill · Review: the
> **ai-pipeline-reviewer** agent

CodeOnboard is an AI application, and this directory is where the AI actually
lives. One sentence governs everything here:

> **Code decides policy, the model writes prose.**

Almost every bad change in this directory is a rule quietly migrating into a
prompt, where nothing can test it and nothing can see it drift.

---

## Before adding or enlarging a model call

Ask in order, and stop at the first yes:

1. **Can Layer A compute it?** `repo/skeleton.py` knows every file, symbol, exact
   line range and import. Never ask a model for one of those.
2. **Can a pure function decide it?** Curriculum size, which response a shortfall
   earns, whether a gap blocks, which form a question takes — all were once prompt
   sentences and are now testable code.
3. **Is it already in the Dossier?** There is exactly **one** exploration loop.
   Every other component reads what `goal_investigation` produced. "The Dossier
   does not have enough" is a fix to the investigation's exit criteria, never a
   second loop one layer up.

What is left — judgement and language — is a model's job.

## The four conventions

1. **The client is injected.** Never construct an `anthropic.Anthropic` when a
   caller supplied one; that is what makes every agent testable with a stub.
2. **Never raise at the caller.** Append to `OnboardState.errors`, leave the field
   `None`, and let the pipeline's conditional edges decide whether the run ends.
3. **Never call another agent.** `OnboardState` is the only channel. A value that
   must survive a process restart rides on the persisted graph, because
   interactive requests rebuild the state from the database.
4. **One job, one prompt, one `MODEL` constant.**

## Models

`claude-sonnet-4-6` in four modules only — `mentor/agent.py`, `curriculum.py`,
`dossier.py`, `mutator.py` — all one-shot synthesis over a large body of evidence.
`claude-haiku-4-5` everywhere else, **including every loop**. Never Sonnet in a
loop; never Opus.

A new call needs an answer to *how often, per what, at what cost*. Baseline:
≈$0.405 warm for a 12-unit session
(`docs/planning/phases/cost-optimization.md`). Cost is a metric, not a design
constraint — do not optimise a number nobody has measured.

## Grounding

- A model names a `file` and a `symbol`; **our code** derives the range through
  `anchors.resolve` against the deterministic Skeleton. A hallucinated range is
  structurally impossible, not merely unlikely.
- *Does this exist?* and *was this shown to the agent?* are different questions.
  Never validate a citation against the evidence the model was given.
- **No source, no lesson.** Some anchors unreadable → degrade and teach from the
  rest. **All** unreadable → fail the lesson. A model handed only an objective
  writes something fluent, confident and entirely invented, and nothing about the
  output looks wrong.
- A unit may have several anchors. `lesson_brief["anchors"]` is the truth;
  `nodes.file` / `line_start` / `line_end` are a derived display projection that
  must always equal one member of it.

## Model output is untrusted input

Parse it into a Pydantic model with `Literal` fields wherever the vocabulary is
fixed. Widening a `Literal` means widening it everywhere it is switched on — the
frontend switches on these keys too. Define the truncation and malformed-response
behaviour; `curriculum.py` has a recovery path because a proposal really did
arrive truncated.

Retries are bounded and stated. **Exhaustion is a result, not an exception:**
return a partial with an honest `stop_reason`, let `accepted: false` propagate
into downstream confidence, and record what is still unknown in `open_questions`.
Budgets are safety rails against runaways, not rationing.

## What a green test run does and does not prove

`tests/` stubs every model, so the suite proves the wiring and proves **nothing**
about whether a prompt got better. The instruments that can are in `scripts/`,
they spend real money, and they are run deliberately — see the `measure-and-record`
skill. A prompt change shipped on a green unit suite is shipped unmeasured, and
should be described that way rather than as verified.

If a flag selects between implementations (`CODEONBOARD_CURRICULUM` picks
`curriculum.py` over `dossier.py`), pin it in the test: `tests/conftest.py`
deletes both flags and the developer's `.env` sets both to `1`.

---

## The Tutor is two agents, and the split is the security property

`tutor/mode.py` decides EXPLAIN or SCAFFOLD from the graph — server-side, on every
call, because a client that could name its own mode could ask for the answer key.
The two modes then run **different agents over different types**.

`ScaffoldContext` has no `reveal` field, no `expected_answer` field and no
`rationale` field. That is not an omission to be tidied up later: it is why the
assessment-mode Tutor cannot hand over an answer it does not hold. The obvious
implementation — one builder with `include_reveal=False` — is rejected, because a
boolean is one wrong caller away from a leak and a type with no field for the
answer cannot leak it however it is called.

Three defences, in descending order of strength, and the order matters when you
are deciding what to trust: **the type**, then **the builder never reading the
keys**, then **the prompt**. `tests/test_tutor_context.py` asserts all three, the
last by an AST walk. A failure there is measuring the feature, not obstructing it.

What remains after all three is a model reasoning to the answer from source it
legitimately holds. That is measured, not assumed —
`docs/planning/phases/evidence/tutor/` — and bounded by the product rather than
the prompt: the reveal is one click away and states its own price.
