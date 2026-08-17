"""M1 — the gap model, its persistence, and the flag contract.

gap-model.md M1. What M1 had to prove is that the data exists, survives, and —
at the time — changed nothing: gaps were deliberately INERT, because blocking
could not land until M6 made closure possible.

**The inertness claim expired when M7 shipped**, and one test here was inverted
to say so rather than deleted, so the sequencing rule's history stays readable.
Everything else in this file is about the model and its persistence, which M7
did not touch.

Run with: uv run pytest tests/test_gap_model.py -v
"""
import ast
import inspect
import json
import sqlite3

import pytest

from backend.learning import store as learning_store
from backend.learning.flags import gaps_enabled
from backend.learning.gaps import (
    BLOCKING_KINDS,
    GAP_KINDS,
    NON_GAP_KINDS,
    Gap,
    GapState,
)
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode, understanding_of


REPO = "https://github.com/psf/requests"
GOAL = {"primary_goal": "x", "goal_type": "understand_component"}

# The two misconceptions from the answer that motivated the whole phase
# (AIMA search.py, session 9d432157). Both `wrong_model`, both independent —
# the case the old scalar `gap_kind` could not represent.
CLAIM_A = "child path_cost and depth are filled in later by the search algorithm"
CLAIM_B = "solution() returns both the states and the actions"


def _graph_with_two_gaps() -> tuple[LearningGraph, LearningNode]:
    graph = LearningGraph(repo_url=REPO, goal=GOAL)
    node = graph.add_node(LearningNode(
        title="Understand Node as the universal search tree unit",
        code_anchor=CodeAnchor(file="search.py", line_start=68, line_end=130),
    ))
    node.gap_state.gaps.append(Gap.create(
        "wrong_model", CLAIM_A, objective_part="what data a Node holds",
    ))
    node.gap_state.gaps.append(Gap.create(
        "wrong_model", CLAIM_B, objective_part="what solution() reconstructs",
    ))
    return graph, node


# ── the model ────────────────────────────────────────────────────────────────


def test_two_misconceptions_of_the_same_kind_are_two_gaps():
    """The whole point of the phase, at the model level.

    Both are `wrong_model`. Under the old scalar field one of them had nowhere
    to live; here they are two objects with two ids and two claims.
    """
    _, node = _graph_with_two_gaps()
    assert len(node.gaps) == 2
    assert node.gaps[0].id != node.gaps[1].id
    assert {g.claim for g in node.gaps} == {CLAIM_A, CLAIM_B}


def test_blocking_is_a_pure_function_of_kind():
    assert Gap.create("wrong_model", "x").is_blocking
    assert Gap.create("missing_prerequisite", "x").is_blocking
    assert not Gap.create("right_idea_wrong_altitude", "x").is_blocking


def test_silence_never_becomes_a_gap():
    """`no_attempt` and `none` must not open a gap — §18.16 LQ9.

    Raising rather than dropping: a caller trying to open a gap for silence has
    misunderstood the policy, and swallowing it would hide that.
    """
    for kind in NON_GAP_KINDS:
        with pytest.raises(ValueError, match="never becomes a gap"):
            Gap.create(kind, "they said they did not know")


def test_an_unknown_kind_is_rejected_at_creation_but_preserved_on_load():
    with pytest.raises(ValueError, match="unknown gap kind"):
        Gap.create("vibes", "x")
    # Loading is deliberately permissive — dropping stored data would be the
    # silent loss the flag contract forbids — and an unknown kind is harmless
    # because it cannot block.
    revived = Gap.from_dict({"id": "abc", "kind": "vibes", "claim": "x"})
    assert revived.kind == "vibes"
    assert not revived.is_blocking


def test_a_gap_needs_a_claim():
    with pytest.raises(ValueError, match="needs a claim"):
        Gap.create("wrong_model", "   ")


def test_identity_is_ours_and_unique():
    ids = {Gap.create("wrong_model", f"claim {i}").id for i in range(50)}
    assert len(ids) == 50


def test_a_new_gap_starts_open_and_unverified():
    gap = Gap.create("wrong_model", CLAIM_A)
    assert gap.status == "open"
    assert gap.is_open
    assert gap.verification_attempts == 0
    assert gap.resolved_by is None
    assert gap.opened_at  # stamped


