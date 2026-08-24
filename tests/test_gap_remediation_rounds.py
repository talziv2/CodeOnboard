"""F100 — the node's remediation budget is actually spent.

`GapState.remediation_rounds` was declared, persisted, deserialized, and read by
`decide_all`'s cap — and written by nothing. `REMEDIATION_ROUND_CAP = 4` was
therefore dead code and the per-node remediation loop was unbounded. Found live
in S0: a warm-up was spliced into a real session and the node's counter stayed
`0`, which is also why a sweep of 759 stored nodes reporting "0 remediation
rounds" proved nothing either way.

What a ROUND is, and why it is not just the structural ones: `decide_all` picks
the action from gap precedence, so a node whose leading gap is
`right_idea_wrong_altitude` earns `followup` every time. If only warm-ups were
counted, that node could be remediated forever and never reach a cap. What bounds
the loop is the number of times the system has responded to this node with help,
whichever form the help took.

Charged for help that LANDED. A prerequisite the Mutator declined and a re-teach
that raised both leave the learner with nothing new, and charging for them would
spend the budget on the system's own failures.

Verifications are not counted here — that is the per-GAP budget, kept by
`Gap.record_failed_verification` (§18.16.1, LQ10).

Run with: uv run pytest tests/test_gap_remediation_rounds.py -v
"""
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import TEST_USER_ID, start_session
from fastapi.testclient import TestClient

import backend.api as api
from backend.learning import store as learning_store
from backend.learning.adaptation import decide_all
from backend.learning.gaps import REMEDIATION_ROUND_CAP, Gap
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode

from tests.test_session_api import (
    FAKE_GOAL,
    FAKE_REPO_URL,
    _mutator_inserts_prerequisite,
    _teaching_side_effect,
)


@pytest.fixture(autouse=True)
def _env_and_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("CODEONBOARD_GAPS", "1")
    monkeypatch.setattr(api, "SESSIONS_DB_PATH", tmp_path / "sessions.db")
    monkeypatch.setattr(api.anthropic, "Anthropic", lambda **kw: MagicMock())


@pytest.fixture
def client():
    return TestClient(api.app)


