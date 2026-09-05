"""Presentation checkpoints — real sessions, duplicated at useful moments.

    uv run python scripts/demo_checkpoints.py import  --from data/rehearsal.db \\
        --session 47dd056f… --db data/demo.db
    uv run python scripts/demo_checkpoints.py snapshot --db data/demo.db \\
        --session 47dd056f… --as "01 · contribution scope"
    uv run python scripts/demo_checkpoints.py list     --db data/demo.db

## What a checkpoint is, and what it is not

It is a **copy of a real session**, produced by the real pipeline and persisted
through the normal product path. Every row is one the product wrote. Opening a
checkpoint is opening a session: same routes, same rendering, same learning
engine, nothing branching on "is this a demo".

It is NOT a restore point. There is no `restore` verb, and that is the design:

  - a restore can fail halfway through, in front of an audience;
  - a restore mutates the thing you are standing on, so a mistake is
    unrecoverable without a second mechanism.

Duplicating instead makes each checkpoint immutable. Dirtying one during a
rehearsal costs nothing — snapshot a fresh copy from the pristine source. The
dashboard becomes the checkpoint menu, and moving between them is opening a URL.

## Generic on purpose

Nothing here knows about any particular repository, task or candidate. It copies
whichever session you name. The session-scoped tables are DISCOVERED from the
schema — any table with a `session_id` column is carried — so a table added
later is copied without this file changing.

## The one subtlety: node ids are globally unique

`nodes` is keyed on `node_id` alone, so a duplicate session cannot reuse them.
Ids are remapped, and the remap is applied as a TEXTUAL substitution over every
copied value rather than to a list of known columns. Node ids are uuid4 hex, so
a false match is not possible, and JSON payloads that reference them —
`journey_events`, `arrival`, the tutor transcript, anything added tomorrow —
are carried correctly without anyone having to remember they exist.

REFUSES `data/sessions.db`, like every other script here: it writes sessions, and
pointing it at the real database would put demo rows in the corpus behind
`docs/planning/phases/evidence/`.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sqlite3
import sys
import uuid
from pathlib import Path

REAL_DB = "sessions.db"

# Tables that are not session-scoped but that a copied session still needs to
# work: the account that owns it, and the cached survey its welcome page and
# skipped-areas list read. Carried on `import`, never duplicated by `snapshot`.
SHARED_TABLES = ("users", "auth_identities", "repo_survey", "repositories")

_UUID_HEX = re.compile(r"^[0-9a-f]{32}$")


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = OFF")
    return connection


def _refuse_real(path: Path) -> None:
    if path.name == REAL_DB:
        raise SystemExit(
            f"refusing to write {path} — that is the irreplaceable corpus. "
            f"Use a dedicated database such as data/demo.db."
        )


def _tables(connection: sqlite3.Connection) -> list[str]:
    return [
        row["name"] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]


def _columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]


def session_tables(connection: sqlite3.Connection) -> list[str]:
    """Every table carrying a `session_id`, discovered rather than listed."""
    return [
        table for table in _tables(connection)
        if "session_id" in _columns(connection, table)
    ]


def _ensure_schema(source: sqlite3.Connection, target: sqlite3.Connection) -> None:
    """Create in `target` whatever `source` has and it does not."""
    for row in source.execute(
        "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL "
        "AND name NOT LIKE 'sqlite_%'"
    ):
        try:
            target.execute(row["sql"].replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ")
                           .replace("CREATE INDEX ", "CREATE INDEX IF NOT EXISTS ")
                           .replace("CREATE UNIQUE INDEX ", "CREATE UNIQUE INDEX IF NOT EXISTS "))
        except sqlite3.OperationalError as exc:
            if "already exists" not in str(exc).lower():
                raise


def _node_ids(connection: sqlite3.Connection, session_id: str) -> list[str]:
    try:
        return [
            row["node_id"] for row in connection.execute(
                "SELECT node_id FROM nodes WHERE session_id = ?", (session_id,)
            )
        ]
    except sqlite3.OperationalError:
        return []


def _rewrite(value, mapping: dict[str, str]):
    """Apply the id remap to one column value.

    Textual, and deliberately so: a node id appears in `nodes.node_id`, in two
    edge tables, in `sessions.current_node_id` and inside several JSON payloads.
    Substituting over the whole value catches all of them, including the ones
    nobody remembers.
    """
    if not isinstance(value, str):
        return value
    for old, new in mapping.items():
        if old in value:
            value = value.replace(old, new)
    return value


def _copy_session(
    source: sqlite3.Connection,
    target: sqlite3.Connection,
    session_id: str,
    new_session_id: str,
    title: str | None,
) -> dict[str, int]:
    """Copy one session's rows, remapping the session id and every node id."""
    mapping = {session_id: new_session_id}
    for node_id in _node_ids(source, session_id):
        # Only remap what looks like a generated id. A column holding something
        # else that happens to be called `node_id` is left alone.
        if _UUID_HEX.match(node_id):
            mapping[node_id] = uuid.uuid4().hex

    counts: dict[str, int] = {}
    for table in session_tables(source):
        columns = _columns(source, table)
        rows = list(source.execute(
            f"SELECT * FROM {table} WHERE session_id = ?", (session_id,)
        ))
        if not rows:
            continue
        payload = []
        for row in rows:
            values = [_rewrite(row[column], mapping) for column in columns]
            if title is not None and table == "sessions" and "title" in columns:
                values[columns.index("title")] = title
            payload.append(tuple(values))
        placeholders = ", ".join("?" * len(columns))
        target.executemany(
            f"INSERT OR REPLACE INTO {table} ({', '.join(columns)}) "
            f"VALUES ({placeholders})",
            payload,
        )
        counts[table] = len(payload)
    return counts


