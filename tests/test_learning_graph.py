"""
Pytest tests for backend/learning/graph.py.
Run with: uv run pytest tests/test_learning_graph.py -v
"""
import pytest

from backend.learning.graph import (
    CodeAnchor,
    LearningGraph,
    LearningNode,
)


def _make_node(title: str = "n", file: str = "a.py", start: int = 1, end: int = 10) -> LearningNode:
    return LearningNode(
        title=title,
        code_anchor=CodeAnchor(file=file, line_start=start, line_end=end),
    )


def _make_graph() -> LearningGraph:
    return LearningGraph(
        repo_url="https://github.com/psf/requests",
        goal={"primary_goal": "x", "goal_type": "understand_component"},
    )


# --- defaulting / identity ---


def test_node_id_defaults_to_unique_value():
    a = _make_node()
    b = _make_node()
    assert a.id != b.id
    assert "-" not in a.id  # uuid4 hex, no dashes


def test_session_id_defaults_to_unique_value():
    assert _make_graph().session_id != _make_graph().session_id


# --- construction ---


def test_add_node_and_edge():
    g = _make_graph()
    a = g.add_node(_make_node("A"))
    b = g.add_node(_make_node("B"))
    g.add_edge(a.id, b.id)
    assert len(g.nodes) == 2
    assert len(g.edges) == 1
    assert g.edges[0].kind == "sequence"


def test_add_node_rejects_duplicate_id():
    g = _make_graph()
    n = _make_node()
    g.add_node(n)
    with pytest.raises(ValueError):
        g.add_node(n)


def test_add_edge_rejects_unknown_endpoint():
    g = _make_graph()
    a = g.add_node(_make_node())
    with pytest.raises(ValueError):
        g.add_edge(a.id, "missing-id")


# --- session-state mutations ---


def test_set_current_validates_node_exists():
    g = _make_graph()
    a = g.add_node(_make_node())
    g.set_current(a.id)
    assert g.current_node_id == a.id
    with pytest.raises(ValueError):
        g.set_current("nope")


def test_mark_visited_flips_flag():
    g = _make_graph()
    a = g.add_node(_make_node())
    assert a.visited is False
    g.mark_visited(a.id)
    assert g.nodes[a.id].visited is True


def test_mark_understanding_not_yet_sets_weak_spot():
    g = _make_graph()
    a = g.add_node(_make_node())
    g.mark_understanding(a.id, "not-yet")
    assert g.nodes[a.id].understanding_state == "not-yet"
    assert g.nodes[a.id].weak_spot is True


def test_weak_spot_is_sticky_across_recovery():
    # Once flagged confused, weak_spot survives later "understood" updates.
    # The Planner uses this as a long-memory signal.
    g = _make_graph()
    a = g.add_node(_make_node())
    g.mark_understanding(a.id, "not-yet")
    g.mark_understanding(a.id, "understood")
    assert g.nodes[a.id].understanding_state == "understood"
    assert g.nodes[a.id].weak_spot is True


def test_override_mark_understood():
    g = _make_graph()
    a = g.add_node(_make_node())
    g.override(a.id, "mark_understood")
    assert g.nodes[a.id].understanding_state == "understood"
    assert g.nodes[a.id].user_override == "mark_understood"


def test_override_skip_marks_visited():
    g = _make_graph()
    a = g.add_node(_make_node())
    g.override(a.id, "skip")
    assert g.nodes[a.id].visited is True
    assert g.nodes[a.id].user_override == "skip"


# --- graph mutations ---


def test_insert_before_reroutes_sequence_edges():
    # A -> B becomes A -> NEW -> B (sequence A->NEW, prerequisite NEW->B).
    g = _make_graph()
    a = g.add_node(_make_node("A"))
    b = g.add_node(_make_node("B"))
    g.add_edge(a.id, b.id, kind="sequence")
    new_node = _make_node("PREREQ")
    g.insert_before(b.id, new_node)
    sequence_targets = [e.to_node_id for e in g.edges if e.kind == "sequence"]
    prerequisite_edges = [e for e in g.edges if e.kind == "prerequisite"]
    assert new_node.id in sequence_targets
    assert b.id not in sequence_targets
    assert len(prerequisite_edges) == 1
    assert prerequisite_edges[0].from_node_id == new_node.id
    assert prerequisite_edges[0].to_node_id == b.id


