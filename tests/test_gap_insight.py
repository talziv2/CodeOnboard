# Gap-derived observations — M3b.
#
# EMPIRICAL STATUS: these are CONTRACT tests against fixtures. The stored corpus
# holds 2 gaps and 0 verification attempts, so the states below do not yet exist
# in real data — building them here is how the semantics get exercised before
# the manual E2E round produces the first real volume. Nothing in this file
# claims the thresholds are right for real learners; it claims the definitions
# behave as specified.
#
# Every template is checked at its threshold AND one observation below it, over
# the full open/verified/waived lifecycle, with evidence that resolves.

import pytest

from backend.learning import gap_insight, history
from backend.learning.gaps import Gap
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode


def _graph(count: int = 3) -> LearningGraph:
    graph = LearningGraph(repo_url="r", goal={})
    previous = None
    for i in range(count):
        node = graph.add_node(LearningNode(
            title=f"n{i}", code_anchor=CodeAnchor("a.py", 1, 2),
            lesson_brief={"priority": "required", "objective": f"claim {i}",
                          "area_id": "a1", "kind": "flow"},
        ))
        if previous:
            graph.add_edge(previous.id, node.id, kind="sequence")
        previous = node
    graph.set_current(graph.path_order()[0])
    return graph


def _answer(graph, node_id, classification="partial", **over):
    graph.record_attempt(graph and node_id, "an answer", classification, "because",
                         gap_kind="wrong_model", **over)
    graph.mark_understanding(
        node_id, {"understood": "understood", "partial": "partial",
                  "confused": "failed"}[classification])
    graph.record_response(node_id, history.new_response("none"))


def _gap(graph, node_id, *, kind="wrong_model", status="open",
         attempts=0, claim="a false claim") -> Gap:
    """One persisted gap, in a given lifecycle position."""
    node = graph.nodes[node_id]
    if not node.attempts:
        _answer(graph, node_id)
    gap = Gap.create(kind, claim, origin_attempt=len(node.attempts) - 1)
    gap.verification_attempts = attempts
    if status == "verified":
        gap.mark_verified(len(node.attempts) - 1)
    elif status == "waived":
        gap.waive()
    node.gap_state.gaps.append(gap)
    return gap


def _cards(graph) -> dict[str, dict]:
    return {c["template"]: c for c in gap_insight.detect(graph)}


# ── backward compatibility: no gap data at all ────────────────────────────────


class TestNoGapData:
    def test_a_graph_with_no_gaps_produces_nothing(self):
        # Every session written before the gap model, and every flag-off
        # session. By far the commonest case today.
        graph = _graph()
        for node_id in graph.path_order():
            _answer(graph, node_id)
        assert gap_insight.detect(graph) == []

    def test_an_empty_graph_does_not_crash(self):
        assert gap_insight.detect(LearningGraph(repo_url="r", goal={})) == []

    def test_the_profile_carries_an_empty_list_rather_than_omitting_it(self):
        # A consumer can always read the key; absence would be indistinguishable
        # from "no gap model".
        graph = _graph()
        assert graph.to_dict()["understanding"]["gap_patterns"] == []


# ── G1 · gap outcomes ─────────────────────────────────────────────────────────


class TestGapOutcomes:
    def test_fires_at_three_gaps(self):
        graph = _graph()
        ids = graph.path_order()
        _gap(graph, ids[0], status="verified")
        _gap(graph, ids[1], status="waived")
        _gap(graph, ids[2], status="open")

        card = _cards(graph)["gap_outcomes"]
        assert card["detail"] == {"total": 3, "verified": 1, "waived": 1, "open": 1}

    def test_two_gaps_are_below_threshold(self):
        graph = _graph()
        ids = graph.path_order()
        _gap(graph, ids[0])
        _gap(graph, ids[1])
        assert "gap_outcomes" not in _cards(graph)

    def test_waived_is_reported_separately_from_verified(self):
        """A waiver is a decision, not evidence. Folding the two into
        "resolved" would let choosing to stop read as mastery."""
        graph = _graph()
        for node_id in graph.path_order():
            _gap(graph, node_id, status="waived")
        card = _cards(graph)["gap_outcomes"]
        assert card["detail"]["waived"] == 3
        assert card["detail"]["verified"] == 0

    def test_evidence_resolves_to_the_answer_that_opened_each_gap(self):
        graph = _graph()
        for node_id in graph.path_order():
            _gap(graph, node_id)
        for ref in _cards(graph)["gap_outcomes"]["evidence"]:
            node = graph.nodes[ref["node_id"]]
            assert 0 <= ref["attempt_index"] < len(node.attempts)
            assert any(g.id == ref["gap_id"] for g in node.gaps)


