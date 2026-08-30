"""Single-use password-reset tokens. Nothing here sends mail.

Multi-user M2 shipped no reset at all (D-5), because a reset flow has to
authenticate the *request* somehow and this system verifies no email address.
**That is still true.** What exists now is narrower and honest about its scope:
the token lifecycle is real — created, expiring, single-use, revoking sessions
on success — and the delivery step, the one part that needs infrastructure this
project does not have, is replaced by handing the link back to the caller in
development.

## The limitation, stated next to the code rather than only in the doc

`POST /auth/forgot` returns the reset link to whoever asked for it. In
development that is the whole point: it is how the flow is demonstrated without
a mail provider. In production it would be an account-takeover endpoint for
anybody who can type an email address — so `config.reveals_reset_link()` is
False there, and the link is neither returned nor logged. The endpoint still
answers, and reveals nothing.

That is a deliberate degradation, not a fix. Until email verification ships,
`scripts/set_password.py` remains the only recovery path that is safe to expose
outside a laptop.

## Shape borrowed from `tokens.py`, deliberately

Same rules for the same reasons — 32 bytes from `secrets.token_urlsafe`, only
the sha256 in the table, expiry checked on read — so there is one story about
how a bearer credential is stored here. Two things differ, both because a reset
token outranks a session cookie: it is worth a password rather than merely a
session, and it travels somewhere a session cookie never does.

  - **Single use.** `used_at` is stamped by the same UPDATE that validates the
    row, so validation and consumption cannot be separated. A link that has
    reset a password cannot reset one again, and two simultaneous submissions of
    the same link cannot both win.
  - **Minutes, not weeks.** `TTL_MINUTES` is 30. A session is a convenience and
    is renewed by use; a reset token is a key to an account, sitting wherever it
    was delivered.

## Why `subject` is stored on the row

`identity.set_password_hash` needs the password identity's subject — the email —
and re-deriving it at consume time from `users.email` would silently target the
wrong identity if the address had changed in between. The row records which
identity the reset was issued *for*.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.auth.schema import init_auth_schema
from backend.learning.store import DEFAULT_DB_PATH, _connect

# 32 bytes → 43 URL-safe characters, same as a session token. It travels in a
# query string, so it must survive a URL unescaped, which `token_urlsafe` gives.
TOKEN_BYTES = 32

TTL_MINUTES = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.replace(microsecond=0).isoformat()


def hash_token(raw: str) -> str:
    """What goes in the table. The raw value goes only to the person resetting."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create(
    user_id: str,
    subject: str,
    *,
    db_path: Path = DEFAULT_DB_PATH,
) -> str:
    """Issue a reset token and return the RAW value — the only time it exists.

    Any token already outstanding for this user is deleted first. Requesting a
    reset twice should leave one live link, not two: the second request is
    normally somebody who did not receive the first, and leaving the earlier one
    valid widens the window for no benefit.
    """
    init_auth_schema(db_path)
    raw = secrets.token_urlsafe(TOKEN_BYTES)
    now = _now()
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM password_resets WHERE user_id = ?", (user_id,))
        conn.execute(
            "INSERT INTO password_resets "
            "(token_hash, user_id, subject, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                hash_token(raw),
                user_id,
                subject,
                _iso(now),
                _iso(now + timedelta(minutes=TTL_MINUTES)),
            ),
        )
    return raw


def consume(raw: str | None, db_path: Path = DEFAULT_DB_PATH) -> dict | None:
    """Spend this token, returning `{user_id, subject}` — or None.

    None covers every way a token can fail: absent, unknown, already used,
    expired. The caller does not get to know which, for the same reason
    `tokens.resolve` does not — distinguishing "expired" from "never existed"
    confirms that a token was once real.

    ## The single UPDATE is the whole safety property

    Validation and consumption are one statement, so there is no window between
    "this token is good" and "this token is spent". A read-then-write version of
    this function lets two concurrent submissions of the same link both pass the
    read. SQLite serialises writers, so the loser of that race matches zero rows
    and gets None.
    """
    if not raw:
        return None
    token_hash = hash_token(raw)
    now = _iso(_now())

    try:
        with _connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            spent = conn.execute(
                "UPDATE password_resets SET used_at = ? "
                "WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?",
                (now, token_hash, now),
            )
            if spent.rowcount != 1:
                return None
            row = conn.execute(
                "SELECT user_id, subject FROM password_resets WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
            return dict(row) if row else None
    except sqlite3.OperationalError as exc:
        # No `password_resets` table: a database from before this feature. No
        # token can be outstanding there, which is what None means.
        if "no such table" in str(exc).lower():
            return None
        raise


def purge_expired(db_path: Path = DEFAULT_DB_PATH) -> int:
    """Delete tokens that can no longer reset anything. Housekeeping, not security.

    `consume` already refuses them; this keeps the table from growing without
    bound in a process that may run for months.
    """
    now = _iso(_now())
    try:
        with _connect(db_path) as conn:
            return conn.execute(
                "DELETE FROM password_resets "
                "WHERE expires_at <= ? OR used_at IS NOT NULL",
                (now,),
            ).rowcount
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return 0
        raise
