# CodeOnboard

An adaptive, repository-aware learning system for unfamiliar codebases. A learner
gives a public GitHub repository and says what they want to be able to do; the
system reads the repository, plans a personalised route through it, and teaches
that route one stop at a time — asking a question at each stop, marking the
answer, naming what was wrong, and reshaping the route around it.

Final-year CS project, close to submission. Prefer working code over perfect
architecture, and flag scope creep into later phases rather than absorbing it.

**The documentation is authoritative and current.** [`docs/README.md`](docs/README.md)
is the index; [`README.md`](README.md) covers setup, running and troubleshooting;
every package has its own README beside the code. This file does not restate them
— it routes to them. Where a document and the code disagree, **the code is right**;
say so rather than leaving the disagreement standing.

---

## Start here: what kind of work is this?

Almost nothing in this repository is a local change. Find the row before you
start.

**Design before implementation.** This project designs a change, argues the
alternatives, and only then builds — that is what `docs/planning/phases/` is. When
the request is about *what the behaviour should be* rather than how to write it —
"design it first", "should this live in the graph", "derived or persisted",
"should the Orchestrator decide this", "would another agent help" — use the skill
**design-a-change**, which routes to the two designers. Their shared references
are in [`.claude/reference/`](.claude/reference/):
[`design-principles.md`](.claude/reference/design-principles.md) (DI-1…DI-12,
**each classified** ① fundamental / ② current decision / ③ implementation
property, plus the claims that were retracted),
[`state-ownership.md`](.claude/reference/state-ownership.md),
[`orchestration-model.md`](.claude/reference/orchestration-model.md) and
[`design-history.md`](.claude/reference/design-history.md).

**Today's implementation is not automatically a rule.** A ③ property is never a
reason to refuse a design, and "that is not how it works today" is not an
argument. Say which class you are appealing to.

| The request | Load | Then review with |
|---|---|---|
| "Design it first" · should this be a new node · derived or persisted · does this belong in the Learning Graph | skill **design-a-change** → agent **learning-system-designer** | — |
| Who should own this · agent vs node vs function · does this need an LLM · are two things authoritative now | skill **design-a-change** → agent **orchestration-designer** | — |
| "Change how retry works" · "add another learning state" · anything about readiness, gaps, understanding, adaptation, scope | skill **change-learning-policy** | **learning-engine-reviewer** |
| "Change how lessons are generated" · edit a prompt · add or move a model call · touch the pipeline or the exploration loop | skill **change-agent-or-prompt** | **ai-pipeline-reviewer** |
| "Change the map behaviour" · surfaces, rail, feedback states, copy | `frontend/CLAUDE.md` (auto-loads) | **frontend-flow-reviewer** + skill **verify-in-browser** |
| "Add a field to a session" · schema, migration, `Start over`, resume | skill **persistence-change** | **session-data-reviewer** |
| "Add / change an endpoint" | skill **api-endpoint** | **session-data-reviewer** |
| "Why is readiness wrong?" · a bug whose layer is unknown · a failing test with an unclear cause | skill **investigate-behaviour** | — |
| "Why was it built this way?" · is this objection right? · is this simplification safe? · defense prep | agent **architecture-historian** | — |
| "Review this PR" | command **/review-changes** | — |
| Prove something about model behaviour, curriculum shape or cost | skill **measure-and-record** | — |
| Update docs after a change; close a milestone | skill **sync-documentation** | — |
| "Prepare the project for submission" | command **/submission-check** | — |
| Anything, before saying it is done | skill **verify-change** | — |

---

## Read before you edit

[`docs/architecture/decisions.md`](docs/architecture/decisions.md) holds 26
invariants, each stated with the failure it prevents. They are the rules where the
wrong change **compiles, passes an eyeball review, and quietly makes the product
lie** — so they are not discoverable from the code you are editing.

That document is organised by decision. This table is the same set organised by
the file you are about to open.

