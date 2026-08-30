# `backend/repo/` — repository understanding

How the system comes to know the repository it is teaching. **No retrieval, no
embeddings, no vector store.**

> Parent: [`backend/`](../README.md) ·
> Architecture: [docs/architecture/repository-understanding.md](../../docs/architecture/repository-understanding.md)

---

## Modules

| File | Owns |
|---|---|
| `cloner.py` | Repository **identity**, URL validation and checkout — three concerns in one place because they have to agree |
| `parser.py` | The tree-sitter walk: one unit per function, class and import, with exact line ranges and a `role` |
| `skeleton.py` | **Layer A** — the deterministic index: files, qualified symbols, imports, subsystems |
| `anchors.py` | The **grounding oracle**. `resolve` (does this exist?) and `resolve_within_evidence` (was it shown?) |
| `tools.py` | The six exploration primitives |
| `explore.py` | The budgeted agentic loop over them |
| `survey.py` | **Layer B** — the goal-agnostic repository survey |
| `survey_store.py` | Survey cache, keyed `(owner/repo, commit_sha, schema)` |
| `investigation.py` | **Layer C** — the goal investigation, producing the Dossier |
| `dossier_store.py` | Dossier persistence, keyed `(session_id, commit_sha, schema)` |
| `dossier_context.py` | The node-scoped slice of the Dossier one lesson needs |
| `structure.py` | Structural neighbours from Layer A — the Mutator's second candidate source |
| `metrics.py` | Measurement over an `Exploration`'s recorded trace and usage |

---

## The three layers

| Layer | Question | Cost | Cached by | Model |
|---|---|---|---|---|
| **A** `skeleton` | What exists, and exactly where? | ms | `repo_path`, in-process | none |
| **B** `survey` | What is this repository, and how is it shaped? | one run | `(repo, commit, schema)` — **shared across users and goals** | Haiku |
| **C** `investigation` | What does *this goal* need? | one run | `(session, commit, schema)` | Haiku |

Layer B is goal-**agnostic**, which is the only reason it can be shared. Layer C is
not.

**Never ask a model for something Layer A can compute.**

---

## Three rules this package holds itself to

**Facts, not judgement.** No tool ranks by importance or summarises. Every result
is derivable from the checkout and the Skeleton.

**Bounded output.** Every tool caps its result and reports `truncated`. Replacing
vector-retrieval context flooding with tool-output context flooding would not be a
migration.

**One boundary check.** All filesystem access goes through
`skeleton.safe_repo_path`; no tool reimplements path validation.

---

## Grounding

`anchors.py` is the single oracle for every agent, and it replaced three
near-identical implementations that each validated against a *retrieval result*.
The consequence is the invariant the whole system rests on:

> A model names a `file` and a `symbol`; **our code derives the line range.**

A hallucinated range is therefore structurally impossible rather than merely
unlikely.

---

## Budgets

`explore.Budget` is enforced **in code**, not requested in a prompt — turns, tool
calls, output characters and wall clock:

| Run | turns | tool calls | chars | seconds |
|---|---|---|---|---|
| Default | 12 | 60 | 240,000 | 240 |
| Goal investigation | 20 | 120 | 500,000 | 720 |

**Exhaustion is a result, not an exception.** Running out yields a partial
`Exploration` with `budget_exhausted=True` and an honest `stop_reason`; so does an
API failure, and so does a tool crash. Nothing raises at the caller. Stopping is
about *understanding*, not spend: budgets are safety rails against runaways, and
remaining uncertainty is recorded in `open_questions` rather than papered over.

Every call is recorded — `Exploration.trace` is replayable and
`Exploration.usage` is per-run cost accounting.

---

## Identity, and the bug that shaped `cloner.py`

`clone_repo` used to key the checkout directory on the URL's **last path
segment**, throwing the owner away, while `survey_store` keyed its cache on
`owner/repo`. So two repositories with the same name and different owners shared
one directory on disk — the second learner silently studied the first one's code,
and the correctly-keyed cache described a repository that was not there. With one
user and one owner per name this never fired; with many users it is a cross-tenant
leak that needs no attacker.

The path now carries the same identity the cache does: `data/repos/<owner>/<name>`,
lower-cased, from the one function every path passes through.

**URL validation is not tidiness either.** `check_repo_reachable` and `clone_repo`
both hand a caller-supplied string to `git`. Without a scheme and host allow-list
that is a server-side request forgery primitive, so the allow-list is applied
here, before any outbound request.

---

## Python only, structurally

The grammar, the qualified-name rule, import resolution and public-API detection
are all Python-specific. Another language means a **sibling adapter behind the
same interface**, not a rewrite. See
[`docs/planning/phases/multi-language.md`](../../docs/planning/phases/multi-language.md)
for the design that has not been built.

---

## Two stale module docstrings

`survey.py` says it is "wired into no agent and no pipeline node" and
`investigation.py` says "nothing here touches production". **Both are stale by two
migration stages** — the survey runs via `survey_store.get_or_create_survey` and
the investigation is the `goal_investigation` graph node. The code is right; those
comments describe an experiment that shipped.

---

## Tests

`tests/test_chunker.py`, `test_skeleton.py`, `test_anchors.py`, `test_tools.py`,
`test_explore.py`, `test_survey.py`, `test_investigation.py`,
`test_structure.py`, `test_cloner.py`, `test_repo_identity.py`,
`test_repo_layout_migration.py`, `test_dossier_session.py`.

Several skip when the fixture repositories are not cloned — see
[docs/testing.md](../../docs/testing.md).
