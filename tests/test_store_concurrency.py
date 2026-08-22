"""SQLite concurrency settings for the shared database (multi-user M0).

Run with: uv run pytest tests/test_store_concurrency.py -v

## The failure these prevent

SQLite's default rollback journal takes an exclusive lock on the whole database
while a write is in flight, and the default `busy_timeout` is ZERO — a connection
that finds the database locked does not wait, it raises `database is locked`
immediately.

With one learner there is never a second request in flight, so neither fact is
observable. With two, `save_graph` — which rewrites every node and edge of a
session on every answer, skip, jump and scope change — is a write long enough for
another request to land inside it. The second learner's action fails with an
opaque SQLite error, and the first learner's write is not to blame for anything
except existing at the same time.

WAL removes the common case (a reader concurrent with a writer) and `busy_timeout`
handles the rest (a writer concurrent with a writer) by waiting instead of
failing.

No network, no LLM, no API key: real SQLite against a temp file.
"""
import sqlite3
import threading
from pathlib import Path

import pytest

from backend.learning.store import (
    BUSY_TIMEOUT_MS,
    _connect,
    load_graph,
    save_graph,
)
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.repo import dossier_store, survey_store


@pytest.fixture
def db_path(tmp_path) -> Path:
    return tmp_path / "sessions.db"


def _graph(title: str = "Understand Session") -> LearningGraph:
    graph = LearningGraph(
        repo_url="https://github.com/psf/requests",
        goal={"primary_goal": "understand sessions", "goal_type": "understand_component"},
    )
    node = graph.add_node(LearningNode(
        title=title,
        code_anchor=CodeAnchor(file="requests/sessions.py", line_start=1, line_end=80),
    ))
    graph.set_current(node.id)
    return graph


# --- the pragmas --------------------------------------------------------------

def test_wal_is_enabled_on_the_learning_store(db_path):
    save_graph(_graph(), db_path)

    with _connect(db_path) as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]

    assert mode.lower() == "wal"


def test_busy_timeout_is_set(db_path):
    save_graph(_graph(), db_path)

    with _connect(db_path) as conn:
        timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]

    assert timeout == BUSY_TIMEOUT_MS


def test_foreign_keys_stay_on(db_path):
    # Pre-existing behaviour the new pragmas must not have displaced: the nodes
    # and edges cascade depends on it.
    save_graph(_graph(), db_path)

    with _connect(db_path) as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


@pytest.mark.parametrize(
    "connect",
    [
        pytest.param(lambda p: survey_store._connect(p), id="survey_store"),
        pytest.param(lambda p: dossier_store._connect(p), id="dossier_store"),
    ],
)
def test_the_other_writers_of_this_file_use_the_same_settings(db_path, connect):
    """Three modules write one database.

    If only one of them sets WAL and a busy timeout, the other two still fail the
    way this milestone exists to stop — and they fail intermittently, from a
    module that looks unrelated to the change.
    """
    save_graph(_graph(), db_path)

    conn = connect(db_path)
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == BUSY_TIMEOUT_MS
    finally:
        conn.close()


# --- the behaviour ------------------------------------------------------------

def test_a_reader_is_not_blocked_by_an_open_write(db_path):
    """WAL's whole point: a lesson loading while an answer is being graded."""
    graph = _graph()
    save_graph(graph, db_path)

    holder = sqlite3.connect(db_path, timeout=BUSY_TIMEOUT_MS / 1000)
    holder.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    try:
        # An open write transaction, deliberately not committed yet.
        holder.execute("BEGIN IMMEDIATE")
        holder.execute(
            "UPDATE sessions SET current_node_id = ? WHERE session_id = ?",
            ("someone-elses-write", graph.session_id),
        )

        # Under the old rollback journal this raised `database is locked`.
        reloaded = load_graph(graph.session_id, db_path)

        assert reloaded is not None
        assert reloaded.session_id == graph.session_id
    finally:
        holder.rollback()
        holder.close()


def test_concurrent_writers_all_succeed(db_path):
    """Eight learners answering at once, against one database file.

    They serialise — SQLite allows one writer — but serialising is waiting, not
    failing, and that distinction is exactly what `busy_timeout` buys.
    """
    graphs = [_graph(f"Stop {i}") for i in range(8)]
    errors: list[Exception] = []
    barrier = threading.Barrier(len(graphs))

    def write(graph: LearningGraph) -> None:
        try:
            barrier.wait(timeout=10)     # maximise the overlap
            for _ in range(3):
                save_graph(graph, db_path)
        except Exception as exc:         # noqa: BLE001 - recorded, then asserted
            errors.append(exc)

    threads = [threading.Thread(target=write, args=(g,)) for g in graphs]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == [], f"concurrent writes failed: {errors!r}"
    for graph in graphs:
        assert load_graph(graph.session_id, db_path) is not None


