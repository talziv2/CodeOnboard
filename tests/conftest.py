"""Suite-wide isolation from the developer's own environment.

## The bug this exists to prevent

`tests/test_mentor_dossier.py` failed 14 of its tests on any full-suite run and
passed every one of them in isolation. The cause was three steps long:

1. `backend/api.py` calls `load_dotenv(override=True)` **at import time**;
2. the developer's `.env` carries `CODEONBOARD_CURRICULUM=1` for manual E2E runs;
3. so importing `backend.api` — which eleven test files do, directly or through
   `tests.test_session_api` — silently switched the Mentor to the objective-first
   planner for every test that ran afterwards.

`test_mentor_dossier.py` exercises the *pre-B3* planner and pinned nothing, so it
got the curriculum planner, its scripted wire failed validation, `state.graph`
came back `None`, and fourteen assertions died on `NoneType has no attribute
'nodes'`. Its sibling `test_curriculum_planner.py` had always pinned the flag
explicitly, which is why only one of the pair broke.

## Why this is the fix, rather than one more fixture in one more file

The failure was not really about that flag or that file. It was that **an ambient
value decided which code path ran**, and nothing in the suite said so. Pinning the
flag in `test_mentor_dossier.py` would have fixed those fourteen tests and left the
next flag, and the next file, to be discovered the same way — by a full run
disagreeing with a single-file run, which is the most expensive way to learn it.

So flags are neutralised for **every** test here. A test that depends on one has to
say which and how, and the ones that already do keep working untouched: an autouse
fixture in a module or a `monkeypatch.setenv` in a test body both run after this
one (conftest fixtures are ordered outermost-first), so they set the value they
want over a known-empty starting point rather than over whatever the machine had.

This does not touch `load_dotenv(override=True)` itself. That is a separate and
real footgun — with `override=True` a stale `.env` beats a variable set on the
command line, so `CODEONBOARD_GAPS=0 uv run uvicorn …` can silently run with gaps
on — but changing environment precedence changes how the app is *run*, not how it
is tested, and it is the developer's call rather than a side effect of a test fix.
Recorded rather than done.
"""
import pytest


# Every flag the backend reads from the environment. Listed rather than pattern
# matched, so adding one is a decision someone makes here on purpose.
#
# Note what "neutralised" means here, because it is not "off". It means UNSET, so
# each flag falls to the default the repository ships — `0` for the first two, and
# `1` for `CODEONBOARD_TUTOR`, which defaults ON. That is deliberate: the suite
# should exercise the configuration a fresh clone actually runs, not a fourth
# configuration that exists only in tests.
#
# `CODEONBOARD_TUTOR` was added to this tuple when its default flipped. Before
# that it was absent, which was a latent version of the very bug this file exists
# to prevent: a developer `.env` carrying `CODEONBOARD_TUTOR=1` turned the Tutor
# routes on for every test that imported `backend.api`, and nothing in the suite
# said so. It is now pinned like the others, so the flag's value in a test is
# either the shipped default or something the test asked for out loud.
AMBIENT_FLAGS = (
    "CODEONBOARD_CURRICULUM",
    "CODEONBOARD_GAPS",
    "CODEONBOARD_TUTOR",
)


@pytest.fixture(autouse=True)
def _neutral_flags(monkeypatch):
    """Start every test with the flags unset, whatever the machine has.

    Unset, not off — each flag then reads its shipped default. `raising=False`
    because unset is the normal case: this is about guaranteeing a known starting
    point, not about asserting one existed.
    """
    for flag in AMBIENT_FLAGS:
        monkeypatch.delenv(flag, raising=False)


# ── authentication, for the suites that predate it (multi-user M3) ────────────
#
# Sixteen test files drive session routes through `TestClient`, and every one of
# those routes now requires a signed-in caller. Rather than teach all sixteen to
# register and carry a cookie — which would bury what each is actually testing —
# every test runs as ONE fixed user by default.
#
# This is a real user id threaded through the real ownership checks, not a bypass:
# `load_graph` still filters on it, `save_graph` still stamps it, and a session
# created by one of these tests genuinely belongs to `TEST_USER_ID`. What is
# stubbed is only the COOKIE→user step, which `tests/test_auth.py` covers for
# real.
#
# A module opts out with `pytestmark = pytest.mark.real_auth` when it needs to
# exercise authentication itself — `test_auth.py` and `test_ownership.py` both do.
TEST_USER_ID = "test-user-00000000000000000000000"
TEST_USER_EMAIL = "test-user@codeonboard.local"


@pytest.fixture(autouse=True)
def _signed_in(request):
    """Run every test as one fixed user, unless it opts out.

    `dependency_overrides` ONLY — no `monkeypatch.setattr` on the module. The
    overrides dict is keyed on the ORIGINAL function object that the routes
    captured at import, so rebinding `deps.current_user` first makes the key a
    different object and the override silently never matches. That was the first
    version of this fixture, and it presented as every route returning 401.
    """
    if request.node.get_closest_marker("real_auth"):
        yield
        return

    import backend.api as api
    from backend.auth import deps

    user = deps.CurrentUser(
        user_id=TEST_USER_ID, email=TEST_USER_EMAIL, display_name="Test User"
    )
    previous = api.app.dependency_overrides.copy()
    api.app.dependency_overrides[deps.current_user] = lambda: user
    api.app.dependency_overrides[deps.optional_user] = lambda: user

    # `session_drafts.user_id` has a real foreign key to `users`, so the
    # stand-in caller needs a real row. Ensured lazily, at the moment a draft is
    # created, because the database path is set by each test's own fixture and
    # is not known when this one runs. In production the row always exists —
    # registration creates it before anything can be drafted.
    from backend.auth import drafts, identity

    original_create = drafts.create

    def create_with_user(user_id, repo_url, db_path=None, **kwargs):
        target = db_path if db_path is not None else api.SESSIONS_DB_PATH
        identity.ensure_user_row(user_id, TEST_USER_EMAIL, target)
        return original_create(user_id, repo_url, target, **kwargs)

    drafts.create = create_with_user
    try:
        yield
    finally:
        drafts.create = original_create
        api.app.dependency_overrides = previous


def start_session(client, repo_url: str, goal: dict, **extra) -> dict:
    """Start a session and return the shape `/session/start` used to return.

    ## Why this exists

    M7 made creation ASYNCHRONOUS: the endpoint reserves the row, hands back the
    id with `202`, and plans in a background task — so that closing the tab
    during a four-minute plan no longer leaves a session the learner cannot find.

    The consequence for the suite is that `POST /session/start` no longer
    carries a graph. Forty-odd tests read one from it, and every one of them is
    about what happens AFTER a session exists rather than about how it came to.
    So this does what those tests mean: start it, then fetch it.

    Not a mock. The real endpoint runs, the real background task plans, and the
    real graph is read back through `GET /session/{id}` — which is also what the
    frontend does.
    """
    response = client.post(
        "/session/start", json={"repo_url": repo_url, "goal": goal, **extra}
    )
    if response.status_code >= 400:
        return response.json() if response.content else {"status_code": response.status_code}
    body = response.json()
    graph = client.get(f"/session/{body['session_id']}")
    return {
        "session_id": body["session_id"],
        "graph": graph.json() if graph.status_code == 200 else None,
        "resumed": False,
        "errors": body.get("errors", []),
        "status": body.get("status"),
    }
