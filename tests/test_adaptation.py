"""
Pytest tests for the adaptation policy (backend/learning/adaptation.py).
Run with: uv run pytest tests/test_adaptation.py -v

No client and no API key: which response a gap earns is a rule, not a judgement,
and prune-ahead is pure Python over state that already exists. What each
response then SAYS is generated, and lives in the teaching agent.
"""
import pytest

from backend.learning.adaptation import decide, prune_ahead
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode


# ── the policy table ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("gap,action", [
    ("no_attempt", "hint"),
    ("wrong_model", "reteach"),
    ("missing_prerequisite", "prerequisite"),
    ("right_idea_wrong_altitude", "followup"),
])
def test_the_gap_decides_the_response(gap, action):
    assert decide("confused", gap) == action


def test_only_a_missing_foundation_changes_the_graph():
    structural = [
        g for g in ("no_attempt", "wrong_model", "missing_prerequisite",
                    "right_idea_wrong_altitude")
        if decide("confused", g) == "prerequisite"
    ]
    assert structural == ["missing_prerequisite"]


def test_not_knowing_gets_a_hint_rather_than_a_longer_journey():
    # The defect this replaces: "I don't know" and a confident misconception
    # both produced a prerequisite.
    assert decide("confused", "no_attempt") == "hint"
    assert decide("confused", "wrong_model") == "reteach"


def test_an_understood_answer_earns_no_response():
    assert decide("understood", "none") == "none"


def test_an_off_topic_answer_never_reshapes_the_path():
    # Preserved from the 2026-08-14 fix: an unrelated answer is evidence of
    # neither understanding nor misunderstanding, so nothing STRUCTURAL.
    for gap in ("wrong_model", "missing_prerequisite", None, "none"):
        assert decide("off-topic", gap) == "none"


def test_i_dont_know_still_gets_a_hint_even_though_it_grades_off_topic():
    # The Grader classifies "I don't know" as off-topic with a no_attempt gap.
    # Withholding the hint because of the classification would apply a guard
    # meant for the GRAPH to a response that never touches it — and would leave
    # the one case the hint exists for with nothing at all.
    assert decide("off-topic", "no_attempt") == "hint"
    assert decide("off-topic", "right_idea_wrong_altitude") == "followup"


def test_a_grade_without_a_gap_keeps_the_pre_b5_behaviour():
    # Every session graded before gap_kind existed.
    assert decide("confused", None) == "prerequisite"
    assert decide("confused", "none") == "prerequisite"
    assert decide("partial", None) == "none"


# ── prune-ahead ───────────────────────────────────────────────────────────────

def _graph_with(units: list[tuple[str, str, str]]) -> LearningGraph:
    """units: (area_id, priority, understanding_state), chained in order."""
    graph = LearningGraph(repo_url="r", goal={})
    previous = None
    for i, (area, priority, state) in enumerate(units):
        node = graph.add_node(LearningNode(
            title=f"n{i}",
            code_anchor=CodeAnchor(file="a.py", line_start=1, line_end=2),
            lesson_brief={"area_id": area, "priority": priority, "objective": "x"},
        ))
        node.understanding_state = state
        if state in ("understood", "partial", "failed"):
            node.visited = True
        if previous:
            graph.add_edge(previous.id, node.id, kind="sequence")
        previous = node
    return graph


def priorities(graph: LearningGraph) -> list[str]:
    return [
        graph.nodes[i].lesson_brief["priority"] for i in graph.path_order()
    ]


def test_sustained_understanding_shortens_the_rest_of_that_area():
    graph = _graph_with([
        ("a1", "required", "understood"),
        ("a1", "required", "understood"),
        ("a1", "recommended", "not_started"),
        ("a1", "recommended", "not_started"),
    ])
    assert prune_ahead(graph)
    assert priorities(graph) == ["required", "required", "optional", "optional"]


def test_one_good_answer_is_not_enough():
    graph = _graph_with([
        ("a1", "required", "understood"),
        ("a1", "recommended", "not_started"),
    ])
    assert prune_ahead(graph) == []
    assert priorities(graph) == ["required", "recommended"]


