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

RESUMING, AND WHY A PARTIAL RERUN IS DANGEROUS WITHOUT IT

The first version of this script wrote only the cells from the current run to
`band-calibration.json`, so `--only fastapi-map` would have silently destroyed
three completed cells. `--resume` loads what is already recorded, keeps it, and
runs only what is missing — including a cell that finished some of its repeats.
Nothing completed is ever re-paid for, and nothing completed is ever overwritten.

BOUNDED CALLS

The SDK defaults to a 600s read timeout with 2 retries, so one stalled request
can hold a cell for ~30 minutes, and `explore`'s own time budget cannot stop it —
that budget is checked between turns, never during a call. This script therefore
passes an explicit, much smaller timeout. A stalled call now fails fast and is
RECORDED as a failed observation rather than silently retried or dropped: a
calibration that quietly discards its slow runs is measuring the wrong
population.
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

# An explicit ceiling on any single API call, well under the SDK's effective
# worst case (600s read x 3 attempts). Chosen against measured behaviour: a
# healthy investigation turn on `fastapi` ran well inside two minutes, and the
# planning call inside 140s, so 180s admits every observation we have actually
# seen while cutting a stall short by an order of magnitude.
#
# `max_retries=0` is deliberate. The SDK's silent retries are what turned a
# stalled call into a half-hour outage with nothing in the log; here a failure
# should surface immediately and be recorded, because a failed observation is
# data about the run, not noise to be papered over.
CALL_TIMEOUT_SECONDS = 180.0
SDK_MAX_RETRIES = 0


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


