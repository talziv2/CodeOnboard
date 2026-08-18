"""
Tests for per-node answer history and the warm-up policy.

Covers three linked behaviours:
  * every graded answer is recorded, so revisiting a node adds to the record
    instead of silently overwriting its state;
  * a wrong answer creates a warm-up automatically;
  * a "partial" answer does not — the warm-up stays an offer.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import backend.api as api
from backend.learning import store as learning_store
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode


FAKE_REPO_URL = "https://github.com/psf/requests"
FAKE_GOAL = {"primary_goal": "understand auth", "goal_type": "understand_component"}
FAKE_LESSON = {
    "walkthrough": "…",
    "prompt": "What does __call__ return?",
    "expected_answer": "The mutated PreparedRequest.",
    "prompt_kind": "predict-then-reveal",
}


@pytest.fixture(autouse=True)
def _env_and_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(api, "SESSIONS_DB_PATH", tmp_path / "sessions.db")
    monkeypatch.setattr(api.anthropic, "Anthropic", lambda **kw: MagicMock())


@pytest.fixture
def client():
    return TestClient(api.app)


def _two_node_graph() -> LearningGraph:
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    a = graph.add_node(LearningNode(
        title="Understand HTTPBasicAuth",
        code_anchor=CodeAnchor(file="requests/auth.py", line_start=72, line_end=100),
    ))
    b = graph.add_node(LearningNode(
        title="Trace Session.send",
        code_anchor=CodeAnchor(file="requests/sessions.py", line_start=394, line_end=470),
    ))
    graph.add_edge(a.id, b.id, kind="sequence")
    graph.set_current(a.id)
    return graph


def _pipeline(repo_url, goal, client=None, progress_id=""):
    state = MagicMock()
    state.graph = _two_node_graph()
    state.errors = []
    return state


def _teaching(state, client=None):
    node = state.graph.nodes[state.graph.current_node_id]
    node.cached_lesson = FAKE_LESSON
    state.current_lesson = FAKE_LESSON
    return state


def _grader(classification: str):
    def _apply(state, user_response, client=None):
        node = state.graph.nodes[state.graph.current_node_id]
        mapping = {"understood": "understood", "partial": "partial",
                   "confused": "failed", "off-topic": "failed"}
        if classification in mapping:
            state.graph.mark_understanding(node.id, mapping[classification])
        state.last_grade = {"classification": classification, "rationale": "because"}
        return state
    return _apply


def _inserts_prerequisite(state, signal, client=None, diagnosis=None, origin=None):
    current = state.graph.current_node_id
    prereq = LearningNode(
        title="Prerequisite",
        code_anchor=CodeAnchor(file="requests/models.py", line_start=10, line_end=40),
    )
    state.graph.insert_before(current, prereq, kind="prerequisite")
    state.graph.set_current(prereq.id)
    state.last_mutation = {"kind": "prerequisite", "new_node_id": prereq.id,
                           "anchor_node_id": current}
    return state


def _start(client):
    resp = client.post("/session/start",
                       json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}).json()
    client.get(f"/session/{resp['session_id']}/lesson")  # so /respond has a prompt
    return resp["session_id"], resp["graph"]["current_node_id"]


# ── the graph model ─────────────────────────────────────────────────────────

def test_record_attempt_appends_in_order():
    graph = _two_node_graph()
    node_id = graph.current_node_id

    graph.record_attempt(node_id, "first try", "confused", "missed the point")
    graph.record_attempt(node_id, "second try", "understood", "got it")

    attempts = graph.nodes[node_id].attempts
    assert [a["classification"] for a in attempts] == ["confused", "understood"]
    assert attempts[0]["answer"] == "first try"
    assert attempts[1]["rationale"] == "got it"
    assert all(a["at"] for a in attempts)


def test_attempts_survive_a_state_change():
    # The point of the history: recovering on a second answer must not erase
    # the record of the first, and the weak-spot flag still sticks.
    graph = _two_node_graph()
    node_id = graph.current_node_id

    graph.record_attempt(node_id, "wrong", "confused", "no")
    graph.mark_understanding(node_id, "failed")
    graph.record_attempt(node_id, "right", "understood", "yes")
    graph.mark_understanding(node_id, "understood")

    assert [a["answer"] for a in graph.nodes[node_id].attempts] == ["wrong", "right"]
    assert graph.nodes[node_id].understanding_state == "understood"
    assert graph.nodes[node_id].weak_spot is True


def test_to_dict_exposes_attempts():
    graph = _two_node_graph()
    graph.record_attempt(graph.current_node_id, "a", "partial", "close")

    node = next(n for n in graph.to_dict()["nodes"] if n["id"] == graph.current_node_id)
    assert node["attempts"][0]["classification"] == "partial"


def test_attempts_round_trip_through_sqlite(tmp_path):
    db = tmp_path / "s.db"
    graph = _two_node_graph()
    graph.record_attempt(graph.current_node_id, "my answer", "partial", "close")
    learning_store.save_graph(graph, db)

    loaded = learning_store.load_graph(graph.session_id, db)

    assert loaded is not None
    assert loaded.nodes[graph.current_node_id].attempts[0]["answer"] == "my answer"


def test_nodes_without_history_load_as_empty(tmp_path):
    # Sessions written before the column existed must still load.
    db = tmp_path / "s.db"
    graph = _two_node_graph()
    learning_store.save_graph(graph, db)

    loaded = learning_store.load_graph(graph.session_id, db)

    assert loaded.nodes[graph.current_node_id].attempts == []


# ── /respond ────────────────────────────────────────────────────────────────

@patch("backend.api.clone_repo", return_value="data/repos/requests")
@patch("backend.api.run_teaching", side_effect=_teaching)
@patch("backend.api.run_pipeline", side_effect=_pipeline)
def test_respond_records_the_answer(mock_p, mock_t, mock_c, client):
    session_id, node_id = _start(client)

    with patch("backend.api.run_grader", side_effect=_grader("understood")):
        client.post(f"/session/{session_id}/respond", json={"response": "it returns r"})

    graph = client.get(f"/session/{session_id}").json()
    node = next(n for n in graph["nodes"] if n["id"] == node_id)
    assert len(node["attempts"]) == 1
    assert node["attempts"][0]["answer"] == "it returns r"
    assert node["attempts"][0]["classification"] == "understood"
    assert node["attempts"][0]["rationale"] == "because"


@patch("backend.api.clone_repo", return_value="data/repos/requests")
@patch("backend.api.run_teaching", side_effect=_teaching)
@patch("backend.api.run_pipeline", side_effect=_pipeline)
def test_re_answering_appends_rather_than_replaces(mock_p, mock_t, mock_c, client):
    session_id, node_id = _start(client)

    with patch("backend.api.run_grader", side_effect=_grader("partial")):
        client.post(f"/session/{session_id}/respond",
                    json={"response": "vague", "node_id": node_id})
        client.post(f"/session/{session_id}/respond",
                    json={"response": "sharper", "node_id": node_id})

    graph = client.get(f"/session/{session_id}").json()
    node = next(n for n in graph["nodes"] if n["id"] == node_id)
    assert [a["answer"] for a in node["attempts"]] == ["vague", "sharper"]


@patch("backend.api.clone_repo", return_value="data/repos/requests")
@patch("backend.api.run_teaching", side_effect=_teaching)
@patch("backend.api.run_pipeline", side_effect=_pipeline)
def test_wrong_answer_creates_a_warm_up_automatically(mock_p, mock_t, mock_c, client):
    session_id, _ = _start(client)

    with patch("backend.api.run_grader", side_effect=_grader("confused")), \
         patch("backend.api.mutate_graph", side_effect=_inserts_prerequisite) as mutate:
        body = client.post(f"/session/{session_id}/respond",
                           json={"response": "no idea"}).json()

    assert body["mutation"]["kind"] == "prerequisite"
    assert mutate.call_args.args[1] == "prerequisite"


@patch("backend.api.clone_repo", return_value="data/repos/requests")
@patch("backend.api.run_teaching", side_effect=_teaching)
@patch("backend.api.run_pipeline", side_effect=_pipeline)
def test_partial_answer_does_not_create_a_warm_up(mock_p, mock_t, mock_c, client):
    session_id, _ = _start(client)

    with patch("backend.api.run_grader", side_effect=_grader("partial")), \
         patch("backend.api.mutate_graph", side_effect=_inserts_prerequisite) as mutate:
        body = client.post(f"/session/{session_id}/respond",
                           json={"response": "half right"}).json()

    assert body["mutation"]["kind"] == "none"
    mutate.assert_not_called()


@patch("backend.api.clone_repo", return_value="data/repos/requests")
@patch("backend.api.run_teaching", side_effect=_teaching)
@patch("backend.api.run_pipeline", side_effect=_pipeline)
def test_grade_survives_a_failed_warm_up(mock_p, mock_t, mock_c, client):
    # A broken mutator must not cost the user their grade or their answer.
    session_id, node_id = _start(client)

    with patch("backend.api.run_grader", side_effect=_grader("confused")), \
         patch("backend.api.mutate_graph", side_effect=RuntimeError("sonnet down")):
        body = client.post(f"/session/{session_id}/respond",
                           json={"response": "no idea"}).json()

    assert body["classification"] == "confused"
    assert body["mutation"]["kind"] == "none"
    graph = client.get(f"/session/{session_id}").json()
    node = next(n for n in graph["nodes"] if n["id"] == node_id)
    assert node["attempts"][0]["answer"] == "no idea"


# ── gap_kind (B1) ─────────────────────────────────────────────────────────────

def _grader_with_gap(classification: str, gap_kind: str):
    def _apply(state, user_response, client=None):
        node = state.graph.nodes[state.graph.current_node_id]
        mapping = {"understood": "understood", "partial": "partial",
                   "confused": "failed"}
        if classification in mapping:
            state.graph.mark_understanding(node.id, mapping[classification])
        state.last_grade = {
            "classification": classification,
            "gap_kind": gap_kind,
            "rationale": "because",
        }
        return state
    return _apply


@patch("backend.api.clone_repo", return_value="data/repos/requests")
@patch("backend.api.run_teaching", side_effect=_teaching)
@patch("backend.api.run_pipeline", side_effect=_pipeline)
def test_why_the_answer_fell_short_is_persisted_with_it(mock_p, mock_t, mock_c, client):
    # Two answers can be equally wrong and want opposite responses. The history
    # has to remember which kind of wrong, or B5's adaptation cannot look back.
    session_id, node_id = _start(client)

    with patch(
        "backend.api.run_grader",
        side_effect=_grader_with_gap("confused", "wrong_model"),
    ):
        body = client.post(
            f"/session/{session_id}/respond", json={"response": "adapters are on the request"}
        ).json()

    assert body["gap_kind"] == "wrong_model"
    graph = client.get(f"/session/{session_id}").json()
    node = next(n for n in graph["nodes"] if n["id"] == node_id)
    assert node["attempts"][0]["gap_kind"] == "wrong_model"


@patch("backend.api.clone_repo", return_value="data/repos/requests")
@patch("backend.api.run_teaching", side_effect=_teaching)
@patch("backend.api.run_pipeline", side_effect=_pipeline)
def test_a_grade_without_a_gap_records_none(mock_p, mock_t, mock_c, client):
    session_id, node_id = _start(client)

    with patch("backend.api.run_grader", side_effect=_grader("understood")):
        client.post(f"/session/{session_id}/respond", json={"response": "yes"})

    graph = client.get(f"/session/{session_id}").json()
    node = next(n for n in graph["nodes"] if n["id"] == node_id)
    assert node["attempts"][0]["gap_kind"] == "none"


def test_attempts_recorded_before_gap_kind_existed_still_load(tmp_path):
    db = tmp_path / "s.db"
    graph = _two_node_graph()
    node = graph.nodes[graph.current_node_id]
    # Exactly the shape the store wrote before this field existed.
    node.attempts.append(
        {"answer": "a", "classification": "partial", "rationale": "close",
         "at": "2026-08-01T00:00:00+00:00"}
    )
    learning_store.save_graph(graph, db)

    loaded = learning_store.load_graph(graph.session_id, db)

    attempt = loaded.nodes[graph.current_node_id].attempts[0]
    assert attempt["classification"] == "partial"
    assert "gap_kind" not in attempt
