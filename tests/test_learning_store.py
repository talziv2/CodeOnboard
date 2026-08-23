"""
Pytest tests for backend/learning/store.py.
Run with: uv run pytest tests/test_learning_store.py -v
"""
import time
from pathlib import Path

import pytest

from tests.conftest import TEST_USER_ID

from backend.learning import store as store_module
from backend.learning.graph import (
    CodeAnchor,
    LearningGraph,
    LearningNode,
)
from backend.learning.store import (
    SCHEMA_VERSION,
    delete_session,
    list_sessions_for_repo,
    load_graph,
    save_graph,
)


@pytest.fixture
def db_path(tmp_path) -> Path:
    return tmp_path / "sessions.db"


def _make_node(title: str, file: str = "a.py") -> LearningNode:
    return LearningNode(
        title=title,
        code_anchor=CodeAnchor(file=file, line_start=1, line_end=10),
        concept_tags=["session", "core"],
        lesson_brief={"why": "central abstraction", "understand": "state machine"},
    )


def _make_graph_with_two_nodes() -> tuple[LearningGraph, LearningNode, LearningNode]:
    g = LearningGraph(
        repo_url="https://github.com/psf/requests",
        goal={
            "primary_goal": "understand request lifecycle",
            "goal_type": "understand_component",
            "focus_area": "sessions",
        },
    )
    a = g.add_node(_make_node("A", file="requests/sessions.py"))
    b = g.add_node(_make_node("B", file="requests/adapters.py"))
    g.add_edge(a.id, b.id)
    g.set_current(a.id)
    return g, a, b


def test_save_and_reload_roundtrip(db_path):
    g, a, b = _make_graph_with_two_nodes()
    save_graph(g, db_path, user_id=TEST_USER_ID)
    loaded = load_graph(g.session_id, TEST_USER_ID, db_path)

    assert loaded is not None
    assert loaded.session_id == g.session_id
    assert loaded.repo_url == g.repo_url
    assert loaded.goal == g.goal
    assert loaded.current_node_id == a.id
    assert set(loaded.nodes) == {a.id, b.id}
    assert loaded.nodes[a.id].title == "A"
    assert loaded.nodes[a.id].code_anchor.file == "requests/sessions.py"
    assert loaded.nodes[a.id].concept_tags == ["session", "core"]
    assert loaded.nodes[a.id].lesson_brief == {
        "why": "central abstraction",
        "understand": "state machine",
    }
    assert len(loaded.edges) == 1
    assert loaded.edges[0].from_node_id == a.id
    assert loaded.edges[0].to_node_id == b.id


def test_mutation_persists_through_save_reload(db_path):
    g, a, b = _make_graph_with_two_nodes()
    save_graph(g, db_path, user_id=TEST_USER_ID)

    g.mark_understanding(a.id, "understood")
    g.mark_visited(a.id)
    g.set_current(b.id)
    save_graph(g, db_path, user_id=TEST_USER_ID)

    loaded = load_graph(g.session_id, TEST_USER_ID, db_path)
    assert loaded is not None
    assert loaded.nodes[a.id].understanding_state == "understood"
    assert loaded.nodes[a.id].visited is True
    assert loaded.current_node_id == b.id


def test_save_replaces_nodes_and_edges_wholesale(db_path):
    # Re-saving a graph with one node removed should not leave the old node
    # behind in the DB.
    g, a, b = _make_graph_with_two_nodes()
    save_graph(g, db_path, user_id=TEST_USER_ID)
    del g.nodes[b.id]
    g.edges = [e for e in g.edges if e.to_node_id != b.id]
    save_graph(g, db_path, user_id=TEST_USER_ID)

    loaded = load_graph(g.session_id, TEST_USER_ID, db_path)
    assert loaded is not None
    assert set(loaded.nodes) == {a.id}
    assert loaded.edges == []


def test_load_missing_session_returns_none(db_path):
    assert load_graph("does-not-exist", TEST_USER_ID, db_path) is None


