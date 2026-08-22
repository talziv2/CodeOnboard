# SQLite persistence for the learning graph.
#
# One file (data/sessions.db) with five tables: sessions, nodes, edges — the LIVE
# graph — and plan_nodes, plan_edges, which hold the ORIGINAL PLAN.
# Standard-library sqlite3 only — no new dependency.
#
# Schema versioning: the sessions row carries `schema_version`. A mismatch
# means the row was written by a different schema; load_graph treats it as
# missing (returns None) rather than trying to migrate. Bump SCHEMA_VERSION
# when the on-disk shape changes; old rows become invisible to the new code.
#
# ── THE TWO SIDES OF THIS FILE (session-reset.md) ─────────────────────────────
#
# `nodes` / `edges` are the LIVE graph, and learning mutates them freely:
# priorities move, warm-ups are spliced in, lessons are re-taught, answers and
# gaps accumulate.
#
# `plan_nodes` / `plan_edges` are what the planner produced, before the learner
# touched it. They exist so `Start over` can RESTORE the plan rather than
# reconstruct it by inverting every mutation — the rejected design, and why it
# was rejected, are in session-reset.md §1. For this module it reduces to one
# rule, and the rule is the whole contract:
#
#     `save_graph` NEVER writes a plan table. The only writers are
#     `create_session` — once, in the same transaction as the session itself —
#     and `record_plan_lesson`, which is physically unable to overwrite.
#
# Two further properties are deliberate:
#
#   - The plan tables' COLUMN LIST *is* the plan/state partition. It is not a
#     frozenset in a test file, because the boundary should be readable in
#     `.schema` by someone who has never seen the phase doc.
#   - Their primary key is `(session_id, node_id)`, not the live `nodes` table's
#     global `(node_id)`. That global key is the reason a plan cannot be copied
#     into a second session today; it is not repeated here.
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


# 3: the plan tables. Bumped rather than added additively, because a session
# written before them has NO PLAN — and a session whose plan cannot be restored
# is one where `Start over` is a button that cannot work. Invisible-and-honest
# beats loadable-and-half-broken (session-reset.md D8). The v2 fixtures the
# measurement scripts pin were copied to `data/sessions-fixtures.db` first.
SCHEMA_VERSION = 3
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


# ── the original plan ─────────────────────────────────────────────────────────
#
# A mirror of `nodes` with every LEARNER-STATE column removed, plus `lesson_json`
# for the unit's first rendered lesson. Reading the two CREATE statements side by
# side is the fastest way to see what this system considers plan and what it
# considers state.
#
# `lesson_json` is NULL at creation because lessons are rendered lazily, one stop
# at a time, long after planning. It is filled exactly once, by
# `record_plan_lesson`. See that function for why the plan is append-only rather
# than sealed, and for the four properties that keep "append-only" from meaning
# "mutable".
_CREATE_PLAN_NODES = """
CREATE TABLE IF NOT EXISTS plan_nodes (
    session_id        TEXT NOT NULL,
    node_id           TEXT NOT NULL,
    title             TEXT NOT NULL,
    file              TEXT NOT NULL,
    line_start        INTEGER NOT NULL,
    line_end          INTEGER NOT NULL,
    symbol            TEXT,
    concept_tags_json TEXT NOT NULL,
    lesson_brief_json TEXT NOT NULL,
    lesson_json       TEXT,
    PRIMARY KEY (session_id, node_id),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
)
"""

_CREATE_PLAN_EDGES = """
CREATE TABLE IF NOT EXISTS plan_edges (
    session_id   TEXT NOT NULL,
    from_node_id TEXT NOT NULL,
    to_node_id   TEXT NOT NULL,
    kind         TEXT NOT NULL,
    PRIMARY KEY (session_id, from_node_id, to_node_id, kind),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
)
"""


