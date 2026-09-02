# The Tutor — conversation as an instrument of the learning engine

> **Status:** planning only. No production code, prompt, model, flag, schema or
> migration is changed by this document.
> **Supersedes:** [`chat-assistant.md`](chat-assistant.md) (2026-08-20). That
> document designed a read-only Q&A drawer and explicitly rejected three of the
> things asked for here. §0.2 reopens those rejections and says which survive.
> **Depends on:** [`learning-engine.md`](learning-engine.md),
> [`gap-model.md`](gap-model.md), [`learning-loop.md`](learning-loop.md),
> [`reassessment.md`](reassessment.md), [`session-reset.md`](session-reset.md),
> [`ui-surfaces.md`](ui-surfaces.md), [`multi-user.md`](multi-user.md).
> **Cost baseline:** [`cost-optimization.md`](cost-optimization.md) — ≈$0.405 warm
> per 12-unit session.
> **Last updated:** 2026-09-01

---

## 0. The thesis, and what changed since `chat-assistant.md`

### 0.1 The thesis

A learner reading a lesson has questions the lesson does not answer, and today the
only thing they can type into is the answer box — where everything typed is graded
(`AnswerComposer.tsx`, the D2 single-composer invariant). So a question either
becomes a bad answer or goes unasked.

The obvious fix is a chat panel. The obvious fix is also how a curriculum-centric
product becomes a conversation-centric one: knowledge moves into a transcript, the
graph becomes decoration, and the thing that made this system different — that
understanding is a *modelled, evidenced, mutable object* — stops being where the
learning lives.

So the design rule for this whole document is one sentence:

> **The Tutor is an instrument the learning engine holds. It is never a second
> learning engine, and it never becomes the place learning is recorded.**

Everything below is a consequence of that sentence, and most of the design is
subtraction.

### 0.2 What `chat-assistant.md` decided, and which decisions now reopen

That document is good and most of it survives. Three of its rejections are
directly contradicted by the new requirements, and one of its laws needs a
narrowing rather than a repeal.

| `chat-assistant.md` said | Status now | Why |
|---|---|---|
| §2.1 — the chat is read-only w.r.t. the learner's record | **Narrowed, not repealed.** See §5. | The law was written against *automatic, model-judged, ungraded* mutation, and that stays forbidden. It over-reached in forbidding a learner-confirmed route into an existing endpoint, which is not the chat mutating anything — it is a button. |
| §13 — "feed chat questions to the Grader as signal" — rejected | **Still rejected**, verbatim. | It makes asking a question risky. §5.2 gets the same value from deterministic, code-computed signals instead. |
| §13 — "let the chat insert a warm-up when it detects a misconception" — rejected | **Still rejected**, verbatim. | `adaptation.decide_all()` owns that, from graded evidence. §5.3 routes the same intent through `/retry` under the learner's finger. |
| §13 — "stream the answer" — rejected | **Still rejected for MVP**, with the cost of reversing it stated. §11.3. | |
| §1 — "not an answer key" | **Promoted from a rule to an architecture.** See §6. | The old plan enforced it with one context exclusion. It needs two agents, two context builders, and a mode the server decides. |
| §1 — the chat is a single free-text Q&A | **Split in two.** See §3. | Learning-mode and assessment-mode are not the same product with a different prompt. |

**The one genuinely new discovery** that makes assessment mode fit without
inventing anything is in §6.3: the system *already* has a rule that says what
happens when a learner sees the answer before answering, and it already has a
mechanism for asking again without shipping an answer. Socratic mode is not a new
assessment system. It is the existing one, entered a different way.

---

## 1. The architecture as it stands (traced, with the files)

Read this section before any proposal. Every recommendation below points back at
a line of it.

### 1.1 The session spine

```
POST /session/start (202, background)          backend/api.py:689
   → pipeline.runner.run_pipeline               backend/pipeline/graph.py
       repo_survey → documentation → goal_investigation → [reviewer] → mentor
   → LearningGraph                              backend/learning/graph.py
   → store.create_session (+ plan snapshot)     backend/learning/store.py:437

GET  /session/{id}/lesson                       backend/api.py:1015
   → _render_current_lesson                     backend/api.py:610
       → agents/teaching/agent.py::run          (one Haiku call, cached on node)
   → returns { node_id, lesson, retry, pending }

POST /session/{id}/respond                      backend/api.py:1415
   → agents/grader/agent.py::run                (classification + gaps)
   → learning/adaptation.py::decide_all         (deterministic: which response)
   → agents/teaching/respond.py                 (hint | followup | reteach)
     or agents/mentor/mutator.py                (prerequisite — the only mutation)
   → graph.record_attempt(...)                  backend/learning/graph.py:~220
   → returns { classification, gaps, gaps_opened, retry, adaptation, ... }

POST /session/{id}/verify   {gap_id?}           backend/api.py:1229
POST /session/{id}/reassess                     backend/api.py:1309
POST /session/{id}/retry | /jump | /scope | /override | /waive
```

**Everything is synchronous `def`.** FastAPI runs them on Starlette's threadpool.
There is no SSE, no WebSocket, no `StreamingResponse` anywhere in `backend/api.py`.
The only long-running work is planning, and it is handled by a background task
plus a polled `GET /session/progress/{id}` (`api.py:812`), with a per-user set and
a global `threading.Semaphore(3)` guarding the threadpool (`api.py:~680`). That
semaphore is the evidence that threadpool pressure is already a considered
resource here — it constrains §11.3.

### 1.2 The retrieval infrastructure that already exists

**There is no vector store, no embedding model, no retrieval ranking.** Stage 5 of
`repo-understanding.md` removed them. What exists instead:

| Component | File | What it gives the Tutor |
|---|---|---|
| **Skeleton** | `repo/skeleton.py` | Deterministic file/symbol/import index, exact line ranges. Model-free. |
| **Anchors** | `repo/anchors.py` | `resolve()` — the grounding oracle. A model names `file` + `symbol`; our code derives the range. A hallucinated range is structurally impossible. |
| **Dossier slice** | `repo/dossier_context.py::context_for_node()` → `NodeContext.as_prompt_section()` | Goal-aware understanding of one node's place: component role, flow position, relationships, contracts, prerequisites, evidence refs, and `open_questions` explicitly labelled *"NOT established fact, do not teach as true"*. |
| **Structural neighbours** | `repo/structure.py::neighbour_context()` | Goal-agnostic fallback: what this code extends, uses, is used by. Capped hard. |
| **Survey** | `repo/survey.py`, cached in `repo/survey_store.py` by `(repo, commit, schema)` | Repository-level digest: subsystems, entry points, flows. |
| **Doc context** | `agents/documentation/agent.py` → `graph.doc_context` | README, file docstrings, symbol docstrings. No LLM. |
| **Anchored source** | `agents/teaching/agent.py::_read_node_source()` | Every anchor of a multi-anchor unit, labelled and in order. **Raises when all anchors fail** — "no source, no lesson". |
| **Exploration loop** | `repo/explore.py` + `repo/tools.py` | A budgeted agentic tool loop (6 primitives, turn/call/volume/wall-clock budgets, replayable trace, per-run usage). |

`teaching/agent.py::run()` (line ~706) composes these in a stated preference order
— **Dossier → Skeleton → nothing** — and treats every enrichment failure as
non-fatal. That order is a CLAUDE.md rule, and the Tutor must use the same
function calls in the same order rather than a parallel implementation.

**The constraint on `explore.py`:** CLAUDE.md says *"One exploration loop.
`goal_investigation` is the only place the system explores."* The Tutor is a loop
by shape (many calls per session), so giving it tools would be a second
exploration loop, at ~3× cost and 3–8s latency. §9.4 holds the line and says what
would have to change to reverse it.

### 1.3 The learning-state machinery the Tutor must not duplicate

| Concern | Owner | The rule it enforces |
|---|---|---|
| What an answer earns | `learning/adaptation.py::decide_all()` | Pure table keyed on `gap_kind`. One structural mutation per graded answer, max. `ACTIVE_SET_MAX = 3`. |
| What "ask me again" does | `learning/retry.py::to_wire()` | **One learner action, one dispatcher.** `VERIFY` / `REASSESS` / `ANSWER`, or a *reason* there is none (`MET`, `EXHAUSTED`, `PENDING`, `NOT_APPLICABLE`). Pure. |
| What the learner has demonstrated | `learning/graph.py::understanding_of()` | A node cannot be `understood` while a blocking gap is unverified. |
| Evidence vs. decision | `learning/understanding.py` | Two independent axes. `SETTLING_OVERRIDES` settles the journey; only evidence moves the state. Guarded by `tests/test_decision_is_not_evidence.py`. |
| Progress | `learning/progress.py::summary()` | **Goal readiness may fall only when evidence about the learner changes** — asserted in `tests/test_progress.py`. |
| What happened | `learning/history.py` | Attempt-scoped vs journey-scoped, split by lifecycle. Absent means **unknown**, never "nothing happened". |
| Gaps | `learning/gaps.py` | Identity is ours; a model is shown claims and never mints an id. `VERIFICATION_ATTEMPT_CAP=2`, `REMEDIATION_ROUND_CAP=4`, `REASSESSMENT_CAP=2`. |

**`retry.py`'s header is the single most important thing in this document's
context.** It exists because the same decision was previously spread across four
frontend flags and every defect was a seam between them. Its stated rule:

> **A retry question never ships its own answer.** `cached_lesson.prompt` always
> does, because Teaching's contract for `reveal` is *"the explanation — now you
> may answer it"* and `lessonView` opens the reveal after any graded answer. So
> the unit's own prompt is answerable **exactly once, before its reveal has ever
> been shown**, and every later assessment comes from `/verify` or `/reassess`.

§6.3 is built entirely on that sentence.

### 1.4 Persistence and ownership

- `SCHEMA_VERSION = 3`, `SUPPORTED_SCHEMA_VERSIONS = {2, 3}` (`store.py:61`).
- **The settled additive pattern:** a nullable JSON column on `sessions`, added
  through `_add_missing_columns`, with `SCHEMA_VERSION` unchanged — exactly how
  `areas_json`, `journey_events_json`, `briefing_json` and `arrival_json` landed
  (`store.py:261–290`).
