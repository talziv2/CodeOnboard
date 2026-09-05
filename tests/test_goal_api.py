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

from tests.conftest import TEST_USER_ID
from fastapi.testclient import TestClient

import backend.api as api

REPO_URL = "https://github.com/psf/requests"
ANS_FAMILIARITY = "Starting fresh — never looked at it"
ANS_GOAL_DEBUG = "Debug an issue I'm hitting"
ANS_CODE_DEPTH = (
    "I'll be working in here — the map, plus what I'd need to change things safely"
)


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    # /goal/answer builds a client eagerly; no question in this file reaches
    # synthesis, so it is never called.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(api.anthropic, "Anthropic", lambda **kw: MagicMock())
    # Interviews live in a table now (M7), scoped to a temp database rather than
    # cleared out of a process dict. The dict is gone precisely because clearing
    # shared state between tests was the smaller half of what was wrong with it.
    monkeypatch.setattr(api, "SESSIONS_DB_PATH", tmp_path / "sessions.db")


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
        lambda repo_url, qa_pairs, client, code_depth, contribution_scope=None:
        goal_agent.GoalOutput(
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


def test_an_interview_survives_a_restart(client):
    """WHAT THE DICT COULD NOT DO.

    Interviews used to live in a module-level dict, so a backend restart lost
    every one in flight — five questions of somebody's work, gone, with nothing
    to say so. A fresh app object over the same database is the closest thing
    in-process to a restart: no memory survives it, and the interview does.
    """
    import importlib

    draft_id = _start(client)
    client.post("/goal/answer", json={"session_id": draft_id, "answer": "a"})

    # CAPTURED FIRST. `importlib.reload` mutates the module object IN PLACE, so
    # `api` and `restarted` are the same object and the attribute has already
    # been reset to its default by the time the reload returns — reading it
    # afterwards copies the default onto itself, and the "restarted" app then
    # looks at the wrong database entirely.
    db_path = api.SESSIONS_DB_PATH

    restarted = importlib.reload(api)
    restarted.SESSIONS_DB_PATH = db_path
    # A reloaded module is a NEW app object with an empty override table, so the
    # stand-in caller has to be applied again. That is the reload behaving
    # correctly — it is the point of the test.
    from backend.auth import deps

    caller = deps.CurrentUser(
        user_id=TEST_USER_ID, email="test-user@codeonboard.local", display_name=None
    )
    restarted.app.dependency_overrides[deps.current_user] = lambda: caller
    restarted.app.dependency_overrides[deps.optional_user] = lambda: caller
    try:
        fresh = TestClient(restarted.app)
        response = fresh.post("/goal/back", json={"session_id": draft_id})
        assert response.status_code == 200, response.text
        assert response.json()["answer"] == "a"
    finally:
        importlib.reload(api)


def test_interviews_are_owner_scoped(client):
    """The dict was shared by everybody, so an id was all you needed.

    404 for "not yours" as well as "not there" — a draft id must not be usable
    to discover that somebody else is mid-interview.
    """
    from backend.auth import drafts

    draft_id = _start(client)

    assert drafts.load(draft_id, "somebody-else", api.SESSIONS_DB_PATH) is None
    assert drafts.load(draft_id, TEST_USER_ID, api.SESSIONS_DB_PATH) is not None


def test_interviews_do_not_accumulate_without_bound(client):
    """Retention is still bounded, but by AGE rather than by a shared cap.

    The dict evicted the oldest past 64 — globally, so ten concurrent learners
    threw away each other's work. A month of inactivity is a far better signal
    than "somebody else started one", and it is per-draft rather than per-process.
    """
    import sqlite3

    from backend.auth import drafts

    draft_id = _start(client)
    assert drafts.purge_older_than(days=30, db_path=api.SESSIONS_DB_PATH) == 0

    with sqlite3.connect(api.SESSIONS_DB_PATH) as conn:
        conn.execute("UPDATE session_drafts SET updated_at = '2000-01-01T00:00:00'")

    assert drafts.purge_older_than(days=30, db_path=api.SESSIONS_DB_PATH) == 1
    assert drafts.load(draft_id, TEST_USER_ID, api.SESSIONS_DB_PATH) is None


def test_one_learner_cannot_evict_anothers_interview(client):
    """The dict's cap was GLOBAL, which is the half that made it unsafe."""
    from backend.auth import drafts, identity

    mine = _start(client)
    identity.ensure_user_row("other-user", "other@example.com", api.SESSIONS_DB_PATH)
    for _ in range(70):
        drafts.create("other-user", REPO_URL, api.SESSIONS_DB_PATH)

    assert drafts.load(mine, TEST_USER_ID, api.SESSIONS_DB_PATH) is not None
