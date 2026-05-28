"""
Pytest tests for backend/learning/store.py.
Run with: uv run pytest tests/test_learning_store.py -v
"""
import time
from pathlib import Path

import pytest

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
    save_graph(g, db_path)
    loaded = load_graph(g.session_id, db_path)

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
    save_graph(g, db_path)

    g.mark_understanding(a.id, "understood")
    g.mark_visited(a.id)
    g.set_current(b.id)
    save_graph(g, db_path)

    loaded = load_graph(g.session_id, db_path)
    assert loaded is not None
    assert loaded.nodes[a.id].understanding_state == "understood"
    assert loaded.nodes[a.id].visited is True
    assert loaded.current_node_id == b.id


def test_save_replaces_nodes_and_edges_wholesale(db_path):
    # Re-saving a graph with one node removed should not leave the old node
    # behind in the DB.
    g, a, b = _make_graph_with_two_nodes()
    save_graph(g, db_path)
    del g.nodes[b.id]
    g.edges = [e for e in g.edges if e.to_node_id != b.id]
    save_graph(g, db_path)

    loaded = load_graph(g.session_id, db_path)
    assert loaded is not None
    assert set(loaded.nodes) == {a.id}
    assert loaded.edges == []


def test_load_missing_session_returns_none(db_path):
    assert load_graph("does-not-exist", db_path) is None


def test_load_with_no_db_file_returns_none(tmp_path):
    # Calling load_graph before any save_graph must not blow up.
    assert load_graph("anything", tmp_path / "never_created.db") is None


def test_schema_version_mismatch_returns_none(db_path, monkeypatch):
    # Write at the current version, then bump the in-memory constant — the
    # row written previously now looks "old" and should be treated as missing.
    g, _, _ = _make_graph_with_two_nodes()
    save_graph(g, db_path)
    monkeypatch.setattr(store_module, "SCHEMA_VERSION", SCHEMA_VERSION + 1)
    assert load_graph(g.session_id, db_path) is None


def test_list_sessions_for_repo_returns_summaries(db_path):
    g, _, _ = _make_graph_with_two_nodes()
    save_graph(g, db_path)

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
    save_graph(g1, db_path)
    time.sleep(0.02)
    g2, _, _ = _make_graph_with_two_nodes()
    save_graph(g2, db_path)

    rows = list_sessions_for_repo(g1.repo_url, db_path)
    assert [r["session_id"] for r in rows[:2]] == [g2.session_id, g1.session_id]


def test_list_sessions_filters_by_repo(db_path):
    g, _, _ = _make_graph_with_two_nodes()
    save_graph(g, db_path)
    assert list_sessions_for_repo("https://github.com/some/other-repo", db_path) == []


def test_delete_session_removes_nodes_and_edges(db_path):
    g, _, _ = _make_graph_with_two_nodes()
    save_graph(g, db_path)
    delete_session(g.session_id, db_path)
    assert load_graph(g.session_id, db_path) is None
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
    save_graph(g, db_path)
    loaded = load_graph(g.session_id, db_path)
    assert loaded is not None
    assert loaded.nodes[a.id].cached_lesson is not None
    assert loaded.nodes[a.id].cached_lesson["prompt_kind"] == "predict-then-reveal"
