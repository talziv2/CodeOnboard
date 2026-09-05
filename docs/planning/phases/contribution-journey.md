# Contribution journey — Phase A proposal

> **Status: Phase A approved; Phase B built on `feat/contribution-journey`,
> uncommitted.** §A is the approved design, §B records what diverged from it
> and what the rehearsal found. A design record in the sense
> `docs/planning/README.md` means: it argues a change and records what was
> rejected. Nothing here describes current behaviour except §1, which is an audit.

Extend the `contribute_code` goal into a goal-directed *contribution* journey: a
concrete task produces a narrower investigation, a shorter required-knowledge
set, a verified readiness gate, and a guided implementation stage that ends in a
PR-ready result.

The demo claim this exists to make visible:

> Same repository + different goal = different investigation = different learning
> scope = different graph.

---

## 1. The current flow, traced

From goal selection to a `LearningGraph`, as the code actually runs.

| # | Where | What happens |
|---|---|---|
| 1 | `POST /goal/start` → `agents/goal/agent.py:start_session` | A `GoalSession` is created. No model call. |
| 2 | `POST /goal/answer` ×N → `questions.py` | Five fixed `CORE_QUESTIONS`, then 1–2 `FOLLOWUP_QUESTIONS[goal_type]`. `Contribute code / open a PR` maps to `contribute_code` and adds exactly one follow-up: `contribution_context` — *"Is there a specific issue or feature you're working on?"* |
| 3 | last answer → `_synthesize_goal` | One Haiku call turns the Q&A into a `GoalOutput`. `code_depth`/`depth` are overwritten in Python, never by the model. `contribution_context` is carried through verbatim-ish. |
| 4 | `POST /session/start` → `api.py:session_start` | Reserves a `generating` row, returns 202 immediately, runs `_generate_session` in a background task. |
| 5 | `pipeline/graph.py` | `START → repo_survey → documentation → goal_investigation → [reviewer] → mentor → END` |
| 5a | `repo_survey` | Clone into `data/repos/<owner>/<name>`, build the deterministic `Skeleton` (hard requirement, D15), then the cached Layer-B `Survey` per `(repo, commit)`. Derives `module_map`. |
| 5b | `documentation` | No LLM. README excerpt + module docstrings → `doc_context`. |
| 5c | `goal_investigation` | **The only exploration loop in the system (D1/D11).** `investigation.run_investigation` drives `explore.explore` with six tools (`list_files`, `symbols`, `read_file`, `search_code`, `neighbors`, `propose_anchor`) against a Haiku model, until `submit_dossier` passes `DossierValidator`. Validation has four families: structural, unresolved anchors, unmet criteria, surface contradictions. Exit criteria are **already goal-typed** — `contribute_code` demands `min_contracts=2, min_relationships=3` on top of the base floors. |
| 5d | `reviewer` | Runs **only** for `improve_existing_system` and `understand_architecture` (`_REVIEWER_GOAL_TYPES`). Emits `strengths / risks / extension_points / test_gaps / boundaries` into the Mentor's prompt. `contribute_code` does not get it. |
| 5e | `mentor` → `mentor/curriculum.py` | Propose-then-cut. **Propose:** one Sonnet call reads `render_dossier(...)` and over-generates `areas` + `objectives`, each with `kind`, `priority`, `depends_on`, `anchors`, `objective`. **Cut, in Python:** `ground()` resolves every anchor against the skeleton *and* the dossier's verified evidence; `core_set()` = required set + dependency closure + one promoted unit per unstaffed area; `select()` demotes everything beyond the `code_depth` band to `optional`; `order()` is topological with area rank as tiebreak; `build_graph()` writes `sequence` and `prerequisite` edges. |
| 6 | `learning_store.create_session` | Writes `sessions/nodes/edges` (live) **and** `plan_nodes/plan_edges` (the immutable original plan). Status → `active`. |

Then the interactive loop: `GET /session/{id}/lesson` renders through the
Teaching Agent (form chosen by `kind` via `_FORM_BY_KIND`), `POST
/session/{id}/respond` grades, `adaptation.decide_all` picks one of
`hint / reteach / prerequisite / followup`, gaps open and are verified, and
`progress.summary` derives every number the UI shows.

### 1.1 The defect this proposal starts from

`investigation._task(goal)` builds the investigator's per-run request from
exactly four fields:

```python
primary_goal, focus_area, goal_type, code_depth
```

**`contribution_context` is not one of them.** It is collected in the interview,
carried through synthesis — and then dropped before the only stage that explores.
It reaches the Mentor solely as an unlabelled key inside
`json.dumps(goal, indent=2)` in `render_dossier`, where it competes with eleven
other keys for the planner's attention.

So today, two learners on `psf/requests` who both pick *Contribute code* get the
**same investigation** whether their task is "add a retry backoff option" or "fix
a cookie-jar edge case". The task influences nothing until after the repository
understanding is already fixed. That single omission is why the contribution goal
currently produces a general tour with a contribution-flavoured exit criterion,
rather than a task-shaped route.

Everything else in this proposal is downstream of fixing that.

---

## 2. What is reused unchanged

The honest answer to "what needs to be built" is *less than it looks*, because
the architecture is already goal-directed. Reused as-is:

| Concept | Why it already fits |
|---|---|
| **Goal-typed exit criteria** (`CRITERIA_BY_GOAL_TYPE`) | The mechanism for "this goal type must establish different things" exists and is enforced by code. Contribution needs one more field, not a new mechanism. |
| **Propose-then-cut** | The planner already over-generates and *code* cuts. A shorter contribution journey comes from a smaller `required` set, not from a smaller band. This is exactly the "shorter because the system knows the outcome, not because we capped it" property asked for. |
| **`core_set()` / the `required` priority** | **This *is* required knowledge.** Required set + dependency closure = "the minimum this learner must understand". No new abstraction. |
| **`understanding_of()` / gaps / `is_demonstrated`** | Readiness to implement is a *predicate over the existing required set*, not a new state machine. |
| **`adaptation.decide` + retry/reteach** | A blocking misconception already keeps the learner in the learning phase. Nothing to add. |
| **Teaching forms** | `test_coverage → predict-then-reveal`, `risk → critique`, `extension_point → locate` are already the right shapes for contribution stops. |
| **The Tutor** | Already scoped to the current stop with a hard boundary (`test_tutor_boundary.py`). Implementation hints reuse it. |
| **Plan tables / `Start over`** | Additive; a contribution payload is learner state and is cleared by construction. |
| **`GET /session/{id}/file`** + `CodeViewer` | Reading the change boundary needs no new code path. |
| **`SurfaceTabs`, `RouteRail`, `CompletionScreen`** | The contribution stage is a new phase of an existing page, not a new app. |

---

## 3. What genuinely must change

1. **The task must reach the investigator.** (§1.1)
2. **The dossier needs a change-boundary section** for `contribute_code` — the
   structured answer to "what may this change touch, and what must it not".
3. **The curriculum prompt needs a `contribute_code` calibration block**, exactly
   as `use_library` got one. Without it the planner defaults to system altitude,
   which is right for architecture and wrong here.
4. **A readiness-to-implement predicate**, derived, in `progress.py`.
5. **A contribution stage** — new state, new endpoints, new UI phase — that is
   *deliberately not* part of the learning graph (§6.2).
6. **A required-knowledge / skipped-areas view** so the goal-direction is visible.

---

## 4. The smallest coherent architecture

```
  Goal interview ── contribution_context ─────────────────┐
                                                          │
  repo_survey ── Skeleton + Survey ──────────────────┐    │
                                                     ▼    ▼
                              goal_investigation (task-aware)
                                          │
                         Dossier + change_boundary          ← NEW section
                                          │
                        ┌─────────────────┴──────────────────┐
                        ▼                                    ▼
                 reviewer (now runs)                 skipped_areas()      ← NEW, pure
                        │                             survey subsystems
                        ▼                             minus dossier reach
             mentor / curriculum planner
             (contribute_code calibration)            ← NEW prompt block
                        │
                 LearningGraph — required set = REQUIRED KNOWLEDGE
                        │
              ══════ existing learning loop, untouched ══════
                        │
                 ready_to_implement(graph)                   ← NEW, pure, derived
                        │
                        ▼
        ┌───────────── ContributionSession ─────────────┐    ← NEW, session state
        │  Plan → Locate → Implement → Validate → Review │      NOT graph nodes
        └───────────────────────────────────────────────┘
                        │
                  PR-ready summary
```

Two structural commitments hold the whole thing together:

- **The learning engine is not modified.** No new understanding state, no new
  readiness number, no new node origin, no schema-version bump.
- **The contribution stage is not in the learning graph.** See §6.2, which is the
  single most consequential decision in this document.

---

## 5. Proposed state and model additions

### 5.1 The contribution task (first-class, without a new field)

`GoalOutput.contribution_context` already exists and is already persisted inside
`goal_json`. Promote it rather than duplicate it:

- add a **second** follow-up question for `contribute_code`, mirroring
  `improve_existing_system`'s pair:
  ```
  contribution_context   "What change do you want to make? Be specific — name the
                          behaviour, and the file or component if you know it."
  contribution_scope     "How much should change? (a small addition · a change to
                          existing behaviour · a bug fix with a test)"
  ```
- `_task()` gains a contribution block so the investigator is briefed on the
  change, not just the goal.

Rejected: a top-level `contribution_task` column. It would make `goal_json` and a
column two authorities on one fact — the failure `state-ownership.md` names.

### 5.2 `change_boundary` — a new optional dossier section

Added to `INVESTIGATION_SPEC.input_schema`, emitted for any goal but **required
by criteria only for `contribute_code`**:

```jsonc
"change_boundary": {
  "target": [ { "file": "...", "symbol": "...", "why_here": "..." } ],
  "must_not_change": [ { "file": "...", "symbol": "...", "why_not": "..." } ],
  "conventions": [ { "convention": "...", "evidence_file": "..." } ],
  "existing_tests":[ { "file": "...", "symbol": "...", "what_it_guards": "..." } ],
  "edge_cases":  [ { "case": "...", "why_it_bites": "..." } ]
}
```

Every `file`/`symbol` pair goes through the **existing** anchor resolution and
`cited_anchors`, so the boundary is grounded exactly like everything else — an
unresolvable target file fails validation and the investigator is told to fix it.
This is the reason to put it in the dossier rather than in a separate agent: the
grounding machinery is already here and is the invariant the system rests on
(D2, D3).

New exit criteria for `contribute_code`:

```python
"contribute_code": ExitCriteria(
    min_contracts=2, min_relationships=3,
    min_boundary_targets=1, min_boundary_tests=1, min_boundary_edge_cases=2,
)
```

### 5.3 `skipped_areas()` — computed, not generated

A pure function in a new `backend/learning/coverage.py`:

```python
def skipped_areas(survey: dict | None, graph: LearningGraph) -> list[dict]
```

Survey subsystems whose files no curriculum anchor touches, each with the
survey's own one-line responsibility. **Deterministic, no model call.** This is
the house rule — *code decides policy, the model writes prose* — and it makes the
demo claim checkable rather than asserted. A model asked "what did you skip?"
would produce a plausible list; this produces the actual one.

### 5.4 `ready_to_implement()` — derived, in `progress.py`

```python
def ready_to_implement(graph) -> dict:
    """{ready: bool, blockers: [...], demonstrated: n, required: m}"""
```

`ready` iff every node in `core_nodes(graph)` satisfies `is_demonstrated(n)` and
carries no open blocking gap. Blockers are named nodes with a reason.

This deliberately **is not** a new boolean stored anywhere. It is
`goal_readiness == 1.0` restated as a predicate with an explanation attached, so
it inherits D7 for free: readiness may fall only when evidence changes, never
because the plan changed.

### 5.5 `ContributionState` — one additive column

`sessions.contribution_json`, nullable, added through `_ADDITIVE_COLUMNS`. **No
`SCHEMA_VERSION` bump** — every existing session loads unchanged and reads
`contribution = None`.

```python
@dataclass
class ContributionState:
    stage: Literal["plan","locate","implement","validate","review","done"] = "plan"
    plan: dict | None = None          # model-written, learner-editable
    patch: str = ""                   # LEARNER-AUTHORED TEXT. Never applied to disk.
    validation: dict | None = None    # structural scope check + model review
    review: dict | None = None
    pr: dict | None = None            # title, body, testing notes
    proceeded_unready: bool = False   # explicit override, recorded
```

