"""The Tutor over HTTP: the five routes, the caps, and the ladder end to end.

Run with: uv run pytest tests/test_tutor_api.py -v

The model is stubbed throughout — what is under test is the wiring, the state
machine and the refusals, none of which should depend on what a model says. The
model's own behaviour is `scripts/tutor_eval.py`'s subject.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import backend.api as api
from backend.learning import retry as retry_model
from backend.learning import store as learning_store
from backend.learning.gaps import Gap
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.learning.tutor import HINT_LADDER_MAX, TUTOR_QUESTION_CAP, new_turn
from tests.conftest import TEST_USER_ID, start_session
from tests.test_session_api import FAKE_GOAL, FAKE_REPO_URL, _teaching_side_effect


PROMPT = "What does Session.send return, and why?"
REVEAL = "It returns a Response, because the adapter has already read the body."


@pytest.fixture(autouse=True)
def _env_and_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("CODEONBOARD_TUTOR", "1")
    monkeypatch.setattr(api, "SESSIONS_DB_PATH", tmp_path / "sessions.db")
    monkeypatch.setattr(api.anthropic, "Anthropic", lambda **kw: MagicMock())


@pytest.fixture
def client():
    return TestClient(api.app)


def _node(title="The Session object", taught=True) -> LearningNode:
    node = LearningNode(
        title=title,
        code_anchor=CodeAnchor(file="requests/sessions.py", line_start=1, line_end=20,
                               symbol="Session"),
        lesson_brief={"objective": f"Explain {title}", "priority": "required"},
    )
    if taught:
        node.cached_lesson = {"prompt": PROMPT, "reveal": REVEAL,
                              "expected_answer": "A Response.", "setup": "…"}
    return node


def _graph(*nodes) -> LearningGraph:
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
        return start_session(client, FAKE_REPO_URL, FAKE_GOAL)["session_id"]


def _stored(session_id) -> LearningGraph:
    return learning_store.load_graph(session_id, TEST_USER_ID, api.SESSIONS_DB_PATH)


def _save(graph):
    learning_store.save_graph(graph, api.SESSIONS_DB_PATH, user_id=TEST_USER_ID)


def _answer(text="An answer.", scope="answered", citations=None,
            suggestion=None, grounded=True):
    return {
        "text": text, "citations": citations or [], "scope": scope,
        "suggestion": suggestion, "grounded": grounded, "usage": {"input_tokens": 10},
    }


def _no_repo():
    """Every Tutor call reads a checkout; none of these tests wants one."""
    return patch("backend.api._tutor_repo_inputs",
                 return_value=api.tutor_context.RepoInputs(
                     source="class Session: ...",
                     citable=(api.tutor_context.Citable(
                         "requests/sessions.py", "Session", 1, 20),),
                 ))


# ── the flag ──────────────────────────────────────────────────────────────────


def test_every_route_is_absent_while_the_flag_is_off(client, monkeypatch):
    monkeypatch.setenv("CODEONBOARD_TUTOR", "0")
    session_id = _start(client, _graph(_node()))
    assert client.get(f"/session/{session_id}/tutor").status_code == 404
    assert client.post(f"/session/{session_id}/tutor/ask", json={"question": "q"}).status_code == 404
    assert client.post(f"/session/{session_id}/tutor/hint", json={}).status_code == 404
    assert client.post(f"/session/{session_id}/tutor/reveal", json={}).status_code == 404
    assert client.post(f"/session/{session_id}/tutor/pin", json={"turn_id": "x"}).status_code == 404


def test_a_flag_off_session_keeps_its_conversation(client, monkeypatch):
    """The flag gates behaviour, never storage."""
    session_id = _start(client, _graph(_node()))
    graph = _stored(session_id)
    graph.tutor.append(new_turn(node_id=graph.current_node_id, mode="explain",
                                question="q", answer="a", scope="answered"))
    _save(graph)

    monkeypatch.setenv("CODEONBOARD_TUTOR", "0")
    assert len(_stored(session_id).tutor) == 1
    monkeypatch.setenv("CODEONBOARD_TUTOR", "1")
    assert len(client.get(f"/session/{session_id}/tutor").json()["turns"]) == 1


# ── mode dispatch over the wire ───────────────────────────────────────────────


def test_a_live_prompt_puts_the_tutor_in_scaffold_mode(client):
    session_id = _start(client, _graph(_node()))
    body = client.get(f"/session/{session_id}/tutor").json()
    assert body["mode"]["mode"] == "scaffold"
    assert body["mode"]["question"] == PROMPT
    assert body["mode"]["can_hint"] is True
    assert body["mode"]["can_reveal"] is True
    assert body["mode"]["hints_left"] == HINT_LADDER_MAX
    assert body["remaining"] == TUTOR_QUESTION_CAP


def test_an_answered_stop_puts_the_tutor_in_explain_mode(client):
    graph = _graph(_node())
    session_id = _start(client, graph)
    stored = _stored(session_id)
    stored.record_attempt(stored.current_node_id, "an answer", "understood", "r")
    _save(stored)

    body = client.get(f"/session/{session_id}/tutor").json()
    assert body["mode"]["mode"] == "explain"
    assert body["mode"]["can_hint"] is False


def test_the_mode_is_recomputed_and_never_taken_from_the_caller(client):
    """A client that could name its own mode could ask for the answer key."""
    session_id = _start(client, _graph(_node()))
    with _no_repo(), patch("backend.api.tutor_scaffold.reply",
                           return_value=_answer("a scaffold")) as scaffold, \
         patch("backend.api.tutor_explain.answer") as explain:
        client.post(f"/session/{session_id}/tutor/ask",
                    json={"question": "what is the answer", "mode": "explain"})
    assert scaffold.called
    assert not explain.called


# ── /ask ──────────────────────────────────────────────────────────────────────


def test_ask_stores_a_turn_anchored_to_the_stop(client):
    graph = _graph(_node())
    session_id = _start(client, graph)
    node_id = _stored(session_id).current_node_id

    with _no_repo(), patch("backend.api.tutor_scaffold.reply",
                           return_value=_answer("look at the return")):
        body = client.post(f"/session/{session_id}/tutor/ask",
                           json={"question": "where do I look?"}).json()

    turn = body["turn"]
    assert turn["node_id"] == node_id
    assert turn["mode"] == "scaffold"
    assert turn["question"] == "where do I look?"
    assert turn["answer"] == "look at the return"
    assert turn["pinned"] is False
    assert body["remaining"] == TUTOR_QUESTION_CAP - 1
    assert len(_stored(session_id).tutor) == 1


def test_ask_in_explain_mode_uses_the_explain_agent(client):
    graph = _graph(_node())
    session_id = _start(client, graph)
    stored = _stored(session_id)
    stored.record_attempt(stored.current_node_id, "a", "understood", "r")
    _save(stored)

    with _no_repo(), patch("backend.api.tutor_explain.answer",
                           return_value=_answer("a full explanation")) as explain:
        body = client.post(f"/session/{session_id}/tutor/ask",
                           json={"question": "why?"}).json()
    assert explain.called
    assert body["turn"]["mode"] == "explain"


def test_an_empty_or_overlong_question_is_refused(client):
    session_id = _start(client, _graph(_node()))
    assert client.post(f"/session/{session_id}/tutor/ask",
                       json={"question": "   "}).json()["detail"] == "question_empty"
    long = client.post(f"/session/{session_id}/tutor/ask",
                       json={"question": "x" * 501})
    assert long.status_code == 400
    assert long.json()["detail"] == "question_too_long"


def test_a_failed_call_costs_the_learner_nothing(client):
    """Our outage must not spend their allowance."""
    session_id = _start(client, _graph(_node()))
    with _no_repo(), patch("backend.api.tutor_scaffold.reply") as reply:
        def _fail(question, ctx, client=None, errors=None):
            errors.append("boom")
            return _answer("sorry", grounded=False)
        reply.side_effect = _fail
        body = client.post(f"/session/{session_id}/tutor/ask",
                           json={"question": "q"}).json()

    assert body["failed"] is True
    assert body["turn"] is None
    assert body["remaining"] == TUTOR_QUESTION_CAP
    assert _stored(session_id).tutor == []


def test_the_cap_is_a_hard_stop_the_learner_can_see(client):
    graph = _graph(_node())
    session_id = _start(client, graph)
    stored = _stored(session_id)
    for i in range(TUTOR_QUESTION_CAP):
        stored.tutor.append(new_turn(node_id=stored.current_node_id, mode="explain",
                                     question=f"q{i}", answer="a", scope="answered"))
    _save(stored)

    assert client.get(f"/session/{session_id}/tutor").json()["remaining"] == 0
    refused = client.post(f"/session/{session_id}/tutor/ask", json={"question": "one more"})
    assert refused.status_code == 409
    assert refused.json()["detail"] == "tutor_limit_reached"


# ── the ladder ────────────────────────────────────────────────────────────────


def test_the_ladder_climbs_three_rungs_then_stops(client):
    session_id = _start(client, _graph(_node()))
    rungs = []
    with _no_repo(), patch("backend.api.tutor_scaffold.hint") as hint:
        hint.side_effect = lambda ctx, rung, client=None, errors=None: _answer(f"hint {rung}")
        for expected in (1, 2, 3):
            body = client.post(f"/session/{session_id}/tutor/hint", json={}).json()
            rungs.append(body["turn"]["hint_level"])
            assert body["mode"]["hints_left"] == HINT_LADDER_MAX - expected
        spent = client.post(f"/session/{session_id}/tutor/hint", json={})

    assert rungs == [1, 2, 3]
    assert spent.status_code == 409
    assert spent.json()["detail"] == "hint_ladder_spent"


def test_a_hint_is_refused_when_nothing_is_being_asked(client):
    graph = _graph(_node())
    session_id = _start(client, graph)
    stored = _stored(session_id)
    stored.record_attempt(stored.current_node_id, "a", "understood", "r")
    _save(stored)

    refused = client.post(f"/session/{session_id}/tutor/hint", json={})
    assert refused.status_code == 409
    assert refused.json()["detail"] == "not_asking"


def test_a_failed_hint_does_not_spend_a_rung(client):
    session_id = _start(client, _graph(_node()))
    with _no_repo(), patch("backend.api.tutor_scaffold.hint") as hint:
        def _fail(ctx, rung, client=None, errors=None):
            errors.append("boom")
            return _answer("sorry", grounded=False)
        hint.side_effect = _fail
        body = client.post(f"/session/{session_id}/tutor/hint", json={}).json()

    assert body["failed"] is True
    assert body["mode"]["hints_left"] == HINT_LADDER_MAX
    assert _stored(session_id).nodes[_stored(session_id).current_node_id].tutor_state.hints_used == 0


def test_an_off_ladder_question_spends_no_rung(client):
    """Asking is never blocked; only being handed the answer is bounded."""
    session_id = _start(client, _graph(_node()))
    with _no_repo(), patch("backend.api.tutor_scaffold.reply",
                           return_value=_answer("Response.raw is the socket stream")):
        for _ in range(3):
            client.post(f"/session/{session_id}/tutor/ask",
                        json={"question": "what is Response.raw?"})
    body = client.get(f"/session/{session_id}/tutor").json()
    assert body["mode"]["hints_left"] == HINT_LADDER_MAX
    assert body["mode"]["can_hint"] is True


# ── /reveal ───────────────────────────────────────────────────────────────────


def test_reveal_returns_the_explanation_and_spends_the_prompt(client):
    session_id = _start(client, _graph(_node()))
    body = client.post(f"/session/{session_id}/tutor/reveal", json={}).json()

    assert body["reveal"] == REVEAL
    assert body["mode"]["mode"] == "explain", "the question is over"
    assert body["mode"]["can_reveal"] is False
    # THE CONSEQUENCE, through the existing machinery.
    assert body["retry"]["mechanism"] == retry_model.REASSESS
    assert body["retry"]["available"] is True
    assert _stored(session_id).nodes[_stored(session_id).current_node_id].tutor_state.revealed


def test_a_revealed_prompt_can_no_longer_be_answered(client):
    """The back door the E2E pass found, closed at the server.

    The frontend remounts the lesson on a reveal so the composer goes read-only —
    but a client holding a stale lesson (a second tab, a pane revealed after the
    page loaded) would still post an answer to a question whose explanation is on
    screen beside it. Grading that is grading what they just read.
    """
    session_id = _start(client, _graph(_node()))
    client.post(f"/session/{session_id}/tutor/reveal", json={})

    with patch("backend.api.run_grader") as grader:
        refused = client.post(f"/session/{session_id}/respond",
                              json={"response": "the answer I just read"})
    assert refused.status_code == 409
    assert refused.json()["detail"] == "prompt_revealed"
    assert not grader.called, "a refused answer must never reach the Grader"
    assert _stored(session_id).nodes[_stored(session_id).current_node_id].attempts == []


def test_a_reassessment_answer_is_never_refused_by_the_reveal_guard(client):
    """Issuing a fresh question clears `revealed`, so the guard cannot catch it."""
    graph = _graph(_node())
    session_id = _start(client, graph)
    client.post(f"/session/{session_id}/tutor/reveal", json={})

    stored = _stored(session_id)
    node = stored.nodes[stored.current_node_id]
    node.tutor_state.new_question()          # what /reassess does
    node.gap_state.pending_reassessment = {"question": "a fresh one"}
    _save(stored)

    def _grader(state, user_response, client=None):
        state.last_grade = {"classification": "understood", "gap_kind": "none",
                            "rationale": "good"}
        return state

    with patch("backend.api.run_grader", side_effect=_grader),          patch("backend.api._node_source", return_value="source"):
        graded = client.post(f"/session/{session_id}/respond",
                             json={"response": "my fresh answer", "kind": "reassessment"})
    assert graded.status_code == 200
    assert graded.json()["classification"] == "understood"


def test_assistance_is_recorded_on_the_attempt_it_preceded(client):
    """§6.4 — metadata about evidence, never evidence."""
    graph = _graph(_node())
    session_id = _start(client, graph)
    stored = _stored(session_id)
    stored.nodes[stored.current_node_id].tutor_state.hints_used = 2
    _save(stored)

    def _grader(state, user_response, client=None):
        # The real Grader applies the verdict to the node as well as reporting it
        # (`_apply_grade`). A stub that only reports leaves the node at
        # `not_started`, and `retry.offer` then answers a different question than
        # the one under test.
        state.last_grade = {"classification": "understood", "gap_kind": "none",
                            "rationale": "good"}
        state.graph.nodes[state.graph.current_node_id].understanding_state = "understood"
        return state

    with patch("backend.api.run_grader", side_effect=_grader),          patch("backend.api._node_source", return_value="source"):
        body = client.post(f"/session/{session_id}/respond",
                           json={"response": "an answer"}).json()

    attempt = _stored(session_id).nodes[_stored(session_id).current_node_id].attempts[-1]
    assert attempt["assistance"] == {"hints": 2, "revealed": False}
    # The GRADE is untouched by assistance — the Grader marks the answer, not the
    # route to it.
    assert body["classification"] == "understood"
    # And the offer stays open, because two hints is heavy assistance.
    assert body["retry"]["mechanism"] == "reassess"
    assert body["retry"]["reason"] == "assisted"


def test_reveal_makes_no_model_call_and_costs_no_allowance(client):
    session_id = _start(client, _graph(_node()))
    with patch("backend.api.tutor_scaffold.hint") as hint, \
         patch("backend.api.tutor_explain.answer") as explain:
        body = client.post(f"/session/{session_id}/tutor/reveal", json={}).json()
    assert not hint.called and not explain.called
    assert body["remaining"] == TUTOR_QUESTION_CAP


def test_reveal_is_refused_twice_and_when_nothing_is_asked(client):
    session_id = _start(client, _graph(_node()))
    client.post(f"/session/{session_id}/tutor/reveal", json={})
    again = client.post(f"/session/{session_id}/tutor/reveal", json={})
    assert again.status_code == 409
    assert again.json()["detail"] == "already_revealed"


def test_reveal_is_refused_for_a_question_that_ships_no_answer(client):
    """A verification question has no reveal by design; showing the lesson's
    would answer a different question."""
    graph = _graph(_node())
    session_id = _start(client, graph)
    stored = _stored(session_id)
    node = stored.nodes[stored.current_node_id]
    stored.record_attempt(node.id, "a", "confused", "r")
    node.gap_state.pending_verification = {"question": "a fresh check"}
    _save(stored)

    refused = client.post(f"/session/{session_id}/tutor/reveal", json={})
    assert refused.status_code == 409
    assert refused.json()["detail"] == "no_explanation_for_this_question"


def test_after_revealing_a_gap_still_outranks_the_objective(client):
    graph = _graph(_node())
    session_id = _start(client, graph)
    stored = _stored(session_id)
    node = stored.nodes[stored.current_node_id]
    gap = Gap.create(kind="wrong_model", claim="wrong", objective_part="o")
    node.gap_state.gaps.append(gap)
    _save(stored)

    body = client.post(f"/session/{session_id}/tutor/reveal", json={}).json()
    assert body["retry"]["mechanism"] == retry_model.VERIFY
    assert body["retry"]["gap_id"] == gap.id


# ── /pin ──────────────────────────────────────────────────────────────────────


def test_pinning_flags_a_turn_and_never_touches_the_lesson(client):
    graph = _graph(_node())
    session_id = _start(client, graph)
    with _no_repo(), patch("backend.api.tutor_scaffold.reply",
                           return_value=_answer("a useful explanation")):
        turn = client.post(f"/session/{session_id}/tutor/ask",
                           json={"question": "q"}).json()["turn"]

    before = _stored(session_id).nodes[_stored(session_id).current_node_id].cached_lesson
    body = client.post(f"/session/{session_id}/tutor/pin",
                       json={"turn_id": turn["id"]}).json()
    after = _stored(session_id)

    assert body["turn"]["pinned"] is True
    assert after.tutor[0]["pinned"] is True
    assert after.nodes[after.current_node_id].cached_lesson == before


def test_unpinning_works_and_an_unknown_turn_is_404(client):
    graph = _graph(_node())
    session_id = _start(client, graph)
    stored = _stored(session_id)
    turn = new_turn(node_id=stored.current_node_id, mode="explain", question="q",
                    answer="a", scope="answered")
    stored.tutor.append(turn)
    _save(stored)

    client.post(f"/session/{session_id}/tutor/pin", json={"turn_id": turn["id"]})
    body = client.post(f"/session/{session_id}/tutor/pin",
                       json={"turn_id": turn["id"], "pinned": False}).json()
    assert body["turn"]["pinned"] is False
    assert client.post(f"/session/{session_id}/tutor/pin",
                       json={"turn_id": "nope"}).status_code == 404


# ── suggestions and offers ────────────────────────────────────────────────────


def test_a_model_suggestion_is_validated_before_it_reaches_the_learner(client):
    graph = _graph(_node("A"), _node("B"))
    session_id = _start(client, graph)
    stored = _stored(session_id)
    stored.record_attempt(stored.current_node_id, "a", "partial", "r")
    _save(stored)

    with _no_repo(), patch("backend.api.tutor_explain.answer",
                           return_value=_answer(
                               "that is stop 2",
                               suggestion={"kind": "jump", "node_id": "not-a-real-node"})):
        turn = client.post(f"/session/{session_id}/tutor/ask",
                           json={"question": "q"}).json()["turn"]
    assert "suggestion" not in turn, "an unresolvable target must be dropped"
    assert turn["answer"] == "that is stop 2", "the text survives"


def test_a_valid_suggestion_reaches_the_learner_as_a_control(client):
    nodes = (_node("A"), _node("B"))
    graph = _graph(*nodes)
    session_id = _start(client, graph)
    stored = _stored(session_id)
    stored.record_attempt(stored.current_node_id, "a", "partial", "r")
    target = [n for n in stored.nodes if n != stored.current_node_id][0]
    _save(stored)

    with _no_repo(), patch("backend.api.tutor_explain.answer",
                           return_value=_answer(
                               "that lives at the next stop",
                               suggestion={"kind": "jump", "node_id": target})):
        turn = client.post(f"/session/{session_id}/tutor/ask",
                           json={"question": "q"}).json()["turn"]
    assert turn["suggestion"] == {"kind": "jump", "label_key": "goToStop",
                                  "node_id": target, "gap_id": None}


def test_a_scaffold_never_proposes_an_exit(client):
    """Offering a way out to somebody mid-thought is telling them to give up."""
    session_id = _start(client, _graph(_node()))
    with _no_repo(), patch("backend.api.tutor_scaffold.reply",
                           return_value=_answer("look here", suggestion=None)):
        turn = client.post(f"/session/{session_id}/tutor/ask",
                           json={"question": "q"}).json()["turn"]
    assert "suggestion" not in turn
    assert client.get(f"/session/{session_id}/tutor").json()["offers"] == []


def test_dwelling_offers_a_fresh_question_but_only_in_explain_mode(client):
    graph = _graph(_node())
    session_id = _start(client, graph)
    stored = _stored(session_id)
    node = stored.nodes[stored.current_node_id]
    stored.record_attempt(node.id, "a", "partial", "r")
    node.tutor_state.turns = 4
    _save(stored)

    offers = client.get(f"/session/{session_id}/tutor").json()["offers"]
    assert [o["signal"] for o in offers] == ["dwelling"]
    assert offers[0]["kind"] == "reassess"


# ── ownership ─────────────────────────────────────────────────────────────────


def test_an_unknown_session_is_404_on_every_route(client):
    for method, path, body in (
        ("get", "/session/nope/tutor", None),
        ("post", "/session/nope/tutor/ask", {"question": "q"}),
        ("post", "/session/nope/tutor/hint", {}),
        ("post", "/session/nope/tutor/reveal", {}),
        ("post", "/session/nope/tutor/pin", {"turn_id": "x"}),
    ):
        response = getattr(client, method)(path, json=body) if body is not None \
            else getattr(client, method)(path)
        assert response.status_code == 404, path
        assert response.json()["detail"] in ("session_not_found", "not_found")


def test_an_unknown_node_is_404(client):
    session_id = _start(client, _graph(_node()))
    response = client.post(f"/session/{session_id}/tutor/ask",
                           json={"question": "q", "node_id": "nope"})
    assert response.status_code == 404
    assert response.json()["detail"] == "node_not_found"
