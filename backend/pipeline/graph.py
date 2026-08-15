# LangGraph orchestration for the onboarding pipeline.
#
# ONE graph shape. Stage 5 deleted the RAG path and its flag:
#
#     START -> repo_survey --(skeleton ok?)-- yes -> documentation -> goal_investigation --(dossier?)-- yes --(reviewer needed?)-- yes -> reviewer -> mentor -> END
#                        \--- no  -> END                                                \--- no  -> END               \--- no  -> mentor -> END
#
#   repo_survey         clone + skeleton (the hard requirement, D15) + Layer B
#                       survey, persisted per (repo, commit) and reused +
#                       module_map derived from the survey's subsystems
#   documentation       no LLM; produces doc_context for the Teaching Agent
#   goal_investigation  D11: the ONLY exploration loop in the system, writing
#                       state.investigation for Reviewer and Mentor to read
#   reviewer            runs only for goal types that turn on architectural
#                       judgement; its findings reach the Mentor's prompt
#   mentor              plans the LearningGraph from the Dossier
#
# The Goal Agent is intentionally NOT a node here — it runs upstream of the
# pipeline as a multi-turn HTTP dialogue via /goal/start and /goal/answer
# (see backend/api.py). By the time invoke() is called, `goal` is finalized
# input.

from langgraph.graph import END, START, StateGraph

from backend.agents.reviewer.agent import should_run as _reviewer_should_run
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


def documentation_node(state: OnboardState) -> dict:
    from backend.pipeline import runner

    prev_errors = list(state.errors)
    runner.run_documentation(state)
    return {
        "doc_context": state.doc_context,
        "errors": _extract_new_errors(state, prev_errors),
    }


def reviewer_node(state: OnboardState) -> dict:
    from backend.pipeline import runner

    prev_errors = list(state.errors)
    runner.run_reviewer(state, client=state.client)
    return {
        "system_review": state.system_review,
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
        "plan_report": state.plan_report,
        "errors": _extract_new_errors(state, prev_errors),
    }


def repo_survey_node(state: OnboardState) -> dict:
    from backend.pipeline import runner

    prev_errors = list(state.errors)
    runner.run_repo_survey(state, client=state.client)
    return {
        "repo_path": state.repo_path,
        "module_map": state.module_map,
        "survey": state.survey,
        "errors": _extract_new_errors(state, prev_errors),
    }


def goal_investigation_node(state: OnboardState) -> dict:
    from backend.pipeline import runner

    prev_errors = list(state.errors)
    runner.run_goal_investigation(state, client=state.client)
    return {
        "investigation": state.investigation,
        "errors": _extract_new_errors(state, prev_errors),
    }


def route_after_repo_survey(state: OnboardState) -> str:
    # The skeleton is the hard requirement (D15); the survey is not — a
    # survey-less state still carries a skeleton-derived module_map. Only a
    # failed clone/skeleton (no repo_path or no module_map) ends the run.
    return "documentation" if state.repo_path and state.module_map else END


def route_after_investigation(state: OnboardState) -> str:
    # No dossier means the Mentor has nothing verified to plan from — end
    # explicitly rather than fabricating (D15). The reviewer, when it runs,
    # reads the same investigation (D11).
    if state.investigation is None:
        return END
    return "reviewer" if _reviewer_should_run(state.goal) else "mentor"


def build_graph():
    """The one production pipeline.

    Stage 5 removed the second shape. There is no `explorer` flag any more
    because there is no other path to select: repository preparation produces a
    Skeleton and a Survey, the Goal Investigation produces the Dossier, and the
    Mentor plans from it.
    """
    graph = StateGraph(OnboardState)

    graph.add_node("repo_survey", repo_survey_node)
    graph.add_node("documentation", documentation_node)
    graph.add_node("goal_investigation", goal_investigation_node)
    graph.add_node("reviewer", reviewer_node)
    graph.add_node("mentor", mentor_node)

    graph.add_edge(START, "repo_survey")
    graph.add_conditional_edges(
        "repo_survey",
        route_after_repo_survey,
        {"documentation": "documentation", END: END},
    )
    graph.add_edge("documentation", "goal_investigation")
    graph.add_conditional_edges(
        "goal_investigation",
        route_after_investigation,
        {"reviewer": "reviewer", "mentor": "mentor", END: END},
    )
    graph.add_edge("reviewer", "mentor")
    graph.add_edge("mentor", END)
    return graph.compile()