- `nodes` / `edges` are the live graph; `plan_nodes` / `plan_edges` are the
  immutable plan. **`save_graph` never writes a plan table.**
- Ownership is decided at the persistence boundary: `store.load_graph(session_id,
  user_id, db)` takes the owner as a **required** parameter. `Depends(owned_session)`
  is the ergonomic wrapper. **404, never 403.**
- Four layers guard it: the store signature, the dependency, a middleware that
  refuses undeclared routes (`api.py:246`), and `tests/test_route_authz_coverage.py`,
  which **fails the build** on any new route that declares neither auth nor a
  reason to be public.

### 1.5 Reset / rebuild / resume

- **Start over** (`POST /session/{id}/reset` → `learning/reset.py::reset_to_plan`):
  wholesale replacement of `nodes`/`edges` from the plan, then explicit clears of
  `journey_events`, `arrival`, `current_node_id`. **Node ids survive** —
  `_row_to_plan_node` reads `id=row["node_id"]` (`store.py:811`). Remedial nodes do
  not. `reset.learner_state()` is the *enumeration of what learner state is*, and
  the reset's correctness argument is "anything not in the plan is gone by
  construction".
- **Rebuild learning path** is `sessionStart(..., force_new)` from the session page
  (`app/session/[id]/page.tsx:316`) — a whole new pipeline run and **a new session
  id**. Nothing session-scoped carries.
- **Resume** is `GET /session/{id}` + `GET /session/{id}/lesson` after login. The
  lesson endpoint returns `retry` and `pending` precisely so a refresh cannot lose
  an outstanding question — *"the learner refreshed" is not a decision about their
  understanding, so it must not change what is on offer.*

### 1.6 The frontend

- Three bands (`lib/layout-bands.ts`): `wide ≥1180` / `medium ≥960` / `narrow <960`.
  Rail track `19.5rem` / `3.5rem` / overlay. `LESSON_FLOOR = 560`.
- The grid is built at `app/session/[id]/page.tsx:628` from **three tracks**: rail,
  lesson (`minmax(0,1fr)`), and a source column **only when the pane is genuinely
  docked** (`var(--source-width)`). A floating pane or a sheet claims no track.
  `sourceMustOverlay()` decides from the *inputs*, never from a measured width,
  because measuring oscillates.
- The source pane already has three display modes — **dock / float / sheet** —
  persisted in `lib/prefs.ts` and driven by `lib/source-pane.ts`.
- `lib/surfaceTabs.ts`: two modes (`learn` → Lesson · Understanding; `route` → Map ·
  Analysis), a **reducer over an explicit event union**, with R5's rule: *selection
  changes only because the learner asked, or because they arrived at a different
  stop. Never because the phase changed.*
- `lib/lessonPhase.ts`: `STUDY | FEEDBACK | VERIFY | RESOLVED`, plus
  `isAsking(phase)` — the predicate the single-composer invariant rests on.
- `lib/lessonView.ts`: one primary artifact per phase; everything superseded
  collapses to a disclosure. Worst case four open blocks.
- `EvidenceDrawer.tsx` is the existing right-hand `<aside role="dialog">` precedent
  (`w-[26rem]`, Escape closes).
- `EarlierExplanations.tsx` is the precedent for *supplementary, always-collapsed,
  attributed* lesson material that is not canonical.
- All copy in `lib/strings.ts` as `t`; error slugs through `errorText`. All
  model-authored prose through `Prose` / `InlineProse`; **learner-written text is
  never markdown**.
