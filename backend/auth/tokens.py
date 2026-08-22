"""Authentication sessions: opaque tokens in a table, delivered as a cookie.

Multi-user M2.

## Why not JWT

The argument for JWT is stateless horizontal scale. This is one uvicorn process
against one SQLite file, so that buys nothing, and staying opaque buys four
things it does not:

  - **Logout actually logs out.** A row is deleted. A JWT is valid until it
    expires, so real logout needs a denylist — which is a session table with
    extra steps and worse ergonomics.
  - No signing key to manage, rotate, or accidentally commit; no algorithm
    confusion; no `alg: none`.
  - No refresh-token dance. Sliding expiry does the same job in one column.
  - "Sign out everywhere" and "your other devices" are queries rather than
    features.

## Only the hash is stored

The cookie carries 256 bits from `secrets.token_urlsafe`; the table stores
`sha256` of it. A dump of `auth_sessions` is therefore not a set of live
credentials, which matters because that table sits in the same file as everything
else and will end up in the same backups.

SHA-256 rather than Argon2 here, deliberately: the token is 256 random bits, not
a human-chosen secret, so there is no dictionary to slow down and nothing to gain
from a work factor that would then run on EVERY authenticated request.

## Expiry

Idle timeout `IDLE_DAYS`, absolute cap `ABSOLUTE_DAYS`. `last_seen_at` is written
at most once an hour rather than on every request: this database's scarce
resource is the write lock (see `store._configure`), and putting an UPDATE in
front of every lesson load would spend it on bookkeeping.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.auth.schema import init_auth_schema
from backend.learning.store import DEFAULT_DB_PATH, _connect

COOKIE_NAME = "co_session"

# 32 bytes → 43 URL-safe characters. Well past guessing.
TOKEN_BYTES = 32

IDLE_DAYS = 14
ABSOLUTE_DAYS = 90

# How stale `last_seen_at` may get before a read pays for a write.
TOUCH_INTERVAL = timedelta(hours=1)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.replace(microsecond=0).isoformat()


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def hash_token(raw: str) -> str:
    """What goes in the table. The raw value goes only to the browser."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue(
    user_id: str,
    *,
    user_agent: str | None = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> str:
    """Create a session and return the RAW token — the only time it exists.

    The caller puts it in a cookie and forgets it. Nothing can recover it from
    the database afterwards, which is the point.
    """
    init_auth_schema(db_path)
    raw = secrets.token_urlsafe(TOKEN_BYTES)
    now = _now()
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO auth_sessions "
            "(token_hash, user_id, created_at, last_seen_at, expires_at, user_agent) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                hash_token(raw),
                user_id,
                _iso(now),
                _iso(now),
                _iso(now + timedelta(days=IDLE_DAYS)),
                (user_agent or "")[:200] or None,
            ),
        )
    return raw


def resolve(raw: str | None, db_path: Path = DEFAULT_DB_PATH) -> str | None:
    """The user this token belongs to, or None. Extends the session on use.

    None covers every way a token can fail — absent, unknown, revoked, idle-
    expired, past the absolute cap — and the caller does not get to know which.
    A 401 that distinguished "expired" from "never existed" would confirm that a
    token had once been real.
    """
    if not raw:
        return None
    token_hash = hash_token(raw)
    now = _now()

    try:
        with _connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM auth_sessions WHERE token_hash = ?", (token_hash,)
            ).fetchone()
            if row is None or row["revoked_at"]:
                return None

            expires = _parse(row["expires_at"])
            created = _parse(row["created_at"])
            if expires is None or expires <= now:
                return None
            # THE ABSOLUTE CAP, and why sliding expiry alone is not enough: a
            # session that is used daily would otherwise never end, so a token
            # stolen once would be good forever as long as it kept being used.
            if created is not None and now - created > timedelta(days=ABSOLUTE_DAYS):
                return None

            last_seen = _parse(row["last_seen_at"])
            if last_seen is None or now - last_seen >= TOUCH_INTERVAL:
                # Slide the idle window, but never past the absolute cap.
                horizon = now + timedelta(days=IDLE_DAYS)
                if created is not None:
                    horizon = min(horizon, created + timedelta(days=ABSOLUTE_DAYS))
                conn.execute(
                    "UPDATE auth_sessions SET last_seen_at = ?, expires_at = ? "
                    "WHERE token_hash = ?",
                    (_iso(now), _iso(horizon), token_hash),
                )
            return row["user_id"]
    except sqlite3.OperationalError as exc:
        # No `auth_sessions` table: a database from before accounts existed.
        # Nobody is logged in there, which is exactly what None means.
        if "no such table" in str(exc).lower():
            return None
        raise


def revoke(raw: str | None, db_path: Path = DEFAULT_DB_PATH) -> bool:
    """End one session — logout. True when something was actually ended.

    DELETE rather than a `revoked_at` stamp. The column exists for an
    administrative "this session is suspect" that keeps the audit row, but an
    ordinary logout should leave nothing behind: a token the learner has
    finished with is not a record worth keeping, and rows that accumulate
    forever are how a session table becomes a liability.
    """
    if not raw:
        return False
    with _connect(db_path) as conn:
        return conn.execute(
            "DELETE FROM auth_sessions WHERE token_hash = ?", (hash_token(raw),)
        ).rowcount > 0


def revoke_all(user_id: str, db_path: Path = DEFAULT_DB_PATH) -> int:
    """End every session this user holds. Returns how many.

    Used by "sign out everywhere", and by M6's Google linking — where proving
    ownership of an account must eject anyone already holding a token for it.
    """
    with _connect(db_path) as conn:
        return conn.execute(
            "DELETE FROM auth_sessions WHERE user_id = ?", (user_id,)
        ).rowcount


def purge_expired(db_path: Path = DEFAULT_DB_PATH) -> int:
    """Delete sessions that can no longer authenticate anyone.

    Housekeeping, not security — `resolve` already refuses them. It keeps the
    table from growing without bound in a process that may run for months.
    """
    now = _iso(_now())
    cutoff = _iso(_now() - timedelta(days=ABSOLUTE_DAYS))
    try:
        with _connect(db_path) as conn:
            return conn.execute(
                "DELETE FROM auth_sessions "
                "WHERE expires_at <= ? OR created_at <= ? OR revoked_at IS NOT NULL",
                (now, cutoff),
            ).rowcount
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return 0
        raise
