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
