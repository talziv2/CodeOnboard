"""
End-to-end smoke test exercising all four mentor agent retrieval paths.

Runs the Code Structure Agent once, then the Mentor Agent four times with
one goal per goal_type. Prints each learning path so the different
retrieval strategies can be compared side by side.

Run with:
    .venv\\Scripts\\python.exe scripts\\smoke_onboard.py
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


REPO_URL = "https://github.com/psf/requests"


GOALS: dict[str, dict] = {
    "understand_system": {
        "primary_goal": "get a high-level tour of the requests library",
        "goal_type": "understand_system",
        "focus_area": "overall architecture",
        "experience_level": "intermediate",
        "depth": "overview",
        "target_repo": REPO_URL,
        "familiarity": "new to requests internals",
        "background": "5 years of Python",
    },
    "understand_component": {
        "primary_goal": "understand how authentication works in requests",
        "goal_type": "understand_component",
        "focus_area": "authentication",
        "experience_level": "intermediate",
        "depth": "deep",
        "target_repo": REPO_URL,
        "familiarity": "new to requests internals",
        "background": "5 years of Python",
    },
    "contribute_code": {
        "primary_goal": "add OAuth2 client-credentials support",
        "goal_type": "contribute_code",
        "focus_area": "authentication",
        "experience_level": "intermediate",
        "depth": "deep",
        "target_repo": REPO_URL,
        "familiarity": "new to requests internals",
        "background": "5 years of Python",
        "contribution_context": "want to add a new auth class for OAuth2 client credentials flow",
    },
    "debug_issue": {
        "primary_goal": "fix SSL verification error",
        "goal_type": "debug_issue",
        "focus_area": "transport",
        "experience_level": "intermediate",
        "depth": "deep",
        "target_repo": REPO_URL,
        "familiarity": "new to requests internals",
        "background": "5 years of Python",
        "error_description": "SSLError on every HTTPS request after urllib3 upgrade",
        "tried_so_far": "verified certs are valid, downgraded urllib3, no luck",
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
