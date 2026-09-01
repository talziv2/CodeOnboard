# State ownership — who is authoritative for what

> The state families, the flow that produces them, and the four kinds of
> transition. Read with [`design-principles.md`](design-principles.md).
> Siblings: [`orchestration-model.md`](orchestration-model.md) ·
> [`design-history.md`](design-history.md)
>
> Descriptive. Where this disagrees with the code, the code is right — every
> claim is anchored so the disagreement is findable.

---

## 1. Vocabulary

Narrower here than in ordinary use; `docs/architecture/learning-engine.md` §1 owns
the full form.

**Unit/node** one teachable claim anchored to real code · **Objective** the claim
the learner should be able to make afterwards, and the contract between Planner,
Teaching and Grader · **Area/chapter** grouping metadata on the session, not an
entity · **Journey/walk** the promised sequence: planned, non-optional units ·
**Required set** the planner's `required` units plus their dependency closure ·
**Gap** one *false claim the learner made* — not a topic, not a score ·
**Verification** a fresh question aimed at one named gap · **Re-assessment** a
fresh question aimed at the objective · **Detour/warm-up** a remedial unit,
excluded from both progress measures · **Settled** the learner has dealt with a
stop, in two strengths (§4).

---

## 2. What produces what

```text
REPOSITORY TRUTH          git clone --depth 1 → tree-sitter
  deterministic, no model repo/parser.py · repo/skeleton.py
        │                 └─ repo/anchors.py resolve(): file+symbol → range
        ▼                    the grounding oracle. A model never names a range.
REPOSITORY INTERPRETATION
  Layer B survey          repo/survey.py — goal-AGNOSTIC, cached per
                            (repo, commit), SHARED across users
  Layer C Dossier         repo/investigation.py — goal-SPECIFIC, per session.
                            The only exploration loop in the system (D1)
        ▼
PLAN                      planner proposes; curriculum.select() CUTS (D5)
  written once            → plan_nodes / plan_edges, written only by
                            create_session and record_plan_lesson (D16)
        ▼
GRAPH TOPOLOGY            nodes · edges(sequence|prerequisite|deeper) ·
  the only structural        priority · area_id · origin
  mutability              authored by the planner; changed afterwards only by
                            mutator.py and scope.py
        ▼
PROGRESSION               path_order() · next_in_path() · resume_point()
  derived from topology   "sequence first, else prerequisite"
        ▼
LESSON                    teaching/agent.py, cached on the node. Source re-read
                            AT LESSON TIME; all anchors unreadable ⇒ fail (D3)
        ▼
ANSWER                    one composer, one submit. `kind` selects which
                            question: assessment · verification · reassessment
        ▼
GRADING                   grader/agent.py → classification + gap_kind + named
  observation only          false claims. It observes; it does not decide (D14)
        ▼
LEARNER STATE             two independent channels (§3)
        ▼
ADAPTATION                adaptation.decide_all() — a pure table
        ▼
RESPONSE                  hint · followup → teaching/respond.py
                          reteach        → respond.py (replaces the lesson)
                          prerequisite   → mutator.py (the only structural one)
        ▼
REPORTING                 progress.summary() — the single computation;
  derived, cached           sessions.*_cached is a cache OF it
```

Cross-cutting: `learning/history.py` records the envelope — attempts,
interventions, journey events — so route changes stay explicable (DI-9).

---

## 3. The state families

| Family | Where it lives | Authority | Mutability |
|---|---|---|---|
| Repository truth | `data/repos/`, Skeleton | `repo/skeleton.py`, `anchors.resolve` (`anchors.py:68`) | rebuilt per commit |
| Repository interpretation | `repo_survey`, `investigation` | `repo/survey.py`, `repo/investigation.py` | cached per (repo, commit) / (session, commit) |
| **Plan** | `plan_nodes`, `plan_edges` | `create_session`, `record_plan_lesson` | written once (D16) |
| **Graph topology** | `nodes`, `edges` | planner → `mutator.py`, `scope.py` | mutable |
| **Learner evidence** | `attempts_json` (append-only), `gaps_json`, `understanding_state` | `understanding_of()` (`graph.py:200`) owns the derived answer | append + explicit state |
| **Learner disposition** | `user_override` | `override`, `continue_past`, `waive*` | never touches evidence |
| Session shape | `sessions.*_json` — areas, journey events, briefing, arrival | `api.py` + `record_journey_event` | mutable |
| Reporting | `progress.summary()` (`progress.py:306`); `sessions.*_cached` | `learning/progress.py` | derived; cache written from `summary()` |
| UI phase | client only | `frontend/lib/lessonPhase.ts` | not persisted, not learner state |

**Stored versus derived, stated exactly.** `understanding_state` is *the latest
recorded assessment* — what the Grader last concluded. `understanding_of(node)` is
*what the learner has demonstrated*, which also consults the gaps. Only the second
is ever reported.

*These placements are answers to DI-3's test given today's data, not rules.*
A designer re-runs the test; they do not quote the table.

---

## 4. `settled` has two strengths, deliberately

`graph.is_settled` (`graph.py:174`) — strict: `understood`, or an explicit
`SETTLING_OVERRIDES` intent. Input to `is_complete()`.
`progress.is_settled` — weak, coverage-shaped: visited, answered, or acted on.

They answer different questions and each docstring points at the other. A change
that "unifies" them is removing a distinction, not simplifying one.

**The two populations.** `core_nodes` (`progress.py:141`) = planned + `required` →
the denominator of goal readiness. `walk_nodes` (`progress.py:157`) = planned +
non-optional → the promised journey, the stop counter, and completion. Remedial
nodes are in neither.

---

## 5. Which kind of transition is this?

Mislabelling one is the most common design error here.

| Kind | Means | Owner | Persisted? |
|---|---|---|---|
| **Graph** | topology changed — a unit spliced in, a priority moved, an edge rerouted | `mutator.py`, `scope.py` | yes: `nodes`/`edges` |
| **Learner-evidence** | what has been demonstrated changed | Grader → `understanding_of()`, gap lifecycle | yes |
| **Learner-disposition** | what the learner decided changed | `override`, `continue_past`, `waive*` | yes: `user_override` |
| **UI** | what is on screen changed | `lessonPhase.ts` — STUDY · FEEDBACK · VERIFY · RESOLVED | **no** |

`lessonPhase` is presentation only: four named phases replacing sixteen
independent conditional blocks. It must not become an input to a learning
decision.

The one client-owned fact is `lib/materialSeen.ts` — *"have I looked at Lesson
since it changed"* — permitted because it is not a fact about understanding and is
not observable server-side. **Reading is guidance and never evidence.**