def test_a_write_waits_for_a_lock_rather_than_failing(db_path):
    """The busy timeout, demonstrated rather than merely read back.

    A competing write is held for a moment and then released; the blocked writer
    must come back with a result, not `database is locked`.

    The lock is taken AND released on one dedicated thread, because a sqlite3
    connection may only be used from the thread that created it. Holding it on
    the main thread and releasing it from a timer raises `ProgrammingError` in
    the timer, the lock is never released, and the writer then fails for the
    right reason at the wrong time — which is how this test failed on its first
    run, before the release moved onto the holder's own thread.
    """
    graph = _graph()
    save_graph(graph, db_path)

    holding = threading.Event()
    outcome: list[object] = []

    def hold_briefly() -> None:
        conn = sqlite3.connect(db_path, timeout=BUSY_TIMEOUT_MS / 1000)
        conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "UPDATE sessions SET current_node_id = ? WHERE session_id = ?",
                ("held", graph.session_id),
            )
            holding.set()
            # Long enough that the writer definitely lands on the lock, far
            # short of BUSY_TIMEOUT_MS so waiting is enough to get through.
            threading.Event().wait(0.4)
            conn.rollback()
        finally:
            conn.close()

    def writer() -> None:
        holding.wait(timeout=5)
        try:
            save_graph(graph, db_path)
            outcome.append("ok")
        except Exception as exc:          # noqa: BLE001
            outcome.append(exc)

    holder = threading.Thread(target=hold_briefly)
    thread = threading.Thread(target=writer)
    holder.start()
    thread.start()
    thread.join(timeout=15)
    holder.join(timeout=15)

    assert outcome == ["ok"], f"a blocked write failed instead of waiting: {outcome!r}"


def test_concurrent_first_writes_to_a_new_database_all_succeed(db_path):
    """Schema initialisation racing itself, which `init_db` does on every save.

    THE BUG THIS CAUGHT: `_add_missing_columns` reads `PRAGMA table_info` and
    then ALTERs what is missing. Two writers arriving at a brand-new database
    both read "absent" and both ALTER; the loser gets
    `duplicate column name: areas_json`.

    It reproduced intermittently — roughly one full-suite run in five — because
    it needs two threads inside the same check-then-act window. The previous
    blanket `except Exception: pass` hid it completely, which is exactly why
    narrowing that catch was worth doing before M1 adds six more columns
    through the same path.
    """
    graphs = [_graph(f"Stop {i}") for i in range(8)]
    errors: list[Exception] = []
    barrier = threading.Barrier(len(graphs))

    def write(graph: LearningGraph) -> None:
        try:
            barrier.wait(timeout=10)
            save_graph(graph, db_path)
        except Exception as exc:          # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=write, args=(g,)) for g in graphs]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == [], f"concurrent schema initialisation failed: {errors!r}"
    for graph in graphs:
        assert load_graph(graph.session_id, db_path) is not None


def test_a_real_alter_failure_is_not_swallowed(db_path, monkeypatch):
    """The other half of narrowing the catch.

    Tolerating "duplicate column name" must not go back to tolerating
    everything: an ALTER that fails because the database is locked has to
    propagate, or `init_db` reports success over a column that does not exist
    and the very next write fails somewhere far away.
    """
    from backend.learning import store

    # A column SQLite genuinely refuses to add: `ALTER TABLE ... ADD COLUMN`
    # cannot introduce a UNIQUE constraint, because it would have to verify the
    # constraint against rows that already exist. A real refusal from the
    # database beats mocking — `sqlite3.Connection` is an immutable type in 3.11
    # and cannot be patched, and a stubbed error would only prove the stub was
    # raised.
    monkeypatch.setattr(
        store,
        "_ADDITIVE_COLUMNS",
        (("sessions", "impossible_col", "TEXT UNIQUE"),),
    )

    with pytest.raises(sqlite3.OperationalError) as caught:
        store.init_db(db_path)

    assert "duplicate column name" not in str(caught.value).lower()
