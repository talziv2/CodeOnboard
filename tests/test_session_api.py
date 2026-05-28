"""
Pytest tests for the Phase 3 session endpoints in backend/api.py.
Run with: uv run pytest tests/test_session_api.py -v

The pipeline, Teaching Agent, and clone_repo are mocked; persistence is real
SQLite pointed at a temp DB via the SESSIONS_DB_PATH indirection. So these
tests exercise the genuine save/load round-trip through HTTP without touching
the network, the LLM, or the real data/ directory.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import backend.api as api
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode


FAKE_REPO_URL = "https://github.com/psf/requests"
FAKE_GOAL = {
    "primary_goal": "understand how authentication works",
    "goal_type": "understand_component",
    "focus_area": "authentication",
    "experience_level": "intermediate",
    "depth": "deep",
}

FAKE_LESSON = {
    "walkthrough": "HTTPBasicAuth attaches the Authorization header…",
    "prompt": "What does __call__ return?",
    "expected_answer": "The mutated PreparedRequest.",
    "prompt_kind": "predict-then-reveal",
}


@pytest.fixture(autouse=True)
def _env_and_db(tmp_path, monkeypatch):
    # Dummy API key so _new_client() doesn't KeyError, and an isolated DB.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(api, "SESSIONS_DB_PATH", tmp_path / "sessions.db")
    # _new_client builds a real anthropic.Anthropic; mock it so no network.
    monkeypatch.setattr(api.anthropic, "Anthropic", lambda **kw: MagicMock())


@pytest.fixture
def client():
    return TestClient(api.app)


def _make_two_node_graph() -> LearningGraph:
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    a = graph.add_node(LearningNode(
        title="Understand HTTPBasicAuth",
        code_anchor=CodeAnchor(file="requests/auth.py", line_start=72, line_end=100),
        concept_tags=["request signing"],
        lesson_brief={"why": "core auth", "understand": "how __call__ signs"},
    ))
    b = graph.add_node(LearningNode(
        title="Trace Session.send",
        code_anchor=CodeAnchor(file="requests/sessions.py", line_start=394, line_end=470),
        concept_tags=["request lifecycle"],
        lesson_brief={"why": "where auth runs", "understand": "the send flow"},
    ))
    graph.add_edge(a.id, b.id, kind="sequence")
    graph.set_current(a.id)
    return graph


def _pipeline_side_effect(repo_url, goal, client=None):
    # Mimic run_pipeline: returns a state carrying a populated graph.
    state = MagicMock()
    state.graph = _make_two_node_graph()
    state.errors = []
    return state


def _teaching_side_effect(state, client=None):
    # Mimic the Teaching Agent: set cached_lesson on the current node + current_lesson.
    node = state.graph.nodes[state.graph.current_node_id]
    node.cached_lesson = FAKE_LESSON
    state.current_lesson = FAKE_LESSON
    return state


# ── /session/start ──────────────────────────────────────────────────────────

@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_session_start_returns_session_and_graph(mock_pipeline, client):
    resp = client.post("/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL})
    assert resp.status_code == 200
    body = resp.json()
    assert "session_id" in body
    assert len(body["graph"]["nodes"]) == 2
    assert body["graph"]["current_node_id"] is not None


@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_session_start_persists_graph(mock_pipeline, client):
    resp = client.post("/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL})
    session_id = resp.json()["session_id"]
    # A fresh GET must find the persisted graph.
    got = client.get(f"/session/{session_id}")
    assert got.status_code == 200
    assert got.json()["session_id"] == session_id


@patch("backend.api.run_pipeline")
def test_session_start_500_when_no_graph(mock_pipeline, client):
    state = MagicMock()
    state.graph = None
    state.errors = ["pipeline failed: boom"]
    mock_pipeline.return_value = state
    resp = client.post("/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL})
    assert resp.status_code == 500
    assert "boom" in str(resp.json()["detail"])


# ── /session/{id} ─────────────────────────────────────────────────────────────

def test_session_get_unknown_returns_404(client):
    assert client.get("/session/does-not-exist").status_code == 404


# ── /session/{id}/lesson ──────────────────────────────────────────────────────

@patch("backend.api.clone_repo", return_value="data/repos/requests")
@patch("backend.api.run_teaching", side_effect=_teaching_side_effect)
@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_lesson_renders_current_node(mock_pipeline, mock_teaching, mock_clone, client):
    session_id = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()["session_id"]

    resp = client.get(f"/session/{session_id}/lesson")
    assert resp.status_code == 200
    body = resp.json()
    assert body["lesson"]["prompt_kind"] == "predict-then-reveal"
    assert body["node_id"] is not None


@patch("backend.api.clone_repo", return_value="data/repos/requests")
@patch("backend.api.run_teaching", side_effect=_teaching_side_effect)
@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_lesson_caches_on_node(mock_pipeline, mock_teaching, mock_clone, client):
    session_id = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()["session_id"]
    client.get(f"/session/{session_id}/lesson")
    # The persisted graph should now report has_lesson on the current node.
    graph = client.get(f"/session/{session_id}").json()
    current = graph["current_node_id"]
    node = next(n for n in graph["nodes"] if n["id"] == current)
    assert node["has_lesson"] is True


def test_lesson_unknown_session_404(client):
    assert client.get("/session/nope/lesson").status_code == 404


# ── /session/{id}/advance ─────────────────────────────────────────────────────

@patch("backend.api.clone_repo", return_value="data/repos/requests")
@patch("backend.api.run_teaching", side_effect=_teaching_side_effect)
@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_advance_moves_to_next_node(mock_pipeline, mock_teaching, mock_clone, client):
    start = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()
    session_id = start["session_id"]
    first_node = start["graph"]["current_node_id"]

    resp = client.post(f"/session/{session_id}/advance", json={"signal": "next"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["done"] is False
    assert body["node_id"] != first_node           # advanced
    assert body["lesson"]["prompt_kind"] == "predict-then-reveal"


@patch("backend.api.clone_repo", return_value="data/repos/requests")
@patch("backend.api.run_teaching", side_effect=_teaching_side_effect)
@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_advance_marks_visited(mock_pipeline, mock_teaching, mock_clone, client):
    start = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()
    session_id = start["session_id"]
    first_node = start["graph"]["current_node_id"]

    client.post(f"/session/{session_id}/advance", json={"signal": "next"})
    graph = client.get(f"/session/{session_id}").json()
    node = next(n for n in graph["nodes"] if n["id"] == first_node)
    assert node["visited"] is True


@patch("backend.api.clone_repo", return_value="data/repos/requests")
@patch("backend.api.run_teaching", side_effect=_teaching_side_effect)
@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_advance_past_end_returns_done(mock_pipeline, mock_teaching, mock_clone, client):
    session_id = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()["session_id"]
    # Two nodes → one advance reaches the second, a second advance hits the end.
    client.post(f"/session/{session_id}/advance", json={"signal": "next"})
    resp = client.post(f"/session/{session_id}/advance", json={"signal": "next"})
    assert resp.status_code == 200
    assert resp.json() == {"done": True}


def test_advance_rejects_unsupported_signal(client):
    # Need a real session first so we reach the signal check.
    with patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect):
        session_id = client.post(
            "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
        ).json()["session_id"]
    resp = client.post(f"/session/{session_id}/advance", json={"signal": "deeper"})
    assert resp.status_code == 400


def test_advance_unknown_session_404(client):
    assert client.post("/session/nope/advance", json={"signal": "next"}).status_code == 404
