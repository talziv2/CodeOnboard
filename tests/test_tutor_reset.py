"""`Start over` clears the Tutor conversation — tutor.md §4.3, decided 2026-09-01.

Run with: uv run pytest tests/test_tutor_reset.py -v

The decision and its argument: the transcript is learner-produced state, so a
surviving one would be the first exception to `reset.py`'s correctness claim that
**anything not in the plan is gone by construction** — and it would sit beside a
freshly restored route as a list of stops that had already confused the learner.

Two of the assertions below are about the ENUMERATION rather than the behaviour:
`reset.learner_state()` is the only description of the plan/state boundary the
reset can be tested against, so a field missing from it is a field nobody will
notice surviving.
"""
import pytest

from backend.learning import store as learning_store
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.learning.reset import learner_state, reset_to_plan
from backend.learning.tutor import TutorState, new_turn


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "sessions.db"
    learning_store.init_db(path)
    return path


def _planned() -> LearningGraph:
    graph = LearningGraph(repo_url="https://github.com/psf/requests", goal={"primary_goal": "g"})
    a = graph.add_node(LearningNode(title="A", code_anchor=CodeAnchor("a.py", 1, 10)))
    b = graph.add_node(LearningNode(title="B", code_anchor=CodeAnchor("b.py", 1, 10)))
    graph.add_edge(a.id, b.id)
    graph.current_node_id = a.id
    return graph


def _walked(graph: LearningGraph) -> LearningGraph:
    """A session somebody has actually used, Tutor included."""
    node = graph.nodes[graph.current_node_id]
    node.visited = True
    node.tutor_state.hints_used = 2
    node.tutor_state.revealed = True
    node.tutor_state.turns = 4
    graph.tutor.append(new_turn(node_id=node.id, mode="explain", question="q1",
                                answer="a1", scope="answered"))
    graph.tutor.append(new_turn(node_id=node.id, mode="scaffold", question="stuck",
                                answer="hint", scope="answered", hint_level=1))
    return graph


# ── the enumeration ───────────────────────────────────────────────────────────


def test_learner_state_counts_the_transcript():
    """If the transcript is not in the enumeration, the enumeration is wrong."""
    graph = _walked(_planned())
    assert learner_state(graph)["tutor_turns"] == 2


def test_learner_state_reports_no_conversation_as_zero():
    assert learner_state(_planned())["tutor_turns"] == 0


# ── the reset ─────────────────────────────────────────────────────────────────


def test_start_over_clears_the_transcript(db):
    graph = _planned()
    learning_store.create_session(graph, db, user_id="u1")
    _walked(graph)
    learning_store.save_graph(graph, db, user_id="u1")

    plan = learning_store.load_plan(graph.session_id, "u1", db)
    assert plan is not None
    summary = reset_to_plan(graph, plan)

    assert graph.tutor == []
    assert summary.tutor_turns == 2
    assert summary.to_dict()["tutor_turns"] == 2


def test_start_over_clears_the_node_counters_without_naming_them(db):
    """The counters go because the NODES go — the property reset.py is built on.

    Asserted explicitly because it is the reason `reset_to_plan` needed only one
    new line rather than three: `load_plan` builds fresh `LearningNode`s whose
    every state field is at its dataclass default, so `tutor_state` was already
    handled the day it was added.
    """
    graph = _planned()
    learning_store.create_session(graph, db, user_id="u1")
    _walked(graph)
    learning_store.save_graph(graph, db, user_id="u1")

    plan = learning_store.load_plan(graph.session_id, "u1", db)
    reset_to_plan(graph, plan)

    assert all(n.tutor_state == TutorState() for n in graph.nodes.values())


def test_the_cleared_transcript_survives_the_round_trip(db):
    """Cleared in memory is not cleared until it is written."""
    graph = _planned()
    learning_store.create_session(graph, db, user_id="u1")
    _walked(graph)
    learning_store.save_graph(graph, db, user_id="u1")

    plan = learning_store.load_plan(graph.session_id, "u1", db)
    reset_to_plan(graph, plan)
    learning_store.save_graph(graph, db, user_id="u1")

    reloaded = learning_store.load_graph(graph.session_id, "u1", db)
    assert reloaded.tutor == []
    assert all(n.tutor_state == TutorState() for n in reloaded.nodes.values())


# ── what a reset is NOT ───────────────────────────────────────────────────────


def test_an_ordinary_save_never_clears_the_transcript(db):
    """Only a reset clears it. Navigation, answering and resuming all preserve.

    The guard on a plausible mistake: making `save_graph` normalise an "empty"
    field, or making some later cleanup treat the transcript as derived.
    """
    graph = _planned()
    learning_store.create_session(graph, db, user_id="u1")
    _walked(graph)
    learning_store.save_graph(graph, db, user_id="u1")

    for _ in range(3):
        reloaded = learning_store.load_graph(graph.session_id, "u1", db)
        reloaded.mark_visited(reloaded.current_node_id)
        learning_store.save_graph(reloaded, db, user_id="u1")

    final = learning_store.load_graph(graph.session_id, "u1", db)
    assert len(final.tutor) == 2
    assert final.nodes[graph.current_node_id].tutor_state.hints_used == 2


def test_rebuild_leaves_the_old_session_transcript_alone(db):
    """`Rebuild` creates a NEW session; the old row is untouched (§4.4).

    There is no rebuild function to call — the frontend calls `sessionStart` with
    a new id — so what is asserted is the property that makes the semantics fall
    out for free: two sessions on the same repository hold independent
    transcripts, and creating the second cannot reach the first.
    """
    old = _planned()
    learning_store.create_session(old, db, user_id="u1")
    _walked(old)
    learning_store.save_graph(old, db, user_id="u1")

    rebuilt = _planned()
    learning_store.create_session(rebuilt, db, user_id="u1")

    assert learning_store.load_graph(rebuilt.session_id, "u1", db).tutor == []
    assert len(learning_store.load_graph(old.session_id, "u1", db).tutor) == 2