# How long a connection waits for a write lock before giving up. Five seconds is
# chosen against what actually contends here: `save_graph` rewrites every node
# and edge of one session, which is milliseconds at these sizes, so anything
# short of a stuck process clears well inside the window — and a caller that
# does wait five seconds is better served by a slow response than by an error.
BUSY_TIMEOUT_MS = 5000


def _configure(conn: sqlite3.Connection) -> None:
    """The pragmas every connection to this database needs.

    ## Why WAL, and why it is a multi-user concern rather than a tuning knob

    SQLite's default rollback journal takes an exclusive lock on the whole
    database for the duration of a write, and readers are locked out while it is
    held. With one learner that is invisible — there is never a second request in
    flight. With two, one learner submitting an answer blocks the other's page
    load, and with the default `busy_timeout` of ZERO the blocked one does not
    wait at all: it raises `database is locked` immediately.

    WAL lets readers run concurrently with a writer, so the common collision —
    someone reading while someone else writes — stops being a collision. Two
    simultaneous *writers* still serialise, which is what `busy_timeout` is for:
    wait for the lock instead of failing on it.

    `journal_mode` is persistent — a property of the database file, not the
    connection — so setting it on every connect is idempotent and costs one
    pragma. It is done here anyway rather than once at startup, because the test
    suite creates fresh databases constantly and "the file was made by whichever
    code path got there first" is not a property worth relying on.

    `survey_store` and `dossier_store` import this rather than restating it: they
    write the same file, and two modules configuring one database differently is
    the kind of disagreement that surfaces as `database is locked` from only one
    of them.
    """
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.Error:
        # WAL is unavailable on some network filesystems. The default journal
        # still works — it is only less concurrent — so this must not be the
        # thing that stops the app from starting.
        pass


@contextmanager
def _connect(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=BUSY_TIMEOUT_MS / 1000)
    _configure(conn)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


_ADDITIVE_COLUMNS: tuple[tuple[str, str, str], ...] = (
    # The Documentation Agent's context, carried on the session so Teaching can
    # reach it when state is reconstructed from the persisted graph.
    ("sessions", "doc_context_json", "TEXT"),
    # Per-node answer history. Existing sessions simply start with none.
    ("nodes", "attempts_json", "TEXT"),
    # Symbol identity alongside the resolved line range (repo-understanding
    # Stage 0). Nodes written before symbol resolution load with symbol = NULL.
    ("nodes", "symbol", "TEXT"),
    # The curriculum's area list — the ONE additive column the learning-engine
    # phase spends (LD6). Everything else it needed (objective, kind, priority,
    # area_id, anchors, gap_kind) went into JSON payloads that already existed,
    # because nothing queries by them. Areas get a column only because they
    # belong to the session rather than to any one node.
    ("sessions", "areas_json", "TEXT"),
    # Outstanding gaps and the per-node remediation counter (gap-model.md M1).
    #
    # Written and read UNCONDITIONALLY. `CODEONBOARD_GAPS` gates behaviour, never
    # storage (gap-model.md §3.8): a flag-off save that loads a gap-bearing
    # graph, changes something unrelated and writes it back must not destroy the
    # gaps. Making persistence conditional is the one way to break that, so this
    # path does not read the flag at all — and a test asserts that structurally,
    # so the contract cannot rot.
    ("nodes", "gaps_json", "TEXT"),
    # PLAN-SCOPED history — prune-ahead, scope changes, remediation insertions
    # (learning-graph.md M2). A column for exactly the reason `areas_json` got
    # one: it belongs to the SESSION rather than to any one node.
    ("sessions", "journey_events_json", "TEXT"),
    # The welcome briefing, session-scoped for the same reason. A graph written
    # before the welcome page loads with briefing = None.
    ("sessions", "briefing_json", "TEXT"),
    # How the learner reached the current stop, when that is worth a notice. A
    # session column rather than a node one because it describes the session's
    # POSITION, not any unit.
    ("sessions", "arrival_json", "TEXT"),
)


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    """Apply `_ADDITIVE_COLUMNS`, skipping the ones already there.

    Every column here is additive and nullable, which is what lets
    SCHEMA_VERSION stay put: `load_graph` treats a version mismatch as MISSING,
    so bumping it would make every session written before the bump invisible
    rather than migrating it.

    ## Why this asks first instead of trying and swallowing

    Each of these used to be its own `try: ALTER … except Exception: pass`, on
    the reasoning that SQLite has no `ADD COLUMN IF NOT EXISTS` and the error it
    raises for an existing column is harmless.

    That is right about the error it was written for and wrong about every other
    error `ALTER TABLE` can raise — and one of those became reachable the moment
    this database got a second concurrent writer. `database is locked` is an
    `OperationalError` too, so under contention a bare `except` silently skips
    the column, `init_db` reports success, and the very next `save_graph` fails
    on a column that does not exist. A migration that can half-apply itself and
    say nothing is the worst possible shape for one.

    ## And why the duplicate-column error is STILL tolerated

    Checking first is a check-then-act, and `init_db` runs on every `save_graph`,
    so two concurrent first-writes can both read "absent" and both ALTER. The
    second loses with `duplicate column name: areas_json` — reproduced
    intermittently by `test_concurrent_writers_all_succeed` the first time this
    file had genuinely concurrent writers, and invisible before only because the
    blanket catch was swallowing it.

    So exactly one message is tolerated: the one that means "another writer
    already did this", which is a success, just not ours. Everything else
    propagates, which is the whole point of having narrowed the catch.
    """
    for table in ("sessions", "nodes"):
        present = _existing_columns(conn, table)
        for target_table, column, column_type in _ADDITIVE_COLUMNS:
            if target_table != table or column in present:
                continue
            try:
                conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {column_type}"
                )
            except sqlite3.OperationalError as exc:
                # Message sniffing, because SQLite gives no error code that
                # distinguishes this from any other OperationalError. Narrow on
                # purpose: anything else is re-raised.
                if "duplicate column name" not in str(exc).lower():
                    raise


