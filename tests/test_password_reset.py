"""Development-grade password reset: `/auth/forgot` → `/auth/reset`.

Run with: uv run pytest tests/test_password_reset.py -v

Real Argon2, real SQLite, real HTTP through `TestClient`. Nothing mocked except
the clock, and only where a test needs a token to be old.

## What is deliberately NOT tested here

That the link reaches the right person. It cannot be: nothing mails it, which is
the whole limitation `backend/auth/reset.py` documents. These tests cover the
token lifecycle and the consequences of spending one — which is the part that
would still be needed on the day a mail provider is added.

The properties, in the order they matter:

  a token is single-use, and expires;
  spending one replaces the password and ends every existing session;
  the reset token is never recoverable from the database;
  and production reveals no link, so the endpoint is inert rather than dangerous.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.api as api
from backend.auth import identity, passwords, reset, throttle, tokens
from backend.learning.store import _connect

# Same reason as `tests/test_auth.py`: this suite tests authentication, so a
# fixture that keeps a caller signed in would make its assertions vacuous.
pytestmark = pytest.mark.real_auth

EMAIL = "shira@example.com"
PASSWORD = "a-long-enough-passphrase"
NEW_PASSWORD = "a-different-long-passphrase"


@pytest.fixture(autouse=True)
def _isolation(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    # Plain http in tests, so the cookie is not `Secure` and TestClient keeps it.
    monkeypatch.setenv("CODEONBOARD_COOKIE_SECURE", "0")
    # Explicit rather than inherited: `reveals_reset_link()` reads this, and a
    # stray production value in the environment would silently blank every link.
    monkeypatch.setenv("CODEONBOARD_ENV", "development")
    monkeypatch.setattr(api, "SESSIONS_DB_PATH", tmp_path / "sessions.db")
    throttle.reset_all()
    yield
    throttle.reset_all()


@pytest.fixture
def db() -> Path:
    return api.SESSIONS_DB_PATH


@pytest.fixture
def client():
    return TestClient(api.app)


@pytest.fixture
def account(client):
    """A registered account, signed OUT — the state a reset actually starts from."""
    response = client.post(
        "/auth/register", json={"email": EMAIL, "password": PASSWORD}
    )
    assert response.status_code == 201
    user_id = response.json()["user_id"]
    client.cookies.clear()
    return user_id


def _forgot(client, email=EMAIL):
    return client.post("/auth/forgot", json={"email": email})


def _token_from(response) -> str:
    url = response.json()["reset_url"]
    assert url, "development should return a link"
    return url.split("token=", 1)[1]


# ── the happy path ────────────────────────────────────────────────────────────

def test_the_link_points_at_the_reset_page(client, account):
    url = _forgot(client).json()["reset_url"]
    assert "/reset-password?token=" in url
    # Against the app's origin, not the API's — the page is served by Next.
    assert url.startswith("http://localhost:3000")


def test_a_reset_replaces_the_password(client, account):
    token = _token_from(_forgot(client))

    response = client.post(
        "/auth/reset", json={"token": token, "password": NEW_PASSWORD}
    )
    assert response.status_code == 200
    assert response.json()["email"] == EMAIL

    client.cookies.clear()
    assert client.post(
        "/auth/login", json={"email": EMAIL, "password": NEW_PASSWORD}
    ).status_code == 200
    assert client.post(
        "/auth/login", json={"email": EMAIL, "password": PASSWORD}
    ).status_code == 401


def test_a_reset_signs_this_browser_in(client, account):
    token = _token_from(_forgot(client))
    client.post("/auth/reset", json={"token": token, "password": NEW_PASSWORD})
    # No second sign-in step: the response carried a session cookie.
    assert client.get("/auth/me").status_code == 200


# ── the token ─────────────────────────────────────────────────────────────────

def test_a_token_works_exactly_once(client, account):
    token = _token_from(_forgot(client))
    assert client.post(
        "/auth/reset", json={"token": token, "password": NEW_PASSWORD}
    ).status_code == 200

    replayed = client.post(
        "/auth/reset", json={"token": token, "password": "yet-another-passphrase"}
    )
    assert replayed.status_code == 401
    assert replayed.json()["detail"] == "invalid_reset_token"


def test_an_expired_token_is_refused(client, account, db):
    token = _token_from(_forgot(client))

    # Age the row rather than the clock: the expiry is a stored timestamp, so
    # this tests the comparison the code actually makes.
    stale = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(microsecond=0)
    with _connect(db) as conn:
        conn.execute(
            "UPDATE password_resets SET expires_at = ?", (stale.isoformat(),)
        )

    assert client.post(
        "/auth/reset", json={"token": token, "password": NEW_PASSWORD}
    ).status_code == 401
    # And the old password still works, because nothing was changed.
    assert client.post(
        "/auth/login", json={"email": EMAIL, "password": PASSWORD}
    ).status_code == 200


def test_an_unknown_token_is_refused(client, account):
    assert client.post(
        "/auth/reset", json={"token": "not-a-real-token", "password": NEW_PASSWORD}
    ).status_code == 401


def test_the_raw_token_is_never_stored(client, account, db):
    token = _token_from(_forgot(client))
    with _connect(db) as conn:
        rows = conn.execute("SELECT * FROM password_resets").fetchall()
    assert len(rows) == 1
    blob = " ".join(str(value) for row in rows for value in row)
    assert token not in blob
    assert reset.hash_token(token) in blob


def test_requesting_twice_leaves_only_the_newer_link_valid(client, account):
    first = _token_from(_forgot(client))
    second = _token_from(_forgot(client))
    assert first != second

    assert client.post(
        "/auth/reset", json={"token": first, "password": NEW_PASSWORD}
    ).status_code == 401
    assert client.post(
        "/auth/reset", json={"token": second, "password": NEW_PASSWORD}
    ).status_code == 200


# ── the consequences of a reset ───────────────────────────────────────────────

def test_a_reset_ends_every_existing_session(client, account, db):
    # Another live session on this account — the one a reset exists to eject.
    # Two of them, so "revoked all" is not accidentally "revoked one".
    stolen = tokens.issue(account, db_path=db)
    also_stolen = tokens.issue(account, db_path=db)

    token = _token_from(_forgot(client))
    client.post("/auth/reset", json={"token": token, "password": NEW_PASSWORD})

    assert tokens.resolve(stolen, db) is None
    assert tokens.resolve(also_stolen, db) is None
    # …and the browser that did the reset is still signed in.
    assert client.get("/auth/me").status_code == 200


def test_a_weak_password_is_refused_and_the_link_survives(client, account):
    token = _token_from(_forgot(client))

    refused = client.post("/auth/reset", json={"token": token, "password": "short"})
    assert refused.status_code == 400
    assert str(passwords.MIN_PASSWORD_LENGTH) in refused.json()["detail"]

    # THE POINT: the token was not spent on a rejected password, so the person
    # can simply try again instead of starting the flow over.
    assert client.post(
        "/auth/reset", json={"token": token, "password": NEW_PASSWORD}
    ).status_code == 200


# ── what /forgot does not disclose ────────────────────────────────────────────

def test_an_unknown_address_gets_the_same_status_and_no_link(client, account):
    known = _forgot(client)
    unknown = _forgot(client, email="nobody@example.com")

    assert known.status_code == unknown.status_code == 200
    assert unknown.json()["reset_url"] is None


def test_a_google_only_account_gets_no_link(client, db):
    """There is no password to replace, and creating one here would be LINKING.

    D-7 makes linking cost a password confirmation. A reset endpoint that
    quietly added a password identity to a federated account would be a way
    around it.
    """
    user_id = identity.create_user("google-person@example.com", db_path=db)
    identity.add_identity(
        user_id, identity.GOOGLE, "google-subject-123",
        email_verified=True, db_path=db,
    )

    response = _forgot(client, email="google-person@example.com")
    assert response.status_code == 200
    assert response.json()["reset_url"] is None


def test_production_reveals_no_link(client, account, monkeypatch):
    """The endpoint still answers, and is inert. See `config.reveals_reset_link`."""
    monkeypatch.setenv("CODEONBOARD_ENV", "production")

    response = _forgot(client)
    assert response.status_code == 200
    assert response.json()["reset_url"] is None