It is **learner state**: `reset.learner_state()` must enumerate it and `Start
over` must clear it. `load_plan` rebuilds nodes at dataclass defaults, so a
session-level field needs the one explicit line — the single place this
architecture does not clean up by construction.

---

## 6. Proposed backend flow

### 6.1 Planning (unchanged shape, three edits)

- `_task()` includes the contribution block.
- `INVESTIGATION_INSTRUCTIONS` gains a short contribution paragraph:
  *establish what the change touches and what it must not; find the tests that
  guard this behaviour and the convention they follow; record the edge cases the
  change has to respect.*
- `_REVIEWER_GOAL_TYPES` gains `contribute_code`. The Reviewer's
  `risks / test_gaps / boundaries` are precisely what a contributor needs, and it
  costs one Haiku call.
- `curriculum._SYSTEM_PROMPT` gains a `contribute_code` calibration block under
  CALIBRATION, in the same shape as `use_library`'s:

  > The developer is going to make **one specific change**. Mark `required` only
  > what they must hold to make *that* change safely. Everything else in this
  > repository — however interesting — is `recommended` or `optional`. Structure
  > the areas as the shape of the change: what the target component owns, the
  > boundary of the change, the contract and edge cases it must respect, and how
  > this repository tests behaviour like it. A journey that teaches this
  > repository's architecture in a sensible order has answered the wrong question.

  **The band is not touched.** Shortness comes from a smaller `required` set, and
  `plan_report.core_before_band` measures whether that actually happened — the
  demo claim is falsifiable rather than staged.

### 6.2 The implementation stage — and why it is not in the graph

Stages live on `ContributionState`, advanced by explicit endpoints. They are
**not** `LearningNode`s. Three reasons, in descending order of severity:

1. **They would corrupt every progress measure.** Five stages in the walk move
   `journey_progress`, `stops_total` and `is_complete()`. If any were marked
   `required` they would enter `goal_readiness`'s denominator — the exact defect
   `progress.py`'s header documents (the gauge fell from 0.50 to 0.33 the moment
   the system decided to help). D7 forbids it.
2. **They carry no objective.** A node's contract is that the Planner writes an
   objective, Teaching builds it, the Grader marks it (D4). "Write your patch"
   has no claim to mark, so it would be a node with a hollow contract.
3. **They are not evidence.** Writing a patch is a learner action. Letting it
   move `understanding_state` reintroduces exactly what D8 and the M0 milestone
   exist to prevent.

So: same session, same page, same header — a different phase of it.

### 6.3 New endpoints

All under the existing four-layer ownership boundary (`Depends(current_user)`,
`_load_session_or_404`, **404 never 403**, and
`test_route_authz_coverage.py` fails the build if either is forgotten).

| Route | Does |
|---|---|
| `GET  /session/{id}/contribution` | The state, plus `ready_to_implement` and the change boundary. Safe on non-contribution sessions: returns `null`. |
| `POST /session/{id}/contribution/plan` | One Haiku call. Task + change_boundary + **the objectives the learner demonstrated** → a 3–6 step plan. Refuses 409 unless ready (or `proceeded_unready`). |
| `POST /session/{id}/contribution/proceed` | The explicit "I'll go on without full readiness" acknowledgement. Records a journey event. Never touches understanding. |
| `POST /session/{id}/contribution/patch` | Stores learner-authored patch text. **No disk write.** |
| `POST /session/{id}/contribution/validate` | (a) deterministic scope check in Python; (b) one Haiku review call. |
| `POST /session/{id}/contribution/pr` | One Haiku call → title, body, testing notes. |

### 6.4 Validation — what is real and what is claimed

**Deterministic half (Python, no model, testable without an API key):**

- parse the patch's file headers; every touched path must exist in the repo *or*
  be a new file under a directory the boundary names;
- every touched path must be in `change_boundary.target` — anything else is
  reported as **out of scope**, by name;
- a path in `must_not_change` is a hard failure;
- flag "no test file touched" against `change_boundary.existing_tests`.

This is what backs the demo's *"Scope: matches requested task"* line. It is a
computed fact, not a model's opinion, and it is the strongest claim in the whole
flow.

**Model half (one Haiku call):** does the patch do what the task asked; does it
respect the contracts and edge cases the dossier established; does it follow the
convention the existing tests use.

**Running tests: recommended, not executed.** See §8.

---

## 7. Proposed frontend flow

| Surface | Change |
|---|---|
| `app/session/[id]/welcome/page.tsx` | **The demo money shot.** For a contribution session, a *Required knowledge* card: the task as stated, "You need N concepts before implementing this safely" over the required set, and *Intentionally skipped:* the computed `skipped_areas` list. |
| `app/session/[id]/page.tsx` | A `phase` alongside the existing `finished` flag. When `ready_to_implement.ready` and the learner accepts, render `ContributionStage` where `CompletionScreen` renders. `RouteRail` stays — the learning route remains visible behind the work, which is what makes it read as one journey. |
| `components/contribution/` (new) | `ReadyGate`, `PlanStep`, `LocateStep` (reuses `CodeViewer`), `ImplementStep` (`<textarea>` + `whitespace-pre-wrap` — **learner text is never markdown**, D23), `ValidateStep`, `ReviewStep`, `PrSummary`. |
| `lib/contribution.ts` (new) | Pure payload → view model, per the `lib/` rule. Stage order, which step is current, which action is primary. **All of it derived server-side and rendered here** (D22). |
| `lib/strings.ts` | All copy. New `detail` slugs (`not_ready_to_implement`, `no_change_boundary`, `contribution_not_available`) need `t.errors` entries. |

No new state library, no client-side computation of readiness.

---

## 8. How readiness integrates with the existing blocker system

- **Ready** = every required node demonstrated, no open blocking gap on one.
  Both halves are existing functions; the predicate composes them.
- **A blocking misconception keeps the learner in the learning phase** with no new
  code: the gap is open, `understanding_of` refuses `understood`,
  `is_demonstrated` is false, `resume_point()` already returns them to the node
  with unfinished remediation, and `adaptation.decide` already chose the reteach.
- **Waiving does not buy readiness.** A waived gap is unverified forever, so the
  node is never demonstrated. That is deliberate and matches `understanding_of`.
- **But the learner is never stranded.** `POST /contribution/proceed` is the
  escape hatch, in the exact shape the codebase already uses for `continue_past`:
  an explicit decision, recorded as a journey event, that unblocks the road
  without ever becoming evidence. The completion screen then says *"Implemented
  with 1 concept unverified"* — honest, and better than either pretending or
  locking the learner out.

---

## 9. Keeping the coding stage from becoming a coding agent

Five structural limits, each enforceable and each testable:

1. **The system never writes code the learner did not write.** The `plan` is
   prose and step titles; the `patch` field is only ever written by
   `POST /contribution/patch` from the request body. No endpoint generates a
   patch. This is a one-line structural test.
2. **Nothing is written to disk, ever.** `data/repos/<owner>/<name>` is a
   **shared checkout across every user and session of that repository** — writing
   a learner's patch there would corrupt other people's sessions. The patch lives
   in `contribution_json`. Test: no contribution module imports a write path.
3. **The stage is unreachable before the learning is done.** `/plan` returns 409
   unless ready or explicitly overridden. The coding stage cannot be the whole
   product because it cannot be the *first* thing.
4. **The change boundary comes from the investigation, not from the coder.** The
   scope check compares against what the dossier established *before the learner
   started*, so "the agent decided to touch six more files" is not expressible.
5. **The Tutor stays inside its boundary.** Implementation hints go through the
   existing Tutor routes with their existing law — a turn is never evidence, and
   nothing under `agents/tutor/` imports grading or mutation
   (`test_tutor_boundary.py`).

---

## 10. File-by-file implementation plan

**Backend — planning**

| File | Change |
|---|---|
| `agents/goal/questions.py` | Second `contribute_code` follow-up (`contribution_scope`); its option vocabulary. |
| `agents/goal/agent.py` | `contribution_scope` on `GoalOutput`; one line in `_SYSTEM_PROMPT` to copy it verbatim. |
| `repo/investigation.py` | `_task()` contribution block · `change_boundary` in `INVESTIGATION_SPEC` · `_entries`-based validation + anchor resolution for it · `min_boundary_*` on `ExitCriteria` · `contribute_code` criteria · contribution paragraph in `INVESTIGATION_INSTRUCTIONS`. |
| `agents/mentor/dossier.py` | `render_dossier` gains a `## The change boundary` section with attached code, ordered right after `understanding`. |
| `agents/mentor/curriculum.py` | `contribute_code` calibration block in `_SYSTEM_PROMPT`. **No band change.** |
| `agents/reviewer/agent.py` | `contribute_code` into `_REVIEWER_GOAL_TYPES`; goal-context line for the task. |

**Backend — learning (additive only)**

| File | Change |
|---|---|
| `learning/coverage.py` *(new)* | `skipped_areas(survey, graph)`. Pure. |
| `learning/progress.py` | `ready_to_implement(graph)`; included in `summary()`. |
| `learning/contribution.py` *(new)* | `ContributionState`, stage transitions, the **deterministic scope check**. Pure — no IO, no model. |
| `learning/store.py` | `("sessions","contribution_json","TEXT")` in `_ADDITIVE_COLUMNS`; read/write in `_write_graph` / `_load_graph_rows`. **Never in a plan table.** |
| `learning/graph.py` | `contribution: ContributionState | None` field. Absent from `to_dict()` (like `tutor`) — its own endpoint serves it. |
| `learning/reset.py` | `learner_state()` counts it; reset clears it. |

**Backend — agents & API**

| File | Change |
|---|---|
| `agents/contribution/plan.py` *(new)* | One Haiku call: task + boundary + demonstrated objectives → plan steps. Never returns code. |
| `agents/contribution/review.py` *(new)* | One Haiku call: patch vs task/boundary/edge cases/conventions. |
| `agents/contribution/pr.py` *(new)* | One Haiku call: title, body, testing notes. |
| `api.py` | Six routes (§6.3), each with the four-layer boundary. |

**Frontend**

| File | Change |
|---|---|
| `lib/api.ts` | `getContribution`, `planContribution`, `proceedUnready`, `savePatch`, `validatePatch`, `generatePr`; types. |
| `lib/contribution.ts` *(new)* | Payload → view model. Pure, with tests. |
| `lib/strings.ts` | All copy + new error slugs. |
| `components/contribution/*` *(new)* | Seven components (§7). |
| `app/session/[id]/welcome/page.tsx` | Required-knowledge + skipped-areas card. |
| `app/session/[id]/page.tsx` | The contribution phase. |

**Tests**

`test_contribution_boundary.py` (structural: nothing writes to disk; no
patch is machine-generated) · `test_contribution_scope_check.py` (the
deterministic validator, no API key) · `test_contribution_state.py` (stage
machine, persistence round-trip, reset) · `test_readiness_gate.py` (ready
predicate, waive does not buy readiness, override records but is not evidence) ·
`test_coverage_skipped.py` · `test_investigation.py` (change_boundary
validation) · `test_curriculum.py` (band unchanged) ·
`test_route_authz_coverage.py` (picks up the new routes automatically) ·
frontend: `contribution.test.ts` + component tests.

**Docs** — `architecture/backend-api.md`, `persistence.md`,
`session-lifecycle.md`, `learning-engine.md`, `agents.md`, `frontend.md`,
`configuration.md` (no new variables), and this file's status line.

---

## 11. Risks and conflicts with the current architecture