def _graph(*gaps: Gap) -> LearningGraph:
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    a = graph.add_node(LearningNode(
        title="Understand what the adapter owns",
        code_anchor=CodeAnchor(file="requests/adapters.py", line_start=1, line_end=40),
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
    a.gap_state.gaps.extend(gaps)
    return graph


def _start(client, graph) -> str:
    """One session, so several answers can accumulate on the same node."""
    def _pipeline(repo_url, goal, client=None, progress_id=""):
        state = MagicMock()
        state.graph = graph
        state.errors = []
        return state

    with patch("backend.api.run_pipeline", side_effect=_pipeline), \
         patch("backend.api.run_teaching", side_effect=_teaching_side_effect), \
         patch("backend.api.clone_repo", return_value="data/repos/requests"):
        body = start_session(client, FAKE_REPO_URL, FAKE_GOAL)
        session_id = body["session_id"]
        client.get(f"/session/{session_id}/lesson")
    return session_id


def _answer(client, session_id, classification, gap_kind, *, mutator=None):
    def _grader(state, user_response, client=None):
        state.last_grade = {"classification": classification,
                            "gap_kind": gap_kind, "rationale": "because"}
        return state

    with patch("backend.api.run_grader", side_effect=_grader), \
         patch("backend.api.mutate_graph",
               side_effect=mutator or _mutator_inserts_prerequisite), \
         patch("backend.api.clone_repo", return_value="data/repos/requests"), \
         patch("backend.api._node_source", return_value="source"), \
         patch("backend.api.teaching_respond") as respond:
        respond.reteach.return_value = MagicMock()
        respond.hint.return_value = "h"
        respond.followup.return_value = "f"
        return client.post(
            f"/session/{session_id}/respond", json={"response": "my answer"}
        ).json()


def _rounds(session_id, node_id) -> int:
    """Read it back from persistence, not from the object in memory."""
    graph = learning_store.load_graph(session_id, TEST_USER_ID, api.SESSIONS_DB_PATH)
    return graph.nodes[node_id].gap_state.remediation_rounds


def _declines(state, kind, client=None, diagnosis=None, origin=None):
    """The Mutator finding no candidate smaller than the stop they are on."""
    state.last_mutation = {"kind": "none", "reason": "no_useful_prerequisite"}
    return state


# ── 1. help that landed is charged ───────────────────────────────────────────


def test_a_reteach_charges_one_round(client):
    graph = _graph(Gap.create("wrong_model", "the adapter builds the request"))
    node_id = graph.current_node_id
    session_id = _start(client, graph)
    assert _rounds(session_id, node_id) == 0

    result = _answer(client, session_id, "confused", "wrong_model")
    assert result["adaptation"]["kind"] == "reteach"
    assert _rounds(session_id, node_id) == 1


def test_a_spliced_warm_up_charges_one_round(client):
    graph = _graph(Gap.create("missing_prerequisite", "no idea what an adapter is"))
    node_id = graph.current_node_id
    session_id = _start(client, graph)

    result = _answer(client, session_id, "confused", "missing_prerequisite")
    assert result["mutation"]["kind"] == "prerequisite"
    assert _rounds(session_id, node_id) == 1


def test_a_followup_charges_a_round_too(client):
    """The case that makes counting only structural changes wrong: this node
    earns `followup` every time, so a warm-up-only counter would never cap it."""
    graph = _graph(Gap.create("right_idea_wrong_altitude", "h() is always admissible"))
    node_id = graph.current_node_id
    session_id = _start(client, graph)

    result = _answer(client, session_id, "partial", "right_idea_wrong_altitude")
    assert result["adaptation"]["kind"] == "followup"
    assert _rounds(session_id, node_id) == 1


def test_rounds_accumulate_across_answers(client):
    graph = _graph(Gap.create("wrong_model", "the adapter builds the request"))
    node_id = graph.current_node_id
    session_id = _start(client, graph)

    for expected in (1, 2, 3):
        _answer(client, session_id, "confused", "wrong_model")
        assert _rounds(session_id, node_id) == expected


# ── 2. the system's own failures are not charged to the learner ──────────────


def test_an_understood_answer_charges_nothing(client):
    """`understood` earns no response, so there is no round to charge for."""
    graph = _graph(Gap.create("wrong_model", "the adapter builds the request"))
    node_id = graph.current_node_id
    session_id = _start(client, graph)

    result = _answer(client, session_id, "understood", "none")
    assert result["adaptation"]["kind"] == "none"
    assert _rounds(session_id, node_id) == 0


def test_a_declined_warm_up_charges_nothing(client):
    graph = _graph(Gap.create("missing_prerequisite", "no idea what an adapter is"))
    node_id = graph.current_node_id
    session_id = _start(client, graph)

    result = _answer(client, session_id, "confused", "missing_prerequisite",
                     mutator=_declines)
    assert result["mutation"]["kind"] == "none"
    assert _rounds(session_id, node_id) == 0


# ── 3. the learner-requested path spends the same budget ─────────────────────


def test_a_learner_requested_warm_up_charges_a_round(client):
    graph = _graph(Gap.create("missing_prerequisite", "no idea what an adapter is"))
    node_id = graph.current_node_id
    session_id = _start(client, graph)

    with patch("backend.api.mutate_graph", side_effect=_mutator_inserts_prerequisite), \
         patch("backend.api.clone_repo", return_value="data/repos/requests"), \
         patch("backend.api.run_teaching", side_effect=_teaching_side_effect), \
         patch("backend.api._render_current_lesson", return_value={"prompt": "p"}):
        body = client.post(f"/session/{session_id}/retry", json={"node_id": node_id}).json()

    assert body["inserted"] is True
    assert _rounds(session_id, node_id) == 1


def test_a_declined_learner_request_charges_nothing(client):
    """The S0 case exactly: `no_useful_prerequisite`, and nothing spent."""
    graph = _graph(Gap.create("missing_prerequisite", "no idea what an adapter is"))
    node_id = graph.current_node_id
    session_id = _start(client, graph)

    with patch("backend.api.mutate_graph", side_effect=_declines), \
         patch("backend.api.clone_repo", return_value="data/repos/requests"):
        body = client.post(f"/session/{session_id}/retry", json={"node_id": node_id}).json()

    assert body["inserted"] is False
    assert _rounds(session_id, node_id) == 0


# ── 4. and the cap it exists for can now fire ────────────────────────────────


def test_the_cap_ends_the_offering_but_not_the_obligation(client):
    """Reaching the cap stops the system PROPOSING. The gap stays open, stays
    blocking, and stays counted — §18.16.1."""
    gap = Gap.create("wrong_model", "the adapter builds the request")
    plan = decide_all("confused", [gap], "wrong_model",
                      remediation_rounds=REMEDIATION_ROUND_CAP)
    assert plan.action == "none"
    assert gap.is_open
    assert gap.is_blocking
    assert gap.id in [g.id for g in plan.deferred]


def test_a_capped_node_stops_earning_remediation_through_respond(client):
    """The end-to-end version: spend the budget, then confirm the next wrong
    answer earns nothing and the counter stops climbing."""
    graph = _graph(Gap.create("wrong_model", "the adapter builds the request"))
    node_id = graph.current_node_id
    session_id = _start(client, graph)

    for _ in range(REMEDIATION_ROUND_CAP):
        _answer(client, session_id, "confused", "wrong_model")
    assert _rounds(session_id, node_id) == REMEDIATION_ROUND_CAP

    result = _answer(client, session_id, "confused", "wrong_model")
    assert result["adaptation"]["kind"] == "none"
    assert _rounds(session_id, node_id) == REMEDIATION_ROUND_CAP


def test_a_capped_node_refuses_a_check_rather_than_inventing_one(client):
    """What the frontend's `nothing_to_verify` corresponds to. The gap is still
    open; there is simply no question left to ask about it."""
    graph = _graph(Gap.create("wrong_model", "the adapter builds the request"))
    node_id = graph.current_node_id
    session_id = _start(client, graph)

    for _ in range(REMEDIATION_ROUND_CAP):
        _answer(client, session_id, "confused", "wrong_model")

    res = client.post(f"/session/{session_id}/verify", json={"node_id": node_id})
    assert res.status_code == 409
    assert res.json()["detail"] == "nothing_to_verify"
