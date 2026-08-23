"""Every route declares authentication, or is deliberately public (multi-user M3).

Run with: uv run pytest tests/test_route_authz_coverage.py -v

`tests/test_ownership.py` proves the routes that exist today are safe. This
proves the ones added TOMORROW cannot quietly not be.

It introspects `app.routes` rather than reading the source, so it sees what
FastAPI sees: a route whose handler pulls in `current_user` at any depth counts,
however it is spelled. A route that does not, and is not named below, fails the
build.

## Why an allow-list rather than a list of protected paths

A list of protected paths fails OPEN — forget an entry and the route is public,
and nothing says so. This fails CLOSED: a new route is a test failure until
somebody adds it to `PUBLIC` here, which is a line in a diff a reviewer sees and
has to think about. The cost of the mistake lands at the right moment.
"""
import pytest

import backend.api as api

# Paths that may be reached without authentication, each with the reason it is
# safe. Adding to this list should feel like a decision, because it is one.
PUBLIC = {
    "/auth/register":        "creating an account cannot require an account",
    "/auth/login":           "signing in cannot require being signed in already",
    "/auth/logout":          "idempotent, and refusing it would strand a client holding a dead cookie",
    "/openapi.json":         "schema only — every path here is still enforced",
    "/docs":                 "the Swagger page itself; its calls are enforced",
    "/docs/oauth2-redirect": "part of the Swagger page",
    "/redoc":                "rendered documentation only; every path it lists is still enforced",
    "/health":               "liveness only — returns a constant, reveals nothing about state",
}

# Names that count as declaring authentication.
AUTH_DEPENDENCIES = {"current_user", "optional_user", "owned_session", "owner_id"}


def _declares_auth(dependant) -> bool:
    if getattr(dependant.call, "__name__", "") in AUTH_DEPENDENCIES:
        return True
    return any(_declares_auth(sub) for sub in dependant.dependencies)


def _api_routes():
    return [
        route for route in api.app.routes
        if getattr(route, "dependant", None) is not None
    ]


def test_every_route_is_either_authenticated_or_deliberately_public():
    undeclared = [
        f"{sorted(route.methods)} {route.path}"
        for route in _api_routes()
        if route.path not in PUBLIC and not _declares_auth(route.dependant)
    ]

    assert not undeclared, (
        "These routes neither require authentication nor appear in PUBLIC:\n  "
        + "\n  ".join(undeclared)
        + "\n\nAdd `user: CurrentUser = Depends(current_user)` to the handler, or "
          "add the path to PUBLIC in this file with the reason it is safe."
    )


def test_every_session_route_is_authenticated():
    """The subset that matters most, asserted separately so the failure is louder.

    A session route without auth is not a missing feature — it is somebody
    else's learning history readable by anyone who guesses a URL.
    """
    unprotected = [
        f"{sorted(route.methods)} {route.path}"
        for route in _api_routes()
        if ("/session" in route.path) and not _declares_auth(route.dependant)
    ]

    assert not unprotected, "UNPROTECTED SESSION ROUTES:\n  " + "\n  ".join(unprotected)


def test_the_public_list_has_not_grown_stale():
    """Every entry in PUBLIC must correspond to a route that exists.

    A stale entry is a path that was renamed or removed while its exemption
    stayed behind — so the next route to take that path would be public without
    anybody deciding it should be.
    """
    live = {route.path for route in api.app.routes if hasattr(route, "path")}
    stale = sorted(set(PUBLIC) - live)

    assert not stale, f"PUBLIC names paths that no longer exist: {stale}"


def test_the_middleware_agrees_with_this_test():
    """Two implementations of one rule, checked against each other.

    `api._declares_auth` runs at request time; this file's copy runs here. They
    are deliberately separate — the middleware must not import test code — so
    this pins them together. If they drift, one of them is wrong about which
    routes are protected, and the drift would be silent.
    """
    for route in _api_routes():
        assert _declares_auth(route.dependant) == api._declares_auth(route.dependant), (
            f"disagreement about {route.path}"
        )


@pytest.mark.parametrize("path,reason", sorted(PUBLIC.items()))
def test_each_public_path_has_a_stated_reason(path, reason):
    """A path is not public because somebody needed it to be; it is public
    because it is safe, and the reason is written down."""
    assert reason and len(reason) > 15, f"{path} needs a real reason, not {reason!r}"
