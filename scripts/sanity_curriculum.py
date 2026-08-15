"""B3 sanity matrix — is the objective-first planner structurally sound and roughly sized?

    uv run python scripts/sanity_curriculum.py --dry-run     # no API calls
    uv run python scripts/sanity_curriculum.py               # the four cells
    uv run python scripts/sanity_curriculum.py --only requests-map

This is NOT the §6.3 calibration. Calibration measures variance across repeats
to replace the provisional guard bands, and it is only meaningful once selection
behaviour has stopped changing. Running it against a planner still being adjusted
would buy numbers that expire before they are used.

What this run is for: catching output that is STRUCTURALLY WRONG or WILDLY
MIS-SIZED, on real repositories, before any of that effort is spent. Two repos
(small and large) at the two ends of `code_depth`, one attempt each.

The structural checks are the interesting half, because they are assertions
rather than impressions — each one is a property the design claims and a test
can only partially reach, since tests use a scripted client and a four-file
repository:

  GROUNDED      every anchor on every unit resolves against the repository
  PROJECTION    the display columns equal one member of the unit's `anchors`
  WALKABLE      path_order() reaches every node — one chain, no orphans
  ACYCLIC       no unit is its own prerequisite, directly or transitively
  ORDERED       every dependency is taught before the unit that declares it
  COVERED       every declared area contributes at least one non-optional unit

The sizing half is deliberately reported, not asserted. A number outside its
band is a finding to look at, not a failure — the bands are uncalibrated
judgement (LD14) and the floor is advisory (LQ6).
"""

import argparse
import json
import os
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

import anthropic  # noqa: E402

from backend.agents.mentor.curriculum import _SCOPE_BANDS  # noqa: E402
from backend.pipeline.runner import run_pipeline  # noqa: E402
from backend.repo.anchors import resolve  # noqa: E402
from backend.repo.skeleton import build_skeleton  # noqa: E402


REQUESTS = "https://github.com/psf/requests"
FASTAPI = "https://github.com/fastapi/fastapi"


def goal(repo_url: str, code_depth: str, primary: str, focus: str) -> dict:
    depth = {"map": "overview", "working": "moderate", "implementation": "deep"}
    return {
        "primary_goal": primary,
        "goal_type": "understand_architecture",
        "focus_area": focus,
        "code_depth": code_depth,
        "depth": depth[code_depth],
        "target_repo": repo_url,
        "familiarity": "Skimmed the README or docs",
        "background": "5 years of Python, some Django",
    }


CELLS = {
    "requests-map": (REQUESTS, goal(
        REQUESTS, "map",
        "understand how a request travels from the public API to the wire",
        "the request lifecycle",
    )),
    "requests-implementation": (REQUESTS, goal(
        REQUESTS, "implementation",
        "understand how a request travels from the public API to the wire",
        "the request lifecycle",
    )),
    "fastapi-map": (FASTAPI, goal(
        FASTAPI, "map",
        "understand how a route is declared, resolved and executed",
        "routing and dependency injection",
    )),
    "fastapi-implementation": (FASTAPI, goal(
        FASTAPI, "implementation",
        "understand how a route is declared, resolved and executed",
        "routing and dependency injection",
    )),
}


# ── structural checks ──────────────────────────────────────────────────────────


def check_grounded(graph, repo_path: str) -> list[str]:
    """Every anchor on every unit resolves — not just the displayed one."""
    skeleton = build_skeleton(repo_path)
    failures = []
    for node in graph.nodes.values():
        stored = (node.lesson_brief or {}).get("anchors") or []
        for anchor in stored:
            resolution = resolve(
                skeleton, anchor["file"], symbol=anchor.get("symbol") or None,
                line_start=anchor.get("line_start"), line_end=anchor.get("line_end"),
            )
            if not resolution.ok:
                failures.append(
                    f"{node.title}: {anchor['file']}:{anchor.get('symbol')}"
                    f" ({resolution.reason})"
                )
    return failures


def check_projection(graph) -> list[str]:
    """The display columns must equal one member of `anchors` (§10)."""
    failures = []
    for node in graph.nodes.values():
        stored = (node.lesson_brief or {}).get("anchors") or []
        if not stored:
            continue
        shown = (
            node.code_anchor.file,
            node.code_anchor.line_start,
            node.code_anchor.line_end,
        )
        if shown not in [
            (a["file"], a["line_start"], a["line_end"]) for a in stored
        ]:
            failures.append(f"{node.title}: display anchor is not one of its anchors")
    return failures


def check_walkable(graph) -> list[str]:
    walked = graph.path_order()
    if len(walked) != len(graph.nodes):
        return [f"path_order reached {len(walked)} of {len(graph.nodes)} nodes"]
    return []


def check_acyclic(graph) -> list[str]:
    prereqs: dict[str, set[str]] = {}
    for edge in graph.edges:
        if edge.kind == "prerequisite":
            prereqs.setdefault(edge.to_node_id, set()).add(edge.from_node_id)

    failures = []
    for start in prereqs:
        seen, frontier = set(), list(prereqs.get(start, ()))
        while frontier:
            current = frontier.pop()
            if current == start:
                failures.append(f"{graph.nodes[start].title}: prerequisite cycle")
                break
            if current in seen:
                continue
            seen.add(current)
            frontier.extend(prereqs.get(current, ()))
    return failures


def check_ordered(graph) -> list[str]:
    position = {nid: i for i, nid in enumerate(graph.path_order())}
    failures = []
    for edge in graph.edges:
        if edge.kind != "prerequisite":
            continue
        if position.get(edge.from_node_id, 0) > position.get(edge.to_node_id, 0):
            failures.append(
                f"{graph.nodes[edge.to_node_id].title}: taught before its prerequisite"
            )
    return failures


