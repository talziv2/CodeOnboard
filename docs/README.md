# CodeOnboard documentation

Everything here describes **the system as it is implemented now**, unless the
document says otherwise. Where a document and the code disagree, the code is
right — say so in a PR rather than leaving the disagreement standing.

---

## Getting started

| | |
|---|---|
| [Root README](../README.md) | What CodeOnboard is, how to set it up from a fresh clone, how to run it, and the first-run walkthrough |
| [Configuration reference](configuration.md) | Every environment variable, what it does, and what happens when it is wrong |
| [Testing](testing.md) | What to run before a PR, what each suite covers, and the two results that look like failures and are not |

---

## Architecture

Start with the overview; it links to everything else.

| | |
|---|---|
| [System architecture](architecture/overview.md) | Components, boundaries, dependency direction, process topology, external integrations |
| [Multi-agent architecture](architecture/agents.md) | The roster, what each agent receives and returns, orchestration, and where each decision is made |
| [Repository analysis](architecture/repository-understanding.md) | Layers A/B/C, the six tools, the exploration loop, grounding, and how repository evidence reaches a lesson |
| [Adaptive learning](architecture/learning-engine.md) | The learning graph, gaps and verification, the two progress measures, and how the next step is chosen |
| [Session lifecycle](architecture/session-lifecycle.md) | Creation, planning, the learning loop, resume, `Start over` versus `Rebuild`, completion |
| [Backend and API](architecture/backend-api.md) | Entry points, the endpoint surface, the four-layer auth boundary, error conventions |
| [Frontend](architecture/frontend.md) | Routing, the API layer, the derived view-model layer, the two surfaces, copy rules |
| [Persistence and data model](architecture/persistence.md) | The entity model, plan versus state, schema versioning, migrations |
| [Authentication and multi-user](architecture/auth.md) | Identities, cookie sessions, passwords and throttling, Google, ownership |
| [Architectural decisions](architecture/decisions.md) | The non-obvious invariants a future change could break without anything failing loudly |

---

## Subsystem READMEs

Each lives beside the code it describes.

| | |
|---|---|
| [`backend/`](../backend/README.md) | The Python application |
| [`backend/agents/`](../backend/agents/README.md) | The model-facing agents |
| [`backend/repo/`](../backend/repo/README.md) | Repository understanding |
| [`backend/learning/`](../backend/learning/README.md) | The learning model and its store |
| [`backend/pipeline/`](../backend/pipeline/README.md) | LangGraph orchestration and shared state |
| [`backend/auth/`](../backend/auth/README.md) | The account layer |
| [`frontend/`](../frontend/README.md) | The Next.js application |
| [`tests/`](../tests/README.md) | The backend suite |
| [`scripts/`](../scripts/README.md) | Measurement harnesses — every one of them spends money |
| [`tools/`](../tools/README.md) | Local setup that spends none: presentation checkpoints, and the working copy the contribution handoff opens |

---

## Reference

| | |
|---|---|
| [Patterns and utilities](reference/patterns.md) | The recurring Python idioms this codebase uses, and when to reach for each |
| <http://localhost:8000/docs> | The generated OpenAPI reference, while the backend is running |

---

## Planning and history

These are **design records**, not descriptions of current behaviour. They carry
the full argument behind most decisions — including the alternatives that were
rejected and the measurements that settled them — and several describe work that
was deliberately **not** built.

| | |
|---|---|
| [`planning/`](planning/README.md) | **Start here for the planning corpus** — what each document is, and which describe work that was deliberately not built |
| [`planning/phases/`](planning/phases/) | One document per workstream: `roadmap`, `repo-understanding`, `learning-engine`, `learning-graph`, `learning-loop`, `gap-model`, `multi-user`, `session-reset`, `reassessment`, `grounding-repair`, `cost-optimization`, `multi-language`, `chat-assistant`, `phase3`, `contribution-journey`, `contribution-handoff`, and the `ui-*` series |
| [`planning/phases/evidence/`](planning/phases/evidence/) | Committed output of the measurement harnesses in `scripts/` — the evaluation of the system as it stands |
| [`planning/vision/`](planning/vision/) | The original proposal and the evaluation plan |
| [`planning/open-source-readiness-plan.md`](planning/open-source-readiness-plan.md) | The audit that produced the current setup path. Completed; retained as a record |
| [`poster/`](poster/) | Poster artwork for the project |
| [`../project-archive/`](../project-archive/README.md) | The **superseded** vector-RAG architecture and the measured migration away from it. Nothing there necessarily describes the current implementation |

---

## Conventions

- **Terminology is fixed.** *Unit*, *objective*, *area*, *journey*, *required
  set*, *gap*, *verification*, *re-assessment*, *detour*, *settled* mean what
  [architecture/learning-engine.md](architecture/learning-engine.md) §1 says they
  mean, everywhere.
- **Deeper documents link back** to their parent and to this index.
- **Explain why a responsibility sits where it does**, rather than listing the
  files in a directory.
- **Do not repeat a long explanation in two places.** Link to the one that owns
  it.
- **Commands, paths, ports and environment variables must be verified** before
  they are written down.
