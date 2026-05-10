"""
End-to-end smoke test for the Phase 1 pipeline.

Run with:
    .venv\\Scripts\\python.exe scripts\\test_onboard.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from backend.pipeline.runner import run_pipeline


load_dotenv()


GOAL = {
    "primary_goal": "understand how authentication works in requests",
    "goal_type": "understand_component",
    "focus_area": "authentication",
    "experience_level": "intermediate",
    "depth": "deep",
    "target_repo": "https://github.com/psf/requests",
    "familiarity": "new to requests internals",
    "background": "5 years of Python",
}


def main() -> None:
    print("Running pipeline on psf/requests… (first run ~1 min, later runs ~10s)")
    state = run_pipeline("https://github.com/psf/requests", GOAL)

    print("\n── errors ──")
    print(state.errors or "none")

    print("\n── confidence ──")
    print(state.confidence)

    print("\n── learning_path ──")
    if state.learning_path:
        print(json.dumps(state.learning_path, indent=2))
    else:
        print("(empty)")


if __name__ == "__main__":
    main()
