"""Run the authored cases against the REAL Grader and report the matrix.

    uv run python scripts/grader_eval.py --dry-run
    uv run python scripts/grader_eval.py

Expectations live in `grader_eval_cases.py`, committed before this ran. This
script only measures; it changes no prompt, threshold, label or policy.

Each case is graded exactly as a session would grade it: the real node, its real
cached lesson (prompt + expected_answer), the real objective and concept tags,
through `backend.agents.grader.run`. The only thing that differs from a live
session is that the answer is scripted.
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(override=True)

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import anthropic  # noqa: E402

from backend.agents.grader import run as run_grader  # noqa: E402
from backend.learning import store as learning_store  # noqa: E402
from backend.learning.graph import LearningGraph  # noqa: E402
from backend.pipeline.state import OnboardState  # noqa: E402

from grader_eval_cases import ANSWERS, EXPECTATION, OBJECTIVES  # noqa: E402

# The FROZEN v2 fixture database, not the live one.
#
# This probe measures against specific stored sessions — its value is that the
# numbers are reproducible against the sessions the phase was measured on. The
# live database moved to schema v3 (`docs/planning/phases/session-reset.md` D8),
# which makes every v2 session invisible to `load_graph`, so pointing here is
# what keeps these fixtures readable rather than merely archived.
DB = Path("data/sessions-fixtures.db")


def load_node(session_id: str, prefix: str):
    graph = learning_store.load_graph(session_id, DB)
    if graph is None:
        return None, None
    for node_id, node in graph.nodes.items():
        if node_id.startswith(prefix):
            return graph, node
    return graph, None


def grade(graph: LearningGraph, node, answer: str, client) -> dict:
    """One real grading call against a one-node copy of the real graph.

    Returns `last_grade` plus the gaps the call opened on the isolated node.
    Under `CODEONBOARD_GAPS=1` that list is the only place multiplicity is
    visible: the scalar `gap_kind` reports the highest-precedence gap and says
    nothing about how many there were, which is precisely the loss the gap model
    exists to end. Measurement only — the isolated node is discarded.
    """
    import copy

    isolated = LearningGraph(repo_url=graph.repo_url, goal=graph.goal)
    fresh = copy.deepcopy(node)
    fresh.attempts = []
    fresh.understanding_state = "not_started"
    fresh.gap_state.gaps = []
    isolated.add_node(fresh)
    isolated.set_current(fresh.id)

    state = OnboardState(repo_url=graph.repo_url, goal=graph.goal, client=client)
    state.graph = isolated
    run_grader(state, answer, client=client)
    result = dict(state.last_grade or {})
    result["gaps"] = [
        {"kind": g.kind, "claim": g.claim, "objective_part": g.objective_part,
         "foundational": g.foundational}
        for g in fresh.gaps
    ]
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out", default="docs/planning/phases/evidence")
    args = parser.parse_args()

    cases = [(o, q) for o in OBJECTIVES for q in EXPECTATION]
    if args.dry_run:
        print("objectives:", len(OBJECTIVES))
        print("qualities :", ", ".join(EXPECTATION))
        print("cases     :", len(cases))
        for _, prefix, repo, kind, label in OBJECTIVES:
            missing = set(EXPECTATION) - set(ANSWERS.get(prefix, {}))
            print(f"  {repo:<9} {kind:<14} {label:<32} missing={missing or 'none'}")
        return 0

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY missing", file=sys.stderr)
        return 2

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=180.0)
    rows: list[dict] = []

    for session_id, prefix, repo, kind, label in OBJECTIVES:
        graph, node = load_node(session_id, prefix)
        if node is None:
            print(f"SKIP {prefix}: node not found", file=sys.stderr)
            continue
        print(f"\n{repo}/{kind}: {label}", flush=True)
        for quality in EXPECTATION:
            answer = ANSWERS[prefix][quality]
            expected_class, expected_gap = EXPECTATION[quality]
            got = grade(graph, node, answer, client)
            actual_class = got.get("classification")
            actual_gap = got.get("gap_kind")
            gaps = got.get("gaps") or []
            class_ok = actual_class in expected_class
            gap_ok = expected_gap is None or actual_gap == expected_gap
            rows.append({
                "repo": repo, "kind": kind, "objective": label, "node": prefix,
                "quality": quality,
                "expected_classification": sorted(expected_class),
                "expected_gap": expected_gap,
                "actual_classification": actual_class,
                "actual_gap": actual_gap,
                "class_agrees": class_ok, "gap_agrees": gap_ok,
                "rationale": got.get("rationale"),
                "gap_count": len(gaps),
                "gaps": gaps,
            })
            mark = "OK " if (class_ok and gap_ok) else "XX "
            print(f"  {mark}{quality:<15} expected {'/'.join(sorted(expected_class)):<20}"
                  f"got {str(actual_class):<11} gap={str(actual_gap)} n={len(gaps)}")

    # ── report ────────────────────────────────────────────────────────────────
    line = "=" * 78
    print(f"\n{line}\nAGREEMENT\n{line}")
    total = len(rows)
    cls_ok = sum(1 for r in rows if r["class_agrees"])
    gap_ok = sum(1 for r in rows if r["gap_agrees"])
    both = sum(1 for r in rows if r["class_agrees"] and r["gap_agrees"])
    print(f"  cases                 {total}")
    print(f"  classification agrees {cls_ok}/{total} ({cls_ok/total:.0%})")
    print(f"  gap_kind agrees       {gap_ok}/{total} ({gap_ok/total:.0%})")
    print(f"  both agree            {both}/{total} ({both/total:.0%})")

    print(f"\n{line}\nBY ANSWER QUALITY\n{line}")
    by_quality = defaultdict(list)
    for r in rows:
        by_quality[r["quality"]].append(r)
    for quality, group in by_quality.items():
        ok = sum(1 for r in group if r["class_agrees"] and r["gap_agrees"])
        got = Counter(f"{r['actual_classification']}/{r['actual_gap']}" for r in group)
        print(f"  {quality:<15} {ok}/{len(group)} agree   actual: {dict(got)}")

    print(f"\n{line}\nTHE understood / partial BOUNDARY\n{line}")
    boundary = [r for r in rows if r["quality"] in ("complete", "concise")]
    for quality in ("complete", "concise"):
        group = [r for r in boundary if r["quality"] == quality]
        understood = sum(1 for r in group if r["actual_classification"] == "understood")
        print(f"  {quality:<10} understood {understood}/{len(group)}   "
              f"actual: {dict(Counter(r['actual_classification'] for r in group))}")
    print("  disagreements:")
    for r in boundary:
        if not r["class_agrees"]:
            print(f"    {r['repo']}/{r['kind']:<14} {r['quality']:<9} -> "
                  f"{r['actual_classification']}/{r['actual_gap']}")
            print(f"       {str(r['rationale'])[:150]}")

    # Inert flag-off (no gaps are recorded), so this section reports nothing
    # rather than being conditional on the environment.
    print(f"\n{line}\nGAP MULTIPLICITY (CODEONBOARD_GAPS)\n{line}")
    with_gaps = [r for r in rows if r["gap_count"] > 0]
    multi = [r for r in rows if r["gap_count"] > 1]
    print(f"  cases with >=1 gap    {len(with_gaps)}/{total}")
    print(f"  cases with >=2 gaps   {len(multi)}/{total}")
    print(f"  distribution          {dict(sorted(Counter(r['gap_count'] for r in rows).items()))}")
    print("  by answer quality:")
    for quality, group in by_quality.items():
        counts = sorted(r["gap_count"] for r in group)
        print(f"    {quality:<15} {counts}")
    if multi:
        print("  multi-gap cases (the claim the phase rests on):")
        for r in multi:
            print(f"    {r['repo']}/{r['kind']:<14} {r['quality']:<15} "
                  f"{r['gap_count']} gaps, kinds={[g['kind'] for g in r['gaps']]}")
            for g in r["gaps"]:
                print(f"       - {g['kind']:<26} {g['claim'][:90]}")

    print(f"\n{line}\nBY LESSON KIND (is strictness concentrated?)\n{line}")
    by_kind = defaultdict(list)
    for r in rows:
        by_kind[f"{r['repo']}/{r['kind']}"].append(r)
    for key, group in sorted(by_kind.items()):
        ok = sum(1 for r in group if r["class_agrees"] and r["gap_agrees"])
        strong = [r for r in group if r["quality"] in ("complete", "concise")]
        u = sum(1 for r in strong if r["actual_classification"] == "understood")
        print(f"  {key:<26} {ok}/{len(group)} agree   strong answers understood {u}/{len(strong)}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "grader-evaluation.json").write_text(
        json.dumps(rows, indent=2), encoding="utf-8")
    print(f"\nwritten: {out / 'grader-evaluation.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
