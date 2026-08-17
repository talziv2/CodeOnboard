# The progress model — learning-graph.md §5.
#
# The centrepiece is `TestPlanMutationNeverLowersGoalReadiness`, which pins
# decision OQ-3 mechanically:
#
#   Goal readiness may fall ONLY when evidence about the learner changes.
#   It must NEVER fall because the system changed the plan.
#
# Every one of those tests corresponds to a row of §5.5's table. They are the
# reason this module exists — the previous gauge failed the first of them, and a
# progress number that moves for reasons the learner cannot see is worse than no
# number at all.

import pytest

from backend.learning import progress, scope
from backend.learning.adaptation import prune_ahead
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode


def _graph(units: list[tuple[str, str, str]]) -> LearningGraph:
    """units: (area_id, priority, understanding_state), chained by sequence edges.

    Same shape as the helpers in test_adaptation.py / test_scope.py, so a
    behaviour asserted there can be compared against one asserted here.
    """
    graph = LearningGraph(repo_url="r", goal={})
    previous = None
    for i, (area, priority, state) in enumerate(units):
        node = graph.add_node(LearningNode(
            title=f"n{i}",
            code_anchor=CodeAnchor(file="a.py", line_start=1, line_end=2),
            lesson_brief={"area_id": area, "priority": priority, "objective": "x"},
        ))
        node.understanding_state = state
        if state != "not_started":
            node.visited = True
        if previous:
            graph.add_edge(previous.id, node.id, kind="sequence")
        previous = node
    if graph.nodes:
        graph.set_current(graph.path_order()[0])
    return graph


def _warm_up(graph: LearningGraph, anchor_id: str, *, origin=progress.SYSTEM_REMEDIATION):
    """Splice in a remedial warm-up exactly as the Mutator does."""
    node = LearningNode(
        title="warm-up",
        code_anchor=CodeAnchor(file="w.py", line_start=1, line_end=2),
        lesson_brief={"priority": "required", "objective": "x", progress.ORIGIN_KEY: origin},
    )
    return graph.insert_before(anchor_id, node, kind="prerequisite")


# ── the invariant (OQ-3) ──────────────────────────────────────────────────────


class TestPlanMutationNeverLowersGoalReadiness:
    """§5.5, row by row. Each mutation is one way the system changes the plan."""

    def test_inserting_a_remedial_prerequisite_does_not_lower_it(self):
        # The defect this whole milestone exists to fix. Measured before the
        # change: 0.50 -> 0.33, because the Mutator marks its warm-up
        # `priority: required` and it landed in the denominator.
        graph = _graph([
            ("a1", "required", "understood"),
            ("a1", "required", "not_started"),
        ])
        blocked = graph.path_order()[1]
        before = progress.goal_readiness(graph)

        _warm_up(graph, blocked)

        assert progress.goal_readiness(graph) == before == pytest.approx(0.5)

    def test_completing_the_warm_up_does_not_raise_it_either(self):
        # OQ-2: a warm-up earns no credit toward the goal. Symmetry with the
        # test above is the point — it is excluded, not merely discounted.
        graph = _graph([
            ("a1", "required", "understood"),
            ("a1", "required", "not_started"),
        ])
        warm_up = _warm_up(graph, graph.path_order()[1])
        before = progress.goal_readiness(graph)

        warm_up.understanding_state = "understood"
        warm_up.visited = True

        assert progress.goal_readiness(graph) == before

    def test_the_return_attempt_is_what_moves_the_number(self):
        # The other half of OQ-2: the learner's work is not lost, it is credited
        # where it was demonstrated — on the unit the warm-up unblocked.
        graph = _graph([
            ("a1", "required", "understood"),
            ("a1", "required", "not_started"),
        ])
        blocked = graph.path_order()[1]
        _warm_up(graph, blocked)
        before = progress.goal_readiness(graph)

        graph.mark_understanding(blocked, "understood")

        assert progress.goal_readiness(graph) > before

    def test_prune_ahead_does_not_change_it(self):
        # Adapting upward shortens the journey. Under the old gauge this RAISED
        # the headline number, which is the same defect as D1 in the other
        # direction: the plan changed, so the goal measure must not move.
        graph = _graph([
            ("a1", "required", "understood"),
            ("a1", "required", "understood"),
            ("a1", "recommended", "not_started"),
            ("a1", "recommended", "not_started"),
        ])
        before = progress.goal_readiness(graph)

        assert prune_ahead(graph), "fixture must actually demote something"

        assert progress.goal_readiness(graph) == before

    def test_scope_shorter_does_not_change_it(self):
        graph = _graph([
            ("a1", "required", "understood"),
            ("a1", "recommended", "not_started"),
            ("a1", "recommended", "not_started"),
        ])
        before = progress.goal_readiness(graph)

        assert scope.shorten(graph), "fixture must actually demote something"

        assert progress.goal_readiness(graph) == before

    def test_scope_deeper_does_not_change_it(self):
        graph = _graph([
            ("a1", "required", "understood"),
            ("a1", "optional", "not_started"),
        ])
        before = progress.goal_readiness(graph)

        assert scope.deepen(graph), "fixture must actually promote something"

        assert progress.goal_readiness(graph) == before

    def test_skipping_a_stop_does_not_change_it(self):
        # A skip scores zero and always did; what must not happen is the number
        # moving at the moment of the skip.
        graph = _graph([
            ("a1", "required", "understood"),
            ("a1", "required", "not_started"),
        ])
        before = progress.goal_readiness(graph)

        graph.override(graph.path_order()[1], "skip")

        assert progress.goal_readiness(graph) == before


