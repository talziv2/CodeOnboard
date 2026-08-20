"""
The goal dialogue over HTTP — specifically its navigation.

Run with: uv run pytest tests/test_goal_api.py -v

`step_back`'s own behaviour is covered in tests/test_goal_agent.py; what is
tested here is the HTTP contract the interview UI depends on: the answer comes
back with the question so the field can be refilled, position moves with it, and
the two ways to ask for something impossible are refused distinctly.
"""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import backend.api as api

REPO_URL = "https://github.com/psf/requests"
ANS_FAMILIARITY = "Starting fresh — never looked at it"
ANS_GOAL_DEBUG = "Debug an issue I'm hitting"
ANS_CODE_DEPTH = (
    "I'll be working in here — the map, plus what I'd need to change things safely"
)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    # /goal/answer builds a client eagerly; no question in this file reaches
    # synthesis, so it is never called.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(api.anthropic, "Anthropic", lambda **kw: MagicMock())
    api.sessions.clear()


@pytest.fixture
def client():
    return TestClient(api.app)


def _start(client) -> str:
    resp = client.post("/goal/start", json={"repo_url": REPO_URL})
    assert resp.status_code == 200
    return resp.json()["session_id"]


def test_back_returns_the_question_and_refills_the_answer(client):
    session_id = _start(client)
    client.post("/goal/answer", json={"session_id": session_id, "answer": ANS_FAMILIARITY})

    resp = client.post("/goal/back", json={"session_id": session_id})

    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == ANS_FAMILIARITY
    assert body["question"]["index"] == 1
    assert ANS_FAMILIARITY in body["question"]["options"]


def test_back_from_the_first_question_is_refused_distinctly(client):
    # Not a 404: the session is fine, the request isn't. The client disables its
    # own Back control here, so this is the race rather than the normal path.
    session_id = _start(client)

    resp = client.post("/goal/back", json={"session_id": session_id})

    assert resp.status_code == 400
    assert resp.json()["detail"] == "at_first_question"


def test_back_on_an_unknown_session_is_a_404(client):
    resp = client.post("/goal/back", json={"session_id": "no-such-session"})

    assert resp.status_code == 404
    assert resp.json()["detail"] == "session_not_found"


def test_answering_again_after_going_back_continues_from_there(client):
    session_id = _start(client)
    client.post("/goal/answer", json={"session_id": session_id, "answer": ANS_FAMILIARITY})
    client.post("/goal/answer", json={"session_id": session_id, "answer": ANS_GOAL_DEBUG})

    client.post("/goal/back", json={"session_id": session_id})
    resp = client.post(
        "/goal/answer", json={"session_id": session_id, "answer": ANS_GOAL_DEBUG}
    )

    body = resp.json()
    assert body["done"] is False
    # Q3, not Q4: the re-answer replaced the old one instead of adding to it.
    assert body["question"]["index"] == 3


# ── the completed dialogue survives, so the review step can still go back ─────


def _finish_debug_interview(client, monkeypatch) -> tuple[str, str]:
    """Answer every question for `debug_issue`, returning (session_id, last answer).

    Synthesis is stubbed: what is under test is the session's lifetime, not the
    goal the model writes.
    """
    from backend.agents.goal import agent as goal_agent

    monkeypatch.setattr(
        goal_agent,
        "_synthesize_goal",
        lambda repo_url, qa_pairs, client, code_depth: goal_agent.GoalOutput(
            primary_goal="find why the timeout never raises",
            goal_type="debug_issue",
            focus_area="the adapter layer",
            code_depth=code_depth,
            depth="moderate",
            target_repo=repo_url,
            familiarity=ANS_FAMILIARITY,
            background="python",
        ),
    )

    session_id = _start(client)
    # 5 core + 2 follow-ups for debug_issue. Only Q2 and Q4 are vocabulary-checked.
    answers = [
        ANS_FAMILIARITY,
        ANS_GOAL_DEBUG,
        "find why the timeout never raises",
        ANS_CODE_DEPTH,
        "python",
        "a timeout that never raises",
        "raising the timeout value",
    ]
    body = {}
    for answer in answers:
        resp = client.post(
            "/goal/answer", json={"session_id": session_id, "answer": answer}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
    assert body["done"] is True, body
    return session_id, answers[-1]


def test_a_finished_dialogue_is_kept_so_its_answers_stay_correctable(
    client, monkeypatch
):
    # The client shows the answers back and waits for confirmation before starting
    # anything. Dropping the session on completion made every Back on that review
    # step a 404, which is the bug this guards.
    session_id, last_answer = _finish_debug_interview(client, monkeypatch)

    resp = client.post("/goal/back", json={"session_id": session_id})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["answer"] == last_answer
    # The last question, handed back unanswered, ready to be re-confirmed.
    assert body["question"]["index"] == 7


def test_reopening_from_a_finished_dialogue_can_walk_all_the_way_back(
    client, monkeypatch
):
    # `Change` on the first row of the review unwinds one question per call.
    session_id, _ = _finish_debug_interview(client, monkeypatch)

    indexes = []
    for _ in range(7):
        resp = client.post("/goal/back", json={"session_id": session_id})
        assert resp.status_code == 200, resp.text
        indexes.append(resp.json()["question"]["index"])

    assert indexes == [7, 6, 5, 4, 3, 2, 1]
    # Nothing left to un-answer.
    resp = client.post("/goal/back", json={"session_id": session_id})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "at_first_question"


def test_goal_sessions_do_not_accumulate_without_bound(client):
    # Retention replaced delete-on-completion, so it has to be bounded: there is no
    # signal for "the learner closed the tab".
    for _ in range(api._MAX_GOAL_SESSIONS + 10):
        _start(client)

    assert len(api.sessions) == api._MAX_GOAL_SESSIONS


def test_the_oldest_dialogue_is_the_one_evicted(client):
    first = _start(client)
    for _ in range(api._MAX_GOAL_SESSIONS):
        _start(client)

    assert first not in api.sessions
    resp = client.post("/goal/back", json={"session_id": first})
    assert resp.status_code == 404
