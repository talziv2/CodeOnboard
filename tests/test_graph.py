"""
Pytest tests for the LangGraph pipeline graph.
Run with: uv run pytest tests/test_graph.py -v
"""
from unittest.mock import MagicMock, patch

from backend.pipeline.graph import build_graph, route_after_code_structure
from backend.pipeline.state import OnboardState


FAKE_REPO_URL = "https://github.com/psf/requests"
FAKE_GOAL = {
    "primary_goal": "understand authentication",
    "goal_type": "understand_component",
    "focus_area": "authentication",
    "experience_level": "intermediate",
    "depth": "deep",
    "target_repo": FAKE_REPO_URL,
    "familiarity": "new",
    "background": "5 years Python",
}


def _populate_module_map(state, client=None):
    state.repo_path = "data/repos/requests"
    state.module_map = {"auth": {"purpose": "x", "key_files": [], "exports": [], "dependencies": []}}
    state.chunks_embedded = True
    return state


def _populate_learning_path(state, client=None):
    state.learning_path = [{"step": 1, "title": "x", "file": "requests/auth.py",
                            "line_range": [1, 10], "why": "x", "understand": "x", "concepts": []}]
    state.confidence = "high"
    return state


def test_build_graph_compiles_and_registers_three_nodes():
    graph = build_graph()
    # get_graph() returns a stable serializable view across LangGraph versions;
    # its .nodes is a dict keyed by node name.
    node_names = set(graph.get_graph().nodes.keys())
    assert "code_structure" in node_names
    assert "prioritization" in node_names
    assert "mentor" in node_names


def test_router_returns_prioritization_when_module_map_present():
    state = OnboardState(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    state.module_map = {"auth": {}}
    assert route_after_code_structure(state) == "prioritization"


def test_router_returns_end_when_module_map_missing():
    from langgraph.graph import END
    state = OnboardState(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    state.module_map = None
    assert route_after_code_structure(state) == END


@patch("backend.pipeline.runner.run_mentor", side_effect=_populate_learning_path)
@patch("backend.pipeline.runner.run_code_structure", side_effect=_populate_module_map)
def test_graph_reaches_mentor_when_module_map_populated(mock_cs, mock_mentor):
    from backend.pipeline.runner import run_pipeline
    state = run_pipeline(FAKE_REPO_URL, FAKE_GOAL, client=MagicMock())
    mock_cs.assert_called_once()
    mock_mentor.assert_called_once()
    assert state.module_map is not None
    assert state.learning_path is not None
    assert state.confidence == "high"


@patch("backend.pipeline.runner.run_mentor")
@patch("backend.pipeline.runner.run_code_structure")
def test_graph_skips_mentor_when_module_map_missing(mock_cs, mock_mentor):
    def cs_failed(state, client=None):
        state.errors.append("cloner failed: boom")
        return state  # module_map stays None

    mock_cs.side_effect = cs_failed
    from backend.pipeline.runner import run_pipeline
    state = run_pipeline(FAKE_REPO_URL, FAKE_GOAL, client=MagicMock())
    mock_mentor.assert_not_called()
    assert state.module_map is None
    assert state.learning_path is None
    # Reducer should preserve the error from code_structure.
    assert "cloner failed: boom" in state.errors


@patch("backend.pipeline.runner.run_mentor", side_effect=_populate_learning_path)
@patch("backend.pipeline.runner.run_code_structure")
def test_graph_errors_accumulate_via_reducer(mock_cs, mock_mentor):
    # Code Structure succeeds (module_map populated) but appends a soft warning.
    def cs_with_warning(state, client=None):
        _populate_module_map(state, client)
        state.errors.append("soft warning: chunk count low")
        return state

    mock_cs.side_effect = cs_with_warning
    from backend.pipeline.runner import run_pipeline
    state = run_pipeline(FAKE_REPO_URL, FAKE_GOAL, client=MagicMock())
    # The reducer should NOT duplicate the error (we return only new errors
    # from each node, not the full accumulated list).
    assert state.errors.count("soft warning: chunk count low") == 1