| Editing | Read first |
|---|---|
| `backend/repo/anchors.py` · `explore.py` · `investigation.py` | D1 one exploration loop · D2 grounding is against the repository, not the evidence shown · D25 exhaustion is a result, not an exception |
| `backend/agents/teaching/` | D3 no source, no lesson · D4 the objective contract · D10 a retry question never ships its own answer |
| `backend/agents/grader/` | D4 mark against the objective, not `expected_answer` · D11 silence never closes a gap · D14 grading and policy are separate |
| `backend/agents/mentor/curriculum.py` · `dossier.py` | D5 the planner over-generates and code cuts · D6 `optional` |
| `backend/agents/mentor/mutator.py` | D15 one structural mutation per graded answer |
| `backend/learning/progress.py` | **D7** readiness may fall only when evidence changes — never because the plan changed |
| `backend/learning/understanding.py` | D8 a learner decision is never evidence of understanding |
| `backend/learning/graph.py` | D6 `optional` is off the walk, not out of the graph · D9 `understanding_of()` is the single owner |
| `backend/learning/gaps.py` | D12 caps bound the system, not the learner · D13 gap identity is ours |
| `backend/learning/adaptation.py` · `retry.py` | D10 · D14 a named `gap_kind` outranks the coarse classification |
| `backend/learning/store.py` | **D16** `save_graph` never writes a plan table · D18 the two schema-version questions · D19 the flag gates behaviour, never storage · D20 ownership |
| `backend/learning/reset.py` | D17 nothing is ever synthesised for a session that has no plan |
| `backend/api.py` · `backend/auth/` | D20 ownership at the persistence boundary, **404 never 403** · D21 nothing about a learner is inferred from an email |
| `backend/agents/tutor/` · `backend/learning/tutor.py` | skill `change-the-tutor` — a turn is not evidence · `ScaffoldContext` is a type with no field for the answer · revealing spends the prompt through `retry.py` |
| `frontend/lib/` · `frontend/components/` | D22 the frontend renders learning decisions; it does not compute them |
| `frontend/lib/markdown.ts` · `strings.ts` | D23 learner-written text is never markdown · D24 fixed keys are parsed; only labels are chosen |

Each entry carries a *prevents* clause naming a defect that actually happened. If
a change looks like it contradicts one, read that clause before concluding it does
not apply.

---

## Boundaries

- **The learning engine knows nothing about users.** `learning/`, `agents/` and
  `repo/` contain no reference to one. `learning/store.py` is the single
  exception, because it *is* the ownership boundary.
- **Agents share `OnboardState` and nothing else.** No agent calls another; none
  raises at its caller; the Anthropic client is always injected.
- **Code decides policy, the model writes prose.** A rule that can be stated and
  tested is a pure function in Python, never a sentence in a prompt.
- **Layer A is deterministic and model-free.** Never ask a model for something
  `repo/skeleton.py` can compute, and never ask one for a line number.
- **One exploration loop.** `goal_investigation` is the only place the system
  explores; everything else reads what it produced.
- **A conversation is never evidence.** The Tutor may describe learner state
  and may offer an action the system already supports; it may never be the
  reason one changed. Structural: nothing under `backend/agents/tutor/`
  imports `run_grader`, `mutate_graph`, `adaptation` or `record_attempt`.
- **The frontend renders learning decisions; it does not compute them.**
- **Python only, structurally.** Another language is a sibling adapter, not a
  rewrite — designed in `docs/planning/phases/multi-language.md`, **not built**.

---

## Commands

```bash
uv run pytest tests/                      # backend — ~70s, 1801 pass
cd frontend && npm test                   # frontend — ~15s, 50 files
cd frontend && npm run build              # frontend — this IS the type check
```

That is the whole gate. There is no CI, no linter, and no separate typecheck
script — so nothing runs unless you run it. Use the **verify-change** skill rather
than guessing which of the three a change needs, and **verify-in-browser** for
anything visual: more than a third of this project's recorded defects were only
findable on a rendered page.

**One backend test fails by design on a used database** —
`test_gap_understanding.py::test_every_stored_gap_free_node_derives_its_stored_state`
(`AssertionError: no gap-free nodes to check`), a development gate that predates
accounts (`docs/testing.md` §5). Do not "fix" it as part of unrelated work:

```bash
uv run pytest tests/ --deselect "tests/test_gap_understanding.py::test_every_stored_gap_free_node_derives_its_stored_state"
```

**Running the app** — `run-dev.bat` on Windows (it verifies both services over
HTTP and exits non-zero unless both answer), or two terminals:
`uv run uvicorn backend.api:app --reload` and `cd frontend && npm run dev`.
Open `http://localhost:3000` only; the browser never calls port 8000.

**The flags trap.** `CODEONBOARD_CURRICULUM` and `CODEONBOARD_GAPS` both default
to `0`, `tests/conftest.py` deletes both for every test — and the developer's local
`.env` sets **both to `1`**. So the app as it is actually run uses the
objective-first planner and the gap model, while the suite tests neither unless a
test says so. "Works in tests, wrong in the app" is a flag difference until proven
otherwise. When behaviour depends on a flag, pin it in the test and say which.

