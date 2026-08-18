# SQLite persistence for the learning graph.
#
# One file (data/sessions.db) with three tables: sessions, nodes, edges.
# Standard-library sqlite3 only — no new dependency.
#
# Schema versioning: the sessions row carries `schema_version`. A mismatch
# means the row was written by a different schema; load_graph treats it as
# missing (returns None) rather than trying to migrate. Bump SCHEMA_VERSION
# when the on-disk shape changes; old rows become invisible to the new code.
#
# Phase 3 Part 1 scope: single-user, repo URLs stored as-is. Multi-user
# identity and URL normalization are deferred to Part 7 — they belong with
# the resume flow that actually needs them.

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from backend.learning.gaps import GapState
from backend.learning.graph import (
    CodeAnchor,
    LearningEdge,
    LearningGraph,
    LearningNode,
)


SCHEMA_VERSION = 2
DEFAULT_DB_PATH = Path("data/sessions.db")


_CREATE_SESSIONS = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id       TEXT PRIMARY KEY,
    repo_url         TEXT NOT NULL,
    goal_json        TEXT NOT NULL,
    current_node_id  TEXT,
    doc_context_json TEXT,
    schema_version   INTEGER NOT NULL,
    created_at       TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
    updated_at       TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now'))
)
"""

_CREATE_SESSIONS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_sessions_repo ON sessions (repo_url)
"""

_CREATE_NODES = """
CREATE TABLE IF NOT EXISTS nodes (
    node_id              TEXT NOT NULL,
    session_id           TEXT NOT NULL,
    title                TEXT NOT NULL,
    file                 TEXT NOT NULL,
    line_start           INTEGER NOT NULL,
    line_end             INTEGER NOT NULL,
    concept_tags_json    TEXT NOT NULL,
    lesson_brief_json    TEXT NOT NULL,
    understanding_state  TEXT NOT NULL,
    visited              INTEGER NOT NULL,
    weak_spot            INTEGER NOT NULL,
    user_override        TEXT,
    cached_lesson_json   TEXT,
    symbol               TEXT,
    PRIMARY KEY (node_id),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
)
"""

_CREATE_NODES_INDEX = """
CREATE INDEX IF NOT EXISTS idx_nodes_session ON nodes (session_id)
"""

_CREATE_EDGES = """
CREATE TABLE IF NOT EXISTS edges (
    session_id   TEXT NOT NULL,
    from_node_id TEXT NOT NULL,
    to_node_id   TEXT NOT NULL,
    kind         TEXT NOT NULL,
    PRIMARY KEY (session_id, from_node_id, to_node_id, kind),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
)
"""


