# `backend/agents/` — the model-facing agents

Each directory owns **one job and one prompt**. Two of them call no model at all —
"agent" here names a responsibility in the pipeline, not the presence of an LLM
call.

> Parent: [`backend/`](../README.md) ·
> Architecture: [docs/architecture/agents.md](../../docs/architecture/agents.md)

---

## The roster

| Directory | Entry point | Model | Consumes | Produces |
|---|---|---|---|---|
| `goal/` | `start_session` · `process_answer` · `step_back` | Haiku ×1 (synthesis) | Six static questions and the learner's answers | The goal object — the single source of truth downstream |
| `documentation/` | `run(state)` | **none** | The checkout | `state.doc_context`: README, module and symbol docstrings, `docs/` files |
| `reviewer/` | `run(state, client)` · `should_run(goal)` | Haiku ×1 | `module_map` + the Dossier rendered as chunks | `state.system_review`: strengths, risks, extension points, test gaps, boundaries |
| `mentor/` | `run(state, client)` | Sonnet ×1 | The Dossier (+ the review, when there is one) | `state.graph`, `learning_path`, `confidence`, `plan_report` |
| `briefing/` | `build_briefing(...)` | Haiku ×1 | Survey + README + the learner's profile | The welcome paragraph, cached on the session |
| `teaching/` | `run(state, client)` | Haiku ×1 (+≤1 retry) | The objective, source read **at lesson time**, the Dossier slice, `doc_context` | The lesson, cached on the node |
| `grader/` | `run(state, response, client)` | Haiku ×1 | Objective, question, reference answer, the learner's text | A verdict, a rationale, and the named false claims |

Plus the pieces that respond to a graded answer:

| Module | Job |
|---|---|
| `mentor/mutator.py` | Splices a warm-up into the graph. Sonnet. The **only** response that changes structure |
| `teaching/respond.py` | Writes what a `hint`, `reteach` or `followup` **says** |
| `teaching/verify.py` | A fresh question aimed at **one** gap. Ships no answer |
| `teaching/reassess.py` | A fresh question aimed at the **objective**. Ships no answer |
| `grader/verification.py` | Grades a verification answer. The **only** producer of `verified` |

Inside `mentor/`, `curriculum.py` is the planner — the only one. `dossier.py`
turns an Investigation Dossier into the prompt text it reasons over and computes
the evidence ranges grounding checks against. `agent.py` owns the wire format,
graph construction and the delegation.

`dossier.py` used to hold a second, pre-B3 planner as well, selected by
`CODEONBOARD_CURRICULUM=0`. That flag and that planner were both removed once the
objective-first planner won: a planner nothing could reach was a choice the
package advertised and could not honour.

---

## Model policy

`claude-sonnet-4-6` in exactly two places — the **planner** and the **Mutator** —
because both are one-shot synthesis over a large body of evidence. Everything
else, including every loop, is `claude-haiku-4-5`. Never Sonnet in a loop.

---

## The four conventions

1. **The client is injected.** A caller-supplied client is always used.
2. **Nothing raises at the caller.** Failures append to `OnboardState.errors`.
3. **No agent calls another.** They share `OnboardState`
   ([`pipeline/state.py`](../pipeline/README.md)) and nothing else.
4. **`__init__.py` is the public surface.** Import from the package, not from
   `agent.py`, so internal files can be split without changing every caller.
   `backend/agents/__init__.py` loads each agent lazily (PEP 562), so importing one
   sub-package does not drag in the rest.

---

## The rules that shape what these agents may do

- **Grounding is against the repository.** A model names a `file` and a `symbol`;
  our code derives the range through `repo/anchors.py`. A hallucinated range is
  structurally impossible.
- **No source, no lesson.** If *some* of a unit's anchors fail to load at lesson
  time, Teaching degrades and teaches from the rest. If **all** of them fail, it
  **fails the lesson** — a model given only an objective writes a confident,
  fluent, entirely invented explanation, and nothing about the output looks wrong.
- **Only `goal_investigation` explores.** Teaching, the Mentor, the Reviewer and
  the Mutator read what it produced. The fallback order everywhere is **Dossier
  first, Skeleton second**.
- **The objective is the contract.** The planner writes it, Teaching builds exactly
  it, the Grader marks against it — not against the `expected_answer` Teaching
  invented. Read it through `LearningNode.objective()`, never straight off
  `lesson_brief`.
- **The question's *form* is chosen by code** from the unit's `kind`
  (`teaching.lesson_form`), and the model is shown only the chosen form's brief. A
  menu invites blending.
- **A retry question never ships its own answer.** `verify` and `reassess` both
  carry a question and nothing else.

---

## Tests

`tests/test_goal_agent.py`, `test_goal_api.py`, `test_documentation_agent.py`,
`test_reviewer_agent.py`, `test_mentor_dossier.py`, `test_curriculum_planner.py`,
`test_curriculum.py`, `test_briefing.py`, `test_teaching_agent.py`,
`test_teaching_forms.py`, `test_grader_agent.py`, `test_grader_gaps.py`,
`test_mutator.py`, `test_prerequisite_diagnosis.py`.

Live behaviour is measured by the harnesses in [`scripts/`](../../scripts/README.md);
their committed output is in `docs/planning/phases/evidence/`.
