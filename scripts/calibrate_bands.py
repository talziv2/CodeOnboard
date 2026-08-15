"""§6.3 guard-band calibration — are the provisional bands set where curricula actually land?

    uv run python scripts/calibrate_bands.py --dry-run
    uv run python scripts/calibrate_bands.py                 # 6 cells x 3 repeats
    uv run python scripts/calibrate_bands.py --repeats 5 --only requests-working

WHAT THIS MEASURES, AND WHAT IT DOES NOT

§6.3 calibrates "objective proposal + selection" — the PLANNER. So each cell
investigates ONCE and then plans N times against that one dossier. Repeats
therefore measure planner variance, which is the thing a band has to be set
around; re-investigating per repeat would fold in exploration variance and
report a spread that no band could ever accommodate.

It also makes the run affordable: the investigation is the expensive stage, and
paying for it once per cell instead of once per repeat is the difference between
a matrix that runs and one that gets skipped.

THE NUMBER THAT MATTERS is `core_before_band`: the required set plus its
dependency closure, measured BEFORE any band is applied. That is what a
curriculum genuinely needs. The journey size after selection cannot answer the
question, because the band is what produced it — asking whether journeys fit
inside the bands is asking whether the guard did its job, not whether it is set
correctly.

BANDS ARE NOT CHANGED BY THIS SCRIPT. It collects evidence and reports; moving
a number is a separate, deliberate act.

The matrix extends the B3 sanity cells with `working`, which §6.3 lists among the
three code_depth values and which is the default depth — calibrating a band with
no observations of it would be a guess wearing a measurement's clothes.
"""

import argparse
import json
import os
import statistics
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

from backend.agents.mentor import curriculum  # noqa: E402
from backend.agents.mentor.curriculum import _SCOPE_BANDS  # noqa: E402
from backend.pipeline.runner import run_pipeline  # noqa: E402
from backend.pipeline.state import OnboardState  # noqa: E402


REQUESTS = "https://github.com/psf/requests"
FASTAPI = "https://github.com/fastapi/fastapi"

GOALS = {
    REQUESTS: (
        "understand how a request travels from the public API to the wire",
        "the request lifecycle",
    ),
    FASTAPI: (
        "understand how a route is declared, resolved and executed",
        "routing and dependency injection",
    ),
}

DEPTH_WORD = {"map": "overview", "working": "moderate", "implementation": "deep"}


def goal_for(repo_url: str, code_depth: str) -> dict:
    primary, focus = GOALS[repo_url]
    return {
        "primary_goal": primary,
        "goal_type": "understand_architecture",
        "focus_area": focus,
        "code_depth": code_depth,
        "depth": DEPTH_WORD[code_depth],
        "target_repo": repo_url,
        "familiarity": "Skimmed the README or docs",
        "background": "5 years of Python, some Django",
    }


def cells() -> dict[str, tuple[str, str]]:
    out = {}
    for repo, short in ((REQUESTS, "requests"), (FASTAPI, "fastapi")):
        for depth in ("map", "working", "implementation"):
            out[f"{short}-{depth}"] = (repo, depth)
    return out


# ── one cell ───────────────────────────────────────────────────────────────────


def run_cell(name: str, repo_url: str, code_depth: str, repeats: int, client) -> dict:
    goal = goal_for(repo_url, code_depth)

    print(f"  {name}: investigating ...", flush=True)
    started = time.time()
    base = run_pipeline(repo_url, goal, client=client)
    investigate_seconds = round(time.time() - started, 1)

    if base.investigation is None or base.graph is None:
        return {
            "cell": name, "code_depth": code_depth, "ok": False,
            "died": "no dossier", "errors": base.errors[-4:],
        }

    runs: list[dict] = []
    for i in range(repeats):
        print(f"  {name}: planning {i + 1}/{repeats} ...", flush=True)
        state = OnboardState(repo_url=repo_url, goal=dict(goal), client=client)
        state.repo_path = base.repo_path
        state.investigation = base.investigation
        state.doc_context = base.doc_context
        state.system_review = base.system_review

        planned = time.time()
        curriculum.run(state, client)
        seconds = round(time.time() - planned, 1)

        report = state.plan_report
        if state.graph is None or report is None:
            runs.append({"repeat": i + 1, "ok": False,
                         "errors": [e for e in state.errors][-3:]})
            continue

        briefs = [(n.lesson_brief or {}) for n in state.graph.nodes.values()]
        kinds: dict[str, int] = {}
        for brief in briefs:
            key = brief.get("kind") or "?"
            kinds[key] = kinds.get(key, 0) + 1

        runs.append({
            "repeat": i + 1,
            "ok": True,
            "seconds": seconds,
            "proposed": report["proposed"],
            "grounding_drops": report["dropped_by_grounding"],
            "core_before_band": report["core_before_band"],
            "journey": report["journey"],
            "optional": report["optional"],
            "band_bound": report["band_bound"],
            "demoted_by_band": report["demoted_by_band"],
            "areas": report["areas_declared"],
            "kinds": kinds,
            "covers_goal": report["covers_goal"],
            "confidence": state.confidence,
        })

    good = [r for r in runs if r.get("ok")]
    low, high = _SCOPE_BANDS[code_depth]
    return {
        "cell": name,
        "code_depth": code_depth,
        "ok": len(good) > 0,
        "band": [low, high],
        "investigate_seconds": investigate_seconds,
        "runs": runs,
        "spread": spread(good),
    }


