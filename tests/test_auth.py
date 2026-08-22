"""Password authentication and opaque cookie sessions (multi-user M2).

Run with: uv run pytest tests/test_auth.py -v

Real Argon2, real SQLite, real HTTP through `TestClient`. No network, no LLM.
The only thing mocked is time, and only where a test needs a session to be old.

The properties these exist to hold, in the order they matter:

  a password is never recoverable from the database;
  a session token is never recoverable from the database;
  logout actually ends the session, on this device or on all of them;
  neither form will tell an anonymous visitor whether an account exists;
  and the whole thing survives a restart, because it is a table and not a dict.
"""
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.api as api
from backend.auth import identity, passwords, throttle, tokens

EMAIL = "shira@example.com"
PASSWORD = "a-long-enough-passphrase"


@pytest.fixture(autouse=True)
def _isolation(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    # Plain http in tests, so the cookie is not `Secure` and TestClient keeps it.
    monkeypatch.setenv("CODEONBOARD_COOKIE_SECURE", "0")
    monkeypatch.setattr(api, "SESSIONS_DB_PATH", tmp_path / "sessions.db")
    # The throttle is process-global by design; a test that trips it must not
    # lock out the next one.
    throttle.reset_all()
    yield
    throttle.reset_all()


@pytest.fixture
def db() -> Path:
    return api.SESSIONS_DB_PATH


@pytest.fixture
def client():
    return TestClient(api.app)


def _register(client, email=EMAIL, password=PASSWORD, **extra):
    return client.post(
        "/auth/register", json={"email": email, "password": password, **extra}
    )


# ── passwords ─────────────────────────────────────────────────────────────────

def test_the_password_is_never_stored(db, client):
    _register(client)

    with sqlite3.connect(db) as conn:
        stored = conn.execute("SELECT secret_hash FROM auth_identities").fetchone()[0]

    assert PASSWORD not in stored
    assert stored.startswith("$argon2id$"), "Argon2id, not something hand-rolled"
    # And nothing else in the row carries it either.
    with sqlite3.connect(db) as conn:
        everything = str(conn.execute("SELECT * FROM auth_identities").fetchall())
    assert PASSWORD not in everything


def test_the_same_password_hashes_differently_each_time(db):
    first = passwords.hash_password(PASSWORD)
    second = passwords.hash_password(PASSWORD)

    # Per-hash salt. Without it, equal hashes would reveal which accounts share
    # a password — and one cracked hash would open all of them.
    assert first != second
    assert passwords.verify(first, PASSWORD)
    assert passwords.verify(second, PASSWORD)


def test_a_wrong_password_does_not_verify():
    stored = passwords.hash_password(PASSWORD)

    assert passwords.verify(stored, PASSWORD + "x") is False
    assert passwords.verify(stored, "") is False


def test_an_identity_with_no_secret_never_verifies():
    """A federated identity has no password of ours — that is a miss, not a crash."""
    assert passwords.verify(None, "anything") is False
    assert passwords.verify("", "anything") is False


@pytest.mark.parametrize("weak", ["short", "password123", "PASSWORD", "12345678"])
def test_weak_passwords_are_refused_at_registration(client, weak):
    response = _register(client, password=weak)

    assert response.status_code == 400


def test_a_weak_password_refusal_says_what_is_wrong(client):
    """NOT generic, unlike the other refusals.

    This judges the caller's OWN password, so it reveals nothing about anyone
    else — and a person who is told only "no" cannot fix it.
    """
    response = _register(client, password="short")

    assert "10 characters" in response.json()["detail"]


def test_an_existing_password_is_never_re_validated_at_login(db, client):
    """Raising the minimum length must not lock people out of their own accounts."""
    _register(client)
    client.post("/auth/logout")

    from backend.auth import passwords as module

    original = module.MIN_PASSWORD_LENGTH
    try:
        module.MIN_PASSWORD_LENGTH = len(PASSWORD) + 50
        assert client.post(
            "/auth/login", json={"email": EMAIL, "password": PASSWORD}
        ).status_code == 200
    finally:
        module.MIN_PASSWORD_LENGTH = original


# ── registration ──────────────────────────────────────────────────────────────

def test_registration_creates_a_user_and_an_identity(db, client):
    response = _register(client, display_name="Shira")

    assert response.status_code == 201
    assert response.json()["email"] == EMAIL
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
        provider, subject = conn.execute(
            "SELECT provider, subject FROM auth_identities"
        ).fetchone()
    assert (provider, subject) == ("password", EMAIL)


def test_registration_signs_you_in(client):
    _register(client)

    assert client.get("/auth/me").status_code == 200


def test_email_is_normalised(db, client):
    _register(client, email="  SHIRA@Example.COM  ")

    assert client.get("/auth/me").json()["email"] == EMAIL
    # And the normalised form is what logs in.
    client.post("/auth/logout")
    assert client.post(
        "/auth/login", json={"email": "Shira@EXAMPLE.com", "password": PASSWORD}
    ).status_code == 200


def test_a_duplicate_email_is_refused_without_confirming_it_exists(client):
    _register(client)
    client.post("/auth/logout")

    response = _register(client, password="a-different-passphrase")

    assert response.status_code == 409
    detail = response.json()["detail"]
    # Says nothing about WHY the address cannot be used. "Already registered"
    # would turn this form into an account-enumeration oracle.
    assert "already" not in detail.lower()
    assert "exists" not in detail.lower()


def test_a_failed_registration_leaves_no_half_account(db, client):
    """THE FAILURE THIS PREVENTS.

    If the user row survived a failed identity insert, the account would exist
    with no way to sign in AND would be holding the email — so the retry would
    fail on the user insert instead, and that address would be unusable forever.
    """
    _register(client)
    client.post("/auth/logout")

    _register(client, password="another-good-passphrase")

    with sqlite3.connect(db) as conn:
        users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        identities = conn.execute("SELECT COUNT(*) FROM auth_identities").fetchone()[0]
    assert users == 1
    assert identities == 1


@pytest.mark.parametrize("bad", ["notanemail", "a@b", "a b@c.com", "@example.com"])
def test_a_malformed_email_is_refused(client, bad):
    assert _register(client, email=bad).status_code in (400, 422)


# ── login ─────────────────────────────────────────────────────────────────────

def test_login_with_the_right_password_succeeds(client):
    _register(client)
    client.post("/auth/logout")

    response = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})

    assert response.status_code == 200
    assert client.get("/auth/me").json()["email"] == EMAIL