class TestEvidenceMayLowerGoalReadiness:
    """The other side of OQ-3 — a ratchet would be dishonest, so falls on real
    evidence must stay possible."""

    def test_a_worse_re_answer_lowers_it(self):
        graph = _graph([("a1", "required", "understood")])
        before = progress.goal_readiness(graph)

        graph.mark_understanding(graph.path_order()[0], "failed")

        assert progress.goal_readiness(graph) < before

    def test_understanding_withdrawn_to_partial_scores_half(self):
        graph = _graph([("a1", "required", "understood")])
        graph.mark_understanding(graph.path_order()[0], "partial")
        assert progress.goal_readiness(graph) == pytest.approx(0.5)


# ── goal readiness ────────────────────────────────────────────────────────────


class TestGoalReadiness:
    def test_denominator_is_the_required_set_only(self):
        # `recommended` is "included if there is room" — enrichment, not what the
        # goal requires. Counting it would dilute a claim about the goal.
        graph = _graph([
            ("a1", "required", "understood"),
            ("a1", "recommended", "not_started"),
            ("a1", "recommended", "not_started"),
        ])
        assert progress.goal_readiness(graph) == 1.0

    def test_partial_scores_half(self):
        graph = _graph([
            ("a1", "required", "understood"),
            ("a1", "required", "partial"),
        ])
        assert progress.goal_readiness(graph) == 0.75

    def test_failed_and_not_started_score_nothing(self):
        graph = _graph([
            ("a1", "required", "failed"),
            ("a1", "required", "not_started"),
        ])
        assert progress.goal_readiness(graph) == 0.0

    def test_optional_units_earn_no_credit(self):
        # Changed from the previous gauge, which counted optional work in the
        # numerator while excluding it from the denominator. That let a number
        # about the goal rise on work the goal never asked for.
        graph = _graph([
            ("a1", "required", "not_started"),
            ("a1", "optional", "understood"),
        ])
        assert progress.goal_readiness(graph) == 0.0

    def test_cannot_exceed_one(self):
        graph = _graph([
            ("a1", "required", "understood"),
            ("a1", "optional", "understood"),
            ("a1", "optional", "understood"),
        ])
        assert progress.goal_readiness(graph) == 1.0

    def test_empty_graph_is_zero(self):
        assert progress.goal_readiness(_graph([])) == 0.0

    def test_a_graph_with_no_required_units_is_zero_not_a_crash(self):
        graph = _graph([("a1", "optional", "understood")])
        assert progress.goal_readiness(graph) == 0.0


# ── journey progress ──────────────────────────────────────────────────────────


