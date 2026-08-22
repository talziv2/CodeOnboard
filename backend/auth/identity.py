"""Users and repositories: the two rows a session points at.

Multi-user M1. Everything here is plain SQL over the shared connection — no
hashing, no tokens, no authentication. Those arrive in M2 and M6; this module
exists so the migration and the session store have one place to resolve "which
user" and "which repository" from.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from backend.auth.schema import init_auth_schema, new_id
from backend.learning.store import DEFAULT_DB_PATH, _connect
from backend.repo.cloner import normalize_repo_url, parse_repo_url


# THE LEGACY OWNER.
#
# Every session written before multi-user existed is assigned to this user by the
# migration, so invariant I1 — every session has exactly one owner — holds from
# the moment the migration finishes rather than from whenever a human first
# registers.
#
# It is created `is_active = 0` and with NO auth identity, which together mean
# nobody can ever log in as it: there is no (provider, subject) pair that
# resolves here. It is a parking space, and `scripts/adopt_legacy_sessions.py`
# (M2) is what empties it into a real account.
#
# `.local` is reserved by RFC 6762 and can never be a real mail domain, so this
# address cannot collide with one a person registers.
LEGACY_EMAIL = "legacy@codeonboard.local"
LEGACY_DISPLAY_NAME = "Sessions from before accounts existed"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# ── users ─────────────────────────────────────────────────────────────────────


def create_user(
    email: str | None,
    display_name: str | None = None,
    *,
    is_active: bool = True,
    db_path: Path = DEFAULT_DB_PATH,
) -> str:
    """Insert a user and return its id. Raises on a duplicate email."""
    init_auth_schema(db_path)
    user_id = new_id()
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO users (user_id, email, display_name, created_at, is_active) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, email, display_name, _now(), int(is_active)),
        )
    return user_id


def find_user_by_email(
    email: str, db_path: Path = DEFAULT_DB_PATH
) -> dict | None:
    """The user with this email, or None.

    A database with no `users` table answers None rather than raising: on a fresh
    install the account schema has not been created yet, and "no users table" and
    "no such user" are the same answer to the only question being asked. Without
    this, the very first `save_graph` on a new database explodes while trying to
    look up the legacy owner it is about to create.
    """
    if not Path(db_path).exists():
        return None
    try:
        with _connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM users WHERE email = ?", (email.strip().lower(),)
            ).fetchone()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return None
        raise
    return dict(row) if row else None


def get_legacy_user_id(db_path: Path = DEFAULT_DB_PATH) -> str | None:
    """The parking-space user, or None where the migration has not run."""
    user = find_user_by_email(LEGACY_EMAIL, db_path=db_path)
    return user["user_id"] if user else None


def ensure_legacy_user(db_path: Path = DEFAULT_DB_PATH) -> str:
    """The legacy user's id, creating the row the first time.

    ## Idempotent AND concurrency-safe, which are not the same thing

    The obvious shape — `get_legacy_user_id()`, and create it if None — is
    idempotent when called twice in sequence and BROKEN when called twice at
    once: both callers see None, both INSERT, and the second dies on
    `UNIQUE constraint failed: users.email`.

    That is not a theoretical race. `save_graph` calls this on every write, so
    the first two concurrent saves against a fresh database hit it directly; it
    was reproduced by `test_concurrent_writers_all_succeed` within a few runs of
    being introduced. It is the same check-then-act shape as
    `_add_missing_columns` in the learning store, arrived at independently, which
    is a good reason to distrust the shape rather than the instance.

    `INSERT … ON CONFLICT DO NOTHING` then SELECT is race-free because each
    statement is atomic: whoever loses the insert reads the winner's row.
    """
    init_auth_schema(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO users (user_id, email, display_name, created_at, is_active) "
            "VALUES (?, ?, ?, ?, 0) ON CONFLICT DO NOTHING",
            (new_id(), LEGACY_EMAIL, LEGACY_DISPLAY_NAME, _now()),
        )
        row = conn.execute(
            "SELECT user_id FROM users WHERE email = ?", (LEGACY_EMAIL,)
        ).fetchone()
    return row[0]


# ── repositories ──────────────────────────────────────────────────────────────


def ensure_repository(repo_url: str, db_path: Path = DEFAULT_DB_PATH) -> str:
    """The repo_id for this URL, inserting the row the first time.

    Every spelling of one repository resolves here to one row, because the
    identity comes from `cloner.parse_repo_url` — the same function that decides
    the checkout path and the survey cache key. The live database holds five
    spellings of three repositories (`…/aima-python`, `…/aima-python.git`,
    `…/requests`, `…/requests/`, `…/fastapi`); they collapse to three rows.

    Raises ValueError for a URL the cloner would refuse, so a repository row can
    never exist for something the system would not clone.
    """
    init_auth_schema(db_path)
    owner, name = parse_repo_url(repo_url)          # validates
    canonical = normalize_repo_url(repo_url)
    host = "github.com"                             # the only allowed host today

    # Insert-then-read rather than read-then-insert, for the same reason as
    # `ensure_legacy_user`: `save_graph` calls this on every write, so two
    # concurrent first saves for one repository would both see "absent" and the
    # loser would die on `idx_repo_canonical`.
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            "INSERT INTO repositories "
            "(repo_id, host, owner, name, canonical_url, slug, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
            (new_id(), host, owner, name, canonical, f"{owner}/{name}", _now()),
        )
        row = conn.execute(
            "SELECT repo_id FROM repositories WHERE host = ? AND owner = ? AND name = ?",
            (host, owner, name),
        ).fetchone()
        return row["repo_id"]


def get_repository(repo_id: str, db_path: Path = DEFAULT_DB_PATH) -> dict | None:
    """The repository row, or None — including where the table does not exist yet."""
    if not Path(db_path).exists():
        return None
    try:
        with _connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM repositories WHERE repo_id = ?", (repo_id,)
            ).fetchone()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return None
        raise
    return dict(row) if row else None