def check_covered(graph) -> list[str]:
    declared = {a["id"] for a in graph.areas}
    staffed = {
        (n.lesson_brief or {}).get("area_id")
        for n in graph.nodes.values()
        if (n.lesson_brief or {}).get("priority") != "optional"
    }
    missing = declared - staffed
    return [f"area {a} has no non-optional unit" for a in sorted(missing)]


CHECKS = {
    "WALKABLE": check_walkable,
    "PROJECTION": check_projection,
    "ACYCLIC": check_acyclic,
    "ORDERED": check_ordered,
    "COVERED": check_covered,
}


# ── the run ────────────────────────────────────────────────────────────────────


def measure(name: str, repo_url: str, goal_dict: dict, client) -> dict:
    started = time.time()
    state = run_pipeline(repo_url, goal_dict, client=client)
    seconds = round(time.time() - started, 1)

    if state.graph is None:
        return {
            "cell": name, "ok": False, "seconds": seconds,
            "died": "no graph", "errors": state.errors[-6:],
        }

    graph = state.graph
    units = list(graph.nodes.values())
    briefs = [(n.lesson_brief or {}) for n in units]
    journey = [b for b in briefs if b.get("priority") != "optional"]
    anchor_counts = [len(b.get("anchors") or []) for b in briefs]

    kinds: dict[str, int] = {}
    for brief in briefs:
        kinds[brief.get("kind") or "?"] = kinds.get(brief.get("kind") or "?", 0) + 1

    code_depth = goal_dict["code_depth"]
    low, high = _SCOPE_BANDS[code_depth]

    failures = {label: check(graph) for label, check in CHECKS.items()}
    failures["GROUNDED"] = check_grounded(graph, state.repo_path)

    return {
        "cell": name,
        "ok": not any(failures.values()),
        "seconds": seconds,
        "code_depth": code_depth,
        "units_total": len(units),
        "journey_size": len(journey),
        "optional": len(units) - len(journey),
        "band": [low, high],
        "in_band": low <= len(journey) <= high,
        "areas": len(graph.areas),
        "area_titles": [a["title"] for a in graph.areas],
        "kinds": kinds,
        "multi_anchor_units": sum(1 for c in anchor_counts if c > 1),
        "max_anchors": max(anchor_counts) if anchor_counts else 0,
        "prerequisite_edges": sum(1 for e in graph.edges if e.kind == "prerequisite"),
        "confidence": state.confidence,
        "objectives_present": sum(1 for b in briefs if b.get("objective")),
        "failures": {k: v for k, v in failures.items() if v},
        "planner_notes": [e for e in state.errors if e.startswith("curriculum:")][:4],
    }


def report(results: list[dict]) -> None:
    print("\n" + "=" * 78)
    print("B3 SANITY MATRIX")
    print("=" * 78)
    for r in results:
        print(f"\n--- {r['cell']} ---")
        if not r.get("ok") and r.get("died"):
            print(f"  DIED: {r['died']} after {r['seconds']}s")
            for e in r.get("errors", []):
                print(f"    {e}")
            continue
        band = f"{r['band'][0]}-{r['band'][1]}"
        flag = "" if r["in_band"] else "   <-- OUTSIDE BAND"
        print(f"  journey {r['journey_size']} units (band {band}){flag}")
        print(f"  + {r['optional']} optional, {r['units_total']} total")
        print(f"  areas {r['areas']}: {', '.join(r['area_titles'])}")
        print(f"  kinds {r['kinds']}")
        print(
            f"  multi-anchor {r['multi_anchor_units']} units "
            f"(max {r['max_anchors']} anchors), "
            f"{r['prerequisite_edges']} prerequisite edges"
        )
        print(
            f"  objectives {r['objectives_present']}/{r['units_total']}, "
            f"confidence {r['confidence']}, {r['seconds']}s"
        )
        if r["failures"]:
            for label, items in r["failures"].items():
                print(f"  {label} FAILED:")
                for item in items[:5]:
                    print(f"    {item}")
        else:
            print("  structural checks: all pass")
        for note in r.get("planner_notes", []):
            print(f"  note: {note[:160]}")

    print("\n" + "=" * 78)
    structural = [r for r in results if not r.get("ok")]
    print(f"structurally clean: {len(results) - len(structural)}/{len(results)}")
    sized = [r for r in results if r.get("in_band")]
    print(f"inside band:        {len(sized)}/{len(results)}")
    print("=" * 78)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="run one cell by name")
    parser.add_argument("--dry-run", action="store_true", help="no API calls")
    parser.add_argument("--out", default="docs/planning/phases/evidence")
    args = parser.parse_args()

    cells = CELLS if not args.only else {args.only: CELLS[args.only]}

    if args.dry_run:
        print("cells:", ", ".join(cells))
        print("checks:", ", ".join(list(CHECKS) + ["GROUNDED"]))
        print("bands:", _SCOPE_BANDS)
        print("flag CODEONBOARD_CURRICULUM will be set to 1")
        return 0

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY missing", file=sys.stderr)
        return 2

    os.environ["CODEONBOARD_CURRICULUM"] = "1"
    # The pipeline's nodes receive only state, so the client rides on it and is
    # never constructed for them — api.py injects one and so must this.
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    results = []
    for name, (repo_url, goal_dict) in cells.items():
        print(f"running {name} ...", flush=True)
        try:
            results.append(measure(name, repo_url, goal_dict, client))
        except Exception as exc:  # a dead cell must not lose the others
            results.append({"cell": name, "ok": False, "died": repr(exc), "seconds": 0})
    report(results)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "b3-sanity-matrix.json"
    path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nwritten: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
