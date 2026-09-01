"""The Tutor's persistence: two additive columns, and the contracts around them.

Run with: uv run pytest tests/test_tutor_store.py -v

Three things are asserted here and nowhere else:

  1. the transcript and the per-node counters round-trip through save/load;
  2. a row written before the Tutor existed loads as "no conversation", never as
     an error and never as a fabricated one;
  3. the FLAG-OFF SAVE preserves everything — the gap-model §3.8 contract, which
     the Tutor inherits verbatim: the flag gates behaviour, never storage.

`SCHEMA_VERSION` does not move for this feature, so a version-2 session must keep
loading. That is asserted too, because the whole reason these are additive columns
is to avoid making the stored corpus invisible.
"""
import json
import sqlite3

import pytest

from backend.learning import store as learning_store
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.learning.tutor import TutorState, new_turn


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "sessions.db"
    learning_store.init_db(path)
    return path


def _graph() -> LearningGraph:
    graph = LearningGraph(repo_url="https://github.com/psf/requests", goal={"primary_goal": "x"})
    a = graph.add_node(LearningNode(title="A", code_anchor=CodeAnchor("requests/api.py", 1, 20)))
    b = graph.add_node(LearningNode(title="B", code_anchor=CodeAnchor("requests/sessions.py", 5, 40)))
    graph.add_edge(a.id, b.id)
    graph.current_node_id = a.id
    return graph


def _save(graph, db, owner="u1"):
    learning_store.save_graph(graph, db, user_id=owner)


def _load(session_id, db, owner="u1"):
    return learning_store.load_graph(session_id, owner, db)


# ── round trip ────────────────────────────────────────────────────────────────


def test_transcript_round_trips(db):
    graph = _graph()
    node_id = graph.current_node_id
    graph.tutor.append(
        new_turn(
            node_id=node_id,
            mode="explain",
            question="what does HTTPAdapter do here",
            answer="It owns the connection pool.",
            scope="answered",
            citations=[{"file": "requests/adapters.py", "symbol": "HTTPAdapter.send",
                        "line_start": 434, "line_end": 538}],
            usage={"input_tokens": 1180, "output_tokens": 214},
        )
    )
    graph.tutor.append(
        new_turn(node_id=node_id, mode="scaffold", question="stuck",
                 answer="Look at the first return.", scope="answered", hint_level=1)
    )
    _save(graph, db)

    loaded = _load(graph.session_id, db)
    assert len(loaded.tutor) == 2
    assert loaded.tutor[0]["question"] == "what does HTTPAdapter do here"
    assert loaded.tutor[0]["citations"][0]["symbol"] == "HTTPAdapter.send"
    assert loaded.tutor[0]["usage"]["output_tokens"] == 214
    assert loaded.tutor[1]["mode"] == "scaffold"
    assert loaded.tutor[1]["hint_level"] == 1
    # Order is the record: oldest first, and a reload must not reorder it.
    assert [t["id"] for t in loaded.tutor] == [t["id"] for t in graph.tutor]


def test_node_counters_round_trip(db):
    graph = _graph()
    node = graph.nodes[graph.current_node_id]
    node.tutor_state.hints_used = 2
    node.tutor_state.revealed = True
    node.tutor_state.turns = 5
    _save(graph, db)

    loaded = _load(graph.session_id, db)
    state = loaded.nodes[node.id].tutor_state
    assert state.hints_used == 2
    assert state.revealed is True
    assert state.turns == 5
    # And the untouched node is still at its default rather than inheriting.
    other = [n for n in loaded.nodes.values() if n.id != node.id][0]
    assert other.tutor_state == TutorState()


def test_an_empty_transcript_stores_null_not_an_empty_blob(db):
    """`tutor_json` stays NULL while nothing has been asked.

    Not cosmetic: a row that stores `"[]"` is indistinguishable from one that
    stored a transcript and had it emptied, and the columns exist precisely so a
    pre-feature row reads as "no conversation".
    """
    graph = _graph()
    _save(graph, db)
    with sqlite3.connect(db) as conn:
        raw = conn.execute(
            "SELECT tutor_json FROM sessions WHERE session_id = ?", (graph.session_id,)
        ).fetchone()[0]
    assert raw is None


