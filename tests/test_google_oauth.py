"""Sign in with Google, and the linking rule that keeps it from being a takeover.

Run with: uv run pytest tests/test_google_oauth.py -v

Authlib is mocked at the token-exchange boundary: these tests are about what we
do with a VALIDATED profile, not about whether Authlib validates. Re-testing the
library's signature checking would be testing the library; what has to be right
here is the decision made afterwards, and that decision is ours.

## The case that shapes this file

D-5 ships no email verification of our own, so `users.email` is an unverified
claim. That makes the obvious linking rule an account takeover:

    an attacker registers a password account as victim@gmail.com;
    the victim later signs in with Google as victim@gmail.com;
    Google says `email_verified: true`, quite correctly;
    a naive rule links the victim's Google identity into the ATTACKER'S account.

`test_the_pre_hijack_attack_is_refused` is that scenario end to end. It is the
reason `/auth/google/link` exists at all.
"""
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.api as api
from backend.auth import google, identity, throttle, tokens

pytestmark = pytest.mark.real_auth

VICTIM = "victim@example.com"
PASSWORD = "a-long-enough-passphrase"
GOOGLE_SUB = "108374651234567890123"


@pytest.fixture(autouse=True)
def _isolation(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("CODEONBOARD_COOKIE_SECURE", "0")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("CODEONBOARD_SECRET_KEY", "test-flow-secret")
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


def _profile(sub=GOOGLE_SUB, email=VICTIM, verified=True, name="Victim"):
    return google.GoogleProfile(
        subject=sub, email=email, email_verified=verified, name=name
    )


def _register_password_account(client, email=VICTIM, password=PASSWORD):
    response = client.post("/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    return response.json()["user_id"]


def _drive_callback(client, monkeypatch, profile, *, state="s", nonce="n"):
    """Complete a callback with a pre-validated profile.

    The flow cookie is minted the way `/start` would, so the state check is
    exercised for real; only the token exchange is stubbed.
    """
    from backend.auth import google_routes

    class _Client:
        async def authorize_access_token(self, request):
            return {"userinfo": {"sub": profile.subject, "email": profile.email,
                                 "email_verified": profile.email_verified,
                                 "name": profile.name, "nonce": nonce}}

    monkeypatch.setattr(google_routes.google, "build_client", lambda: _Client())
    client.cookies.set(
        google.FLOW_COOKIE,
        google_routes._sign({"state": state, "nonce": nonce, "verifier": "v"}),
    )
    return client.get(
        f"/auth/google/callback?state={state}&code=abc", follow_redirects=False
    )


# ── the claims we act on ──────────────────────────────────────────────────────

def test_the_identity_key_is_sub_not_email(db):
    """Google emails can change; `sub` cannot.

    Keying on the email would make a person who changes their Google address a
    different user — losing their sessions — or, worse, inheriting somebody
    else's.
    """
    user_id = google.create_account(_profile(), db)

    moved = _profile(email="renamed@example.com")
    assert google.resolve(moved, db) == (user_id, None)


def test_an_unverified_email_is_refused(db):
    """D-4's condition. Google itself declines to stand behind the address."""
    with pytest.raises(ValueError, match="not verified"):
        google.resolve(_profile(verified=False), db)


def test_a_missing_verified_claim_is_treated_as_false(db):
    """Absent is not true. A claim we did not receive is not one to act on."""
    token = {"userinfo": {"sub": GOOGLE_SUB, "email": VICTIM, "name": "V"}}

    profile = google.profile_from_token(token)

    assert profile.email_verified is False


def test_a_token_with_no_subject_is_refused():
    with pytest.raises(ValueError, match="subject"):
        google.profile_from_token({"userinfo": {"email": VICTIM}})


# ── a brand-new account ───────────────────────────────────────────────────────

def test_a_new_google_user_gets_an_account_with_no_password(db):
    user_id = google.create_account(_profile(), db)

    identities = identity.identities_for(user_id, db)
    assert [i["provider"] for i in identities] == ["google"]
    with sqlite3.connect(db) as conn:
        secret = conn.execute(
            "SELECT secret_hash FROM auth_identities WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
    assert secret is None, "a federated identity has no secret of ours"


def test_a_google_only_account_cannot_be_signed_into_with_a_password(db, client):
    """`passwords.verify` treats a NULL secret as a miss, not an error."""
    google.create_account(_profile(), db)

    response = client.post(
        "/auth/login", json={"email": VICTIM, "password": PASSWORD}
    )

    assert response.status_code == 401


def test_signing_in_again_reuses_the_same_account(db, client, monkeypatch):
    first = _drive_callback(client, monkeypatch, _profile())
    assert first.status_code == 303
    client.cookies.clear()
    second = _drive_callback(client, monkeypatch, _profile())

    assert second.status_code == 303
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1


def test_a_successful_callback_lands_on_the_dashboard(client, monkeypatch):
    response = _drive_callback(client, monkeypatch, _profile())

    assert response.status_code == 303
    assert response.headers["location"] == "/sessions"
    assert client.get("/auth/me").status_code == 200


# ── D-7: the pre-hijack attack ────────────────────────────────────────────────

def test_the_pre_hijack_attack_is_refused(db, client, monkeypatch):
    """**The reason `/auth/google/link` exists.**

    An attacker holds a password account on an address they do not own. The real
    owner signs in with Google. Nothing may be linked on Google's word alone —
    it proves the EMAIL, not the ACCOUNT — or the victim's identity lands in the
    attacker's account and their sessions with it.
    """
    attacker_id = _register_password_account(client, VICTIM)
    client.cookies.clear()

    response = _drive_callback(client, monkeypatch, _profile())

    # Not signed in, and nothing linked.
    assert response.status_code == 303
    assert response.headers["location"] == "/login?link=google"
    assert identity.find_identity(identity.GOOGLE, GOOGLE_SUB, db) is None
    assert [i["provider"] for i in identity.identities_for(attacker_id, db)] == ["password"]


def test_the_link_completes_only_with_the_account_password(db, client, monkeypatch):
    user_id = _register_password_account(client, VICTIM)
    client.cookies.clear()
    _drive_callback(client, monkeypatch, _profile())

    wrong = client.post("/auth/google/link", json={"password": "not-the-password"})
    assert wrong.status_code == 401
    assert identity.find_identity(identity.GOOGLE, GOOGLE_SUB, db) is None

    right = client.post("/auth/google/link", json={"password": PASSWORD})
    assert right.status_code == 200
    linked = identity.find_identity(identity.GOOGLE, GOOGLE_SUB, db)
    assert linked is not None and linked["user_id"] == user_id


def test_linking_revokes_every_other_session(db, client, monkeypatch):
    """The second half of D-7, and not optional.

    Whoever was holding a token for this account before the real owner proved
    ownership should stop holding one.
    """
    _register_password_account(client, VICTIM)
    attacker_browser = TestClient(api.app)
    attacker_browser.post("/auth/login", json={"email": VICTIM, "password": PASSWORD})
    assert attacker_browser.get("/auth/me").status_code == 200

    client.cookies.clear()
    _drive_callback(client, monkeypatch, _profile())
    client.post("/auth/google/link", json={"password": PASSWORD})

    assert attacker_browser.get("/auth/me").status_code == 401


def test_the_linking_browser_ends_up_signed_in(client, monkeypatch):
    """Its session is issued AFTER the revocation, or it would be revoked too."""
    _register_password_account(client, VICTIM)
    client.cookies.clear()
    _drive_callback(client, monkeypatch, _profile())

    client.post("/auth/google/link", json={"password": PASSWORD})

    assert client.get("/auth/me").status_code == 200


def test_after_linking_both_methods_reach_one_account(db, client, monkeypatch):
    user_id = _register_password_account(client, VICTIM)
    client.cookies.clear()
    _drive_callback(client, monkeypatch, _profile())
    client.post("/auth/google/link", json={"password": PASSWORD})

    by_password = TestClient(api.app)
    by_password.post("/auth/login", json={"email": VICTIM, "password": PASSWORD})
    by_google = TestClient(api.app)
    _drive_callback(by_google, monkeypatch, _profile())

    assert by_password.get("/auth/me").json()["user_id"] == user_id
    assert by_google.get("/auth/me").json()["user_id"] == user_id
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1


def test_a_link_without_a_pending_flow_is_refused(client, monkeypatch):
    _register_password_account(client, VICTIM)

    assert client.post(
        "/auth/google/link", json={"password": PASSWORD}
    ).status_code == 400


def test_the_link_password_check_is_throttled(client, monkeypatch):
    """Otherwise it is a password oracle with a friendlier name."""
    _register_password_account(client, VICTIM)
    client.cookies.clear()
    _drive_callback(client, monkeypatch, _profile())

    codes = [
        client.post("/auth/google/link", json={"password": "wrong-one-here"}).status_code
        for _ in range(throttle.FREE_ATTEMPTS + 2)
    ]

    assert codes[0] == 401
    assert codes[-1] == 429


# ── the flow's own integrity ──────────────────────────────────────────────────

def test_a_callback_with_no_flow_cookie_is_refused(client, monkeypatch):
    from backend.auth import google_routes

    monkeypatch.setattr(google_routes.google, "build_client", lambda: None)

    response = client.get("/auth/google/callback?state=s&code=abc", follow_redirects=False)

    assert response.status_code == 303
    assert "oauth_state" in response.headers["location"]


def test_a_mismatched_state_is_refused(client, monkeypatch):
    """CSRF on the callback.

    Without this an attacker can complete the flow in a victim's browser with
    the attacker's own code, silently signing the victim into the attacker's
    account.
    """
    response = _drive_callback(client, monkeypatch, _profile(), state="mine")
    assert response.status_code == 303
    client.cookies.clear()

    from backend.auth import google_routes
    client.cookies.set(
        google.FLOW_COOKIE,
        google_routes._sign({"state": "mine", "nonce": "n", "verifier": "v"}),
    )
    forged = client.get(
        "/auth/google/callback?state=theirs&code=abc", follow_redirects=False
    )

    assert "oauth_state" in forged.headers["location"]


def test_a_tampered_flow_cookie_is_refused(client):
    from backend.auth import google_routes

    signed = google_routes._sign({"state": "s", "nonce": "n"})
    raw, mac = signed.rsplit(".", 1)
    client.cookies.set(google.FLOW_COOKIE, f"{raw}.{'0' * len(mac)}")

    response = client.get(
        "/auth/google/callback?state=s&code=abc", follow_redirects=False
    )

    assert "oauth_state" in response.headers["location"]


def test_an_unverified_email_lands_on_a_readable_error(client, monkeypatch):
    response = _drive_callback(client, monkeypatch, _profile(verified=False))

    assert response.status_code == 303
    assert "oauth_unverified" in response.headers["location"]


def test_start_sends_you_back_when_google_is_not_configured(client, monkeypatch):
    """A browser navigation must not end on a JSON body.

    This route is only ever reached by a full page navigation, so `503
    {"detail": "google_not_configured"}` put a raw JSON object on a blank tab
    with no way back — which is what a learner actually saw. It goes back to the
    sign-in page with a reason the page can render.
    """
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)

    response = client.get("/auth/google/start", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login?error=google_not_configured"


def test_the_providers_endpoint_is_readable_before_signing_in(client, monkeypatch):
    """The sign-in page has to know BEFORE anybody is authenticated.

    Otherwise it can only offer the button and hope — and an unconfigured server
    turns that hope into an error page.
    """
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)

    response = client.get("/auth/providers")

    assert response.status_code == 200
    assert response.json() == {"password": True, "google": False}


def test_the_providers_endpoint_reports_google_once_configured(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")

    assert client.get("/auth/providers").json()["google"] is True


# ── unlinking ─────────────────────────────────────────────────────────────────

def test_google_can_be_unlinked_when_a_password_remains(db, client, monkeypatch):
    _register_password_account(client, VICTIM)
    client.cookies.clear()
    _drive_callback(client, monkeypatch, _profile())
    client.post("/auth/google/link", json={"password": PASSWORD})

    assert client.delete("/auth/identities/google").status_code == 204
    assert identity.find_identity(identity.GOOGLE, GOOGLE_SUB, db) is None


def test_the_last_identity_cannot_be_unlinked(db, client, monkeypatch):
    """With no password reset (D-5), an account with no identities is one nobody
    can ever open again — and its sessions go with it."""
    _drive_callback(client, monkeypatch, _profile())

    response = client.delete("/auth/identities/google")

    assert response.status_code == 409
    assert response.json()["detail"] == "last_identity"


def test_the_identities_endpoint_lists_how_you_can_sign_in(client, monkeypatch):
    _register_password_account(client, VICTIM)

    body = client.get("/auth/identities").json()

    assert [i["provider"] for i in body["identities"]] == ["password"]
    assert body["google_configured"] is True
