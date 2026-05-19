# Pipeline runner — sequential agent chain.
#
# Phase 1: plain Python function chain (no LangGraph). Each agent reads/writes
# OnboardState; the runner short-circuits if the Code Structure Agent fails to
# produce a module_map (without it, the Mentor Agent has nothing to ground on).

import anthropic

from backend.agents import run_code_structure, run_mentor, run_prioritization
from backend.pipeline.state import OnboardState


def run_pipeline(
    repo_url: str,
    goal: dict,
    client: anthropic.Anthropic | None = None,
) -> OnboardState:
    state = OnboardState(repo_url=repo_url, goal=goal)

    run_code_structure(state, client=client)

    if state.module_map is None:
        return state

    # Prioritization narrows the module map before the Mentor Agent runs.
    # On failure it leaves relevant_modules None — the Mentor Agent then
    # falls back to the full map, so this step never blocks the pipeline.
    run_prioritization(state, client=client)

    run_mentor(state, client=client)
    return state
