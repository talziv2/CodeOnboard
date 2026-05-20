# LangGraph orchestration for the onboarding pipeline.
#
# Graph shape (Phase 2 migration; logically equivalent to the Phase 1
# sequential runner):
#
#     START -> code_structure --(module_map set?)-- yes -> prioritization -> mentor -> END
#                                              \--- no  -> END
#
# The Goal Agent is intentionally NOT a node here — it runs upstream of the
# pipeline as a multi-turn HTTP dialogue via /goal/start and /goal/answer
# (see backend/api.py). By the time invoke() is called, `goal` is finalized
# input.

from langgraph.graph import END, START, StateGraph

from backend.pipeline.state import OnboardState


def _new_errors(prev: list, current: list) -> list:
    # Agents mutate state.errors in place by appending. The errors field has an
    # operator.add reducer, so we must return ONLY the newly-appended items —
    # returning the full list would cause the reducer to duplicate prior errors.
    return current[len(prev):]


def code_structure_node(state: OnboardState) -> dict:
    # Deferred import breaks the runner <-> graph circular import. Routing
    # through `runner` (rather than importing the agent directly) preserves
    # the existing test pattern of patching backend.pipeline.runner.run_*.
    from backend.pipeline import runner

    prev_errors = list(state.errors)
    runner.run_code_structure(state, client=state.client)
    return {
        "repo_path": state.repo_path,
        "module_map": state.module_map,
        "chunks_embedded": state.chunks_embedded,
        "errors": _new_errors(prev_errors, state.errors),
    }


def prioritization_node(state: OnboardState) -> dict:
    from backend.pipeline import runner

    prev_errors = list(state.errors)
    runner.run_prioritization(state, client=state.client)
    return {
        "relevant_modules": state.relevant_modules,
        "errors": _new_errors(prev_errors, state.errors),
    }


def mentor_node(state: OnboardState) -> dict:
    from backend.pipeline import runner

    prev_errors = list(state.errors)
    runner.run_mentor(state, client=state.client)
    return {
        "learning_path": state.learning_path,
        "confidence": state.confidence,
        "errors": _new_errors(prev_errors, state.errors),
    }


def route_after_code_structure(state: OnboardState) -> str:
    # Mirrors the Phase 1 short-circuit: without a module_map the Mentor Agent
    # has nothing to ground on, so skip the rest of the pipeline.
    return "prioritization" if state.module_map is not None else END


def build_graph():
    graph = StateGraph(OnboardState)

    graph.add_node("code_structure", code_structure_node)
    graph.add_node("prioritization", prioritization_node)
    graph.add_node("mentor", mentor_node)

    graph.add_edge(START, "code_structure")
    graph.add_conditional_edges(
        "code_structure",
        route_after_code_structure,
        {"prioritization": "prioritization", END: END},
    )
    graph.add_edge("prioritization", "mentor")
    graph.add_edge("mentor", END)

    return graph.compile()
