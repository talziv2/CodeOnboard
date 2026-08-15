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
    "code_depth": "working",
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


# ── /session/{id}/respond ─────────────────────────────────────────────────────

def _grader_side_effect(classification: str):
    def _apply(state, user_response, client=None):
        node = state.graph.nodes[state.graph.current_node_id]
        # Mimic the real agent's node update. `off-topic` is absent on purpose:
        # it is evidence of neither understanding nor misunderstanding, so the
        # node keeps the state it already had (see grader/agent.py).
        mapping = {"understood": "understood", "partial": "partial",
                   "confused": "failed"}
        if classification in mapping:
            state.graph.mark_understanding(node.id, mapping[classification])
        state.last_grade = {"classification": classification, "rationale": "mock"}
        return state
    return _apply


@patch("backend.api.clone_repo", return_value="data/repos/requests")
@patch("backend.api.run_teaching", side_effect=_teaching_side_effect)
@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_respond_classifies_and_persists(mock_pipeline, mock_teaching, mock_clone, client):
    session_id = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()["session_id"]
    client.get(f"/session/{session_id}/lesson")  # render so there's a lesson to grade

    with patch("backend.api.run_grader", side_effect=_grader_side_effect("understood")):
        resp = client.post(f"/session/{session_id}/respond", json={"response": "good answer"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["classification"] == "understood"
    assert body["understanding_state"] == "understood"

    # And it persisted: the graph now reports the node as understood.
    graph = client.get(f"/session/{session_id}").json()
    current = graph["current_node_id"]
    node = next(n for n in graph["nodes"] if n["id"] == current)
    assert node["understanding_state"] == "understood"


@patch("backend.api.mutate_graph")
@patch("backend.api.clone_repo", return_value="data/repos/requests")
@patch("backend.api.run_teaching", side_effect=_teaching_side_effect)
@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_off_topic_does_not_trigger_an_automatic_prerequisite(
    mock_pipeline, mock_teaching, mock_clone, mock_mutate, client
):
    """The other half of the off-topic bug, one layer up.

    Fixing the Grader's state mapping was not enough: /respond also branched on
    `off-topic` to insert a warm-up. Typing something unrelated would still have
    reshaped the learning path.
    """
    session_id = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()["session_id"]
    client.get(f"/session/{session_id}/lesson")

    with patch("backend.api.run_grader", side_effect=_grader_side_effect("off-topic")):
        resp = client.post(f"/session/{session_id}/respond", json={"response": "hello?"})

    assert resp.status_code == 200
    mock_mutate.assert_not_called()
    graph = client.get(f"/session/{session_id}").json()
    node = next(n for n in graph["nodes"] if n["id"] == graph["current_node_id"])
    assert node["weak_spot"] is False
    assert node["understanding_state"] == "not_started"
    # The answer is still recorded — it happened, it just carries no verdict.
    assert node["attempts"][-1]["classification"] == "off-topic"


@patch("backend.api.mutate_graph")
@patch("backend.api.clone_repo", return_value="data/repos/requests")
@patch("backend.api.run_teaching", side_effect=_teaching_side_effect)
@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_confused_still_triggers_an_automatic_prerequisite(
    mock_pipeline, mock_teaching, mock_clone, mock_mutate, client
):
    session_id = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()["session_id"]
    client.get(f"/session/{session_id}/lesson")

    with patch("backend.api.run_grader", side_effect=_grader_side_effect("confused")):
        client.post(f"/session/{session_id}/respond", json={"response": "no idea"})

    mock_mutate.assert_called_once()


@patch("backend.api.clone_repo", return_value="data/repos/requests")
@patch("backend.api.run_teaching", side_effect=_teaching_side_effect)
@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_respond_confused_sets_weak_spot(mock_pipeline, mock_teaching, mock_clone, client):
    session_id = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()["session_id"]
    client.get(f"/session/{session_id}/lesson")

    with patch("backend.api.run_grader", side_effect=_grader_side_effect("confused")):
        client.post(f"/session/{session_id}/respond", json={"response": "no idea"})

    graph = client.get(f"/session/{session_id}").json()
    current = graph["current_node_id"]
    node = next(n for n in graph["nodes"] if n["id"] == current)
    assert node["understanding_state"] == "failed"
    assert node["weak_spot"] is True


@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_respond_409_before_lesson_rendered(mock_pipeline, client):
    # No /lesson call → current node has no cached_lesson → 409.
    session_id = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()["session_id"]
    resp = client.post(f"/session/{session_id}/respond", json={"response": "x"})
    assert resp.status_code == 409


def test_respond_unknown_session_404(client):
    assert client.post("/session/nope/respond", json={"response": "x"}).status_code == 404


# ── Part 6: mutation on confused, skip, override ──────────────────────────────

def _mutator_inserts_prerequisite(state, signal, client=None, diagnosis=None):
    # Mimic the real mutator's prerequisite insertion without RAG/LLM.
    graph = state.graph
    current = graph.current_node_id
    from backend.learning.graph import CodeAnchor, LearningNode
    prereq = LearningNode(
        title="Prerequisite",
        code_anchor=CodeAnchor(file="requests/models.py", line_start=10, line_end=40),
        lesson_brief={"why": "foundation", "understand": "the basics"},
    )
    graph.insert_before(current, prereq, kind="prerequisite")
    graph.set_current(prereq.id)
    state.last_mutation = {"kind": "prerequisite", "new_node_id": prereq.id,
                           "anchor_node_id": current}
    return state


@patch("backend.api.clone_repo", return_value="data/repos/requests")
@patch("backend.api.run_teaching", side_effect=_teaching_side_effect)
@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_confused_inserts_prerequisite_and_walk_returns_to_node(
    mock_pipeline, mock_teaching, mock_clone, client
):
    start = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()
    session_id = start["session_id"]
    confused_node = start["graph"]["current_node_id"]
    client.get(f"/session/{session_id}/lesson")  # render so /respond has a prompt

    with patch("backend.api.run_grader", side_effect=_grader_side_effect("confused")), \
         patch("backend.api.mutate_graph", side_effect=_mutator_inserts_prerequisite):
        resp = client.post(f"/session/{session_id}/respond", json={"response": "lost"})

    body = resp.json()
    assert body["classification"] == "confused"
    assert body["mutation"]["kind"] == "prerequisite"
    prereq_id = body["mutation"]["new_node_id"]
    # Current moved to the new prerequisite.
    assert body["current_node_id"] == prereq_id

    # The persisted graph gained a node, and the prereq walks back to the
    # originally-confused node.
    graph = client.get(f"/session/{session_id}").json()
    assert len(graph["nodes"]) == 3
    assert graph["current_node_id"] == prereq_id
    prereq_edge = next(
        e for e in graph["edges"]
        if e["from_id"] == prereq_id and e["to_id"] == confused_node
    )
    assert prereq_edge["kind"] == "prerequisite"


@patch("backend.api.clone_repo", return_value="data/repos/requests")
@patch("backend.api.run_teaching", side_effect=_teaching_side_effect)
@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_advancing_from_a_prerequisite_returns_to_the_failed_node(
    mock_pipeline, mock_teaching, mock_clone, client
):
    # The point of a remediation prerequisite is a second attempt at the
    # objective the learner failed. Advancing off the warm-up must land back on
    # that node — not jump past it, which would leave it permanently unlearned.
    start = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()
    session_id = start["session_id"]
    confused_node = start["graph"]["current_node_id"]
    client.get(f"/session/{session_id}/lesson")

    with patch("backend.api.run_grader", side_effect=_grader_side_effect("confused")), \
         patch("backend.api.mutate_graph", side_effect=_mutator_inserts_prerequisite):
        prereq_id = client.post(
            f"/session/{session_id}/respond", json={"response": "lost"}
        ).json()["mutation"]["new_node_id"]

    client.get(f"/session/{session_id}/lesson")  # learn the warm-up
    advanced = client.post(
        f"/session/{session_id}/advance", json={"signal": "next"}
    ).json()

    assert advanced["done"] is False
    assert advanced["node_id"] == confused_node

    graph = client.get(f"/session/{session_id}").json()
    assert graph["current_node_id"] == confused_node
    original = next(n for n in graph["nodes"] if n["id"] == confused_node)
    # Still unvisited: the learner is being asked to attempt it again, so the
    # node must not carry a "done" marker it never earned.
    assert original["visited"] is False


@patch("backend.api.clone_repo", return_value="data/repos/requests")
@patch("backend.api.run_teaching", side_effect=_teaching_side_effect)
@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_understood_does_not_mutate(mock_pipeline, mock_teaching, mock_clone, client):
    session_id = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()["session_id"]
    client.get(f"/session/{session_id}/lesson")

    with patch("backend.api.run_grader", side_effect=_grader_side_effect("understood")):
        resp = client.post(f"/session/{session_id}/respond", json={"response": "great answer"})

    assert resp.json()["mutation"]["kind"] == "none"
    graph = client.get(f"/session/{session_id}").json()
    assert len(graph["nodes"]) == 2  # unchanged


@patch("backend.api.clone_repo", return_value="data/repos/requests")
@patch("backend.api.run_teaching", side_effect=_teaching_side_effect)
@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_advance_skip_marks_skipped_and_moves_on(mock_pipeline, mock_teaching, mock_clone, client):
    start = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()
    session_id = start["session_id"]
    first = start["graph"]["current_node_id"]

    resp = client.post(f"/session/{session_id}/advance", json={"signal": "skip"})
    assert resp.status_code == 200
    assert resp.json()["done"] is False

    graph = client.get(f"/session/{session_id}").json()
    node = next(n for n in graph["nodes"] if n["id"] == first)
    assert node["visited"] is True
    assert graph["current_node_id"] != first


@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_override_mark_understood(mock_pipeline, client):
    start = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()
    session_id = start["session_id"]
    node_id = start["graph"]["current_node_id"]

    resp = client.post(
        f"/session/{session_id}/override",
        json={"action": "mark_understood", "node_id": node_id},
    )
    assert resp.status_code == 200
    assert resp.json()["understanding_state"] == "understood"

    graph = client.get(f"/session/{session_id}").json()
    node = next(n for n in graph["nodes"] if n["id"] == node_id)
    assert node["understanding_state"] == "understood"


@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_override_rejects_unknown_action(mock_pipeline, client):
    session_id = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()["session_id"]
    resp = client.post(f"/session/{session_id}/override", json={"action": "explode"})
    assert resp.status_code == 400


# ── Part 7: resume ────────────────────────────────────────────────────────────

@patch("backend.api.clone_repo", return_value="data/repos/requests")
@patch("backend.api.run_teaching", side_effect=_teaching_side_effect)
@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_same_repo_goal_resumes_without_rerunning_pipeline(
    mock_pipeline, mock_teaching, mock_clone, client
):
    start = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()
    session_id = start["session_id"]
    assert start["resumed"] is False
    # Advance once so the first node is visited and current moves to the second.
    client.post(f"/session/{session_id}/advance", json={"signal": "next"})

    # Second start, same repo + goal → resume the SAME session, no new pipeline.
    again = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()
    assert again["resumed"] is True
    assert again["session_id"] == session_id
    assert mock_pipeline.call_count == 1  # pipeline ran only the first time


@patch("backend.api.clone_repo", return_value="data/repos/requests")
@patch("backend.api.run_teaching", side_effect=_teaching_side_effect)
@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_resume_moves_current_to_first_unvisited(
    mock_pipeline, mock_teaching, mock_clone, client
):
    start = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()
    session_id = start["session_id"]
    first_node = start["graph"]["current_node_id"]
    client.post(f"/session/{session_id}/advance", json={"signal": "next"})

    again = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()
    # First node was visited → resume lands on the second (first unvisited).
    assert again["graph"]["current_node_id"] != first_node


@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_different_goal_creates_new_session(mock_pipeline, client):
    client.post("/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL})
    other_goal = {**FAKE_GOAL, "primary_goal": "something else entirely"}
    resp = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": other_goal}
    ).json()
    assert resp["resumed"] is False
    assert mock_pipeline.call_count == 2  # ran for each distinct goal


@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_force_new_starts_fresh_despite_match(mock_pipeline, client):
    first = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()
    forced = client.post(
        "/session/start",
        json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL, "force_new": True},
    ).json()
    assert forced["resumed"] is False
    assert forced["session_id"] != first["session_id"]
    assert mock_pipeline.call_count == 2


@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_list_sessions_for_repo(mock_pipeline, client):
    client.post("/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL})
    resp = client.get("/sessions", params={"repo_url": FAKE_REPO_URL})
    assert resp.status_code == 200
    sessions = resp.json()["sessions"]
    assert len(sessions) >= 1
    assert sessions[0]["goal"] == FAKE_GOAL


def test_list_sessions_empty_for_unknown_repo(client):
    resp = client.get("/sessions", params={"repo_url": "https://github.com/none/none"})
    assert resp.status_code == 200
    assert resp.json()["sessions"] == []