# ── G2 · blocking backlog ─────────────────────────────────────────────────────


class TestBlockingBacklog:
    def test_fires_at_two_open_blocking_gaps_across_two_objectives(self):
        graph = _graph()
        ids = graph.path_order()
        _gap(graph, ids[0], kind="wrong_model")
        _gap(graph, ids[1], kind="missing_prerequisite")

        card = _cards(graph)["blocking_backlog"]
        assert card["detail"]["gaps"] == 2
        assert card["detail"]["nodes"] == 2

    def test_two_gaps_on_ONE_objective_is_not_a_backlog(self):
        # One unit still being worked through; the profile already says so.
        graph = _graph()
        node_id = graph.path_order()[0]
        _gap(graph, node_id)
        _gap(graph, node_id, claim="another false claim")
        assert "blocking_backlog" not in _cards(graph)

    def test_non_blocking_gaps_never_form_a_backlog(self):
        # `right_idea_wrong_altitude` is recorded and does not block.
        graph = _graph()
        ids = graph.path_order()
        _gap(graph, ids[0], kind="right_idea_wrong_altitude")
        _gap(graph, ids[1], kind="right_idea_wrong_altitude")
        assert "blocking_backlog" not in _cards(graph)

    @pytest.mark.parametrize("status", ["verified", "waived"])
    def test_settled_gaps_are_not_a_backlog(self, status):
        graph = _graph()
        ids = graph.path_order()
        _gap(graph, ids[0], status=status)
        _gap(graph, ids[1], status=status)
        assert "blocking_backlog" not in _cards(graph)

    def test_an_exhausted_gap_is_counted_and_named(self):
        # The cap means the system stopped proposing. Silence there would read
        # as "still being worked on".
        graph = _graph()
        ids = graph.path_order()
        _gap(graph, ids[0], attempts=2)
        _gap(graph, ids[1])
        assert _cards(graph)["blocking_backlog"]["detail"]["exhausted"] == 1


# ── G3 · verification outcomes ────────────────────────────────────────────────


class TestVerificationOutcomes:
    def test_fires_at_three_tested_gaps(self):
        graph = _graph()
        ids = graph.path_order()
        _gap(graph, ids[0], status="verified")
        _gap(graph, ids[1], status="verified")
        _gap(graph, ids[2], attempts=1)

        card = _cards(graph)["verification_outcomes"]
        assert card["detail"]["tested"] == 3
        assert card["detail"]["closed"] == 2

    def test_untested_gaps_are_not_verification_failures(self):
        """THE correctness case: a gap nobody asked about has not been failed."""
        graph = _graph()
        for node_id in graph.path_order():
            _gap(graph, node_id)                      # open, never tested
        assert "verification_outcomes" not in _cards(graph)

    def test_two_tested_gaps_are_below_threshold(self):
        graph = _graph()
        ids = graph.path_order()
        _gap(graph, ids[0], status="verified")
        _gap(graph, ids[1], attempts=1)
        assert "verification_outcomes" not in _cards(graph)

    def test_a_retried_gap_is_counted(self):
        graph = _graph()
        ids = graph.path_order()
        _gap(graph, ids[0], attempts=2)
        _gap(graph, ids[1], attempts=1)
        _gap(graph, ids[2], status="verified")
        assert _cards(graph)["verification_outcomes"]["detail"]["retried"] == 1

    def test_assessment_answers_do_not_enter_the_verification_population(self):
        # The population is gap objects; assessment answers cannot inflate it.
        graph = _graph()
        for node_id in graph.path_order():
            _answer(graph, node_id)
            _answer(graph, node_id, "understood")
        assert "verification_outcomes" not in _cards(graph)

    def test_verification_attempts_are_not_pooled_with_assessments(self):
        # An answer recorded as a verification must not be read as an
        # assessment by anything here — asserted through `history`, which is the
        # single owner of that split.
        graph = _graph(1)
        node_id = graph.path_order()[0]
        _answer(graph, node_id)
        graph.record_attempt(node_id, "v", "understood", "r",
                             kind=history.VERIFICATION)
        assessments = history.assessments(graph.nodes[node_id].attempts)
        assert len(assessments) == 1


