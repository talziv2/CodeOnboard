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


def owned_session(session_id: str, user: CurrentUser = Depends(current_user)):
    """The caller's session, or 404 — the chokepoint every session route uses.

    ## Why this is a dependency and not a helper the routes call

    A helper can be forgotten. A dependency is declared in the signature, which
    means `tests/test_route_authz_coverage.py` can enumerate `app.routes` and
    fail the build when a new session route does not have one. Three layers hold
    invariant I2 up, and each catches what the others miss:

      1. `store.load_graph` REQUIRES a `user_id`, so no code path anywhere can
         produce a `LearningGraph` without naming an owner;
      2. this dependency, so the routes get it right ergonomically;
      3. the coverage test, so a route added later cannot quietly skip both.

    ## 404, never 403

    A 403 says "this exists but is not yours", which is a working oracle for
    which session ids are real. The store's `WHERE user_id = ?` gives the right
    answer for free: a foreign session simply returns no row, and is
    indistinguishable from one that never existed (I6).
    """
    from backend.learning import store as learning_store

    graph = learning_store.load_graph(session_id, user.user_id, _db_path_for(user))
    if graph is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    return graph


def _db_path_for(_user: CurrentUser) -> Path:
    """The database this request works against.

    Read from `backend.api.SESSIONS_DB_PATH` at CALL time — the test suite
    repoints that attribute per test, and a module-level import would bind the
    production path once and quietly write there instead.
    """
    from backend import api

    return api.SESSIONS_DB_PATH


def owner_id(user: CurrentUser = Depends(current_user)) -> str:
    """Just the id, for routes that write rather than read a graph."""
    return user.user_id
