"""Version-2 sessions after the plan tables (multi-user.md OPEN-14).

Run with: uv run pytest tests/test_legacy_session_compatibility.py -v

## The decision these pin down

`feat/session-reset-m1` moved SCHEMA_VERSION from 2 to 3 to introduce
`plan_nodes` / `plan_edges`, and `load_graph` treats a version mismatch as
MISSING by design. Every session in the live database is version 2, so the bump
made all ninety of them — the manual-E2E corpus behind
`docs/planning/phases/evidence/` — invisible.

The rule chosen keeps both features whole:

  1. a version-2 session LOADS and RESUMES normally;
  2. its lesson, progress, gaps and history are exactly as they were;
  3. `Start over` is UNAVAILABLE for it, with a reason the caller can read;
  4. a version-3 session keeps the full reset behaviour, unchanged;
  5. nothing ever synthesises a plan for a session that never had one.

Point 5 is the one worth being emphatic about, and it is why the fifth section
below exists. A plan reconstructed from a half-walked graph is not the plan — it
is wherever the learner had got to, relabelled — so restoring it would return
them to a mid-journey state while calling it a fresh start. Absent is honest;
fabricated is not.

## What "version 2" means in these tests

A genuine v2 session is one written before the plan tables existed: its
`schema_version` is 2 AND it has no plan rows. Relabelling a v3 session without
also removing its plan rows produces a state that cannot occur, and would test
the opposite of what it claims — availability is gated on the plan being there,
not on the version number.
"""
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.api as api
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.learning.store import (
    SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
    create_session,
    load_graph,
    load_plan,
    save_graph,
)


@pytest.fixture
def db(tmp_path) -> Path:
    return tmp_path / "sessions.db"


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(api, "SESSIONS_DB_PATH", db)
    return TestClient(api.app)


def _graph() -> LearningGraph:
    graph = LearningGraph(
        repo_url="https://github.com/psf/requests",
        goal={"primary_goal": "understand sessions",
              "goal_type": "understand_component",
              "focus_area": "the Session object"},
    )
    first = graph.add_node(LearningNode(
        title="Understand Session",
        code_anchor=CodeAnchor(file="requests/sessions.py", line_start=1, line_end=80),
        concept_tags=["connection pooling"],
        lesson_brief={"objective": "explain what Session owns"},
    ))
    second = graph.add_node(LearningNode(
        title="Trace Session.send",
        code_anchor=CodeAnchor(file="requests/sessions.py", line_start=394, line_end=470),
        lesson_brief={"objective": "trace the send path"},
    ))
    graph.add_edge(first.id, second.id, kind="sequence")
    graph.set_current(first.id)
    return graph


def _walked(graph: LearningGraph) -> LearningGraph:
    """Give the session a learner's history — the thing that must survive."""
    first = graph.path_order()[0]
    node = graph.nodes[first]
    node.cached_lesson = {
        "setup": "A Session keeps connections alive.",
        "prompt": "What does a Session own that a bare request does not?",
        "reveal": "Connection reuse, cookie persistence, default configuration.",
    }
    graph.record_attempt(first, "It reuses connections.", "partial", "close but thin")
    graph.mark_visited(first)
    node.weak_spot = True
    return graph


def _make_v2(db: Path) -> LearningGraph:
    """A session as it existed before the plan tables: version 2, no plan rows."""
    graph = _walked(_graph())
    create_session(graph, db)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE sessions SET schema_version = 2 WHERE session_id = ?",
                     (graph.session_id,))
        conn.execute("DELETE FROM plan_nodes WHERE session_id = ?", (graph.session_id,))
        conn.execute("DELETE FROM plan_edges WHERE session_id = ?", (graph.session_id,))
    return graph


def _make_v3(db: Path) -> LearningGraph:
    graph = _walked(_graph())
    create_session(graph, db)
    return graph


# ── 1. a version-2 session loads and resumes normally ─────────────────────────

def test_a_version_2_session_loads(db):
    graph = _make_v2(db)

    reloaded = load_graph(graph.session_id, db)

    assert reloaded is not None, (
        "the live database is entirely version 2; refusing to load it makes the "
        "whole corpus invisible rather than merely un-resettable"
    )
    assert reloaded.session_id == graph.session_id


def test_a_version_2_session_resumes_where_the_learner_left_off(db):
    graph = _make_v2(db)
    expected = load_graph(graph.session_id, db).resume_point()

    reloaded = load_graph(graph.session_id, db)

    assert reloaded.resume_point() == expected
    assert reloaded.current_node_id == graph.current_node_id


def test_both_supported_versions_are_readable(db):
    assert SUPPORTED_SCHEMA_VERSIONS == frozenset({2, 3})
    assert SCHEMA_VERSION in SUPPORTED_SCHEMA_VERSIONS