| # | Risk | Severity | Response |
|---|---|---|---|
| 1 | **The repo checkout is shared.** `data/repos/<owner>/<name>` is one directory per repository, used by every user and session. | **Critical** | The patch is never applied to disk. §9.2, enforced structurally by test. |
| 2 | **There is no sandbox and no test runner.** No `subprocess` anywhere in `backend/`; GitPython is used only to clone and read HEAD. Executing a cloned public repo's test suite is arbitrary code execution as the server user. | **Critical** | **Descope.** Validate = recommend the command, do not run it. §12. |
| 3 | `data/sessions.db` is irreplaceable and un-backed-up. | High | Additive nullable column only; no migration, no `SCHEMA_VERSION` bump; all tests on `tmp_path`. |
| 4 | Contribution journeys will land below the `working` band floor (8) and log a `band_report` note. | Low | The floor is **advisory and only logged** (LQ6). Expected, not a fault — but it will appear in `state.errors`, so do not read it as a failure during the demo. |
| 5 | Cost (D26). Adds ~2 Haiku calls to planning (reviewer + longer investigation) and ~3 to the contribution stage. | Medium | Cost is a metric, not a constraint. Record the delta in `plan_report` and `docs/planning/phases/cost-optimization.md`. |
| 6 | A model asked for a change boundary may hallucinate a target file. | Medium | Every boundary anchor goes through the same resolution and evidence check as every other anchor; unresolvable ones fail validation and the investigator is told to fix them. |
| 7 | The requested `ready_to_implement = A AND B AND C AND D` boolean would be four new stored facts. | Medium | **Declined in that shape**, delivered in substance: the same four conditions are already expressed by the required set, its gaps, and the change boundary. §5.4. |
| 8 | Stage 5's demo contrast needs two real runs on one repo, with real spend. | Medium | Rehearse on `psf/requests` with a genuine small task; seed a fixture DB (`scripts/seed_ux_fixture.py`) so the UI can be shown without re-spending. |
| 9 | `graph.is_complete()` vs readiness are different measures. | Low | The gate is **readiness**, never completion. Do not conflate; they answer different questions and neither gates the other. |

---

## 12. Recommendation: now vs. later

### Build now — the demo's spine

1. Task into the investigation (§6.1) — **the highest-leverage single change**.
2. `change_boundary` in the dossier, with exit criteria.
3. `contribute_code` calibration block; Reviewer enabled for it.
4. `skipped_areas()` + `ready_to_implement()` — both pure, both cheap.
5. Required-knowledge card on the welcome page — this is what makes the
   goal-direction *visible* to an audience.
6. Contribution stage: Plan → Locate → Implement → Validate → Review → PR summary,
   with the **deterministic scope check** as the centrepiece of Validate.

### Explicitly deferred

| Deferred | Why |
|---|---|
| **Executing tests** | Needs a sandbox that does not exist. Requested; declined with reason (§11.2). The stage recommends the exact command and explains why it is the smallest relevant one. |
| **Real PR creation** | No GitHub write infrastructure, and the configured GitHub MCP server does not currently connect. The deliverable is a PR-*ready* result, which is what was asked for. |
| **A diff editor / applying patches to a working copy** | Would require per-session checkouts — a real change to the storage model, and out of scope this close to submission. |
| **Multi-task contributions, task decomposition** | One task, one journey. |
| **Contribution flow for `improve_existing_system`** | It has its own follow-ups and a different shape. Keep the demo claim one goal type wide. |

### The one thing worth doing even if nothing else is

Fix §1.1. Sending `contribution_context` into `_task()` is roughly five lines,
and it alone changes the investigation, which changes the dossier, which changes
the curriculum, which changes the graph. That is the demo's whole claim, and it
is currently one dropped field away from being true.

---
---

# Phase A addendum — decisions taken 2026-09-04

Approved from the proposal above: implementation stages are not graph nodes;
readiness is derived; no patch reaches the shared checkout; no repository code is
executed; the existing learning engine is reused. The following tightens the
product semantics before implementation.

---

## A1. The contribution scope card

**Placement.** Session-level, on `app/session/[id]/welcome/page.tsx` — after the
task-aware investigation has produced a graph, before the first learning stop.
That page already loads the session, already renders `RouteOverview` from the
areas, and already owns the *Begin* button, so the card is an insertion rather
than a new surface.

**Shape.**

```
Your contribution plan is ready

Task
  Add RequestsCookieJar.get_all(name) returning every value stored under
  that name, and cover its boundary cases with tests.

You need 4 concepts before implementing this safely.

Required
  · What RequestsCookieJar owns that http.cookiejar.CookieJar does not
  · Why get() raises CookieConflictError instead of choosing
  · The domain/path filter convention _find and get_dict share
  · How this repository tests the cookie jar

Not required for this contribution
  · Transport adapters and connection pooling
  · Authentication handlers

This path was generated for your task.

                                     [ Start focused learning ]
```

**Rules.**

- **The count is derived, never written.** It is `len(core_nodes(graph))` — the
  required set plus its dependency closure, the same set `goal_readiness`
  divides by. There is no constant anywhere.
- **The required list is the required nodes' titles**, in walk order. Not a
  paraphrase and not a second summary: the same units the rail is about to show.
- **The skipped list is evidence-bound.** `skipped_areas()` returns only
  subsystems the **Layer-B survey itself named**, none of whose files any
  curriculum anchor touches. If the survey is absent — it is cached per
  `(repo, commit)` and can legitimately be missing — the section is **omitted
  entirely**, never filled with plausible-sounding areas. Capped at three, in the
  survey's own order, because a long list reads as padding.
- The card renders **only** for `goal_type == "contribute_code"` with a
  `change_boundary`. Every other goal type sees today's welcome page unchanged.

---

## A2. Scope-check wording

`change_boundary` is itself model-derived during investigation. The product must
therefore never let a path comparison imply correctness.

**Say:**

> **Scope check passed** — no files outside the planned contribution boundary
> were modified.
> *The boundary was derived from the investigation of your task.*

**On failure:**

> **Scope check: 1 file outside the planned boundary** — `src/requests/sessions.py`.
> Your task's boundary covers `src/requests/cookies.py` and `tests/test_requests.py`.

**Never say:** correct · safe · valid · passing · verified · works.

Three things stay semantically separate in the copy, in the payload, and in the
strings table:

| | Claim it makes | Who decides |
|---|---|---|
| **Scope** | which files were touched | Python, deterministically |
| **Correctness** | whether the change does what the task asked | a model's opinion, labelled as one |
| **Tests** | whether the repository still passes | **nobody — not run** |

---

## A3. The Validate stage

Renders exactly three blocks, always all three, in this order:

```
Scope check              Passed — no files outside the planned boundary
Syntax                   Both files parse as Python
Symbol                   get_all is defined in src/requests/cookies.py
Test file                tests/test_requests.py included

Recommended validation command
  pytest tests/test_requests.py -k cookie -q
  (the tests this repository already uses to guard this behaviour)

Repository tests         Not executed by CodeOnboard
```

The last row is **always present**, never conditional, and never renders a tick.
A stage that shows nothing about tests when none ran reads as a pass.

### The deterministic checks, in full

All operate on **learner-authored text only**. None reads or writes the
repository checkout; none executes anything.

| Check | How | Honest claim |
|---|---|---|
| **Path scope** | patch paths vs `change_boundary.target` / `must_not_change` | "no files outside the planned boundary" |
| **Syntax** | `ast.parse(contents)` per `.py` file | "parses as Python" |
| **Symbol defined** | walk the AST for `FunctionDef` / `AsyncFunctionDef` / `ClassDef` names | "`get_all` is defined in …" |
| **Test file present** | a patch path matching `change_boundary.existing_tests`, or under a `tests/` directory | "a test file is included" |
| **Test naming** | new `FunctionDef`s in a test file start with `test_` | "follows this repository's test naming" |

`ast.parse` builds a syntax tree; it does not import, execute or evaluate the
code. It is the one safe structural read available, and it is the whole reason
these checks can exist at all.

Its two failure modes are bounded rather than trusted: patches are capped at
**10 files × 64 KB**, and `ast.parse` is wrapped for `SyntaxError`,
`RecursionError`, `MemoryError` and `ValueError` — a pathological input reports
"could not be parsed", never a 500.

**Rejected for v1:** import-graph checking (needs to read repository modules to
mean anything), style or format checks (a dependency and an opinion), diff
application (§9.2), coverage (needs execution).

---

## A4. The demo task

### Repository revision

`psf/requests` at **`e8d2c015eecda8273612dd4562425e00cd164ba5`** (2026-05-09).

**It is already pinned, by construction, with no code change.**
`cloner.clone_repo` never updates an existing checkout — *"a clone is pinned,
which is what lets the survey cache key on (repo, commit)"* — so the demo
requirement reduces to one operational rule:

> Do not delete `data/repos/psf/requests` before the presentation.

Deleting it re-clones at whatever `HEAD` is that day, invalidates the
`(repo, commit)` survey cache, and changes the code the dossier anchored on.

### Candidate 1 — cookie jar `get_all` *(recommended)*

> **Add `RequestsCookieJar.get_all(name, domain=None, path=None)` returning every
> value stored under that name, and cover its boundary cases with tests.**

| | |
|---|---|
| Files | `src/requests/cookies.py` · `tests/test_requests.py` |
| Implementation | ~8–12 lines |
| Concepts | 4 |
| Offline tests | **yes** — the cookie-jar unit tests take no `httpbin` fixture |

**Concepts the change genuinely requires**

1. `RequestsCookieJar` is *both* an `http.cookiejar.CookieJar` and a
   `MutableMapping` — the dict face is a **lossy view** over a store that allows
   the same name on several domains.
2. `_find_no_duplicates` raises `CookieConflictError` rather than choosing, and
   `get()` / `__getitem__` are its only callers. That refusal is the contract
   `get_all` exists to complement.
3. The `domain` / `path` filter convention shared by `_find`,
   `_find_no_duplicates` and `get_dict` — the new method must match it, not
   invent a third.
4. How this repository tests the jar: construct, `jar.set(key, value,
   domain=…)`, assert, `pytest.raises` for the conflict.

**Boundary cases, each pointing at real code**

- **The same name on two domains** — the case `get()` refuses. Already written
  down as `test_cookie_duplicate_names_different_domains`, so the learner has a
  model to imitate and the system has evidence to teach from.
- **Name absent** — `[]` or `KeyError`? `get()` raises, `get(name, default)`
  does not, `get_dict()` omits. The learner must *choose* and justify against
  the neighbours. This is the stop with something to be wrong about.
- **A cookie whose value is `None`** — `_find_no_duplicates` tests
  `if toReturn is not None`, so a valueless cookie is invisible to `get()` while
  `get_dict()` includes it. A real asymmetry, sitting in the code, that nobody
  spots by skimming.

**Why this one.** It is the only candidate whose edge case is a *behavioural
contract with a `raise` in it*, which is what gives the learning stops something
to be right or wrong about — the Grader marks against an objective (D4), and an
objective needs a claim, not an observation. The `None`-valued cookie is the
strongest available demonstration that the system found something the learner
would not have. And "how this repository tests this" is a real concept here, with
two real prior tests as evidence, rather than a formality.

**Known risk.** `cookies.py` is 625 lines and pulls in `MockRequest`,
`extract_cookies_to_jar` and `merge_cookies`. The investigation may reach wider
than the change needs, pushing the core set to 5 or 6. That is acceptable — and
it is *visible*, because `plan_report.core_before_band` records it.

### Candidate 2 — `CaseInsensitiveDict.original_case`

> **Add `CaseInsensitiveDict.original_case(key, default=None)` returning the
> casing a header name was last stored with, and cover its boundary cases with
> tests.**

| | |
|---|---|
| Files | `src/requests/structures.py` · `tests/test_requests.py` |
| Implementation | ~5 lines |
| Concepts | 3 |
| Offline tests | **yes** — `TestCaseInsensitiveDict` is pure |

Concepts: the two-level `_store` (`lower → (cased, value)`) and why `__iter__`
yields the cased key while lookup lowercases · the "last case wins" rule · the
test class's conventions. Boundary cases: the same key set with four casings
(already `test_fixes_649`) · key absent · a non-string key raising
`AttributeError` from `.lower()` rather than `KeyError`.

**Why not.** The smallest and safest, and the most audience-legible in one
sentence — but its boundary case is largely stated in the class docstring and
already written as a test, so the system would be *confirming* what a careful
reader sees rather than *finding* it. Weaker evidence for the claim the demo is
making. Keep as the **fallback** if candidate 1's investigation proves too broad
in rehearsal.

### Candidate 3 — `status_codes.name_for(code)`

> **Add `requests.status_codes.name_for(code)` returning the canonical name for a
> status code, and cover its boundary cases with tests.**

| | |
|---|---|
| Files | `src/requests/status_codes.py` · `tests/test_requests.py` |
| Implementation | ~6 lines |
| Concepts | 4 |
| Offline tests | **yes** |

Concepts: `_codes` is many-names-to-one-code and `_init()` flattens it onto a
`LookupDict`, so the forward map is **lossy in reverse** · `LookupDict.__getitem__`
deliberately falls through to `None` instead of raising, which is why a reverse
lookup cannot be built from it · `_init()`'s upper-casing rule and its `\o/` and
`✓` exclusions · `_codes` is also the source of the generated `__doc__`, so it is
the authority. Boundary cases: 200 has seven names — which is canonical? · an
unknown code · the non-alphabetic aliases.

