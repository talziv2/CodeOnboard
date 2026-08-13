# Pipeline runner — public entry point for the onboarding pipeline.
#
# One compiled LangGraph, built once at import. Stage 5 removed the second
# graph shape and the CODEONBOARD_EXPLORER flag that selected it: there is now
# a single production path, so there is nothing to choose between.
#
# Note: run_mentor / run_repo_survey / run_goal_investigation / run_reviewer are
# re-imported at module level so tests (and the graph nodes) can patch them at
# backend.pipeline.runner.run_*.

import anthropic

from backend.agents import run_documentation, run_mentor, run_reviewer  # re-exported  # noqa: F401
from backend.pipeline.explorer_nodes import run_goal_investigation, run_repo_survey  # re-exported  # noqa: F401
from backend.pipeline.state import OnboardState

# The graph imports this module lazily (inside its node functions) to break the
# circular import.
from backend.pipeline.graph import build_graph  # noqa: E402

_graph = build_graph()


def run_pipeline(
    repo_url: str,
    goal: dict,
    client: anthropic.Anthropic | None = None,
) -> OnboardState:
    initial = OnboardState(repo_url=repo_url, goal=goal, client=client)
    final = _graph.invoke(initial)
    # LangGraph returns the compiled state. With a dataclass schema it is
    # already an OnboardState in current versions; fall back to constructing
    # one from a dict in case the runtime returns a mapping.
    if isinstance(final, OnboardState):
        return final
    return OnboardState(**final)
