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

from tests.conftest import TEST_USER_ID
from fastapi.testclient import TestClient

import backend.api as api
from backend.learning import store as learning_store
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.pipeline import progress as pipeline_progress


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


def _pipeline_side_effect(repo_url, goal, client=None, progress_id=""):
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


@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_session_start_persists_the_original_plan(mock_pipeline, client):
    """The endpoint must use `create_session`, not `save_graph` (session-reset.md §4.2).

    Asserted at the HTTP boundary rather than only against the store, because this
    is the call site that can silently regress: swapping back to `save_graph` here
    would leave every store-level test passing and every new session unresettable.
    """
    session_id = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()["session_id"]

    plan = learning_store.load_plan(session_id, TEST_USER_ID, api.SESSIONS_DB_PATH)
    assert plan is not None
    live = learning_store.load_graph(session_id, TEST_USER_ID, api.SESSIONS_DB_PATH)
    assert set(plan.nodes) == set(live.nodes)


@patch("backend.api.clone_repo", return_value="/tmp/repo")
@patch("backend.api.run_teaching", side_effect=_teaching_side_effect)
@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_the_first_render_fills_the_plan_lesson_slot(mock_p, mock_t, mock_c, client):
    session_id = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()["session_id"]
    node_id = client.get(f"/session/{session_id}").json()["current_node_id"]

    assert learning_store.load_plan(session_id, TEST_USER_ID, api.SESSIONS_DB_PATH) \
        .nodes[node_id].cached_lesson is None

    client.get(f"/session/{session_id}/lesson")

    assert learning_store.load_plan(session_id, TEST_USER_ID, api.SESSIONS_DB_PATH) \
        .nodes[node_id].cached_lesson == FAKE_LESSON


@patch("backend.api.clone_repo", return_value="/tmp/repo")
@patch("backend.api.run_teaching")
@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_a_teaching_failure_does_not_seal_the_fallback_into_the_plan(
    mock_p, mock_teaching, mock_c, client
):
    """The fallback lesson is a system outage, not the unit's original lesson.

    Recording it would make `Start over` restore "this lesson could not be
    generated" forever. The slot must stay NULL so a later real render fills it.
    """
    def fails(state, client=None):
        state.current_lesson = None
        state.errors = ["teaching: boom"]
        return state

    mock_teaching.side_effect = fails
    session_id = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()["session_id"]
    node_id = client.get(f"/session/{session_id}").json()["current_node_id"]

    client.get(f"/session/{session_id}/lesson")

    plan = learning_store.load_plan(session_id, TEST_USER_ID, api.SESSIONS_DB_PATH)
    assert plan.nodes[node_id].cached_lesson is None
    # The LIVE side still got the fallback, so the session is not blocked.
    live = learning_store.load_graph(session_id, TEST_USER_ID, api.SESSIONS_DB_PATH)
    assert live.nodes[node_id].cached_lesson is not None

    # And a later successful render fills the slot the outage left empty.
    mock_teaching.side_effect = _teaching_side_effect
    client.get(f"/session/{session_id}/lesson")
    assert learning_store.load_plan(session_id, TEST_USER_ID, api.SESSIONS_DB_PATH) \
        .nodes[node_id].cached_lesson == FAKE_LESSON


# ── /session/progress/{id} ───────────────────────────────────────────────────

def test_progress_of_an_unknown_run_is_a_404(client):
    # The client treats this as "no news" — the POST is the only authority on
    # whether the run worked — so it must not be a 500.
    resp = client.get("/session/progress/never-started")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "progress_not_found"


def test_the_run_reports_the_stages_it_passed_through():
    def _reporting_pipeline(repo_url, goal, client=None, progress_id=""):
        # Stand in for the real nodes, which report from inside the graph.
        pipeline_progress.stage(progress_id, "clone")
        pipeline_progress.stage(progress_id, "structure")
        return _pipeline_side_effect(repo_url, goal, client=client)

    with patch("backend.api.run_pipeline", side_effect=_reporting_pipeline):
        resp = TestClient(api.app).post("/session/start", json={
            "repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL, "progress_id": "run-abc",
        })

    assert resp.status_code == 200
    snap = pipeline_progress.snapshot("run-abc")
    assert snap["done"] == ["clone", "structure"]


def test_a_run_is_marked_finished_even_when_the_pipeline_fails(client):
    # Otherwise a client polls a dead run forever, having already been told the
    # request failed.
    state = MagicMock()
    state.graph = None
    state.errors = ["pipeline failed: boom"]
    with patch("backend.api.run_pipeline", return_value=state):
        resp = client.post("/session/start", json={
            "repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL, "progress_id": "run-dead",
        })

    assert resp.status_code == 500
    assert pipeline_progress.snapshot("run-dead")["finished"] is True


