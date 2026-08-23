"""The session list and its lifecycle: list, rename, archive, delete (M4).

Run with: uv run pytest tests/test_sessions_api.py -v

The dashboard's data layer. What is worth pinning down here is not that the CRUD
works, but the three properties that make it a dashboard rather than a table:

  it shows YOUR sessions and only yours (M3's guarantee, re-checked here at the
  list level because a listing is where a leak would be most useful);

  it costs nothing to draw — no graph is loaded, which is why the progress
  numbers are cached columns rather than a computation;

  archiving is not deleting, and the difference survives.
"""
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.api as api
from tests.conftest import TEST_USER_ID
from backend.auth import identity
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.learning.store import create_session, load_graph, save_graph


@pytest.fixture(autouse=True)
def _isolation(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(api, "SESSIONS_DB_PATH", tmp_path / "sessions.db")


@pytest.fixture
def db() -> Path:
    return api.SESSIONS_DB_PATH


@pytest.fixture
def client():
    return TestClient(api.app)


def _graph(focus="the Session object", repo="https://github.com/psf/requests"):
    graph = LearningGraph(
        repo_url=repo,
        goal={"primary_goal": "understand sessions", "focus_area": focus},
    )
    first = graph.add_node(LearningNode(
        title="Understand Session",
        code_anchor=CodeAnchor(file="requests/sessions.py", line_start=1, line_end=80),
        lesson_brief={"priority": "required"},
    ))
    second = graph.add_node(LearningNode(
        title="Trace send",
        code_anchor=CodeAnchor(file="requests/sessions.py", line_start=394, line_end=470),
        lesson_brief={"priority": "required"},
    ))
    graph.add_edge(first.id, second.id, kind="sequence")
    graph.set_current(first.id)
    return graph


def _mine(db, focus="the Session object", repo="https://github.com/psf/requests"):
    graph = _graph(focus, repo)
    create_session(graph, db, user_id=TEST_USER_ID)
    return graph


# ── listing ───────────────────────────────────────────────────────────────────

def test_the_list_is_empty_before_anything_exists(client):
    assert client.get("/sessions").json()["sessions"] == []


def test_the_list_returns_what_a_card_needs(db, client):
    graph = _mine(db)

    row = client.get("/sessions").json()["sessions"][0]

    assert row["session_id"] == graph.session_id
    assert row["repo_url"] == "https://github.com/psf/requests"
    assert row["goal"]["focus_area"] == "the Session object"
    assert row["repo_id"], "the canonical repository row"
    assert "progress" in row


def test_the_list_does_not_load_graphs(db, client, monkeypatch):
    """THE REASON THE PROGRESS COLUMNS EXIST.

    Forty sessions on the dashboard would otherwise mean reading every node row
    of all forty — nine hundred rows of JSON — to show three numbers per card.
    """
    for i in range(3):
        _mine(db, focus=f"area {i}")
    from backend.learning import store

    def explode(*args, **kwargs):
        raise AssertionError("the listing loaded a graph")

    monkeypatch.setattr(store, "load_graph", explode)

    assert len(client.get("/sessions").json()["sessions"]) == 3


def test_progress_is_cached_on_save_from_the_one_thing_that_owns_it(db, client):
    graph = _mine(db)
    node = graph.path_order()[0]
    graph.record_attempt(node, "an answer", "understood", "yes")
    graph.mark_visited(node)
    save_graph(graph, db, user_id=TEST_USER_ID)

    row = client.get("/sessions").json()["sessions"][0]

    from backend.learning import progress as progress_model

    truth = progress_model.summary(load_graph(graph.session_id, TEST_USER_ID, db))
    assert row["progress"]["goal_readiness"] == truth["goal_readiness"]
    assert row["progress"]["stops_total"] == truth["stops_total"]


def test_an_uncached_session_reports_unknown_not_zero(db, client):
    """NULL means "not computed". Reading it as 0% would be a claim about the
    learner rather than about the cache — a migrated session that has not been
    saved since would show as no progress at all."""
    graph = _mine(db)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE sessions SET readiness_cached = NULL, "
                     "stops_settled_cached = NULL, stops_total_cached = NULL")

    row = client.get("/sessions").json()["sessions"][0]

    assert row["progress"]["goal_readiness"] is None
    assert row["progress"]["stops_total"] is None


