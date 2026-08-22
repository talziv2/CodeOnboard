"""Give every existing session an owner and a repository. Idempotent.

Multi-user M1 (docs/planning/phases/multi-user.md §13). Creates the account
tables, backfills `repositories` from the URLs already in `sessions`, creates the
inert legacy user, assigns every session to it, and derives the display metadata
the dashboard will need.

**`SCHEMA_VERSION` DOES NOT MOVE.** `load_graph` treats a version mismatch as
MISSING rather than migrating it, so a bump would make all 90 sessions in the
live database invisible — the opposite of a migration. Every column this adds is
additive and nullable, applied through the learning store's own
`_ADDITIVE_COLUMNS` mechanism, exactly as the eight before it were.

## What it does NOT do

No authentication, no authorization, no route changes. Afterwards every session
has an owner and every request still reaches every session, because there is
still no way to log in. Enforcement is M3, and doing it here would break the
whole app in the name of a rule nothing could yet satisfy.

## Idempotence

Every step is `IF NOT EXISTS`, a lookup-then-insert, or an `UPDATE … WHERE
column IS NULL`. A second run reports zero changes. That matters more than it
sounds: the first run of a migration is the one most likely to be interrupted,
and "run it again" has to be the correct response.

Usage:

    uv run python -m backend.migrations.001_multi_user            # dry run
    uv run python -m backend.migrations.001_multi_user --apply
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from backend.auth.identity import ensure_legacy_user, ensure_repository
from backend.auth.schema import init_auth_schema
from backend.learning.store import DEFAULT_DB_PATH, SCHEMA_VERSION, _connect, init_db
from backend.repo.cloner import parse_repo_url


def _session_title(goal: dict, slug: str | None) -> str:
    """A name for the dashboard card, derived from what the session already knows.

    `focus_area` is the learner's own words for what they came to understand, so
    it makes the better title; `primary_goal` is the fallback and the repository
    slug the last resort. Truncated on a word boundary — a card is not a place
    for a sentence.

    Derived rather than generated: a model call per session would cost real money
    to name rows that already describe themselves, and the learner can rename
    any of them once M4 ships `PATCH /sessions/{id}`.
    """
    for key in ("focus_area", "primary_goal"):
        value = (goal.get(key) or "").strip()
        if value:
            title = value[0].upper() + value[1:]
            if len(title) <= 60:
                return title
            cut = title[:60].rsplit(" ", 1)[0]
            return (cut or title[:60]).rstrip(",;:") + "…"
    return slug or "Learning session"


def _status_for(current_node_id: str | None) -> str:
    """Every migrated session is `active`.

    Not `completed`, even where the walk has finished: completion is DERIVED
    from the graph (`is_complete()`), and writing it into `status` here would
    create a second source of truth that could disagree with the engine the first
    time a learner reopened a session and answered something. `status` carries
    only what the engine cannot say for itself — generating, failed, archived.
    """
    return "active"


def migrate(db_path: Path = DEFAULT_DB_PATH, *, apply: bool = False) -> dict:
    """Run the migration. Returns a report; changes nothing unless `apply`."""
    report: dict = {
        "db": str(db_path),
        "sessions_total": 0,
        "sessions_assigned": 0,
        "sessions_already_owned": 0,
        "repositories_created": 0,
        "repositories_total": 0,
        "titles_set": 0,
        "status_set": 0,
        "last_active_set": 0,
        "unmappable_repo_urls": [],
        "applied": apply,
    }
    if not Path(db_path).exists():
        report["error"] = "database does not exist"
        return report

    # Both initialisers, in this order: the learning store adds the `user_id` /
    # `repo_id` columns, and the account layer's `sessions` indexes name them.
    if apply:
        init_db(db_path)
        init_auth_schema(db_path)

    # ── reading a database that has not been migrated yet ────────────────────
    #
    # A DRY RUN MUST WORK ON AN UNMIGRATED DATABASE — that is the state anyone
    # would run one in. So the account columns are selected only where they
    # already exist, and treated as NULL where they do not. Naming them
    # unconditionally made the dry run fail with `no such column: user_id` on
    # exactly the database it exists to inspect.
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        present = {r[1] for r in conn.execute("PRAGMA table_info(sessions)")}
        account_columns = ("user_id", "repo_id", "title", "status", "last_active_at")
        selected = ", ".join(
            column if column in present else f"NULL AS {column}"
            for column in account_columns
        )
        # ── EVERY row, whatever its `schema_version` ─────────────────────────
        #
        # Ownership is a property of the ROW, not of the graph shape inside it.
        # A session whose `schema_version` this build no longer reads still has a
        # `repo_url`, a `goal` and a learner it belonged to, and giving it an
        # owner costs nothing and keeps it adoptable if the version question is
        # later resolved.
        #
        # THIS IS NOT HYPOTHETICAL. The session-reset workstream moved
        # SCHEMA_VERSION from 2 to 3, and all 90 sessions in the live database
        # are version 2 — so filtering on the constant here migrated exactly
        # nothing while reporting a clean run. A migration whose scope silently
        # depends on an unrelated workstream's constant is a migration that
        # cannot be trusted to have run.
        rows = conn.execute(
            "SELECT session_id, repo_url, goal_json, current_node_id, updated_at, "
            f"{selected} FROM sessions"
        ).fetchall()
    report["sessions_total"] = len(rows)

    # ── repositories, from the URLs already present ───────────────────────────
    #
    # One row per canonical (host, owner, name). The live database holds five
    # spellings of three repositories; `ensure_repository` collapses them,
    # because it derives identity from the same `parse_repo_url` that decides the
    # checkout path and the survey cache key.
    repo_ids: dict[str, str | None] = {}
    for url in {r["repo_url"] for r in rows}:
        try:
            parse_repo_url(url)
        except ValueError:
            # A URL the cloner would now refuse. The session keeps working — it
            # has a graph, lessons and answers — it simply gets no repository
            # row. Reported rather than swallowed, and never a reason to fail.
            report["unmappable_repo_urls"].append(url)
            repo_ids[url] = None
            continue
        repo_ids[url] = ensure_repository(url, db_path) if apply else "(dry-run)"

    if apply:
        with _connect(db_path) as conn:
            report["repositories_total"] = conn.execute(
                "SELECT COUNT(*) FROM repositories"
            ).fetchone()[0]
        report["repositories_created"] = report["repositories_total"]
    else:
        report["repositories_total"] = len(
            {tuple(parse_repo_url(u)) for u in repo_ids if repo_ids[u] is not None}
        )

    # ── the legacy owner ──────────────────────────────────────────────────────
    legacy_id = ensure_legacy_user(db_path) if apply else "(dry-run)"
    report["legacy_user_id"] = legacy_id

    # ── assignment ────────────────────────────────────────────────────────────
    #
    # `WHERE … IS NULL` on every update, which is what makes a second run a
    # no-op and — more importantly — makes this safe to run after M2 has adopted
    # sessions into a real account. An unconditional UPDATE here would hand them
    # back to the legacy user.
    for row in rows:
        if row["user_id"]:
            report["sessions_already_owned"] += 1
        else:
            report["sessions_assigned"] += 1
        if not row["title"]:
            report["titles_set"] += 1
        if not row["status"]:
            report["status_set"] += 1
        if not row["last_active_at"]:
            report["last_active_set"] += 1

    if not apply:
        return report

    with _connect(db_path) as conn:
        for row in rows:
            goal = json.loads(row["goal_json"])
            repo_id = repo_ids.get(row["repo_url"])
            slug = None
            if repo_id:
                slug = "/".join(parse_repo_url(row["repo_url"]))
            conn.execute(
                """
                UPDATE sessions SET
                    user_id        = COALESCE(user_id, ?),
                    repo_id        = COALESCE(repo_id, ?),
                    title          = COALESCE(NULLIF(title, ''), ?),
                    status         = COALESCE(NULLIF(status, ''), ?),
                    last_active_at = COALESCE(last_active_at, ?)
                WHERE session_id = ?
                """,
                (
                    legacy_id,
                    repo_id,
                    _session_title(goal, slug),
                    _status_for(row["current_node_id"]),
                    row["updated_at"],
                    row["session_id"],
                ),
            )

    return report


def _print(report: dict) -> None:
    print("APPLYING" if report["applied"] else "DRY RUN - nothing will change")
    print()
    if report.get("error"):
        print(f"  error: {report['error']}")
        return
    print(f"  database              {report['db']}")
    print(f"  sessions              {report['sessions_total']}")
    print(f"    to assign           {report['sessions_assigned']}")
    print(f"    already owned       {report['sessions_already_owned']}")
    print(f"  repositories          {report['repositories_total']}")
    print(f"  titles to set         {report['titles_set']}")
    print(f"  status to set         {report['status_set']}")
    print(f"  last_active to set    {report['last_active_set']}")
    print(f"  legacy user           {report['legacy_user_id']}")
    if report["unmappable_repo_urls"]:
        print("  repo_urls with no repository row (sessions still work):")
        for url in report["unmappable_repo_urls"]:
            print(f"    {url}")
    if not report["applied"]:
        print("\nRe-run with --apply to perform the migration.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    args = parser.parse_args()
    _print(migrate(Path(args.db), apply=args.apply))
    return 0


if __name__ == "__main__":
    sys.exit(main())
