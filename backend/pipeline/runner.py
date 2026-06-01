# Pipeline runner — public entry point for the onboarding pipeline.
#
# Phase 2: internals delegate to a LangGraph stateful graph (backend/pipeline/
# graph.py). The function signature is unchanged from Phase 1 so api.py and
# the existing tests keep working untouched.
#
# Note: run_code_structure / run_prioritization / run_mentor are re-imported
# at module level so tests (and the graph nodes) can patch them at
# backend.pipeline.runner.run_*.

import anthropic

from backend.agents import run_code_structure, run_documentation, run_mentor, run_prioritization  # re-exported  # noqa: F401
from backend.pipeline.state import OnboardState

# Compile the graph once at import. The graph itself imports this module
# lazily (inside its node functions) to break the circular import.
from backend.pipeline.graph import build_graph  # noqa: E402

_graph = build_graph()


def run_pipeline(
    repo_url: str,
    goal: dict,
    client: anthropic.Anthropic | None = None,
) -> OnboardState:
    initial = OnboardState(repo_url=repo_url, goal=goal, client=client)
    final = _graph.invoke(initial)
    # LangGraph returns the compiled state. With a dataclass schema it's
    # already an OnboardState in current versions; fall back to constructing
    # one from a dict in case the runtime returns a mapping.
    if isinstance(final, OnboardState):
        return final
    return OnboardState(**final)
