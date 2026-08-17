"""
Pytest tests for the adaptation policy (backend/learning/adaptation.py).
Run with: uv run pytest tests/test_adaptation.py -v

No client and no API key: which response a gap earns is a rule, not a judgement,
and prune-ahead is pure Python over state that already exists. What each
response then SAYS is generated, and lives in the teaching agent.
"""
import pytest

from backend.learning import progress
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


def test_an_unrelated_off_topic_answer_never_reshapes_the_path():
    # Preserved from the 2026-08-14 fix, and now stated precisely: what earns
    # nothing is an off-topic answer that names NO gap. That is the case where
    # there is genuinely no evidence — not off-topic as such.
    for gap in (None, "none", ""):
        assert decide("off-topic", gap) == "none"


def test_i_dont_know_still_gets_a_hint_even_though_it_grades_off_topic():
    # The Grader classifies "I don't know" as off-topic with a no_attempt gap.
    assert decide("off-topic", "no_attempt") == "hint"
    assert decide("off-topic", "right_idea_wrong_altitude") == "followup"


def test_a_named_missing_prerequisite_survives_an_off_topic_classification():
    """The defect this pins, found in live fastapi validation.

    A learner wrote "I can't follow this because I don't know what a function
    signature is". The Grader read it exactly right and reported
    `missing_prerequisite`; the policy discarded the signal because the same
    answer was also classified `off-topic`, and the learner got nothing at all —
    in the one case a prerequisite exists for.
    """
    assert decide("off-topic", "missing_prerequisite") == "prerequisite"


def test_the_named_gap_outranks_the_coarse_classification():
    # The general rule behind that fix: classification says how far the answer
    # fell short, gap_kind says why. The specific signal decides.
    for classification in ("off-topic", "confused", "partial"):
        assert decide(classification, "missing_prerequisite") == "prerequisite"
        assert decide(classification, "no_attempt") == "hint"
        assert decide(classification, "wrong_model") == "reteach"


def test_understood_still_outranks_everything():
    # The one place the classification does win: an answer that reached the
    # objective needs no response, whatever gap the Grader also volunteered.
    for gap in ("missing_prerequisite", "no_attempt", "wrong_model", "none"):
        assert decide("understood", gap) == "none"


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
        # Evidence, not a bare flag: Model A' defines demonstrated coverage
        # over `understanding.classify`, which needs an assessed answer.
        if state in ("understood", "partial", "failed"):
            graph.record_attempt(
                node.id, "an answer",
                {"understood": "understood", "partial": "partial",
                 "failed": "confused"}[state], "because")
            node.understanding_state = state
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


def test_pruning_ahead_never_lowers_progress():
    """Adapting upward must not punish the learner — and must not flatter them.

    RE-POINTED with the progress model (learning-graph.md §5.5). This used to
    assert that pruning RAISED `readiness()`, which was true and is now the
    wrong thing to want: pruning changes the PLAN, and goal readiness is
    evidence-only (OQ-3). The shortening is real, so it shows up where it
    belongs — in journey progress.
    """
    graph = _graph_with([
        ("a1", "required", "understood"),
        ("a1", "required", "understood"),
        ("a1", "recommended", "not_started"),
        ("a1", "recommended", "not_started"),
    ])
    goal_before = progress.goal_readiness(graph)
    journey_before = progress.journey_progress(graph)

    prune_ahead(graph)

    assert progress.goal_readiness(graph) == goal_before
    assert progress.journey_progress(graph) > journey_before


def test_partial_earns_no_demonstrated_credit():
    """RE-POINTED for Model A' (was `test_partial_still_scores_half`, 0.75).

    An assessed unit that fell short is not half-demonstrated; it is not
    demonstrated. It stays visible as *Needs work* in the profile.
    """
    graph = _graph_with([
        ("a1", "required", "understood"),
        ("a1", "required", "partial"),
    ])
    assert graph.readiness() == 0.5


def test_a_graph_of_only_optional_units_does_not_divide_by_zero():
    graph = _graph_with([("a1", "optional", "understood")])
    assert graph.readiness() == 0.0