def test_the_vocabularies_match_the_approved_policy():
    assert BLOCKING_KINDS == {"missing_prerequisite", "wrong_model"}
    assert GAP_KINDS == {
        "missing_prerequisite", "wrong_model", "right_idea_wrong_altitude",
    }
    assert NON_GAP_KINDS == {"none", "no_attempt"}
    assert BLOCKING_KINDS <= GAP_KINDS
    assert not (NON_GAP_KINDS & GAP_KINDS)


# ── persistence ──────────────────────────────────────────────────────────────


def test_gaps_survive_a_save_and_load_with_every_field_intact(tmp_path):
    db = tmp_path / "s.db"
    graph, node = _graph_with_two_gaps()
    node.gap_state.gaps[0].status = "waived"
    node.gap_state.gaps[1].verification_attempts = 1
    node.gap_state.remediation_rounds = 2
    before = node.gap_state.to_dict()

    learning_store.save_graph(graph, db)
    reloaded = learning_store.load_graph(graph.session_id, db)

    assert reloaded.nodes[node.id].gap_state.to_dict() == before


def test_a_graph_with_no_gaps_round_trips_as_empty(tmp_path):
    db = tmp_path / "s.db"
    graph = LearningGraph(repo_url=REPO, goal=GOAL)
    node = graph.add_node(LearningNode(
        title="A", code_anchor=CodeAnchor(file="a.py", line_start=1, line_end=2)))
    learning_store.save_graph(graph, db)
    reloaded = learning_store.load_graph(graph.session_id, db)
    assert reloaded.nodes[node.id].gaps == []
    assert reloaded.nodes[node.id].gap_state.remediation_rounds == 0


def test_a_pre_gap_row_with_a_null_column_loads_unchanged(tmp_path):
    """Every session written before this phase. The column is NULL for them."""
    db = tmp_path / "s.db"
    graph = LearningGraph(repo_url=REPO, goal=GOAL)
    node = graph.add_node(LearningNode(
        title="A", code_anchor=CodeAnchor(file="a.py", line_start=1, line_end=2)))
    learning_store.save_graph(graph, db)
    with sqlite3.connect(db) as conn:          # simulate a pre-migration row
        conn.execute("UPDATE nodes SET gaps_json = NULL")
        conn.commit()

    reloaded = learning_store.load_graph(graph.session_id, db)
    assert reloaded is not None
    assert reloaded.nodes[node.id].gaps == []


def test_a_bare_list_payload_degrades_rather_than_losing_the_gaps():
    state = GapState.from_dict([{"id": "a", "kind": "wrong_model", "claim": CLAIM_A}])
    assert len(state.gaps) == 1
    assert state.remediation_rounds == 0


def test_schema_version_did_not_move():
    """A bump would make every existing session invisible to this code."""
    assert learning_store.SCHEMA_VERSION == 2


# ── the flag contract (gap-model.md §3.8) ────────────────────────────────────