def test_a_wrong_password_and_an_unknown_email_are_indistinguishable(client):
    _register(client)
    client.post("/auth/logout")

    wrong = client.post("/auth/login", json={"email": EMAIL, "password": "wrong-one-here"})
    unknown = client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}
    )

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]


def test_a_miss_costs_about_as_much_as_a_wrong_password(client):
    """The TIMING half of not confirming an account exists.

    Without the dummy verify, a miss returns in microseconds while a wrong
    password pays the ~50ms Argon2 is tuned to cost — a gap that is measurable
    over a handful of requests and defeats identical wording entirely.

    The bound is loose on purpose: this asserts the dummy verify HAPPENS, not
    that two Argon2 runs take equal wall-clock on a shared CI machine.
    """
    _register(client)
    client.post("/auth/logout")
    throttle.reset_all()

    def timed(email: str) -> float:
        start = time.perf_counter()
        client.post("/auth/login", json={"email": email, "password": "wrong-one-here"})
        throttle.reset_all()
        return time.perf_counter() - start

    wrong_password = min(timed(EMAIL) for _ in range(3))
    unknown_email = min(timed("nobody@example.com") for _ in range(3))

    assert unknown_email > wrong_password * 0.3, (
        f"miss {unknown_email:.4f}s vs wrong password {wrong_password:.4f}s — "
        "the miss path is not paying for a verification"
    )


def test_a_deactivated_account_cannot_log_in(db, client):
    _register(client)
    client.post("/auth/logout")
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE users SET is_active = 0")

    response = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})

    assert response.status_code == 401


def test_the_legacy_user_cannot_be_logged_in_as(db, client):
    """It has no password identity, so there is no credential that resolves to it."""
    legacy = identity.ensure_legacy_user(db)

    response = client.post(
        "/auth/login", json={"email": identity.LEGACY_EMAIL, "password": PASSWORD}
    )

    assert response.status_code == 401
    assert identity.get_user(legacy, db)["is_active"] == 0


def test_a_successful_login_rehashes_when_parameters_have_risen(db, client):
    """The only moment a stronger hash can be made is a correct login."""
    _register(client)
    client.post("/auth/logout")
    with sqlite3.connect(db) as conn:
        before = conn.execute("SELECT secret_hash FROM auth_identities").fetchone()[0]

    from argon2 import PasswordHasher
    from backend.auth import passwords as module

    stronger = PasswordHasher(time_cost=module._hasher.time_cost + 1)
    original = module._hasher
    try:
        module._hasher = stronger
        assert client.post(
            "/auth/login", json={"email": EMAIL, "password": PASSWORD}
        ).status_code == 200
    finally:
        module._hasher = original

    with sqlite3.connect(db) as conn:
        after = conn.execute("SELECT secret_hash FROM auth_identities").fetchone()[0]
    assert after != before
    assert passwords.verify(after, PASSWORD)


