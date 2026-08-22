"""Users and repositories: the two rows a session points at.

Multi-user M1. Everything here is plain SQL over the shared connection — no
hashing, no tokens, no authentication. Those arrive in M2 and M6; this module
exists so the migration and the session store have one place to resolve "which
user" and "which repository" from.
"""

from __future__ import annotations

import re
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


# ── auth identities (multi-user M2) ───────────────────────────────────────────
#
# `users` is WHO someone is; `auth_identities` is HOW they prove it. One row per
# (provider, subject): a password identity's subject is the normalised email, a
# Google identity's is the `sub` claim. A third provider later is a new row kind,
# not a schema change.

PASSWORD = "password"
GOOGLE = "google"


def normalize_email(email: str) -> str:
    """The form an email is stored and compared in.

    Lower-cased and stripped, and nothing cleverer. Gmail's dot-and-plus
    equivalence is real but is NOT ours to apply: `a.b@gmail.com` and
    `ab@gmail.com` are one mailbox at Google and two different strings
    everywhere else, so normalising them here would silently merge two people's
    accounts on a provider-specific rule we would then have to maintain per
    domain.
    """
    return email.strip().lower()


# Deliberately permissive: one @, something either side, no whitespace, a dot in
# the domain. It is a SHAPE check, not a validity check.
#
# `email-validator` (what pydantic's `EmailStr` pulls in) would be more precise
# and is not worth a dependency here, because nothing in this system ever sends
# mail — D-5 ships no verification and no reset — so the address is contact
# information a person may one day read, not an endpoint we rely on. Rejecting
# an unusual-but-real address would cost more than accepting an unusable one,
# which is why this errs toward accepting.
_EMAIL_SHAPE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")


class InvalidEmailError(ValueError):
    """The string is not shaped like an email address."""


def validate_email(email: str) -> str:
    """Normalise and shape-check, or raise. Returns the stored form."""
    normalised = normalize_email(email)
    if not normalised or len(normalised) > 254 or not _EMAIL_SHAPE.match(normalised):
        raise InvalidEmailError("Enter a valid email address.")
    return normalised


def find_identity(
    provider: str, subject: str, db_path: Path = DEFAULT_DB_PATH
) -> dict | None:
    """The identity row for this (provider, subject), or None.

    THE LOGIN LOOKUP. Answers None where the table does not exist yet, so a
    database from before accounts is "nobody is registered" rather than a crash.
    """
    if not Path(db_path).exists():
        return None
    try:
        with _connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM auth_identities WHERE provider = ? AND subject = ?",
                (provider, subject),
            ).fetchone()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return None
        raise
    return dict(row) if row else None


def add_identity(
    user_id: str,
    provider: str,
    subject: str,
    *,
    secret_hash: str | None = None,
    email_verified: bool = False,
    db_path: Path = DEFAULT_DB_PATH,
) -> str:
    """Attach a way of proving identity to an existing user.

    Raises `sqlite3.IntegrityError` when this (provider, subject) already belongs
    to someone — the unique index is what makes one identity resolve to one user,
    and letting a second row through would be the whole security model gone.
    """
    init_auth_schema(db_path)
    identity_id = new_id()
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO auth_identities "
            "(identity_id, user_id, provider, subject, secret_hash, "
            " email_verified, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (identity_id, user_id, provider, subject, secret_hash,
             int(email_verified), _now()),
        )
    return identity_id


def set_password_hash(
    user_id: str, subject: str, secret_hash: str, db_path: Path = DEFAULT_DB_PATH
) -> None:
    """Replace the stored hash on a password identity.

    Two callers: rehash-on-login when the parameters have been raised, and
    `scripts/set_password.py`. Never an endpoint — with no email verification
    shipping (D-5) there is no safe way to authenticate a reset request.
    """
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE auth_identities SET secret_hash = ? "
            "WHERE user_id = ? AND provider = ? AND subject = ?",
            (secret_hash, user_id, PASSWORD, subject),
        )


def identities_for(user_id: str, db_path: Path = DEFAULT_DB_PATH) -> list[dict]:
    """Every way this user can sign in. Used by M6's "unlink" guard."""
    if not Path(db_path).exists():
        return []
    try:
        with _connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT identity_id, provider, subject, email_verified, created_at "
                "FROM auth_identities WHERE user_id = ? ORDER BY created_at",
                (user_id,),
            ).fetchall()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return []
        raise
    return [dict(r) for r in rows]


def get_user(user_id: str, db_path: Path = DEFAULT_DB_PATH) -> dict | None:
    if not Path(db_path).exists():
        return None
    try:
        with _connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return None
        raise
    return dict(row) if row else None


def touch_login(user_id: str, db_path: Path = DEFAULT_DB_PATH) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE users SET last_login_at = ? WHERE user_id = ?", (_now(), user_id)
        )
