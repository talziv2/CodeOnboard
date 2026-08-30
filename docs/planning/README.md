# `docs/planning/` — design records

> **Read this before anything in here.**
>
> These are **design records, not descriptions of current behaviour.** Each was
> written to decide something, and each was written at a point in time. Several
> describe work that was deliberately **not** built. Where one disagrees with the
> code, **the code is right** — and the place to look for what the system does
> today is [`docs/architecture/`](../architecture/overview.md).

They are kept because the architecture documents state *what* the system does and
these state *why*, including the alternatives that were rejected and the
measurements that settled them. A decision you cannot see the argument for is a
decision the next person will re-litigate.

> Index: [docs/README.md](../README.md)

---

## Phases

Each document owns one workstream. The ones that most directly explain current
behaviour are marked ✔ — they are still the fullest argument behind a shipped
mechanism.

| Document | Subject | |
|---|---|---|
| [`roadmap.md`](phases/roadmap.md) | The end-to-end phase plan. **Its Phase-1/2 layer diagram is superseded** — it names a "Vector Database (RAG)" layer and a Prioritization Agent that do not exist, and calls the orchestration a plain Python chain where it is a compiled LangGraph | |
| [`repo-understanding.md`](phases/repo-understanding.md) | The migration from retrieval to exploration: Layers A/B/C, the six tools, the grounding oracle, the stage gates | ✔ |
| [`learning-engine.md`](phases/learning-engine.md) | Objectives, the objective-first planner, question forms, the response policy, curriculum sizing | ✔ |
| [`learning-graph.md`](phases/learning-graph.md) | The two progress measures, the understanding profile, the evidence hierarchy | ✔ |
| [`learning-loop.md`](phases/learning-loop.md) | Re-assessment, the retry dispatch, and why a decision is not evidence | ✔ |
| [`gap-model.md`](phases/gap-model.md) | Gaps: identity, lifecycle, blocking, verification, the caps | ✔ |
| [`multi-user.md`](phases/multi-user.md) | Accounts, ownership, the four-layer boundary, the decisions D-1…D-9 | ✔ |
| [`session-reset.md`](phases/session-reset.md) | The plan snapshot, and why `Start over` restores rather than inverts | ✔ |
| [`reassessment.md`](phases/reassessment.md) | Re-assessing the objective after a shortfall | ✔ |
| [`cost-optimization.md`](phases/cost-optimization.md) | What a run costs, and the open gap against the stated target | ✔ |
| [`ui-concept.md`](phases/ui-concept.md) · [`ui-direction.md`](phases/ui-direction.md) · [`ui-baseline.md`](phases/ui-baseline.md) · [`ui-implementation.md`](phases/ui-implementation.md) · [`ui-surfaces.md`](phases/ui-surfaces.md) | The interface redesign, up to the two-surface arrangement that shipped | ✔ |
| [`phase3.md`](phases/phase3.md) | The original design for the interactive learning graph. Largely shipped; the terminology has moved on | |
| [`grounding-repair.md`](phases/grounding-repair.md) | **Planning only.** Grounded grading, structural verification integrity, the property-claim safeguard and a `disputed` gap status are **not implemented** | |
| [`multi-language.md`](phases/multi-language.md) | **Planning only.** The sibling-adapter design for a second language. Not built | |
| [`chat-assistant.md`](phases/chat-assistant.md) | **Planning only.** Not built | |

---

## Evidence

[`phases/evidence/`](phases/evidence/) holds the committed output of the
measurement harnesses in [`scripts/`](../../scripts/README.md) — grader
evaluations, band calibration, the gap model's acceptance runs, cost
measurements, and the manual end-to-end journeys.

This is the evaluation of the system **as it stands**. The evaluation of the
architecture it replaced lives separately, in
[`project-archive/rag-migration/`](../../project-archive/rag-migration/), so the
two are never mistaken for each other.

---

## Vision

[`vision/proposal.md`](vision/proposal.md) and
[`vision/evaluation.md`](vision/evaluation.md) — the original project proposal and
the evaluation plan.

---

## Completed audits

[`open-source-readiness-plan.md`](open-source-readiness-plan.md) — the audit that
produced the current setup path. **Completed**; retained as a record of what was
checked and what was deliberately left out. Its references to a separate `RUN.md`
are historical: that guide has since been folded into the
[root README](../../README.md).
