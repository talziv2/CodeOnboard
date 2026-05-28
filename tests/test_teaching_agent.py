"""
Pytest tests for the Teaching Agent using mocks.
Run with: uv run pytest tests/test_teaching_agent.py -v

No real Haiku, no real file reads, no real ChromaDB — source reading and
supporting-chunk retrieval are patched.
"""
import json
from unittest.mock import MagicMock, patch

from backend.agents.teaching import run
from backend.agents.teaching.agent import (
    LessonOutput,
    _build_prior_context,
    _parse_output,
)
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.pipeline.state import OnboardState


FAKE_REPO_URL = "https://github.com/psf/requests"
FAKE_REPO_PATH = "data/repos/requests"
FAKE_GOAL = {
    "primary_goal": "understand how authentication works",
    "goal_type": "understand_component",
    "focus_area": "authentication",
    "experience_level": "intermediate",
    "depth": "deep",
}

FAKE_SOURCE = "class HTTPBasicAuth:\n    def __call__(self, r):\n        ..."

FAKE_LESSON_OUTPUT = {
    "walkthrough": "`HTTPBasicAuth.__call__` attaches the Authorization header…",
    "prompt": "Before reading on: what do you think __call__ returns?",
    "expected_answer": "The mutated PreparedRequest with the auth header set.",
    "prompt_kind": "predict-then-reveal",
}


def _make_node(title: str = "Understand HTTPBasicAuth", understood: bool = False) -> LearningNode:
    node = LearningNode(
        title=title,
        code_anchor=CodeAnchor(file="requests/auth.py", line_start=72, line_end=100),
        concept_tags=["callable classes", "request signing"],
        lesson_brief={"why": "central auth abstraction", "understand": "how __call__ signs"},
    )
    if understood:
        node.understanding_state = "understood"
    return node


def _make_state_with_current_node() -> tuple[OnboardState, LearningNode]:
    state = OnboardState(repo_url=FAKE_REPO_URL)
    state.repo_path = FAKE_REPO_PATH
    state.goal = FAKE_GOAL
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    node = graph.add_node(_make_node())
    graph.set_current(node.id)
    state.graph = graph
    return state, node


def _make_mock_client(content: str) -> MagicMock:
    message = MagicMock()
    message.content = [MagicMock(text=content)]
    client = MagicMock()
    client.messages.create.return_value = message
    return client


# ── happy path ────────────────────────────────────────────────────────────────

@patch("backend.agents.teaching.agent.retrieve_supporting_chunks", return_value=[])
@patch("backend.agents.teaching.agent._read_source_lines", return_value=FAKE_SOURCE)
def test_run_sets_current_lesson(mock_read, mock_support):
    state, node = _make_state_with_current_node()
    client = _make_mock_client(json.dumps(FAKE_LESSON_OUTPUT))
    result = run(state, client=client)
    assert result.current_lesson is not None
    assert result.current_lesson["prompt_kind"] == "predict-then-reveal"
    assert result.current_lesson["walkthrough"].startswith("`HTTPBasicAuth")


@patch("backend.agents.teaching.agent.retrieve_supporting_chunks", return_value=[])
@patch("backend.agents.teaching.agent._read_source_lines", return_value=FAKE_SOURCE)
def test_run_caches_lesson_on_node(mock_read, mock_support):
    state, node = _make_state_with_current_node()
    client = _make_mock_client(json.dumps(FAKE_LESSON_OUTPUT))
    run(state, client=client)
    assert node.cached_lesson is not None
    assert node.cached_lesson == state.current_lesson


@patch("backend.agents.teaching.agent.retrieve_supporting_chunks", return_value=[])
@patch("backend.agents.teaching.agent._read_source_lines", return_value=FAKE_SOURCE)
def test_run_uses_haiku_model(mock_read, mock_support):
    state, node = _make_state_with_current_node()
    client = _make_mock_client(json.dumps(FAKE_LESSON_OUTPUT))
    run(state, client=client)
    assert client.messages.create.call_args.kwargs["model"] == "claude-haiku-4-5"


@patch("backend.agents.teaching.agent.retrieve_supporting_chunks", return_value=[])
@patch("backend.agents.teaching.agent._read_source_lines", return_value=FAKE_SOURCE)
def test_run_handles_fenced_json(mock_read, mock_support):
    state, node = _make_state_with_current_node()
    fenced = f"```json\n{json.dumps(FAKE_LESSON_OUTPUT)}\n```"
    client = _make_mock_client(fenced)
    result = run(state, client=client)
    assert result.current_lesson is not None


@patch("backend.agents.teaching.agent.retrieve_supporting_chunks", return_value=[])
@patch("backend.agents.teaching.agent._read_source_lines", return_value=FAKE_SOURCE)
def test_run_passes_source_into_prompt(mock_read, mock_support):
    state, node = _make_state_with_current_node()
    client = _make_mock_client(json.dumps(FAKE_LESSON_OUTPUT))
    run(state, client=client)
    user_msg = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "HTTPBasicAuth" in user_msg
    assert "requests/auth.py" in user_msg


# ── caching ───────────────────────────────────────────────────────────────────

