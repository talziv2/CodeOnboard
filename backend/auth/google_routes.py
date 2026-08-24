"""`/auth/google/*` — the Google sign-in flow (multi-user M6, D-4 + D-7).

Its own module rather than more of `routes.py`, because the linking rule needs
about as much explanation as password auth does and burying it under three
hundred lines of that would hide the one decision here that is genuinely
dangerous to get wrong.

Everything cryptographic is Authlib's: the ID token's signature, issuer,
audience, expiry and nonce are validated against Google's published keys before
any claim in it is read. We never accept a token from the browser — it carries a
one-time code, and the exchange is server-to-server.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets as _secrets
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from backend.auth import google, identity, passwords, tokens
from backend.auth.deps import CurrentUser, current_user
from backend.auth.routes import (
    UserOut, _INVALID, _db_path, _forgive, _guard, _penalise, _secure_cookies,
    _set_cookie,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth/google", tags=["auth"])

_EPHEMERAL_SECRET: str | None = None


def _flow_secret() -> str:
    """The key the short-lived flow cookie is signed with.

    Falls back to a per-process random value when `CODEONBOARD_SECRET_KEY` is
    unset, which means a restart mid-flow invalidates the flow — the safe
    direction for something that lives ten minutes. Refusing to start over a
    missing secret would make local development need one for a feature most runs
    never touch; M8's startup check requires it where it matters.
    """
    global _EPHEMERAL_SECRET
    configured = os.environ.get("CODEONBOARD_SECRET_KEY")
    if configured:
        return configured
    if _EPHEMERAL_SECRET is None:
        _EPHEMERAL_SECRET = _secrets.token_urlsafe(32)
        logger.warning(
            "CODEONBOARD_SECRET_KEY is not set; using a per-process value. "
            "Google sign-in flows will not survive a restart."
        )
    return _EPHEMERAL_SECRET


def _sign(payload: dict) -> str:
    raw = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    mac = hmac.new(_flow_secret().encode(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{mac}"


def _read(value: str | None) -> dict | None:
    """The flow payload, or None if it is not ours or was tampered with.

    `compare_digest` rather than `==`: a comparison that short-circuits on the
    first wrong byte leaks how much of a forged signature was right.
    """
    if not value or "." not in value:
        return None
    raw, mac = value.rsplit(".", 1)
    expected = hmac.new(_flow_secret().encode(), raw.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, expected):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(raw.encode()))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _set_flow(response: Response, payload: dict) -> None:
    response.set_cookie(
        google.FLOW_COOKIE, _sign(payload),
        max_age=google.FLOW_TTL_SECONDS, httponly=True, samesite="lax",
        secure=_secure_cookies(), path="/",
    )


def _back_to(path: str) -> RedirectResponse:
    """Relative, always.

    The app is same-origin behind the Next rewrite (D-2), so a relative path is
    both correct and impossible to turn into an open redirect by anything Google
    or a caller sends.
    """
    return RedirectResponse(path, status_code=303)


@router.get("/start")
async def google_start(request: Request) -> Response:
    """Begin the flow. Redirects to Google — or back to the sign-in page.

    THIS ROUTE IS ONLY EVER A FULL BROWSER NAVIGATION, never an XHR: the browser
    has to follow Google's redirect, and a fetch cannot. So an error here must be
    something a person can read on a page, not a JSON body.

    Returning `503 {"detail": "google_not_configured"}` put exactly that in front
    of a learner — a raw JSON object on a blank tab, with no way back. The status
    was right and the medium was wrong. It redirects to the sign-in page with a
    readable reason instead, which is also where they were trying to get to.
    """
    if not google.is_configured():
        return _back_to("/login?error=google_not_configured")

    flow = google.new_flow_state()
    client = google.build_client()
    redirect_uri = str(request.url_for("google_callback"))
    response = await client.authorize_redirect(
        request, redirect_uri, state=flow["state"], nonce=flow["nonce"]
    )
    # `state` defeats CSRF on the callback: without it an attacker can complete
    # the flow in a victim's browser with their own code, silently signing the
    # victim into the ATTACKER'S account. `nonce` is bound into the ID token by
    # Google, so a token minted for another request cannot be replayed here.
    _set_flow(response, flow)
    return response


@router.get("/callback", name="google_callback")
async def google_callback(request: Request) -> Response:
    db_path = _db_path()
    flow = _read(request.cookies.get(google.FLOW_COOKIE))
    if flow is None or request.query_params.get("state") != flow.get("state"):
        # No flow cookie, one we did not sign, or a state that does not match:
        # the flow expired, or somebody is replaying a callback into this
        # browser. Both are refusals, and neither says which.
        return _back_to("/login?error=oauth_state")

    try:
        client = google.build_client()
        token = await client.authorize_access_token(request)
        profile = google.profile_from_token(token)
    except Exception as exc:                       # noqa: BLE001
        logger.warning("google callback failed: %s", exc)
        return _back_to("/login?error=oauth_failed")

    try:
        user_id, needs_password_for = google.resolve(profile, db_path)
    except ValueError as exc:
        logger.info("google refused: %s", exc)
        return _back_to("/login?error=oauth_unverified")

    if needs_password_for is not None:
        # D-7. The verified email proves they own the ADDRESS. The password will
        # prove they own the ACCOUNT. Nothing is linked until both are in hand —
        # see `google.py` for the pre-hijacking attack this closes.
        response = _back_to("/login?link=google")
        _set_flow(response, {
            "link_user_id": needs_password_for,
            "subject": profile.subject,
            "email": profile.email,
            "name": profile.name,
        })
        return response

    if user_id is None:
        user_id = google.create_account(profile, db_path)

    identity.touch_login(user_id, db_path)
    raw = tokens.issue(
        user_id, user_agent=request.headers.get("user-agent"), db_path=db_path
    )
    response = _back_to("/sessions")
    _set_cookie(response, raw)
    response.delete_cookie(google.FLOW_COOKIE, path="/")
    return response


class GoogleLinkRequest(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


@router.post("/link", response_model=UserOut)
def google_link(
    body: GoogleLinkRequest, request: Request, response: Response
) -> UserOut:
    """Confirm the password, then link the pending Google identity (D-7).

    On success every OTHER session for that account is revoked, so an attacker
    already holding a token is ejected at the moment the real owner proves
    ownership. This browser's new session is issued AFTER that revocation —
    issuing it first would revoke it along with the rest.
    """
    db_path = _db_path()
    pending = _read(request.cookies.get(google.FLOW_COOKIE))
    if not pending or not pending.get("link_user_id"):
        raise HTTPException(status_code=400, detail="no_pending_link")

    user = identity.get_user(pending["link_user_id"], db_path)
    if user is None or not user.get("is_active", 1):
        raise HTTPException(status_code=400, detail="no_pending_link")

    account_key = user.get("email") or user["user_id"]
    _guard(request, account_key)
    record = identity.find_identity(identity.PASSWORD, account_key, db_path)
    if record is None or not passwords.verify(record["secret_hash"], body.password):
        # Throttled exactly like a login, because that is what it is. An
        # unlimited version of this is a password oracle with a friendlier name.
        _penalise(request, account_key)
        raise HTTPException(status_code=401, detail=_INVALID)

    _forgive(request, account_key)
    google.link_to(
        user["user_id"],
        google.GoogleProfile(
            subject=pending["subject"], email=pending.get("email"),
            email_verified=True, name=pending.get("name"),
        ),
        db_path,
    )
    raw = tokens.issue(
        user["user_id"], user_agent=request.headers.get("user-agent"), db_path=db_path
    )
    _set_cookie(response, raw)
    response.delete_cookie(google.FLOW_COOKIE, path="/")
    identity.touch_login(user["user_id"], db_path)
    return UserOut(
        user_id=user["user_id"], email=user.get("email"),
        display_name=user.get("display_name"),
    )


identities_router = APIRouter(prefix="/auth", tags=["auth"])


@identities_router.get("/providers")
def list_providers() -> dict:
    """Which ways of signing in this server actually offers.

    Public, and deliberately: the sign-in page has to read it BEFORE anybody is
    signed in, which is the whole point. It reveals only whether Google is
    configured on this deployment — not a fact about any person, and one anybody
    could discover by clicking the button.

    Without it the page could only offer the button and hope, which is how a
    learner ends up looking at `{"detail":"google_not_configured"}`.
    """
    return {"password": True, "google": google.is_configured()}


@identities_router.get("/identities")
def list_identities(user: CurrentUser = Depends(current_user)) -> dict:
    """How this account can be signed into. For the settings screen."""
    return {
        "identities": [
            {"provider": i["provider"], "created_at": i["created_at"]}
            for i in identity.identities_for(user.user_id, _db_path())
        ],
        "google_configured": google.is_configured(),
    }


@identities_router.delete("/identities/google", status_code=204)
def unlink_google(
    response: Response, user: CurrentUser = Depends(current_user)
) -> Response:
    """Disconnect Google — unless it is the only way in.

    With no password reset (D-5), an account with no identities is one nobody
    can ever open again, and its sessions go with it. Refusing the last one is
    the difference between a setting and a trapdoor.
    """
    if not google.unlink(user.user_id, _db_path()):
        raise HTTPException(status_code=409, detail="last_identity")
    response.status_code = 204
    return response
