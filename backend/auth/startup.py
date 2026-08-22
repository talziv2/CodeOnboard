"""Invariants checked when the process starts, before it serves anything.

Multi-user M1. Two checks, and they are deliberately different in severity —
one refuses to start, the other repairs quietly — because they protect against
different failures.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from backend.learning.store import DEFAULT_DB_PATH, _connect

logger = logging.getLogger(__name__)


class UnownedSessionsError(RuntimeError):
    """Sessions exist with no owner. The migration has not run, or half ran."""


def count_unowned_sessions(db_path: Path = DEFAULT_DB_PATH) -> int:
    if not Path(db_path).exists():
        return 0
    try:
        with _connect(db_path) as conn:
            # Every row, not only the ones this build can currently READ.
            # `schema_version` describes the graph shape; `user_id` describes who
            # the row belongs to, and a row nobody owns is a row nobody can ever
            # reach again whether or not today's code can parse its nodes.
            return conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE user_id IS NULL"
            ).fetchone()[0]
    except sqlite3.OperationalError as exc:
        if "no such column" in str(exc).lower() or "no such table" in str(exc).lower():
            # Nothing has been migrated on this file yet, so there is nothing to
            # be unowned. A fresh database and a fully migrated one both answer
            # zero, which is what makes this check safe to run unconditionally.
            return 0
        raise


def assert_every_session_is_owned(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Refuse to run with an unowned session on disk.

    ## Why a startup assertion and not a NOT NULL constraint

    `user_id` is added by `ALTER TABLE … ADD COLUMN`, and SQLite cannot add a
    NOT NULL column to a populated table without a default — and there is no
    sensible default for "who owns this". Enforcing it in the schema would mean
    rebuilding `sessions`, which is exactly the kind of change the additive
    discipline exists to avoid (multi-user.md §13.1).

    So the invariant is enforced by the process instead, and it is enforced by
    REFUSING TO START rather than by logging. An unowned session is not a
    degraded state the app can serve around: with M3's ownership filter in place
    it is a session that has become permanently unreachable by anybody, and the
    person who would notice is a learner whose work has silently vanished from
    their dashboard. Failing loudly at boot is the only version of this that
    gets looked at.

    It is a cheap COUNT on an indexed column, once per process.
    """
    unowned = count_unowned_sessions(db_path)
    if unowned:
        raise UnownedSessionsError(
            f"{unowned} session(s) have no user_id in {db_path}. "
            "Run: uv run python -m backend.migrations.001_multi_user --apply"
        )


def sweep_orphaned_investigations(db_path: Path = DEFAULT_DB_PATH) -> int:
    """Delete Dossiers whose session is gone. Returns how many.

    `investigation` has no foreign key to `sessions` (`dossier_store.py`:
    `session_id TEXT PRIMARY KEY`, no FK clause), so before `delete_session`
    learned to remove them, every deleted session left one behind — keyed to an
    id nothing will ever ask for again, holding a full exploration payload.

    Unlike the ownership check this REPAIRS rather than refuses, because an
    orphaned dossier harms nothing: it is unreachable derived data, and the rule
    that governs it (D12) already makes "absent" a supported state for every
    consumer. Refusing to start over one would be a tantrum about disk space.

    Best-effort by design — a sweep that cannot run must not stop the process.
    """
    if not Path(db_path).exists():
        return 0
    try:
        with _connect(db_path) as conn:
            removed = conn.execute(
                "DELETE FROM investigation WHERE session_id NOT IN "
                "(SELECT session_id FROM sessions)"
            ).rowcount
    except sqlite3.OperationalError as exc:
        # No `investigation` table yet on a fresh database.
        logger.debug("orphan sweep skipped: %s", exc)
        return 0
    if removed:
        logger.info("removed %d orphaned investigation row(s)", removed)
    return max(removed, 0)


def run_startup_checks(db_path: Path = DEFAULT_DB_PATH) -> dict:
    """Both checks, in the order their severity implies.

    The sweep runs FIRST so that a tidy-up never appears to be the thing that
    failed, and the assertion last so its exception is the one that reaches the
    caller.
    """
    swept = sweep_orphaned_investigations(db_path)
    assert_every_session_is_owned(db_path)
    return {"orphaned_investigations_removed": swept}
