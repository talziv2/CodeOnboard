"""Invariants checked when the process starts, before it serves anything.

Multi-user M1. Two checks, and they are deliberately different in severity —
one refuses to start, the other repairs quietly — because they protect against
different failures.

A third thing happens first, and it is neither: `ensure_schema` CREATES what the
checks then read. See its docstring for why that has to be here rather than in
each reader.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from backend.learning.store import DEFAULT_DB_PATH, _connect, init_db

logger = logging.getLogger(__name__)


class UnownedSessionsError(RuntimeError):
    """Sessions exist with no owner. The migration has not run, or half ran."""


def ensure_schema(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Create both halves of the schema before anything reads either. Idempotent.

    ## The bug this fixes

    A brand-new installation used to answer `GET /sessions` with a 500. The
    sequence was three steps and every one of them looked right on its own:

    1. Nothing creates the database at startup, so a fresh install has no file.
    2. `POST /auth/register` writes through `init_auth_schema`, which CREATES THE
       FILE and the six account tables — and none of the learning store's.
    3. `list_sessions_for_user` guards with `if not Path(db_path).exists()`,
       which was written for "no file at all". The file now exists, so the guard
       passes and the query hits `no such table: sessions`.

    So the first screen a learner saw after signing up carried a red error. It
    cleared itself once they started a session — `create_pending_session` calls
    `init_db` — which is exactly why it survived: it is invisible to anyone whose
    database already has rows in it.

    ## Why here, and not a guard in each reader

    `list_sessions_for_user` is not the only reader with that shape;
    `delete_session` has it too, and nothing stops a third from being written.
    Fixing them one at a time treats "the tables exist" as something each caller
    must remember, which is the same class of mistake as the one being fixed.

    Doing it once at startup makes it true of the process instead. That is the
    discipline this module already applies to its other invariants, and it is
    strictly less code than the per-reader alternative.

    ## Order

    `init_db` first. `init_auth_schema` creates two indexes over `sessions`
    columns (`user_id`, `repo_id`) that `init_db` adds through
    `_ADDITIVE_COLUMNS`; it tolerates their absence, so this is not a
    correctness requirement — but running in this order means the normal boot
    stops relying on that tolerance.

    Both are `CREATE … IF NOT EXISTS` throughout, and `_add_missing_columns`
    reads `PRAGMA table_info` before altering anything, so on an existing
    database this is a no-op costing two connections.
    """
    from backend.auth.schema import init_auth_schema

    init_db(db_path)
    init_auth_schema(db_path)


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


def fail_stale_generating(db_path: Path = DEFAULT_DB_PATH) -> int:
    """Mark sessions still claiming to be generating as failed (M7).

    A pipeline runs in a background task, so a process killed mid-plan leaves a
    row nothing will ever move. THE PROCESS IS NEW, so nothing that claimed to
    be running still is — which makes startup the one moment this is safe to
    assume.

    A card that spins forever is worse than one that says it failed: the learner
    cannot tell whether to wait or to retry.
    """
    from backend.learning.store import fail_stale_generating_sessions

    failed = fail_stale_generating_sessions(db_path, older_than_minutes=0)
    if failed:
        logger.info("marked %d interrupted generation(s) as failed", failed)
    return failed


def purge_old_drafts(db_path: Path = DEFAULT_DB_PATH) -> int:
    """Forget interviews nobody has touched in a month.

    Housekeeping. Unlike the dict this replaced, the table has no cap to evict
    against, so without this it grows forever.
    """
    from backend.auth import drafts

    return drafts.purge_old_drafts(db_path) if hasattr(drafts, "purge_old_drafts")         else drafts.purge_older_than(db_path=db_path)


def run_startup_checks(db_path: Path = DEFAULT_DB_PATH) -> dict:
    """Everything the process checks before it serves anything.

    Ordered by severity, deliberately: the repairs run FIRST so a tidy-up never
    appears to be the thing that failed, and the assertion runs LAST so its
    exception is the one that reaches the caller.

    `ensure_schema` runs before all of them, because it is not a check at all —
    it is the precondition the checks read. Every guard below stays exactly as
    it is: they tolerate a missing table because a caller may pass a path this
    function never saw, and that tolerance is now a second line rather than the
    only one.
    """
    ensure_schema(db_path)
    swept = sweep_orphaned_investigations(db_path)
    stale = fail_stale_generating(db_path)
    drafts_purged = purge_old_drafts(db_path)
    expired = _purge_expired_auth_sessions(db_path)
    assert_every_session_is_owned(db_path)
    return {
        "orphaned_investigations_removed": swept,
        "interrupted_generations_failed": stale,
        "abandoned_drafts_purged": drafts_purged,
        "expired_auth_sessions_purged": expired,
    }


def _purge_expired_auth_sessions(db_path: Path) -> int:
    """Delete auth sessions that can no longer authenticate anyone.

    Housekeeping, not security — `tokens.resolve` already refuses them. It keeps
    the table from growing without bound in a process that may run for months.
    """
    from backend.auth import tokens

    try:
        return tokens.purge_expired(db_path)
    except Exception as exc:                      # noqa: BLE001
        logger.debug("auth-session purge skipped: %s", exc)
        return 0