def test_an_unsupported_version_is_still_treated_as_missing(db, monkeypatch):
    """The no-silent-migration rule is unchanged — only its membership test is."""
    graph = _make_v2(db)
    from backend.learning import store

    monkeypatch.setattr(store, "SUPPORTED_SCHEMA_VERSIONS", frozenset({3}))
    assert load_graph(graph.session_id, db) is None


# ── 2. its state is unchanged ─────────────────────────────────────────────────

def test_lesson_progress_gaps_and_history_survive_exactly(db):
    graph = _make_v2(db)
    first = graph.path_order()[0]

    reloaded = load_graph(graph.session_id, db)
    node = reloaded.nodes[first]

    assert node.cached_lesson == graph.nodes[first].cached_lesson
    assert node.attempts == graph.nodes[first].attempts
    assert node.visited is True
    assert node.weak_spot is True
    assert node.understanding_state == graph.nodes[first].understanding_state
    assert [g.id for g in node.gaps] == [g.id for g in graph.nodes[first].gaps]
    assert reloaded.journey_events == graph.journey_events
    assert reloaded.areas == graph.areas


def test_a_version_2_session_can_still_be_answered_and_advanced(db):
    """Resumable means WRITEABLE, not merely readable."""
    graph = _make_v2(db)
    first = graph.path_order()[0]

    reloaded = load_graph(graph.session_id, db)
    reloaded.record_attempt(first, "It owns connection reuse.", "understood", "yes")
    save_graph(reloaded, db)

    again = load_graph(graph.session_id, db)
    assert len(again.nodes[first].attempts) == 2
    assert again.nodes[first].attempts[-1]["answer"] == "It owns connection reuse."


def test_saving_a_version_2_session_does_not_relabel_it_as_version_3(db):
    """THE FABRICATION THIS FORBIDS.

    Rewriting `schema_version` on save would make a v2 session claim to be v3
    while `plan_nodes` stayed empty — a row asserting a plan it does not have.
    `load_plan` gates on the rows, so `Start over` would still refuse, but the
    stored version would be a lie about why.
    """
    graph = _make_v2(db)

    save_graph(load_graph(graph.session_id, db), db)

    with sqlite3.connect(db) as conn:
        version = conn.execute(
            "SELECT schema_version FROM sessions WHERE session_id = ?",
            (graph.session_id,),
        ).fetchone()[0]
    assert version == 2


def test_a_new_session_is_written_at_the_current_version(db):
    graph = _graph()
    save_graph(graph, db)

    with sqlite3.connect(db) as conn:
        version = conn.execute(
            "SELECT schema_version FROM sessions WHERE session_id = ?",
            (graph.session_id,),
        ).fetchone()[0]
    assert version == SCHEMA_VERSION


# ── 3. Start over is unavailable, with a reason ───────────────────────────────

def test_a_version_2_session_has_no_plan_to_restore(db):
    graph = _make_v2(db)

    assert load_plan(graph.session_id, db) is None


def test_a_version_2_session_reports_has_plan_false_on_the_wire(db, client):
    """The field the UI reads to disable `Start over` rather than hide it.

    Added by the session-reset workstream (`157a514`) rather than invented here:
    it is that feature's semantics, and one owner beats two. Keyed on plan-row
    presence and never persisted, so it cannot drift from the tables.
    """
    graph = _make_v2(db)

    payload = client.get(f"/session/{graph.session_id}").json()

    assert payload["has_plan"] is False


def test_a_version_3_session_reports_has_plan_true(db, client):
    graph = _make_v3(db)

    assert client.get(f"/session/{graph.session_id}").json()["has_plan"] is True


# `has_plan` is never persisted — owned by
# `test_plan_snapshot.py::test_has_plan_is_never_persisted`, where the field
# lives. Two tests of one behaviour in two files drift; one owner does not.


# ── 4. a version-3 session still resets normally ──────────────────────────────

def test_a_version_3_session_still_has_its_plan(db):
    graph = _make_v3(db)

    plan = load_plan(graph.session_id, db)

    assert plan is not None
    assert set(plan.nodes) == set(graph.nodes)


def test_start_over_still_works_on_a_version_3_session(db, client):
    graph = _make_v3(db)
    first = graph.path_order()[0]

    response = client.post(f"/session/{graph.session_id}/reset")

    assert response.status_code == 200
    restored = load_graph(graph.session_id, db)
    assert restored.nodes[first].attempts == []
    assert restored.nodes[first].visited is False
    assert restored.nodes[first].weak_spot is False


