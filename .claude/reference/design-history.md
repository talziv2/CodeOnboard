# Design history — where the argument lives, and what has already moved

> Read before proposing a change to how learning works. Most proposals have been
> considered before, and the reason one lost is usually the answer.
>
> Siblings: [`design-principles.md`](design-principles.md) ·
> [`state-ownership.md`](state-ownership.md) ·
> [`orchestration-model.md`](orchestration-model.md)
>
> For anything not covered here, ask the **architecture-historian** agent — it
> reads the whole corpus and returns the argument.

---

## 1. Where the argument for each domain is written down

| Domain | Current behaviour | The argument, and the rejected alternatives |
|---|---|---|
| Graph, units, objectives, planning | `docs/architecture/learning-engine.md` §1–3 | `docs/planning/phases/learning-engine.md` |
| Progress, understanding, evidence hierarchy | `learning-engine.md` §7–8 | `docs/planning/phases/learning-graph.md` §5 — six defects, the invariant, "why not atomic nodes", "why not `objective_parts`" |
| Retry, re-assessment, decision-vs-evidence | `learning-engine.md` §9 | `docs/planning/phases/learning-loop.md`, `reassessment.md` |
| Gaps, verification, caps | `learning-engine.md` §6 | `docs/planning/phases/gap-model.md` |
| Session lifecycle, reset, resume | `docs/architecture/session-lifecycle.md` | `docs/planning/phases/session-reset.md` |
| Ownership, accounts | `docs/architecture/auth.md` | `docs/planning/phases/multi-user.md` (D-1…D-9) |
| Agents, orchestration, model policy | `docs/architecture/agents.md` | `docs/planning/phases/roadmap.md`, `phase3.md` |
| Repository understanding, grounding | `docs/architecture/repository-understanding.md` | `docs/planning/phases/repo-understanding.md`; `project-archive/rag-migration/` for the measured comparison |
| Surfaces, what belongs where on screen | `docs/architecture/frontend.md` | `docs/planning/phases/ui-*.md` |
| Cost | — | `docs/planning/phases/cost-optimization.md` |
| Conversation as an instrument | — | `docs/planning/phases/tutor.md` — **planning only**, supersedes `chat-assistant.md` |

Planning documents are **design records**, not current behaviour. Several describe
work deliberately not built. They label claims `[FACT]` (verified, with a
citation) · `[REC]` · `[ASSUME]` · `[OPEN]` · `[DECIDED — id]`. Use the same
labels when adding to them, and **do not retcon a record** — write what shipped
and where it diverged.

---

## 2. Responsibilities that have already moved

Each of these was a defensible design that produced a specific failure. This is
the most useful history for a designer: it says what an arrangement *costs*, which
is what an argument to move it back would have to overcome.

| Moved | From → To | Because |
|---|---|---|
| The retry decision | four flags in the panel → `learning/retry.py` | every defect was a seam: a scaffold whose only usable button was unreachable; an exhausted gap offered and then refused as an error; one flag derived two ways and wrong on one |
| Readiness arithmetic | `LearningGraph.readiness()` → `learning/progress.py` | the frontend, the map and any later report must not each carry a version of it |
| Understanding state | a stored value read directly → derived by `understanding_of()` | a node reported mastery with two detected misconceptions open |
| Settlement of an assertion | a direct `understanding_state` write → `SETTLING_OVERRIDES` | an assertion is not a demonstration |
| Curriculum size | a sentence in the planner's prompt → `curriculum.select()` | keyed on a field nobody asked the user for, with no code checking it |
| Warm-up selection | chosen for the *node* → chosen for the *diagnosis* | proximity was being mistaken for diagnosis |
| Gap-kind vs classification | classification won → a named `gap_kind` outranks it | a learner said they did not know what a function signature was; the signal was discarded because the answer was also `off-topic` |
| Repository understanding | vector RAG → tool-driven exploration | measured; `project-archive/rag-migration/` |
| The plan | reconstructed on `Start over` → `plan_nodes`, written once | a plan rebuilt from a half-walked graph is not the plan |
| Provenance of a warm-up | inferred from topology → declared in `lesson_brief["origin"]` | the rail captioned nearly every planned stop "added after confusion". The structural rule survives only as a fallback for the 62 pre-`origin` sessions |
| `.env` precedence | `override=True` → plain `load_dotenv()` | a stale file beat a variable set on the command line |

---

## 3. Two patterns worth noticing in that table

**Facts move toward a single owner, and the move is usually triggered by a
disagreement rather than by a review.** Retry, readiness and understanding all
became one-owner after two derivations diverged in production. A design that
creates a second derivation is not caught by tests; it is caught by a learner
seeing the wrong thing.

**Provenance moves from inferred to declared.** The warm-up row is the clearest
case, and it runs *opposite* to what an observer of the code might conclude, since
the structural inference is still there for legacy data. Direction of travel
matters more than current shape when deciding where a new design should sit.
