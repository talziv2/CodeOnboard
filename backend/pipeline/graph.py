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


def _extract_new_errors(state: OnboardState, prev: list) -> list:
    # Agents mutate state.errors in place by appending. Because LangGraph
    # tracks the same list reference, those appends are already visible in
    # the reducer's "current" value. If we also returned the new items, the
    # operator.add reducer would double-count them. So we (a) compute the
    # diff, then (b) roll state.errors back to its pre-node value, leaving
    # the reducer as the sole accumulator.
    new_errors = state.errors[len(prev):]
    state.errors[:] = prev
    return new_errors


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
        "errors": _extract_new_errors(state, prev_errors),
    }


def prioritization_node(state: OnboardState) -> dict:
    from backend.pipeline import runner

    prev_errors = list(state.errors)
    runner.run_prioritization(state, client=state.client)
    return {
        "relevant_modules": state.relevant_modules,
        "errors": _extract_new_errors(state, prev_errors),
    }


def mentor_node(state: OnboardState) -> dict:
    from backend.pipeline import runner

    prev_errors = list(state.errors)
    runner.run_mentor(state, client=state.client)
    return {
        # Phase 3: state.graph is the source of truth; learning_path is
        # derived inside run_mentor by walking sequence edges. Both fields
        # come out of the same single Sonnet call.
        "graph": state.graph,
        "learning_path": state.learning_path,
        "confidence": state.confidence,
        "errors": _extract_new_errors(state, prev_errors),
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