**Why not.** A genuinely good "the map is many-to-one" story, and the one with
the most surprising code (`__doc__` generated at import). But the change is a
data lookup with no contract to violate — nothing breaks if it is wrong — so the
`risk` and `contract` objectives the contribution calibration asks for have
little to bite on.

### Recommendation

**Candidate 1.** Rehearse it end to end before fixing the calibration prompt; if
the core set comes back above 6, fall back to candidate 2, which is the same demo
at lower resolution.

### The contrast run

Same repository, same revision, one changed answer at Q2:

| | Goal A — *Understand the architecture* | Goal B — *Contribute code* |
|---|---|---|
| Investigation | breadth across subsystems | the change, its contract, its tests |
| `core_before_band` | 11–15 (measured, `map` depth, 6 runs) | 3–5 (expected) |
| Areas | subsystems | the shape of the change |
| Ends at | journey complete | a PR-ready contribution |

Both numbers come from `plan_report`, which the planner already writes. The
contrast is **measured after the fact, not staged** — and if a rehearsal shows
the contribution run landing at 11, that is a finding to fix in the calibration,
not a number to cap.

---

## A5. Contribution session state — exact shape

`backend/learning/contribution.py`. Pure: no IO, no model calls, no execution.

```python
Stage = Literal["plan", "locate", "implement", "validate", "review", "done"]

STAGE_ORDER: tuple[Stage, ...] = (
    "plan", "locate", "implement", "validate", "review", "done",
)

# Bounds on learner-authored text. `ast.parse` is safe but not unbounded:
# deeply nested input can exhaust the C stack. Refusing early is cheaper than
# catching RecursionError and more honest than truncating.
MAX_PATCH_FILES = 10
MAX_PATCH_BYTES = 64 * 1024


@dataclass
class PatchFile:
    """One file the learner proposes to write. NEVER applied to disk."""
    path: str                                   # repository-relative
    contents: str                               # learner-authored
    intent: Literal["modify", "add"] = "modify"


@dataclass
class ScopeCheck:
    """Deterministic findings. No model, no execution, no repository write."""
    in_boundary: list[str] = field(default_factory=list)
    outside_boundary: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)       # hit must_not_change
    unparseable: list[str] = field(default_factory=list)     # SyntaxError
    symbols_defined: list[str] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    misnamed_tests: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """SCOPE ONLY. Not correctness, and not a test result."""
        return not (self.outside_boundary or self.forbidden)


@dataclass
class ContributionState:
    stage: Stage = "plan"
    plan: dict | None = None          # {"steps": [{"title","detail"}], "at"}
    patch: list[PatchFile] = field(default_factory=list)
    scope_check: ScopeCheck | None = None
    review: dict | None = None        # {"meets_task","observations","concerns","at"}
    pr: dict | None = None            # {"title","body","testing_notes","at"}
    # The learner chose to start implementing before every required concept was
    # demonstrated. Recorded, never evidence — the `continue_past` shape.
    proceeded_unready: bool = False
    # RECOMMENDED, never executed. Derived from change_boundary.existing_tests.
    validation_command: str = ""
```

**What is deliberately absent**

- **`task`.** It is `graph.goal["contribution_context"]`, read where needed. A
  copy here would make two rows authoritative for one fact — the failure
  `state-ownership.md` exists to prevent, and the same reason §5.1 declined a
  `contribution_task` column.
- **`change_boundary`.** It belongs to the dossier, loaded via
  `dossier_store.load_investigation(session_id, …)`. One authority.
- **Any understanding, readiness or gap field.** Readiness is derived from the
  graph (§5.4). Nothing here may be read by the learning engine.

**Persistence.** One additive nullable column, `sessions.contribution_json`, via
`_ADDITIVE_COLUMNS`. **No `SCHEMA_VERSION` bump** — every stored session loads
unchanged with `contribution = None`. **Never written to a plan table** (D16).

**Reset.** Learner-produced, so `Start over` clears it and
`reset.learner_state()` counts it (`patch_files`, `stage`). This is the one place
the architecture does not clean up by construction, because `load_plan` rebuilds
*nodes* and this is session-scoped.

---

## A6. Task-aware investigation — the exact change

Three edits in `backend/repo/investigation.py`. Nothing else in the pipeline moves.

### A6.1 `_task()` — the per-run brief

Today (verbatim):

```python
def _task(goal: dict) -> str:
    parts = [f"The user's goal: {goal.get('primary_goal', '')}"]
    if goal.get("focus_area"):
        parts.append(f"Focus area: {goal['focus_area']}")
    if goal.get("goal_type"):
        parts.append(f"Goal type: {goal['goal_type']}")
    if goal.get("code_depth"):
        parts.append(f"How deep the user asked to go: {goal['code_depth']}")
    parts.append(
        "Investigate the repository until you can explain the goal-relevant "
        "behaviour from verified code, then submit the dossier."
    )
    return "\n".join(parts)
```

`contribution_context` is absent, which is the audit's §1.1 finding. Proposed:

```python
_CONTRIBUTION_BRIEF = """\
THIS IS A CONTRIBUTION, NOT A TOUR. The developer is going to make ONE specific
change to this repository, and they are going to write it themselves.

THE CHANGE THEY INTEND TO MAKE:
{task}
{scope}

Investigate for THAT change. Concretely, this redirects the investigation:

  WHERE IT BELONGS. The file and the symbol the change would be added to or
  alter — verified by reading them, not the subsystem it is vaguely near.

  THE CONTRACT ALREADY IN FORCE. What callers of that code may rely on, what it
  promises, and what an existing caller would notice if it changed.

  THE EDGE CASES IT MUST RESPECT. Prefer cases you can point at in code — a
  branch, a raise, a default, a comment explaining a subtlety — over cases you
  can imagine. An edge case with an anchor is worth five without one.

  THE TESTS THAT ALREADY GUARD THIS BEHAVIOUR. Read them. How this repository
  writes a test for this kind of code is part of what the developer needs.

  WHAT THE CHANGE MUST NOT TOUCH. The neighbouring code that looks related and
  is not, or that would be unsafe to alter while making this change.

Breadth for its own sake is now a cost. A subsystem this change does not touch
does not belong in the dossier, however interesting it is. This is NOT a licence
to stop early: the exit criteria still apply, and an investigation that has not
established the contract, the edge cases and the tests is not finished.

Investigate until you could tell this developer exactly where to start, what they
must not break, and how to test it. Then submit the dossier, including the
`change_boundary` section.
"""


def _task(goal: dict) -> str:
    parts = [f"The user's goal: {goal.get('primary_goal', '')}"]
    if goal.get("focus_area"):
        parts.append(f"Focus area: {goal['focus_area']}")
    if goal.get("goal_type"):
        parts.append(f"Goal type: {goal['goal_type']}")
    if goal.get("code_depth"):
        parts.append(f"How deep the user asked to go: {goal['code_depth']}")

    # THE CONTRIBUTION TASK REACHES THE ONLY STAGE THAT EXPLORES.
    #
    # It was collected by the interview, carried through synthesis, and then
    # dropped here — so two learners with different contribution tasks got the
    # same investigation, and the task first mattered at planning time, by which
    # point the repository understanding was already fixed.
    task = str(goal.get("contribution_context") or "").strip()
    if goal.get("goal_type") == "contribute_code" and task:
        scope = str(goal.get("contribution_scope") or "").strip()
        parts.append(_CONTRIBUTION_BRIEF.format(
            task=task,
            scope=f"\nHOW LARGE THEY EXPECT IT TO BE: {scope}" if scope else "",
        ))
    else:
        parts.append(
            "Investigate the repository until you can explain the goal-relevant "
            "behaviour from verified code, then submit the dossier."
        )
    return "\n".join(parts)
```

**Two properties this deliberately has.**

- **It redirects, it does not shrink.** Nothing tells the investigator to find
  fewer things. The base floors (`min_components=3`, `min_flows=1`,
  `min_prerequisites=1`) and the contribution criteria still bind, and the
  paragraph says so explicitly. A shorter journey has to come out of the
  *curriculum's required set*, which is the only place shortness can be earned.
- **It falls through untouched for every other goal type**, and for a
  `contribute_code` session with an empty `contribution_context` — so an existing
  session, a re-run, or a learner who skipped the question behaves exactly as
  today.

### A6.2 `change_boundary` in `INVESTIGATION_SPEC`

Added to `input_schema["properties"]`, and **not** to the top-level `required`
list — it is produced for any goal and *demanded* only by the `contribute_code`
criteria, which is how a new section avoids bricking the other six goal types.

```jsonc
"change_boundary": {
  "type": "object",
  "description":
    "For a goal that is making a specific change: where that change belongs and "
    "what it must not disturb. Every file/symbol here is checked against the "
    "repository like every other citation.",
  "properties": {
    "target":          [ { "file", "symbol", "why_here" } ],
    "must_not_change": [ { "file", "symbol", "why_not"  } ],
    "conventions":     [ { "convention", "evidence_file" } ],
    "existing_tests":  [ { "file", "symbol", "what_it_guards" } ],
    "edge_cases":      [ { "case", "why_it_bites", "file", "symbol" } ]
  }
}
```

`cited_anchors()` gains the `target`, `must_not_change` and `existing_tests`
entries (and `edge_cases` where one carries an anchor), so every one of them is
resolved by `anchors.resolve` and an unresolvable path becomes a repair message —
the same grounding every other claim gets (D2, D3). An edge case with no anchor
is permitted and is *not* counted toward `min_boundary_edge_cases`, which is what
makes the prompt's "an edge case with an anchor is worth five without one"
enforced rather than advisory.

### A6.3 Exit criteria

```python
@dataclass(frozen=True)
class ExitCriteria:
    ...                                   # unchanged
    min_boundary_targets: int = 0
    min_boundary_tests: int = 0
    min_boundary_edge_cases: int = 0      # anchored ones only

CRITERIA_BY_GOAL_TYPE["contribute_code"] = ExitCriteria(
    min_contracts=2,                      # unchanged
    min_relationships=3,                  # unchanged
    min_boundary_targets=1,
    min_boundary_tests=1,
    min_boundary_edge_cases=2,
)
```

Base floors are **not lowered**. Lowering them to make the journey short would be
exactly the artificial cap this design refuses.

---

## A7. UI states, intake to completion

### Existing primitives, and what each is reused for

| Primitive | Reused as |
|---|---|
| `GoalDialogue` + `OptionList` | the intake questions (one more follow-up) |
| `StartingProgress` | generation, unchanged |
| welcome page + `RouteOverview` + `ProfileCard` | host of the **scope card** (A1) |
| `RouteRail`, `SessionHeader`, `SurfaceTabs` | unchanged; the rail stays visible through the contribution stage so it reads as one journey |
| `CodeViewer` / `CodeLines` (Shiki, `langForPath`) | **Locate** — the boundary's files, at their anchors |
| `PracticeSurface` | the frame each contribution step is drawn in — the region where the learner *acts*, which is exactly what this is |
| `ChoiceOrText`'s textarea styling | the patch composer's field |
| `Prose` / `InlineProse` | plan steps and review prose (model-authored → markdown) |
| `Disclosure`, `SectionLabel`, `Callout`, `Button`, `Marker` | chrome |
| `CompletionScreen` | the slot the contribution stage renders into |

**Nothing new is invented.** No editor, no diff view, no second state library.

One invariant to respect: `AnswerComposer` documents a **single-composer rule** —
the lesson's textarea and `VerificationBlock`'s must never be on screen together.
The contribution composer is safe because the contribution stage *replaces* the
lesson area, exactly as `CompletionScreen` does. It must never be rendered beside
a live lesson.

### The patch is a list of files, not a unified diff

Each `PatchFile` is `{ path, contents }`. The path is chosen from the boundary's
targets **or typed freely**; the contents are the code the learner proposes.

- The scope check becomes a set comparison rather than a diff parser, and — the
  point — **it can genuinely fail**, because a free path is typeable. A check
  that cannot fail proves nothing.
- `CodeLines` highlights `.py` contents properly. `langForPath` has no `diff`
  grammar, so a unified diff would render grey.
- Hand-writing a valid unified diff in a textarea in three minutes is a demo
  failure mode waiting to happen, and a malformed one would fail on punctuation
  rather than on substance.