# ── the cookie ────────────────────────────────────────────────────────────────

def test_the_cookie_is_httponly_and_samesite_lax(client):
    response = _register(client)

    header = response.headers["set-cookie"]
    assert "httponly" in header.lower(), "readable by script is readable by XSS"
    assert "samesite=lax" in header.lower()
    assert "path=/" in header.lower()


def test_the_cookie_is_secure_when_not_told_otherwise(client, monkeypatch):
    """Defaults ON. A wrong default must fail visibly on http, not silently on https."""
    monkeypatch.delenv("CODEONBOARD_COOKIE_SECURE", raising=False)

    response = _register(client)

    assert "secure" in response.headers["set-cookie"].lower()


def test_only_the_hash_of_the_token_is_stored(db, client):
    response = _register(client)
    raw = response.cookies[tokens.COOKIE_NAME]

    with sqlite3.connect(db) as conn:
        rows = str(conn.execute("SELECT * FROM auth_sessions").fetchall())

    assert raw not in rows, "a database dump must not be a set of live credentials"
    assert tokens.hash_token(raw) in rows


def test_a_forged_token_authenticates_nobody(client):
    _register(client)
    client.cookies.set(tokens.COOKIE_NAME, "not-a-real-token")

    assert client.get("/auth/me").status_code == 401


# ── sessions ──────────────────────────────────────────────────────────────────

def test_logout_ends_the_session_and_clears_the_cookie(db, client):
    _register(client)

    response = client.post("/auth/logout")

    assert response.status_code == 204
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0] == 0
    assert client.get("/auth/me").status_code == 401


def test_logout_is_idempotent(client):
    _register(client)
    client.post("/auth/logout")

    # "Log me out" cannot fail from the caller's point of view.
    assert client.post("/auth/logout").status_code == 204


def test_logout_everywhere_ends_every_device(db, client):
    _register(client)
    other_device = TestClient(api.app)
    other_device.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0] == 2

    client.post("/auth/logout/all")

    assert other_device.get("/auth/me").status_code == 401
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0] == 0


def test_logout_everywhere_requires_being_signed_in(client):
    assert client.post("/auth/logout/all").status_code == 401


def test_two_devices_hold_independent_sessions(db, client):
    _register(client)
    other = TestClient(api.app)
    other.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})

    client.post("/auth/logout")

    # Signing out here must not sign out there.
    assert client.get("/auth/me").status_code == 401
    assert other.get("/auth/me").status_code == 200


def test_an_expired_session_stops_working(db, client):
    _register(client)
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE auth_sessions SET expires_at = ?", (past,))

    assert client.get("/auth/me").status_code == 401


def test_a_session_past_the_absolute_cap_stops_working(db, client):
    """Sliding expiry alone would keep a daily-used session alive forever — so a
    token stolen once would be good indefinitely as long as it kept being used."""
    _register(client)
    ancient = (
        datetime.now(timezone.utc) - timedelta(days=tokens.ABSOLUTE_DAYS + 1)
    ).isoformat()
    far_future = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE auth_sessions SET created_at = ?, expires_at = ?",
            (ancient, far_future),
        )

    assert client.get("/auth/me").status_code == 401


def test_using_a_session_slides_its_expiry(db, client):
    _register(client)
    # A session ISSUED two hours ago, not merely one whose `last_seen_at` was
    # edited: the new horizon is computed from NOW, so ageing only `last_seen_at`
    # recomputes the same second and the slide is invisible.
    two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE auth_sessions SET last_seen_at = ?, created_at = ?, expires_at = ?",
            (
                two_hours_ago.isoformat(),
                two_hours_ago.isoformat(),
                (two_hours_ago + timedelta(days=tokens.IDLE_DAYS)).isoformat(),
            ),
        )
        before = conn.execute("SELECT expires_at FROM auth_sessions").fetchone()[0]

    client.get("/auth/me")

    with sqlite3.connect(db) as conn:
        after = conn.execute("SELECT expires_at FROM auth_sessions").fetchone()[0]
    assert after > before


def test_a_recently_used_session_is_not_written_to_again(db, client):
    """`last_seen_at` is written at most hourly.

    This file's scarce resource is the write lock; an UPDATE in front of every
    lesson load would spend it on bookkeeping.
    """
    _register(client)
    with sqlite3.connect(db) as conn:
        before = conn.execute("SELECT last_seen_at FROM auth_sessions").fetchone()[0]

    client.get("/auth/me")
    client.get("/auth/me")

    with sqlite3.connect(db) as conn:
        after = conn.execute("SELECT last_seen_at FROM auth_sessions").fetchone()[0]
    assert after == before


