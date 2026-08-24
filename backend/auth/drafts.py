"""The goal interview, persisted (multi-user M7).

Replaces `backend.api.sessions` — a module-level dict, capped at 64, shared by
everybody. Three things were wrong with it and only the first was obvious:

  it died with the process, so a backend restart lost every in-flight interview;
  the cap was GLOBAL, so ten concurrent learners evicted each other's;
  and it was unowned, so anybody holding an id could drive somebody else's
  interview (M3 patched that with a parallel dict; this removes the need).

A draft is small — a repo URL, a goal type and a handful of answers — so the cost
of persisting it is nothing, and what it buys is that "I closed the tab" and "the
server restarted" stop being ways to lose five questions of work.

`GoalSession` itself is untouched. It belongs to the goal agent, and the agent
must not learn about users (I9); this module is only where the dataclass is kept
between requests.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from backend.agents.goal import GoalSession
from backend.auth.schema import init_auth_schema, new_id
from backend.learning.store import DEFAULT_DB_PATH, _connect


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def create(user_id: str, repo_url: str, db_path: Path = DEFAULT_DB_PATH) -> GoalSession:
    """Start an interview for this user. Returns the agent's own object."""
    init_auth_schema(db_path)
    draft_id = new_id()
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO session_drafts "
            "(draft_id, user_id, repo_url, goal_type, answers_json, created_at, updated_at) "
            "VALUES (?, ?, ?, NULL, '{}', ?, ?)",
            (draft_id, user_id, repo_url, _now(), _now()),
        )
    return GoalSession(session_id=draft_id, repo_url=repo_url)


def load(draft_id: str, user_id: str, db_path: Path = DEFAULT_DB_PATH) -> GoalSession | None:
    """The caller's interview, or None — owner-scoped like everything else.

    None for "not yours" as well as "not there", so a draft id cannot be used to
    discover that somebody else is mid-interview.
    """
    if not Path(db_path).exists():
        return None
    try:
        with _connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM session_drafts WHERE draft_id = ? AND user_id = ?",
                (draft_id, user_id),
            ).fetchone()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return None
        raise
    if row is None:
        return None
    return GoalSession(
        session_id=row["draft_id"],
        repo_url=row["repo_url"],
        goal_type=row["goal_type"],
        answers=json.loads(row["answers_json"] or "{}"),
    )


def save(session: GoalSession, user_id: str, db_path: Path = DEFAULT_DB_PATH) -> None:
    """Write the interview back. Owner-scoped in the UPDATE."""
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE session_drafts SET goal_type = ?, answers_json = ?, updated_at = ? "
            "WHERE draft_id = ? AND user_id = ?",
            (session.goal_type, json.dumps(session.answers), _now(),
             session.session_id, user_id),
        )


def delete(draft_id: str, user_id: str, db_path: Path = DEFAULT_DB_PATH) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "DELETE FROM session_drafts WHERE draft_id = ? AND user_id = ?",
            (draft_id, user_id),
        )


def list_for(user_id: str, db_path: Path = DEFAULT_DB_PATH) -> list[dict]:
    """Unfinished interviews, newest first — so one can be resumed rather than redone."""
    if not Path(db_path).exists():
        return []
    try:
        with _connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT draft_id, repo_url, goal_type, answers_json, created_at, updated_at "
                "FROM session_drafts WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return []
        raise
    return [
        {
            "draft_id": r["draft_id"],
            "repo_url": r["repo_url"],
            "goal_type": r["goal_type"],
            "answered": len(json.loads(r["answers_json"] or "{}")),
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]


def purge_older_than(days: int = 30, db_path: Path = DEFAULT_DB_PATH) -> int:
    """Forget abandoned interviews.

    Housekeeping rather than policy: an interview nobody has touched in a month
    is one nobody is coming back to, and unlike the old dict this table has no
    cap to evict against — it would otherwise grow forever.
    """
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - days * 86400))
    try:
        with _connect(db_path) as conn:
            return conn.execute(
                "DELETE FROM session_drafts WHERE updated_at < ?", (cutoff,)
            ).rowcount
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return 0
        raise
