"""M1 — the gap model and its persistence.

gap-model.md M1. What M1 had to prove is that the data exists, survives, and —
at the time — changed nothing: gaps were deliberately INERT, because blocking
could not land until M6 made closure possible.

**The inertness claim expired when M7 shipped**, and one test here was inverted
to say so rather than deleted, so the sequencing rule's history stays readable.
Everything else in this file is about the model and its persistence, which M7
did not touch.

`CODEONBOARD_GAPS` used to be the third subject here, with four tests toggling
it across a save and a load. The flag is gone — gap recording is unconditional —
so what those tests were really protecting is stated once, without it: the
persistence path reads no environment at all, and a gap survives a round trip
byte for byte. The structural test is the one that still earns its place, and it
now covers `CODEONBOARD_TUTOR` too, since it asserts the absence of the
mechanism rather than of one name.

Run with: uv run pytest tests/test_gap_model.py -v
"""
import ast
import inspect
import json
import sqlite3

import pytest

from tests.conftest import TEST_USER_ID

from backend.learning import store as learning_store
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

    learning_store.save_graph(graph, db, user_id=TEST_USER_ID)
    reloaded = learning_store.load_graph(graph.session_id, TEST_USER_ID, db)

    assert reloaded.nodes[node.id].gap_state.to_dict() == before


def test_a_graph_with_no_gaps_round_trips_as_empty(tmp_path):
    db = tmp_path / "s.db"
    graph = LearningGraph(repo_url=REPO, goal=GOAL)
    node = graph.add_node(LearningNode(
        title="A", code_anchor=CodeAnchor(file="a.py", line_start=1, line_end=2)))
    learning_store.save_graph(graph, db, user_id=TEST_USER_ID)
    reloaded = learning_store.load_graph(graph.session_id, TEST_USER_ID, db)
    assert reloaded.nodes[node.id].gaps == []
    assert reloaded.nodes[node.id].gap_state.remediation_rounds == 0


def test_a_pre_gap_row_with_a_null_column_loads_unchanged(tmp_path):
    """Every session written before this phase. The column is NULL for them."""
    db = tmp_path / "s.db"
    graph = LearningGraph(repo_url=REPO, goal=GOAL)
    node = graph.add_node(LearningNode(
        title="A", code_anchor=CodeAnchor(file="a.py", line_start=1, line_end=2)))
    learning_store.save_graph(graph, db, user_id=TEST_USER_ID)
    with sqlite3.connect(db) as conn:          # simulate a pre-migration row
        conn.execute("UPDATE nodes SET gaps_json = NULL")
        conn.commit()

    reloaded = learning_store.load_graph(graph.session_id, TEST_USER_ID, db)
    assert reloaded is not None
    assert reloaded.nodes[node.id].gaps == []


def test_a_bare_list_payload_degrades_rather_than_losing_the_gaps():
    state = GapState.from_dict([{"id": "a", "kind": "wrong_model", "claim": CLAIM_A}])
    assert len(state.gaps) == 1
    assert state.remediation_rounds == 0


def test_schema_version_moves_only_deliberately():
    """A bump makes every session written before it invisible to this code.

    Pinned at 2 for the whole Gap Model phase, whose persistence was additive by
    design: `gaps_json` arrived as a nullable column precisely so that stored
    sessions kept loading.

    **It moved to 3 for the plan snapshot** (session-reset.md D8) — and that is
    the decision this guard exists to force someone to make out loud. A session
    written before `plan_nodes` has no plan, so `Start over` cannot work for it,
    and a row that loads but cannot be reset is worse than one that does not
    load. The 90 v2 development sessions were copied to
    `data/sessions-fixtures.db` first, and the measurement scripts that pin
    session ids now read that file.

    Kept rather than deleted: it still fails on the NEXT bump, which is the point.
    """
    assert learning_store.SCHEMA_VERSION == 3


# ── the storage contract (gap-model.md §3.8) ──────────────────────────────────


