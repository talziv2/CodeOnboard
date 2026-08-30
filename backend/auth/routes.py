"""`/auth/*` — register, log in, log out, and say who is calling.

Multi-user M2. Password only; Google arrives in M6 and adds routes beside these
rather than changing them.

## The cookie

`HttpOnly` so no script can read it — including a script that got in through the
markdown renderer, which is the realistic XSS surface in this app.
`SameSite=Lax` because the Next.js `/api/*` rewrite (D-2) makes every request
first-party, so there is no cross-site case to allow. `Secure` whenever the
deployment is not plain-http localhost.

## What the responses deliberately do not say

Registration with a taken email and login with a wrong password both return the
same shape of refusal they would for any other failure. Distinguishing them turns
either form into an account-enumeration oracle: "is this person a user here" is
not a question an anonymous caller should be able to ask.

That is [OPEN-3]'s recommended answer, implemented rather than left pending
because M2 could not ship without choosing one. It is reversible in one place —
`_TAKEN` below — if the UX cost is judged too high.

## Password reset

`/forgot` and `/reset` are here too, and they are **development-grade on
purpose**: nothing mails the link. Outside production `/forgot` returns it, which
is the whole delivery mechanism; in production it returns nothing and the flow is
inert. `backend/auth/reset.py` states the limitation and why it is not closed
here. `scripts/set_password.py` remains the recovery path that is safe anywhere.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from backend.auth import config, identity, passwords, reset, throttle, tokens
from backend.auth.deps import CurrentUser, current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


# One message for both halves of a failed login, and for a registration whose
# email is taken. See the module docstring.
_INVALID = "Email or password is incorrect."
_TAKEN = "That email cannot be used to register."


def _db_path() -> Path:
    from backend import api

    return api.SESSIONS_DB_PATH


def _secure_cookies() -> bool:
    """Whether to set `Secure`, which makes the cookie https-only.

    Defaults ON and is turned off explicitly for local http development. That
    direction matters: a missing flag in production is a cookie sent in clear,
    and a wrong default should fail in the safe direction — visibly broken on
    plain http rather than silently insecure over the internet.
    """
    return os.environ.get("CODEONBOARD_COOKIE_SECURE", "1") != "0"


def _set_cookie(response: Response, raw: str) -> None:
    response.set_cookie(
        key=tokens.COOKIE_NAME,
        value=raw,
        httponly=True,
        samesite="lax",
        secure=_secure_cookies(),
        path="/",
        max_age=tokens.IDLE_DAYS * 24 * 60 * 60,
    )


def _clear_cookie(response: Response) -> None:
    # Same attributes as when it was set — a browser matches on path and
    # security attributes, so a mismatched delete silently leaves the cookie in
    # place and the learner stays "logged in" until it expires.
    response.delete_cookie(
        key=tokens.COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=_secure_cookies(),
    )


def _client_ip(request: Request) -> str:
    """The address to throttle on.

    `X-Forwarded-For` is honoured only when a proxy is declared, because a
    header the client controls is otherwise a throttle bypass: an attacker would
    simply vary it. With no declared proxy the socket address is the only thing
    that cannot be forged.
    """
    if os.environ.get("CODEONBOARD_TRUST_PROXY") == "1":
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _refuse_if_locked(wait: float) -> None:
    if wait > 0:
        raise HTTPException(
            status_code=429,
            detail="too_many_attempts",
            headers={"Retry-After": str(int(wait) + 1)},
        )


def _guard(request: Request, account_key: str) -> None:
    """Refuse early when this IP or this account is locked out."""
    ip = _client_ip(request)
    _refuse_if_locked(max(
        throttle.by_ip.retry_after(f"ip:{ip}"),
        throttle.by_account.retry_after(f"acct:{account_key}"),
    ))


def _guard_ip(request: Request) -> None:
    """Per-IP only, for `/reset` — which has no account to key on.

    The account is not known until the token resolves, and keying on a constant
    instead would let five bad guesses lock every reset in the deployment: a
    denial of service handed to an anonymous caller. Per-IP is what actually
    bounds token guessing, and the token itself is 256 bits.
    """
    _refuse_if_locked(throttle.by_ip.retry_after(f"ip:{_client_ip(request)}"))


def _penalise_ip(request: Request) -> None:
    throttle.by_ip.record_failure(f"ip:{_client_ip(request)}")


def _penalise(request: Request, account_key: str) -> None:
    throttle.by_ip.record_failure(f"ip:{_client_ip(request)}")
    throttle.by_account.record_failure(f"acct:{account_key}")


def _forgive(request: Request, account_key: str) -> None:
    throttle.by_ip.record_success(f"ip:{_client_ip(request)}")
    throttle.by_account.record_success(f"acct:{account_key}")


class RegisterRequest(BaseModel):
    # `str`, not pydantic's `EmailStr`, which would pull in `email-validator`
    # for a precision this system cannot use: nothing here ever sends mail
    # (D-5 ships no verification, and `/forgot` hands its link to the caller
    # rather than mailing it), so the address is contact information rather than
    # an endpoint. `identity.validate_email` does the shape check.
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)
    display_name: str | None = Field(default=None, max_length=80)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class UserOut(BaseModel):
    user_id: str
    email: str | None
    display_name: str | None


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: RegisterRequest, request: Request, response: Response) -> UserOut:
    db_path = _db_path()
    try:
        email = identity.validate_email(body.email)
    except identity.InvalidEmailError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _guard(request, email)

    try:
        passwords.validate(body.password)
    except passwords.WeakPasswordError as exc:
        # NOT throttled and NOT generic: this is the caller's own password being
        # judged, so it reveals nothing about anyone else and the person needs to
        # know what to fix.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    secret = passwords.hash_password(body.password)
    user_id = None
    try:
        user_id = identity.create_user(
            email, (body.display_name or "").strip() or None, db_path=db_path
        )
        identity.add_identity(
            user_id, identity.PASSWORD, email, secret_hash=secret, db_path=db_path
        )
    except sqlite3.IntegrityError as exc:
        # The email or the identity is taken. Both unique constraints land here,
        # and both mean the same thing to the caller.
        #
        # THE USER ROW IS CLEANED UP if it was created before the identity insert
        # failed. Without this a collision on the identity would leave an account
        # with no way to sign in — and, worse, one holding the email, so the
        # retry would fail on the user insert instead and the address would be
        # permanently unusable.
        if user_id is not None:
            _delete_user_if_identityless(user_id, db_path)
        _penalise(request, email)
        raise HTTPException(status_code=409, detail=_TAKEN) from exc

    _forgive(request, email)
    identity.touch_login(user_id, db_path)
    raw = tokens.issue(
        user_id, user_agent=request.headers.get("user-agent"), db_path=db_path
    )
    _set_cookie(response, raw)
    logger.info("registered user=%s", user_id)
    return UserOut(user_id=user_id, email=email,
                   display_name=(body.display_name or "").strip() or None)


def _delete_user_if_identityless(user_id: str, db_path: Path) -> None:
    from backend.learning.store import _connect

    with _connect(db_path) as conn:
        has_identity = conn.execute(
            "SELECT 1 FROM auth_identities WHERE user_id = ? LIMIT 1", (user_id,)
        ).fetchone()
        if has_identity is None:
            conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))


@router.post("/login", response_model=UserOut)
def login(body: LoginRequest, request: Request, response: Response) -> UserOut:
    db_path = _db_path()
    # Normalised but NOT shape-validated: a malformed address at login is simply
    # an address that matches no identity, and rejecting it with a different
    # status would tell an attacker which strings are even candidates.
    email = identity.normalize_email(body.email)
    _guard(request, email)

    record = identity.find_identity(identity.PASSWORD, email, db_path)
    if record is None:
        # BOTH BRANCHES MUST COST THE SAME. Without this the miss returns in
        # microseconds while a wrong password takes the ~50ms Argon2 is tuned
        # to, and that gap is a reliable account-enumeration oracle however
        # carefully the two responses are worded.
        passwords.verify_dummy()
        _penalise(request, email)
        raise HTTPException(status_code=401, detail=_INVALID)

    if not passwords.verify(record["secret_hash"], body.password):
        _penalise(request, email)
        raise HTTPException(status_code=401, detail=_INVALID)

    user = identity.get_user(record["user_id"], db_path)
    if user is None or not user.get("is_active", 1):
        # A deactivated account — the legacy owner is exactly this shape, and it
        # has no password identity, so this is belt to that brace.
        _penalise(request, email)
        raise HTTPException(status_code=401, detail=_INVALID)

    # The plaintext is in hand and correct: the one moment a stronger hash can be
    # made. Raising the Argon2 parameters later upgrades accounts as people
    # return, with no migration and no forced reset.
    if passwords.needs_rehash(record["secret_hash"]):
        identity.set_password_hash(
            record["user_id"], email, passwords.hash_password(body.password), db_path
        )

    _forgive(request, email)
    identity.touch_login(user["user_id"], db_path)
    raw = tokens.issue(
        user["user_id"], user_agent=request.headers.get("user-agent"), db_path=db_path
    )
    _set_cookie(response, raw)
    logger.info("login user=%s", user["user_id"])
    return UserOut(
        user_id=user["user_id"],
        email=user.get("email"),
        display_name=user.get("display_name"),
    )


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response) -> Response:
    """End this session. Idempotent, and never an error.

    204 whether or not a session was found: "log me out" cannot fail from the
    caller's point of view, and a 401 here would leave a confused client holding
    a cookie it has already been told to forget.
    """
    tokens.revoke(request.cookies.get(tokens.COOKIE_NAME), _db_path())
    _clear_cookie(response)
    response.status_code = 204
    return response


@router.post("/logout/all", status_code=204)
def logout_all(
    request: Request, response: Response, user: CurrentUser = Depends(current_user)
) -> Response:
    """End every session this user holds, on every device.

    Requires authentication, unlike `/logout`: it acts on an account rather than
    on the token in hand, so the caller has to prove which account.
    """
    ended = tokens.revoke_all(user.user_id, _db_path())
    _clear_cookie(response)
    logger.info("logout-all user=%s sessions=%d", user.user_id, ended)
    response.status_code = 204
    return response


# ── password reset (development-grade — see `backend/auth/reset.py`) ──────────

class ForgotRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class ForgotResponse(BaseModel):
    """`reset_url` is populated only outside production.

    One response model for both cases rather than two status codes, so the
    production shape is identical whether or not the address has an account —
    the enumeration rule that governs `/login` governs this too.
    """

    reset_url: str | None = None


def _reset_link(raw: str) -> str:
    """The URL a person opens to finish the reset.

    Built against the app's first allowed origin — the Next dev server — because
    the reset PAGE is served by Next while this endpoint is served by FastAPI, so
    `request.base_url` would point at the API and produce a link to nothing.
    """
    from backend import api

    origin = api.ALLOWED_ORIGINS[0] if api.ALLOWED_ORIGINS else ""
    return f"{origin}/reset-password?token={raw}"


@router.post("/forgot", response_model=ForgotResponse)
def forgot_password(body: ForgotRequest, request: Request) -> ForgotResponse:
    """Begin a password reset. Always 200, and never says whether the email exists.

    Normalised but NOT shape-validated, for the same reason as `/login`: a
    malformed address is simply one that matches no identity, and a different
    status for it would tell an attacker which strings are candidates.
    """
    db_path = _db_path()
    email = identity.normalize_email(body.email)
    _guard(request, email)

    record = identity.find_identity(identity.PASSWORD, email, db_path)
    if record is None or not record["secret_hash"]:
        # Two cases, one answer: no identity at all, or a federated one. A Google
        # row keeps no secret of ours, so there is nothing to replace — and
        # creating a password for it here would be identity LINKING, which D-7
        # deliberately costs a password confirmation. Neither is a reset.
        _penalise(request, email)
        logger.info("reset requested for an address that cannot be reset")
        return ForgotResponse()

    raw = reset.create(record["user_id"], email, db_path=db_path)
    _forgive(request, email)

    if not config.reveals_reset_link():
        # Production. The token exists and is unreachable: nothing mails it and
        # nothing here will say it, so the endpoint is inert. Logged WITHOUT the
        # token, so an operator can still see that somebody is locked out.
        logger.warning(
            "password reset requested user=%s — no delivery configured, "
            "use scripts/set_password.py",
            record["user_id"],
        )
        return ForgotResponse()

    link = _reset_link(raw)
    # WARNING, not INFO: this is a live credential on stdout. The line should
    # look like the compromise it would be anywhere but a development machine.
    logger.warning(
        "PASSWORD RESET LINK (development only) user=%s %s", record["user_id"], link
    )
    return ForgotResponse(reset_url=link)


class ResetRequest(BaseModel):
    token: str = Field(min_length=1, max_length=512)
    password: str = Field(min_length=1, max_length=1024)


@router.post("/reset", response_model=UserOut)
def reset_password(
    body: ResetRequest, request: Request, response: Response
) -> UserOut:
    """Spend a reset token, set the new password, and sign this browser in.

    The order of the last three steps is load-bearing: replace the hash, revoke
    EVERY existing session, then issue one. Revoking after issuing would kill the
    session just created; not revoking at all would preserve exactly the access
    the reset exists to close, since a password is reset by someone who believes
    the old one is known to somebody else. Same reasoning as `set_password.py`.
    """
    db_path = _db_path()
    _guard_ip(request)

    try:
        passwords.validate(body.password)
    except passwords.WeakPasswordError as exc:
        # Checked BEFORE the token is spent, so a rejected password leaves the
        # link usable. Spending it on a typo would send the learner back to
        # `/forgot` for a new one, which is a bad enough experience that people
        # would reach for a weaker password to avoid repeating it.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    claim = reset.consume(body.token, db_path)
    if claim is None:
        # Unknown, already used, or expired — one refusal for all three.
        _penalise_ip(request)
        raise HTTPException(status_code=401, detail="invalid_reset_token")

    user = identity.get_user(claim["user_id"], db_path)
    if user is None or not user.get("is_active", 1):
        # Deactivated between issue and use. The token is already spent, which is
        # the safe direction.
        raise HTTPException(status_code=401, detail="invalid_reset_token")

    identity.set_password_hash(
        claim["user_id"], claim["subject"], passwords.hash_password(body.password),
        db_path,
    )
    tokens.revoke_all(claim["user_id"], db_path)

    identity.touch_login(user["user_id"], db_path)
    raw = tokens.issue(
        user["user_id"], user_agent=request.headers.get("user-agent"), db_path=db_path
    )
    _set_cookie(response, raw)
    logger.info("reset completed user=%s", user["user_id"])
    return UserOut(
        user_id=user["user_id"],
        email=user.get("email"),
        display_name=user.get("display_name"),
    )


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser = Depends(current_user)) -> UserOut:
    """Who is calling. The frontend's whole auth model is one call to this."""
    return UserOut(**user.to_dict())
