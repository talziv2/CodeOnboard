"""
End-to-end smoke test against fastapi/fastapi — the large stress-test repo.

Unlike the other smoke scripts, this one exists to measure the Prioritization
Agent's effect. fastapi has enough modules to cross MIN_MODULES_TO_PRIORITIZE,
so for each goal_type it runs the Mentor Agent TWICE:

  baseline  — relevant_modules = None  (Phase 1 behaviour, full module map)
  filtered  — relevant_modules set by the Prioritization Agent

then prints which modules were dropped and whether the learning path changed.

Run with:
    .venv\\Scripts\\python.exe scripts\\smoke_onboard_fastapi.py
"""
import json
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from backend.agents import run_code_structure, run_mentor, run_prioritization
from backend.pipeline.state import OnboardState


load_dotenv(override=True)


REPO_URL = "https://github.com/fastapi/fastapi"


GOALS: dict[str, dict] = {
    "understand_system": {
        "primary_goal": "get a high-level tour of how FastAPI handles a request",
        "goal_type": "understand_system",
        "focus_area": "overall request lifecycle",
        "experience_level": "intermediate",
        "depth": "overview",
        "target_repo": REPO_URL,
        "familiarity": "new to FastAPI internals",
        "background": "5 years of Python, used FastAPI as a user",
    },
    "understand_component": {
        "primary_goal": "understand how FastAPI's dependency injection works",
        "goal_type": "understand_component",
        "focus_area": "dependency injection and the Depends mechanism",
        "experience_level": "intermediate",
        "depth": "deep",
        "target_repo": REPO_URL,
        "familiarity": "new to FastAPI internals",
        "background": "5 years of Python",
    },
    "contribute_code": {
        "primary_goal": "add a new parameter source for request trailers",
        "goal_type": "contribute_code",
        "focus_area": "request parameter extraction",
        "experience_level": "intermediate",
        "depth": "deep",
        "target_repo": REPO_URL,
        "familiarity": "new to FastAPI internals",
        "background": "5 years of Python",
        "contribution_context": "want to add a Trailer() param source alongside Header/Query/Path",
    },
    "debug_issue": {
        "primary_goal": "fix a response model validation error",
        "goal_type": "debug_issue",
        "focus_area": "response serialization",
        "experience_level": "intermediate",
        "depth": "deep",
        "target_repo": REPO_URL,
        "familiarity": "new to FastAPI internals",
        "background": "5 years of Python",
        "error_description": "ResponseValidationError raised for a field that is valid in the route's return type",
        "tried_so_far": "confirmed the Pydantic model is correct in isolation",
    },
}


def _print_header(title: str) -> None:
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def _path_summary(state: OnboardState) -> tuple[int, list[str]]:
    if not state.learning_path:
        return 0, []
    # The LLM normalizes path separators inconsistently between runs, so
    # fold to '/' before comparing — otherwise the baseline/filtered diff
    # reports every file as changed.
    files = sorted(
        {step["file"].replace("\\", "/") for step in state.learning_path}
    )
    return len(state.learning_path), files


def _run_mentor(base: OnboardState, goal: dict, relevant: list[str] | None) -> OnboardState:
    state = OnboardState(
        repo_url=base.repo_url,
        goal=deepcopy(goal),
        repo_path=base.repo_path,
        module_map=deepcopy(base.module_map),
        relevant_modules=relevant,
        chunks_embedded=base.chunks_embedded,
    )
    run_mentor(state)
    return state


def main() -> None:
    print(f"Running Code Structure Agent once on {REPO_URL}...")
    base_state = OnboardState(repo_url=REPO_URL)
    run_code_structure(base_state)

    if base_state.module_map is None:
        print(f"Code Structure Agent failed: {base_state.errors}")
        return

    all_modules = list(base_state.module_map)
    print(f"module_map keys ({len(all_modules)}):")
    for key in all_modules:
        print(f"  - {key}")

    for label, goal in GOALS.items():
        _print_header(f"goal_type = {label}")

        # 1. Prioritization Agent — what does it keep / drop?
        prio_state = OnboardState(
            repo_url=base_state.repo_url,
            goal=deepcopy(goal),
            repo_path=base_state.repo_path,
            module_map=deepcopy(base_state.module_map),
            chunks_embedded=base_state.chunks_embedded,
        )
        run_prioritization(prio_state)
        relevant = prio_state.relevant_modules
        if prio_state.errors:
            print(f"prioritization errors: {prio_state.errors}")
        if relevant is None:
            print("prioritization: no filtering (relevant_modules=None) — full map kept")
        else:
            dropped = sorted(set(all_modules) - set(relevant))
            print(f"prioritization: kept {len(relevant)}/{len(all_modules)} modules")
            print(f"  kept:    {sorted(relevant)}")
            print(f"  dropped: {dropped}")

        # 2. Mentor — baseline (no prioritization) vs filtered.
        baseline = _run_mentor(base_state, goal, relevant=None)
        b_steps, b_files = _path_summary(baseline)
        print(f"\nbaseline   — confidence={baseline.confidence} "
              f"steps={b_steps} files={b_files}")
        if baseline.errors:
            print(f"  errors: {baseline.errors}")

        if relevant is None:
            print("filtered   — skipped (prioritization was a no-op)")
            continue

        filtered = _run_mentor(base_state, goal, relevant=relevant)
        f_steps, f_files = _path_summary(filtered)
        print(f"filtered   — confidence={filtered.confidence} "
              f"steps={f_steps} files={f_files}")
        if filtered.errors:
            print(f"  errors: {filtered.errors}")

        only_baseline = sorted(set(b_files) - set(f_files))
        only_filtered = sorted(set(f_files) - set(b_files))
        if not only_baseline and not only_filtered:
            print("diff       — same file set in both paths")
        else:
            print(f"diff       — only in baseline: {only_baseline}")
            print(f"             only in filtered: {only_filtered}")

        print("\nfiltered learning_path:")
        print(json.dumps(filtered.learning_path, indent=2))


if __name__ == "__main__":
    main()