### The states

| # | State | Condition | What is on screen |
|---|---|---|---|
| 1 | **Intake** | Q2 = *Contribute code / open a PR* | The two follow-ups: the concrete task, then its expected size. |
| 2 | **Generating** | `status = generating` | `StartingProgress`, unchanged. |
| 3 | **Scope card** | welcome, contribution session with a boundary | A1. Primary action *Start focused learning*. |
| 3b | *Scope card degraded* | no `change_boundary` | Today's welcome page exactly. The session still works as an ordinary journey; nothing claims a boundary that does not exist. |
| 4 | **Learning** | any required node not demonstrated | Today's session page, unchanged. A footer line: **"2 of 4 concepts demonstrated — implementation unlocks at 4."** Derived from `ready_to_implement`; no new computation in the client. |
| 5 | **Blocked** | a required node carries an open blocking gap | Same page. The existing reteach/retry flow already routes them there. The footer names the blocker: **"`get()`'s conflict contract is still unresolved."** Plus a quiet *Start implementing anyway* link → state 6b. |
| 6 | **Ready** | `ready_to_implement.ready` | `ReadyGate` in the `CompletionScreen` slot: the 4 concepts with their verdicts, the task restated, one primary *Start implementing*. |
| 6b | **Proceed unready** | learner took the quiet link | A confirm panel naming exactly what is unverified, then `POST …/contribution/proceed`. Records a journey event. **Never touches understanding.** |
| 7 | **Plan** | `stage = "plan"` | 3–6 steps in a `PracticeSurface`, each `Prose`. *Regenerate* and *This looks right →*. |
| 8 | **Locate** | `stage = "locate"` | The boundary as two lists — *Change these* / *Do not change these* — each row opening `CodeViewer` at its anchor. The `why_here` / `why_not` text is the model's, labelled as the investigation's finding. |
| 9 | **Implement** | `stage = "implement"` | Per-file composer: a path field (prefilled from targets, editable), a textarea, *Add another file*. Saved on blur via `POST …/patch`. The task and the plan stay pinned above. *Stuck?* opens the existing Tutor, scoped to the current stop. |
| 10 | **Validate** | `stage = "validate"` | A3's exact three-block layout. Failures name files. *Back to editing* and *Continue to review*. |
| 11 | **Review** | `stage = "review"` | The model's review in three labelled parts: *does it do what you asked* (opinion), *against the boundary* (fact), *concerns*. Every model claim sits inside a block whose label says it is a review, never a verdict. |
| 12 | **Done** | `stage = "done"` | **Contribution ready.** Files changed · scope-check result · *Repository tests: not executed by CodeOnboard* · PR title, body and testing notes, each copyable. Below it, the learning recap the ordinary `CompletionScreen` shows. |

State 4's footer is the one piece of new copy on the existing lesson page. Every
number in it comes from `progress.summary()["ready_to_implement"]`; the client
computes none of it (D22).

---
---

# Phase B — what was built, and where it diverged

Implemented 2026-09-04 on `feat/contribution-journey`. **Status: built, not
merged, not committed.** This section records the divergences from the approved
design and the defects the rehearsal found, because most of them are things no
unit test could have caught.

---

## B1. Divergences from the approved Phase A design

Six, in descending order of consequence. Everything else was built as approved.

### B1.1 `must_not_change` is symbol-level; a path check cannot evaluate it

**Approved:** the scope check compares touched paths against
`change_boundary.target` and `must_not_change`, and a path in `must_not_change`
is a hard failure.

**Built:** only a `must_not_change` entry with **no symbol** can fail a path
check. An entry naming a symbol is a symbol-level constraint the check cannot
see, and reporting it as a path violation would be claiming to have checked
something it did not.

**Why it changed.** The rehearsal's real boundary named
`cookies.py:RequestsCookieJar` as the target and
`cookies.py:RequestsCookieJar.get` as untouchable — one file, two symbols — and
listed `tests/test_requests.py:TestRequests.test_cookie_duplicate_names_
different_domains` untouchable in the very file the learner must add a test to.
The approved rule marked **both files of a correct patch forbidden**. For a small
contribution the code being added and the code that must not move almost always
live together, so the approved rule fails essentially every well-formed patch.

What is lost is real and is deliberately left unclaimed: nothing deterministic
can tell the learner they edited `get()`. That is what the Review step reads for,
and it is labelled an opinion because it is one.

### B1.2 "Outside the boundary" means the boundary never mentions the file

**Approved:** allowed = `target` ∪ `existing_tests`; anything else is outside.

**Built:** allowed = every file the boundary names anywhere, minus whole-file
exclusions.

**Why.** Same rehearsal, one level out: the boundary listed the test file *only*
under `must_not_change`, so a learner adding a test to it was reported as out of
scope. A file the investigation named — even to say "do not break the test in
it" — is part of the neighbourhood it drew. The claim `passed` now supports is
exactly its wording: *no files outside the planned contribution boundary*.

### B1.3 The stage is entered from server state, not a client flag

**Approved (implicitly):** the page holds `inStage` and renders the stage when it
is true.

**Built:** the page renders the stage when `phaseOf(contribution) === "stage"` —
derived from `state.stage`, the plan and the patch — and holds only the inverse
flag, `leftStage`, for "I clicked back to re-read a stop".

**Why.** Found by reloading the page. A learner with a written plan and a saved
patch was returned to stop 1 of a journey they had finished, with no route back
to their own work. Whether the work has started is a server fact, and D22 says
the client does not compute those.

### B1.4 The stepper gates on the furthest stage *viewed*, not reached

`POST /patch` advances the server to `implement`; the server only reaches
`validate` when `/validate` is called, which the UI offers **from** the Validate
step. Gating the stepper on the server's stage alone dead-ended a learner who had
just saved: Validate was the next thing to do and the only control that could
reach it was disabled. `Save and check` now moves the view to Validate.

### B1.5 Two additions to the investigation brief, both from rehearsal

Neither is a threshold change; both fix defects the contribution framing itself
introduced.

- **"THE CHANGE DOES NOT EXIST YET."** Asked to investigate a change, the model
  anchored seven citations on `RequestsCookieJar.get_all` — the method the
  developer is about to write. None resolved. Grounding accuracy was 0.794 and
  the run spent turns retrying. With the line: **1.000, zero unresolved.**
- **Naming the field for the tests.** The brief said "read the tests"; the
  contract checks `change_boundary.existing_tests`. The model read them and put
  them elsewhere. The brief now names the field. **Unverified against a live
  run** — see B3.

### B1.6 `skipped_areas` reads `key_file`, and orders by the survey's own centrality

The approved accessor read `key_files`/`files`/`paths`. A real survey writes
`key_file`, **singular**, so on every real session every subsystem looked
file-less and the list was silently empty. Ordering was "survey order", which put
`setup.py` and `compat.py` in front of `models.py`; it now sorts by whether the
survey's own `core_abstractions` or `key_symbol` treat the file as central —
order only, never membership.

---

## B2. The rehearsal — Candidate A against the pinned checkout

`psf/requests` @ `e8d2c015eecda8273612dd4562425e00cd164ba5`, `code_depth:
working` on both arms, survey cache warm.

### The contrast

| | Architecture | Contribution (3 runs) |
|---|---|---|
| `core_before_band` | **14** | **8 · 11 · 10** |
| journey (walked stops) | **19** | **11 · 14 · 10** |
| areas | **8** | **5 · 4 · 4** |
| proposed → grounded | 20 → 20 | 12→12 · 14→14 · 10→10 |
| band bound? | no | no |
| dossier accepted | **yes** | **no** (all three) |
| confidence | high | medium |
| investigation cost | $0.234 | $0.102 · $0.153 · $0.138 |

The contribution journey is **~30–45% smaller on every measure**, and the band
never bound in either arm — so the difference is the required set, not a cap.
`plan_report` records it, so the claim is measured rather than staged.

**The areas are the shape of the change, not the repository:** *RequestsCookieJar
ownership → filtering pattern and existing accessors → edge cases get_all() must
handle → test idiom and safe boundaries*. Against the architecture arm's *public
surface → Session as orchestrator → request lifecycle → …*.

**It found the non-obvious thing.** Every contribution run produced a stop on the
`None`-valued cookie: `_find_no_duplicates` tests `if toReturn is not None`, so a
valueless cookie is invisible to `get()` while `get_dict()` includes it. That was
the predicted "the system found something you would not have" moment, and it
arrived unprompted.

### What did not work

**The dossier was never `accepted`** — all three runs stopped at `turn_budget`
and were salvaged, capping confidence at medium. Two criteria stayed unmet:

1. `min_flow_files=2` — a BASE floor, unchanged by this work. This contribution's
   behaviour genuinely lives in one file, so the criterion is unsatisfiable
   honestly. Demanding it invites an invented cross-file flow.
2. `change_boundary.existing_tests` — my criterion, unfilled in all three runs.

**`change_boundary` is unreliable run to run.** Rich in runs 1–2; **entirely
empty in run 3**, which also dropped grounding to 0.609. It is not in the
schema's `required` list (so the six other goal types are unaffected), so under
turn pressure it is the first thing dropped. The product degrades honestly —
Locate says the boundary was not recorded, the scope check says there is nothing
to compare against — but the demo's Locate and scope-check steps depend on it.

**A pre-existing `surface` false positive burns turns**: `RequestsCookieJar.get`
is flagged against `requests.get` in `api.py` — same bare name, unrelated
definitions. Not introduced here, but this goal triggers it every run.

### Recommendations, not applied

Deliberately not done, because they are threshold changes and the instruction was
to report rather than tune:

- Raise the investigation turn budget for `contribute_code` only. The contract
  asks for more than the base one; 20 turns was set before it existed.
- Exempt `contribute_code` from `min_flow_files`, or make it `1`. This is the one
  base floor that is wrong for a single-file change rather than merely demanding.
- Make `change_boundary` structurally required for `contribute_code` (a per-goal
  required list), so it cannot be the thing that gets dropped.

---

## B3. What is verified, and what is not

**Verified live, on screen:** the scope card (task, derived count, the required
concepts, the three skipped areas); the ready gate; Locate against a real
boundary; the patch composer; persistence of a patch across a reload; the scope
check **passing and failing**, with syntax, symbol and test rows, and
`Repository tests — Not executed by CodeOnboard` present in both.

**Verified by test only:** proceed/override (25 API tests), readiness gating,
reset, the structural no-write/no-execute boundary.

**NOT verified against a live model:** Plan, Review and PR summary. The account's
API credit was exhausted by the four pipeline runs, so those three endpoints
return 502 and the UI shows their error copy. Their prompts are therefore
**shipped unmeasured**, as is the `existing_tests` brief fix in B1.5.

Suites at the end of Phase B: backend **2084 passed, 1 skipped** (plus the one
deselected by design); frontend **895 passed, 56 files**; `npm run build` clean.

---

## B4. Hardening the investigation contract

Applied after the first rehearsal, before any commit. Three changes to what the
contract asks for, and one to what the scope check claims.

### B4.1 `min_flow_files` is EXEMPT for `contribute_code`, not lowered

The field became `int | None`, and `contribute_code` sets `None`.

The distinction carries the reasoning and is not a spelling of 1. Every other
criterion here is a **floor** — more of it is better evidence. This one is a
**shape claim**: it asserts the goal's behaviour spans files. A floor of 1 would
say "one file is barely enough" and leave an arbitrary number in place that
happens to pass; `None` says the number is not evidence about this goal at all,
which for a contribution correctly scoped to one production file is the true
statement. The rehearsal's blocker was a single-file change being told its
behaviour "spans at least 2 files".

Every other goal type keeps the base floor of 2, pinned by a test.

### B4.2 A usable `change_boundary` is an exit requirement for `contribute_code`

`ExitCriteria.requires_change_boundary`, checked through the ordinary criteria
machinery so it reaches the investigator in the same feedback as every other
shortfall and can be repaired inside the same budget.

**"Usable" is deliberately the smallest thing that is true:** at least one
`target` naming a file and a symbol **that resolves against the repository**.
Not "every section populated" — that would be demanding a full schema to prove
the section is not empty, which is the opposite of a usability test, and the
other sections already have their own counted criteria.

One resolvable target is exactly what the three consumers need: `Locate` opens it
at its anchor, the plan is written against it, the scope check compares paths to
it. Resolution is the load-bearing word — a target naming a symbol that is not
there sends the learner to write code in a place that does not exist, which is
the failure the anchoring rule exists to prevent.