def test_reset_is_gated_twice_over(db, client):
    """TWO INDEPENDENT ROUTES to "this session cannot be reset", by design.

    `load_plan` checks BOTH that the row's version is the current one AND that
    plan rows exist, and either alone is enough to refuse. That redundancy is
    the session-reset workstream's call and it is a good one: the state it
    guards against — a session with a plan it should not have — is the one
    thing OPEN-14 forbids outright, so a second lock on it costs nothing.

    Demonstrated by the case that separates the two gates: a row labelled
    version 2 that DOES still have plan rows is refused on the version alone.

    THE COST, RECORDED WHERE IT WILL BE READ: at the next bump, a version-3
    session with a real plan silently stops being resettable — this same bug one
    version later. Whoever moves SCHEMA_VERSION to 4 must decide then whether
    `load_plan` should widen with it. `test_the_next_bump_must_revisit_load_plan`
    below is the tripwire.
    """
    graph = _make_v3(db)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE sessions SET schema_version = 2 WHERE session_id = ?",
                     (graph.session_id,))

    assert load_plan(graph.session_id, db) is None, "the version gate alone refuses"
    assert client.post(f"/session/{graph.session_id}/reset").status_code == 409


def test_the_next_bump_must_revisit_load_plan(db):
    """A tripwire, not a behaviour test.

    `load_plan` is strict against `SCHEMA_VERSION`, so the day that constant
    moves to 4, every existing version-3 session loses `Start over` — silently,
    exactly as version 2 lost it here. This fails when that day comes, which is
    the only reliable way to make the decision happen on purpose rather than be
    discovered afterwards.

    If you are reading this because it failed: the question is whether
    `load_plan` should accept the previous version too. It should, if that
    version's sessions have real plan rows.
    """
    assert SCHEMA_VERSION == 3, (
        "SCHEMA_VERSION moved. Revisit load_plan's strict version check "
        "(backend/learning/store.py) before updating this assertion — see "
        "multi-user.md OPEN-14."
    )


# ── 5. nothing fabricates a plan ──────────────────────────────────────────────

def test_loading_a_version_2_session_never_creates_plan_rows(db):
    graph = _make_v2(db)

    load_graph(graph.session_id, db)
    load_plan(graph.session_id, db)

    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM plan_nodes WHERE session_id = ?",
            (graph.session_id,),
        ).fetchone()[0] == 0


def test_saving_a_version_2_session_never_creates_plan_rows(db):
    """`save_graph` writes the LIVE side only. `create_session` is the only
    function that writes a plan, and it runs once, at planning time."""
    graph = _make_v2(db)

    for _ in range(3):
        reloaded = load_graph(graph.session_id, db)
        reloaded.mark_visited(reloaded.path_order()[0])
        save_graph(reloaded, db)

    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM plan_nodes WHERE session_id = ?",
            (graph.session_id,),
        ).fetchone()[0] == 0


def test_the_migration_does_not_give_a_version_2_session_a_plan(db):
    """The multi-user migration assigns OWNERSHIP and nothing else.

    It reads every row regardless of `schema_version`, which is what lets it
    give the v2 corpus an owner — so it is exactly the code most likely to be
    mistaken for a place to "fix up" those sessions while it is in there.
    """
    import importlib

    graph = _make_v2(db)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE sessions SET user_id = NULL")

    importlib.import_module("backend.migrations.001_multi_user").migrate(db, apply=True)

    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM plan_nodes WHERE session_id = ?",
            (graph.session_id,),
        ).fetchone()[0] == 0
        version, user_id = conn.execute(
            "SELECT schema_version, user_id FROM sessions WHERE session_id = ?",
            (graph.session_id,),
        ).fetchone()
    assert version == 2, "the migration must not relabel the row"
    assert user_id is not None, "but it must still give it an owner"
    assert load_plan(graph.session_id, db) is None


def test_a_failed_reset_does_not_leave_a_partial_plan(db, client):
    graph = _make_v2(db)

    client.post(f"/session/{graph.session_id}/reset")

    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM plan_nodes WHERE session_id = ?",
            (graph.session_id,),
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM plan_edges WHERE session_id = ?",
            (graph.session_id,),
        ).fetchone()[0] == 0


def test_a_database_older_than_the_plan_tables_answers_no_plan(db):
    """A restored backup, or the live file before anything has run `init_db`.

    "No `plan_nodes` table" and "no plan for this session" are the same answer to
    the only question being asked, and the caller already knows what to do with
    it. Raising instead turned `/reset`'s honest 409 into a 500 — the same
    refusal delivered as a malfunction.

    Found by running against a copy of the real database rather than a fixture,
    which is the only place this state occurs: every fixture here is built by
    `create_session`, which creates the tables on the way past.
    """
    graph = _make_v2(db)
    with sqlite3.connect(db) as conn:
        conn.execute("DROP TABLE plan_nodes")
        conn.execute("DROP TABLE plan_edges")

    assert load_plan(graph.session_id, db) is None
    assert load_graph(graph.session_id, db) is not None


def test_start_over_on_a_pre_plan_database_is_a_409_not_a_500(db, client):
    graph = _make_v2(db)
    with sqlite3.connect(db) as conn:
        conn.execute("DROP TABLE plan_nodes")
        conn.execute("DROP TABLE plan_edges")

    response = client.post(f"/session/{graph.session_id}/reset")

    assert response.status_code == 409
    assert response.json()["detail"] == "no_plan_snapshot"