@contextmanager
def _connect(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    with _connect(db_path) as conn:
        conn.execute(_CREATE_SESSIONS)
        conn.execute(_CREATE_SESSIONS_INDEX)
        conn.execute(_CREATE_NODES)
        conn.execute(_CREATE_NODES_INDEX)
        conn.execute(_CREATE_EDGES)
        # Add the doc_context_json column to existing databases that were
        # created before schema v2. SQLite has no ADD COLUMN IF NOT EXISTS,
        # so we catch the OperationalError that fires when the column already
        # exists rather than checking first.
        try:
            conn.execute("ALTER TABLE sessions ADD COLUMN doc_context_json TEXT")
        except Exception:
            pass
        # Same additive trick for the per-node answer history. Adding a column
        # rather than bumping SCHEMA_VERSION keeps existing sessions loadable —
        # they simply start with an empty history.
        try:
            conn.execute("ALTER TABLE nodes ADD COLUMN attempts_json TEXT")
        except Exception:
            pass
        # Symbol identity alongside the resolved line range (Stage 0 of the
        # repo-understanding migration). Additive and nullable for the same
        # reason as the columns above: sessions written before symbol resolution
        # existed still load, with symbol = NULL.
        try:
            conn.execute("ALTER TABLE nodes ADD COLUMN symbol TEXT")
        except Exception:
            pass
        # The curriculum's area list — the ONE additive column the learning-engine
        # phase spends (LD6). Everything else it needed (objective, kind,
        # priority, area_id, anchors, gap_kind) went into JSON payloads that
        # already existed, because nothing queries by them. Areas get a column
        # only because they belong to the session rather than to any one node.
        try:
            conn.execute("ALTER TABLE sessions ADD COLUMN areas_json TEXT")
        except Exception:
            pass
        # Outstanding gaps and the per-node remediation counter (gap-model.md
        # M1). Additive and nullable like every column above, so SCHEMA_VERSION
        # does not move and a graph written before the gap model loads with an
        # empty GapState — which reads correctly as "no outstanding gaps".
        #
        # Written and read UNCONDITIONALLY. `CODEONBOARD_GAPS` gates behaviour,
        # never storage (gap-model.md §3.8): a flag-off save that loads a
        # gap-bearing graph, changes something unrelated and writes it back must
        # not destroy the gaps. Making persistence conditional is the one way to
        # break that, so this path does not read the flag at all — and a test
        # asserts that structurally, so the contract cannot rot.
        try:
            conn.execute("ALTER TABLE nodes ADD COLUMN gaps_json TEXT")
        except Exception:
            pass
        # PLAN-SCOPED history — prune-ahead, scope changes, remediation
        # insertions (learning-graph.md M2). A column for exactly the reason
        # `areas_json` got one: it belongs to the SESSION rather than to any one
        # node, so there is no node payload it could ride in, and the only
        # session payloads that exist are owned by other producers (`goal_json`
        # is the agents' source of truth, `doc_context_json` the Documentation
        # Agent's). Nothing queries it, so it stays JSON in one column rather
        # than becoming a table.
        try:
            conn.execute("ALTER TABLE sessions ADD COLUMN journey_events_json TEXT")
        except Exception:
            pass
        # The welcome briefing, for the same reason `areas_json` gets a column:
        # it belongs to the SESSION, not to any node, and the session payloads
        # that already exist are owned by other producers. Additive and nullable,
        # so a graph written before the welcome page loads with briefing = None
        # and simply writes one the first time that page is opened.
        try:
            conn.execute("ALTER TABLE sessions ADD COLUMN briefing_json TEXT")
        except Exception:
            pass


def save_graph(graph: LearningGraph, db_path: Path = DEFAULT_DB_PATH) -> None:
    init_db(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sessions
                (session_id, repo_url, goal_json, current_node_id,
                 doc_context_json, areas_json, journey_events_json, briefing_json,
                 schema_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                repo_url            = excluded.repo_url,
                goal_json           = excluded.goal_json,
                current_node_id     = excluded.current_node_id,
                doc_context_json    = excluded.doc_context_json,
                areas_json          = excluded.areas_json,
                journey_events_json = excluded.journey_events_json,
                briefing_json       = excluded.briefing_json,
                schema_version      = excluded.schema_version,
                updated_at       = strftime('%Y-%m-%d %H:%M:%f', 'now')
            """,
            (
                graph.session_id,
                graph.repo_url,
                json.dumps(graph.goal),
                graph.current_node_id,
                json.dumps(graph.doc_context) if graph.doc_context is not None else None,
                json.dumps(graph.areas) if graph.areas else None,
                json.dumps(graph.journey_events) if graph.journey_events else None,
                json.dumps(graph.briefing) if graph.briefing is not None else None,
                SCHEMA_VERSION,
            ),
        )
        # Nodes and edges: replace wholesale rather than diff. Sessions are
        # small (under a hundred nodes) and writes happen at human cadence
        # (one per user action), so the simplicity wins over efficiency.
        conn.execute("DELETE FROM nodes WHERE session_id = ?", (graph.session_id,))
        conn.execute("DELETE FROM edges WHERE session_id = ?", (graph.session_id,))
        conn.executemany(
            """
            INSERT INTO nodes (
                node_id, session_id, title, file, line_start, line_end,
                concept_tags_json, lesson_brief_json, understanding_state,
                visited, weak_spot, user_override, cached_lesson_json,
                attempts_json, symbol, gaps_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [_node_row(graph.session_id, n) for n in graph.nodes.values()],
        )
        conn.executemany(
            "INSERT INTO edges (session_id, from_node_id, to_node_id, kind) VALUES (?, ?, ?, ?)",
            [(graph.session_id, e.from_node_id, e.to_node_id, e.kind) for e in graph.edges],
        )


def load_graph(session_id: str, db_path: Path = DEFAULT_DB_PATH) -> LearningGraph | None:
    if not db_path.exists():
        return None
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        session_row = conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if session_row is None:
            return None
        if session_row["schema_version"] != SCHEMA_VERSION:
            # Different schema — treat as missing. No silent migration.
            return None
        raw_doc = session_row["doc_context_json"]
        graph = LearningGraph(
            repo_url=session_row["repo_url"],
            goal=json.loads(session_row["goal_json"]),
            session_id=session_row["session_id"],
            current_node_id=session_row["current_node_id"],
            doc_context=json.loads(raw_doc) if raw_doc is not None else None,
            areas=_json_or_default(session_row, "areas_json", []),
            journey_events=_json_or_default(session_row, "journey_events_json", []),
            briefing=_json_or_default(session_row, "briefing_json", None),
        )
        for node_row in conn.execute(
            "SELECT * FROM nodes WHERE session_id = ?", (session_id,)
        ):
            graph.nodes[node_row["node_id"]] = _row_to_node(node_row)
        for edge_row in conn.execute(
            "SELECT * FROM edges WHERE session_id = ?", (session_id,)
        ):
            graph.edges.append(
                LearningEdge(
                    from_node_id=edge_row["from_node_id"],
                    to_node_id=edge_row["to_node_id"],
                    kind=edge_row["kind"],
                )
            )
        return graph


def list_sessions_for_repo(
    repo_url: str,
    db_path: Path = DEFAULT_DB_PATH,
) -> list[dict]:
    # Lightweight summaries for the future resume UX (Part 7). Exact repo_url
    # match for now — URL normalization is a Part 7 concern.
    if not db_path.exists():
        return []
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT session_id, goal_json, current_node_id, created_at, updated_at
            FROM sessions
            WHERE repo_url = ? AND schema_version = ?
            ORDER BY updated_at DESC
            """,
            (repo_url, SCHEMA_VERSION),
        ).fetchall()
        return [
            {
                "session_id": r["session_id"],
                "goal": json.loads(r["goal_json"]),
                "current_node_id": r["current_node_id"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]


def delete_session(session_id: str, db_path: Path = DEFAULT_DB_PATH) -> None:
    if not db_path.exists():
        return
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))


def _node_row(session_id: str, node: LearningNode) -> tuple:
    return (
        node.id,
        session_id,
        node.title,
        node.code_anchor.file,
        node.code_anchor.line_start,
        node.code_anchor.line_end,
        json.dumps(node.concept_tags),
        json.dumps(node.lesson_brief),
        node.understanding_state,
        1 if node.visited else 0,
        1 if node.weak_spot else 0,
        node.user_override,
        json.dumps(node.cached_lesson) if node.cached_lesson is not None else None,
        json.dumps(node.attempts),
        node.code_anchor.symbol,
        json.dumps(node.gap_state.to_dict()),
    )


def _row_to_node(row: sqlite3.Row) -> LearningNode:
    return LearningNode(
        id=row["node_id"],
        title=row["title"],
        code_anchor=CodeAnchor(
            file=row["file"],
            line_start=row["line_start"],
            line_end=row["line_end"],
            symbol=_column_or_default(row, "symbol", None),
        ),
        concept_tags=json.loads(row["concept_tags_json"]),
        lesson_brief=json.loads(row["lesson_brief_json"]),
        understanding_state=row["understanding_state"],
        visited=bool(row["visited"]),
        weak_spot=bool(row["weak_spot"]),
        user_override=row["user_override"],
        cached_lesson=(
            json.loads(row["cached_lesson_json"])
            if row["cached_lesson_json"] is not None
            else None
        ),
        attempts=_json_or_default(row, "attempts_json", []),
        gap_state=GapState.from_dict(_json_or_default(row, "gaps_json", None)),
    )


def _column_or_default(row: sqlite3.Row, column: str, default):
    # Rows written before the column existed have no key at all when an older DB
    # is opened without the ALTER having run, so degrade to the default.
    try:
        value = row[column]
    except IndexError:
        return default
    return default if value is None else value


def _json_or_default(row: sqlite3.Row, column: str, default):
    raw = _column_or_default(row, column, None)
    return json.loads(raw) if raw else default