The message names the lever and distinguishes the two ways it fails: *no target
names both a file and a symbol* versus *none of its N targets resolve*.

### B4.3 `ScopeCheck` no longer implies it enforces symbol-level constraints

`unchecked_symbols` records every symbol-level `must_not_change` entry in a file
the patch touches — **not a finding and never a failure**, but the list of things
the check was asked about and cannot answer. It exists because silence reads as a
pass: "do not change `cookies.py:get`" beside a green scope result invites the
reading that `get` was checked and found intact. Nothing parses the original file
or compares at symbol granularity.

The Validate surface now reads:

```
Path scope               Passed — no files outside the planned contribution boundary.
Syntax                   All 2 files parse as Python
Symbol                   RequestsCookieJar is defined
Test file                Included — tests/test_requests.py
Protected-symbol check   Not performed — 7 protected symbols; this check
                         compares file paths, not symbols.
Repository tests         Not executed by CodeOnboard
```

The scope row is renamed **Path scope**, which is what stops it standing for the
symbol-level rule beneath it. The protected row renders only when symbol-level
constraints exist, and the two "did not happen" rows sit adjacent at the bottom
because reading them together is what stops either being mistaken for a result.
No AST-diff infrastructure was added.

---

## B5. What the corrected contract does to the stored runs

**No new pipeline runs: the account's API credit is still exhausted.** What is
free is re-validating the four stored dossiers against the corrected criteria,
which answers directly whether the fixes remove the observed blockers. It is
**not** a clean rerun — these dossiers were produced under the old contract — and
the numbers below must not be read as one.

| run | goal | boundary usable | grounding | unmet under the CORRECTED contract |
|---|---|---|---|---|
| 1 `9f23ad46` | contribution | **yes** | 0.794 | `existing_tests` only |
| 2 `8c59aaf1` | contribution | **yes** | **1.000** | `existing_tests` only |
| 3 `bffa9838` | contribution | **no** | 0.609 | boundary not usable, + 3 counts |
| — `c9cea872` | architecture | n/a | 1.000 | **none — ok: True** |

Three things follow.

**The `min_flow_files` blocker is gone** from every contribution run, and the
architecture arm is untouched (still `ok: True`, still 1.000).

**Run 3 is now correctly refused**, by the requirement written for exactly it,
with a message naming what to go and do.

**Runs 1 and 2 are one criterion from acceptance**, and that criterion is
`existing_tests` — whose fix (naming the field in the brief) went in *after* those
runs and **has never been measured**. So the remaining blocker is the one thing
still untested.

### The turn budget: do not change it

Recommendation: **leave it at 20.** The evidence for raising it is contaminated
exactly as anticipated — every measured exhaustion happened under a contract that
was also failing for reasons since fixed (anchoring on the created symbol,
unresolved anchors, `min_flow_files`, an unnamed field). Two of the three runs
would now fail on a single criterion with an unmeasured fix already in place.

Raising the budget now would be tuning against contaminated evidence to make a
demo pass, which is the thing this project keeps having to undo. The next step is
three clean runs; only if those still exhaust the budget is a contribution-
specific increase justified.

### Still unverified

- **Three clean reruns of Candidate A** — blocked on API credit.
- **Plan, Review and PR summary** against a live model — same blocker. Their
  prompts remain shipped unmeasured, as does the `existing_tests` brief fix.

Suites after hardening: backend **2109 passed, 1 skipped**; frontend **899
passed, 56 files**; `npm run build` clean. Re-verified on screen: the Validate
surface in both outcomes with the new protected-symbol row, and stage/patch/check
persistence across a reload.

One incidental finding worth keeping: a production `npm run build` sharing
`NEXT_DIST_DIR` with a running dev server corrupts the dev server's chunks
mid-session (`Cannot find module './447.js'`). `frontend/CLAUDE.md` warns about
two dev servers sharing `.next`; a build and a dev server collide the same way.

---

## B6. Final verification pass — three clean runs

Same pinned revision (`e8d2c015`), same task, same `code_depth`. **Nothing was
changed between runs**: no prompt, threshold, band or budget. The harness refuses
to start if the checkout has drifted, and every run appends to
`data/candidate-a-runs.jsonl`.

| | run 1 | run 2 | run 3 |
|---|---|---|---|
| accepted | **no** | **no** | **no** |
| stop reason | `turn_budget` | `turn_budget` | `turn_budget` |
| turns / budget | 22 / 20 | 21 / 20 | 22 / 20 |
| tool calls | 22 | 27 | 29 |
| grounding | 0.667 (18/27) | **1.000 (37/37)** | 0.682 |
| unresolved anchors | **9** | **0** | **7** |
| unmet criteria | 4 | **0** | 5 |
| `change_boundary` usable | **no** | **yes** | **no** |
| resolved target | — | `src/requests/cookies.py:RequestsCookieJar` ✓ | — |
| `existing_tests` | 0 | **3** | 0 |
| anchored edge cases | 0 | 5 | 0 |
| `core_before_band` | 8 | 9 | 9 |
| core (final) | 8 | 9 | 9 |
| journey stops | 11 | 11 | 11 |
| areas | 4 | 4 | 4 |
| band bound | none | none | none |
| duration | 148.5 s | 190.3 s | 168.8 s |
| cost | $0.2227 | $0.2363 | $0.2257 |

Three runs, **$0.6847**. Run 2's split: 22 Haiku calls $0.159, 1 Sonnet call
$0.078.

### Reliability criteria

| criterion | run 1 | run 2 | run 3 |
|---|---|---|---|
| usable `change_boundary` | FAIL | PASS | FAIL |
| no unresolved target anchors | PASS | PASS | PASS |
| `existing_tests` populated | FAIL | PASS | FAIL |
| no `min_flow_files` blocker | PASS | PASS | PASS |
| no band binding | PASS | PASS | PASS |
| narrower than architecture | PASS | PASS | PASS |
| accepted without a budget increase | FAIL | FAIL | FAIL |

**1 of 3 runs is demo-usable.**

---

## B7. Cause analysis — and it is not the budget

### The primary cause: the schema pulls the model into an illegal anchor

Runs 1 and 3 failed identically. Every unresolved anchor is the same symbol:

```
run 1   9 × RequestsCookieJar.get_all (unknown_symbol)
run 3   7 × RequestsCookieJar.get_all (unknown_symbol)
run 2   none
```

and they sit in the same two sections:

```
flow:get_all(name, domain=None, path=None) execution: …get_all (unknown_symbol)
relationship_from:                          …get_all (unknown_symbol)
```

The model is building a **flow for the method it is being asked to help create**,
and relationships from it to the helpers it will call.

This is a SCHEMA MISMATCH, not a wording failure. `flows` and `relationships`
exist to describe how code that runs today executes, and every anchor in them
must resolve. For a contribution, the most natural thing to say about the change
is "here is the path the new method will take" — and the schema offers `flows` as
the only place to say it. `_CONTRIBUTION_BRIEF` tells the model not to
(*"THE CHANGE DOES NOT EXIST YET"*), but a prohibition with no slot to redirect
into is a prohibition fighting the schema. **One run in three obeyed it.**

The consequence cascades: unresolved anchors → rejection → re-emission → turns
spent → budget exhausted before `change_boundary` (the last and only optional
section) is ever filled. That is why the two failures lost the boundary *and* the
tests together.

### The secondary cause: two turn-wasters unrelated to contribution

Run 2 is the control, and it is the informative one. It ended with **zero unmet
criteria** — a fully contract-satisfying dossier — and was still recorded
`accepted: false`, because it submitted that dossier on turn 21 of a 20-turn
budget. Its three rejections were:

1. **A transmission fault** — `components` arrived as XML tool markup
   (`<invoke name="propose_anchor">…`). Pre-existing, goal-independent.
2. Genuine thinness — flow steps, relationships, contracts. Legitimate.
3. **The `surface` false positive** — `cookies.py:get` flagged against
   `requests.get` in `api.py`. Same bare name, unrelated definitions.
   Pre-existing; this goal triggers it every run.

So two of the three turns that pushed run 2 past its budget were spent on things
that have nothing to do with the contribution contract.

### Why the budget must not move

The budget is a **symptom**. Raising it to 25 would let runs 1 and 3 spend five
more turns re-emitting anchors that can never resolve, and would let run 2 pay
for a transmission fault and a false positive out of a larger purse. Fix the
anchor mismatch and the surface false positive first, then measure again; the
honest expectation is that a clean run lands inside 20.

**Recommended fix, NOT APPLIED** — it belongs to a change round, not a
verification pass:

- Give the intended behaviour a **slot** rather than a prohibition: the
  contribution brief should say that the change's own flow belongs in
  `understanding` prose and in `change_boundary` (`why_here`, `edge_cases`), and
  that `flows` and `relationships` describe **only code that runs today**.
- Better still, act at the moment of the mistake: when a rejected anchor names a
  symbol the task says is being added, the repair message should say so and name
  where it belongs, instead of the generic `unknown_symbol`. That is code, it is
  testable, and it lands 20 turns closer to the error than the brief does.
- Narrow the `surface` check so a method on a class is not compared against a
  module-level function of the same bare name.

---

## B8. What is reliable, and what is not

**The curriculum is stable even when the investigation is poor.** Across all
three runs, including the two that lost their boundary:

```
core_before_band   8 · 9 · 9
journey stops     11 · 11 · 11
areas              4 ·  4 ·  4
band bound      none · none · none
```

Area titles were near-identical each time (jar ownership → filtering pattern →
edge cases → test idiom). So the **scope card and the focused learning would demo
correctly 3 times in 3**; only `Locate` and the scope check depend on the
boundary, and those are the surfaces at risk.

---

## B9. Live implementation stage — PASSED

Verified against the live model on run 2's session
(`d0a18721f3934ec08bdce13763e0bffc`).

**Plan** (8.8 s, 6 steps) is grounded throughout: it names the target file and
the line region near `get()`/`get_dict()`, cites the boundary's docstring
conventions (the O(n) note, the `keys()`/`values()`/`items()` style), lists the
boundary's five edge cases, names `test_cookie_duplicate_names_different_domains`
as the test to imitate, and names `_find_no_duplicates()`, `CookieConflictError`
and `get()` as untouchable. **It writes no code.**

**Review** (3.3 s on a good patch) observed only what was in the task, the
boundary and the learner's own text. No generic repository advice.

**Discrimination test.** A deliberately flawed patch — `domain`/`path` compared
as literals so `None` matches only `None`, `KeyError` on empty, one test —
returned `meets_task: false` with six concerns, every one tied to the task or the
boundary:

> The filter logic treats None as a literal value to match, but the task
> requires None to mean 'any value' … the task states `get_all()` should return
> empty list `[]` for no matches, not raise KeyError … the boundary explicitly
> calls this out as a required distinction … no test covers the primary use case
> mentioned in the boundary …

No drift into generic advice, no invented scope.

---

## B10. PR-ready output — passes the honesty bar, misses one requirement

The generated testing notes end:

> **Note: these tests have not been executed yet.**

No "all tests pass" claim anywhere, and the completion screen carries
`Repository tests — Not executed by CodeOnboard` independently of the model.

**The gap:** the summary distinguishes only two of the three required things. It
states the *recommended validation* and that *validation was not executed*, but
it never reports the *deterministic checks CodeOnboard actually performed* —
path scope, syntax, symbol defined, test file present. The PR agent is not given
the `ScopeCheck`, so it cannot report it.

Small and specified; **deliberately not applied** during a verification pass, so
that the output reported here is what the verified build produces.

---

## B11. Rehearsal timings, and what is brittle

| step | measured |
|---|---|
| pipeline (investigation + reviewer + curriculum) | **148–190 s** |
| lesson render, cold | **12.1–12.9 s** |
| lesson render, cached | 0.24 s |
| answer by choosing an option | **0.25 s** (deterministic, no model call) |
| answer by typing | **2.1 s** |
| `/advance` (pre-renders the next lesson) | 12.1 s |
| contribution Plan | 8.8 s |
| patch save | 0.30 s |
| Validate (all deterministic checks) | **0.34 s** |
| Review | 3.3–4.9 s |
| PR summary | 5.9 s |

**Presentation risks, in order:**

1. **Generation is 2.5–3 minutes of dead air.** Start the session before the
   audience is watching, or narrate the progress stages.
