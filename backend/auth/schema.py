"""The account layer's tables: users, identities, auth sessions, repositories, drafts.

Multi-user M1 (docs/planning/phases/multi-user.md §5, §13). **No behaviour
changes here** — this milestone creates the shape and fills it in from what
already exists. Nothing authenticates, nothing is authorised, and no route
changes what it returns.

## Why these tables live beside the learning store rather than inside it

Same SQLite file (`data/sessions.db`), same connection settings, different
module. One file because there is one database and a foreign key cannot cross
files; a different module because `backend/learning/store.py` is the learning
graph's persistence and would stop being legible if account identity were folded
into it.

The one place the two genuinely meet is `sessions.user_id` / `sessions.repo_id`,
and those are columns on a table the learning store already owns — added through
its `_ADDITIVE_COLUMNS` mechanism, not from here.

## Identity: User + AuthIdentity, and why not one flat table

`users` is the canonical internal identity — the thing a session points at.
`auth_identities` is how a human proves they are that user: one row per
(provider, subject). Password and Google are two rows; a third provider is a
third row and no migration.

The flat alternative (`users.password_hash`, `users.google_sub`) is smaller today
and makes every later provider a schema change plus a new branch in every login
path. The extra table is the cheaper of the two once "more identity providers"
is a stated possibility (§5.3).

`users.email` is **contact and display only**. It is not the authentication key —
`auth_identities.(provider, subject)` is — which is what keeps a changed email
address from breaking a Google login. It is also, with no verification shipping
(D-5), an unverified claim, and nothing here may treat it as proof.

## Repositories are not owned

A `repositories` row is a canonical identity for a PUBLIC artifact, not an owned
object. Two users studying `psf/requests` share the row, the checkout on disk and
the goal-agnostic survey; they share nothing else. Ownership lives on the
session (§9).

Keyed `(host, owner, name)` lower-cased — the same identity `cloner.parse_repo_url`
produces, so the row, the checkout path and the survey cache key cannot disagree.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from backend.learning.store import DEFAULT_DB_PATH, _connect


def new_id() -> str:
    """A fresh identifier. uuid4 hex, matching the learning graph's ids."""
    return uuid.uuid4().hex


# ── users ─────────────────────────────────────────────────────────────────────
#
# `is_active` exists for exactly one reason in M1: the legacy user that owns the
# pre-multi-user sessions is created inactive and with NO auth identity, so it
# is a row nobody can ever log in as. It is a parking space, not an account.
_CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    user_id       TEXT PRIMARY KEY,
    email         TEXT,
    display_name  TEXT,
    created_at    TEXT NOT NULL,
    last_login_at TEXT,
    is_active     INTEGER NOT NULL DEFAULT 1
)
"""

# Partial index: `email` is nullable (a Google-only user need not have one that
# is unique to us), but where it is present it identifies one person.
_CREATE_USERS_EMAIL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email
    ON users (email) WHERE email IS NOT NULL
"""


# ── auth_identities ───────────────────────────────────────────────────────────
#
# `secret_hash` is argon2id for password rows and NULL for every federated one —
# there is no secret of ours to keep for a Google identity. `email_verified`
# records what the PROVIDER asserted, never what we assumed: with D-5 shipping no
# verification of our own, a password row's value is always 0.
_CREATE_IDENTITIES = """
CREATE TABLE IF NOT EXISTS auth_identities (
    identity_id    TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL,
    provider       TEXT NOT NULL,
    subject        TEXT NOT NULL,
    secret_hash    TEXT,
    email_verified INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
)
"""

# THE LOGIN LOOKUP, and the constraint that makes one identity resolve to one
# user. Unique on the pair, not on either half: one person may hold a password
# identity and a Google identity, and two people may not share either.
_CREATE_IDENTITIES_UNIQUE = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_identity_provider_subject
    ON auth_identities (provider, subject)
