# Project archive

Development and evaluation artifacts kept on purpose. This is not a folder of
leftovers: everything here documents how the system came to be what it is, and
it is retained so that the decisions behind it can be checked rather than taken
on trust.

## Read this first

**Nothing in this directory necessarily describes the current implementation.**
`superseded-architecture/` describes a vector-RAG system — ChromaDB, local
embeddings, a Code Structure Agent, a `backend/rag/` package — that was removed
outright and does not exist in the code. Read those documents as history, never
as reference.

## Where the current system is described

| Question | Where to look |
|---|---|
| How does the system work today? | [`docs/reference/system-architecture.md`](../docs/reference/system-architecture.md) — written against the code, with `[implemented]` / `[known limitation]` / `[planned]` labels |
| How do I run it? | [`README.md`](../README.md) |
| What are the conventions and rules? | [`CLAUDE.md`](../CLAUDE.md) |
| How was the *current* system evaluated? | `docs/planning/phases/evidence/`, and the harnesses that produce it in `scripts/` |

## What is here

| Directory | Contents |
|---|---|
| `superseded-architecture/` | Design documents for the pre-migration architecture, plus the Phase 1 completion record. |
| `rag-migration/` | The measured comparison between retrieval-based repository understanding and the exploration-based architecture that replaced it — the curated results, and the harnesses that produced them. |

## Why it is kept

The architecture these documents describe was replaced, not merely revised. The
migration away from vector retrieval is the largest design decision in the
project, and it is only assessable if the thing that was replaced is still
legible. Deleting the old design would leave the current one looking inevitable
rather than chosen.

A migration record that keeps only its wins is not evidence, so the results in
`rag-migration/results/` include the runs where the **replaced** architecture did
better — most instructively `integration-rest.json`, where retrieval scored 100%
discovery on `fastapi-di` and exploration scored 80%.

## This archive is read, not written

`rag-migration/results/` is a historical corpus, fixed at the point the migration
closed. Nothing writes into it.

The harnesses in `rag-migration/harnesses/` were moved out of `scripts/`; each one
resolves the repository root from its own location, so that root was recomputed
for the new depth and they still run from the repository root:

    uv run python project-archive/rag-migration/harnesses/smoke_stage0.py

Where a harness produces output, it writes to `data/experiments/` — outside this
directory — exactly as it did before. Harnesses that measure the *current* system
never moved: they are in `scripts/`, and their results go to
`docs/planning/phases/evidence/`.

## What is deliberately *not* here

Validation of the system as it stands today. That lives in
`docs/planning/phases/evidence/` and stays in the main repository, because it
substantiates claims about the final product rather than about its history. A
reviewer should not read this archive as the evaluation of the project.