# ── G4 · remediation closure ──────────────────────────────────────────────────


class TestRemediationClosure:
    def _warm_up(self, graph, anchor_id, gap, closed):
        node = LearningNode(
            title="warm-up", code_anchor=CodeAnchor("w.py", 1, 2),
            lesson_brief={"priority": "required", "origin": "system_remediation",
                          "remediates": [gap.id]})
        graph.insert_before(anchor_id, node, kind="prerequisite")
        if closed:
            gap.mark_verified(0)
        return node

    def test_fires_at_three_warm_ups(self):
        graph = _graph()
        ids = graph.path_order()
        for i, node_id in enumerate(ids):
            gap = _gap(graph, node_id)
            self._warm_up(graph, node_id, gap, closed=i < 2)

        card = _cards(graph)["remediation_closure"]
        assert card["detail"] == {"warmups": 3, "closed": 2}

    def test_two_warm_ups_are_below_threshold(self):
        graph = _graph()
        ids = graph.path_order()
        for node_id in ids[:2]:
            gap = _gap(graph, node_id)
            self._warm_up(graph, node_id, gap, closed=True)
        assert "remediation_closure" not in _cards(graph)

    def test_a_warm_up_without_a_remediates_link_is_not_counted(self):
        # Every warm-up in the stored corpus is in this shape — generated before
        # M5 recorded which gap it was built for.
        graph = _graph()
        for node_id in graph.path_order():
            _gap(graph, node_id)
            node = LearningNode(
                title="warm-up", code_anchor=CodeAnchor("w.py", 1, 2),
                lesson_brief={"priority": "required", "origin": "system_remediation"})
            graph.insert_before(node_id, node, kind="prerequisite")
        assert "remediation_closure" not in _cards(graph)

    def test_a_waived_target_does_not_count_as_closed(self):
        """Only verification closes a gap. A waiver stops the asking."""
        graph = _graph()
        for node_id in graph.path_order():
            gap = _gap(graph, node_id)
            self._warm_up(graph, node_id, gap, closed=False)
            gap.waive()
        assert _cards(graph)["remediation_closure"]["detail"]["closed"] == 0


# ── scope and shape ───────────────────────────────────────────────────────────


class TestScopeAndShape:
    def test_gaps_on_remedial_warm_ups_are_out_of_the_journey_population(self):
        graph = _graph(2)
        warm_up = LearningNode(
            title="warm-up", code_anchor=CodeAnchor("w.py", 1, 2),
            lesson_brief={"priority": "required", "origin": "system_remediation"})
        graph.insert_before(graph.path_order()[1], warm_up, kind="prerequisite")
        warm_up.attempts.append({"answer": "a", "classification": "partial",
                                 "rationale": "r", "at": "now"})
        for i in range(3):
            warm_up.gap_state.gaps.append(Gap.create("wrong_model", f"claim {i}"))
        assert "gap_outcomes" not in _cards(graph)

    def test_every_card_carries_resolvable_evidence(self):
        graph = _graph()
        ids = graph.path_order()
        _gap(graph, ids[0], status="verified")
        _gap(graph, ids[1], attempts=1)
        _gap(graph, ids[2])
        cards = gap_insight.detect(graph)
        assert cards
        for card in cards:
            assert card["evidence"], f"{card['template']} has no evidence"
            for ref in card["evidence"]:
                node = graph.nodes[ref["node_id"]]
                assert 0 <= ref["attempt_index"] < len(node.attempts)

    def test_detail_carries_numbers_only(self):
        # Wording lives in strings.ts; a sentence here would put the part that
        # can over-claim outside the file where copy is reviewed.
        graph = _graph()
        for node_id in graph.path_order():
            _gap(graph, node_id)
        for card in gap_insight.detect(graph):
            for value in card["detail"].values():
                assert isinstance(value, (int, float)), card

    def test_the_foundational_flag_is_never_read(self):
        """`Gap.foundational` is observed, not decisive (gap-model M1).

        Asserted structurally so an insight cannot start quietly depending on a
        model's aside instead of on `is_blocking`, which is policy.
        """
        import inspect

        source = inspect.getsource(gap_insight)
        code = "\n".join(
            line for line in source.splitlines() if not line.strip().startswith("#")
        )
        assert ".foundational" not in code