@patch("backend.agents.teaching.agent.retrieve_supporting_chunks", return_value=[])
@patch("backend.agents.teaching.agent._read_source_lines", return_value=FAKE_SOURCE)
def test_run_cache_hit_skips_llm(mock_read, mock_support):
    state, node = _make_state_with_current_node()
    node.cached_lesson = FAKE_LESSON_OUTPUT  # pre-seed a prior visit
    client = MagicMock()
    result = run(state, client=client)
    client.messages.create.assert_not_called()
    assert result.current_lesson == FAKE_LESSON_OUTPUT


# ── prior-context ─────────────────────────────────────────────────────────────

def test_prior_context_empty_when_no_understood_nodes():
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    cur = graph.add_node(_make_node())
    text = _build_prior_context(graph, cur.id)
    assert "first lesson" in text.lower()


def test_prior_context_lists_understood_nodes():
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    cur = graph.add_node(_make_node("Current node"))
    done = graph.add_node(_make_node("Session basics", understood=True))
    text = _build_prior_context(graph, cur.id)
    assert "Session basics" in text
    assert "Current node" not in text  # the current node is excluded


@patch("backend.agents.teaching.agent.retrieve_supporting_chunks", return_value=[])
@patch("backend.agents.teaching.agent._read_source_lines", return_value=FAKE_SOURCE)
def test_run_includes_prior_understanding_in_prompt(mock_read, mock_support):
    state, node = _make_state_with_current_node()
    done = state.graph.add_node(_make_node("Session basics", understood=True))
    client = _make_mock_client(json.dumps(FAKE_LESSON_OUTPUT))
    run(state, client=client)
    user_msg = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "Session basics" in user_msg


# ── supporting-chunk retrieval is best-effort ──────────────────────────────────

@patch("backend.agents.teaching.agent.retrieve_supporting_chunks",
       side_effect=Exception("chroma down"))
@patch("backend.agents.teaching.agent._read_source_lines", return_value=FAKE_SOURCE)
def test_run_survives_supporting_retrieval_failure(mock_read, mock_support):
    state, node = _make_state_with_current_node()
    client = _make_mock_client(json.dumps(FAKE_LESSON_OUTPUT))
    result = run(state, client=client)
    # Lesson still generated; failure recorded but non-fatal.
    assert result.current_lesson is not None
    assert any("supporting retrieval failed" in e for e in result.errors)


@patch("backend.agents.teaching.agent.retrieve_supporting_chunks", return_value=[])
@patch("backend.agents.teaching.agent._read_source_lines", return_value=FAKE_SOURCE)
def test_run_excludes_own_anchor_from_supporting_query(mock_read, mock_support):
    state, node = _make_state_with_current_node()
    client = _make_mock_client(json.dumps(FAKE_LESSON_OUTPUT))
    run(state, client=client)
    exclude = mock_support.call_args.kwargs["exclude"]
    assert ("requests/auth.py", 72, 100) in exclude


# ── error handling ────────────────────────────────────────────────────────────

def test_run_errors_when_graph_missing():
    state = OnboardState(repo_url=FAKE_REPO_URL)
    state.goal = FAKE_GOAL
    result = run(state, client=MagicMock())
    assert result.current_lesson is None
    assert any("graph missing" in e for e in result.errors)


def test_run_errors_when_no_current_node():
    state = OnboardState(repo_url=FAKE_REPO_URL)
    state.goal = FAKE_GOAL
    state.graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)  # no current_node_id
    result = run(state, client=MagicMock())
    assert result.current_lesson is None
    assert any("no current node" in e for e in result.errors)


def test_run_errors_when_goal_missing():
    state, node = _make_state_with_current_node()
    state.goal = None
    result = run(state, client=MagicMock())
    assert result.current_lesson is None
    assert any("goal missing" in e for e in result.errors)


@patch("backend.agents.teaching.agent._read_source_lines",
       side_effect=FileNotFoundError("no such file"))
def test_run_errors_when_source_unreadable(mock_read):
    state, node = _make_state_with_current_node()
    client = MagicMock()
    result = run(state, client=client)
    assert result.current_lesson is None
    assert any("could not read source" in e for e in result.errors)
    client.messages.create.assert_not_called()


@patch("backend.agents.teaching.agent.retrieve_supporting_chunks", return_value=[])
@patch("backend.agents.teaching.agent._read_source_lines", return_value=FAKE_SOURCE)
def test_run_handles_invalid_llm_json(mock_read, mock_support):
    state, node = _make_state_with_current_node()
    client = _make_mock_client("not valid json")
    result = run(state, client=client)
    assert result.current_lesson is None
    assert node.cached_lesson is None
    assert any("LLM call failed" in e for e in result.errors)


# ── parsing ───────────────────────────────────────────────────────────────────

def test_parse_output_plain_json():
    output = _parse_output(json.dumps(FAKE_LESSON_OUTPUT))
    assert isinstance(output, LessonOutput)
    assert output.prompt_kind == "predict-then-reveal"


def test_parse_output_defaults_prompt_kind():
    payload = {k: v for k, v in FAKE_LESSON_OUTPUT.items() if k != "prompt_kind"}
    output = _parse_output(json.dumps(payload))
    assert output.prompt_kind == "predict-then-reveal"