def run_cell(
    name: str,
    repo_url: str,
    code_depth: str,
    repeats: int,
    client,
    previous: dict | None = None,
) -> dict:
    """One cell. `previous` carries any repeats already recorded for it.

    A cell that already has a dossier and some good repeats only pays for the
    repeats it is missing — the investigation is the expensive stage, and
    re-running it would also change what the remaining repeats are measured
    against, quietly splitting one cell across two dossiers.
    """
    goal = goal_for(repo_url, code_depth)
    done = [r for r in (previous or {}).get("runs", []) if r.get("ok")]
    if len(done) >= repeats:
        print(f"  {name}: already complete ({len(done)} repeats) — skipped", flush=True)
        return previous  # type: ignore[return-value]

    if done:
        # A partially-finished cell cannot be topped up: its repeats were planned
        # against a dossier that no longer exists in memory. Redoing the whole
        # cell is the only way to keep all repeats comparable, so say so rather
        # than silently mixing two populations.
        print(
            f"  {name}: {len(done)} repeat(s) recorded but the dossier is gone; "
            f"re-running the cell whole so all repeats share one dossier",
            flush=True,
        )

    print(f"  {name}: investigating ...", flush=True)
    started = time.time()
    try:
        base = run_pipeline(repo_url, goal, client=client)
    except Exception as exc:
        return {
            "cell": name, "code_depth": code_depth, "ok": False,
            "died": "investigation raised",
            "errors": [f"{type(exc).__name__}: {exc}"],
            "seconds": round(time.time() - started, 1),
        }
    investigate_seconds = round(time.time() - started, 1)

    if base.investigation is None or base.graph is None:
        return {
            "cell": name, "code_depth": code_depth, "ok": False,
            "died": "no dossier", "errors": base.errors[-4:],
            "investigate_seconds": investigate_seconds,
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
            # A failed repeat is an OBSERVATION, kept with its cause. Dropping it
            # would quietly narrow the population the bands are fitted to, and a
            # calibration that discards its slow or failed runs is measuring
            # something other than what the user will experience.
            errors = list(state.errors)[-3:]
            runs.append({
                "repeat": i + 1,
                "ok": False,
                "seconds": seconds,
                "failure": _classify(errors, seconds),
                "errors": errors,
            })
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


_TIMEOUT_MARKERS = ("timeout", "timed out", "readtimeout", "connecterror", "apiconnection")


def _classify(errors: list[str], seconds: float) -> str:
    """Why a repeat produced nothing. Named, not lumped into one bucket.

    A timeout and a malformed proposal are different facts about the run: the
    first says the call never landed, the second says the planner did and its
    answer was unusable. Reporting both as "failed" would hide exactly the
    distinction this hardening exists to expose.
    """
    blob = " ".join(errors).lower()
    if any(marker in blob for marker in _TIMEOUT_MARKERS):
        return "timeout"
    if seconds >= CALL_TIMEOUT_SECONDS:
        # No marker, but it ran to the ceiling — the SDK's exception text varies
        # by transport, so duration is the corroborating signal.
        return "timeout_suspected"
    if "truncated" in blob or "unterminated" in blob:
        return "truncated_proposal"
    return "other"


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
        s, band = r.get("spread") or {}, r.get("band", [0, 0])
        good = [x for x in r.get("runs", []) if x.get("ok")]
        failed = [x for x in r["runs"] if not x.get("ok")]
        print(
            f"  band {band[0]}-{band[1]}   "
            f"({len(good)} good / {len(r.get('runs', []))} repeats)"
        )
        for f in failed:
            print(
                f"    FAILED repeat #{f['repeat']}: {f.get('failure')} "
                f"after {f.get('seconds')}s — {(f.get('errors') or [''])[-1][:90]}"
            )
        if not s:
            # No usable repeats. Say so rather than crashing the whole report —
            # one barren cell must not cost the summary of every other.
            print("    (no successful repeats — nothing to summarise)")
            continue
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
        s, band = r.get("spread") or {}, r.get("band", [0, 0])
        if not r.get("ok") or not s:
            continue
        total = len(r.get("runs", []))
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


def load_existing(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        return {c["cell"]: c for c in json.loads(path.read_text(encoding="utf-8"))}
    except Exception as exc:
        print(f"could not read {path}: {exc}", file=sys.stderr)
        return {}


def complete(cell: dict | None, repeats: int) -> bool:
    if not cell or not cell.get("ok"):
        return False
    return sum(1 for r in cell.get("runs", []) if r.get("ok")) >= repeats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--only")
    parser.add_argument("--resume", action="store_true",
                        help="keep everything already recorded; run only what is missing")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out", default="docs/planning/phases/evidence")
    args = parser.parse_args()

    matrix = cells() if not args.only else {args.only: cells()[args.only]}
    path = Path(args.out) / "band-calibration.json"

    # Always read what is on disk, even without --resume. Loading it only when
    # resuming is what made the guard below unreachable: `existing` was empty
    # precisely in the case the guard exists to catch. Found by the flag's own
    # test, which started a live run instead of refusing.
    on_disk = load_existing(path)
    existing = on_disk if args.resume else {}

    todo = {
        name: spec for name, spec in matrix.items()
        if not complete(existing.get(name), args.repeats)
    }

    if args.dry_run:
        print("cells in matrix:", ", ".join(matrix))
        if args.resume:
            keep = [n for n in existing if complete(existing[n], args.repeats)]
            print("already complete (kept, not re-run):", ", ".join(keep) or "none")
        print("to run:", ", ".join(todo) or "none")
        print("repeats per cell:", args.repeats)
        print("planning calls:", len(todo) * args.repeats)
        print("investigations:", len(todo), "(one per cell, shared by repeats)")
        print(f"per-call timeout: {CALL_TIMEOUT_SECONDS}s, sdk retries: {SDK_MAX_RETRIES}")
        print("bands (unchanged):", _SCOPE_BANDS)
        return 0

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY missing", file=sys.stderr)
        return 2

    if not args.resume and on_disk:
        # The defect that made a partial rerun destructive. Refuse rather than
        # overwrite: evidence that cost real money should not be lost to a
        # forgotten flag.
        print(
            f"{path} already holds {len(on_disk)} cell(s): "
            f"{', '.join(on_disk)}.\n"
            f"Re-run with --resume to keep them, or pass a different --out to "
            f"start a fresh matrix.",
            file=sys.stderr,
        )
        return 3

    os.environ["CODEONBOARD_CURRICULUM"] = "1"
    client = anthropic.Anthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        timeout=CALL_TIMEOUT_SECONDS,
        max_retries=SDK_MAX_RETRIES,
    )

    # Completed cells are carried through untouched, in matrix order, so a
    # resumed run writes a whole matrix rather than a fragment of one.
    collected: dict[str, dict] = dict(existing)

    def flush() -> None:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        ordered = [collected[n] for n in matrix if n in collected]
        ordered += [c for n, c in collected.items() if n not in matrix]
        path.write_text(json.dumps(ordered, indent=2), encoding="utf-8")

    for name, (repo_url, depth) in matrix.items():
        if name not in todo:
            print(f"cell {name}: complete, kept as recorded", flush=True)
            continue
        print(f"cell {name} ...", flush=True)
        try:
            collected[name] = run_cell(
                name, repo_url, depth, args.repeats, client, existing.get(name)
            )
        except Exception as exc:  # a dead cell must not lose the others
            collected[name] = {"cell": name, "ok": False, "died": repr(exc)}
        # Written after every cell: a long matrix must not lose everything to a
        # failure in its last one.
        flush()

    report([collected[n] for n in matrix if n in collected])
    print(f"\nwritten: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
