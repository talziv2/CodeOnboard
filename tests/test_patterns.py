# Learning patterns — L2 templates and their thresholds (M3a.2).
#
# Every test here exists to stop the UI saying something the evidence does not
# support. The negative cases matter more than the positive ones: a template
# that fires one observation early is worse than one that never fires, because
# the learner cannot tell the difference between a real pattern and a coincidence
# the system dressed up.
#
# The properties pinned:
#   - each template fires EXACTLY at its threshold, and not one observation below
#   - repetition on a single objective is never a cross-objective pattern
#   - grading failures and off-topic answers cannot manufacture one
#   - waived/continued units stay truthful in aggregates without becoming tasks
#   - unknown intervention history never distorts anything
#   - every rendered pattern resolves to real attempts

import pytest

from backend.learning import history, patterns, progress, understanding
from backend.learning.gaps import Gap
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode


def _graph(specs: list[tuple[str, str]]) -> LearningGraph:
    """specs: (kind, area_id) per unit, chained in order."""
    graph = LearningGraph(repo_url="r", goal={})
    graph.areas = [{"id": "a1", "title": "Request lifecycle", "why": "", "order": 1},
                   {"id": "a2", "title": "Adapters", "why": "", "order": 2}]
    previous = None
    for i, (kind, area) in enumerate(specs):
        node = graph.add_node(LearningNode(
            title=f"n{i}", code_anchor=CodeAnchor("a.py", 1, 2),
            lesson_brief={"priority": "required", "objective": f"claim {i}",
                          "area_id": area, "kind": kind},
        ))
        if previous:
            graph.add_edge(previous.id, node.id, kind="sequence")
        previous = node
    graph.set_current(graph.path_order()[0])
    return graph


def _answer(graph, node_id, classification, gap_kind="none", **over):
    graph.record_attempt(node_id, "an answer", classification, "because",
                         gap_kind=gap_kind, **over)
    mapping = {"understood": "understood", "partial": "partial", "confused": "failed"}
    if classification in mapping:
        graph.mark_understanding(node_id, mapping[classification])
    graph.record_response(node_id, history.new_response("none"))


def _templates(graph) -> dict[str, dict]:
    return {p["template"]: p for p in patterns.detect(graph)}


# ── P1 · kind contrast ────────────────────────────────────────────────────────


class TestKindContrast:
    def _two_kinds(self, flow_extra: int, flow_n: int, comp_n: int) -> LearningGraph:
        graph = _graph([("flow", "a1")] * flow_n + [("component", "a1")] * comp_n)
        ids = graph.path_order()
        for i in range(flow_n):
            if i < flow_extra:
                _answer(graph, ids[i], "partial")       # did not land first time
                _answer(graph, ids[i], "understood")
            else:
                _answer(graph, ids[i], "understood")
        for j in range(comp_n):
            _answer(graph, ids[flow_n + j], "understood")
        return graph

    def test_fires_at_the_threshold(self):
        # flow 2 of 2 needed a second answer, component 0 of 2 did.
        graph = self._two_kinds(flow_extra=2, flow_n=2, comp_n=2)
        card = _templates(graph)["kind_contrast"]
        assert card["detail"]["lead_kind"] == "flow"
        assert card["detail"]["lead_extra"] == 2
        assert card["detail"]["base_kind"] == "component"
        assert card["detail"]["base_extra"] == 0

    def test_one_supporting_unit_is_not_a_kind_difference(self):
        # THE negative case: a single rough unit must not become a claim about
        # a whole kind of understanding.
        graph = self._two_kinds(flow_extra=1, flow_n=2, comp_n=2)
        assert "kind_contrast" not in _templates(graph)

    def test_a_kind_with_one_assessed_unit_cannot_be_a_population(self):
        graph = self._two_kinds(flow_extra=2, flow_n=2, comp_n=1)
        assert "kind_contrast" not in _templates(graph)

    def test_no_contrast_when_both_kinds_behave_the_same(self):
        graph = _graph([("flow", "a1")] * 2 + [("component", "a1")] * 2)
        ids = graph.path_order()
        for node_id in ids:                       # every unit needs two answers
            _answer(graph, node_id, "partial")
            _answer(graph, node_id, "understood")
        assert "kind_contrast" not in _templates(graph)

    def test_a_recovered_unit_counts_as_having_needed_more_answers(self):
        # The claim is about ANSWERS, not mastery: recovering still took an
        # extra pass, and that is what is being counted.
        graph = self._two_kinds(flow_extra=2, flow_n=2, comp_n=2)
        lead_ids = {e["node_id"] for e in _templates(graph)["kind_contrast"]["evidence"]}
        for node_id in lead_ids:
            assert understanding.classify(graph.nodes[node_id]) == understanding.RECOVERED

    def test_evidence_points_at_the_answer_that_fell_short(self):
        graph = self._two_kinds(flow_extra=2, flow_n=2, comp_n=2)
        for ref in _templates(graph)["kind_contrast"]["evidence"]:
            attempt = graph.nodes[ref["node_id"]].attempts[ref["attempt_index"]]
            assert attempt["classification"] == "partial"


