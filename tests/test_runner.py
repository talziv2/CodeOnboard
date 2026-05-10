"""
Pytest tests for the pipeline runner using mocks.
Run with: uv run pytest tests/test_runner.py -v
"""
from unittest.mock import MagicMock, patch

from backend.pipeline.runner import run_pipeline
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


def _code_structure_side_effect(state, client=None):
    state.repo_path = "data/repos/requests"
    state.module_map = {"auth": {"purpose": "x", "key_files": [], "exports": [], "dependencies": []}}
    state.chunks_embedded = True
    return state


def _mentor_side_effect(state, client=None):
    state.learning_path = [{"step": 1, "title": "x", "file": "requests/auth.py",
                            "line_range": [1, 10], "why": "x", "understand": "x", "concepts": []}]
    state.confidence = "high"
    return state


@patch("backend.pipeline.runner.run_mentor", side_effect=_mentor_side_effect)
@patch("backend.pipeline.runner.run_code_structure", side_effect=_code_structure_side_effect)
def test_pipeline_returns_populated_state(mock_cs, mock_mentor):
    state = run_pipeline(FAKE_REPO_URL, FAKE_GOAL, client=MagicMock())
    assert isinstance(state, OnboardState)
    assert state.repo_url == FAKE_REPO_URL
    assert state.goal == FAKE_GOAL
    assert state.module_map is not None
    assert state.learning_path is not None
    assert state.confidence == "high"


@patch("backend.pipeline.runner.run_mentor", side_effect=_mentor_side_effect)
@patch("backend.pipeline.runner.run_code_structure", side_effect=_code_structure_side_effect)
def test_pipeline_calls_agents_in_order(mock_cs, mock_mentor):
    run_pipeline(FAKE_REPO_URL, FAKE_GOAL, client=MagicMock())
    mock_cs.assert_called_once()
    mock_mentor.assert_called_once()


@patch("backend.pipeline.runner.run_mentor")
@patch("backend.pipeline.runner.run_code_structure")
def test_pipeline_skips_mentor_when_module_map_missing(mock_cs, mock_mentor):
    def cs_failed(state, client=None):
        state.errors.append("cloner failed: boom")
        return state  # module_map stays None

    mock_cs.side_effect = cs_failed
    state = run_pipeline(FAKE_REPO_URL, FAKE_GOAL, client=MagicMock())
    mock_mentor.assert_not_called()
    assert state.module_map is None
    assert state.learning_path is None


@patch("backend.pipeline.runner.run_mentor", side_effect=_mentor_side_effect)
@patch("backend.pipeline.runner.run_code_structure", side_effect=_code_structure_side_effect)
def test_pipeline_passes_client_to_both_agents(mock_cs, mock_mentor):
    client = MagicMock()
    run_pipeline(FAKE_REPO_URL, FAKE_GOAL, client=client)
    assert mock_cs.call_args.kwargs.get("client") is client or mock_cs.call_args.args[1] is client
    assert mock_mentor.call_args.kwargs.get("client") is client or mock_mentor.call_args.args[1] is client


@patch("backend.pipeline.runner.run_mentor", side_effect=_mentor_side_effect)
@patch("backend.pipeline.runner.run_code_structure", side_effect=_code_structure_side_effect)
def test_pipeline_seeds_state_with_repo_url_and_goal(mock_cs, mock_mentor):
    run_pipeline(FAKE_REPO_URL, FAKE_GOAL, client=MagicMock())
    cs_state = mock_cs.call_args.args[0]
    assert cs_state.repo_url == FAKE_REPO_URL
    assert cs_state.goal == FAKE_GOAL
