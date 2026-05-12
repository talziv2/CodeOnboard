"""
End-to-end smoke test against the 4D submarine path-optimization repo.

Mirrors scripts/smoke_onboard.py but targets a small, single-author
repo so we can see how the mentor agent behaves on a codebase very
different in shape from psf/requests.

Goals are drafted from the actual repo contents:
  main.py        — entrypoint that runs A* with two heuristics
  submarine.py   — GateSubmarineProblem (state, transitions, heuristic)
  search.py      — local copy of aima-python's search module
  utils.py       — helpers
  (aima-python/  — submodule, not fetched by our shallow cloner)

Run with:
    .venv\\Scripts\\python.exe scripts\\smoke_onboard_submarines.py
"""
import json
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from backend.agents import run_code_structure, run_mentor
from backend.pipeline.state import OnboardState


load_dotenv(override=True)


REPO_URL = "https://github.com/ShiraZakov/Dynamic4DPathOptimizationForSubmarines"


GOALS: dict[str, dict] = {
    "understand_system": {
        "primary_goal": "get a high-level tour of how the 4D submarine path planner works",
        "goal_type": "understand_system",
        "focus_area": "overall pathfinding architecture",
        "experience_level": "intermediate",
        "depth": "overview",
        "target_repo": REPO_URL,
        "familiarity": "comfortable with A* but new to this repo",
        "background": "AI coursework background, has implemented search before",
    },
    "understand_component": {
        "primary_goal": "understand how the submarine path planning problem is defined",
        "goal_type": "understand_component",
        "focus_area": "the GateSubmarineProblem state representation, transitions, and heuristic",
        "experience_level": "intermediate",
        "depth": "deep",
        "target_repo": REPO_URL,
        "familiarity": "comfortable with A* but new to this repo",
        "background": "AI coursework background",
    },
    "contribute_code": {
        "primary_goal": "add support for dynamic moving obstacles to the path planner",
        "goal_type": "contribute_code",
        "focus_area": "problem definition and transitions",
        "experience_level": "intermediate",
        "depth": "deep",
        "target_repo": REPO_URL,
        "familiarity": "comfortable with A* but new to this repo",
        "background": "AI coursework background",
        "contribution_context": (
            "want to extend GateSubmarineProblem so obstacles have positions "
            "that change with time t, and the planner avoids them at the "
            "specific timestep the submarine would be at that cell"
        ),
    },
    "debug_issue": {
        "primary_goal": "fix incorrect path costs returned by A*",
        "goal_type": "debug_issue",
        "focus_area": "cost accounting in the search loop",
        "experience_level": "intermediate",
        "depth": "deep",
        "target_repo": REPO_URL,
        "familiarity": "comfortable with A* but new to this repo",
        "background": "AI coursework background",
        "error_description": (
            "A* sometimes returns a path whose result.path_cost does not match "
            "the sum of _step_cost values printed for each step"
        ),
        "tried_so_far": (
            "verified _step_cost returns positive values, confirmed the initial "
            "state has cost 0, the discrepancy only shows up on paths that pass "
            "through at least one gate"
        ),
    },
}


def _print_header(title: str) -> None:
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def _print_result(state: OnboardState) -> None:
    print(f"errors:     {state.errors or 'none'}")
    print(f"confidence: {state.confidence}")
    if not state.learning_path:
        print("learning_path: (empty)")
        return
    files = sorted({step["file"] for step in state.learning_path})
    print(f"steps:      {len(state.learning_path)}")
    print(f"files ({len(files)}):")
    for f in files:
        print(f"  - {f}")
    print("\nlearning_path:")
    print(json.dumps(state.learning_path, indent=2))


def main() -> None:
    print(f"Running Code Structure Agent once on {REPO_URL}...")
    base_state = OnboardState(repo_url=REPO_URL)
    run_code_structure(base_state)

    if base_state.module_map is None:
        print(f"Code Structure Agent failed: {base_state.errors}")
        return

    print(f"module_map keys ({len(base_state.module_map)}):")
    for key in base_state.module_map:
        print(f"  - {key}")

    for label, goal in GOALS.items():
        _print_header(f"goal_type = {label}")
        state = OnboardState(
            repo_url=base_state.repo_url,
            goal=deepcopy(goal),
            repo_path=base_state.repo_path,
            module_map=deepcopy(base_state.module_map),
            chunks_embedded=base_state.chunks_embedded,
        )
        run_mentor(state)
        _print_result(state)


if __name__ == "__main__":
    main()
