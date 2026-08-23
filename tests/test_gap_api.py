"""M9 (backend half) — the gap surface over HTTP.

gap-model.md M9, §18.10. Three endpoints' worth of contract:

  /respond   gains `gaps` — "the product's most honest surface: it tells the
             learner what they still do not know, by name" — and accepts
             `kind="verification"` to grade an answer to a verification question.
  /verify    returns a FRESH question aimed at ONE gap. Replaces "Try again",
             which re-showed the answered question after `reveal` had already
             given the reasoning away.
  /waive     stops the system asking, per gap or per node. Never evidence.

The invariant M9 is held to is **compatibility**: every pre-existing response key
survives, so a client that has not been updated keeps working. That is asserted
as a superset, not an exact set — a key vanishing is the failure, a key being
added is the point.

The frontend half (RouteRail, strings) is deliberately not touched here; it waits
on the concurrent frontend work.

Run with: uv run pytest tests/test_gap_api.py -v
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import TEST_USER_ID
from fastapi.testclient import TestClient

import backend.api as api
from backend.learning import history
from backend.learning import store as learning_store
from backend.learning.gaps import VERIFICATION_ATTEMPT_CAP, Gap
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode

from tests.test_session_api import (
    FAKE_GOAL,
    FAKE_REPO_URL,
    _teaching_side_effect,
)


CLAIM = "the handler opens the connection to read the server's challenge"


@pytest.fixture(autouse=True)
def _env_and_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("CODEONBOARD_GAPS", "1")
    monkeypatch.setattr(api, "SESSIONS_DB_PATH", tmp_path / "sessions.db")
    monkeypatch.setattr(api.anthropic, "Anthropic", lambda **kw: MagicMock())


@pytest.fixture
def client():
    return TestClient(api.app)


def _node(title: str, state: str = "partial") -> LearningNode:
    node = LearningNode(
        title=title,
        code_anchor=CodeAnchor(file="requests/sessions.py", line_start=1, line_end=20),
        lesson_brief={"objective": f"Explain {title}", "priority": "required"},
    )
    node.understanding_state = state
    node.cached_lesson = {"prompt": "the original question", "setup": "…"}
    return node


def _graph(*nodes: LearningNode) -> LearningGraph:
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    for node in nodes:
        graph.add_node(node)
    for a, b in zip(nodes, nodes[1:]):
        graph.add_edge(a.id, b.id, kind="sequence")
    graph.set_current(nodes[0].id)
    return graph


def _start(client, graph) -> str:
    def _pipeline(repo_url, goal, client=None, progress_id=""):
        state = MagicMock()
        state.graph = graph
        state.errors = []
        return state

    with patch("backend.api.run_pipeline", side_effect=_pipeline), \
         patch("backend.api.run_teaching", side_effect=_teaching_side_effect):
        return client.post(
            "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
        ).json()["session_id"]


def _stored(session_id):
    return learning_store.load_graph(session_id, TEST_USER_ID, api.SESSIONS_DB_PATH)


# ── /respond: the gaps list ──────────────────────────────────────────────────


def _respond(client, session_id, classification="confused", gap_kind="wrong_model",
             **body):
    def _grader(state, user_response, client=None):
        state.last_grade = {"classification": classification,
                            "gap_kind": gap_kind, "rationale": "because"}
        return state

    with patch("backend.api.run_grader", side_effect=_grader), \
         patch("backend.api._node_source", return_value="source"), \
         patch("backend.api.teaching_respond") as respond, \
         patch("backend.api.mutate_graph"):
        respond.reteach.return_value = MagicMock()
        respond.hint.return_value = "h"
        respond.followup.return_value = "f"
        return client.post(
            f"/session/{session_id}/respond",
            json={"response": "my answer", **body},
        )


def test_respond_returns_the_open_gaps_by_name(client):
    node = _node("A")
    gap = Gap.create("wrong_model", CLAIM, objective_part="what the handler owns")
    node.gap_state.gaps.append(gap)
    session_id = _start(client, _graph(node, _node("B")))

    body = _respond(client, session_id).json()

    assert len(body["gaps"]) == 1
    shown = body["gaps"][0]
    assert shown["id"] == gap.id
    assert shown["claim"] == CLAIM
    assert shown["kind"] == "wrong_model"
    assert shown["status"] == "open"
    assert shown["blocking"] is True
    assert shown["objective_part"] == "what the handler owns"


def test_respond_sends_settled_gaps_with_their_status(client):
    """The payload is a LEDGER, not a debt column.

    It sent open gaps only, which meant the one act a learner can perform on a
    gap — closing it — deleted the row. Success erased its own record. So every
    gap ships, and `status` is what distinguishes outstanding work from repaired
    work; the client filters for whichever it is rendering.
    """
    node = _node("A")
    verified, waived, open_ = (
        Gap.create("wrong_model", "v"), Gap.create("wrong_model", "w"),
        Gap.create("wrong_model", CLAIM),
    )
    verified.mark_verified(0)
    waived.waive()
    node.gap_state.gaps.extend([verified, waived, open_])
    session_id = _start(client, _graph(node, _node("B")))

    body = _respond(client, session_id).json()
    assert {g["claim"]: g["status"] for g in body["gaps"]} == {
        "v": "verified", "w": "waived", CLAIM: "open",
    }
    # A settled gap carries when it settled, so the ledger can say so.
    assert next(g for g in body["gaps"] if g["claim"] == "v")["closed_at"]
    assert next(g for g in body["gaps"] if g["claim"] == CLAIM)["closed_at"] is None


def test_respond_reports_a_non_blocking_gap_as_not_blocking(client):
    node = _node("A")
    node.gap_state.gaps.append(Gap.create("right_idea_wrong_altitude", "too low"))
    session_id = _start(client, _graph(node, _node("B")))
    body = _respond(client, session_id, gap_kind="right_idea_wrong_altitude").json()
    assert body["gaps"][0]["blocking"] is False


def test_respond_exposes_the_verification_budget(client):
    """So the UI can stop offering a check the system has stopped proposing."""
    node = _node("A")
    gap = Gap.create("wrong_model", CLAIM)
    gap.verification_attempts = VERIFICATION_ATTEMPT_CAP
    node.gap_state.gaps.append(gap)
    session_id = _start(client, _graph(node, _node("B")))
    shown = _respond(client, session_id).json()["gaps"][0]
    assert shown["verification_attempts"] == VERIFICATION_ATTEMPT_CAP
    assert shown["exhausted"] is True


def test_respond_reports_journey_completion(client):
    node = _node("A", "understood")
    session_id = _start(client, _graph(node))
    body = _respond(client, session_id, "understood", "none").json()
    assert body["complete"] is True


def test_a_client_that_sends_no_kind_gets_the_assessment_path(client):
    """The compatibility default: verification is opt-in per request."""
    node = _node("A")
    node.gap_state.gaps.append(Gap.create("wrong_model", CLAIM))
    session_id = _start(client, _graph(node, _node("B")))
    body = _respond(client, session_id).json()
    assert body["classification"] == "confused"
    assert body["gap_kind"] == "wrong_model"


# ── POST /verify ─────────────────────────────────────────────────────────────


def _verify(client, session_id, question="a fresh question about a new case",
            **body):
    def _make(state, node, gaps, source, client=None):
        from backend.agents.teaching.verify import VerificationPrompt
        return VerificationPrompt(question=question, targets=[g.id for g in gaps])

    with patch("backend.api.teaching_verify.verify", side_effect=_make), \
         patch("backend.api._node_source", return_value="source"):
        return client.post(f"/session/{session_id}/verify", json=body)


def test_verify_returns_a_question_and_no_answer(client):
    """No `reveal`, no expected answer — shipping the answer beside the question
    is what made re-asking meaningless (§18.7)."""
    node = _node("A")
    gap = Gap.create("wrong_model", CLAIM)
    node.gap_state.gaps.append(gap)
    session_id = _start(client, _graph(node))

    body = _verify(client, session_id).json()

    assert body["question"] == "a fresh question about a new case"
    assert body["targets"] == [gap.id]
    assert "reveal" not in body
    assert "expected_answer" not in body


def test_verify_aims_at_one_gap_even_when_several_are_open(client):
    """Asking about three at once lets an answer address one and appear to have
    addressed all three."""
    node = _node("A")
    for i in range(3):
        node.gap_state.gaps.append(Gap.create("wrong_model", f"claim {i}"))
    session_id = _start(client, _graph(node))
    assert len(_verify(client, session_id).json()["targets"]) == 1


def test_verify_targets_the_highest_precedence_gap(client):
    node = _node("A")
    altitude = Gap.create("right_idea_wrong_altitude", "too low")
    foundation = Gap.create("missing_prerequisite", "no idea what a socket is")
    node.gap_state.gaps.extend([altitude, foundation])
    session_id = _start(client, _graph(node))
    assert _verify(client, session_id).json()["targets"] == [foundation.id]


def test_verify_stores_the_question_on_the_node(client):
    node = _node("A")
    node.gap_state.gaps.append(Gap.create("wrong_model", CLAIM))
    session_id = _start(client, _graph(node))
    _verify(client, session_id)
    pending = _stored(session_id).nodes[node.id].gap_state.pending_verification
    assert pending["question"] == "a fresh question about a new case"


def test_verify_refuses_when_there_is_nothing_to_verify(client):
    node = _node("A")
    session_id = _start(client, _graph(node))
    got = _verify(client, session_id)
    assert got.status_code == 409
    assert got.json()["detail"] == "nothing_to_verify"


def test_verify_refuses_an_exhausted_gap(client):
    """The cap stops the system PROPOSING. The gap stays open and blocking."""
    node = _node("A")
    gap = Gap.create("wrong_model", CLAIM)
    gap.verification_attempts = VERIFICATION_ATTEMPT_CAP
    node.gap_state.gaps.append(gap)
    session_id = _start(client, _graph(node))
    assert _verify(client, session_id).status_code == 409
    assert _stored(session_id).nodes[node.id].gaps[0].status == "open"


def test_verify_reports_generation_failure_rather_than_inventing_a_question(client):
    node = _node("A")
    node.gap_state.gaps.append(Gap.create("wrong_model", CLAIM))
    session_id = _start(client, _graph(node))
    with patch("backend.api.teaching_verify.verify", return_value=None), \
         patch("backend.api._node_source", return_value="source"):
        got = client.post(f"/session/{session_id}/verify", json={})
    assert got.status_code == 503


def test_verify_refuses_without_readable_source(client):
    """§4.1.2: with no source the model invents the scenario, and failing an
    imaginary question would record real evidence about it."""
    node = _node("A")
    node.gap_state.gaps.append(Gap.create("wrong_model", CLAIM))
    session_id = _start(client, _graph(node))
    with patch("backend.api._node_source", side_effect=RuntimeError("gone")):
        got = client.post(f"/session/{session_id}/verify", json={})
    assert got.status_code == 409
    assert got.json()["detail"] == "source_unavailable"


# ── /respond with kind="verification" ────────────────────────────────────────


def _grade_verification(resolved_ids, rationale="r", new_gaps=None):
    def _fake(state, node, answer, client=None):
        for gap in node.gaps:
            if gap.id in resolved_ids:
                gap.mark_verified(len(node.attempts))
        node.gap_state.pending_verification = None
        return {
            "resolved": list(resolved_ids),
            "unresolved": [g.id for g in node.gaps if g.is_open],
            "new_gaps": len(new_gaps or []),
            "rationale": rationale,
        }
    return _fake


def test_a_verification_answer_closes_the_gap_it_demonstrated(client):
    node = _node("A")
    gap = Gap.create("wrong_model", CLAIM)
    node.gap_state.gaps.append(gap)
    session_id = _start(client, _graph(node))
    _verify(client, session_id)

    with patch("backend.api.grade_verification",
               side_effect=_grade_verification([gap.id])):
        body = client.post(
            f"/session/{session_id}/respond",
            json={"response": "the right answer", "kind": "verification"},
        ).json()

    assert body["kind"] == "verification"
    assert body["resolved"] == [gap.id]
    # THE ROW SURVIVES ITS OWN CLOSURE. It used to leave the payload here, which
    # made the learner's one success the one thing they could not see afterwards.
    assert [(g["id"], g["status"]) for g in body["gaps"]] == [(gap.id, "verified")]
    assert _stored(session_id).nodes[node.id].gaps[0].status == "verified"


def test_a_verification_answer_is_recorded_with_its_own_kind(client):
    """So it can never be pooled with answers to the objective."""
    node = _node("A")
    gap = Gap.create("wrong_model", CLAIM)
    node.gap_state.gaps.append(gap)
    session_id = _start(client, _graph(node))
    _verify(client, session_id)

    with patch("backend.api.grade_verification",
               side_effect=_grade_verification([gap.id])):
        client.post(f"/session/{session_id}/respond",
                    json={"response": "answer", "kind": "verification"})

    attempts = _stored(session_id).nodes[node.id].attempts
    assert attempts[-1]["kind"] == history.VERIFICATION
    assert history.assessments(attempts) == []   # excluded from assessment views


def test_a_verification_answer_runs_no_adaptation(client):
    """The outcome of a verification is a gap closing or not closing — not a
    hint, a re-teach or a warm-up."""
    node = _node("A")
    gap = Gap.create("wrong_model", CLAIM)
    node.gap_state.gaps.append(gap)
    session_id = _start(client, _graph(node))
    _verify(client, session_id)

    with patch("backend.api.grade_verification",
               side_effect=_grade_verification([])), \
         patch("backend.api.teaching_respond") as respond, \
         patch("backend.api.mutate_graph") as mutate:
        body = client.post(f"/session/{session_id}/respond",
                           json={"response": "wrong", "kind": "verification"}).json()

    respond.reteach.assert_not_called()
    respond.hint.assert_not_called()
    mutate.assert_not_called()
    assert body["adaptation"] == {"kind": "none"}
    assert body["classification"] is None


def test_a_verification_answer_does_not_re_grade_the_objective(client):
    node = _node("A", "partial")
    gap = Gap.create("wrong_model", CLAIM)
    node.gap_state.gaps.append(gap)
    session_id = _start(client, _graph(node))
    _verify(client, session_id)

    with patch("backend.api.grade_verification",
               side_effect=_grade_verification([gap.id])):
        client.post(f"/session/{session_id}/respond",
                    json={"response": "answer", "kind": "verification"})

    stored = _stored(session_id).nodes[node.id]
    # The stored assessment is untouched; only the gap moved.
    assert stored.understanding_state == "partial"


def test_verification_without_a_pending_question_is_refused(client):
    node = _node("A")
    node.gap_state.gaps.append(Gap.create("wrong_model", CLAIM))
    session_id = _start(client, _graph(node))
    got = client.post(f"/session/{session_id}/respond",
                      json={"response": "answer", "kind": "verification"})
    assert got.status_code == 409
    assert got.json()["detail"] == "no_pending_verification"


def test_a_verification_grading_failure_costs_the_learner_nothing(client):
    node = _node("A")
    gap = Gap.create("wrong_model", CLAIM)
    node.gap_state.gaps.append(gap)
    session_id = _start(client, _graph(node))
    _verify(client, session_id)

    def _failed(state, node, answer, client=None):
        return {"resolved": [], "unresolved": [gap.id], "new_gaps": 0,
                "rationale": "", "failed": True}

    with patch("backend.api.grade_verification", side_effect=_failed):
        got = client.post(f"/session/{session_id}/respond",
                          json={"response": "answer", "kind": "verification"})

    assert got.status_code == 503
    stored = _stored(session_id).nodes[node.id]
    assert stored.gaps[0].status == "open"
    assert stored.gaps[0].verification_attempts == 0
    # The question survives, so they can answer again.
    assert stored.gap_state.pending_verification is not None


# ── /waive ───────────────────────────────────────────────────────────────────


def test_waive_a_single_gap_by_id(client):
    node = _node("A")
    a, b = Gap.create("wrong_model", "A"), Gap.create("wrong_model", "B")
    node.gap_state.gaps.extend([a, b])
    session_id = _start(client, _graph(node))

    body = client.post(f"/session/{session_id}/waive",
                       json={"gap_id": a.id}).json()

    assert body["waived"] == [a.id]
    assert {g["id"]: g["status"] for g in body["gaps"]} == {a.id: "waived", b.id: "open"}
    stored = _stored(session_id).nodes[node.id]
    assert {g.id: g.status for g in stored.gaps} == {a.id: "waived", b.id: "open"}


def test_waive_the_node_waives_every_open_blocking_gap_and_names_them(client):
    node = _node("A")
    a, b = Gap.create("wrong_model", "A"), Gap.create("missing_prerequisite", "B")
    node.gap_state.gaps.extend([a, b])
    session_id = _start(client, _graph(node))

    body = client.post(f"/session/{session_id}/waive", json={}).json()

    assert set(body["waived"]) == {a.id, b.id}
    # Waiving stops the asking; it does not erase what was asked about. The rows
    # stay so the learner can still choose to clear one.
    assert {g["status"] for g in body["gaps"]} == {"waived"}
    assert _stored(session_id).nodes[node.id].user_override == "waive_remaining"


def test_waiving_never_produces_understood(client):
    """Waiving is a decision, not evidence (§18.16.2)."""
    node = _node("A", "understood")
    node.gap_state.gaps.append(Gap.create("wrong_model", CLAIM))
    session_id = _start(client, _graph(node))
    body = client.post(f"/session/{session_id}/waive", json={}).json()
    assert body["understanding_state"] != "understood"
    assert body["readiness"] < 1.0


def test_waiving_makes_the_journey_completable(client):
    """The §18.16.3 target state, over HTTP: complete, but not 100% verified."""
    node = _node("A", "understood")
    node.gap_state.gaps.append(Gap.create("wrong_model", CLAIM))
    session_id = _start(client, _graph(node))
    body = client.post(f"/session/{session_id}/waive", json={}).json()
    assert body["complete"] is True
    assert body["readiness"] < 1.0


def test_waiving_an_unknown_gap_is_a_404_not_a_silent_success(client):
    """So a stale UI cannot report a waiver that did not happen."""
    node = _node("A")
    node.gap_state.gaps.append(Gap.create("wrong_model", CLAIM))
    session_id = _start(client, _graph(node))
    got = client.post(f"/session/{session_id}/waive", json={"gap_id": "nope"})
    assert got.status_code == 404
    assert got.json()["detail"] == "gap_not_open"


def test_waive_leaves_a_non_blocking_gap_alone(client):
    node = _node("A")
    blocking = Gap.create("wrong_model", CLAIM)
    altitude = Gap.create("right_idea_wrong_altitude", "too low")
    node.gap_state.gaps.extend([blocking, altitude])
    session_id = _start(client, _graph(node))

    body = client.post(f"/session/{session_id}/waive", json={}).json()

    assert body["waived"] == [blocking.id]
    assert {g["id"]: g["status"] for g in body["gaps"]} == {
        blocking.id: "waived", altitude.id: "open",
    }


def test_a_waived_gap_can_be_verified_later(client):
    """"An offer to verify it now" on the completion screen rests on this: the
    gap is still on the node, so re-opening it is possible."""
    node = _node("A")
    gap = Gap.create("wrong_model", CLAIM)
    node.gap_state.gaps.append(gap)
    session_id = _start(client, _graph(node))
    client.post(f"/session/{session_id}/waive", json={})

    stored = _stored(session_id).nodes[node.id]
    assert stored.gaps[0].status == "waived"
    assert stored.gaps[0].claim == CLAIM      # still nameable, still recoverable


# ── the M2 envelope carries the gap slots (§18.9) ────────────────────────────


def test_an_assessment_records_the_gaps_it_opened(client):
    """Into M2's EXISTING envelope, via the `**detail` channel it provides —
    not a second verification-history shape beside it."""
    node = _node("A")
    session_id = _start(client, _graph(node, _node("B")))

    def _grader_opens(state, user_response, client=None):
        target = state.graph.nodes[state.graph.current_node_id]
        target.gap_state.gaps.append(Gap.create("wrong_model", CLAIM))
        state.last_grade = {"classification": "confused",
                            "gap_kind": "wrong_model", "rationale": "r"}
        return state

    with patch("backend.api.run_grader", side_effect=_grader_opens), \
         patch("backend.api._node_source", return_value="source"), \
         patch("backend.api.teaching_respond") as respond, \
         patch("backend.api.mutate_graph"):
        respond.reteach.return_value = MagicMock()
        client.post(f"/session/{session_id}/respond", json={"response": "wrong"})

    stored = _stored(session_id).nodes[node.id]
    envelope = stored.attempts[-1][history.RESPONSE]
    gap_id = stored.gaps[0].id
    assert envelope["gaps_opened"] == [gap_id]
    assert envelope["gaps_addressed"] == [gap_id]


def test_an_answer_that_opens_nothing_records_no_gap_keys(client):
    """Absent means "none", like every other detail key — not "unknown"."""
    node = _node("A", "understood")
    session_id = _start(client, _graph(node, _node("B")))
    _respond(client, session_id, "understood", "none")
    envelope = _stored(session_id).nodes[node.id].attempts[-1].get(history.RESPONSE)
    assert "gaps_opened" not in (envelope or {})


def test_a_verification_records_what_it_resolved(client):
    node = _node("A")
    gap = Gap.create("wrong_model", CLAIM)
    node.gap_state.gaps.append(gap)
    session_id = _start(client, _graph(node))
    _verify(client, session_id)

    with patch("backend.api.grade_verification",
               side_effect=_grade_verification([gap.id])):
        client.post(f"/session/{session_id}/respond",
                    json={"response": "answer", "kind": "verification"})

    attempts = _stored(session_id).nodes[node.id].attempts
    envelope = attempts[-1][history.RESPONSE]
    assert attempts[-1]["kind"] == history.VERIFICATION
    assert envelope["gaps_resolved"] == [gap.id]
    assert envelope["action"] == "none"     # verification produces no adaptation


def test_the_verification_envelope_does_not_land_on_the_assessment(client):
    """`record_response` files against the latest assessment, so verification
    writes its own record directly — the two questions stay apart."""
    node = _node("A")
    gap = Gap.create("wrong_model", CLAIM)
    node.gap_state.gaps.append(gap)
    session_id = _start(client, _graph(node))
    graph = _stored(session_id)
    graph.record_attempt(node.id, "first", "confused", "r")
    learning_store.save_graph(graph, api.SESSIONS_DB_PATH, user_id=TEST_USER_ID)
    _verify(client, session_id)

    with patch("backend.api.grade_verification",
               side_effect=_grade_verification([gap.id])):
        client.post(f"/session/{session_id}/respond",
                    json={"response": "answer", "kind": "verification"})

    attempts = _stored(session_id).nodes[node.id].attempts
    assessment = history.assessments(attempts)[-1]
    assert history.RESPONSE not in assessment
    assert attempts[-1][history.RESPONSE]["gaps_resolved"] == [gap.id]


# ── the drawer can now explain "understood, but not demonstrated" ────────────


def test_evidence_explains_an_understood_answer_that_is_still_unresolved(client):
    """M3a.1's open question, closed by M9.

    `node_summary` said it plainly: gap-model M7 can hold a node at `partial`
    though its latest answer reached the objective, and "without gap content on
    the wire (M9) the UI cannot say *why*". This is that content.
    """
    from backend.learning import understanding

    node = _node("A")
    gap = Gap.create("wrong_model", CLAIM, objective_part="what the handler owns")
    node.gap_state.gaps.append(gap)
    graph = _graph(node)
    graph.mark_understanding(node.id, "understood")
    graph.record_attempt(node.id, "a good answer", "understood", "reached it")

    got = understanding.evidence(graph, node.id)

    # The honest discrepancy M3a.1 could report...
    assert got["understanding"] == "unresolved"
    assert got["state_matches_latest_answer"] is False
    # ...and the reason it could not, until now.
    assert got["gaps_blocking"] == 1
    assert [g["claim"] for g in got["gaps"]] == [CLAIM]
    assert got["gaps"][0]["status"] == "open"


def test_evidence_reports_a_pending_verification(client):
    """The precise case: the answer landed, the check has been issued, and the
    node is waiting on it rather than on the learner."""
    from backend.agents.teaching.verify import VerificationPrompt
    from backend.agents.teaching import verify as tv
    from backend.learning import understanding

    node = _node("A")
    node.gap_state.gaps.append(Gap.create("wrong_model", CLAIM))
    graph = _graph(node)
    graph.mark_understanding(node.id, "understood")
    graph.record_attempt(node.id, "a good answer", "understood", "reached it")
    tv.store(node, VerificationPrompt(question="q?", targets=[node.gaps[0].id]))

    got = understanding.evidence(graph, node.id)
    assert got["verification_pending"] is True
    assert got["understanding"] == "unresolved"


def test_evidence_shows_a_waived_gap_as_part_of_the_explanation(client):
    """"This was waived" explains a state as much as "this is still open"."""
    from backend.learning import understanding

    node = _node("A")
    node.gap_state.gaps.append(Gap.create("wrong_model", CLAIM))
    graph = _graph(node)
    graph.mark_understanding(node.id, "understood")
    graph.record_attempt(node.id, "a good answer", "understood", "reached it")
    graph.waive_remaining(node.id)

    got = understanding.evidence(graph, node.id)
    assert got["gaps_waived"] == 1
    assert got["gaps_open"] == 0
    assert got["gaps"][0]["status"] == "waived"
    assert got["disposition"] == "waived"
    # Waiving is a decision, not evidence: still not demonstrated.
    assert got["understanding"] == "unresolved"


def test_evidence_links_a_gap_to_the_attempts_that_opened_and_closed_it(client):
    from backend.learning import understanding

    node = _node("A")
    gap = Gap.create("wrong_model", CLAIM, origin_attempt=0)
    node.gap_state.gaps.append(gap)
    graph = _graph(node)
    graph.record_attempt(node.id, "wrong", "confused", "r")
    graph.record_attempt(node.id, "verified", "", "r", kind=history.VERIFICATION)
    gap.mark_verified(1)

    got = understanding.evidence(graph, node.id)
    assert got["gaps"][0]["origin_attempt"] == 0
    assert got["gaps"][0]["resolved_by"] == 1
    assert got["timeline"][1]["kind"] == history.VERIFICATION


# ── /verify: the learner naming a gap ────────────────────────────────────────
#
# Precedence is the SYSTEM's rule for choosing when nobody said. Once the gap
# list is a set of buttons, the learner says — and these are the four ways that
# can go.


def test_verify_targets_the_gap_the_learner_named(client):
    """Without this the learner reads three named misconceptions and can only be
    asked about whichever one the arbitration order happens to lead with."""
    node = _node("A")
    altitude = Gap.create("right_idea_wrong_altitude", "too low")
    foundation = Gap.create("missing_prerequisite", "no idea what a socket is")
    node.gap_state.gaps.extend([altitude, foundation])
    session_id = _start(client, _graph(node))

    # `foundation` outranks it, so precedence alone would never pick this one —
    # which is exactly what `test_verify_targets_the_highest_precedence_gap`
    # asserts about the unnamed call on this same shape.
    got = _verify(client, session_id, gap_id=altitude.id)
    assert got.json()["targets"] == [altitude.id]


def test_a_named_gap_is_reachable_past_the_cap(client):
    """`VERIFICATION_ATTEMPT_CAP` bounds the system's nagging, not the learner's
    appetite (gaps.py §18.16.1). Unnamed, this same gap is the 409 asserted in
    `test_verify_refuses_an_exhausted_gap`."""
    node = _node("A")
    gap = Gap.create("wrong_model", CLAIM)
    gap.verification_attempts = VERIFICATION_ATTEMPT_CAP
    node.gap_state.gaps.append(gap)
    session_id = _start(client, _graph(node))

    got = _verify(client, session_id, gap_id=gap.id)
    assert got.status_code == 200
    assert got.json()["targets"] == [gap.id]


def test_naming_a_settled_gap_is_a_404(client):
    """A verified gap has nothing left to demonstrate. Refused rather than
    re-asked, so a stale list cannot spend a call re-closing a closed gap."""
    node = _node("A")
    gap = Gap.create("wrong_model", CLAIM)
    gap.mark_verified(0)
    node.gap_state.gaps.append(gap)
    session_id = _start(client, _graph(node))

    got = _verify(client, session_id, gap_id=gap.id)
    assert got.status_code == 404
    assert got.json()["detail"] == "gap_not_found"


def test_naming_an_unknown_gap_is_a_404(client):
    """So a stale list cannot be answered with someone else's question."""
    node = _node("A")
    node.gap_state.gaps.append(Gap.create("wrong_model", CLAIM))
    session_id = _start(client, _graph(node))
    assert _verify(client, session_id, gap_id="nope").status_code == 404