# ── P2 · recurring shortfall ──────────────────────────────────────────────────


class TestRecurringShortfall:
    def test_fires_at_three_across_two_objectives(self):
        graph = _graph([("flow", "a1")] * 2)
        a, b = graph.path_order()
        _answer(graph, a, "partial", "right_idea_wrong_altitude")
        _answer(graph, a, "partial", "right_idea_wrong_altitude")
        _answer(graph, b, "partial", "right_idea_wrong_altitude")

        card = _templates(graph)["recurring_shortfall"]
        assert card["detail"] == {
            "gap_kind": "right_idea_wrong_altitude", "attempts": 3, "nodes": 2,
        }

    def test_two_occurrences_are_not_a_repetition(self):
        graph = _graph([("flow", "a1")] * 2)
        a, b = graph.path_order()
        _answer(graph, a, "partial", "wrong_model")
        _answer(graph, b, "partial", "wrong_model")
        assert "recurring_shortfall" not in _templates(graph)

    def test_three_shortfalls_on_ONE_objective_is_not_cross_objective(self):
        # One unit going badly three times is one unit going badly.
        graph = _graph([("flow", "a1")] * 2)
        a, _ = graph.path_order()
        for _ in range(3):
            _answer(graph, a, "partial", "wrong_model")
        assert "recurring_shortfall" not in _templates(graph)

    def test_different_shortfall_kinds_do_not_add_up(self):
        graph = _graph([("flow", "a1")] * 3)
        a, b, c = graph.path_order()
        _answer(graph, a, "partial", "wrong_model")
        _answer(graph, b, "partial", "missing_prerequisite")
        _answer(graph, c, "partial", "right_idea_wrong_altitude")
        assert "recurring_shortfall" not in _templates(graph)

    @pytest.mark.parametrize("kind", ["none", "no_attempt"])
    def test_non_misconception_kinds_never_form_a_pattern(self, kind):
        # `no_attempt` is a fact about engagement, not about understanding.
        graph = _graph([("flow", "a1")] * 3)
        for node_id in graph.path_order():
            _answer(graph, node_id, "partial", kind)
        assert "recurring_shortfall" not in _templates(graph)

    def test_pre_b5_attempts_without_a_gap_kind_contribute_nothing(self):
        graph = _graph([("flow", "a1")] * 3)
        for node_id in graph.path_order():
            graph.nodes[node_id].attempts.append({
                "answer": "old", "classification": "partial", "rationale": "r",
                "at": "2026-08-01T00:00:00+00:00",
            })
        assert "recurring_shortfall" not in _templates(graph)

    def test_an_understood_answer_is_not_a_shortfall(self):
        graph = _graph([("flow", "a1")] * 3)
        for node_id in graph.path_order():
            _answer(graph, node_id, "understood", "none")
        assert "recurring_shortfall" not in _templates(graph)


# ── P3 · area evidence ────────────────────────────────────────────────────────


class TestAreaEvidence:
    def test_fires_when_no_assessed_unit_in_the_area_was_demonstrated(self):
        graph = _graph([("flow", "a1")] * 2)
        for node_id in graph.path_order():
            _answer(graph, node_id, "partial")
        card = _templates(graph)["area_evidence"]
        assert card["detail"]["assessed"] == 2
        assert card["detail"]["demonstrated"] == 0
        assert card["detail"]["area_title"] == "Request lifecycle"

    def test_one_assessed_unit_is_not_an_area_pattern(self):
        graph = _graph([("flow", "a1")] * 2)
        _answer(graph, graph.path_order()[0], "partial")
        assert "area_evidence" not in _templates(graph)

    def test_a_single_demonstrated_unit_stops_it(self):
        graph = _graph([("flow", "a1")] * 2)
        a, b = graph.path_order()
        _answer(graph, a, "partial")
        _answer(graph, b, "understood")
        assert "area_evidence" not in _templates(graph)

    def test_a_recovered_unit_counts_as_demonstrated(self):
        graph = _graph([("flow", "a1")] * 2)
        a, b = graph.path_order()
        _answer(graph, a, "partial")
        _answer(graph, b, "confused")
        _answer(graph, b, "understood")          # recovered
        assert "area_evidence" not in _templates(graph)


# ── waived and continued units ────────────────────────────────────────────────


class TestDispositionIsNotOverridden:
    def _waived_area(self) -> LearningGraph:
        graph = _graph([("flow", "a1")] * 2)
        a, b = graph.path_order()
        _answer(graph, a, "partial")
        _answer(graph, b, "partial")
        graph.nodes[b].gap_state.gaps.append(Gap.create("wrong_model", "a false claim"))
        graph.waive_remaining(b)
        return graph

    def test_a_waived_unit_still_counts_as_not_demonstrated(self):
        # The approved rule: understanding truth survives the decision. "0 of 2
        # demonstrated" stays true when one of them was waived.
        graph = self._waived_area()
        card = _templates(graph)["area_evidence"]
        assert card["detail"]["assessed"] == 2
        assert card["detail"]["demonstrated"] == 0

    def test_the_pattern_reports_how_many_were_set_aside(self):
        # So the wording can stay descriptive instead of implying an obligation
        # the learner already declined.
        graph = self._waived_area()
        assert _templates(graph)["area_evidence"]["detail"]["set_aside"] == 1

    def test_waiving_does_not_change_the_m3a1_classification(self):
        graph = self._waived_area()
        waived = graph.path_order()[1]
        assert understanding.classify(graph.nodes[waived]) == understanding.UNRESOLVED
        assert understanding.is_set_aside(graph.nodes[waived]) is True
        assert understanding.is_needs_work(graph.nodes[waived]) is False


