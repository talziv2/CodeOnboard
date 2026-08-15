"""§14 #16 — what does a session actually cost, and which part drives it?

    uv run python scripts/measure_cost.py --dry-run
    uv run python scripts/measure_cost.py
    uv run python scripts/measure_cost.py --journey 12

MEASURES THE SYSTEM AS IT IS. No prompt, model or behaviour change is made to
chase the $0.10 target — the point is to find out where the money goes, and a
measurement taken while tuning the thing measured is worth nothing.

WHY NOT ONE BLENDED NUMBER

"A session costs $X" hides the only two questions worth asking: is the budget
spent once at planning time or repeatedly at session time, and does adaptation
change the answer. So this reports:

  PLANNING TIME   paid once per session: survey, documentation, investigation,
                  and the planner itself, attributed per stage.
  SESSION TIME    paid per unit or per answer: the lesson, the grade, and
                  whichever adaptation the gap earned.

and then projects a whole journey from those parts.

HOW SCENARIOS ARE FORCED

Each adaptation scenario needs a specific `gap_kind`, which is the Grader's
judgement and not ours to command. So the Grader is CALLED FOR REAL — its cost
is measured, not estimated — and only its parsed verdict is overridden
afterwards. The alternative, stubbing the call out and adding a constant back,
would report a grading cost nobody had observed.

Every scenario runs against the same planned graph, on a deep copy, so scenarios
cannot contaminate each other's node state.
"""

import argparse
import copy
import json
import os
import sys
import time
from collections import defaultdict
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
from backend.agents.mentor.mutator import mutate as mutate_graph  # noqa: E402
from backend.agents.teaching import respond as teaching_respond  # noqa: E402
from backend.agents.teaching import run as run_teaching  # noqa: E402
from backend.agents.teaching.agent import _read_node_source  # noqa: E402
from backend.pipeline.runner import (  # noqa: E402
    run_documentation,
    run_goal_investigation,
    run_mentor,
    run_repo_survey,
)
from backend.pipeline.state import OnboardState  # noqa: E402
from backend.repo.cloner import clone_repo  # noqa: E402
from backend.repo.explore import (  # noqa: E402
    CACHE_READ_MULTIPLIER,
    CACHE_WRITE_MULTIPLIER,
    PRICING,
)


REPO = "https://github.com/psf/requests"
GOAL = {
    "primary_goal": "understand how a request travels from the public API to the wire",
    "goal_type": "understand_architecture",
    "focus_area": "the request lifecycle",
    "code_depth": "working",
    "depth": "moderate",
    "target_repo": REPO,
    "familiarity": "Skimmed the README or docs",
    "background": "5 years of Python, some Django",
}

# A confident, on-topic, WRONG answer. Used for every graded scenario so the
# grading call's own cost is comparable across them; the verdict is overridden
# afterwards to force the gap being measured.
ANSWER = (
    "Session.send validates the URL and writes the bytes to the socket itself, "
    "then hands the raw response to the adapter to be parsed into a Response."
)


# ── recording ──────────────────────────────────────────────────────────────────


class RecordingClient:
    """A real client that records every call, tagged with the stage that made it.

    Wraps rather than subclasses: the agents receive this object and call
    `.messages.create(...)` exactly as they would the real one, so nothing in
    production has to know it is being measured.
    """

    def __init__(self, inner: anthropic.Anthropic):
        self._inner = inner
        self.stage = "unattributed"
        self.calls: list[dict] = []
        self.messages = _Messages(self)

    def record(self, model: str, response, seconds: float) -> None:
        usage = getattr(response, "usage", None)
        got = {
            "stage": self.stage,
            "model": model,
            "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
            "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
            "cache_write": int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
            "cache_read": int(getattr(usage, "cache_read_input_tokens", 0) or 0),
            "seconds": round(seconds, 1),
        }
        got["cost_usd"] = cost_of(got)
        self.calls.append(got)

    def drain(self) -> list[dict]:
        calls, self.calls = self.calls, []
        return calls

    def __getattr__(self, name):  # anything else the SDK exposes
        return getattr(self._inner, name)