def _purge_session(target: sqlite3.Connection, session_id: str) -> None:
    """Remove every trace of one session from the target.

    RE-IMPORTING IS A RESTORE, and a restore has to REPLACE. `_copy_session`
    mints a fresh `node_id` for every node — which is what makes a snapshot
    independent of the checkpoint it came from — so importing a session whose id
    already exists in the target inserts a SECOND full set of nodes under ids
    nothing collides with. `INSERT OR REPLACE` replaces only the `sessions` row,
    whose primary key did not change.

    That is not hypothetical: restoring checkpoint `03` after a stray click left
    it with 24 nodes and 12 distinct titles, and every stop appeared twice in the
    route. The old idempotency test missed it by counting `sessions` alone.
    """
    for table in session_tables(target):
        target.execute(f"DELETE FROM {table} WHERE session_id = ?", (session_id,))


def _copy_shared(source: sqlite3.Connection, target: sqlite3.Connection) -> None:
    for table in SHARED_TABLES:
        if table not in _tables(source) or table not in _tables(target):
            continue
        columns = _columns(source, table)
        rows = [tuple(row[c] for c in columns) for row in
                source.execute(f"SELECT * FROM {table}")]
        if not rows:
            continue
        target.executemany(
            f"INSERT OR REPLACE INTO {table} ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' * len(columns))})",
            rows,
        )


# ── verbs ─────────────────────────────────────────────────────────────────────


def do_import(args) -> int:
    source_path, target_path = Path(args.source).resolve(), Path(args.db).resolve()
    _refuse_real(target_path)
    if not source_path.exists():
        raise SystemExit(f"{source_path} does not exist")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    fresh = not target_path.exists()
    source, target = _connect(source_path), _connect(target_path)
    try:
        _ensure_schema(source, target)
        _copy_shared(source, target)
        for session_id in args.session:
            # A restore replaces; see `_purge_session`. Harmless when the target
            # has never seen this session.
            _purge_session(target, session_id)
            counts = _copy_session(source, target, session_id, session_id, None)
            if not counts:
                print(f"  {session_id[:8]}  NOT FOUND in {source_path.name}")
                continue
            print(f"  {session_id[:8]}  " +
                  "  ".join(f"{t}={n}" for t, n in sorted(counts.items())))
        target.commit()
    finally:
        source.close(); target.close()
    print(f"{'created' if fresh else 'updated'} {target_path}")
    return 0


def do_snapshot(args) -> int:
    db_path = Path(args.db).resolve()
    _refuse_real(db_path)
    connection = _connect(db_path)
    try:
        new_id = uuid.uuid4().hex
        counts = _copy_session(connection, connection, args.session, new_id, args.name)
        if not counts:
            raise SystemExit(f"session {args.session} not found in {db_path}")
        connection.commit()
    finally:
        connection.close()
    print(f"{args.name}")
    print(f"  session_id  {new_id}")
    print(f"  copied      " + "  ".join(f"{t}={n}" for t, n in sorted(counts.items())))
    return 0


def do_list(args) -> int:
    db_path = Path(args.db).resolve()
    if not db_path.exists():
        raise SystemExit(f"{db_path} does not exist")
    connection = _connect(db_path)
    try:
        rows = list(connection.execute(
            "SELECT session_id, title, goal_json, status, updated_at "
            "FROM sessions ORDER BY COALESCE(title, ''), updated_at"
        ))
        for row in rows:
            import json
            goal = json.loads(row["goal_json"] or "{}")
            stage = "—"
            try:
                raw = connection.execute(
                    "SELECT contribution_json FROM sessions WHERE session_id = ?",
                    (row["session_id"],)
                ).fetchone()[0]
                if raw:
                    stage = json.loads(raw).get("stage", "—")
            except (sqlite3.OperationalError, TypeError, ValueError):
                pass
            nodes = connection.execute(
                "SELECT COUNT(*) FROM nodes WHERE session_id = ?", (row["session_id"],)
            ).fetchone()[0]
            print(f"{row['session_id']}  {(row['title'] or '(untitled)'):<34} "
                  f"{goal.get('goal_type', '?'):<24} stage={stage:<10} nodes={nodes}")
    finally:
        connection.close()
    return 0


def do_backup(args) -> int:
    """A file copy of the whole demo database, for the pristine spare."""
    db_path = Path(args.db).resolve()
    out = Path(args.out).resolve()
    if not db_path.exists():
        raise SystemExit(f"{db_path} does not exist")
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_path, out)
    print(f"copied {db_path} -> {out}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="verb", required=True)

    p = sub.add_parser("import", help="copy real sessions into a demo database")
    p.add_argument("--from", dest="source", required=True)
    p.add_argument("--session", nargs="+", required=True)
    p.add_argument("--db", default="data/demo.db")
    p.set_defaults(func=do_import)

    p = sub.add_parser("snapshot", help="duplicate a session as a named checkpoint")
    p.add_argument("--db", default="data/demo.db")
    p.add_argument("--session", required=True)
    p.add_argument("--as", dest="name", required=True)
    p.set_defaults(func=do_snapshot)

    p = sub.add_parser("list", help="what is in the demo database")
    p.add_argument("--db", default="data/demo.db")
    p.set_defaults(func=do_list)

    p = sub.add_parser("backup", help="file copy of the whole demo database")
    p.add_argument("--db", default="data/demo.db")
    p.add_argument("--out", required=True)
    p.set_defaults(func=do_backup)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
