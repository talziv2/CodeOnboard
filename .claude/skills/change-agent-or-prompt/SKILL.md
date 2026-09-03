---
name: change-agent-or-prompt
description: Change an agent, a prompt, a model call, or the LangGraph pipeline — Goal, Documentation, Reviewer, Mentor/planner, Briefing, Teaching, Grader, Mutator, or the exploration loop. Use when editing anything under backend/agents/, backend/pipeline/, or backend/repo/explore.py, investigation.py and survey.py, including prompt text alone.
---

# Changing an agent, a prompt, or the pipeline

The rule that governs this whole area: **code decides policy, the model writes
prose.** Almost every bad change here is a rule quietly migrating into a prompt,
where nothing can test it.

Read first: `docs/architecture/agents.md` (the roster, the four conventions, §5
"where each decision is made") and, for anything in `repo/`,
`docs/architecture/repository-understanding.md` §3–§7.

---

## 1. Before editing: is a model call the right answer at all?

Ask in this order, and stop at the first yes:

1. **Can Layer A compute it?** `repo/skeleton.py` knows every file, symbol, exact
   line range and import. Never ask a model for any of those.
2. **Can a pure function decide it?** Curriculum size, which response a shortfall
   earns, whether a gap blocks, which form a question takes — all of these were
   once prompt sentences and are now testable code (D5).
3. **Does the Dossier already contain it?** There is exactly one exploration loop
   (D1). Teaching, the Mentor, the Reviewer and the Mutator *read* what
   `goal_investigation` produced. If the answer is "the Dossier does not have
   enough", the fix belongs in the investigation's exit criteria — **not** in a
   second loop one layer up.

Only what is left — judgement and language — is a model's job.

## 2. Model selection

`claude-sonnet-4-6` in two modules only: `mentor/curriculum.py` and
`mentor/mutator.py` — both one-shot synthesis over a large body of evidence.
`claude-haiku-4-5` everywhere else, **including every loop** (`repo/explore.py`
says so in its header). Never Sonnet in a loop. Never Opus.

A new model call needs an answer to: how often does it run, per what, and what
does it add to a session's cost? `explore.PRICING` and `repo/metrics.py` compute
it; `docs/planning/phases/cost-optimization.md` holds the baseline (~$0.405 warm
for a 12-unit session). Do not justify a change with an unmeasured cost claim in
either direction (D26).

## 3. Keep the agent contract

1. **Client injected** — never construct one when a caller supplied it; that is
   what makes every agent testable with a stub.
2. **Never raise at the caller** — append to `OnboardState.errors`, leave the
   field `None`. The pipeline's conditional edges decide whether the run ends.
3. **Never call another agent** — `OnboardState` is the only channel. If a new
   value must reach a later node, add a field to `backend/pipeline/state.py`; if
   it must survive a process restart, note that interactive requests rebuild
   `OnboardState` from the database, which is why `doc_context` rides on the
   persisted graph.
4. **One job, one prompt, one `MODEL` constant.**

## 4. Grounding, if the change touches what is taught

- A model names a `file` and a `symbol`; **our code** derives the range through
  `anchors.resolve` (D2). Never accept a range from a model, and never validate a
  citation against the evidence the model was shown — *does this exist* and *was
  this shown* are different questions.
- **No source, no lesson** (D3). Some anchors unreadable → degrade and teach from
  the rest. **All** unreadable → fail the lesson. Never add a fallback that
  teaches from the objective alone: the output will be fluent, confident and
  entirely invented, and nothing about it will look wrong.
- A unit may have **several** anchors. `nodes.file` / `line_start` / `line_end`
  are a derived display projection; `lesson_brief["anchors"]` is the truth, and
  the display columns must equal one member of it.

## 5. Structured output

Model output crosses a trust boundary, so parse it into a Pydantic model with
`Literal` fields wherever the vocabulary is fixed (`docs/reference/patterns.md`).
Then:

- Widening a `Literal` means widening it everywhere it is switched on, in both
  languages — the frontend switches on these keys too (D24).
- Define the truncation and malformed-response behaviour. `curriculum.py` has a
  recovery path for a truncated proposal because that happened; a new call needs
  its own answer.
- Retries are bounded and stated (Teaching allows ≤1). Exhaustion is a **result**,
  not an exception (D25): return a partial with an honest `stop_reason`, let
  `accepted: false` propagate into confidence, and record what is still unknown in
  `open_questions`.

## 6. Verify — and be honest about what verification proves

```bash
uv run pytest tests/test_teaching_agent.py tests/test_grader_agent.py tests/test_dossier_rendering.py tests/test_curriculum_planner.py tests/test_explorer_pipeline.py tests/test_anchors.py -q
```

Then the full gate via `verify-change`.

**The suite stubs every model, so a green run says nothing about whether a prompt
got better.** If the change alters prompt text or a model's task, name the harness
that would show it, say what it costs, and **ask before running it** — see the
`measure-and-record` skill. A prompt change shipped on a green unit suite is
shipped unmeasured, and should be described that way.

If a flag selects between implementations, pin it explicitly in the test —
`tests/conftest.py` deletes every flag it knows about, so an unpinned test runs
the shipped default. `CODEONBOARD_TUTOR` is the only such flag now.
`CODEONBOARD_CURRICULUM`, which picked `curriculum.py` over a second planner in
`dossier.py`, was removed along with that planner; `curriculum.py` is the only
planner and `dossier.py` holds the rendering it reasons over.

For a substantial change, ask the **ai-pipeline-reviewer** agent to review the
diff.

## Completion criteria

- Nothing testable moved into a prompt.
- Grounding still derives ranges from the Skeleton, and the all-anchors-fail path
  still refuses.
- The four agent conventions hold; `OnboardState` is still the only channel.
- Model choice matches the policy, and a new call has a stated cost.
- If a prompt changed, the report says which harness would demonstrate it and
  whether it was run.

## Common failure modes

- "Just tell the model to keep it to eight units" — sizing is `curriculum.select()`.
- Adding a small retrieval helper inside Teaching.
- Letting a lesson render from an objective when the source could not be read.
- Widening a `Literal` in Python only.
- Treating a passing test suite as evidence about model behaviour.