class _Messages:
    def __init__(self, recorder: RecordingClient):
        self._recorder = recorder

    def create(self, **kwargs):
        started = time.time()
        response = self._recorder._inner.messages.create(**kwargs)
        self._recorder.record(kwargs.get("model", "?"), response, time.time() - started)
        return response


def cost_of(call: dict) -> float:
    """One call's cost at list price, using the repo's existing rate table."""
    rates = PRICING.get(call["model"])
    if rates is None:
        return 0.0
    per_in, per_out = rates
    billed_in = (
        call["input_tokens"]
        + call["cache_write"] * CACHE_WRITE_MULTIPLIER
        + call["cache_read"] * CACHE_READ_MULTIPLIER
    )
    return (billed_in * per_in + call["output_tokens"] * per_out) / 1_000_000


def summarise(calls: list[dict]) -> dict:
    return {
        "calls": len(calls),
        "input_tokens": sum(c["input_tokens"] for c in calls),
        "output_tokens": sum(c["output_tokens"] for c in calls),
        "cache_read": sum(c["cache_read"] for c in calls),
        "cost_usd": round(sum(c["cost_usd"] for c in calls), 6),
        "seconds": round(sum(c["seconds"] for c in calls), 1),
    }


# ── planning time ──────────────────────────────────────────────────────────────


def measure_planning(recorder: RecordingClient) -> tuple[OnboardState, dict]:
    """Run the stages individually so each one's cost is attributable.

    This is the same sequence `build_graph()` wires together; calling them
    directly buys per-stage attribution, which one `run_pipeline` call cannot
    give because every stage's calls would land in the same undifferentiated pile.
    """
    state = OnboardState(repo_url=REPO, goal=dict(GOAL))
    state.client = recorder
    stages: dict[str, dict] = {}

    def record(label: str, fn) -> None:
        recorder.stage = label
        started = time.time()
        fn()
        calls = recorder.drain()
        stages[label] = summarise(calls) | {"wall_seconds": round(time.time() - started, 1)}
        stages[label]["models"] = sorted({c["model"] for c in calls})

    for label, fn in (
        ("repo_survey", lambda: run_repo_survey(state, client=recorder)),
        ("documentation", lambda: run_documentation(state)),
        ("goal_investigation", lambda: run_goal_investigation(state, client=recorder)),
    ):
        record(label, fn)

    # BOTH planners, against the SAME dossier. The flag still defaults to 0, so
    # measuring only the objective-first planner would price something nobody
    # runs today, and measuring only the old one would price something this
    # phase exists to replace. One call each makes the comparison nearly free —
    # and it is exactly the number needed to decide what flipping the default
    # costs.
    os.environ["CODEONBOARD_CURRICULUM"] = "0"
    legacy = OnboardState(repo_url=REPO, goal=dict(GOAL), client=recorder)
    legacy.repo_path = state.repo_path
    legacy.investigation = state.investigation
    legacy.doc_context = state.doc_context
    record("mentor (flag=0, pre-B3)", lambda: run_mentor(legacy, client=recorder))

    os.environ["CODEONBOARD_CURRICULUM"] = "1"
    record("mentor (flag=1, B3)", lambda: run_mentor(state, client=recorder))

    return state, stages


# ── session time ───────────────────────────────────────────────────────────────


def forced_grade(state, answer, classification, gap_kind, recorder):
    """Call the real Grader, then overwrite its verdict.

    The call is genuine, so its cost is measured rather than assumed; only the
    judgement is replaced, because a scenario needs a specific gap and the
    Grader is not ours to instruct.
    """
    run_grader(state, answer, client=recorder)
    node_id = state.graph.current_node_id
    state.last_grade = {
        "classification": classification,
        "gap_kind": gap_kind,
        "rationale": "forced for measurement",
    }
    mapping = {"understood": "understood", "partial": "partial", "confused": "failed"}
    if classification in mapping:
        state.graph.mark_understanding(node_id, mapping[classification])


