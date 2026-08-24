"""The security review, written as tests (multi-user M8).

Run with: uv run pytest tests/test_security.py -v

A review is a document that describes what was true on the day somebody read
the code. These are the same claims, checked on every run — so the ones that stop
being true fail rather than quietly age.

Grouped by the thing that would go wrong, not by the module that implements it.
"""
import re
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.api as api
from backend.auth import config as auth_config
from backend.auth import identity, passwords, throttle, tokens

pytestmark = pytest.mark.real_auth

EMAIL = "learner@example.com"
PASSWORD = "a-long-enough-passphrase"


@pytest.fixture(autouse=True)
def _isolation(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("CODEONBOARD_COOKIE_SECURE", "0")
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


def _register(client, email=EMAIL, password=PASSWORD):
    response = client.post(
        "/auth/register", json={"email": email, "password": password}
    )
    assert response.status_code == 201, response.text
    return response.json()["user_id"]


# ── secrets never reach disk in a recoverable form ────────────────────────────

def test_no_password_and_no_token_is_stored_in_recoverable_form(db, client):
    """The single most important property in the file.

    A dump of this database — a backup, a laptop, a support ticket — must not be
    a set of credentials.
    """
    _register(client)

    with sqlite3.connect(db) as conn:
        everything = ""
        for (table,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ):
            everything += str(conn.execute(f"SELECT * FROM {table}").fetchall())

    assert PASSWORD not in everything, "the password is on disk somewhere"
    assert client.cookies.get(tokens.COOKIE_NAME) not in everything, (
        "the raw session token is on disk"
    )


def test_the_stored_password_is_argon2id(db, client):
    _register(client)

    with sqlite3.connect(db) as conn:
        stored = conn.execute("SELECT secret_hash FROM auth_identities").fetchone()[0]

    assert stored.startswith("$argon2id$"), stored[:20]


# ── the API says as little as possible ────────────────────────────────────────

def test_no_endpoint_confirms_whether_an_account_exists(client):
    _register(client)
    client.post("/auth/logout")

    wrong = client.post("/auth/login", json={"email": EMAIL, "password": "wrong-one-x"})
    throttle.reset_all()
    unknown = client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}
    )

    assert wrong.status_code == unknown.status_code
    assert wrong.json() == unknown.json()


def test_error_bodies_do_not_carry_internals(db, client):
    """A traceback, a file path or a SQL fragment in a 500 is a map of the app."""
    _register(client)

    response = client.get("/session/" + "0" * 32)

    body = response.text
    for leak in ("Traceback", "sqlite3", "site-packages", "SELECT ", "backend\\\\", "/backend/"):
        assert leak not in body, f"{leak!r} leaked in {body[:200]}"


def test_a_foreign_session_and_a_missing_one_are_identical(db, client):
    """IDOR, and the oracle that would remain if it answered 403."""
    from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
    from backend.learning.store import create_session

    _register(client)
    stranger = identity.create_user("stranger@example.com", db_path=db)
    graph = LearningGraph(repo_url="https://github.com/psf/requests", goal={})
    graph.add_node(LearningNode(
        title="x", code_anchor=CodeAnchor(file="a.py", line_start=1, line_end=2)))
    create_session(graph, db, user_id=stranger)

    real = client.get(f"/session/{graph.session_id}")
    invented = client.get("/session/" + "0" * 32)

    assert real.status_code == invented.status_code == 404
    assert real.json() == invented.json()


# ── headers and cookies ───────────────────────────────────────────────────────

def test_the_session_cookie_cannot_be_read_by_script(client):
    response = client.post(
        "/auth/register", json={"email": EMAIL, "password": PASSWORD}
    )

    assert "httponly" in response.headers["set-cookie"].lower()


def test_security_headers_are_present(client):
    response = client.get("/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_cors_never_pairs_a_wildcard_with_credentials(client):
    """A combination browsers reject anyway, and a mistake worth failing on.

    `allow_credentials=True` with `allow_origins=["*"]` is the shape somebody
    reaches for when CORS is in the way.
    """
    assert "*" not in api.ALLOWED_ORIGINS


def test_an_unknown_origin_is_refused(client):
    response = client.options(
        "/auth/login",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert "access-control-allow-origin" not in response.headers


# ── brute force ───────────────────────────────────────────────────────────────

def test_login_is_throttled(client):
    _register(client)
    client.post("/auth/logout")

    codes = [
        client.post(
            "/auth/login", json={"email": EMAIL, "password": "wrong-one-x"}
        ).status_code
        for _ in range(throttle.FREE_ATTEMPTS + 3)
    ]

    assert 429 in codes


def test_the_throttle_cannot_be_bypassed_with_a_forged_header(client, monkeypatch):
    """`X-Forwarded-For` is honoured ONLY behind a declared proxy.

    Otherwise an attacker varies it and the per-IP counter never fires.
    """
    monkeypatch.delenv("CODEONBOARD_TRUST_PROXY", raising=False)
    _register(client)
    client.post("/auth/logout")

    codes = []
    for i in range(throttle.FREE_ATTEMPTS + 3):
        codes.append(client.post(
            "/auth/login",
            json={"email": EMAIL, "password": "wrong-one-x"},
            headers={"X-Forwarded-For": f"10.0.0.{i}"},
        ).status_code)

    assert 429 in codes, "a forged header defeated the throttle"


# ── outbound requests ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "http://169.254.169.254/latest/meta-data/",
    "http://localhost:8000/session/x",
    "file:///etc/passwd",
    "https://evil.example.com/a/b",
    "https://github.com.evil.example.com/a/b",
])
def test_the_server_will_not_fetch_an_arbitrary_url(client, url, monkeypatch):
    """`/repo/check` makes the SERVER fetch what the CALLER names.

    Unbounded, that is a server-side request forgery primitive: a URL the caller
    cannot reach becomes a request the server makes for them.
    """
    from backend.repo import cloner

    def explode(*a, **k):                       # pragma: no cover - must not run
        raise AssertionError(f"git was called for {url}")

    monkeypatch.setattr(cloner.git.cmd, "Git", explode)
    _register(client)

    response = client.post("/repo/check", json={"repo_url": url})

    assert response.status_code == 200
    assert response.json()["ok"] is False


