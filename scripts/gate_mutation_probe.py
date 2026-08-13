"""Does the Mutator still need retrieval? — re-probe persisted gate sessions.

    uv run python scripts/gate_mutation_probe.py data/experiments/gate-run2.json
    uv run python scripts/gate_mutation_probe.py <gate.json> --at 0.5

The gate's inline probe always fired at the session's FIRST node, which is the
systematic worst case for prerequisite derivation: everything foundational is
either already a graph node (and therefore excluded) or an unanchored concept.
Measuring the Mutator there and concluding "the dossier cannot supply
prerequisites" would be an artifact of where we stood, not a finding.

So this re-probes the same persisted sessions part-way along the path, which is
where a confusion signal actually arrives in the product. No pipeline re-run: the
graphs and dossiers are already in `data/sessions.db`, which is the point of
persisting them.

Retrieval stays severed. A Mutator that reaches it is recorded as reaching it —
that is the capability question this script exists to answer.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(override=True)

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from backend.learning import store as learning_store  # noqa: E402
from gate_stage4 import CONFUSED_ANSWER, DB_PATH, GOALS, sever_rag  # noqa: E402


def _short(text, width):
    text = " ".join(str(text or "").split())
    return text if len(text) <= width else text[: width - 1] + "…"


def _sources(candidates) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        counts[candidate.source] = counts.get(candidate.source, 0) + 1
    return counts


def probe(record: dict, fraction: float, spies: dict) -> dict:
    """One confusion event, with the whole candidate derivation recorded.

    The two sources are computed separately for the report — dossier-local and
    Skeleton-derived — and then the real `mutate` runs. Recomputing rather than
    instrumenting keeps the production path exactly as a user would hit it.
    """
    import anthropic

    from backend import api
    from backend.agents.grader.agent import run as run_grader
    from backend.agents.mentor import mutator
    from backend.pipeline.state import OnboardState
    from backend.repo import dossier_context, dossier_store, structure
    from backend.repo.skeleton import build_skeleton

    session_id = record.get("session_id")
    spec = GOALS[record["goal"]]
    graph = learning_store.load_graph(session_id, DB_PATH) if session_id else None
    if graph is None:
        return {"goal": record["goal"], "outcome": "session not found"}

    order = graph.path_order()
    if not order:
        return {"goal": record["goal"], "outcome": "no path order"}
    index = min(len(order) - 1, max(1, int(len(order) * fraction)))
    graph.set_current(order[index])

    client = anthropic.Anthropic()
    # The Grader reads the node's lesson, so it has to exist before we answer it.
    api._render_current_lesson(graph, client)

    node = graph.nodes[graph.current_node_id]
    anchor = node.code_anchor
    skeleton = build_skeleton(spec["repo_path"])
    from backend.repo.cloner import get_commit_sha

    stored = dossier_store.load_investigation(
        session_id, get_commit_sha(spec["repo_path"]), DB_PATH
    )
    dossier = (stored or {}).get("dossier") or {}
    taught_ranges, taught_symbols = mutator._taught(graph)

    # What each source offers on its own, before and after exclusion, so the
    # report can say which one supplied the candidate that was chosen.
    dossier_all = dossier_context.prerequisite_candidates(
        skeleton, dossier, anchor.file, symbol=anchor.symbol,
        line_start=anchor.line_start, line_end=anchor.line_end,
    ) if dossier else []
    dossier_kept = dossier_context.prerequisite_candidates(
        skeleton, dossier, anchor.file, symbol=anchor.symbol,
        line_start=anchor.line_start, line_end=anchor.line_end,
        exclude=taught_ranges,
    ) if dossier else []
    skeleton_kept = structure.neighbour_candidates(
        skeleton, anchor.file, symbol=anchor.symbol,
        line_start=anchor.line_start, line_end=anchor.line_end,
        exclude=taught_ranges, exclude_symbols=taught_symbols,
    )

    before = len(spies["retrieve_supporting_chunks"].calls)
    state = OnboardState(repo_url=spec["repo_url"], goal=dict(spec["goal"]),
                         client=client, repo_path=spec["repo_path"])
    state.graph = graph
    try:
        run_grader(state, CONFUSED_ANSWER, client=client)
        pool = mutator.candidate_pool(state, node)
        mutator.mutate(state, "prerequisite", client=client)
    except Exception as exc:
        return {"goal": record["goal"], "outcome": f"raised {type(exc).__name__}: {exc}"}

    mutation = state.last_mutation or {"kind": "none"}
    inserted = selected_source = why = None
    if mutation.get("kind") == "prerequisite":
        new = graph.nodes[mutation["new_node_id"]]
        inserted = f"{new.code_anchor.file}:{new.code_anchor.symbol or ''}"
        why = (new.lesson_brief or {}).get("why")
        for candidate in pool:
            if candidate.file == new.code_anchor.file and \
                    candidate.symbol == new.code_anchor.symbol:
                selected_source = candidate.source
                break

    return {
        "goal": record["goal"],
        "node_index": f"{index + 1}/{len(order)}",
        "confused_at": f"{anchor.file}:{anchor.symbol or ''}",
        "grade": (state.last_grade or {}).get("classification"),
        "dossier_candidates": [c.label() for c in dossier_kept],
        "dossier_sources": _sources(dossier_kept),
        "skeleton_candidates": [c.label() for c in skeleton_kept],
        "skeleton_sources": _sources(skeleton_kept),
        "removed_by_exclusion": [
            c.label() for c in dossier_all
            if c.label() not in {k.label() for k in dossier_kept}
        ],
        "pool_used": [f"{c.label()} [{c.source}]" for c in pool],
        "selected": inserted,
        "selected_source": selected_source,
        "selected_why": why,
        # Why nothing was inserted, when that was a judgement rather than a gap.
        "declined_because": mutation.get("rationale"),
        "outcome": mutation.get("kind") if inserted else mutation.get("reason", "none"),
        "reached_retrieval":
            len(spies["retrieve_supporting_chunks"].calls) > before,
        "errors": list(state.errors),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gate_json")
    parser.add_argument("--at", default="0.3,0.6,0.9",
                        help="Comma-separated fractions along the path to probe.")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    records = json.loads(Path(args.gate_json).read_text(encoding="utf-8"))
    runnable = [r for r in records if r.get("session_id")]
    positions = [float(p) for p in args.at.split(",")]
    print(f"probing {len(runnable)} persisted session(s) at {positions} along the "
          f"path; retrieval severed\n")

    spies = sever_rag()
    results = []
    for record in runnable:
        for fraction in positions:
            for spy in spies.values():
                spy.calls.clear()
            result = probe(record, fraction, spies)
            results.append(result)
            print(f"  {result['goal']:17s} node {result.get('node_index', '?'):>6s}  "
                  f"{result.get('confused_at', '')}")
            print(f"      dossier  {len(result.get('dossier_candidates') or []):>2} "
                  f"{result.get('dossier_sources') or {}}")
            print(f"      skeleton {len(result.get('skeleton_candidates') or []):>2} "
                  f"{result.get('skeleton_sources') or {}}")
            if result.get("removed_by_exclusion"):
                print(f"      excluded {result['removed_by_exclusion']}")
            print(f"      -> {result.get('outcome')}"
                  + (f"  [{result.get('selected_source')}] {result.get('selected')}"
                     if result.get("selected") else "")
                  + f"   retrieval={result.get('reached_retrieval')}")
            if result.get("selected_why"):
                print(f"         why: {_short(result['selected_why'], 92)}")
            if result.get("declined_because"):
                print(f"         because: {_short(result['declined_because'], 92)}")
            if result.get("errors"):
                print(f"      errors: {[_short(e, 90) for e in result['errors']]}")

    inserted = [r for r in results if r.get("selected")]
    from_dossier = sum(1 for r in inserted if r.get("selected_source") in (
        "prerequisite", "depends_on", "used_by", "contract", "flow_predecessor"))
    declined = sum(1 for r in results if r.get("outcome") == "no_useful_prerequisite")
    reached = sum(1 for r in results if r.get("reached_retrieval"))
    dossier_sufficed = sum(1 for r in results if r.get("dossier_candidates"))
    skeleton_needed = sum(
        1 for r in results
        if not r.get("dossier_candidates") and r.get("skeleton_candidates")
    )
    print(f"\nprobes                              {len(results)}")
    print(f"prerequisite inserted               {len(inserted)}"
          f"  ({from_dossier} from a dossier candidate, "
          f"{len(inserted) - from_dossier} from a skeleton candidate)")
    print(f"declined as not useful              {declined}")
    print(f"dossier alone had candidates        {dossier_sufficed}")
    print(f"only the skeleton had candidates    {skeleton_needed}")
    print(f"reached retrieval                   {reached}")

    out = Path(args.out) if args.out else Path(
        f"data/experiments/mutation-probe-{time.strftime('%Y%m%d-%H%M%S')}.json"
    )
    out.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