SCENARIOS = [
    ("happy_path", "understood", "none"),
    ("no_attempt_hint", "off-topic", "no_attempt"),
    ("wrong_altitude_followup", "confused", "right_idea_wrong_altitude"),
    ("wrong_model_reteach", "confused", "wrong_model"),
    ("missing_prerequisite", "confused", "missing_prerequisite"),
]


def measure_scenario(
    name: str, classification: str, gap_kind: str,
    planned: OnboardState, recorder: RecordingClient, repo_path: str,
) -> dict:
    graph = copy.deepcopy(planned.graph)
    state = OnboardState(repo_url=REPO, goal=dict(GOAL), client=recorder)
    state.repo_path = repo_path
    state.graph = graph
    state.doc_context = planned.doc_context
    state.investigation = planned.investigation

    node = graph.nodes[graph.current_node_id]
    node.cached_lesson = None          # force a real render
    parts: dict[str, dict] = {}

    recorder.stage = f"{name}:lesson"
    run_teaching(state, client=recorder)
    parts["lesson"] = summarise(recorder.drain())

    recorder.stage = f"{name}:grade"
    forced_grade(state, ANSWER, classification, gap_kind, recorder)
    parts["grade"] = summarise(recorder.drain())

    recorder.stage = f"{name}:adaptation"
    rationale = "forced for measurement"
    if gap_kind == "no_attempt":
        teaching_respond.hint(state, node, ANSWER, rationale, client=recorder)
    elif gap_kind == "right_idea_wrong_altitude":
        teaching_respond.followup(state, node, ANSWER, rationale, client=recorder)
    elif gap_kind == "wrong_model":
        source = _read_node_source(repo_path, node)
        teaching_respond.reteach(state, node, ANSWER, rationale, source, client=recorder)
    elif gap_kind == "missing_prerequisite":
        mutation_state = OnboardState(repo_url=REPO, goal=dict(GOAL), client=recorder)
        mutation_state.graph = graph
        mutation_state.repo_path = repo_path
        mutation_state.investigation = planned.investigation
        mutate_graph(mutation_state, "prerequisite", client=recorder)
    parts["adaptation"] = summarise(recorder.drain())

    total = {
        key: sum(p[key] for p in parts.values())
        for key in ("calls", "input_tokens", "output_tokens")
    }
    total["cost_usd"] = round(sum(p["cost_usd"] for p in parts.values()), 6)
    return {"scenario": name, "gap_kind": gap_kind, "parts": parts, "total": total}


# ── report ─────────────────────────────────────────────────────────────────────