def test_newest_activity_first(db, client):
    first = _mine(db, focus="older")
    second = _mine(db, focus="newer")
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE sessions SET last_active_at = ? WHERE session_id = ?",
                     ("2020-01-01T00:00:00", first.session_id))
        conn.execute("UPDATE sessions SET last_active_at = ? WHERE session_id = ?",
                     ("2030-01-01T00:00:00", second.session_id))

    listed = [s["session_id"] for s in client.get("/sessions").json()["sessions"]]

    assert listed[0] == second.session_id


# ── several sessions on one repository (I3) ───────────────────────────────────

def test_three_sessions_on_one_repository_are_independent(db, client):
    """The explicit product requirement, at the list level."""
    a = _mine(db, focus="auth")
    b = _mine(db, focus="routing")
    c = _mine(db, focus="pooling")

    listed = client.get("/sessions").json()["sessions"]

    assert len({s["session_id"] for s in listed}) == 3
    assert {s["goal"]["focus_area"] for s in listed} == {"auth", "routing", "pooling"}
    # And they share no nodes, so no state can leak between them.
    ids = [set(load_graph(s.session_id, TEST_USER_ID, db).nodes) for s in (a, b, c)]
    assert not (ids[0] & ids[1]) and not (ids[1] & ids[2])


def test_the_repo_filter_narrows_rather_than_widens(db, client):
    _mine(db, focus="requests one")
    _mine(db, focus="fastapi one", repo="https://github.com/fastapi/fastapi")

    listed = client.get(
        "/sessions?repo_url=https://github.com/fastapi/fastapi"
    ).json()["sessions"]

    assert [s["goal"]["focus_area"] for s in listed] == ["fastapi one"]


# ── rename ────────────────────────────────────────────────────────────────────

def test_renaming_a_session(db, client):
    graph = _mine(db)

    response = client.patch(
        f"/sessions/{graph.session_id}", json={"title": "  Connection pooling  "}
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Connection pooling"
    assert client.get("/sessions").json()["sessions"][0]["title"] == "Connection pooling"


def test_renaming_does_not_touch_the_learning(db, client):
    graph = _mine(db)
    node = graph.path_order()[0]
    graph.record_attempt(node, "an answer", "partial", "close")
    save_graph(graph, db, user_id=TEST_USER_ID)

    client.patch(f"/sessions/{graph.session_id}", json={"title": "Renamed"})

    reloaded = load_graph(graph.session_id, TEST_USER_ID, db)
    assert len(reloaded.nodes[node].attempts) == 1


def test_renaming_a_session_that_is_not_yours_is_a_404(db, client):
    graph = _graph()
    other = identity.create_user("someone@example.com", db_path=db)
    create_session(graph, db, user_id=other)

    response = client.patch(f"/sessions/{graph.session_id}", json={"title": "mine now"})

    assert response.status_code == 404
    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "SELECT title FROM sessions WHERE session_id = ?", (graph.session_id,)
        ).fetchone()[0] != "mine now"


# ── archive ───────────────────────────────────────────────────────────────────

def test_archiving_hides_from_the_default_list(db, client):
    graph = _mine(db)

    client.patch(f"/sessions/{graph.session_id}", json={"archived": True})

    assert client.get("/sessions").json()["sessions"] == []
    assert len(client.get("/sessions?include_archived=true").json()["sessions"]) == 1