def test_load_with_no_db_file_returns_none(tmp_path):
    # Calling load_graph before any save_graph must not blow up.
    assert load_graph("anything", TEST_USER_ID, tmp_path / "never_created.db") is None


def test_an_unsupported_schema_version_returns_none(db_path, monkeypatch):
    """A row written by a schema this build does not understand reads as MISSING.

    Still the rule, and still deliberate — no silent migration. What changed
    (multi-user.md OPEN-14) is that "understood" is now a SET rather than one
    constant: version 2 and version 3 are both readable, so the check is
    membership and this test patches the set rather than the version.

    Patching `SCHEMA_VERSION` no longer proves anything here, because what a row
    is written AT and what this build can READ are now separate questions —
    which is the whole point of the change.
    """
    g, _, _ = _make_graph_with_two_nodes()
    save_graph(g, db_path, user_id=TEST_USER_ID)
    monkeypatch.setattr(store_module, "SUPPORTED_SCHEMA_VERSIONS", frozenset({99}))
    assert load_graph(g.session_id, TEST_USER_ID, db_path) is None


def test_list_sessions_for_repo_returns_summaries(db_path):
    g, _, _ = _make_graph_with_two_nodes()
    save_graph(g, db_path, user_id=TEST_USER_ID)

    rows = list_sessions_for_repo(g.repo_url, db_path)
    assert len(rows) == 1
    assert rows[0]["session_id"] == g.session_id
    assert rows[0]["goal"] == g.goal


def test_list_sessions_orders_by_updated_at_desc(db_path):
    # Two sessions on the same repo — the most recently saved comes first.
    # Sleep between saves so the millisecond-precision timestamps differ;
    # in production, sessions are saved seconds-to-minutes apart so the
    # ordering is never ambiguous.
    g1, _, _ = _make_graph_with_two_nodes()
    save_graph(g1, db_path, user_id=TEST_USER_ID)
    time.sleep(0.02)
    g2, _, _ = _make_graph_with_two_nodes()
    save_graph(g2, db_path, user_id=TEST_USER_ID)

    rows = list_sessions_for_repo(g1.repo_url, db_path)
    assert [r["session_id"] for r in rows[:2]] == [g2.session_id, g1.session_id]


def test_list_sessions_filters_by_repo(db_path):
    g, _, _ = _make_graph_with_two_nodes()
    save_graph(g, db_path, user_id=TEST_USER_ID)
    assert list_sessions_for_repo("https://github.com/some/other-repo", db_path) == []


def test_delete_session_removes_nodes_and_edges(db_path):
    g, _, _ = _make_graph_with_two_nodes()
    save_graph(g, db_path, user_id=TEST_USER_ID)
    delete_session(g.session_id, db_path)
    assert load_graph(g.session_id, TEST_USER_ID, db_path) is None
    # And the cascade actually removed nodes/edges, not just the session row.
    rows = list_sessions_for_repo(g.repo_url, db_path)
    assert rows == []


def test_cached_lesson_roundtrips(db_path):
    g, a, _ = _make_graph_with_two_nodes()
    g.nodes[a.id].cached_lesson = {
        "walkthrough": "Session is the central abstraction…",
        "prompt": "What does Session.get return?",
        "prompt_kind": "predict-then-reveal",
    }
    save_graph(g, db_path, user_id=TEST_USER_ID)
    loaded = load_graph(g.session_id, TEST_USER_ID, db_path)
    assert loaded is not None
    assert loaded.nodes[a.id].cached_lesson is not None
    assert loaded.nodes[a.id].cached_lesson["prompt_kind"] == "predict-then-reveal"


# ── symbol identity on the anchor (Stage 0, D14) ─────────────────────────────


