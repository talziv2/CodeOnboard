"""
Pytest tests for adaptation through the /respond endpoint.
Run with: uv run pytest tests/test_adaptation_api.py -v

test_adaptation.py covers the policy in isolation. What must hold here: the
right response is actually invoked, only `missing_prerequisite` touches the
graph, a failed adaptation never costs the grade that prompted it, and the
attempt history records every answer regardless of what the system did about it.
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import backend.api as api
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode

from tests.test_session_api import (
    FAKE_GOAL,
    FAKE_LESSON,
    FAKE_REPO_URL,
    _mutator_inserts_prerequisite,
    _teaching_side_effect,
)


@pytest.fixture(autouse=True)
def _env_and_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(api, "SESSIONS_DB_PATH", tmp_path / "sessions.db")
    monkeypatch.setattr(api.anthropic, "Anthropic", lambda **kw: MagicMock())


@pytest.fixture
def client():
    return TestClient(api.app)


def _graph() -> LearningGraph:
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    a = graph.add_node(LearningNode(
        title="Understand the adapter layer",
        code_anchor=CodeAnchor(file="requests/adapters.py", line_start=1, line_end=20),
        concept_tags=["architecture"],
        lesson_brief={"objective": "Explain what the adapter owns",
                      "area_id": "a1", "priority": "required"},
    ))
    b = graph.add_node(LearningNode(
        title="Trace the send",
        code_anchor=CodeAnchor(file="requests/sessions.py", line_start=1, line_end=20),
        concept_tags=["flow"],
        lesson_brief={"objective": "Trace it", "area_id": "a1", "priority": "required"},
    ))
    graph.add_edge(a.id, b.id, kind="sequence")
    graph.set_current(a.id)
    return graph


def _pipeline(repo_url, goal, client=None):
    state = MagicMock()
    state.graph = _graph()
    state.errors = []
    return state


def _grader(classification: str, gap_kind: str):
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


def _start(client) -> tuple[str, str]:
    body = client.post(
        "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
    ).json()
    session_id = body["session_id"]
    client.get(f"/session/{session_id}/lesson")
    return session_id, body["graph"]["current_node_id"]


def _respond(client, session_id: str, classification: str, gap_kind: str):
    """Grade an answer with a scripted verdict. Callers patch the adaptation."""
    with patch("backend.api.run_grader", side_effect=_grader(classification, gap_kind)), \
         patch("backend.api.mutate_graph", side_effect=_mutator_inserts_prerequisite), \
         patch("backend.api._node_source", return_value="source"):
        return client.post(
            f"/session/{session_id}/respond", json={"response": "my answer"}
        ).json()


PIPE = patch("backend.api.run_pipeline", side_effect=_pipeline)
TEACH = patch("backend.api.run_teaching", side_effect=_teaching_side_effect)
CLONE = patch("backend.api.clone_repo", return_value="data/repos/requests")


@CLONE
@TEACH
@PIPE
def test_not_knowing_gets_a_hint_and_leaves_the_graph_alone(p, t, c, client):
    session_id, _ = _start(client)
    with patch("backend.api.teaching_respond.hint", return_value="Start at line 3."):
        body = _respond(client, session_id, "confused", "no_attempt")

    assert body["adaptation"]["kind"] == "hint"
    assert body["adaptation"]["text"] == "Start at line 3."
    graph = client.get(f"/session/{session_id}").json()
    assert len(graph["nodes"]) == 2          # nothing inserted
    assert body["mutation"]["kind"] == "none"


@CLONE
@TEACH
@PIPE
def test_a_misconception_is_retaught_rather_than_remediated(p, t, c, client):
    session_id, _ = _start(client)
    with patch("backend.api.teaching_respond.reteach", return_value=MagicMock()) as rt:
        body = _respond(client, session_id, "confused", "wrong_model")

    assert body["adaptation"] == {"kind": "reteach", "retaught": True}
    rt.assert_called_once()
    graph = client.get(f"/session/{session_id}").json()
    assert len(graph["nodes"]) == 2


@CLONE
@TEACH
@PIPE
def test_a_missing_foundation_is_the_only_thing_that_grows_the_graph(p, t, c, client):
    session_id, _ = _start(client)
    body = _respond(client, session_id, "confused", "missing_prerequisite")

    assert body["adaptation"]["kind"] == "prerequisite"
    assert body["mutation"]["kind"] == "prerequisite"
    graph = client.get(f"/session/{session_id}").json()
    assert len(graph["nodes"]) == 3


@CLONE
@TEACH
@PIPE
def test_the_right_idea_at_the_wrong_level_gets_a_follow_up(p, t, c, client):
    session_id, _ = _start(client)
    with patch("backend.api.teaching_respond.followup", return_value="Zoom out: …"):
        body = _respond(client, session_id, "confused", "right_idea_wrong_altitude")

    assert body["adaptation"]["kind"] == "followup"
    assert body["adaptation"]["text"].startswith("Zoom out")
    graph = client.get(f"/session/{session_id}").json()
    assert len(graph["nodes"]) == 2


@CLONE
@TEACH
@PIPE
def test_an_understood_answer_earns_no_adaptation(p, t, c, client):
    session_id, _ = _start(client)
    body = _respond(client, session_id, "understood", "none")
    assert body["adaptation"]["kind"] == "none"


@CLONE
@TEACH
@PIPE
def test_a_failed_hint_never_costs_the_grade(p, t, c, client):
    # Every adaptation is enrichment on top of a verdict that already exists.
    session_id, node_id = _start(client)
    with patch("backend.api.teaching_respond.hint", return_value=None):
        body = _respond(client, session_id, "confused", "no_attempt")

    assert body["classification"] == "confused"
    assert body["adaptation"]["text"] is None
    graph = client.get(f"/session/{session_id}").json()
    node = next(n for n in graph["nodes"] if n["id"] == node_id)
    assert node["attempts"][0]["gap_kind"] == "no_attempt"


@CLONE
@TEACH
@PIPE
def test_a_reteach_that_raises_never_costs_the_grade(p, t, c, client):
    session_id, _ = _start(client)
    # §4.1.2: a re-teach is still a lesson, so an unreadable source must fail it
    # rather than let it be written from the objective alone.
    with patch("backend.api._node_source", side_effect=FileNotFoundError("gone")), \
         patch("backend.api.run_grader", side_effect=_grader("confused", "wrong_model")):
        body = client.post(
            f"/session/{session_id}/respond", json={"response": "x"}
        ).json()

    assert body["classification"] == "confused"
    assert body["adaptation"]["retaught"] is False


@CLONE
@TEACH
@PIPE
def test_every_answer_is_recorded_whatever_the_system_did_about_it(p, t, c, client):
    session_id, node_id = _start(client)
    with patch("backend.api.teaching_respond.hint", return_value="hint"):
        _respond(client, session_id, "confused", "no_attempt")

    graph = client.get(f"/session/{session_id}").json()
    node = next(n for n in graph["nodes"] if n["id"] == node_id)
    assert node["attempts"][0]["answer"] == "my answer"
    assert node["attempts"][0]["classification"] == "confused"


@CLONE
@TEACH
@PIPE
def test_pruning_ahead_is_reported_when_it_fires(p, t, c, client):
    session_id, node_id = _start(client)
    # Two understood units in one area, with a recommended one still ahead.
    graph = api.learning_store.load_graph(session_id, api.SESSIONS_DB_PATH)
    order = graph.path_order()
    graph.nodes[order[1]].understanding_state = "understood"
    graph.nodes[order[1]].visited = True
    extra = graph.add_node(LearningNode(
        title="Optional depth",
        code_anchor=CodeAnchor(file="a.py", line_start=1, line_end=2),
        lesson_brief={"objective": "x", "area_id": "a1", "priority": "recommended"},
    ))
    graph.add_edge(order[1], extra.id, kind="sequence")
    api.learning_store.save_graph(graph, api.SESSIONS_DB_PATH)

    body = _respond(client, session_id, "understood", "none")

    assert body["adaptation"].get("pruned") == 1
    after = client.get(f"/session/{session_id}").json()
    assert next(n for n in after["nodes"] if n["id"] == extra.id)["priority"] == "optional"


# ── a named gap outranks the coarse classification (live-found defect) ────────

@CLONE
@TEACH
@PIPE
def test_off_topic_with_a_named_missing_prerequisite_still_remediates(p, t, c, client):
    # Found in live fastapi validation: the Grader reported
    # `missing_prerequisite` and the policy discarded it because the same answer
    # was also `off-topic`, so a learner stuck on a foundation got nothing.
    session_id, _ = _start(client)
    body = _respond(client, session_id, "off-topic", "missing_prerequisite")

    assert body["adaptation"]["kind"] == "prerequisite"
    assert body["mutation"]["kind"] == "prerequisite"
    graph = client.get(f"/session/{session_id}").json()
    assert len(graph["nodes"]) == 3


@CLONE
@TEACH
@PIPE
def test_an_unrelated_off_topic_answer_still_changes_nothing(p, t, c, client):
    # The guard that must survive the fix: no named gap, no evidence, no change.
    session_id, node_id = _start(client)
    body = _respond(client, session_id, "off-topic", "none")

    assert body["adaptation"]["kind"] == "none"
    assert body["mutation"]["kind"] == "none"
    graph = client.get(f"/session/{session_id}").json()
    assert len(graph["nodes"]) == 2
    node = next(n for n in graph["nodes"] if n["id"] == node_id)
    # And it still does not touch the earned state or the weak-spot flag.
    assert node["understanding_state"] == "not_started"
    assert node["weak_spot"] is False


# ── the warm-up is chosen for the diagnosis, not just for the node (§18.2) ────


@CLONE
@TEACH
@PIPE
def test_respond_passes_the_graded_answer_into_prerequisite_generation(p, t, c, client):
    """The branch that reshapes the graph now sees what the learner wrote.

    `hint`, `followup` and `reteach` always did; `prerequisite` did not, so it
    selected a warm-up for the NODE from structural candidates alone.
    """
    session_id, _ = _start(client)
    seen = {}

    def _capture(state, signal, client=None, diagnosis=None):
        seen["diagnosis"] = diagnosis
        state.last_mutation = {"kind": "none"}
        return state

    with patch("backend.api.run_grader",
               side_effect=_grader("confused", "missing_prerequisite")), \
         patch("backend.api.mutate_graph", side_effect=_capture):
        client.post(f"/session/{session_id}/respond",
                    json={"response": "depth is filled in later by the search"})

    diagnosis = seen["diagnosis"]
    assert diagnosis is not None
    assert diagnosis.answer == "depth is filled in later by the search"
    assert diagnosis.rationale == "because"
    assert diagnosis.gap_kind == "missing_prerequisite"


@CLONE
@TEACH
@PIPE
def test_retry_recovers_the_diagnosis_from_the_recorded_attempt(p, t, c, client):
    """A learner-requested warm-up carries the diagnosis even with no grade in scope.

    `/retry` passes none, so the Mutator reads the node's own attempt history —
    which nothing read before this fix.
    """
    session_id, node_id = _start(client)
    with patch("backend.api.run_grader",
               side_effect=_grader("confused", "wrong_model")), \
         patch("backend.api._node_source", return_value="source"), \
         patch("backend.api.teaching_respond.reteach", return_value=None):
        client.post(f"/session/{session_id}/respond",
                    json={"response": "solution() returns states and actions"})

    seen = {}

    def _capture(state, signal, client=None, diagnosis=None):
        from backend.agents.mentor.mutator import Diagnosis
        node = state.graph.nodes[state.graph.current_node_id]
        seen["recovered"] = Diagnosis.from_attempt(
            node.attempts[-1] if node.attempts else None
        )
        state.last_mutation = {"kind": "none"}
        return state

    with patch("backend.api.mutate_graph", side_effect=_capture):
        client.post(f"/session/{session_id}/retry", json={"node_id": node_id})

    recovered = seen["recovered"]
    assert recovered is not None
    assert recovered.answer == "solution() returns states and actions"
    assert recovered.gap_kind == "wrong_model"
