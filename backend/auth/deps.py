"""FastAPI dependencies: who is calling, and which session they may touch.

Multi-user M2 ships `current_user` and `optional_user`. `owned_session` — the
chokepoint that makes ownership structural — arrives in M3, because there is
nothing to enforce until people can log in.

## The cookie is the only credential

No `Authorization: Bearer` fallback, deliberately. Two ways in means two code
paths to keep correct, and a header the browser can read is a header XSS can
steal — which is the property the HttpOnly cookie exists to have.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi import Depends, HTTPException, Request

from backend.auth import identity, tokens


@dataclass(frozen=True)
class CurrentUser:
    """The authenticated caller. Immutable — nothing downstream may edit it."""

    user_id: str
    email: str | None
    display_name: str | None

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "email": self.email,
            "display_name": self.display_name,
        }


def _db_path(request: Request) -> Path:
    """The database this request works against.

    Read from `backend.api.SESSIONS_DB_PATH` at CALL time rather than imported
    at module scope, because the test suite repoints that attribute at a temp
    file per test. A module-level import would bind the production path once and
    every auth test would quietly write to `data/sessions.db`.
    """
    from backend import api

    return api.SESSIONS_DB_PATH


def optional_user(request: Request) -> CurrentUser | None:
    """The caller, or None when they are not signed in. Never raises.

    For endpoints that behave differently when signed in but do not require it.
    """
    raw = request.cookies.get(tokens.COOKIE_NAME)
    db_path = _db_path(request)
    user_id = tokens.resolve(raw, db_path)
    if user_id is None:
        return None
    record = identity.get_user(user_id, db_path)
    if record is None or not record.get("is_active", 1):
        # The token resolved but the account is gone or deactivated. Treated as
        # not-signed-in rather than as an error: the legacy user is exactly this
        # shape, and a token for it must never authenticate anybody.
        return None
    return CurrentUser(
        user_id=record["user_id"],
        email=record.get("email"),
        display_name=record.get("display_name"),
    )


def current_user(
    user: CurrentUser | None = Depends(optional_user),
) -> CurrentUser:
    """The caller, or 401.

    One message for every way authentication can fail — absent cookie, unknown
    token, expired session, deactivated account. Distinguishing them would tell
    an attacker which of those they had achieved.
    """
    if user is None:
        raise HTTPException(status_code=401, detail="not_authenticated")
    return user