def test_the_persistence_path_reads_no_feature_flag():
    """Structural, so the contract cannot rot.

    A flag gates behaviour, never storage. If persistence ever consults one,
    every round-trip guarantee below becomes conditional on how the process was
    launched — and turning a flag off once becomes silent, permanent data loss.

    Asserted as "reads no environment and imports no flags module" rather than
    as a list of flag names, which is why it outlived the flag it was written
    for: `CODEONBOARD_GAPS` no longer exists, `CODEONBOARD_TUTOR` still does,
    and the next one is covered before it is added.

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


def test_gap_state_survives_a_save_load_change_resave_round_trip(tmp_path):
    """The trap worth naming: a save that touches something else entirely.

    Load a gap-bearing graph, change an unrelated field, write it back. The gap
    state must come back byte for byte — status, `resolved_by`, the remediation
    counter, all of it. Anything that reads a gap on the way in and rebuilds it
    on the way out will fail here, which is the point: this is what makes
    "storage is unconditional" a checked claim rather than a comment.

    This was four tests, each toggling `CODEONBOARD_GAPS` across a step. With no
    flag left to toggle, the round trip itself is the whole of what they proved.
    """
    db = tmp_path / "s.db"
    graph, node = _graph_with_two_gaps()
    node.gap_state.gaps[0].status = "verified"
    node.gap_state.gaps[0].resolved_by = 3
    node.gap_state.remediation_rounds = 1
    learning_store.save_graph(graph, db, user_id=TEST_USER_ID)
    expected = json.dumps(node.gap_state.to_dict(), sort_keys=True)

    reloaded = learning_store.load_graph(graph.session_id, TEST_USER_ID, db)
    assert json.dumps(
        reloaded.nodes[node.id].gap_state.to_dict(), sort_keys=True
    ) == expected

    reloaded.nodes[node.id].title = "changed for an unrelated reason"
    reloaded.mark_visited(node.id)
    learning_store.save_graph(reloaded, db, user_id=TEST_USER_ID)

    again = learning_store.load_graph(graph.session_id, TEST_USER_ID, db)
    assert json.dumps(
        again.nodes[node.id].gap_state.to_dict(), sort_keys=True
    ) == expected
    assert again.nodes[node.id].title == "changed for an unrelated reason"


# ── M1 is inert ──────────────────────────────────────────────────────────────


def test_gaps_reach_the_api_payload_by_name_and_keep_their_status():
    """Inverted twice. Through M1–M8 this asserted that nothing surfaced at all;
    M9 flipped it to OPEN gaps only; the ledger flips the second half again.

    Settled gaps now ship too, because this payload is what the lesson falls
    back to between answers — filtering them out here is what made a gap the
    learner CLEARED vanish from the list that had just named it. `status` is how
    a consumer tells outstanding work from repaired work; the rail filters on it
    to keep its count meaning "still unresolved".

    The internal container still does not leak: `gap_state` is storage, `gaps`
    is the wire.
    """
    graph, node = _graph_with_two_gaps()
    payload = graph.to_dict()
    node_payload = next(n for n in payload["nodes"] if n["id"] == node.id)

    assert "gap_state" not in node_payload
    assert {g["claim"] for g in node_payload["gaps"]} == {CLAIM_A, CLAIM_B}
    assert all(g["blocking"] is True for g in node_payload["gaps"])
    assert all(g["status"] == "open" for g in node_payload["gaps"])

    # A settled gap KEEPS its row, and says how it settled.
    node.gap_state.gaps[0].waive()
    node.gap_state.gaps[1].mark_verified(0)
    reshown = next(
        n for n in graph.to_dict()["nodes"] if n["id"] == node.id
    )["gaps"]
    assert {g["claim"]: g["status"] for g in reshown} == {
        CLAIM_A: "waived", CLAIM_B: "verified",
    }
    # And when it settled, which is what the session log's gap rows read.
    assert all(g["closed_at"] for g in reshown)


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