2. **Every unvisited stop costs ~12 s on `/advance`.** Walking 11 stops live is
   over two minutes of waiting. Pre-walk the route so lessons are cached — a
   revisit is 0.24 s.
3. **Answer by clicking an option, not by typing.** 0.25 s versus 2.1 s, and the
   deterministic path cannot be flaky.
4. **The investigation is 1-in-3.** Do not generate a contribution session live.
   Use a session verified beforehand.
5. Two operational traps, both hit during this pass: a production `npm run build`
   sharing `NEXT_DIST_DIR` with a running dev server corrupts the dev server's
   chunks; and the survey is written to the DEFAULT database while the API reads
   it from `SESSIONS_DB_PATH`, so a redirected database silently loses the
   briefing and the skipped-areas list.

Manual intervention needed during this rehearsal: 7 of 9 stops were seeded rather
than answered (2 were answered live, to measure the loop). Nothing else.

---

## B12. The comparison, and the recommendation

| | `core_before_band` | journey | areas |
|---|---|---|---|
| **Architecture** | **14** | **19** | **8** |
| **Contribution** | **8 · 9 · 9** | **11 · 11 · 11** | **4 · 4 · 4** |

**No band and no hard cap caused the difference.** `band_bound` was `null` on
every contribution run and on the architecture run; the `working` band is
`[8, 22]` and nothing came near the ceiling. The contribution journey is smaller
because its required set is smaller — which is the property the whole design
exists to demonstrate, and it held on all three runs including the two whose
investigation failed.

### Recommendation: **C — a system-level issue remains**

Not B. The failure is **not specific to Candidate A**: any contribution task adds
a symbol that does not exist yet, so Candidate B
(`CaseInsensitiveDict.original_case`) would meet the same `flows`/`relationships`
trap. Switching candidates would change the odds, not the mechanism.

The issue is narrow, understood and fixable: give the change's intended behaviour
a legitimate slot, repair the anchor rejection message at the point of failure,
and narrow the `surface` false positive. None of those is a threshold change, and
none should touch the budget until they have been measured.

---

## B13. The four fixes, and what they moved

Applied after the first three-run pass. No threshold, band or budget touched.

1. **The brief gives the intent a place.** `_CONTRIBUTION_BRIEF` no longer only
   forbids citing the symbol being added; it names where each part of the intent
   goes instead — behaviour to `understanding`, location to
   `change_boundary.target` *anchored on the container, which exists*, cases to
   `edge_cases`, protections to `must_not_change` — and states that
   `components` / `entry_points` / `flows` / `relationships` / `contracts`
   describe code that runs today.
2. **Grounding recognises a future symbol.** `is_future_symbol(skeleton, goal,
   symbol)` is true when the goal is a contribution, the task names the bare
   symbol, **and the symbol is defined nowhere in the repository**. The third
   condition was learned in test: "add a `get_all` method to `Jar`" names the
   container too, and a citation of `__init__.py:Jar` fails for a completely
   different reason (imported there, not defined there) that wants the generic
   repair. The citation stays counted as unresolved — grounding accuracy is not
   flattered — but the advice changes, and the generic "verify, then correct or
   drop" is suppressed for it.
3. **The `surface` check ignores qualified names.** `A.b` and `b` are different
   names, so a method is no longer compared against a module-level function
   sharing its leaf. `RequestsCookieJar.get` was flagged against `requests.get`
   on every pre-fix run.
4. **The PR summary is given the `ScopeCheck`.** `_checks_text` renders what was
   actually checked — path scope, syntax, symbol, test file — plus an explicit
   *NOT checked* line for symbol-level constraints. `None` when Validate was
   skipped, and the notes then say no automatic checks were run rather than
   implying some were.

Backend suite after the four: **2127 passed, 1 skipped.**

---

## B14. The same 3-run harness, re-run

Unchanged harness, unchanged revision, unchanged task, nothing altered between
runs.

| | run 1 | run 2 | run 3 |
|---|---|---|---|
| **accepted** | no | **YES** | no |
| turns / budget | 22 / 20 | 21 / 20 | 22 / 20 |
| grounding | 0.591 | **1.000** | 0.640 |
| unresolved anchors | 9 | **0** | 9 |
| boundary usable | no | **yes** | no |
| `existing_tests` | 0 | **4** | 0 |
| `core_before_band` | 7 | 8 | 10 |
| journey | 7 | 9 | 12 |
| areas | 5 | 4 | 4 |
| `demoted_by_band` | **0** | **0** | **0** |
| cost / duration | $0.216 / 158 s | $0.270 / 251 s | $0.199 / 162 s |

Three runs, $0.6842. **Still 1 of 3** — but the first accepted dossier this
project has produced.

### What the fixes demonstrably moved

| | before | after |
|---|---|---|
| `surface` false-positive rejections | 3 across 3 runs | **0** |
| future-symbol feedback delivered | never (message did not exist) | **all 3 runs** |
| accepted dossiers | **0 of 3** | **1 of 3** |

Fix 3 is confirmed eliminated. Fix 2 is confirmed delivered — verbatim, in every
run:

> *1 citation(s) name the symbol this contribution is going to CREATE:
> `src/requests/cookies.py:RequestsCookieJar.get_all`. It does not exist yet, so
> no anchor on it can ever resolve … the intended behaviour belongs in
> `understanding`, and where it goes belongs in `change_boundary.target` … *

---

## B15. The remaining cause is not this feature

Rejection trajectories, all six runs plus the architecture baseline:

| run | accepted | rejections, in order |
|---|---|---|
| before 1 | no | **XML-FAULT**, surface |
| before 2 | no | **XML-FAULT**, surface, surface |
| before 3 | no | **XML-FAULT**, surface |
| after 1 | no | **XML-FAULT**, future-symbol |
| after 2 | **YES** | future-symbol, thin |
| after 3 | no | **XML-FAULT**, future-symbol |
| architecture | yes | **XML-FAULT × 16**, other |

**The correlation is total. Every run whose first submission hit the XML
transmission fault was refused; the one run that did not was accepted.**

The fault is the model emitting `<parameter name="component">` XML tool markup
inside a JSON tool input. `DossierCheck.repair_message` then suppresses every
other diagnostic — correctly, and by design: reporting "0 components
established" about an unparseable payload sends the investigator exploring when
what it must do is re-emit. The cost is that the submission yields **nothing
about the contract**. At roughly three submissions per run, losing the first is
losing a third of the feedback loop, and the contribution contract — which asks
for a boundary on top of the base floors — is the one that cannot absorb it.

**It is pre-existing and goal-independent.** The architecture baseline hit it
**sixteen consecutive times** and still passed, because its contract is
satisfiable in the submissions that remain. This is the single most common
failure in the exploration harness, it predates the contribution journey, and it
lives in `explore.py`'s tool-call handling rather than anywhere in this feature.

Fixing it is out of the scope set for this round, and it is not a threshold
change: it is a serialisation defect in a shared harness that every goal type
uses, so it deserves its own change with its own measurement.

---

## B16. The comparison, restated

| | `core_before_band` | journey | areas |
|---|---|---|---|
| **Architecture** | **14** | **19** | **8** |
| **Contribution** (post-fix) | **7 · 8 · 10** | **7 · 9 · 12** | **5 · 4 · 4** |