class TestJourneyProgress:
    def test_counts_stops_dealt_with_not_stops_mastered(self):
        # The reason there are two measures: walking the journey without
        # answering reads 0% on goal readiness, which is correct and would be
        # the only number on screen without this one.
        graph = _graph([
            ("a1", "required", "not_started"),
            ("a1", "required", "not_started"),
        ])
        for node in graph.nodes.values():
            node.visited = True

        assert progress.journey_progress(graph) == 1.0
        assert progress.goal_readiness(graph) == 0.0

    def test_a_skip_settles_a_stop(self):
        graph = _graph([("a1", "required", "not_started")])
        graph.override(graph.path_order()[0], "skip")
        assert progress.journey_progress(graph) == 1.0

    def test_optional_units_are_not_stops(self):
        graph = _graph([
            ("a1", "required", "understood"),
            ("a1", "optional", "not_started"),
        ])
        assert progress.journey_progress(graph) == 1.0

    def test_remedial_warm_ups_are_not_stops(self):
        graph = _graph([
            ("a1", "required", "understood"),
            ("a1", "required", "not_started"),
        ])
        _warm_up(graph, graph.path_order()[1])
        assert progress.summary(graph)["stops_total"] == 2

    def test_shortening_the_journey_raises_it(self):
        # Where the old `readiness()` behaviour correctly belongs: the same work
        # over a smaller journey IS more journey progress. It is a statement
        # about the plan, so it moves the plan measure and not the goal measure.
        graph = _graph([
            ("a1", "required", "understood"),
            ("a1", "recommended", "not_started"),
            ("a1", "recommended", "not_started"),
        ])
        before = progress.journey_progress(graph)
        scope.shorten(graph)
        assert progress.journey_progress(graph) > before


# ── provenance ────────────────────────────────────────────────────────────────


class TestRemedialDetection:
    def test_a_spliced_warm_up_is_remedial(self):
        graph = _graph([("a1", "required", "understood"), ("a1", "required", "not_started")])
        warm_up = _warm_up(graph, graph.path_order()[1])
        assert warm_up.id in progress.remedial_ids(graph)

    def test_a_planned_dependency_edge_is_not_remedial(self):
        # The defect that shipped once already: the B3 planner emits a
        # `prerequisite` edge per `depends_on`, dozens per journey. Reading edge
        # kind alone reports a planned curriculum as a sequence of failures.
        graph = _graph([
            ("a1", "required", "understood"),
            ("a1", "required", "not_started"),
            ("a1", "required", "not_started"),
        ])
        first, second, third = graph.path_order()
        graph.add_edge(first, third, kind="prerequisite")
        graph.add_edge(second, third, kind="prerequisite")

        assert progress.remedial_ids(graph) == set()

    def test_the_last_planned_stop_is_not_remedial(self):
        # It has no outgoing sequence edge either — which is why the structural
        # rule requires an outgoing PREREQUISITE edge as well.
        graph = _graph([
            ("a1", "required", "understood"),
            ("a1", "required", "not_started"),
        ])
        assert progress.remedial_ids(graph) == set()

    def test_an_explicit_origin_overrides_the_structural_guess(self):
        graph = _graph([("a1", "required", "understood"), ("a1", "required", "not_started")])
        warm_up = _warm_up(graph, graph.path_order()[1])
        warm_up.lesson_brief[progress.ORIGIN_KEY] = progress.PLANNED

        assert progress.remedial_ids(graph) == set()

    def test_a_learner_requested_warm_up_keeps_its_origin(self):
        graph = _graph([("a1", "required", "understood"), ("a1", "required", "not_started")])
        warm_up = _warm_up(graph, graph.path_order()[1], origin=progress.LEARNER_REQUEST)

        detour = progress.detours(graph)[0]
        assert detour["origin"] == progress.LEARNER_REQUEST
        assert detour["unlocks"] == graph.path_order()[-1]

    def test_an_unmarked_warm_up_reports_system_remediation(self):
        # Every warm-up in the 62 stored sessions predates the `origin` key.
        # Claiming `learner_request` for one would invent an intent nothing
        # recorded, so the fallback names the policy-driven case.
        graph = _graph([("a1", "required", "understood"), ("a1", "required", "not_started")])
        node = LearningNode(
            title="warm-up",
            code_anchor=CodeAnchor(file="w.py", line_start=1, line_end=2),
            lesson_brief={"priority": "required"},
        )
        graph.insert_before(graph.path_order()[1], node, kind="prerequisite")

        assert progress.detours(graph)[0]["origin"] == progress.SYSTEM_REMEDIATION