def test_the_slide_never_passes_the_absolute_cap(db, client):
    _register(client)
    nearly_done = (
        datetime.now(timezone.utc) - timedelta(days=tokens.ABSOLUTE_DAYS - 1)
    ).isoformat()
    stale = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE auth_sessions SET created_at = ?, last_seen_at = ?",
            (nearly_done, stale),
        )

    client.get("/auth/me")

    with sqlite3.connect(db) as conn:
        expires = conn.execute("SELECT expires_at FROM auth_sessions").fetchone()[0]
    horizon = datetime.now(timezone.utc) + timedelta(days=2)
    assert datetime.fromisoformat(expires) <= horizon


def test_purge_removes_only_dead_sessions(db, client):
    _register(client)
    other = TestClient(api.app)
    other.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE auth_sessions SET expires_at = ? WHERE token_hash = "
            "(SELECT token_hash FROM auth_sessions LIMIT 1)",
            (past,),
        )

    assert tokens.purge_expired(db) == 1
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0] == 1


# ── persistence across a restart ──────────────────────────────────────────────

def test_a_session_survives_a_backend_restart(db, client):
    """THE POINT OF A TABLE RATHER THAN A DICT.

    A fresh `TestClient` over a fresh app object, carrying only the cookie, is
    the closest thing in-process to a restarted server: no in-memory state
    survives it, and the session does.
    """
    raw = _register(client).cookies[tokens.COOKIE_NAME]

    import importlib

    restarted = importlib.reload(api)
    restarted.SESSIONS_DB_PATH = db
    fresh = TestClient(restarted.app)
    fresh.cookies.set(tokens.COOKIE_NAME, raw)

    try:
        response = fresh.get("/auth/me")
        assert response.status_code == 200
        assert response.json()["email"] == EMAIL
    finally:
        # Other test modules hold this module object; leave it as they expect.
        importlib.reload(api)


# ── throttling ────────────────────────────────────────────────────────────────

def test_repeated_failures_are_eventually_refused(client):
    _register(client)
    client.post("/auth/logout")

    codes = [
        client.post(
            "/auth/login", json={"email": EMAIL, "password": "wrong-one-here"}
        ).status_code
        for _ in range(throttle.FREE_ATTEMPTS + 2)
    ]

    assert codes[0] == 401
    assert codes[-1] == 429


def test_a_lockout_says_how_long_to_wait(client):
    _register(client)
    client.post("/auth/logout")
    for _ in range(throttle.FREE_ATTEMPTS + 2):
        client.post("/auth/login", json={"email": EMAIL, "password": "wrong-one-here"})

    response = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})

    assert response.status_code == 429
    assert int(response.headers["retry-after"]) >= 1


def test_a_correct_password_clears_the_counter(client):
    _register(client)
    client.post("/auth/logout")
    for _ in range(throttle.FREE_ATTEMPTS - 1):
        client.post("/auth/login", json={"email": EMAIL, "password": "wrong-one-here"})

    assert client.post(
        "/auth/login", json={"email": EMAIL, "password": PASSWORD}
    ).status_code == 200
    # Someone who mistyped four times and then got it right is not an attacker.
    client.post("/auth/logout")
    assert client.post(
        "/auth/login", json={"email": EMAIL, "password": "wrong-one-here"}
    ).status_code == 401


def test_the_lockout_grows_with_each_failure():
    counter = throttle.Throttle()
    penalties = [
        counter.record_failure("k") for _ in range(throttle.FREE_ATTEMPTS + 4)
    ]

    charged = [p for p in penalties if p > 0]
    assert charged == sorted(charged), "must not get cheaper"
    assert charged[-1] > charged[0]
    assert charged[-1] <= throttle.MAX_PENALTY_SECONDS


def test_the_counter_forgets_after_the_window():
    counter = throttle.Throttle()
    for _ in range(throttle.FREE_ATTEMPTS + 3):
        counter.record_failure("k", now=0.0)

    assert counter.retry_after("k", now=0.0) > 0
    assert counter.retry_after("k", now=throttle.WINDOW_SECONDS + 1) == 0.0


def test_a_flood_of_new_keys_cannot_evict_a_live_counter():
    """The eviction rule, which is the difference between a throttle and a hint.

    If a flood could push out the counter tracking it, an attacker would simply
    generate keys to buy their own amnesty.
    """
    counter = throttle.Throttle()
    for _ in range(throttle.FREE_ATTEMPTS + 3):
        counter.record_failure("victim", now=1000.0)
    assert counter.retry_after("victim", now=1000.0) > 0

    for i in range(throttle.MAX_KEYS + 50):
        counter.record_failure(f"flood-{i}", now=1000.0)

    assert counter.retry_after("victim", now=1000.0) > 0