def test_symbol_roundtrips_on_the_code_anchor(db_path):
    g = LearningGraph(repo_url="r", goal={"primary_goal": "g"})
    node = g.add_node(LearningNode(
        title="How Session.send dispatches",
        code_anchor=CodeAnchor(
            file="src/requests/sessions.py",
            line_start=662,
            line_end=748,
            symbol="Session.send",
        ),
    ))
    save_graph(g, db_path, user_id=TEST_USER_ID)

    loaded = load_graph(g.session_id, TEST_USER_ID, db_path)
    anchor = loaded.nodes[node.id].code_anchor
    assert anchor.symbol == "Session.send"
    # Symbol is identity; the range is the resolved location for this commit.
    assert (anchor.file, anchor.line_start, anchor.line_end) == (
        "src/requests/sessions.py", 662, 748
    )


def test_node_without_a_symbol_roundtrips_as_none(db_path):
    g = LearningGraph(repo_url="r", goal={"primary_goal": "g"})
    node = g.add_node(_make_node("no symbol here"))
    save_graph(g, db_path, user_id=TEST_USER_ID)

    loaded = load_graph(g.session_id, TEST_USER_ID, db_path)
    assert loaded.nodes[node.id].code_anchor.symbol is None


def test_session_written_before_the_symbol_column_still_loads(db_path):
    """Backwards compatibility: a pre-Stage-0 database has no `symbol` column.

    Simulated by dropping the column after a normal write, which is as close to
    an old on-disk row as SQLite allows.
    """
    import sqlite3

    g = LearningGraph(repo_url="r", goal={"primary_goal": "g"})
    node = g.add_node(_make_node("legacy node"))
    save_graph(g, db_path, user_id=TEST_USER_ID)

    conn = sqlite3.connect(db_path)
    conn.execute("ALTER TABLE nodes DROP COLUMN symbol")
    conn.commit()
    conn.close()

    # init_db re-adds the column as NULL; the row predates it either way.
    loaded = load_graph(g.session_id, TEST_USER_ID, db_path)
    assert loaded is not None, "an old session must never fail to load"
    assert loaded.nodes[node.id].title == "legacy node"
    assert loaded.nodes[node.id].code_anchor.symbol is None


def test_arrival_roundtrips(db_path):
    """The notice must survive a reload — a learner who refreshes is still off-route."""
    g = LearningGraph(repo_url="r", goal={"primary_goal": "g"})
    a = g.add_node(_make_node("first"))
    b = g.add_node(_make_node("second"))
    g.add_edge(a.id, b.id, kind="sequence")
    g.set_current(b.id)
    g.record_arrival(b.id, kind="jumped", from_node_id=a.id)
    save_graph(g, db_path, user_id=TEST_USER_ID)

    loaded = load_graph(g.session_id, TEST_USER_ID, db_path)
    assert loaded is not None
    assert loaded.arrival["node_id"] == b.id
    assert loaded.arrival["from_node_id"] == a.id
    assert loaded.arrival["kind"] == "jumped"


def test_a_cleared_arrival_roundtrips_as_none(db_path):
    g = LearningGraph(repo_url="r", goal={"primary_goal": "g"})
    node = g.add_node(_make_node("only"))
    g.record_arrival(node.id, kind="jumped", from_node_id=None)
    g.clear_arrival()
    save_graph(g, db_path, user_id=TEST_USER_ID)

    loaded = load_graph(g.session_id, TEST_USER_ID, db_path)
    assert loaded is not None
    assert loaded.arrival is None


def test_session_written_before_the_arrival_column_still_loads(db_path):
    """A session from before the arrival column loads with no notice, not an error.

    Same guarantee as the `symbol` column above, and the same reason: every one of
    the stored sessions predates this, and `None` reads correctly as "nothing to
    say about how they got here".
    """
    import sqlite3

    g = LearningGraph(repo_url="r", goal={"primary_goal": "g"})
    node = g.add_node(_make_node("legacy node"))
    save_graph(g, db_path, user_id=TEST_USER_ID)

    conn = sqlite3.connect(db_path)
    conn.execute("ALTER TABLE sessions DROP COLUMN arrival_json")
    conn.commit()
    conn.close()

    loaded = load_graph(g.session_id, TEST_USER_ID, db_path)
    assert loaded is not None, "an old session must never fail to load"
    assert loaded.arrival is None
    assert loaded.nodes[node.id].title == "legacy node"