# ── pre-B3 graphs ─────────────────────────────────────────────────────────────


class TestGraphsWithoutPriority:
    """The pre-B3 planner writes no `priority`, and 532 of 574 stored nodes are
    in that shape. Both measures must be defined on them, not merely not crash."""

    def _bare(self, states: list[str]) -> LearningGraph:
        graph = LearningGraph(repo_url="r", goal={})
        previous = None
        for i, state in enumerate(states):
            node = graph.add_node(LearningNode(
                title=f"n{i}",
                code_anchor=CodeAnchor(file="a.py", line_start=1, line_end=2),
            ))
            node.understanding_state = state
            if previous:
                graph.add_edge(previous.id, node.id, kind="sequence")
            previous = node
        return graph

    def test_a_missing_priority_counts_as_required(self):
        graph = self._bare(["understood", "partial", "not_started"])
        assert progress.goal_readiness(graph) == pytest.approx((1 + 0.5) / 3)

    def test_every_unit_is_a_stop(self):
        graph = self._bare(["understood", "not_started"])
        assert progress.summary(graph)["stops_total"] == 2


# ── evidence quality ──────────────────────────────────────────────────────────


class TestAssessedCoverage:
    def test_an_off_topic_answer_is_not_evidence(self):
        # A quarter of every attempt stored to date is off-topic. Counting them
        # as evidence would overstate how much of the journey is understood.
        graph = _graph([("a1", "required", "not_started")])
        node = graph.nodes[graph.path_order()[0]]
        node.attempts.append({"answer": "no idea", "classification": "off-topic",
                              "rationale": "", "at": "now"})

        assert progress.assessed_coverage(graph) == 0.0

    def test_a_real_answer_is_evidence_even_when_it_fell_short(self):
        graph = _graph([("a1", "required", "failed")])
        node = graph.nodes[graph.path_order()[0]]
        node.attempts.append({"answer": "wrong", "classification": "confused",
                              "rationale": "", "at": "now"})

        assert progress.assessed_coverage(graph) == 1.0


# ── the wire ──────────────────────────────────────────────────────────────────


class TestSummaryAndWire:
    def test_readiness_key_still_equals_goal_readiness(self):
        # Six call sites and the `/scope` response read this key. It keeps
        # working; only its definition moved.
        graph = _graph([
            ("a1", "required", "understood"),
            ("a1", "required", "not_started"),
        ])
        payload = graph.to_dict()

        assert payload["readiness"] == pytest.approx(0.5)
        assert payload["progress"]["goal_readiness"] == payload["readiness"]

    def test_summary_reports_detours_separately_from_both_measures(self):
        graph = _graph([
            ("a1", "required", "understood"),
            ("a1", "required", "not_started"),
        ])
        _warm_up(graph, graph.path_order()[1])
        summary = progress.summary(graph)

        assert summary["core_total"] == 2
        assert summary["stops_total"] == 2
        assert len(summary["detours"]) == 1

    def test_nodes_carry_objective_override_and_origin(self):
        graph = _graph([("a1", "required", "not_started")])
        node_id = graph.path_order()[0]
        graph.override(node_id, "mark_understood")
        node = next(n for n in graph.to_dict()["nodes"] if n["id"] == node_id)

        assert node["objective"] == "x"
        assert node["user_override"] == "mark_understood"
        assert node["origin"] == progress.PLANNED

    def test_skips_are_counted_so_a_low_number_is_explainable(self):
        graph = _graph([
            ("a1", "required", "not_started"),
            ("a1", "required", "not_started"),
        ])
        graph.override(graph.path_order()[0], "skip")

        assert progress.summary(graph)["skipped"] == 1