def spread(runs: list[dict]) -> dict:
    """Variance across repeats, for the numbers a band is set around."""
    if not runs:
        return {}
    out: dict = {}
    for key in ("proposed", "core_before_band", "journey", "optional", "areas"):
        values = [r[key] for r in runs]
        out[key] = {
            "min": min(values),
            "max": max(values),
            "mean": round(statistics.mean(values), 1),
            "stdev": round(statistics.stdev(values), 2) if len(values) > 1 else 0.0,
        }
    out["bound"] = {
        "ceiling": sum(1 for r in runs if r["band_bound"] == "ceiling"),
        "floor": sum(1 for r in runs if r["band_bound"] == "floor"),
        "none": sum(1 for r in runs if r["band_bound"] is None),
    }
    out["grounding_drops_total"] = sum(r["grounding_drops"] for r in runs)
    return out


# ── report ─────────────────────────────────────────────────────────────────────


def report(results: list[dict]) -> None:
    print("\n" + "=" * 78)
    print("GUARD-BAND CALIBRATION — EVIDENCE ONLY, NO BANDS CHANGED")
    print("=" * 78)

    for r in results:
        print(f"\n--- {r['cell']} ---")
        if not r.get("ok"):
            print(f"  DIED: {r.get('died')}  {r.get('errors', '')}")
            continue
        s, band = r["spread"], r["band"]
        print(f"  band {band[0]}-{band[1]}   ({len(r['runs'])} repeats)")
        for key in ("proposed", "core_before_band", "journey", "optional", "areas"):
            v = s[key]
            print(
                f"    {key:<18} min {v['min']:<4} max {v['max']:<4} "
                f"mean {v['mean']:<6} sd {v['stdev']}"
            )
        print(
            f"    band bound         ceiling {s['bound']['ceiling']}  "
            f"floor {s['bound']['floor']}  none {s['bound']['none']}"
        )
        print(f"    grounding drops    {s['grounding_drops_total']}")
        for run in r["runs"]:
            if run.get("ok"):
                print(f"      #{run['repeat']} kinds {run['kinds']}")

    print("\n" + "=" * 78)
    print("BAND PRESSURE (§6.3 step 3: a band should bind RARELY)")
    print("=" * 78)
    for r in results:
        if not r.get("ok"):
            continue
        s, band = r["spread"], r["band"]
        total = len(r["runs"])
        ceiling, floor = s["bound"]["ceiling"], s["bound"]["floor"]
        core = s["core_before_band"]
        verdict = (
            "CEILING BINDS" if ceiling > total / 2
            else "floor fires" if floor > total / 2
            else "binds rarely"
        )
        headroom = band[1] - core["max"]
        print(
            f"  {r['cell']:<26} core {core['min']}-{core['max']} "
            f"vs band {band[0]}-{band[1]}   headroom {headroom:+d}   "
            f"ceiling {ceiling}/{total}  floor {floor}/{total}   {verdict}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--only")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out", default="docs/planning/phases/evidence")
    args = parser.parse_args()

    matrix = cells() if not args.only else {args.only: cells()[args.only]}

    if args.dry_run:
        print("cells:", ", ".join(matrix))
        print("repeats per cell:", args.repeats)
        print("planning calls:", len(matrix) * args.repeats)
        print("investigations:", len(matrix), "(one per cell, shared by repeats)")
        print("bands (unchanged):", _SCOPE_BANDS)
        return 0

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY missing", file=sys.stderr)
        return 2

    os.environ["CODEONBOARD_CURRICULUM"] = "1"
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    results = []
    for name, (repo_url, depth) in matrix.items():
        print(f"cell {name} ...", flush=True)
        try:
            results.append(run_cell(name, repo_url, depth, args.repeats, client))
        except Exception as exc:  # a dead cell must not lose the others
            results.append({"cell": name, "ok": False, "died": repr(exc)})
        # Written after every cell: a long matrix must not lose everything to a
        # failure in its last one.
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "band-calibration.json").write_text(
            json.dumps(results, indent=2), encoding="utf-8"
        )

    report(results)
    print(f"\nwritten: {Path(args.out) / 'band-calibration.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