def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    with _connect(db_path) as conn:
        conn.execute(_CREATE_SESSIONS)
        conn.execute(_CREATE_SESSIONS_INDEX)
        conn.execute(_CREATE_NODES)
        conn.execute(_CREATE_NODES_INDEX)
        conn.execute(_CREATE_EDGES)
        conn.execute(_CREATE_PLAN_NODES)
        conn.execute(_CREATE_PLAN_EDGES)
        # The eight additive columns this used to add with eight
        # `try: ALTER … except Exception: pass` blocks. `_add_missing_columns`
        # applies exactly the same eight — verified column by column against the
        # chain it replaces — and differs only in HOW it tolerates a column that
        # is already there: it reads `PRAGMA table_info` first and then swallows
        # nothing but `duplicate column name`.
        #
        # That distinction is why the chain went rather than the helper. A bare
        # `except Exception` also swallows `database is locked`, which became
        # reachable the moment this file got a second concurrent writer: the
        # column is silently skipped, `init_db` reports success, and the next
        # `save_graph` fails on a column that does not exist.
        _add_missing_columns(conn)


def save_graph(graph: LearningGraph, db_path: Path = DEFAULT_DB_PATH) -> None:
    """Persist the LIVE graph. Never touches a plan table — see the header."""
    init_db(db_path)
    with _connect(db_path) as conn:
        _write_graph(conn, graph)


def create_session(graph: LearningGraph, db_path: Path = DEFAULT_DB_PATH) -> None:
    """Persist a NEWLY PLANNED graph, and its plan, in ONE transaction.

    The only writer of `plan_nodes` / `plan_edges` apart from
    `record_plan_lesson`, and the reason it exists rather than being two calls to
    two functions: **a session that exists without a plan is a session where
    `Start over` cannot work**, and that has to be unrepresentable rather than
    merely unlikely. Two transactions would leave a window — a crash, a killed
    process, a raised exception between them — where exactly that session exists
    on disk, permanently, with no way to notice.

    Every other caller keeps using `save_graph`. A graph that is *saved* rather
    than *created* has a plan already, and rewriting it is the one thing this
    module must never do.
    """
    init_db(db_path)
    with _connect(db_path) as conn:
        _write_graph(conn, graph)
        _write_plan(conn, graph)