def test_insert_after_does_not_disturb_sequence():
    # A -> B with a "deeper" node hung off A.
    g = _make_graph()
    a = g.add_node(_make_node("A"))
    b = g.add_node(_make_node("B"))
    g.add_edge(a.id, b.id, kind="sequence")
    deeper = _make_node("DEEPER")
    g.insert_after(a.id, deeper)
    sequence_edges = [e for e in g.edges if e.kind == "sequence"]
    deeper_edges = [e for e in g.edges if e.kind == "deeper"]
    assert len(sequence_edges) == 1
    assert sequence_edges[0].from_node_id == a.id
    assert sequence_edges[0].to_node_id == b.id
    assert len(deeper_edges) == 1
    assert deeper_edges[0].from_node_id == a.id
    assert deeper_edges[0].to_node_id == deeper.id


# --- readiness ---


def test_readiness_empty_graph_is_zero():
    g = _make_graph()
    assert g.readiness() == 0.0


def test_readiness_counts_only_understood():
    g = _make_graph()
    a = g.add_node(_make_node("A"))
    b = g.add_node(_make_node("B"))
    g.add_node(_make_node("C"))
    g.mark_understanding(a.id, "understood")
    g.mark_understanding(b.id, "partial")
    assert g.readiness() == pytest.approx(1 / 3)


# --- traversal ---


def test_next_in_sequence_follows_chain():
    g = _make_graph()
    a = g.add_node(_make_node("A"))
    b = g.add_node(_make_node("B"))
    c = g.add_node(_make_node("C"))
    g.add_edge(a.id, b.id, kind="sequence")
    g.add_edge(b.id, c.id, kind="sequence")
    assert g.next_in_sequence(a.id) == b.id
    assert g.next_in_sequence(b.id) == c.id
    assert g.next_in_sequence(c.id) is None  # end of chain


def test_next_in_sequence_ignores_non_sequence_edges():
    g = _make_graph()
    a = g.add_node(_make_node("A"))
    deeper = g.add_node(_make_node("DEEPER"))
    g.add_edge(a.id, deeper.id, kind="deeper")
    # Only "deeper" edge leaves A — sequence traversal stops here.
    assert g.next_in_sequence(a.id) is None


def test_sequence_head_is_node_with_no_incoming_sequence_edge():
    g = _make_graph()
    a = g.add_node(_make_node("A"))
    b = g.add_node(_make_node("B"))
    g.add_edge(a.id, b.id, kind="sequence")
    assert g.sequence_head() == a.id


def test_sequence_head_none_on_empty_graph():
    assert _make_graph().sequence_head() is None


# --- serialization ---


def test_to_dict_shape():
    g = _make_graph()
    a = g.add_node(_make_node("A"))
    b = g.add_node(_make_node("B"))
    g.add_edge(a.id, b.id, kind="sequence")
    g.set_current(a.id)
    g.mark_understanding(a.id, "understood")
    d = g.to_dict()
    assert d["session_id"] == g.session_id
    assert d["current_node_id"] == a.id
    assert d["readiness"] == pytest.approx(0.5)
    assert len(d["nodes"]) == 2
    assert len(d["edges"]) == 1
    assert d["edges"][0]["kind"] == "sequence"
    node_a = next(n for n in d["nodes"] if n["id"] == a.id)
    assert node_a["understanding_state"] == "understood"
    assert node_a["has_lesson"] is False


def test_to_dict_has_lesson_reflects_cache():
    g = _make_graph()
    a = g.add_node(_make_node("A"))
    a.cached_lesson = {"walkthrough": "x", "prompt": "y", "expected_answer": "z",
                       "prompt_kind": "predict-then-reveal"}
    d = g.to_dict()
    assert d["nodes"][0]["has_lesson"] is True
