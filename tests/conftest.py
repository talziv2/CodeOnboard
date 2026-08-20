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
AMBIENT_FLAGS = (
    "CODEONBOARD_CURRICULUM",
    "CODEONBOARD_GAPS",
)


@pytest.fixture(autouse=True)
def _neutral_flags(monkeypatch):
    """Start every test with the flags unset, whatever the machine has.

    `raising=False` because unset is the normal case: this is about guaranteeing a
    known starting point, not about asserting one existed.
    """
    for flag in AMBIENT_FLAGS:
        monkeypatch.delenv(flag, raising=False)