def _write_graph(conn: sqlite3.Connection, graph: LearningGraph) -> None:
    """The live-side write, without its own transaction.

    Extracted so `create_session` can put it and the plan write inside one
    transaction. It takes a connection rather than a path for exactly that
    reason, and it is private because no caller outside this module should be
    choosing its own transaction boundary here.
    """
    conn.execute(
        """
        INSERT INTO sessions
            (session_id, repo_url, goal_json, current_node_id,
             doc_context_json, areas_json, journey_events_json, briefing_json,
             arrival_json, schema_version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            repo_url            = excluded.repo_url,
            goal_json           = excluded.goal_json,
            current_node_id     = excluded.current_node_id,
            doc_context_json    = excluded.doc_context_json,
            areas_json          = excluded.areas_json,
            journey_events_json = excluded.journey_events_json,
            briefing_json       = excluded.briefing_json,
            arrival_json        = excluded.arrival_json,
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
            json.dumps(graph.arrival) if graph.arrival is not None else None,
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


def _write_plan(conn: sqlite3.Connection, graph: LearningGraph) -> None:
    """The plan-side write. Called ONCE per session, from `create_session`.

    `INSERT OR IGNORE`, not a plain INSERT and not an upsert. If this ever runs
    twice for the same session — a retry, a caller that should not exist — the
    second run must be a no-op rather than either an exception or an overwrite.
    Refusing to overwrite is the property; failing loudly on a duplicate would
    only convert a silent corruption into a broken request, and the plan being
    already-written is not an error.
    """
    conn.executemany(
        """
        INSERT OR IGNORE INTO plan_nodes (
            session_id, node_id, title, file, line_start, line_end,
            symbol, concept_tags_json, lesson_brief_json, lesson_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """,
        [
            (
                graph.session_id,
                node.id,
                node.title,
                node.code_anchor.file,
                node.code_anchor.line_start,
                node.code_anchor.line_end,
                node.code_anchor.symbol,
                json.dumps(node.concept_tags),
                json.dumps(node.lesson_brief),
            )
            for node in graph.nodes.values()
        ],
    )
    conn.executemany(
        """
        INSERT OR IGNORE INTO plan_edges (session_id, from_node_id, to_node_id, kind)
        VALUES (?, ?, ?, ?)
        """,
        [
            (graph.session_id, e.from_node_id, e.to_node_id, e.kind)
            for e in graph.edges
        ],
    )


def record_plan_lesson(
    session_id: str,
    node_id: str,
    lesson: dict,
    db_path: Path = DEFAULT_DB_PATH,
) -> bool:
    """Fill this unit's ORIGINAL lesson slot. At most once, ever.

    Lessons are rendered lazily, one stop at a time, so the plan cannot carry
    them at creation. This is what makes the plan **append-only rather than
    sealed** — and the four properties below are what keep "append-only" from
    quietly meaning "mutable":

      1. `WHERE lesson_json IS NULL` makes overwriting *physically impossible*,
         not merely unattempted. It also removes the read-modify-write a single
         JSON blob would have needed, so two stops rendering concurrently cannot
         lose one another's lesson.
      2. Only a SUCCESSFUL render calls this. A Teaching failure leaves the slot
         NULL so a later render can fill it, rather than sealing "this lesson
         could not be generated" into the plan forever. That is strictly better
         than the live side, where the fallback sits in `cached_lesson` until
         something overwrites it.
      3. A re-teach never calls this, and could not overwrite if it did. A node's
         first render can never *be* a re-teach: `/respond` refuses to grade
         without a `cached_lesson`, so a graded answer implies a prior render.
      4. A REMEDIAL node is not in `plan_nodes` at all, so its render matches
         zero rows and is a harmless no-op. This is precisely why the statement
         is an UPDATE and not an upsert — an upsert would quietly add
         learner-created nodes to the plan, and `Start over` would then restore
         the warm-ups it exists to remove.

    Returns whether this call was the one that filled the slot, so a caller can
    log it. Nothing depends on the return value.
    """
    if not db_path.exists():
        return False
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE plan_nodes SET lesson_json = ?
             WHERE session_id = ? AND node_id = ? AND lesson_json IS NULL
            """,
            (json.dumps(lesson), session_id, node_id),
        )
        return cursor.rowcount > 0


def load_plan(session_id: str, db_path: Path = DEFAULT_DB_PATH) -> LearningGraph | None:
    """The graph AS PLANNED — the restore source for `Start over`.

    Every learner-state field is at its dataclass default, because the plan
    tables have no column for any of them. That is the point, and it is why a new
    state field on `LearningNode` needs no reset code: whatever it is, it lands
    here at its default by construction.

    `cached_lesson` comes from `lesson_json`, so a restored graph reads with the
    ORIGINAL prose rather than a re-taught replacement — and with None for any
    stop the learner never reached, which is exactly the state a fresh session is
    in for those stops.

    The session-level columns come from the same `sessions` row the live graph
    uses (`repo_url`, `goal`, `doc_context`, `areas`, `briefing`), because
    nothing in the learning loop writes them and duplicating them into the plan
    would create two copies that could disagree. `current_node_id`, `arrival` and
    `journey_events` are deliberately NOT carried across: they are the session's
    position and history, which is what a reset discards.

    Returns None when the session is absent, is a different schema version, or
    has no plan rows — the last being every pre-v3 session (D8). The caller
    decides what to do about it; this does not reconstruct anything.
    """
    if not db_path.exists():
        return None
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        session_row = conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if session_row is None or session_row["schema_version"] != SCHEMA_VERSION:
            return None

        node_rows = conn.execute(
            "SELECT * FROM plan_nodes WHERE session_id = ?", (session_id,)
        ).fetchall()
        if not node_rows:
            return None

        raw_doc = session_row["doc_context_json"]
        graph = LearningGraph(
            repo_url=session_row["repo_url"],
            goal=json.loads(session_row["goal_json"]),
            session_id=session_row["session_id"],
            doc_context=json.loads(raw_doc) if raw_doc is not None else None,
            areas=_json_or_default(session_row, "areas_json", []),
            briefing=_json_or_default(session_row, "briefing_json", None),
        )
        for row in node_rows:
            graph.nodes[row["node_id"]] = _row_to_plan_node(row)
        for row in conn.execute(
            "SELECT * FROM plan_edges WHERE session_id = ?", (session_id,)
        ):
            graph.edges.append(
                LearningEdge(
                    from_node_id=row["from_node_id"],
                    to_node_id=row["to_node_id"],
                    kind=row["kind"],
                )
            )
        return graph


def _row_to_plan_node(row: sqlite3.Row) -> LearningNode:
    """A planned node: plan columns from the row, everything else at its default.

    Every learner-state argument is left unpassed rather than passed explicitly
    as a default value. If `LearningNode` grows a state field, this function is
    already correct for it — spelling the defaults out here would mean a second
    place that has to be remembered.
    """
    return LearningNode(
        id=row["node_id"],
        title=row["title"],
        code_anchor=CodeAnchor(
            file=row["file"],
            line_start=row["line_start"],
            line_end=row["line_end"],
            symbol=row["symbol"],
        ),
        concept_tags=json.loads(row["concept_tags_json"]),
        lesson_brief=json.loads(row["lesson_brief_json"]),
        cached_lesson=_json_or_default(row, "lesson_json", None),
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
            arrival=_json_or_default(session_row, "arrival_json", None),
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