def test_the_file_endpoint_cannot_escape_the_checkout(db, client, tmp_path):
    from backend.repo.cloner import resolve_within

    checkout = tmp_path / "requests"
    (checkout / "src").mkdir(parents=True)
    (tmp_path / "requests-private").mkdir()

    assert resolve_within(str(checkout), "../requests-private/secret") is None
    assert resolve_within(str(checkout), "../../etc/passwd") is None
    assert resolve_within(str(checkout), "/etc/passwd") is None


# ── configuration ─────────────────────────────────────────────────────────────

def test_production_refuses_insecure_cookies(monkeypatch):
    monkeypatch.setenv("CODEONBOARD_ENV", "production")
    monkeypatch.setenv("CODEONBOARD_COOKIE_SECURE", "0")
    monkeypatch.setenv("CODEONBOARD_SECRET_KEY", "x")
    monkeypatch.setenv("CODEONBOARD_ALLOWED_ORIGINS", "https://app.example.com")

    problems = auth_config.check()

    assert any("COOKIE_SECURE" in p for p in problems)


def test_production_refuses_a_missing_signing_key(monkeypatch):
    monkeypatch.setenv("CODEONBOARD_ENV", "production")
    monkeypatch.delenv("CODEONBOARD_SECRET_KEY", raising=False)
    monkeypatch.setenv("CODEONBOARD_ALLOWED_ORIGINS", "https://app.example.com")

    assert any("SECRET_KEY" in p for p in auth_config.check())


def test_production_refuses_a_leftover_localhost_origin(monkeypatch):
    monkeypatch.setenv("CODEONBOARD_ENV", "production")
    monkeypatch.setenv("CODEONBOARD_SECRET_KEY", "x")
    monkeypatch.setenv("CODEONBOARD_ALLOWED_ORIGINS", "http://localhost:3000")

    assert any("localhost" in p for p in auth_config.check())


def test_production_refuses_half_configured_google(monkeypatch):
    """A client id with no secret is a button that always fails.

    To a learner that reads as the product being broken rather than the
    deployment being incomplete.
    """
    monkeypatch.setenv("CODEONBOARD_ENV", "production")
    monkeypatch.setenv("CODEONBOARD_SECRET_KEY", "x")
    monkeypatch.setenv("CODEONBOARD_ALLOWED_ORIGINS", "https://app.example.com")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id")
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)

    assert any("half-configured" in p for p in auth_config.check())


def test_development_is_not_nagged(monkeypatch):
    """The checks must not make local development need a production setup."""
    monkeypatch.setenv("CODEONBOARD_ENV", "development")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.delenv("CODEONBOARD_SECRET_KEY", raising=False)

    assert auth_config.check() == []


# ── logging ───────────────────────────────────────────────────────────────────

def test_no_source_file_logs_a_password_or_a_token():
    """Checked structurally, because this is the kind of thing added in a hurry.

    A `logger.info` with a password in it survives code review far more easily
    than it survives a grep.
    """
    offenders = []
    # `password` and `secret_hash` are unambiguous, and `raw_token` is the name
    # the session token carries wherever it exists in plaintext.
    #
    # A bare `raw` and a bare `token` were in this list and produced only false
    # positives — the goal agent's `logger.error("… unparseable JSON: %s", raw)`
    # logs a model response, not a credential. A check that cries wolf gets
    # silenced, so it is narrower than it could be, on purpose.
    pattern = re.compile(
        r"log(?:ger)?\.\w+\([^)]*\b(password|secret_hash|raw_token)\b", re.I
    )
    for path in Path("backend").rglob("*.py"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if pattern.search(line):
                offenders.append(f"{path}:{number}: {line.strip()}")

    assert not offenders, "possible secret in a log line:\n  " + "\n  ".join(offenders)


def test_the_session_token_is_never_returned_in_a_body(client):
    """It belongs in a `Set-Cookie` and nowhere else.

    A token in a JSON body is one a script can read, which is the property
    HttpOnly exists to remove.
    """
    response = client.post(
        "/auth/register", json={"email": EMAIL, "password": PASSWORD}
    )

    raw = client.cookies.get(tokens.COOKIE_NAME)
    assert raw and raw not in response.text


# ── the console tools ─────────────────────────────────────────────────────────

def test_the_password_setter_has_no_http_surface():
    """Its entire safety is that it needs shell access to the machine."""
    for route in api.app.routes:
        module = getattr(getattr(route, "endpoint", None), "__module__", "") or ""
        assert "set_password" not in module