def report(planning: dict, scenarios: list[dict], journey: int) -> None:
    line = "=" * 78
    print(f"\n{line}\nPLANNING TIME — paid once per session\n{line}")
    print(f"  {'stage':<22}{'calls':>6}{'in':>10}{'out':>9}{'cost':>10}  models")
    plan_total = 0.0
    for name, s in planning.items():
        # Only one planner runs in a real session; the other is measured for
        # comparison and must not be added twice.
        if not name.startswith("mentor (flag=0"):
            plan_total += s["cost_usd"]
        print(
            f"  {name:<22}{s['calls']:>6}{s['input_tokens']:>10}"
            f"{s['output_tokens']:>9}{s['cost_usd']:>10.4f}  {','.join(s['models']) or '-'}"
        )
    print(f"  {'TOTAL (with flag=1)':<22}{'':>6}{'':>10}{'':>9}{plan_total:>10.4f}")
    swap = (
        planning.get("mentor (flag=0, pre-B3)", {}).get("cost_usd", 0.0)
        - planning.get("mentor (flag=1, B3)", {}).get("cost_usd", 0.0)
    )
    print(f"  {'(flag=0 would be)':<22}{'':>6}{'':>10}{'':>9}{plan_total + swap:>10.4f}")

    print(f"\n{line}\nSESSION TIME — per unit / per answer\n{line}")
    happy = next(s for s in scenarios if s["scenario"] == "happy_path")
    base = happy["total"]["cost_usd"]
    print(f"  {'scenario':<26}{'calls':>6}{'in':>10}{'out':>9}{'cost':>10}{'vs happy':>11}")
    for s in scenarios:
        delta = s["total"]["cost_usd"] - base
        mark = "  (baseline)" if s["scenario"] == "happy_path" else f"{delta:>+11.4f}"
        print(
            f"  {s['scenario']:<26}{s['total']['calls']:>6}"
            f"{s['total']['input_tokens']:>10}{s['total']['output_tokens']:>9}"
            f"{s['total']['cost_usd']:>10.4f}{mark}"
        )

    print(f"\n  per-call breakdown:")
    for s in scenarios:
        bits = ", ".join(
            f"{k} {v['calls']}c/${v['cost_usd']:.4f}"
            for k, v in s["parts"].items() if v["calls"]
        )
        print(f"    {s['scenario']:<26}{bits}")

    print(f"\n{line}\nPROJECTED SESSION — {journey} units\n{line}")
    adaptations = {s["scenario"]: s["total"]["cost_usd"] - base for s in scenarios}
    all_happy = plan_total + journey * base
    print(f"  planning (once)                     {plan_total:>9.4f}")
    print(f"  {journey} x happy-path unit                {journey * base:>9.4f}")
    print(f"  every unit answered well            {all_happy:>9.4f}")
    for name, delta in adaptations.items():
        if name == "happy_path":
            continue
        print(f"    + one {name:<28}{all_happy + delta:>9.4f}")
    worst = all_happy + sum(d for n, d in adaptations.items() if n != "happy_path")
    print(f"  one of EVERY adaptation             {worst:>9.4f}")
    print(f"\n  target: $0.10/session")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--journey", type=int, default=12,
                        help="units in the projected session (calibration mean ~14)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out", default="docs/planning/phases/evidence")
    args = parser.parse_args()

    if args.dry_run:
        print("planning stages:", "repo_survey, documentation, goal_investigation, mentor")
        print("scenarios:", ", ".join(n for n, _, _ in SCENARIOS))
        print("projected journey length:", args.journey)
        print("pricing (USD/Mtok):", PRICING)
        print("CODEONBOARD_CURRICULUM:", os.environ.get("CODEONBOARD_CURRICULUM", "0"))
        return 0

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY missing", file=sys.stderr)
        return 2

    recorder = RecordingClient(
        anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=300.0)
    )

    print("planning ...", flush=True)
    planned, planning = measure_planning(recorder)
    if planned.graph is None:
        print("planning produced no graph:", planned.errors[-3:], file=sys.stderr)
        return 1
    print(f"  planned {len(planned.graph.nodes)} units", flush=True)

    repo_path = clone_repo(REPO)
    scenarios = []
    for name, classification, gap_kind in SCENARIOS:
        print(f"scenario {name} ...", flush=True)
        scenarios.append(
            measure_scenario(name, classification, gap_kind, planned, recorder, repo_path)
        )

    report(planning, scenarios, args.journey)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "curriculum_flag": os.environ.get("CODEONBOARD_CURRICULUM", "0"),
        "repo": REPO,
        "goal": GOAL,
        "units_planned": len(planned.graph.nodes),
        "pricing_usd_per_mtok": PRICING,
        "planning": planning,
        "scenarios": scenarios,
        "projected_journey_units": args.journey,
    }
    (out / "cost-measurement.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(f"\nwritten: {out / 'cost-measurement.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