**No band and no cap caused the difference.** `demoted_by_band` is **0 on every
run** — the band cut nothing. Run 1 records `band_bound: "floor"`, which is the
ADVISORY note that the journey (7) came out under the `working` floor of 8; the
floor is only ever logged (`band_report`: *"kept as planned — the floor is
advisory"*) and `select()` enforces the ceiling alone. Nothing was truncated.

The contribution journey is smaller because its required set is smaller, on all
three runs, as before.

---

## B17. Status

**Not ready to commit.** The three runs are not clean — 1 of 3 — so the final
end-to-end rehearsal was not run, per the condition set for it.

What is settled:

- the four fixes work, and two of them are confirmed eliminated or delivered;
- the contribution design is no longer implicated in the remaining failure;
- the curriculum is stable across all six runs and no band ever bound;
- the live implementation stage (Plan → Review → PR) was verified grounded in
  §B9, and the PR summary now has the three-way distinction it lacked.

What blocks it: **one pre-existing serialisation defect in the exploration
harness**, which is the sole remaining correlate of failure and which affects
every goal type.

---

## B18. The transport defect, fixed at the shared boundary

`explore.repair_tool_input` is applied at the ONE place every tool input passes
through — so every tool and every `ReportSpec` is covered, not just the dossier.

**It repairs only what is provably repairable.** Three shapes were observed in
production; only the first has a self-verifying repair:

| observed value | repair |
|---|---|
| `<parameter name="components">\n[\n  {\n …` | **unwrapped** — strip the tag; if what remains parses as JSON, that is what was meant |
| `<invoke name="propose_anchor">\n<paramete…` | left alone — there is no components data in a tool call |
| `<item>\n<parameter name="file">src/reque…` | left alone — hand-rolling an XML reader for an undefined format is how a mis-parse becomes evidence |

`raw_decode` rather than `loads`, because the wrapper is as often unclosed as
closed. Only a list or dict is recovered; a wrapped scalar is left, since
unwrapping one would change a legitimate field's meaning for no gain.

**Nothing here bypasses grounding.** What is recovered is a list of dicts that
then goes through the same anchor resolution as any other claim — pinned by
`test_recovery_does_not_bypass_grounding`. This fixes an encoding, never a fact.

### And the diagnostics that used to be destroyed

`gap_message` used to `return` the repair instruction and discard everything
else. That was right about the danger — reporting "0 components established"
about an unreadable payload sends the investigator exploring for evidence it
already has — and far too broad about the remedy: a report mangled in ONE field
bought only "re-emit", spending roughly a third of a run's feedback on nothing.

Now `corrupted_fields()` names the unreadable fields, `validate_dossier` skips
only the complaints that are artifacts of them, and the message leads with the
repair and then says *"Once it is readable, the contract still needs: … include
them in the SAME resubmission rather than exploring first."* Re-emission stays
the first move; the contract information survives.

Regression tests: `tests/test_tool_markup_repair.py`, 23 tests, reproducing all
three shapes verbatim from the recorded rejections.

---

## B19. Re-run, and what it moved

| | accepted | usable boundary | XML fault hit | grounding |
|---|---|---|---|---|
| **before any fix** | 0/3 | 1/3 | **3/3** | 0.67 · 1.00 · 0.68 |
| **after fixes 1–3** | 1/3 | 1/3 | 2/3 | 0.59 · 1.00 · 0.64 |
| **after the XML fix** | **0/3** | **2/3** | **1/3** | **1.00 · 1.00 · 0.73** |

The transport repair works: the fault fell from every run to one, and grounding
is the healthiest it has been. Boundary usability doubled. **But nothing was
accepted**, and the reason is two further defects the cleaner runs exposed —
both of them mine, both introduced with this feature.

### Defect A — the brief over-corrected

Run 1 submitted a dossier containing **`change_boundary` and nothing else**:
`understanding`, `components`, `entry_points`, `flows`, `relationships`,
`contracts` and `prerequisites` all absent, seven criteria unmet at once.

Fix 1 told the model firmly what must NOT go in those sections and never
restated that they are still required. It read the whole instruction as "the
boundary is the deliverable". The brief now says so explicitly — *"THEY ARE
STILL REQUIRED, AND THEY ARE STILL MOST OF THE DOSSIER … populate them with the
existing code the change joins"* — pinned by
`test_it_still_demands_the_ordinary_sections`.

### Defect B — the boundary's sections arrived un-nested, undetected

A later run submitted `existing_tests` (4), `edge_cases` (6),
`must_not_change` (6) and `conventions` (6) as **top-level keys**, with
`change_boundary` empty.

The work had been done. The investigator was told *"0 entries"* for every one of
it — which reads as "you did not find any" and sends it back to look for what it
had already written down.

`structural_faults` knew about stranded ITEM keys and nothing about stranded
SECTION names, because it predates `change_boundary`. It now reports them, in the
same shape as the existing check and with the same instruction to re-emit rather
than explore.

### One operational anomaly

One run took **7129 seconds** of wall clock (against a 720 s exploration budget)
and stopped on `time_budget` at 17 turns — roughly thirty times the usual 150–250 s.
API latency rather than anything in this code, but it is a real presentation risk:
a demo that generates live can hang for two hours.

---

## B20. Status after this round

**Not ready to commit,** and the reason is now a pattern rather than a defect.

Three rounds, three fixes each time, and each round's cleaner runs exposed a
shape the previous round's noise had hidden:

1. the `surface` false positive and the missing future-symbol feedback;
2. the XML transport artifact;
3. an over-corrected brief, and un-nested boundary sections.

Every fix was correct and every one moved a measure. The direction is right —
grounding is now 1.00 on two runs in three, boundary usability has doubled, the
XML fault is down to a third of what it was. But **acceptance has not yet been
reached twice in a row**, and defects A and B are fixed but **unmeasured**: no
run has yet happened with them in place.

Suites: backend **2151 passed, 1 skipped**. Spend on verification this session:
**$2.27 over 10 runs.**

The next measurement is one 3-run set (~$0.70) against the two unmeasured fixes.
It is worth taking only as a deliberate decision, because the honest prior — from
three rounds of evidence — is that it may find a fourth shape.

---

## B21. Final measurement — three runs against the two latest fixes

Unchanged harness, prompt, budget, band, threshold, candidate and revision.

| | run 1 | run 2 | run 3 |
|---|---|---|---|
| **accepted** | **YES** | no | — |
| stop reason | turn_budget | turn_budget | **no graph produced** |
| turns | 21 | 22 | — |
| grounding | **1.000** | 0.967 | — |
| boundary usable | **yes** | no | — |
| `existing_tests` | **3** | 0 | — |
| `core_before_band` | 11 | 9 | — |
| journey / areas | 12 / 5 | 11 / 4 | — |
| rejections | XML, XML, future | XML, future | — |
| cost / duration | $0.273 | $0.221 | $0.127 / 702 s |

Set cost $0.6205. **Run 1 passes all seven reliability criteria.** Run 2 fails on
the boundary. Run 3 is a new shape.

### The new shape — and the stop

Run 3 produced **no graph at all**:

```
curriculum: dossier contains no resolvable evidence
```

The investigation returned a dossier, but `_dossier_evidence_ranges` resolved
nothing in it, so the planner refused to build a curriculum from it and the
session failed outright. Every previous failure still produced a usable journey;
this one produced nothing.

Behaviourally this is D15 working exactly as intended — no dossier, no graph,
never fabricate — but it means a contribution run can fail completely rather than
degrade. It ran 702 s against a 720 s exploration budget, so the proximate cause
is near-certainly a dossier salvaged at the time budget with nothing resolvable
in it.

**Measurement stopped here**, per the standing instruction: report a new shape
rather than enter another fix/rerun loop.

### Across four rounds

| | accepted | usable boundary | XML fault | grounding |
|---|---|---|---|---|
| before any fix | 0/3 | 1/3 | 3/3 | 0.67 · 1.00 · 0.68 |
| after fixes 1–3 | 1/3 | 1/3 | 2/3 | 0.59 · 1.00 · 0.64 |
| after the XML fix | 0/3 | 2/3 | 1/3 | 1.00 · 1.00 · 0.73 |
| **after the last two** | **1/3** | 1/3 | 2/3 | 1.00 · 0.97 · — |

Twelve runs, ~$2.89. Every fix was correct and each moved a measure; **none moved
acceptance above one in three.** The rate has not improved across four rounds,
and each round has surfaced a shape the previous round's noise concealed. That is
the finding, and it is more useful than any single run's numbers: **generation is
approximately a one-in-three proposition and should not be relied on live.**

The curriculum, by contrast, has been stable in every run that produced one:
`core_before_band` 7–12 against architecture's 14, journey 7–14 against 19, areas
4–5 against 8, and `demoted_by_band` **0 every time**. The learning path is the
reliable part; the investigation is not.

---

## B22. The session preserved for the presentation

**`47dd056fb7b346da99b0fc464e7ffd70`** — the only run to pass all seven criteria.
Real, produced by the real pipeline against the pinned revision, persisted
through the normal product path.

- investigation **accepted**, grounding **1.000**, 21 turns, $0.18
- **5 areas**, shaped as the change: *RequestsCookieJar structure and ownership →
  Filtering and iteration contract → get() vs get_all() boundary → Edge cases the
  new method must survive → Testing idiom and conventions*
- **12 stops, 11 required**
- boundary: 1 resolvable target, 4 `must_not_change`, 4 conventions,
  3 `existing_tests`, **6 anchored edge cases**
- skipped areas computed: `adapters.py`, `auth.py`, `models.py`
- `validation_command`: `pytest tests/test_requests.py -q`

Stop 8 is **"Handle cookies with value=None"** — the non-obvious finding, present
again: *"a cookie's value may legitimately be None … `get_all()` must include
None-valued cookies in the returned list."* That is the stop to demonstrate.

The architecture counterpart for the contrast is **`c9cea872`** (core 14, journey
19, 8 areas, accepted, grounding 1.000).

---

## B23. The presentation checkpoint mechanism

`tools/demo_checkpoints.py` — generic, no candidate hard-coded, nothing
demo-specific in the product. `tools/` rather than `scripts/` because the
distinction is real: `scripts/` holds measurement harnesses that call live models
and spend money, and this copies rows between SQLite files.

**A checkpoint is a duplicated session, not a restore point.** There is no
`restore` verb. A restore can fail halfway through in front of an audience, and
it mutates the thing you are standing on. Duplication makes each checkpoint
immutable: present from a copy, and a spoiled copy costs one second to replace.
The dashboard becomes the checkpoint menu.

Two properties worth recording:

- **Session-scoped tables are DISCOVERED**, not listed — any table carrying a
  `session_id` is carried, so a table added later needs no change here.
- **Node ids are remapped textually.** `nodes` is keyed on `node_id` alone, so a
  duplicate cannot reuse them; and ids appear not only in columns but inside
  `journey_events`, `arrival` and the tutor transcript. A substitution over every
  copied value catches all of them, including the ones nobody remembers. Ids are
  uuid4 hex, so a false match is impossible.

Tests: `tests/test_demo_checkpoints.py`, 15 of them, reading every result back
through the **real loader**. The load-bearing one is
`test_dirtying_a_checkpoint_leaves_the_source_pristine`.

### The checkpoints, and how they were made

Every state was produced by driving the REAL endpoints — `/lesson` rendered
through the Teaching Agent, `/respond` graded by the real Grader or the
deterministic choice path, `/verify` closing a real gap, `/contribution/*` for
the stage. Nothing was written behind the product's back.

| checkpoint | session | how it got there |
|---|---|---|
| `00` pristine source | `47dd056f…` | the accepted run of §B21, imported |
| `01` contribution scope | `eed356da…` | copy of `00`, nothing walked |
| `02` learning stop | `880773df…` | 7 stops answered, sitting on stop 8 with its lesson cached |
| `03` ready to implement | `73a2248c…` | all 12 walked; one gap opened by the Grader and closed through `/verify` |
| `04` patch written | `0aeafb3a…` | Plan generated, patch entered |
| `05` validated | `c60fc8fb…` | scope check run |
| `06` PR-ready | `ced67291…` | review and PR summary generated |
| `A` architecture | `c9cea872…` | the contrast baseline, imported |

Reaching `03` was itself a product test worth recording: an answer graded
`understood` still carried a `wrong_model` gap, `understanding_of` correctly held
the node at `unresolved`, readiness stayed 10/11, and only answering the
verification question closed it — D14 and M7 both behaving exactly as designed on
real learner input.

### Verified

- every checkpoint opens through the real UI, and its numbers match the API;
- state survives a page reload (checked on `02`: 6/11, stop 8, unanswered);
- moving forward uses the normal flow — the stop-8 critique question was answered
  live on a working copy and graded `understood`, leaving the checkpoint clean;
- **no dependency on `sessions.db` or on the rehearsal database** — `demo.db`
  carries its own account, its own survey (so the briefing and the skipped-areas
  list work) and its own dossiers;
- the architecture contrast is present and reproducible;
- **a full restart of both servers loses nothing** — all eight sessions return;
- served by the repository's own `scripts/ux_fixture_app.py` with
  `CODEONBOARD_UX_DB=data/demo.db`, under **real authentication**, so presentation
  day depends on nothing outside the repository.

Runbook: [`docs/presentation-runbook.md`](../../presentation-runbook.md).

---

## B24. The phase boundary, and the rail that spans it

Found by walking the demo, and it is one defect with two halves.

### B24.1 The centre column belonged to the session

The first implementation derived which surface was on screen from the session's
own phase:

```tsx
) : contribution?.available && !leftStage && phaseOf(contribution) === "stage" ? (
     <ContributionStage/>          // ← above the lesson branch
```

So the moment a learner pressed *Start implementing*, the route rail went inert.
Every stop they clicked re-rendered Locate; the lesson was unreachable for the
rest of the session. The only escape, `leftStage`, was set by one button that
exists solely on the final `done` step.

**The mistake was treating "which surface" as a fact about the SESSION. It is a
fact about NAVIGATION** — selecting a stop is a request to see that stop, and
pressing *Start implementing* is a request to see the stage.

`centreSurface(contribution, requested)` in `frontend/lib/contribution.ts` now
decides it: an explicit request wins in **both** directions, and the session's
phase is only the default for a learner who has not asked for anything yet.
`requested` is genuinely client state — nothing server-side records which of two
surfaces someone is looking at, and nothing should. That is the narrow exception
D22 already allows: it decides what is on screen, never what is true about the
learner.

### B24.2 Two navigation systems, or one journey

The rendering fix raises the layout question underneath it. Once implementation
begins, the route rail and the stage's stepper are both on screen — and the first
proposal was to **collapse the rail** while the contribution surface is showing,
leaving the stepper as the only navigation.

That was rejected, and the reason is the product's own claim: **implementation is
the last phase of a learning journey, not a separate product.** A rail that
disappears says the opposite — that the learner left the journey to go somewhere
else.

So the implementation phase is drawn **inside the rail**, below the chapters:

```
YOUR ROUTE
  Briefing
  [chapters / stops]
  ──────────────────
  IMPLEMENTATION
    Plan · Locate · Implement · Validate · Review
```

The rail already had the vocabulary. The briefing is a bordered box in sentence
case at the head of the route, deliberately shaped unlike a stop (pin on a
connector) or a chapter (tracked uppercase mono) — the walk was already
"bracketed by the two things that are not part of it". This is the third, and it
is the destination.

Three properties are load-bearing:

- **The rows are not stops.** A `StatePin` encodes an understanding state, so
  drawing these as stops would assert that writing a patch is evidence of
  understanding — the one thing D8 forbids. They are rows in a `Callout`, the
  shape this product already uses for "set apart from the flow around it", and
  the *container* carries the prominence rather than the rows.
- **The tones are the Callout's own**, not new ones: `neutral` while locked —
  present, subdued, and carrying the gate's own counter so it says what opens it
  — and `signal` once live, already this palette's "notice this".
- **A stage that cannot be entered is not a control.** A disabled button reads as
  one that failed; a plain row reads as a step not yet reached, which is what it
  is.

The three statuses are the three phases in order — `locked`, `ready`, `active` —
and the `ready` state draws *Ready to implement* as its own row, so the middle
phase of the hierarchy exists in the rail rather than only on a screen the
learner may have navigated away from.

### B24.3 One source for "which stage is on screen"

`viewing` was local state inside `ContributionStage`. With the rail drawing the
same five stages, two copies of that fact would have drifted on the first
interaction — the rail marking the server's stage while the stepper showed
another. It is lifted to the page and passed to both, which is the seam
`frontend/CLAUDE.md` warns about, avoided rather than fixed later.

A useful side effect: the stage the learner left is the stage they come back to.

### B24.4 The door, and what it costs

The centre fix cuts both ways — a learner who clicks a stop mid-implementation
could reach the lesson but not get back. **Back to implementation** sits beside
*Show source* and *Chat*, shown only when a stage exists and is not already on
screen (`canResumeContribution`). One control, not a second navigation system:
the rail moves you around the journey, this moves you between the two surfaces.

### Verified

Both halves were falsified before being believed:

- reverting `setRequestedSurface("journey")` in `handleJump` fails 3 page tests,
  including *"SELECTING A STOP SHOWS ITS LESSON, not the implementation stage"*;
- making `implementationRail` read the server's stage instead of the viewed one
  fails 3 tests across `lib` and the page;
- removing the rail's three props from the page fails all 5 new page tests.

Frontend suite **940 tests, 56 files**; `npm run build` clean. No backend change.