"""

_CREATE_IDENTITIES_USER = """
CREATE INDEX IF NOT EXISTS idx_identity_user ON auth_identities (user_id)
"""


# ── auth_sessions ─────────────────────────────────────────────────────────────
#
# Opaque tokens rather than JWTs (§6.1): logout should be a DELETE, not a
# denylist. Only the SHA-256 of the cookie value is stored, so a dump of this
# table is not a set of live credentials.
#
# Created in M1 and written by nothing until M2. It is here because the schema is
# one migration, not because anything authenticates yet.
_CREATE_AUTH_SESSIONS = """
CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash   TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    last_seen_at TEXT,
    expires_at   TEXT NOT NULL,
    user_agent   TEXT,
    revoked_at   TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
)
"""

_CREATE_AUTH_SESSIONS_USER = """
CREATE INDEX IF NOT EXISTS idx_authsessions_user ON auth_sessions (user_id)
"""


# ── repositories ──────────────────────────────────────────────────────────────
#
# `canonical_url` is what `cloner.normalize_repo_url` produces; `slug` is
# `owner/name`, which is the survey cache's key. Both are stored rather than
# derived on read so a query can group by repository without importing the
# cloner — and both come from one function, so they cannot drift apart.
_CREATE_REPOSITORIES = """
CREATE TABLE IF NOT EXISTS repositories (
    repo_id       TEXT PRIMARY KEY,
    host          TEXT NOT NULL,
    owner         TEXT NOT NULL,
    name          TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    slug          TEXT NOT NULL,
    created_at    TEXT NOT NULL
)
"""

_CREATE_REPOSITORIES_UNIQUE = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_repo_canonical
    ON repositories (host, owner, name)
"""


# ── session_drafts ────────────────────────────────────────────────────────────
#
# The goal interview, which today lives in a 64-entry module-level dict in
# `api.py` that evicts other people's in-flight interviews and dies with the
# process (§2 P5). The table lands in M1 with the rest of the shape; the
# endpoints move onto it in M7.
_CREATE_DRAFTS = """
CREATE TABLE IF NOT EXISTS session_drafts (
    draft_id     TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    repo_url     TEXT NOT NULL,
    goal_type    TEXT,
    answers_json TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
)
"""

_CREATE_DRAFTS_USER = """
CREATE INDEX IF NOT EXISTS idx_drafts_user ON session_drafts (user_id, updated_at DESC)
"""


# ── indexes on the learning store's own table ─────────────────────────────────
#
# `sessions` is owned by `backend/learning/store.py` and its columns are added
# there. These two indexes are declared HERE because they exist to serve queries
# this layer makes — "my sessions, newest first" and "my sessions on this
# repository" — and would be unexplainable sitting next to the graph's own index.
_CREATE_SESSIONS_USER = """
CREATE INDEX IF NOT EXISTS idx_sessions_user
    ON sessions (user_id, last_active_at DESC)
"""

_CREATE_SESSIONS_USER_REPO = """
CREATE INDEX IF NOT EXISTS idx_sessions_user_repo ON sessions (user_id, repo_id)
"""


_STATEMENTS = (
    _CREATE_USERS,
    _CREATE_USERS_EMAIL,
    _CREATE_IDENTITIES,
    _CREATE_IDENTITIES_UNIQUE,
    _CREATE_IDENTITIES_USER,
    _CREATE_AUTH_SESSIONS,
    _CREATE_AUTH_SESSIONS_USER,
    _CREATE_REPOSITORIES,
    _CREATE_REPOSITORIES_UNIQUE,
    _CREATE_DRAFTS,
    _CREATE_DRAFTS_USER,
)


def init_auth_schema(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Create the account tables. Idempotent — every statement is IF NOT EXISTS.

    The two `sessions` indexes are created separately and tolerantly: they name
    columns the learning store adds through its own additive mechanism, and on a
    database where `init_db` has not run yet those columns do not exist. Failing
    here would make the order the two initialisers run in load-bearing, which is
    exactly the kind of coupling this split is meant to avoid.
    """
    with _connect(db_path) as conn:
        for statement in _STATEMENTS:
            conn.execute(statement)
        for statement in (_CREATE_SESSIONS_USER, _CREATE_SESSIONS_USER_REPO):
            try:
                conn.execute(statement)
            except sqlite3.OperationalError as exc:
                # `init_db` has not run on this file yet, so either the table is
                # absent entirely ("no such table: main.sessions") or it predates
                # the account columns ("no such column: user_id"). Both mean the
                # same thing — there is nothing to index yet — and `init_db` will
                # create the index itself on the next call, because these
                # statements are IF NOT EXISTS and run on every init.
                #
                # Narrow on purpose: anything else is a real failure and raises.
                message = str(exc).lower()
                if "no such column" not in message and "no such table" not in message:
                    raise