def test_the_persistence_path_never_reads_the_flag():
    """Structural, so the contract cannot rot.

    The flag gates behaviour, never storage. If persistence ever consults it,
    every round-trip guarantee below becomes conditional.

    Parsed as an AST rather than grepped, so that the module may *explain* the
    contract in a comment — which it does — without the explanation tripping the
    assertion. Comments do not survive parsing; code does.
    """
    tree = ast.parse(inspect.getsource(learning_store))
    names = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    } | {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "CODEONBOARD_GAPS" not in names
    assert "gaps_enabled" not in names
    assert "getenv" not in names and "environ" not in names

    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    } | {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert not any("flags" in name for name in imported)


def test_gaps_written_flag_on_load_intact_with_the_flag_off(tmp_path, monkeypatch):
    db = tmp_path / "s.db"
    monkeypatch.setenv("CODEONBOARD_GAPS", "1")
    graph, node = _graph_with_two_gaps()
    learning_store.save_graph(graph, db)
    expected = node.gap_state.to_dict()

    monkeypatch.setenv("CODEONBOARD_GAPS", "0")
    assert not gaps_enabled()
    reloaded = learning_store.load_graph(graph.session_id, db)
    assert reloaded.nodes[node.id].gap_state.to_dict() == expected


def test_a_flag_off_resave_does_not_destroy_gaps(tmp_path, monkeypatch):
    """The trap worth naming: a flag-off session that touches something else.

    Load a gap-bearing graph with the flag off, change an unrelated field, save
    it back. The gaps must survive — otherwise turning the flag off once is
    silent, permanent data loss.
    """
    db = tmp_path / "s.db"
    monkeypatch.setenv("CODEONBOARD_GAPS", "1")
    graph, node = _graph_with_two_gaps()
    learning_store.save_graph(graph, db)
    expected = node.gap_state.to_dict()

    monkeypatch.setenv("CODEONBOARD_GAPS", "0")
    reloaded = learning_store.load_graph(graph.session_id, db)
    reloaded.nodes[node.id].title = "changed while the flag was off"
    reloaded.mark_visited(node.id)
    learning_store.save_graph(reloaded, db)

    monkeypatch.setenv("CODEONBOARD_GAPS", "1")
    again = learning_store.load_graph(graph.session_id, db)
    assert again.nodes[node.id].gap_state.to_dict() == expected
    assert again.nodes[node.id].title == "changed while the flag was off"


def test_re_enabling_the_flag_restores_exactly_the_persisted_state(tmp_path, monkeypatch):
    db = tmp_path / "s.db"
    monkeypatch.setenv("CODEONBOARD_GAPS", "1")
    graph, node = _graph_with_two_gaps()
    node.gap_state.gaps[0].status = "verified"
    node.gap_state.gaps[0].resolved_by = 3
    node.gap_state.remediation_rounds = 1
    learning_store.save_graph(graph, db)
    expected = json.dumps(node.gap_state.to_dict(), sort_keys=True)

    for setting in ("0", "1", "0", "1"):
        monkeypatch.setenv("CODEONBOARD_GAPS", setting)
        reloaded = learning_store.load_graph(graph.session_id, db)
        got = json.dumps(reloaded.nodes[node.id].gap_state.to_dict(), sort_keys=True)
        assert got == expected, f"gap state changed with the flag at {setting}"


def test_the_flag_defaults_to_off(monkeypatch):
    monkeypatch.delenv("CODEONBOARD_GAPS", raising=False)
    assert not gaps_enabled()


# ── M1 is inert ──────────────────────────────────────────────────────────────


def test_open_gaps_reach_the_api_payload_by_name():
    """Inverted when M9 landed; through M1–M8 this asserted the opposite.

    M1's contract was that nothing observable changed, and the wire was part of
    that — "gaps surface in M9" was the note. M9 is where they surface, so the
    expectation flips. What is asserted now is the shape M9 promised: OPEN gaps,
    named, with the `blocking` flag the UI needs to distinguish "holding this
    stop back" from "worth knowing".

    The internal container still does not leak: `gap_state` is storage, `gaps`
    is the wire.
    """
    graph, node = _graph_with_two_gaps()
    payload = graph.to_dict()
    node_payload = next(n for n in payload["nodes"] if n["id"] == node.id)

    assert "gap_state" not in node_payload
    assert {g["claim"] for g in node_payload["gaps"]} == {CLAIM_A, CLAIM_B}
    assert all(g["blocking"] is True for g in node_payload["gaps"])

    # Settled gaps are not outstanding work and do not appear.
    node.gap_state.gaps[0].waive()
    reshown = next(
        n for n in graph.to_dict()["nodes"] if n["id"] == node.id
    )["gaps"]
    assert [g["claim"] for g in reshown] == [CLAIM_B]


def test_gaps_now_hold_back_understanding_and_readiness():
    """Updated when M7 landed; it previously asserted the opposite.

    Through M1–M6 this test pinned the fact that gaps were INERT — recorded but
    powerless — because blocking had to wait until M6 made closure possible.
    That was the point of the sequencing rule, and this assertion is what proved
    the rule was being followed.

    M7 gives gaps their teeth, so the expectation inverts. What survives
    unchanged is the *recording*: `mark_understanding` still writes what the
    Grader concluded. What changed is that writing it no longer settles the
    question — `understanding_of` does, and it will not report mastery over two
    open blocking gaps.
    """
    graph, node = _graph_with_two_gaps()
    graph.mark_understanding(node.id, "understood")
    assert node.understanding_state == "understood"   # still recorded
    assert understanding_of(node) == "partial"        # but not concluded
    assert graph.readiness() < 1.0
