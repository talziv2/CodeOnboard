"""No user may touch another user's session (multi-user M3, invariant I2).

Run with: uv run pytest tests/test_ownership.py -v

**The load-bearing file of the whole multi-user layer.** Everything else can be
wrong in a way that costs a feature; this being wrong costs someone else's
learning history.

Real authentication throughout — `pytestmark = real_auth` opts out of conftest's
signed-in-by-default fixture, because a stubbed caller would make every
assertion here vacuous. Two accounts are registered through `/auth/register` and
each drives a real `TestClient` with its own cookie.

## What "isolation" has to mean

Not "user B gets an error". **User B must be unable to tell that user A's session
exists at all** (I6), and must not change it. So every case asserts two things:
the response is a 404 identical to a session id that was never real, and A's data
is byte-identical afterwards.
"""
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.api as api
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.learning.store import create_session, load_graph, save_graph

pytestmark = pytest.mark.real_auth

A_EMAIL, B_EMAIL = "alice@example.com", "mallory@example.com"
PASSWORD = "a-long-enough-passphrase"


@pytest.fixture(autouse=True)
def _isolation(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("CODEONBOARD_COOKIE_SECURE", "0")
    monkeypatch.setattr(api, "SESSIONS_DB_PATH", tmp_path / "sessions.db")
    monkeypatch.setattr(api, "clone_repo", lambda url: str(tmp_path / "repo"))
    from backend.auth import throttle

    throttle.reset_all()
    yield
    throttle.reset_all()


@pytest.fixture
def db() -> Path:
    return api.SESSIONS_DB_PATH


def _account(email: str) -> tuple[TestClient, str]:
    client = TestClient(api.app)
    response = client.post(
        "/auth/register", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 201, response.text
    return client, response.json()["user_id"]


@pytest.fixture
def alice():
    return _account(A_EMAIL)


@pytest.fixture
def mallory():
    return _account(B_EMAIL)


def _graph() -> LearningGraph:
    graph = LearningGraph(
        repo_url="https://github.com/psf/requests",
        goal={"primary_goal": "understand sessions", "focus_area": "the Session object"},
    )
    first = graph.add_node(LearningNode(
        title="Understand Session",
        code_anchor=CodeAnchor(file="requests/sessions.py", line_start=1, line_end=80),
        lesson_brief={"objective": "explain what Session owns"},
    ))
    second = graph.add_node(LearningNode(
        title="Trace send",
        code_anchor=CodeAnchor(file="requests/sessions.py", line_start=394, line_end=470),
    ))
    graph.add_edge(first.id, second.id, kind="sequence")
    graph.set_current(first.id)
    first.cached_lesson = {"setup": "s", "prompt": "p", "reveal": "r"}
    graph.record_attempt(first.id, "Alice's private answer.", "partial", "close")
    return graph


def _alices_session(db: Path, alice_id: str) -> LearningGraph:
    graph = _graph()
    create_session(graph, db, user_id=alice_id)
    return graph


def _snapshot(db: Path, session_id: str) -> tuple:
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
        session = conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchall()
        nodes = conn.execute(
            "SELECT * FROM nodes WHERE session_id = ? ORDER BY node_id", (session_id,)
        ).fetchall()
    return (session, nodes)


# ── every route, both properties ──────────────────────────────────────────────

READS = [
    ("GET", "/session/{sid}", None),
    ("GET", "/session/{sid}/lesson", None),
    ("GET", "/session/{sid}/welcome", None),
    ("GET", "/session/{sid}/file?path=README.md", None),
]

WRITES = [
    ("POST", "/session/{sid}/advance", {"signal": "next"}),
    ("POST", "/session/{sid}/respond", {"response": "mallory's answer"}),
    ("POST", "/session/{sid}/verify", {}),
    ("POST", "/session/{sid}/waive", {}),
    ("POST", "/session/{sid}/retry", {}),
    ("POST", "/session/{sid}/jump", {"node_id": "anything"}),
    ("POST", "/session/{sid}/scope", {"direction": "shorter"}),
    ("POST", "/session/{sid}/override", {"action": "mark_understood"}),
    ("POST", "/session/{sid}/reset", None),
]


@pytest.mark.parametrize("method,template,body", READS + WRITES,
                         ids=[t for _, t, _ in READS + WRITES])
def test_a_stranger_gets_404_and_changes_nothing(
    db, alice, mallory, method, template, body
):
    """404, not 403 — and Alice's data untouched.

    A 403 would say "this exists but is not yours", which is a working oracle
    for which session ids are real. The store's `WHERE user_id = ?` gives the
    right answer for free: a foreign session returns no row and is
    indistinguishable from one that never existed.
    """
    _, alice_id = alice
    mallory_client, _ = mallory
    graph = _alices_session(db, alice_id)
    before = _snapshot(db, graph.session_id)

    response = mallory_client.request(
        method, template.format(sid=graph.session_id), json=body
    )

    assert response.status_code == 404, (
        f"{method} {template} leaked: {response.status_code} {response.text[:120]}"
    )
    assert response.json()["detail"] == "session_not_found"
    assert _snapshot(db, graph.session_id) == before, "a stranger changed the data"


@pytest.mark.parametrize("method,template,body", READS + WRITES,
                         ids=[t for _, t, _ in READS + WRITES])
def test_a_real_id_and_a_made_up_one_are_indistinguishable(
    db, alice, mallory, method, template, body
):
    """The oracle test: the two refusals must be identical, byte for byte.

    If a real-but-foreign id answered differently from a nonexistent one — a
    different status, a different `detail`, even a different error shape — then
    an attacker could enumerate which sessions exist without ever reading one.
    """
    _, alice_id = alice
    mallory_client, _ = mallory
    graph = _alices_session(db, alice_id)

    real = mallory_client.request(
        method, template.format(sid=graph.session_id), json=body
    )
    invented = mallory_client.request(
        method, template.format(sid="0" * 32), json=body
    )

    assert real.status_code == invented.status_code
    assert real.json() == invented.json()


def test_the_evidence_route_does_not_leak_answers(db, alice, mallory):
    """`/evidence` returns verbatim learner answers — the most private payload."""
    _, alice_id = alice
    mallory_client, _ = mallory
    graph = _alices_session(db, alice_id)
    node_id = next(iter(graph.nodes))

    response = mallory_client.get(f"/session/{graph.session_id}/evidence/{node_id}")

    assert response.status_code == 404
    assert "Alice's private answer" not in response.text


def test_the_session_list_shows_only_your_own(db, alice, mallory):
    alice_client, alice_id = alice
    mallory_client, mallory_id = mallory
    mine = _alices_session(db, alice_id)
    theirs = _graph()
    create_session(theirs, db, user_id=mallory_id)

    alice_sees = {s["session_id"] for s in alice_client.get("/sessions").json()["sessions"]}
    mallory_sees = {s["session_id"] for s in mallory_client.get("/sessions").json()["sessions"]}

    assert alice_sees == {mine.session_id}
    assert mallory_sees == {theirs.session_id}
    assert not alice_sees & mallory_sees


def test_the_session_list_is_not_widened_by_the_repo_filter(db, alice, mallory):
    """`repo_url` is a FILTER now, not the key it used to be.

    It was a required parameter that returned every session on that repository
    belonging to anybody. Passing it must narrow the caller's own list, never
    reach outside it.
    """
    alice_client, alice_id = alice
    _, mallory_id = mallory
    _alices_session(db, alice_id)
    theirs = _graph()
    create_session(theirs, db, user_id=mallory_id)

    listed = alice_client.get(
        "/sessions?repo_url=https://github.com/psf/requests"
    ).json()["sessions"]

    assert theirs.session_id not in {s["session_id"] for s in listed}


# ── the store boundary itself ─────────────────────────────────────────────────

def test_the_store_refuses_a_foreign_read(db, alice, mallory):
    """Below the routes: `load_graph` is where this is actually decided.

    A route could be added tomorrow that forgets the dependency. It still could
    not read a foreign session, because there is no way to ask for one.
    """
    _, alice_id = alice
    _, mallory_id = mallory
    graph = _alices_session(db, alice_id)

    assert load_graph(graph.session_id, alice_id, db) is not None
    assert load_graph(graph.session_id, mallory_id, db) is None


def test_the_store_will_not_write_without_an_owner(db):
    graph = _graph()

    with pytest.raises(TypeError):
        save_graph(graph, db)


def test_a_save_never_reassigns_an_owner(db, alice, mallory):
    """A save is the owner working on their session, never a change of owner.

    If the upsert wrote `excluded.user_id`, every save would be a chance to take
    someone else's session — the exact hole this milestone exists to close,
    opened by the code meant to close it.
    """
    _, alice_id = alice
    _, mallory_id = mallory
    graph = _alices_session(db, alice_id)

    save_graph(graph, db, user_id=mallory_id)

    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
        owner = conn.execute(
            "SELECT user_id FROM sessions WHERE session_id = ?", (graph.session_id,)
        ).fetchone()[0]
    assert owner == alice_id
    assert load_graph(graph.session_id, mallory_id, db) is None


# ── anonymous callers ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("method,template,body", READS + WRITES,
                         ids=[t for _, t, _ in READS + WRITES])
def test_an_anonymous_caller_gets_401(db, alice, method, template, body):
    _, alice_id = alice
    graph = _alices_session(db, alice_id)
    anonymous = TestClient(api.app)

    response = anonymous.request(method, template.format(sid=graph.session_id), json=body)

    assert response.status_code == 401


def test_logging_out_ends_access_immediately(db, alice):
    alice_client, alice_id = alice
    graph = _alices_session(db, alice_id)
    assert alice_client.get(f"/session/{graph.session_id}").status_code == 200

    alice_client.post("/auth/logout")

    assert alice_client.get(f"/session/{graph.session_id}").status_code == 401