@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_a_run_without_a_progress_id_reports_nothing(mock_pipeline, client):
    # The id is optional: an older client must still get a session.
    resp = client.post("/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL})

    assert resp.status_code == 200
    assert pipeline_progress.snapshot("") is None


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

def _mutator_inserts_prerequisite(state, signal, client=None, diagnosis=None, origin=None):
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

@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_the_same_repo_and_goal_now_produce_a_SECOND_session(mock_pipeline, client):
    """M3 DELETED implicit resume, and this is the behaviour that replaces it.

    `_try_resume` used to scan every session in the database for a matching
    (repo_url, goal) and return it rather than planning. Two learners who picked
    the same repository and answered the interview the same way got THE SAME
    SESSION — each other's answers, gaps and history (multi-user.md §2 P1).

    It also contradicted the requirement it looked like it served: a learner may
    hold several sessions on one repository, with the same goal or a different
    one, and they must be independent (I3).

    So creation always creates. Resuming means opening a session you already
    own, by id, from the dashboard.
    """
    first = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()
    second = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()

    assert first["session_id"] != second["session_id"]
    assert second["resumed"] is False
    assert mock_pipeline.call_count == 2, "the second must be planned, not reused"

    # And they are genuinely independent: advancing one leaves the other alone.
    stored_first = learning_store.load_graph(
        first["session_id"], TEST_USER_ID, api.SESSIONS_DB_PATH
    )
    stored_second = learning_store.load_graph(
        second["session_id"], TEST_USER_ID, api.SESSIONS_DB_PATH
    )
    assert set(stored_first.nodes) != set(stored_second.nodes), (
        "two sessions sharing node ids would share state"
    )


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


# ── /session/{id}/jump — the record a jump leaves ───────────────────────────
#
# Jumping stays unconditional: no stop is locked and dependencies are not
# enforced. What these pin is that it stops being INVISIBLE. Before this it was
# the only navigation act in the system that wrote nothing at all, so a session
# spent jumping around was afterwards indistinguishable from one spent walking.
#
# Two records, two readers, and the tests are separate because the difference is
# the design: `journey_events` is permanent (the session log reads it) and
# `arrival` is the one live fact (the notice on the stop reads it, and it must go
# stale the moment the learner rejoins the route).

@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_jump_records_a_journey_event_naming_both_stops(mock_pipeline, client):
    start = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()
    session_id = start["session_id"]
    first_node = start["graph"]["current_node_id"]
    other = next(
        n["id"] for n in start["graph"]["nodes"] if n["id"] != first_node
    )

    client.post(f"/session/{session_id}/jump", json={"node_id": other})

    events = client.get(f"/session/{session_id}").json()["journey_events"]
    jumps = [e for e in events if e["kind"] == "jumped"]
    assert len(jumps) == 1
    # Both ends, because "they jumped" without saying from where cannot answer
    # the only question the log is opened with.
    assert jumps[0]["nodes"] == [other]
    assert jumps[0]["from_node_id"] == first_node
    assert jumps[0]["intent"] == "study"


@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_jump_records_the_arrival_for_the_notice(mock_pipeline, client):
    start = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()
    session_id = start["session_id"]
    first_node = start["graph"]["current_node_id"]
    other = next(
        n["id"] for n in start["graph"]["nodes"] if n["id"] != first_node
    )

    resp = client.post(f"/session/{session_id}/jump", json={"node_id": other})
    assert resp.status_code == 200
    assert resp.json()["arrival"]["node_id"] == other
    assert resp.json()["arrival"]["from_node_id"] == first_node

    # And it SURVIVES a reload: a learner who refreshes is still off-route, so
    # the notice cannot be component state that a remount forgets.
    arrival = client.get(f"/session/{session_id}").json()["arrival"]
    assert arrival["node_id"] == other
    assert arrival["kind"] == "jumped"


@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_a_fresh_session_has_no_arrival(mock_pipeline, client):
    # Null means "nothing to say", and the first stop of a journey is reached by
    # starting rather than by jumping.
    start = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()
    assert start["graph"]["arrival"] is None


@patch("backend.api.clone_repo", return_value="data/repos/requests")
@patch("backend.api.run_teaching", side_effect=_teaching_side_effect)
@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_advancing_clears_the_arrival(mock_pipeline, mock_teaching, mock_clone, client):
    """Walking on IS rejoining the route, so the notice stops being true.

    THE FAILURE THIS PREVENTS: an arrival that outlived an advance would keep
    telling the learner they are off-route from a stop they have already left,
    and the only way to silence it would be to jump again.
    """
    start = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()
    session_id = start["session_id"]
    first_node = start["graph"]["current_node_id"]
    other = next(
        n["id"] for n in start["graph"]["nodes"] if n["id"] != first_node
    )

    client.post(f"/session/{session_id}/jump", json={"node_id": other})
    client.post(f"/session/{session_id}/advance", json={"signal": "next"})

    graph = client.get(f"/session/{session_id}").json()
    assert graph["arrival"] is None
    # The permanent record is untouched — clearing the notice is not forgetting
    # that it happened.
    assert [e["kind"] for e in graph["journey_events"]].count("jumped") == 1


@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_resuming_clears_the_arrival_but_is_still_recorded(mock_pipeline, client):
    """The return offered by the notice is the opposite act, and recorded as one.

    It clears the notice (they are back on the route) yet still writes an event:
    a log that recorded only departures would imply the learner never came back.
    """
    start = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()
    session_id = start["session_id"]
    first_node = start["graph"]["current_node_id"]
    other = next(
        n["id"] for n in start["graph"]["nodes"] if n["id"] != first_node
    )

    client.post(f"/session/{session_id}/jump", json={"node_id": other})
    resp = client.post(
        f"/session/{session_id}/jump",
        json={"node_id": first_node, "intent": "resume"},
    )
    assert resp.status_code == 200
    assert resp.json()["arrival"] is None

    graph = client.get(f"/session/{session_id}").json()
    assert graph["arrival"] is None
    assert graph["current_node_id"] == first_node
    intents = [e.get("intent") for e in graph["journey_events"] if e["kind"] == "jumped"]
    assert intents == ["study", "resume"]


@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_jump_rejects_an_unknown_intent(mock_pipeline, client):
    start = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()
    session_id = start["session_id"]
    node = start["graph"]["current_node_id"]

    resp = client.post(
        f"/session/{session_id}/jump", json={"node_id": node, "intent": "teleport"}
    )
    assert resp.status_code == 400
    assert "teleport" in resp.json()["detail"]


@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_jump_to_an_unknown_node_is_a_404(mock_pipeline, client):
    start = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()
    resp = client.post(
        f"/session/{start['session_id']}/jump", json={"node_id": "nope"}
    )
    assert resp.status_code == 404



# ── /session/{id}/file containment (multi-user M0) ────────────────────────────


@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_the_file_endpoint_serves_a_file_inside_the_checkout(
    mock_pipeline, client, tmp_path
):
    checkout = tmp_path / "requests"
    (checkout / "requests").mkdir(parents=True)
    (checkout / "requests" / "sessions.py").write_text("class Session: pass\n")

    session_id = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()["session_id"]

    with patch("backend.api.clone_repo", return_value=str(checkout)):
        response = client.get(
            f"/session/{session_id}/file", params={"path": "requests/sessions.py"}
        )

    assert response.status_code == 200
    assert "class Session" in response.json()["content"]


@pytest.mark.parametrize(
    "path",
    [
        # THE ONE THE OLD CHECK LET THROUGH. `startswith` compared strings, and
        # "requests-private" starts with "requests", so a sibling checkout was
        # inside the repository as far as the guard was concerned. Harmless
        # while every checkout was one public repo in a flat directory; not
        # harmless once checkouts are per-owner and sessions belong to people.
        "../requests-private/secrets.py",
        "../../etc/passwd",
        "requests/../../escape.txt",
        "/etc/passwd",
    ],
)
@patch("backend.api.run_pipeline", side_effect=_pipeline_side_effect)
def test_the_file_endpoint_refuses_to_escape_the_checkout(
    mock_pipeline, client, tmp_path, path
):
    checkout = tmp_path / "requests"
    (checkout / "requests").mkdir(parents=True)
    (checkout / "requests" / "sessions.py").write_text("ok\n")
    sibling = tmp_path / "requests-private"
    sibling.mkdir()
    (sibling / "secrets.py").write_text("SECRET = 'do not read me'\n")
    (tmp_path / "escape.txt").write_text("outside\n")

    session_id = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()["session_id"]

    with patch("backend.api.clone_repo", return_value=str(checkout)):
        response = client.get(f"/session/{session_id}/file", params={"path": path})

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid_path"