# ── evidence hygiene ──────────────────────────────────────────────────────────


class TestEvidenceRules:
    def test_off_topic_answers_cannot_manufacture_a_pattern(self):
        graph = _graph([("flow", "a1")] * 3)
        for node_id in graph.path_order():
            _answer(graph, node_id, "off-topic", "wrong_model")
        assert _templates(graph) == {}

    def test_grading_failures_cannot_manufacture_a_pattern(self):
        graph = _graph([("flow", "a1")] * 3)
        for node_id in graph.path_order():
            _answer(graph, node_id, "partial", "wrong_model", graded=False)
        assert _templates(graph) == {}

    def test_verification_answers_are_not_assessment_evidence(self):
        graph = _graph([("flow", "a1")] * 3)
        for node_id in graph.path_order():
            _answer(graph, node_id, "partial", "wrong_model",
                    kind=history.VERIFICATION)
        assert _templates(graph) == {}

    def test_unknown_intervention_history_distorts_nothing(self):
        # Pre-M2 attempts carry no response record. No template reads one, so an
        # old session must behave exactly as an instrumented one with the same
        # verdicts.
        graph = _graph([("flow", "a1")] * 2)
        a, b = graph.path_order()
        for node_id, count in ((a, 2), (b, 1)):
            for _ in range(count):
                graph.nodes[node_id].attempts.append({
                    "answer": "old", "classification": "partial",
                    "gap_kind": "wrong_model", "rationale": "r",
                    "at": "2026-08-01T00:00:00+00:00",
                })
        card = _templates(graph)["recurring_shortfall"]
        assert card["detail"]["attempts"] == 3
        for ref in card["evidence"]:
            assert history.is_instrumented(
                graph.nodes[ref["node_id"]].attempts[ref["attempt_index"]]) is False

    def test_an_empty_session_produces_nothing(self):
        assert patterns.detect(_graph([("flow", "a1")] * 3)) == []

    def test_a_handful_of_answers_produces_nothing(self):
        # The common case, and the intended outcome.
        graph = _graph([("flow", "a1"), ("component", "a2")])
        _answer(graph, graph.path_order()[0], "understood")
        assert patterns.detect(graph) == []

    def test_every_rendered_pattern_resolves_to_real_attempts(self):
        graph = _graph([("flow", "a1")] * 2 + [("component", "a1")] * 2)
        ids = graph.path_order()
        for node_id in ids[:2]:
            _answer(graph, node_id, "partial", "wrong_model")
            _answer(graph, node_id, "understood")
        for node_id in ids[2:]:
            _answer(graph, node_id, "understood")

        found = patterns.detect(graph)
        assert found, "fixture must produce at least one pattern"
        for card in found:
            assert card["evidence"], f"{card['template']} rendered with no evidence"
            for ref in card["evidence"]:
                node = graph.nodes[ref["node_id"]]
                assert 0 <= ref["attempt_index"] < len(node.attempts)

    def test_remedial_and_optional_units_are_out_of_scope(self):
        # Same population as the profile and both progress measures.
        graph = _graph([("flow", "a1")] * 2)
        warm_up = LearningNode(
            title="warm-up", code_anchor=CodeAnchor("w.py", 1, 2),
            lesson_brief={"priority": "required", "origin": "system_remediation",
                          "kind": "flow", "area_id": "a1"})
        graph.insert_before(graph.path_order()[1], warm_up, kind="prerequisite")
        for _ in range(3):
            _answer(graph, warm_up.id, "partial", "wrong_model")
        assert _templates(graph) == {}


# ── the M3a.1 contracts are untouched ─────────────────────────────────────────


class TestNoRegression:
    def test_patterns_ride_on_the_profile_without_changing_it(self):
        graph = _graph([("flow", "a1")] * 2)
        for node_id in graph.path_order():
            _answer(graph, node_id, "partial", "wrong_model")
        payload = graph.to_dict()["understanding"]

        assert "patterns" in payload
        assert payload["totals"][understanding.UNRESOLVED] == 2
        assert len(payload["needs_work"]) == 2

    def test_progress_semantics_are_untouched(self):
        graph = _graph([("flow", "a1")] * 2)
        a, b = graph.path_order()
        _answer(graph, a, "understood")
        _answer(graph, b, "partial")
        before_goal = progress.goal_readiness(graph)
        before_journey = progress.journey_progress(graph)

        patterns.detect(graph)          # pure: reading must change nothing

        assert progress.goal_readiness(graph) == before_goal == 0.75
        assert progress.journey_progress(graph) == before_journey
