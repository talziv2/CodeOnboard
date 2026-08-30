"""The first run of a fresh installation, driven the way a new learner drives it.

## What this file is defending

A brand-new install used to answer `GET /sessions` with a 500, and the reason it
survived so long is that it is invisible to anybody whose database already has
rows in it:

    register  → 201, and the account tables are created (the file now EXISTS)
    /sessions → sqlite3.OperationalError: no such table: sessions

`list_sessions_for_user` guards with `if not Path(db_path).exists()`, which was
written for "no file at all". Registration creates the file without the learning
store's tables, so the guard passes and the query hits a table that is not there.

## Why these are route-level and not a unit test of `ensure_schema`

A unit test asserting `ensure_schema` creates tables would have passed on the
broken build too — the function is new, and the bug was never that table creation
was wrong. The bug was that **nothing called it before the dashboard was read**.
Only the sequence catches that, so these tests spend a `TestClient` and drive the
actual first-run path: empty disk → startup → register → list sessions.

`pytestmark = real_auth` because the point is a real registration through the
real cookie, not the suite's signed-in-by-default fixture.
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend import api

pytestmark = pytest.mark.real_auth


PASSWORD = "correct horse battery staple"


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """A database path that does not exist yet, and is never `data/sessions.db`.

    Points at a `data/` SUBDIRECTORY that also does not exist, because creating
    the parent is part of what a fresh install has to do — `_connect` mkdirs it,
    and a test that pre-created the directory would not prove that.
    """
    db_path = tmp_path / "data" / "sessions.db"
    monkeypatch.setattr(api, "SESSIONS_DB_PATH", db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("CODEONBOARD_COOKIE_SECURE", "0")
    assert not db_path.exists()
    return db_path


def _register(client: TestClient, email: str = "newcomer@example.com"):
    return client.post(
        "/auth/register", json={"email": email, "password": PASSWORD}
    )


def test_a_new_learner_registers_and_sees_an_empty_dashboard(fresh_db):
    """The whole acceptance path: no database → start → register → list sessions.

    THE REGRESSION. On the build before `ensure_schema` the last call raised
    `no such table: sessions`, and the dashboard rendered a red error line to
    somebody whose account was ten seconds old.
    """
    with TestClient(api.app) as client:
        assert _register(client).status_code == 201

        response = client.get("/sessions")

    assert response.status_code == 200
    assert response.json()["sessions"] == []


def test_the_archived_view_is_empty_too(fresh_db):
    """`include_archived` takes a different branch of the same query.

    Cheap, and it is the other thing the dashboard calls on arrival — the toggle
    is rendered before any session exists.
    """
    with TestClient(api.app) as client:
        assert _register(client).status_code == 201

        response = client.get("/sessions", params={"include_archived": True})

    assert response.status_code == 200
    assert response.json()["sessions"] == []


def test_startup_creates_both_halves_of_the_schema(fresh_db):
    """Starting the app is enough; nothing has to be registered first.

    Both table sets, because the bug was precisely that ONE of them appeared
    without the other. `sessions` belongs to the learning store, `users` to the
    account layer, and a fresh boot has to produce both.
    """
    with TestClient(api.app):
        pass

    assert fresh_db.exists()
    with sqlite3.connect(fresh_db) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }

    assert {"sessions", "nodes", "edges", "plan_nodes", "plan_edges"} <= tables
    assert {"users", "auth_identities", "auth_sessions", "session_drafts"} <= tables


def test_booting_twice_on_the_same_database_is_harmless(fresh_db):
    """Idempotence, at the level that matters: the second process serves too.

    `init_db` and `init_auth_schema` are `IF NOT EXISTS` throughout, but the
    claim being tested is the one a developer relies on — restarting `uvicorn`
    against an existing database does not fail and does not lose the account
    created before the restart.
    """
    with TestClient(api.app) as client:
        assert _register(client).status_code == 201

    with TestClient(api.app) as client:
        # A fresh process: no cookie, so this is the account layer answering
        # about a database that already exists rather than one it just made.
        assert client.get("/auth/me").status_code == 401
        assert client.post(
            "/auth/login",
            json={"email": "newcomer@example.com", "password": PASSWORD},
        ).status_code == 200
        assert client.get("/sessions").json()["sessions"] == []


def test_a_fresh_install_carries_no_data_from_anywhere_else(fresh_db):
    """One account, no sessions — nothing inherited from a development database.

    The acceptance test in the plan checks this over SQLite directly; this is the
    same assertion where it can run on every commit.
    """
    with TestClient(api.app) as client:
        assert _register(client).status_code == 201

    with sqlite3.connect(fresh_db) as conn:
        emails = [row[0] for row in conn.execute("SELECT email FROM users")]
        sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

    assert emails == ["newcomer@example.com"]
    assert sessions == 0
