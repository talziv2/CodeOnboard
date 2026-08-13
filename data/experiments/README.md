# Experiment artifacts — the evidence behind the RAG migration

Raw results from Stages 2–5 of the repository-understanding migration
(`docs/planning/phases/repo-understanding.md`). Kept deliberately: they are the
evidence base for the final report, and they record **both** where the new
architecture improved on RAG and where RAG did better.

Superseded, aborted and precursor runs have been removed. What is left is the
smallest set that still supports every measured claim in the decision log.

## The head-to-head comparisons (RAG vs explorer)

| File | What it is |
|---|---|
| `stage3-merged.json` | **The primary A/B.** 4 goals × 3 arms (`baseline` = RAG, `nosurvey`, `survey`), each with the full learning path, path metrics and investigation telemetry. The only complete comparison; every relevance/discovery figure in §21 comes from here |
| `integration-auth.json`, `integration-rest.json` | Explorer vs RAG after the native-Dossier Mentor landed. `integration-rest` holds the `fastapi-di` result where **RAG scored 100% discovery and the explorer 80%** |
| `integration-flow3.json` | The explorer arm for `requests-flow`, pairing with the RAG arm in `integration-rest.json` |
| `stage4-explorer.json`, `stage4-explorer2.json`, `stage4-rag.json` | The full adaptive loop (lesson → grade → confusion → prerequisite → D12 fallback) in both architectures. The only Teaching-context and prerequisite-selection head-to-head; `explorer` and `rag` selected the **same** prerequisite node |

## Stage 2 — the Survey (Layer B)

| File | What it is |
|---|---|
| `stage2-final.json` | Consolidated policy A/B: `default` vs `structural` navigation, both repos, 2 runs per cell |
| `stage2-requests-repeats.json`, `stage2-fastapi-repeats.json` | The repeat runs behind the P2 closure (every subsystem accounted for, 0 silent omissions) and the consistency figures |
| `stage2-cache-breakpoints.json`, `stage2-fastapi.json` | The one-vs-two conversation-breakpoint arms. These are the only files containing `structural/one`, and they are the evidence that the two-breakpoint hypothesis was **falsified** |
| `stage2-notice-requests.json`, `stage2-notice-fastapi.json` | Runs with the one-shot `[budget]` notice, which raised survey acceptance 1/6 → 3/4 on `requests` and was inconclusive on `fastapi` |

## Stage 4/4a — reliability

| File | What it is |
|---|---|
| `consistency-1.json` | **Two failures, and the most useful file here.** Holds the raw malformed dossier payload (`components` as XML-ish markup, item keys stranded at the root) that drove the whole Stage-4b serialisation diagnosis |
| `consistency-2.json`, `consistency-3.json` | Explorer repeats for `requests-auth` and `fastapi-di`; the source of the discovery-variance findings |
| `gate-run1.json` | Reliability gate, batch 1: 4 attempts ran, 6 lost to an API credit outage |
| `gate-run2.json` | Reliability gate, batch 2: 8/8 end to end, both repos, three goal types |
| `gate-run3.json` | 3 × `fastapi-di` after the public-API fix — discovery 80% → 100% |

## Stage 4b/5 — the Mutator and the final state

| File | What it is |
|---|---|
| `mutation-probe.json` | **Pre-fix**: 8 sessions probed mid-path, 7/8 fell through to retrieval. The measurement that justified the Skeleton-backed candidate pool |
| `mutation-probe-wide.json` | **Post-fix**: 16 probes, both repos, two path positions. 0/16 reached retrieval; contains examples of all three outcomes (dossier sufficient, skeleton necessary, correctly nothing) |
| `mutation-probe-di.json` | 4 further probes on the post-fix `fastapi-di` sessions |
| `stage5-e2e.json` | The final validation, run with no vector infrastructure installed at all: 4/4 end to end across both repos |

## Reading them

`gate-*.json` and `mutation-probe-*.json` are lists of per-attempt records.
`stage2-*.json` have a `rows` array (one per run) plus `cells`/`consistency`
summaries. `stage3-merged.json` and `integration-*.json` are keyed by goal, then
by arm. The harnesses that produced them are in `scripts/`.