def test_archiving_keeps_everything(db, client):
    """ARCHIVING IS NOT DELETING, and the difference has to survive.

    A learner tidying their dashboard has not thrown their work away, and
    un-archiving must give it all back.
    """
    graph = _mine(db)
    node = graph.path_order()[0]
    graph.record_attempt(node, "an answer worth keeping", "partial", "close")
    save_graph(graph, db, user_id=TEST_USER_ID)

    client.patch(f"/sessions/{graph.session_id}", json={"archived": True})
    reloaded = load_graph(graph.session_id, TEST_USER_ID, db)

    assert reloaded is not None
    assert reloaded.nodes[node].attempts[0]["answer"] == "an answer worth keeping"


def test_un_archiving_brings_it_back(db, client):
    graph = _mine(db)
    client.patch(f"/sessions/{graph.session_id}", json={"archived": True})

    client.patch(f"/sessions/{graph.session_id}", json={"archived": False})

    assert len(client.get("/sessions").json()["sessions"]) == 1


# ── delete ────────────────────────────────────────────────────────────────────

def test_deleting_removes_the_session_and_everything_under_it(db, client):
    graph = _mine(db)

    assert client.delete(f"/sessions/{graph.session_id}").status_code == 204

    assert load_graph(graph.session_id, TEST_USER_ID, db) is None
    with sqlite3.connect(db) as conn:
        for table in ("sessions", "nodes", "edges", "plan_nodes", "plan_edges"):
            assert conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE session_id = ?",
                (graph.session_id,),
            ).fetchone()[0] == 0, f"{table} left rows behind"


def test_deleting_removes_the_dossier_that_has_no_foreign_key(db, client):
    """`investigation` has no FK to `sessions`, so a cascade cannot reach it.

    Before this it was left behind on every delete — a full exploration payload
    keyed to an id nothing would ever ask for again.
    """
    from backend.repo import dossier_store

    graph = _mine(db)
    dossier_store.save_investigation(
        graph.session_id, "abc123", {"dossier": {"claims": []}}, db
    )

    client.delete(f"/sessions/{graph.session_id}")

    assert dossier_store.load_investigation(graph.session_id, "abc123", db) is None


def test_deleting_someone_elses_session_is_a_404_and_changes_nothing(db, client):
    graph = _graph()
    other = identity.create_user("someone@example.com", db_path=db)
    create_session(graph, db, user_id=other)

    assert client.delete(f"/sessions/{graph.session_id}").status_code == 404

    assert load_graph(graph.session_id, other, db) is not None


def test_deleting_one_session_leaves_its_siblings_alone(db, client):
    keep = _mine(db, focus="keep me")
    drop = _mine(db, focus="drop me")

    client.delete(f"/sessions/{drop.session_id}")

    remaining = client.get("/sessions").json()["sessions"]
    assert [s["session_id"] for s in remaining] == [keep.session_id]
    assert load_graph(keep.session_id, TEST_USER_ID, db) is not None


def test_deleting_an_unknown_session_is_a_404(client):
    assert client.delete("/sessions/" + "0" * 32).status_code == 404


# ── the cheap single-session read ─────────────────────────────────────────────

def test_the_summary_endpoint_returns_one_row(db, client):
    graph = _mine(db)

    row = client.get(f"/sessions/{graph.session_id}").json()

    assert row["session_id"] == graph.session_id
    assert "progress" in row


def test_the_summary_endpoint_finds_an_archived_session(db, client):
    """Archived sessions are hidden from the LIST, not made unreachable."""
    graph = _mine(db)
    client.patch(f"/sessions/{graph.session_id}", json={"archived": True})

    assert client.get(f"/sessions/{graph.session_id}").status_code == 200


def test_the_summary_endpoint_is_owner_scoped(db, client):
    graph = _graph()
    other = identity.create_user("someone@example.com", db_path=db)
    create_session(graph, db, user_id=other)

    assert client.get(f"/sessions/{graph.session_id}").status_code == 404