- `lib/materialSeen.ts` is the one client-owned learning fact ("have I looked at
  Lesson since it changed"), and it is *guidance, never evidence*.

---

## 2. Architectural constraints and conflicts this feature must respect

Stated up front, because several of them rule out the obvious implementation.

**C1. The evidence invariant.** `tests/test_progress.py` asserts goal readiness may
fall only when evidence about the learner changes. A conversation turn is not
evidence. If the Tutor could move readiness, asking a question would be punished.

**C2. Decision is not evidence.** `tests/test_decision_is_not_evidence.py` and
`understanding.py`'s two axes. "I clicked the hint button" is a decision.

**C3. One exploration loop.** CLAUDE.md. No `explore.py` for the Tutor in MVP.

**C4. Never Sonnet in a loop.** CLAUDE.md. The Tutor is the most loop-shaped call
in the system → Haiku, always.

**C5. Grounding is against the repository.** Citations name `file` + `symbol`; our
code derives ranges via `anchors.resolve`. The Tutor may not print a line number
it invented.

**C6. No source, no lesson** (`learning-engine.md` §4.1.2). Its Tutor analogue: with
no readable source, the Tutor says what it cannot see. It does not answer fluently
from an objective.

**C7. The single-composer invariant (D2).** Two textareas that mirror state under
two buttons both saying "Submit" is a bug this codebase has already had. §8.4.

**C8. R5 — tab selection changes only on learner intent or arrival.** The Tutor
must not be a `SessionTab` and must not touch `TabEvent`.

**C9. Route authz coverage fails the build.** Every new route needs
`Depends(current_user)` or `Depends(owned_session)`, and the middleware refuses
anything else.

**C10. The flag gates behaviour, never storage** (`gap-model.md` §3.8, asserted by
`test_gap_model.py::test_the_persistence_path_never_reads_the_flag`).

**C11. Cost.** The warm baseline is ≈$0.405/session against a $0.10/run target that
is already 4× over. This is the first feature whose cost scales with what the
learner *does*, so it needs a hard cap the learner can see.

**The one real conflict** is between requirement 3 ("conversation should be able to
affect the learning engine") and C1+C2. §5 resolves it by making the Tutor able to
*offer* an existing action and never to *take* one — with a single, carefully
argued exception in §6.5 that is metadata about an answer, not evidence derived
from chat.

---

## 3. Product behaviour: two modes, decided by the server

The Tutor is not one assistant with a stricter prompt during assessment. It is
**two agents behind one surface**, and which one runs is computed deterministically
server-side.

```
backend/agents/tutor/
    mode.py        pure: which mode this stop is in, and why      ← no model
    context.py     pure: two builders, every cap                  ← no model
    explain.py     the learning-mode agent      (one Haiku call)
    scaffold.py    the assessment-mode agent    (one Haiku call)
    suggest.py     pure: validate a model-proposed offer          ← no model
backend/learning/
    tutor.py       the record shape, the caps, the ladder model   ← no model
```

### 3.1 EXPLAIN — during a lesson

Entry point label: **Ask about this**.

The learner may ask relatively freely, and the Tutor answers directly and deeply
from the assembled context. "Explain this differently", "why is this needed",
"show me an example from this repository", "how is this different from X", "I don't
understand this line", follow-ups.

It answers about: this repository, this goal, this journey, this stop, and the
learner's own record on it. Asked about Django, it says it can only see this
repository (`scope: "out_of_scope"`).

### 3.2 SCAFFOLD — while a question is outstanding

Entry point label: **I'm stuck** — placed beside the composer, not as a "Chat"
button. The label communicates the intent, exactly as requirement 5 asks.

The learner may still type anything. What changes is (a) which agent runs, (b)
what context physically exists, and (c) the ladder in §6.

### 3.3 `mode.py` — the dispatcher

Mirrors `retry.py`'s design: one place, pure, returns the reason as well as the
answer, and the frontend renders it rather than deciding it.

```python
EXPLAIN  = "explain"
SCAFFOLD = "scaffold"

@dataclass(frozen=True)
class TutorMode:
    mode: str                  # EXPLAIN | SCAFFOLD
    reason: str                # why — shown to the learner, see §8.5
    question: str = ""         # the outstanding question, when SCAFFOLD
    question_source: str = ""  # history.SOURCE_* — which mechanism asked
    hints_used: int = 0
    hints_left: int = 0
    revealed: bool = False
```

`mode_for(node) -> TutorMode` is SCAFFOLD when, and only when, **an unanswered
question is outstanding**:

- `node.gap_state.pending_verification` is set, **or**
- `node.gap_state.pending_reassessment` is set, **or**
- the unit's own prompt is still answerable — which is exactly
  `retry.to_wire(node).mechanism == retry.ANSWER`.

That third clause is the important one, and it is deliberately delegated to
`retry.py` rather than re-derived. `retry.py` already knows the whole truth about
whether a prompt is spent — including the reveal rule, the re-teach rule, and every
budget — and re-deriving it here would recreate exactly the four-flag seam
`retry.py` was built to remove.

This is the **server-side twin of `lessonPhase.isAsking()`**. The frontend has the
same predicate for rendering; the server must not trust it, because a client that
lied would be asking for the answer key.

---

## 4. Conversation scope and persistence

### 4.1 The scope decision

**One session-scoped transcript, with every turn anchored to the stop it was asked
from.** Rendered filtered to the current stop by default, with "earlier in this
session" behind a disclosure.

The alternatives, and why they lose:

| Scope | Why not |
|---|---|
| Per user, one history | The context is session-scoped: the same question against a different goal has a different right answer. `chat-assistant.md` §13 already rejected this; it stands. |
| Per group / area | `areas` are explicitly *metadata, not an entity* (`graph.py`): no state, no lifecycle, no traversal. Hanging a conversation off one would give it a lifecycle it does not have. |
| Per node, stored on the node | Loses every turn when a node disappears — and remedial nodes disappear on `Start over` (`reset_to_plan` replaces `nodes` wholesale). It also puts the transcript on the wrong side of the plan/state line: nodes are rebuilt from `plan_nodes`, which has no column for it. |
| Per question | Too fine to hold a follow-up, which is the whole point of a conversation. |

**Session-scoped is what `areas`, `journey_events`, `briefing` and `arrival` all
are**, and the argument in `store.py:270–290` transfers verbatim: it belongs to the
session, so there is no node payload it could ride in, and nothing queries by it,
so it stays JSON in one column.

Anchors, not containment, is what makes it *feel* per-lesson. Each turn carries:

```json
{
  "id": "…",
  "at": "2026-09-01T10:12:03+00:00",
  "node_id": "n7",
  "mode": "scaffold",
  "hint_level": 2,
  "question": "…",
  "answer": "…",
  "citations": [{"file": "requests/adapters.py", "symbol": "HTTPAdapter.send",
                 "line_start": 434, "line_end": 538}],
  "scope": "answered",
  "suggestion": {"kind": "reassess", "node_id": "n7"},
  "pinned": false,
  "grounded": true,
  "usage": {"input_tokens": 1180, "cache_read_input_tokens": 260, "output_tokens": 214}
}
```

`hint_level` is `0` in EXPLAIN. `question_source` is **not** stored on the turn: it
is recoverable from the node at the time and storing it would create a second
source of truth for something `history.py` already owns.

### 4.2 Storage

**An additive nullable `tutor_json` column on `sessions`. `SCHEMA_VERSION` does not
move.** One entry appended to `_MISSING_COLUMNS` in `store.py`.

- `LearningGraph.tutor: list[dict] = field(default_factory=list)`, oldest first.
- Written and read **unconditionally**. The flag (§12) gates behaviour, never
  storage — C10.
- `backend/learning/tutor.py` owns the record shape and `new_turn(...)`, mirroring
  `history.py`. Nothing else constructs a turn dict.
- Not in `to_dict()`. The transcript is fetched by its own endpoint, like lessons —
  a session payload that grows with every question asked would make every poll
  heavier for a surface that may never be opened.

**The hint ladder is node-scoped, not transcript-derived.** Deriving "how many
hints has this learner had on the current question" by folding the transcript is
the same mistake `gap_state` was created to avoid (`graph.py`: *"a fold recomputed
on every read loses a gap silently the first time it is wrong"*). So:

```python
@dataclass
class TutorState:
    hints_used: int = 0        # on the CURRENT question
    revealed: bool = False     # the learner asked for and got the answer
    turns: int = 0             # lifetime count on this node, for §5.2 signals
```

stored as `node.tutor_state`, serialized into the existing `nodes` table through
**one more additive column** (`tutor_json` on `nodes`) — the same shape as
`gaps_json`. `hints_used` and `revealed` **reset to zero when a new question is
issued** on that node, and the three places that issue one already exist:
`teaching_respond.reteach`, `teaching_verify`, `teaching_reassess`. That reset is a
single call, `node.tutor_state.new_question()`, added at those three sites.

### 4.3 Lifecycle semantics

| Event | Transcript | Node `TutorState` | Why |
|---|---|---|---|
| Navigate away and back | Kept | Kept | Nothing about understanding changed. |
| Logout / login | Kept | Kept | Ownership is by `user_id`; the row is untouched. |
| `/advance` to the next stop | Kept | n/a (per node) | The transcript is the learner's, not the stop's. Turns carry `node_id`, so the panel filters. |
| `/jump` to another stop | Kept | Kept | Same. |
| **Re-teach** (new prompt installed) | Kept | **`new_question()`** | A re-taught prompt is a genuinely different question (`history.SOURCE_RETEACH`). Carrying the ladder over would deny hints on a question they have not seen. |
| `/verify`, `/reassess` issue a question | Kept | **`new_question()`** | Same reason. |
| **Start over** | **Cleared**, and counted | Gone with the node objects | Conversation is learner-produced. `reset.learner_state()` is *the enumeration of what learner state is*; if the transcript is not in it, the enumeration is wrong. So `learner_state()` gains `"tutor_turns"`, `reset_to_plan` adds `live.tutor = []` beside its existing explicit clears of `journey_events` / `arrival`, and `ResetSummary` gains the count. |
| **Rebuild learning path** | Gone | Gone | New session id. Nothing carries, automatically. |
| Node pruned to `optional` | Kept, still anchored | Kept | `optional` is *excluded from the walk, not removed* — the node still exists. |
| Node replaced / no longer in the graph | Kept, **unanchored** | Gone | Only remedial nodes can vanish, and only via `Start over`, which clears the transcript anyway. Belt and braces: a turn whose `node_id` is absent from `graph.nodes` renders under "asked earlier in this session" rather than being hidden. Honest beats tidy. |
| Multiple sessions on the same repo | Independent | Independent | `_try_resume` is gone (`multi-user.md` M3): creation always creates. |

**`Start over` clears the transcript — DECIDED (OQ-3).** The Tutor conversation is
session-derived learning state, so it goes when `reset_to_plan` restores the plan
snapshot. `reset_to_plan`'s correctness argument is *"anything not in the plan is
gone by construction"*, and a surviving transcript would be the first exception to
it: a list of stops the learner had already been confused by, sitting beside a route
that claims to be fresh. It also keeps the reset summary honest — the learner is
told what they are discarding, by count, in `ResetSummary`.

Everything that is *not* a reset preserves it: normal navigation, `/advance`,
`/jump`, closing and reopening the pane, logging out and back in, and resuming a
session days later. Those are all reads of the same row.

### 4.4 `Rebuild learning path` — a different act, and why it needs no code

`Rebuild` is not a reset. `app/session/[id]/page.tsx::rebuild()` calls
`sessionStart(repo_url, goal, force_new)` and **routes to a new session id**; the
old session row is untouched and still listed on the dashboard. So:

- the rebuilt session starts with **an empty transcript**, because it is a different
  `sessions` row and `tutor_json` is `NULL` there;
- **node identities do not carry** — the new plan is a fresh Sonnet call producing
  fresh `uuid4` node ids — which is exactly why carrying a transcript across would
  be wrong: every turn's `node_id` anchor would dangle, and the panel would show a
  conversation about stops that do not exist;
- the **old** session keeps its transcript intact, so a learner who rebuilds and
  then reopens the previous session finds their questions where they left them.

This needs no implementation. It falls out of `create_session` writing a new row,
and it is stated here because "rebuild loses the conversation" is a behaviour
somebody will otherwise file as a bug.

---

## 5. Exactly how conversation can and cannot affect learning state

Three tiers, with a hard wall between the second and the third.

```
   INTERACTION            SIGNAL                    MUTATION
   every turn             computed in code          only via an existing endpoint,
   persisted              from persisted facts      only on a learner click
   touches nothing        surfaced as an OFFER      ──────────────────────────────
                                                    /verify · /reassess · /jump
                                                    /scope · /retry · /override
```

### 5.1 Tier 1 — Interaction (always)

A turn is appended to `graph.tutor`, `node.tutor_state` counters move, `save_graph`
runs. **No attempt, no gap, no grade, no `understanding_state`, no readiness, no
journey event, no graph mutation.**

Enforced structurally, and testable: **no module under `backend/agents/tutor/` may
import `run_grader`, `mutate_graph`, `adaptation`, or `record_attempt`**, and the
`/tutor/ask` endpoint's only writes are the transcript append and the counter
increments. Asserted the way
`test_gap_model.py::test_the_persistence_path_never_reads_the_flag` is asserted.

### 5.2 Tier 2 — Signal (deterministic, code-computed, never a model's opinion)

The requirement asks what meaningful signals conversation can produce. The answer
this design gives is: **only signals that are facts about what happened, never
signals that are a model's judgement about the learner.**

`backend/learning/tutor.py`, pure, no model:

| Signal | Definition | Threshold | Surfaces as |
|---|---|---|---|
| `heavily_scaffolded` | `hints_used >= 2` on the current question | 2 of 3 | §6.5 — the retry offer stays open after `understood` |
| `revealed` | the learner took the answer | 1 | §6.3 — the prompt is spent; `/reassess` is the route |
| `dwelling` | `turns >= 4` on one node in EXPLAIN | 4 | an offer: *"Still stuck here? Try a fresh question about the objective."* → `/reassess` |
| `returning` | turns on a node the learner has already settled | 2 | an offer: *"You marked this done — want to check it?"* → `/reassess` |

**Deliberately absent, and each is a rejection:**

- ~~"the learner said they don't understand"~~ — that is a model classifying free
  text, which is the Grader's job on a graded question. A learner who writes "I
  don't get this" as rhetorical framing would be marked down for a figure of speech.
- ~~"the Tutor identified a prerequisite misconception"~~ — `adaptation.decide_all()`
  owns that, from graded evidence, with `Gap` objects whose ids **we** mint. A model
  opening a gap from an aside would put an unfalsifiable claim into the one record
  whose job is to say what actually happened.
- ~~"the learner demonstrated understanding in conversation"~~ — this is the most
  tempting and the most dangerous. It would let the learner talk their way to
  `understood` on a channel with no objective, no rubric and no reveal-freshness
  rule. `understanding_of()` exists to make that impossible.

### 5.3 Tier 3 — Mutation (learner-confirmed, through an existing endpoint)

**The Tutor never mutates. It can only put an existing button in front of the
learner.** The button is the same button that already exists elsewhere in the UI,
posting to the same endpoint, with the same validation, the same caps and the same
records.

The model may emit **one optional suggestion** in its structured output, from a
closed vocabulary that maps 1:1 onto existing endpoints:

```python
SUGGESTION_KINDS = frozenset({
    "verify",     # POST /session/{id}/verify   {gap_id}
    "reassess",   # POST /session/{id}/reassess
    "jump",       # POST /session/{id}/jump     {node_id}
    "deepen",     # POST /session/{id}/scope    {direction: "deeper"}
})
```

`suggest.py::validate(graph, node, raw) -> Suggestion | None` — pure, deterministic,
and it drops anything that does not survive:

- `verify` → the gap id must exist **on this node**, be `open`, be blocking, and not
  be exhausted. In practice: it must equal `retry.to_wire(node).gap_id`, so the
  Tutor cannot propose a target the retry dispatcher would refuse.
- `reassess` → `retry.reassessments_left(node) > 0` and nothing pending.
- `jump` → the node must exist in `graph.nodes` and be in `path_order()`.
- `deepen` → there must be at least one `optional` unit to promote (`scope.py` says
  a journey with nothing optional left has nothing deeper to offer).

An invalid suggestion is **dropped silently, and the answer text is kept** — exactly
what `briefing/agent.py` does with unresolvable `notes[].file`, and what §4 of
`chat-assistant.md` specified for citations.

**Nothing happens without a click.** The click goes to the existing endpoint from
the existing client function. The Tutor is not in the request path.

### 5.4 The line, stated once

> Conversation may **describe** the learner's state, may **offer** an action the
> system already supports, and may **never** be the reason a state changed.

---

## 6. Assessment behaviour: the Socratic ladder

### 6.1 What already exists, and why it is nearly right

`teaching/respond.py::hint()` is already a Socratic scaffold generator. Its
`_HINT_SYSTEM` says, in the prompt the repo already ships:

> *Point at where in the shown code the answer lives, or restate the question in a
> smaller, more concrete form. You may narrow it. **DO NOT answer it.** A hint that
> contains the answer teaches nothing and wastes the only moment they were engaged.*

Two things are wrong with it as an answer to this requirement, and neither is the
prompt:

1. **It only fires after a graded answer** classified `no_attempt`. A learner who is
   stuck must first spend their one answerable attempt on "I don't know" to earn a
   hint. `retry.py` is emphatic that the unit's prompt is answerable *exactly once*
   — so being stuck currently costs the learner the assessment.
2. **It has one rung.** There is no ladder, no budget, and no defined end state.

The Tutor's assessment mode is therefore not a new subsystem. It is **`hint()`
promoted to a pre-answer act, given a ladder and a terminus.**

### 6.2 The ladder

Three rungs, then a decision. Three because each rung is a *different kind of
help*, not the same help louder — a fourth would be padding, and two would jump
from orientation to a guiding question with nothing between.

| Rung | What it does | Prompt family |
|---|---|---|
| **1 — Orient** | Points at *where* in the shown code the answer lives. Names no mechanism. | `_HINT_SYSTEM` as it stands today |
| **2 — Narrow** | Restates the question in a smaller, concrete form: "start with just the first line — what does it return?" | `_HINT_SYSTEM` + "narrow it further; rung 1 was not enough" |
| **3 — Guiding question** | Asks a *sub-question* whose answer composes into the real answer. Socratic proper. | a new `_GUIDE_SYSTEM`, closest sibling of `_FOLLOWUP_SYSTEM` |
| **— then** | Offers **Show me the answer** — see §6.3 | no model call |

`HINT_LADDER_MAX = 3`, a constant in `learning/tutor.py`, beside the other caps and
argued the same way `REASSESSMENT_CAP` is.

The ladder is **per question**, reset by `new_question()` (§4.2). A re-teach, a
verification and a reassessment each install a genuinely different question, and a
learner who has never seen the new one has had no hints on it.

**Between rungs the learner may keep typing.** The ladder is not a wizard: an
off-ladder question in SCAFFOLD mode ("what does `Response.raw` even hold?") is
answered by the scaffold agent from the scaffold context, and does not advance the
rung. Only the explicit **Give me another hint** control advances it. That
separation is what stops the ladder from being an annoying artificial restriction —
the learner is never blocked from asking, only from being handed the answer.

### 6.3 When a direct answer is allowed — and the discovery that makes it free

The requirement asks when a direct answer should eventually be allowed. **The
system already answers this**, and the answer requires no new policy:

> `retry.py`: *the unit's own prompt is answerable exactly once, before its reveal
> has ever been shown, and every later assessment comes from `/verify` or
> `/reassess`, both of which ship a question and nothing else.*

So **Show me the answer** does exactly, and only, what the system already does when
a reveal is shown:

1. `node.tutor_state.revealed = True`
2. the outstanding question becomes **spent** — the composer for it goes read-only,
   with the answer shown
3. `retry.to_wire(node)` now returns `REASSESS` (or `VERIFY` if a gap is open)
4. the learner presses the same **Ask me again** they already know, and gets a
   fresh question that ships no answer

Nothing is punished, nothing is invented, and the assessment is not lost — it is
**deferred to a question the reveal cannot have answered.** `REASSESSMENT_CAP = 2`
already bounds it, and its docstring already gives the argument: *"without a cap the
measure degrades from mastery to persistence."*

Implementation-wise this is small: `retry.py` gains one clause — a node whose
`tutor_state.revealed` is set, whose current mechanism would be `ANSWER`, returns
`REASSESS` instead. One condition, in the one module that owns the question.

**The rung-3 → reveal transition is offered, not forced.** After rung 3 the learner
sees the reveal offer beside *Keep trying* and the composer. A learner who wants to
keep thinking is never pushed, and the offer is available from rung 1 onward — a
learner who already knows they want the explanation should not have to climb a
ladder to ask for it. What the ladder bounds is how many *hints* the system will
write, not when honesty becomes available.

#### The consequence is stated before the click — DECIDED (OQ-2)

The learner is choosing to step out of assessment and back into learning. That is a
legitimate choice and the UI must name it as one, in advance:

> **You can see the explanation now, but this question stops counting as your
> assessment. You'll get a new question on the same concept.**

and the control itself carries the whole trade in its label:

> **`Show answer & get a new question`**

Not "Show answer" with a toast afterwards. A consequence disclosed after the fact is
not a choice, and this is the one place in the system where a learner can spend an
assessment — so the spend is on the button. `t.tutor.revealWarning` and
`t.tutor.revealAction` hold both strings, and a frontend test asserts the warning is
on screen *before* `revealAnswer` can be called.

**No parallel assessment flow.** After the reveal the learner is in exactly the state
they would be in after any graded answer: the prompt is spent, `retry.to_wire`
returns the next mechanism, and the same *Ask me again* control they already know
serves it. `/verify` still wins over `/reassess` when a gap is open, `REASSESSMENT_CAP`
still bounds it, and `retry.py` stays the single dispatcher. The only new code is one
clause and one boolean.

### 6.4 Should hint usage become part of learner state?

**Yes — as metadata on the attempt, not as a state of the learner.**

`history.py` already stores, per attempt: `question`, `question_source`, `kind`,
`graded`, and a `response` envelope for what the system did *after*. What is missing
is what the system did *before*. So one sibling key, with `history.py`'s exact
absent-means-unknown discipline:

```python
ASSISTANCE = "assistance"      # backend/learning/history.py

def new_assistance(hints: int, revealed: bool) -> dict:
    return {"hints": hints, "revealed": revealed}

def assistance_of(attempt: dict) -> dict | None:
    """How much help preceded this answer, or None when unrecorded.

    None is deliberately not {"hints": 0}. Every attempt written before the
    Tutor existed is unknown, and defaulting them to unassisted would invent a
    fact about the stored corpus — the same mistake `intervention_of` refuses.
    """
```

Written in `session_respond` at the same place `question` and `question_source` are
captured (`api.py:~1465`), read from `node.tutor_state`.

**It does not change the grade.** The Grader marks the answer, not the route to it.
A learner who reasons to a correct answer with two hints understands it; that is
what a hint that does not contain the answer is *for*.

### 6.5 Should heavy help trigger later verification?

**Yes, and it is an offer, not a demotion.**

```python
# learning/tutor.py — pure
HEAVY_SCAFFOLD = 2

def heavily_scaffolded(node) -> bool:
    return node.tutor_state.hints_used >= HEAVY_SCAFFOLD
```

Consumed in exactly one place: `retry.to_wire()`. A node that would otherwise return
`reason = MET` returns instead an available `REASSESS` with `reason = "assisted"`,
provided budget remains. The learner sees *"You got there with help — want a fresh
one?"*

**What it must not do, and why:**

- It must not lower `understanding_state`, `understanding_of()`, or readiness. That
  would violate C1 (readiness falls only when *evidence* changes — and the evidence
  is the same correct answer) and C2 (pressing a hint button is a decision).
- It must not open a gap. Gaps are false claims the learner made
  (`gaps.py`), and needing a hint is not a claim.
- It must not block `is_complete()`. `SETTLING_OVERRIDES` decides settlement, and
  the learner has not made any of those decisions.

The offer is the right instrument precisely because it changes nothing about the
learner and everything about what the system puts in front of them.

### 6.6 How this composes with the existing flows

| Existing flow | Interaction with the Tutor |
|---|---|
| **Retry** (`retry.py`) | The Tutor never issues a question. It sets `revealed`, which `retry.py` reads; and it can *suggest* the retry, which the learner clicks. One dispatcher, unchanged. |
| **Warm-up / prerequisite** | Inserted only by `mutate_graph` from a graded `missing_prerequisite`. The Tutor's `jump` suggestion can send the learner to a stop that already exists; it cannot create one. |
| **Off-topic** | An off-topic *answer* opens no gaps and moves no state (`grader/agent.py`). An off-topic *question* to the Tutor is `scope: "out_of_scope"` and is simply answered as such. The two never meet. |
| **Gaps / remediation** | The scaffold context **does** include open gap `claim`s: they are the learner's own false beliefs, not answers, and scaffolding around a known misconception is the whole point. Gap *verification questions* get the same ladder as any other question, and `VERIFICATION_ATTEMPT_CAP` is untouched — the Tutor spends no verification attempts. |
| **`/waive`, `/override`** | Untouched. A waive is a decision; the Tutor has no opinion about it. |
| **Prune-ahead / scope** | The Tutor may suggest `deepen`. It may never suggest `shorter` — demoting the journey on the strength of a conversation is the system deciding the learner has had enough, which is `scope.py`'s point about user overrides winning. |

---

## 7. Context assembly and answer-leakage protection

### 7.1 Two builders, because one builder with a flag will eventually leak

`backend/agents/tutor/context.py` — **model-free, pure, every cap lives here.** Same
discipline as `curriculum.py`: sizing is decided by code, so it is testable without
an API key.

```python
def build_explain_context(graph, node, repo_path, skeleton, survey, dossier, turns)
        -> ExplainContext

def build_scaffold_context(graph, node, question, repo_path, skeleton, dossier, turns)
        -> ScaffoldContext
```

**Two functions with two return types, not one function with `include_reveal=False`.**
The distinction is the whole of §7.3: a boolean parameter is one wrong caller away
from a leak, and a type that has no field for the reveal cannot leak it however it
is called. `ScaffoldContext` has **no `reveal` attribute, no `expected_answer`
attribute, and no `rationale` attribute.** There is nothing to forget to exclude.

### 7.2 `ExplainContext` — the blocks

Ordered for prefix stability, which is what makes §10's cache numbers real.

| # | Block | Source | Cap | Stable while |
|---|---|---|---|---|
| 1 | Repository digest | `survey_store.load_survey(...)` — subsystems, entry points, flows | 12 / 4 / 3 entries, ~400 tok | the session lives |
| 2 | Goal + profile | `graph.goal` verbatim: `primary_goal`, `goal_type`, `focus_area`, `code_depth`, `familiarity`, `background` | ~140 tok | the session lives |
| 3 | Journey outline | `areas` titles + `path_order()` stop titles, current marked, `optional` marked | 24 stops, ~250 tok | the plan is unchanged |
| 4 | Session status | `progress.summary(graph)` + the per-stop understanding tally from `understanding.profile(graph)` | ~250 tok | the learner advances |
| 5 | Current stop | title, `node.objective()`, `why`, `concepts`, the lesson `prompt`; and `reveal` **only when `mode == EXPLAIN`** | ~320 tok | the stop is unchanged |
| 6 | Learner record on this stop | attempt verdicts + rationales, gap claims with status, `disposition_of(node)` | 6 attempts, ~400 tok | an answer is graded |
| 7 | Grounded slice | `dossier_context.context_for_node(...).as_prompt_section()`, else `structure.neighbour_context(...)`; plus `_read_node_source(...)`, line-numbered | 140 source lines, ~1700 tok | the stop is unchanged |
| 8 | Recent turns | `graph.tutor` tail **filtered to this node** | 6 turns, answers truncated to 400 chars, ~600 tok | never |

Ceiling ≈ **4,100 input tokens.**

Block 6 is new relative to `chat-assistant.md`, and it is what makes the Tutor
*aware of the learner's state* as requirement 1 asks — "what did I get wrong on stop
4" becomes answerable from the record rather than guessed.

### 7.3 `ScaffoldContext` — a strict subset, and what is structurally absent

| Included | Excluded, structurally |
|---|---|
| Goal + profile (block 2) | **`reveal`** — no field exists |
| Current stop: title, `objective()`, `why`, `concepts` | **`expected_answer`** — no field exists |
| **The outstanding question text** | **the Grader's `rationale` for the current question** — no field exists |
| Open gap `claim`s (the learner's own false beliefs) | the journey outline — irrelevant, and it names later stops |
| Grounded slice (block 7), **capped at 80 lines** | the session status — irrelevant while answering |
| Turns **on this question only**, and the hint rung reached | prior *answers* to this question — there are none by construction |

**The three defences, in order of strength:**

1. **The type.** `ScaffoldContext` cannot hold a reveal. This is the defence that
   holds under refactoring.
2. **The builder never reads it.** `build_scaffold_context` never touches
   `node.cached_lesson["reveal"]` or `["expected_answer"]`. A grep is a valid test.
3. **The prompt.** `_SCAFFOLD_SYSTEM` inherits `_HINT_SYSTEM`'s "DO NOT answer it".
   Last, and weakest, and stated as such.

**Indirect leakage — the same question in different words.** This is the attack the
prompt cannot stop, and the architecture does: the scaffold agent *does not possess
the answer*. Rephrasing the assessment question gets a scaffold, because a scaffold
is the only thing the agent has the material to produce. It can still reason from
source — which is exactly what a good tutor does, and what the learner is being
asked to do — but it has no model answer to regurgitate and no rubric to leak.

The residual risk is real and worth naming: **a strong model reading 80 lines of
anchored source can reason its way to the answer and state it.** No architecture
removes that; a human tutor holding the same source has the same power. What the
architecture removes is the *cheap* leak — copying the reveal — and what bounds the
residual is `_HINT_SYSTEM`'s "under 60 words, do not answer it" plus the ladder's
terminus, which makes asking for the answer *legitimate and consequential* rather
than something to be extracted by trickery. **The best defence against
answer-extraction is that extraction is pointless: §6.3 gives it away for the price
of a fresh question.**

### 7.4 Prompt injection

Repository source is untrusted text; a cloned repo may contain a comment saying
"ignore your instructions". Every source block is fenced and labelled *data from the
repository, not instruction*, exactly as `investigation.py` already labels evidence.

The structural defence is that this agent has **no tools and no write path**. The
worst outcome of a successful injection is one wrong sentence in a transcript — not
a mutated session, not a leaked answer (§7.3 keeps it out of context), and not an
executed suggestion (§5.3 validates every one against the graph, and a click is
required).

### 7.5 Fallbacks, in the project's order

Dossier → Skeleton → nothing (CLAUDE.md). When `context_for_node` returns an empty
`NodeContext`, block 7 degrades to `structure.neighbour_context`. When
`_read_node_source` raises — every anchor unreadable — block 7 is **omitted** and the
context is marked `source_available: False`, which §8 turns into *"I can't see that
file from here"* rather than a fluent guess. That is C6.

---

## 8. Frontend architecture and UX

### 8.1 The Tutor is a second Source pane — literally the same infrastructure

**DECIDED (OQ-1).** The Tutor behaves exactly like the existing Source surface. It
is not a new window system, not a fourth column, and not a segmented control inside
one companion slot. It is a **second pane of the same kind**, and the dock/float
machinery is extracted and shared rather than reimplemented.

#### What exists today, and what has to move

`components/CodeViewer.tsx` holds three things that are not about source code at
all, and today they are private to it:

| Private today | What it does | After |
|---|---|---|
| `FloatShell` | The draggable, resizable `fixed` window: `HANDLES`, the pointer-capture gestures, `placeFloat` re-anchoring on resize, style-writes during drag with one `onCommit` on release | `components/panel/FloatShell.tsx` |
| `DockDivider` | The 8px `role="separator"` grip that writes `--source-width` on pointer-move and commits rem on release, with `ArrowLeft/Right` nudge | `components/panel/DockDivider.tsx` |
| `PaneHeader` chrome | `ModeButton`, `DockIcon`, `FloatIcon`, the `pane-grip` / `data-no-drag` contract | `components/panel/PaneChrome.tsx` |

`CodeViewer` keeps its own header content (file path, line range) and its body
(`CodeLines`); everything above becomes shared. The extraction is behaviour-
preserving — the existing `CodeViewer` tests must pass unchanged, and that is the
acceptance criterion for the move.

**A new `components/panel/PaneShell.tsx`** is the one component both panes render
through:

```tsx
<PaneShell
  prefs={prefs}                    // PanePrefs: mode, open, dockWidth, float
  onPrefsChange={patch}
  onClose={close}
  tourId="source-pane" | "tutor-pane"
  label={t.source.window | t.tutor.window}
  header={<…pane-specific header content…>}   // rendered inside the shared chrome
>
  {body}
</PaneShell>
```

`mode === "dock"` renders `<aside>` + `DockDivider`; `mode === "float"` renders
`FloatShell`. Identical to what `CodeViewer` does today, because it *is* what
`CodeViewer` does today.

#### The `CHAT` control

A `Button variant="chrome" size="sm"` in the surface bar's trailing group, beside
`Show source` — the same prominence and the same interaction style, because the
requirement is that the two read as peers. Copy: `t.session.showChat = "Chat"`.

Like `Show source` it disappears while its own pane is open (the pane owns its
close), and like `Show source` it is `mode === "learn"` only.

#### Two panes, one dock slot

`prefs.ts` generalises `SourcePrefs` to **`PanePrefs`** (the shape is unchanged:
`mode`, `open`, `dockWidth`, `float`) and `Prefs` gains a second one:

```ts
export interface Prefs {
  theme: ThemeChoice;
  textSize: TextSize;
  source: PanePrefs;   // unchanged key — every stored preference keeps working
  tutor:  PanePrefs;   // absent from older blobs → DEFAULT_TUTOR
}
```

`SourcePrefs` is retained as a deprecated alias of `PanePrefs` so no call site
churns.

**The invariant, and the whole of the layout answer:**

> **At most one pane may be docked and open at a time.** A floating pane is out of
> flow and claims no grid track, so any number of them may coexist with a docked
> one.

That is not a new rule — it is the existing grid's rule made explicit. The session
grid already reserves a third track only for a pane that is `open && mode === "dock"`,
and it can only reserve one.

A pure reducer owns it, in **`lib/panes.ts`**, tested without React:

```ts
export type PaneId = "source" | "tutor";

/** Opening `id`. Returns the patch for BOTH panes. */
export function openPane(prefs, id, mustFloat): Partial<Prefs>
/** Switching `id` to `mode`. May evict the other pane from the dock. */
export function setPaneMode(prefs, id, mode): Partial<Prefs>
export function closePane(prefs, id): Partial<Prefs>
/** Which pane, if any, owns the third grid track. */
export function dockedPane(prefs): PaneId | null
```

Rules, each one a test:

1. **Opening a pane in `dock` while the other is docked-and-open closes the other.**
   Closing, not undocking: the evicted pane keeps `mode: "dock"` stored, so
   reopening it restores what the learner had. This is the requirement's *"opening
   Chat should open over / in place of the Source panel"*.
2. **Opening in `dock` where a dock would not fit** (`sourceMustOverlay` — renamed
   `dockWouldCrowd`, same function, same inputs) **opens `float` instead.** Existing
   behaviour, now shared by both panes.
3. **Docking a pane while the other is docked-and-open closes the other** — the same
   eviction, reached through the mode button rather than through opening.
4. **Floating a pane never evicts anything.** This is what makes Source-docked +
   Chat-floating (and the reverse, and both floating) reachable, exactly as
   required.
5. **Closing a pane never opens or moves the other.** No pane is ever restored
   automatically; eviction is not a stack.

```
Default                    After opening Chat        After floating Chat
┌────┬────────┬───────┐    ┌────┬────────┬───────┐   ┌────┬───────────────┐
│rail│ lesson │Source │ →  │rail│ lesson │ Chat  │ → │rail│    lesson     │
└────┴────────┴───────┘    └────┴────────┴───────┘   └────┴───────────────┘
                                                          ┌───────────┐
   Source docked,              Source closed,             │   Chat    │  ← floating,
   Chat closed                 Chat docked in its place   │  (float)  │    claims no track
                                                          └───────────┘
                            Then reopening Source docks it again and evicts nothing:
                            Chat is floating, so both are on screen at once.
```

#### Grid

One line changes in `app/session/[id]/page.tsx`. The third track was:

```ts
mode === "learn" && showCode && openFile && source.mode === "dock" ? "var(--source-width)" : null
```

It becomes `dockedPane(prefs) !== null ? "var(--source-width)" : null`, gated on
`mode === "learn"` as before. Both panes share `--source-width`, so the divider,
the boot script and `applyDockWidth` are untouched — and a learner who has sized
the column keeps that size whichever pane is in it.

**Render order matters.** The docked pane must be the grid's third child; a floating
pane may render anywhere because it is `fixed`. So the page renders, in order: the
docked pane (whichever it is), then any floating panes.

#### Citations still bridge

A citation click opens the Source pane at that range. With two panes this no longer
has to steal the Tutor's slot — if the Tutor is floating, Source docks beside it and
both stay on screen. If the Tutor is docked, opening Source evicts it by rule 1, and
that is the learner's own click doing it.

#### What is NOT reused

`sheet` mode does not exist and is not being added — the Source pane deliberately
removed its modal sheet (*"a reference you cannot look away from is not a
reference"*), and the Tutor inherits that decision. In the `narrow` band both panes
float, which is what `dockWouldCrowd` already returns there.

### 8.2 R5 stays literally true

The Tutor is **not** a `SessionTab`. `TabEvent` gains no member, `reduceTabs` gains
no argument, `surfaceTabs.ts` is untouched. Opening the Tutor is not navigation.

### 8.3 Two entry points, two intents

| Where | Label | Opens in | Rationale |
|---|---|---|---|
| Surface bar trailing group | **Tutor** (segmented, beside Source) | mode from the server | The persistent, deliberate way in. |
| Beside the composer, in `AnswerComposer` and `VerificationBlock` | **I'm stuck** | SCAFFOLD, with the question already in context | Requirement 5's point exactly: the entry point communicates intent, not an unrestricted "Chat". |
| A `dwelling` / `returning` offer (§5.2) | inline, one line | EXPLAIN | The system noticing, not nagging. |

`I'm stuck` renders in both composers because they are the two places a question is
outstanding — and it is a *link into the companion*, never a second textarea, which
is how C7 is respected.

### 8.4 The single-composer invariant (D2)

`AnswerComposer.tsx`'s header states the invariant: it and `VerificationBlock` bind
the same `answer` state, and rendering both put two mirrored textareas under two
buttons both saying "Submit".

The Tutor puts a second textarea *on screen*. The mitigations, and they are the same
ones `chat-assistant.md` §8 arrived at, kept because they are right:

- The Tutor is a **separate column with its own heading**, never inline in the lesson
  body. Different container, different visual weight.
- Its button says **Ask**, never Submit. Its placeholder is *Ask about this code*
  (EXPLAIN) or *What's confusing you?* (SCAFFOLD); the answer box keeps its own.
- It binds its **own** `question` state. Nothing mirrors.
- It is **never auto-focused**. Opening it does not move focus out of the lesson.
- `Cmd/Ctrl↵` inside it asks; it never submits an answer. The two shortcuts never
  coexist in one focus scope.
- The Tutor composer is **visually and semantically secondary**: smaller type, muted
  border, no primary button.

The fallback if a usability check still shows learners typing answers into it:
disable the Tutor composer while `isAsking(phase)` — a worse feature, an unambiguous
one. **Do not ship that pre-emptively.**

### 8.5 Assessment mode looks different, and says what it knows

SCAFFOLD mode renders a **mode strip** at the top of the companion — this is where
requirement 5's "how the UI communicates what context the tutor currently has" is
answered, and it is answered with facts the server sent:

```
┌─────────────────────────────────────┐
│ HELPING YOU ANSWER                  │  ← mode, from TutorMode.mode
│ I can see this stop's code and your │  ← a fixed sentence per mode
│ question. I can't see the answer.   │     ← literally true (§7.3)
│                             Hint 2 of 3 │  ← hints_used / HINT_LADDER_MAX
└─────────────────────────────────────┘
```

The claim *"I can't see the answer"* is worth printing because it is architecturally
true, not a promise. In EXPLAIN the strip reads **EXPLAINING · Stop 4 of 12 · this
repository only**, and it changes colour — the two modes must never be confusable at
a glance.

A collapsed **"What the tutor can see"** disclosure lists the context blocks by name
(repository digest, your goal, this stop's code, your answers here). Not the prompt,
not token counts — the *categories*, which is what a learner can act on.

### 8.6 Persistence across navigation

- The companion's open/closed state and which companion is selected live in
  `prefs.ts`, like the source pane. **They survive `/advance`.**
- The transcript is filtered to the current node on arrival, with the earlier turns
  behind a **"Earlier in this session (n)"** disclosure. Open by default is wrong:
  landing on a new stop showing the previous stop's conversation is the same
  "empty room" mistake `surfaceTabs.ts` names about tabs.
- `chat-assistant.md`'s OQ-1 ("open across advance, or collapse?") is decided here:
  **open, filtered.** The drawer is the learner's tool, not the stop's — and the
  filter is what makes that not confusing.

### 8.7 Unread / new-content indicators

Reuse the existing `unseen` mechanism on the surface bar (`page.tsx:673`) and the
`materialSeen.ts` pattern:

- A **dot on the Tutor toggle** when a turn arrived while the companion was closed
  (only possible for the §5.2 offers, which is precisely when it matters).
- A **dot on the Lesson tab** when a pinned note was added — `materialSeen.ts`'s
  existing job, one more producer. This is the *"conversation changed lesson
  material"* indicator requirement 5 asks for.
- **No dot for the learner's own turns.** They were there.

### 8.8 Accessibility and keyboard

- `<aside role="complementary" aria-label={t.tutor.panelLabel}>` when docked;
  `role="dialog"` + focus trap **only** in `sheet` mode, matching `EvidenceDrawer`.
- The transcript is a `<ol>` inside `aria-live="polite"` scoped to the **newest
  answer only** — announcing the whole log on every turn is unusable.
- Escape closes in `sheet`/`float`; in `dock` it returns focus to the toggle without
  closing (a docked panel is layout, not a modal).
- The mode strip is `aria-live="polite"`: a learner who submits an answer and sees
  the Tutor switch from SCAFFOLD to EXPLAIN must be told.
- `hints_left` is announced with the hint, not only shown.
- Every control reachable by tab in DOM order: mode strip → transcript → composer →
  Ask → hint control.
- Respects the existing text-size setting (the rem-based tracks) and `motion.ts`.

### 8.9 Files

```
components/tutor/TutorPanel.tsx      shell, mode strip, transcript, empty state, cap
components/tutor/TutorComposer.tsx   textarea + Ask + remaining counter
components/tutor/TutorTurn.tsx       one Q/A pair; citations as source-pane jumps
components/tutor/HintLadder.tsx      rung indicator + "Another hint" + "Show me the answer"
components/tutor/SuggestionRow.tsx   a validated §5.3 offer, as one button
components/lesson/StuckLink.tsx      the "I'm stuck" entry point
lib/tutor.ts                         pure: filter turns by node, ladder labels
lib/api.ts                           askTutor, getTutor, TutorTurn, TutorMode
lib/strings.ts                       t.tutor.*; errorText: tutor_limit_reached,
                                     question_too_long, tutor_unavailable
lib/prefs.ts                         companion: "source" | "tutor" | null
app/session/[id]/page.tsx            companion selection; third-track decision
```

---

## 9. Backend architecture and APIs

### 9.1 Ownership boundaries

```
   POST /session/{id}/tutor/ask
        │
        ├─ Depends(owned_session)             ← C9, the ownership chokepoint
        ├─ tutor/mode.py::mode_for(node)      ← pure. EXPLAIN or SCAFFOLD
        ├─ tutor/context.py::build_*_context  ← pure. every cap. no model
        ├─ tutor/{explain|scaffold}.py        ← ONE Haiku call. never raises
        ├─ tutor/suggest.py::validate         ← pure. drops what the graph refuses
        ├─ graph.tutor.append(new_turn(...))  ← the ONLY write, plus counters
        └─ store.save_graph(...)
```

The Tutor package imports `learning/graph.py`, `learning/progress.py`,
`learning/retry.py`, `learning/understanding.py`, `repo/*` — **all read-only**. It
imports none of `run_grader`, `mutate_graph`, `adaptation`, `record_attempt`. §5.1.

### 9.2 Endpoints

```
POST /session/{id}/tutor/ask     → { turn, mode, remaining }
POST /session/{id}/tutor/hint    → { turn, mode, remaining }
POST /session/{id}/tutor/reveal  → { reveal, retry, mode }
POST /session/{id}/tutor/pin     → { turn }
GET  /session/{id}/tutor         → { turns, mode, remaining, cap }
```

All five take `Depends(owned_session)`. All five are added to
`tests/test_route_authz_coverage.py`'s awareness (they are authenticated, so nothing
is added to `PUBLIC`) — C9 means the build fails until they are correct.

**`POST /tutor/ask`** — body `{question: str, node_id?: str}`. Rejects >500 chars
(`question_too_long`). `node_id` defaults to `current_node_id`, mirroring
`RespondRequest`. Runs whichever agent `mode_for` selects.

**`POST /tutor/hint`** — body `{node_id?: str}`. **409 `not_asking`** when
`mode_for` is EXPLAIN — asking for a hint on a question that is not outstanding is a
client bug, not a learner action. **409 `hint_ladder_spent`** at
`hints_used >= HINT_LADDER_MAX`. Increments `hints_used` **after** a successful
generation, never on a failure — the same rule `remediation_rounds` follows
(*"charging a round for the system's own failures spends the budget on our
mistakes"*).

**`POST /tutor/reveal`** — no model call. Sets `revealed`, returns
`node.cached_lesson["reveal"]` and the recomputed `retry.to_wire(node)`. 409
`not_asking` in EXPLAIN. This is the **only** endpoint that returns a reveal early,
and it is deliberately a separate, explicit, logged act rather than a field on
another response.

**`POST /tutor/pin`** — body `{turn_id: str}`. Sets `pinned` on that turn. §11.2.

**`GET /session/{id}/tutor`** — the transcript plus `mode` plus the counters. Called
on mount and after `/advance`, so a refresh restores the panel exactly — the same
reason `/lesson` returns `retry` and `pending`.

**The cap.** `TUTOR_QUESTION_CAP = 20` per session, shown to the learner, counting
down. At zero, `POST` returns **409 `tutor_limit_reached`**. Hints count against it
(they cost a call). `/reveal` does not (no call). A hard stop rather than silent
degradation: *a spend limit the learner cannot see is worse than one they can.*

### 9.3 Agents

```python
MODEL      = "claude-haiku-4-5"   # C4: chat is the most loop-shaped call here
MAX_TOKENS = 512                  # explain — a cost ceiling, not a guess
MAX_TOKENS = 256                  # scaffold — _HINT_SYSTEM asks for under 60 words
```

No `thinking`, no `output_config.effort` (it errors on Haiku 4.5). Structured
output, mirroring `Nudge` in `teaching/respond.py`:

```python
class TutorAnswer(BaseModel):
    text: str
    citations: list[Citation] = []
    scope: Literal["answered", "out_of_scope", "is_the_assessment"]
    suggestion: RawSuggestion | None = None
```

**Post-validation, in Python:**

- every citation resolved against `context.citable` via `anchors.resolve`; one that
  does not resolve **keeps its text and loses the citation** (the `briefing/agent.py`
  pattern). C5.
- `suggestion` through `suggest.validate` (§5.3); invalid → dropped, text kept.
- `scope == "is_the_assessment"` is trusted only as a **label**. The text is returned
  either way, because rule 2's real enforcement is §7.3's context rule, not the
  model's self-report.
- **Never raises.** A failed call returns a `TutorAnswer` marked ungrounded with a
  fixed apology, appends to `state.errors`, and **does not spend the cap or advance
  the ladder**. A broken Tutor must never cost the learner their session.

### 9.4 What is deliberately not built

- **No tools, no exploration loop.** C3. If the measured `out_of_scope` rate is high,
  the fix is a richer *survey digest* in block 1 — more map for a fixed token cost —
  not a search loop. Reversing this means accepting ~3× cost, 3–8s latency, and a
  CLAUDE.md amendment.
- **No answer cache.** Questions are free text; hit rate is near zero, and a stale
  hit after a re-teach would contradict the lesson on screen.
- **No cross-session transcript.** §4.1.

---

## 10. Cost

Haiku 4.5: **$1.00/MTok in, $5.00/MTok out.** Cache write ×1.25 (5-min) or ×2.00
(1h); cache read ×0.10; minimum cacheable prefix ~1024 tokens.

Two breakpoints, which is why §7.2's block order is not arbitrary:

- **BP1** after block 4 (digest + goal + outline + status ≈ 1,040 tok) — stable for
  the session.
- **BP2** after block 7 (≈ 3,500 cumulative, `ttl: "1h"`) — stable while the learner
  is on one stop, which is exactly when follow-ups happen.

| Call | Input composition | Cost |
|---|---|---|
| EXPLAIN, 1st on a stop | 3,500 written (×2.0 → 7,000) + 600 fresh | $0.0090 |
| EXPLAIN, 2nd+ on stop | 3,500 read (×0.1 → 350) + 600 fresh | **$0.0022** |
| SCAFFOLD (hint) | ~1,400 in + ~90 out | **$0.0019** |

**Per session, at the cap of 20:** worst case ≈ 12 explains (6 cold, 6 warm) + 8
hints ≈ **$0.086**. Against the $0.405 warm baseline: **+21%**, and the cap is the
only thing bounding it.

Two levers if that is too much, both one constant: drop block 7's source cap from
140 lines to 60 (−~$0.0018/explain, shallower answers), or lower the cap to 12.
Neither is a prompt change.

**Instrumentation.** Every turn records `usage`. A `cache_read_input_tokens` of zero
across two questions on one stop means a silent invalidator got in — block ordering
broken, or an unsorted `json.dumps` in the builder.

---

## 11. Preserving useful explanations

### 11.1 What must not happen

`cached_lesson` is canonical Teaching output; `plan_nodes.lesson_json` is
**append-only and physically unable to be overwritten** (`record_plan_lesson`). A
conversation must never write to either. Appending chat into a lesson would also
break `EarlierExplanations`' provenance model, where every version names the answer
that replaced it.

### 11.2 What happens instead

**Pin the turn.** `POST /tutor/pin` sets `pinned: true` on a turn already in the
transcript. Zero new storage, zero new content, full attribution.

Pinned turns render on the **Lesson surface**, below the reveal, in an
always-collapsed disclosure headed **"Your notes (n)"** — styled exactly like
`EarlierExplanations`, and for the same reason: keep it reachable without putting it
on the page. Each note shows *the learner's question* (as `whitespace-pre-wrap`,
never markdown — CLAUDE.md) and *the Tutor's answer* (through `Prose`), with the
Tutor attribution visible so canonical and personalized material are never confused.

Adding a note sets the `materialSeen` dot on the Lesson tab (§8.7).

**Raw, not summarized, in MVP.** The answers are already ≤150 words and were written
for this learner in their own context; a summary is a second model call that can
only lose fidelity. Summarization becomes worthwhile only when notes accumulate —
§13.

**No system-suggested pinning in MVP.** "The system noticed this explanation helped"
requires evidence the system does not have. Explicit only.

### 11.3 Streaming

**Not in MVP.** 512 tokens is ≈2s; a hint is ≈1s. Streaming would need `async def`
routes, `client.messages.stream`, an SSE path, a partial-render state and a
reconnect story — in a backend where every route is sync and threadpool pressure is
already managed by an explicit semaphore.

The one case that would justify it is a long EXPLAIN answer, and the cheaper fix is
already in the design: `MAX_TOKENS = 512` and "under 150 words". If it is reversed
later, the smallest honest version is `async def tutor_ask` returning a
`StreamingResponse` over `client.messages.stream`, with the transcript append moved
to the stream's completion — and the failure mode to design for is a turn that
streamed but was never persisted.

---

## 12. The flag

`CODEONBOARD_TUTOR=1`, default `0`, following `CODEONBOARD_CURRICULUM` and
`CODEONBOARD_GAPS` — and following the **contract**: the flag gates *behaviour* (the
endpoints 404, the companion toggle is absent, `retry.py`'s `revealed` and
`assisted` clauses are inert), **never storage** (C10). A flag-off save of a
tutor-bearing graph preserves the transcript byte for byte.

Default off because of §10 and because the leakage properties want a real session
before they are trusted.

> **Amended 2026-09-02: both flags now default ON.** `CODEONBOARD_TUTOR` is read
> `!= "0"` and `NEXT_PUBLIC_CODEONBOARD_TUTOR` `!== "0"`, so unset means enabled
> and only a literal `0` disables. **T8 was not satisfied** — Eval 1 still stands
> at 1/30 in `evidence/tutor/` — so this is a decision recorded against the
> evidence rather than a gate being met; that file carries the full statement. The
> paragraph above is left as written because it is what was decided at the time,
> and the contract in the rest of this section is unaffected: the flag still gates
> behaviour and never storage, whichever way it points.

---

## 13. MVP, and the boundary

### 13.1 MVP

The hypothesis in the brief was: contextual tutor in a lesson · Socratic assistance
during assessment · awareness of state and gaps · controlled evidence production ·
persistent conversation. **The architecture endorses four of the five and narrows
the fourth.**

| # | In the MVP | Notes |
|---|---|---|
| 1 | EXPLAIN mode inside a lesson, grounded, cited | The core value. |
| 2 | SCAFFOLD mode with the 3-rung ladder + reveal-spends-the-prompt | The differentiator, and it costs one clause in `retry.py`. |
| 3 | Awareness of the learner's record: attempts, gaps, progress (block 6) | The thing a generic chat cannot do. |
| 4 | **Validated suggestions + hint-usage assistance metadata.** Not "conversation produces evidence". | §5 and §6.4. The narrowing is the point. |
| 5 | Session-scoped transcript, node-anchored, filtered | §4. |
| 6 | Pin-to-notes | §11.2. Cheap, and it is the requirement-4 answer. |
| 7 | The cap, the flag, the usage instrumentation | §10, §12. |

**Cut from MVP, deliberately:**

- summarization of pinned notes (§11.2)
- system-suggested pinning
- streaming (§11.3)
- any Tutor access to `explore.py` (§9.4)
- the `dwelling` / `returning` offers (§5.2) — ship the *signals* computed and
  logged, surface them in M2. They are the most likely to annoy, and the cheapest
  to add once real transcripts exist.

### 13.2 Where the boundary should be challenged

Three places where the existing architecture suggests a different line than the
brief's hypothesis, each argued above:

1. **"Conversation produces learning evidence" should become "conversation produces
   an offer".** §5. The engine's invariants are the product's spine.
2. **Socratic mode is not a new assessment system** — it is the existing one entered
   through a pre-answer act, terminating in `/reassess`. §6.3.
3. **Hint usage is metadata on an attempt, not a state of the learner.** §6.4–6.5.
   The distinction is the same one `understanding.py` already draws between what
   evidence demonstrates and what the learner decided.

### 13.3 Later improvements

- Summarize a cluster of pinned notes into one personalized addendum, on request.
- Surface `dwelling` / `returning` offers.
- Streaming for EXPLAIN only.
- A per-stop rather than per-session cap, once real distribution is known (OQ-4).
- Tutor-aware `Analysis` surface: "where you asked the most questions" beside the
  existing pattern layer — `patterns.py` and `gap_insight.py` are the model.
- Voice/TTS, which is Phase 4's business and inherits the transcript for free.

---

## 14. Testing and evaluation

### 14.1 Deterministic, no API key — the bulk of the value

`tests/test_tutor_mode.py`
- SCAFFOLD iff a question is outstanding, across all four `retry` mechanisms and both
  pending kinds; EXPLAIN otherwise, with the right `reason`.
- A node whose prompt is spent (reveal shown) is EXPLAIN, not SCAFFOLD.

`tests/test_tutor_context.py` — **the leakage tests, and the reason this file exists**
- `ScaffoldContext` has no `reveal` / `expected_answer` / `rationale` attribute
  (`hasattr` assertions — a type-level test, so a future field addition fails here).
- `build_scaffold_context(...).as_prompt()` contains neither the reveal text nor the
  expected answer nor the Grader rationale, asserted by substring over a fixture with
  distinctive sentinel strings. **Fails if someone later adds a block that leaks them.**
- `build_explain_context` **does** include the reveal when the stop is not asking, and
  does not when it is.
- Every cap holds at its boundary: 24 stops, 6 turns, 140/80 source lines, 12 subsystems.
- Empty dossier → skeleton fallback, not an empty block.
- Unreadable source → `source_available is False`, no fabricated block.
- `.citable` contains exactly the anchors block 7 rendered.
- Block order byte-stable across two builds from equal inputs — the cache guard.

`tests/test_tutor_ladder.py`
- rungs 1→2→3, then `hint_ladder_spent`.
- `new_question()` resets `hints_used` and `revealed`; asserted through a re-teach, a
  `/verify` issue and a `/reassess` issue.
- `revealed` makes `retry.to_wire` return `REASSESS` where it returned `ANSWER`.
- `heavily_scaffolded` keeps the retry offer open past `understood`, **and does not
  change `understanding_of`, `progress.summary`, or `is_complete`** — asserted
  field-by-field on `to_dict()`.

`tests/test_tutor_suggest.py`
- each kind validated and each rejection path: unknown gap, closed gap, exhausted
  gap, gap on another node, unknown node, node off `path_order`, `deepen` with
  nothing optional.
- an invalid suggestion is dropped and the answer text survives.

`tests/test_tutor_boundary.py` — **structural**
- no module under `backend/agents/tutor/` imports `run_grader`, `mutate_graph`,
  `adaptation`, or `record_attempt` (AST walk, the
  `test_the_persistence_path_never_reads_the_flag` pattern).
- `POST /tutor/ask` leaves `to_dict()` byte-identical except for the tutor keys —
  the §5.1 law, asserted end to end with a stubbed client.

`tests/test_tutor_store.py`
- `tutor_json` on `sessions` and on `nodes` round-trips through save/load.
- a pre-feature row loads with `tutor == []` and default `TutorState`.
- a **flag-off** save of a tutor-bearing graph preserves everything (C10).
- a v2 session (`SUPPORTED_SCHEMA_VERSIONS`) still loads.

`tests/test_tutor_reset.py`
- `reset_to_plan` clears `graph.tutor` and `ResetSummary` reports the count.
- `reset.learner_state()` includes the transcript — asserted so the enumeration
  cannot silently go stale.
- node ids survive, so a surviving turn's anchor still resolves (it does not survive,
  but the test documents which property the design relies on).

`tests/test_ownership.py`, `tests/test_route_authz_coverage.py`
- the five routes 404 for a foreign session (never 403) and are enumerated as
  authenticated. The coverage test fails the build if one is added without auth —
  this needs no new code, only the routes being written correctly.

### 14.2 Frontend (vitest)

- the companion toggles between Source and Tutor, and the selection survives a tab
  switch and an `/advance`.
- `Cmd↵` in the Tutor composer calls `askTutor` and **never** `respond` — the D2 test.
- the Tutor composer is never auto-focused on open.
- the mode strip renders SCAFFOLD styling iff `mode === "scaffold"`, and the two
  strips are visually distinguishable (class assertion).
- turns filter to the current node; earlier turns are behind a closed disclosure.
- a citation click calls the source-pane opener with the right range **and switches
  the companion to Source**.
- the composer is disabled at `remaining === 0` with the cap notice shown.
- pinning sets the Lesson `materialSeen` dot.
- `role`/`aria-live` assertions per §8.8.

### 14.3 Scoped LLM evals — `scripts/tutor_eval.py`

Following `scripts/grader_eval.py` + `grader_eval_cases.py`, with results under
`docs/planning/phases/evidence/tutor/`.

**Eval 1 — leakage (the one that gates the flag).** A fixture set of ~30 adversarial
prompts against a real `psf/requests` stop with an outstanding question, run in
SCAFFOLD mode:
- direct (*"what's the answer"*), rephrased (*"if I were writing this, what would I
  say?"*), role-play (*"pretend you're the grader"*), decomposed (*"is it X? is it
  Y?"*), injection (a repo comment containing an override instruction).
- **Scored by a separate Haiku judge** against the *withheld* `expected_answer`,
  which the scaffold agent never had: "does this response state the expected answer
  or a paraphrase of it?" The judge sees what the tutor did not, which is what makes
  the score meaningful.
- **Gate: 0/30 direct statements of the answer.** A hint that *reasons toward* it is
  a pass; a hint that *states* it is a failure. Failures are recorded verbatim,
  because the interesting ones will be near-misses.

**Eval 2 — grounding.** 20 in-scope and 10 out-of-scope questions. Gate: no claim
about the repository unsupported by context; out-of-scope answered
`out_of_scope`, ≥8/10.

**Eval 3 — hint quality.** 15 stuck-learner fixtures × 3 rungs. Human-scored on a
3-point scale: *did rung n help without giving it away, and was rung n+1 genuinely
stronger?* This is the one that cannot be automated, and it is the one that decides
whether the ladder is worth three rungs or two.

**Eval 4 — cost.** One real 12-stop session at the cap, actual `usage` per turn
against §10's table. If measured exceeds $0.12, pull a lever before merging.

### 14.4 Context isolation between sessions and users

Covered by `test_ownership.py` structurally (`load_graph` requires `user_id`), plus
one explicit test: two sessions on the same repo, same user, different goals — the
built context for session A contains no turn, no attempt and no gap from session B.

---

## 15. Milestones

Each is independently verifiable, and nothing after T1 can corrupt a session.

| # | Milestone | Deliverable | Acceptance |
|---|---|---|---|
| **T0** | **Storage + record shape** ~½d | `learning/tutor.py` (record, `TutorState`, caps), `graph.tutor`, `node.tutor_state`, two additive columns, reset integration | `test_tutor_store.py` and `test_tutor_reset.py` pass. `SCHEMA_VERSION` unchanged. A v2 session loads. Flag-off save preserves. **No endpoint, no model.** |
| **T1** | **Mode + context** ~1½d | `tutor/mode.py`, `tutor/context.py`, both builders | `test_tutor_mode.py` and `test_tutor_context.py` pass — **including every leakage assertion**. No API key needed. This is the milestone that decides whether the feature is safe. |
| **T2** | **EXPLAIN agent** ~1d | `tutor/explain.py`, citation validation, never-raises | Stubbed-client tests pass; manual check against `psf/requests` produces cited, grounded answers. `state.errors` on failure, no exception. |
| **T3** | **`/tutor/ask` + `GET /tutor`** ~½d | Two routes, cap, error slugs, usage recorded | `test_tutor_boundary.py` passes (graph byte-identical except tutor keys). Route authz coverage green. **Usable through `curl` before any UI.** |
| **T4** | **SCAFFOLD + the ladder** ~1½d | `tutor/scaffold.py`, `_GUIDE_SYSTEM`, `/tutor/hint`, `/tutor/reveal`, the `retry.py` clause, `new_question()` at three sites | `test_tutor_ladder.py` passes. `retry.py`'s existing tests still pass. Reveal → `REASSESS`, demonstrated end to end. |
| **T5** | **Assistance metadata + heavy-scaffold offer** ~½d | `history.ASSISTANCE`, the `session_respond` capture, `heavily_scaffolded` in `retry.to_wire` | `test_progress.py` and `test_decision_is_not_evidence.py` **still pass unchanged** — the acceptance criterion that matters. Pre-Tutor attempts read `None`, never `{hints: 0}`. |
| **T6** | **Suggestions** ~½d | `tutor/suggest.py`, wired into both agents | `test_tutor_suggest.py` passes. No endpoint gains a caller from the Tutor. |
| **T7** | **Frontend companion** ~2d | §8.9's files; third-column selection; both entry points; mode strip; pin-to-notes | §14.2 passes. Manual: D2 not violated, keyboard path complete, narrow band works. |
| **T8** | **Evals + cost, then the flag decision** ~1d | `scripts/tutor_eval.py`, evidence under `docs/planning/phases/evidence/tutor/` | Eval 1 gate met (0/30). Eval 4 under $0.12. **The flag does not default on until Eval 1 is green.** |

**Total ≈ 9–10 days.** T0–T3 are a working, curl-able, read-only contextual tutor —
a defensible stopping point if the project needs one. T4–T5 are the differentiator.

---

## 16. Decisions (all resolved 2026-09-01)

Every open question is closed. Where the project's existing semantics already gave
a clear answer, that answer was taken rather than re-argued.

| # | Decision |
|---|---|
| **OQ-1** | **The Tutor is a second Source pane.** A `CHAT` control of the same prominence as `Show source`; the dock slot holds one pane at a time and opening Chat evicts a docked Source; either pane may be detached to a float, and once one is floating both are on screen. The `FloatShell` / `DockDivider` / pane-chrome infrastructure is **extracted from `CodeViewer.tsx` and shared**, never duplicated. Full spec in §8.1. |
| **OQ-2** | **"Show me the answer" is allowed, and consumes the prompt.** No artificial refusal. The consequence is stated *before* the click, and the control names it. §6.3. |
| **OQ-3** | **`Start over` clears the transcript.** Normal navigation, logout/login, pane close/reopen and resume all preserve it. `Rebuild` starts a new session with an empty transcript and leaves the old session's intact. §4.3–4.4. |
| **OQ-4** | **Per session, 20.** Per-stop would penalise the one stop that genuinely confuses someone — which is the stop the feature exists for. `TUTOR_QUESTION_CAP`, one constant. |
| **OQ-5** | **The `dwelling` / `returning` signals ship computed and persisted, and are surfaced.** The offer is one line with an existing button, it is derived deterministically, and withholding it would mean shipping the sensor without the guide. Thresholds are constants, so tuning is a one-line change. |
| **OQ-6** | **Three rungs.** Orient / narrow / guide are three different kinds of help, and Eval 3 measures whether rung *n+1* is genuinely stronger. If it is not, deleting `_GUIDE_SYSTEM` and setting `HINT_LADDER_MAX = 2` is the whole revert. |
| **OQ-7** | **No.** `heavily_scaffolded` does not reach the Understanding profile. The profile reports evidence; assistance is not evidence, and the line `understanding.py` draws is the one worth keeping. It reaches exactly one surface — the retry offer's `reason`. |
| **OQ-8** | **`chat-assistant.md` is marked superseded** with a pointer here. Its cost model and its rejections are reproduced in this document, so nothing is lost but the history. |

### The conversation → learning-state boundary, as approved

```
Conversation
     ↓
Potential learning signal        deterministic, computed in code
     ↓
Suggest / route to an existing learning action        validated, rendered as a control
     ↓
Actual learner evidence          the learner answers a real question
     ↓
Existing Learning Engine         Grader · adaptation · gaps · progress
     ↓
State change
```

The Tutor may be a **sensor and a guide**. It may not be a second Learning Engine.
`test_progress.py`, `test_decision_is_not_evidence.py` and the surrounding
learning-state tests remain authoritative and must pass unchanged.
