"""What must be true of the environment before this process serves anyone.

Multi-user M8.

## Why this refuses to start rather than warning

Every value here has a safe default for development and NO safe default in
production, and the difference between the two is not something a log line
survives. A missing `CODEONBOARD_SECRET_KEY` in production means the cookie that
carries the OAuth `state` is signed with a key that changes on every restart; a
`CODEONBOARD_COOKIE_SECURE=0` means session cookies travel in clear. Both work
perfectly until they matter.

So the check is a refusal, and it is loud. A process that will not start gets
looked at; a warning in a log does not.

## What decides "production"

`CODEONBOARD_ENV`. Explicit rather than inferred from a hostname or a debug
flag, because every inference here has a failure mode where the guess is wrong
in the unsafe direction — and the whole point is to be wrong safely.
"""

from __future__ import annotations

import os


class InsecureConfiguration(RuntimeError):
    """The environment is not safe to serve from. Nothing has started."""


def is_production() -> bool:
    return os.environ.get("CODEONBOARD_ENV", "development").lower() == "production"


def _cookies_are_secure() -> bool:
    return os.environ.get("CODEONBOARD_COOKIE_SECURE", "1") != "0"


def check() -> list[str]:
    """Problems with the current environment. Empty means fine.

    Returns rather than raises so a caller can report all of them at once — a
    deployment that is missing three things should learn that in one run, not in
    three restarts.
    """
    problems: list[str] = []

    if not os.environ.get("ANTHROPIC_API_KEY"):
        problems.append(
            "ANTHROPIC_API_KEY is not set — every lesson, grade and plan needs it."
        )

    if not is_production():
        return problems

    if not _cookies_are_secure():
        problems.append(
            "CODEONBOARD_COOKIE_SECURE=0 in production: session cookies would be "
            "sent over plain http, where anything on the network can read them."
        )

    if not os.environ.get("CODEONBOARD_SECRET_KEY"):
        problems.append(
            "CODEONBOARD_SECRET_KEY is not set in production: the cookie carrying "
            "the OAuth state would be signed with a key that changes on every "
            "restart, so sign-in flows would break unpredictably."
        )

    origins = os.environ.get("CODEONBOARD_ALLOWED_ORIGINS", "")
    if "localhost" in origins or "127.0.0.1" in origins:
        problems.append(
            "CODEONBOARD_ALLOWED_ORIGINS still contains a localhost origin in "
            "production — a leftover development value."
        )

    # Configured-or-absent, never half. A client id with no secret produces a
    # sign-in button that always fails, which reads to a learner as the product
    # being broken rather than the deployment being incomplete.
    has_id = bool(os.environ.get("GOOGLE_CLIENT_ID"))
    has_secret = bool(os.environ.get("GOOGLE_CLIENT_SECRET"))
    if has_id != has_secret:
        problems.append(
            "Google sign-in is half-configured: set both GOOGLE_CLIENT_ID and "
            "GOOGLE_CLIENT_SECRET, or neither."
        )

    return problems


def enforce() -> None:
    problems = check()
    if problems:
        raise InsecureConfiguration(
            "Refusing to start:\n  - " + "\n  - ".join(problems)
        )