`CODEONBOARD_TUTOR` is the third, and it is default `0` **on evidence rather
than caution**: `docs/planning/phases/evidence/tutor/` measures 1 leak in 30
adversarial prompts against a stated gate of 0. It has a build-time twin,
`NEXT_PUBLIC_CODEONBOARD_TUTOR`, because Next inlines `NEXT_PUBLIC_*` — the
backend gates the routes at request time, the bundle gates the control at build
time. Neither gates storage: a conversation survives both being turned off.

---

## Model policy

`claude-sonnet-4-6` in four modules only — `agents/mentor/agent.py`,
`curriculum.py`, `dossier.py`, `mutator.py` — all one-shot synthesis.
`claude-haiku-4-5` everywhere else, **including every loop**. Never Sonnet in a
loop. Never Opus. Details and the reasoning live in
[`backend/agents/CLAUDE.md`](backend/agents/CLAUDE.md), which loads when you work
there.

**Cost is a metric, not a design constraint** (D26). Every run reports its own; a
real session currently costs materially more than the $0.10 once targeted, and
that gap is tracked in `docs/planning/phases/cost-optimization.md` rather than
restated as a rule.

---

## Money, data, and things that cannot be undone

- **`scripts/` spends real money** on the user's own API key. Never run a harness
  unless asked. Most accept `--dry-run`, which makes no API calls — offer that
  first, with a rough cost. See the **measure-and-record** skill.
- **`data/sessions.db` is irreplaceable.** Every account and every session,
  gitignored, no backup, and the corpus behind
  `docs/planning/phases/evidence/`. Never delete it, never migrate it in place,
  never point a script or a test at it. Tests use `tmp_path`; UI work uses
  `scripts/seed_ux_fixture.py` and `data/ux-fixture.db`.
- **Never commit or push** unless explicitly asked.

---

## Conventions

- **Commits.** `type: a lowercase sentence in the product's voice` — what the
  change means for a learner, not which files moved ("a way out of a session, back
  to the learner's own list", not "add DashboardLink component"). The body opens
  with the failure it fixes and how it reached the user. `git log` is the
  reference. Types: `feat` `fix` `docs` `refactor` `test` `chore` `perf` `ci`.
- **Comments explain why.** Every substantial module opens with a header — a `#`
  block or a docstring — naming the decision it holds and the defect that decision
  prevents. Match that; a comment restating the code is noise here.
- **Pure means pure.** `progress.py`, `understanding.py`, `adaptation.py`,
  `retry.py`, `scope.py`, `gaps.py` and `curriculum.select()` do no IO and make no
  model calls. That is what makes the learning policy testable without an API key.
- **State a rule with the failure it prevents.** That is the house style in
  `decisions.md`, in module headers and in commit bodies, and it is what makes a
  rule checkable rather than decorative.
- **Docs are updated with the change**, in the document that owns the explanation
  — see the **sync-documentation** skill. Verify commands, paths, ports and
  symbols before writing them down.

---

## Where to look

| Question | Document |
|---|---|
| What is this, how do I run it, what broke | [`README.md`](README.md) |
| Everything else | [`docs/README.md`](docs/README.md) — the index |
| The invariants a change could break quietly | [`docs/architecture/decisions.md`](docs/architecture/decisions.md) |
| What each agent receives, returns and costs | [`docs/architecture/agents.md`](docs/architecture/agents.md) |
| The learning model, gaps, progress | [`docs/architecture/learning-engine.md`](docs/architecture/learning-engine.md) |
| Endpoints, the four-layer auth boundary, error conventions | [`docs/architecture/backend-api.md`](docs/architecture/backend-api.md) |
| Tables, plan vs state, schema versions, migrations | [`docs/architecture/persistence.md`](docs/architecture/persistence.md) |
| Creation, resume, `Start over` vs `Rebuild`, completion | [`docs/architecture/session-lifecycle.md`](docs/architecture/session-lifecycle.md) |
| What to run, and the two results that look like failures | [`docs/testing.md`](docs/testing.md) |
| Every environment variable and what happens when it is wrong | [`docs/configuration.md`](docs/configuration.md) |
| Recurring Python idioms and when to reach for each | [`docs/reference/patterns.md`](docs/reference/patterns.md) |
| Who is authoritative for which fact | [`.claude/reference/state-ownership.md`](.claude/reference/state-ownership.md) |
| The design principles, and how much weight each carries | [`.claude/reference/design-principles.md`](.claude/reference/design-principles.md) |

Planning documents under `docs/planning/` are **design records**, not descriptions
of current behaviour, and several describe work that was deliberately not built.
`project-archive/` is the superseded vector-RAG architecture — nothing there
necessarily describes the current implementation.

Demo repositories: `https://github.com/psf/requests` (small, used for
development) and `https://github.com/fastapi/fastapi` (large, stress testing).