def test_a_required_unit_is_never_demoted():
    # The required set is the floor of the curriculum, and past performance is
    # not evidence about a unit nobody has seen yet.
    graph = _graph_with([
        ("a1", "required", "understood"),
        ("a1", "required", "understood"),
        ("a1", "required", "not_started"),
    ])
    prune_ahead(graph)
    assert priorities(graph) == ["required", "required", "required"]


def test_another_areas_units_are_untouched():
    graph = _graph_with([
        ("a1", "required", "understood"),
        ("a1", "required", "understood"),
        ("a2", "recommended", "not_started"),
    ])
    prune_ahead(graph)
    assert priorities(graph)[2] == "recommended"


def test_a_broken_streak_stops_the_pruning():
    graph = _graph_with([
        ("a1", "required", "understood"),
        ("a1", "required", "failed"),
        ("a1", "required", "understood"),
        ("a1", "recommended", "not_started"),
    ])
    assert prune_ahead(graph) == []


def test_a_unit_already_worked_through_is_left_alone():
    # Demoting something the learner already did would rewrite their history.
    graph = _graph_with([
        ("a1", "required", "understood"),
        ("a1", "required", "understood"),
        ("a1", "recommended", "partial"),
    ])
    prune_ahead(graph)
    assert priorities(graph)[2] == "recommended"


def test_a_user_override_always_wins():
    # §9.2: overrides are the user's opinion; this is the system's.
    graph = _graph_with([
        ("a1", "required", "understood"),
        ("a1", "required", "understood"),
        ("a1", "recommended", "not_started"),
    ])
    target = graph.nodes[graph.path_order()[2]]
    target.user_override = "mark_weak"
    prune_ahead(graph)
    assert target.lesson_brief["priority"] == "recommended"


def test_pruning_demotes_and_never_deletes():
    graph = _graph_with([
        ("a1", "required", "understood"),
        ("a1", "required", "understood"),
        ("a1", "recommended", "not_started"),
    ])
    before = len(graph.nodes)
    prune_ahead(graph)
    assert len(graph.nodes) == before


def test_a_graph_with_no_areas_is_never_pruned():
    # Every pre-B3 graph.
    graph = LearningGraph(repo_url="r", goal={})
    for i in range(3):
        node = graph.add_node(LearningNode(
            title=f"n{i}",
            code_anchor=CodeAnchor(file="a.py", line_start=1, line_end=2),
            lesson_brief={"why": "x", "understand": "y"},
        ))
        node.understanding_state = "understood"
    assert prune_ahead(graph) == []


def test_pruning_is_idempotent():
    graph = _graph_with([
        ("a1", "required", "understood"),
        ("a1", "required", "understood"),
        ("a1", "recommended", "not_started"),
    ])
    assert len(prune_ahead(graph)) == 1
    assert prune_ahead(graph) == []


# ── core-weighted readiness ───────────────────────────────────────────────────

def test_optional_units_are_excluded_from_the_denominator():
    # L10: the gauge must not fall because the system shortened the journey.
    graph = _graph_with([
        ("a1", "required", "understood"),
        ("a1", "required", "understood"),
        ("a1", "optional", "not_started"),
    ])
    assert graph.readiness() == 1.0


def test_doing_an_optional_unit_never_lowers_the_gauge():
    graph = _graph_with([
        ("a1", "required", "understood"),
        ("a1", "optional", "understood"),
    ])
    assert graph.readiness() == 1.0


def test_pruning_ahead_raises_readiness_rather_than_lowering_it():
    graph = _graph_with([
        ("a1", "required", "understood"),
        ("a1", "required", "understood"),
        ("a1", "recommended", "not_started"),
        ("a1", "recommended", "not_started"),
    ])
    before = graph.readiness()
    prune_ahead(graph)
    assert graph.readiness() > before


def test_partial_still_scores_half():
    graph = _graph_with([
        ("a1", "required", "understood"),
        ("a1", "required", "partial"),
    ])
    assert graph.readiness() == 0.75


def test_a_graph_of_only_optional_units_does_not_divide_by_zero():
    graph = _graph_with([("a1", "optional", "understood")])
    assert graph.readiness() == 0.0