# ── compatibility ─────────────────────────────────────────────────────────────


def test_a_pre_tutor_row_loads_with_no_conversation(db):
    """A session whose columns are NULL loads clean, not broken."""
    graph = _graph()
    _save(graph, db)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE sessions SET tutor_json = NULL WHERE session_id = ?",
                     (graph.session_id,))
        conn.execute("UPDATE nodes SET tutor_json = NULL WHERE session_id = ?",
                     (graph.session_id,))

    loaded = _load(graph.session_id, db)
    assert loaded.tutor == []
    assert all(n.tutor_state == TutorState() for n in loaded.nodes.values())


def test_a_corrupt_counter_degrades_to_a_fresh_state(db):
    """A counter we cannot read must not cost the learner their session."""
    graph = _graph()
    _save(graph, db)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE nodes SET tutor_json = ? WHERE node_id = ?",
                     (json.dumps({"hints_used": "lots", "revealed": "yes"}),
                      graph.current_node_id))

    loaded = _load(graph.session_id, db)
    state = loaded.nodes[graph.current_node_id].tutor_state
    assert state.hints_used == 0
    assert state.revealed is False


def test_a_version_two_session_still_loads_with_the_new_columns(db):
    """The whole point of additive columns: the stored corpus stays readable."""
    graph = _graph()
    _save(graph, db)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE sessions SET schema_version = 2 WHERE session_id = ?",
                     (graph.session_id,))

    loaded = _load(graph.session_id, db)
    assert loaded is not None
    assert loaded.tutor == []


# ── the flag gates behaviour, never storage ───────────────────────────────────


def test_the_persistence_path_never_reads_the_tutor_flag():
    """Structural, in the shape `test_gap_model.py` established.

    If `store.py` ever asks whether the Tutor is enabled, a flag-off deployment
    starts silently dropping conversations — and the round-trip guarantee above
    stops being true by construction and becomes true by care.

    Parsed as an AST rather than grepped, exactly as
    `test_gap_model.py::test_the_persistence_path_never_reads_the_flag` is, so the
    module may EXPLAIN the contract in a comment — which it does, right above the
    two columns — without the explanation tripping the assertion.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(learning_store))
    names = (
        {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        | {
            n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        }
    )
    assert "CODEONBOARD_TUTOR" not in names
    assert "tutor_enabled" not in names


def test_a_flag_off_save_preserves_a_tutor_bearing_graph(db, monkeypatch):
    """Load flag-off, change something unrelated, write back: nothing is lost."""
    graph = _graph()
    node_id = graph.current_node_id
    graph.tutor.append(new_turn(node_id=node_id, mode="explain", question="q",
                                answer="a", scope="answered"))
    graph.nodes[node_id].tutor_state.hints_used = 3
    _save(graph, db)

    monkeypatch.delenv("CODEONBOARD_TUTOR", raising=False)
    reloaded = _load(graph.session_id, db)
    reloaded.mark_visited(node_id)          # something unrelated
    _save(reloaded, db)

    monkeypatch.setenv("CODEONBOARD_TUTOR", "1")
    final = _load(graph.session_id, db)
    assert len(final.tutor) == 1
    assert final.tutor[0]["question"] == "q"
    assert final.nodes[node_id].tutor_state.hints_used == 3


# ── the plan tables stay plan tables ──────────────────────────────────────────


def test_the_plan_never_carries_tutor_state(db):
    """`tutor_state` is state, so it must not reach `plan_nodes`.

    Asserted against the schema rather than against a behaviour, because the
    failure mode is silent: a plan that carried the counters would restore them on
    `Start over`, and the learner would begin a fresh route with a spent ladder.
    """
    with sqlite3.connect(db) as conn:
        columns = {r[1] for r in conn.execute("PRAGMA table_info(plan_nodes)")}
    assert "tutor_json" not in columns
