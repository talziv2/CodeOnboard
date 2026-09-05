# Readiness to implement — derived, never stored.
#
# The gate on the contribution stage is `progress.ready_to_implement`, and it is
# deliberately NOT a new fact: it is `goal_readiness == 1.0` restated as a
# predicate with its blockers named, over the same `core_nodes` set. Composing
# the two existing definitions rather than adding a third is what makes it
# inherit §5.3 for free —
#
#     readiness may fall ONLY when evidence about the learner changes.
#
# `TestThePlanCannotOpenTheGate` is the class that pins that, and it is the
# reason this file exists rather than three assertions inside test_progress.py.

import pytest

from backend.learning import progress, scope
from backend.learning.adaptation import prune_ahead
from backend.learning.gaps import Gap
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode


def _graph(units: list[tuple[str, str]]) -> LearningGraph:
    """units: (priority, understanding_state), chained by sequence edges."""
    graph = LearningGraph(repo_url="r", goal={"goal_type": "contribute_code"})
    previous = None
    for i, (priority, state) in enumerate(units):
        node = graph.add_node(LearningNode(
            title=f"n{i}",
            code_anchor=CodeAnchor(file="a.py", line_start=1, line_end=2),
            lesson_brief={"area_id": "a1", "priority": priority, "objective": f"claim {i}"},
        ))
        node.understanding_state = state
        if state == "understood":
            # EVIDENCE, not just a state flag. `is_demonstrated` reads the
            # Understanding Profile, which needs a real assessment behind it.
            node.attempts.append({
                "kind": "assessment", "answer": "a", "classification": "understood",
                "rationale": "r", "at": "2026-01-01T00:00:00Z",
            })
        if previous:
            graph.add_edge(previous, node.id, kind="sequence")
        previous = node.id
    graph.set_current(next(iter(graph.nodes)))
    return graph


def _block_with_gap(graph: LearningGraph, node_id: str) -> Gap:
    node = graph.nodes[node_id]
    node.understanding_state = "failed"
    node.attempts.append({
        "kind": "assessment", "answer": "a", "classification": "confused",
        "gap_kind": "wrong_model", "rationale": "r", "at": "2026-01-01T00:00:00Z",
    })
    # `Gap.create` is the only way application code mints one — it refuses the
    # kinds that must never become a gap, which a bare constructor would not.
    gap = Gap.create("wrong_model", "the jar picks one silently",
                     objective_part="conflict contract")
    node.gap_state.gaps.append(gap)
    return gap


class TestTheGate:
    def test_all_required_demonstrated_is_ready(self):
        graph = _graph([("required", "understood"), ("required", "understood")])
        ready = progress.ready_to_implement(graph)
        assert ready["ready"] is True
        assert ready["required"] == 2
        assert ready["demonstrated"] == 2
        assert ready["blockers"] == []

    def test_one_undemonstrated_required_unit_closes_it(self):
        graph = _graph([("required", "understood"), ("required", "not_started")])
        ready = progress.ready_to_implement(graph)
        assert ready["ready"] is False
        assert ready["demonstrated"] == 1
        assert [b["reason"] for b in ready["blockers"]] == ["unverified"]

    def test_recommended_and_optional_units_never_gate(self):
        """The gate is about what the CHANGE requires, which is the required set.
        Depth the learner was never promised cannot hold them back."""
        graph = _graph([
            ("required", "understood"),
            ("recommended", "not_started"),
            ("optional", "not_started"),
        ])
        assert progress.ready_to_implement(graph)["ready"] is True

    def test_an_open_blocking_gap_names_itself(self):
        """`gap` outranks `unverified`: when a misconception has been named,
        naming it is more useful than reporting that nothing was shown."""
        graph = _graph([("required", "understood"), ("required", "understood")])
        second = list(graph.nodes)[1]
        gap = _block_with_gap(graph, second)
        ready = progress.ready_to_implement(graph)
        assert ready["ready"] is False
        blocker = next(b for b in ready["blockers"] if b["node_id"] == second)
        assert blocker["reason"] == "gap"
        assert blocker["gaps"][0]["claim"] == gap.claim

    def test_a_graph_with_no_required_units_is_not_ready(self):
        """Reporting ready on an empty denominator would open the stage on the
        strength of nothing at all."""
        graph = _graph([("optional", "understood")])
        assert progress.ready_to_implement(graph)["ready"] is False

    def test_the_gate_agrees_with_goal_readiness(self):
        """One definition, two shapes. If these could disagree, the header and
        the gate would be two authorities on the same question."""
        graph = _graph([("required", "understood"), ("required", "not_started")])
        assert progress.goal_readiness(graph) < 1.0
        assert progress.ready_to_implement(graph)["ready"] is False
        graph.nodes[list(graph.nodes)[1]].understanding_state = "understood"
        graph.nodes[list(graph.nodes)[1]].attempts.append({
            "kind": "assessment", "answer": "a", "classification": "understood",
            "rationale": "r", "at": "2026-01-01T00:00:00Z",
        })
        assert progress.goal_readiness(graph) == 1.0
        assert progress.ready_to_implement(graph)["ready"] is True

    def test_it_rides_on_the_progress_summary(self):
        """Computed for every session, not only contribution ones: a payload key
        that appears and disappears by goal type is one every consumer guards."""
        graph = _graph([("required", "understood")])
        assert "ready_to_implement" in progress.summary(graph)


class TestWaivingDoesNotBuyReadiness:
    def test_a_waived_gap_still_blocks(self):
        """A waived gap is unverified forever, so its node is never demonstrated.
        What waiving buys is that the system stops ASKING — which is a different
        thing from the learner having shown they understand it."""
        graph = _graph([("required", "understood")])
        node_id = list(graph.nodes)[0]
        _block_with_gap(graph, node_id)
        graph.waive_remaining(node_id)
        assert progress.ready_to_implement(graph)["ready"] is False

    def test_marking_understood_does_not_open_the_gate(self):
        """A learner decision is never evidence of understanding (D8, M0)."""
        graph = _graph([("required", "not_started")])
        graph.override(list(graph.nodes)[0], "mark_understood")
        assert progress.ready_to_implement(graph)["ready"] is False

    def test_skipping_does_not_open_the_gate(self):
        graph = _graph([("required", "not_started")])
        graph.override(list(graph.nodes)[0], "skip")
        assert progress.ready_to_implement(graph)["ready"] is False

    def test_journey_completion_does_not_imply_readiness(self):
        """Two different measures, and neither gates the other. A learner can
        finish the walk by settling every stop without demonstrating any of it."""
        graph = _graph([("required", "not_started"), ("required", "not_started")])
        for node_id in list(graph.nodes):
            graph.override(node_id, "skip")
            graph.nodes[node_id].user_override = "continue"
        assert graph.is_complete() is True
        assert progress.ready_to_implement(graph)["ready"] is False


class TestThePlanCannotOpenTheGate:
    """Readiness may move only when EVIDENCE moves — never when the plan does.

    The gate composes `core_nodes` and `is_demonstrated`, both of which already
    obey §5.3, so these are regression tests on the composition rather than on a
    new rule. They matter because a gate that opened when the system pruned the
    journey would let a learner into the implementation stage on the strength of
    the system having decided to ask less of them.
    """

    def test_shortening_the_scope_does_not_open_it(self):
        graph = _graph([("required", "not_started"), ("recommended", "not_started")])
        before = progress.ready_to_implement(graph)
        scope.shorten(graph)
        after = progress.ready_to_implement(graph)
        assert after["ready"] == before["ready"] is False
        assert after["required"] == before["required"]

    def test_prune_ahead_does_not_open_it(self):
        graph = _graph([
            ("required", "understood"), ("recommended", "not_started"),
            ("recommended", "not_started"),
        ])
        before = progress.ready_to_implement(graph)
        prune_ahead(graph)
        after = progress.ready_to_implement(graph)
        assert after["required"] == before["required"]
        assert after["demonstrated"] == before["demonstrated"]

    def test_a_spliced_warm_up_does_not_close_it(self):
        """The Mutator marks its warm-up `required` so scope control cannot take
        it away. If it entered this denominator, the gate would slam shut the
        moment the system decided to help — the defect `progress.py` records."""
        graph = _graph([("required", "understood")])
        anchor = list(graph.nodes)[0]
        assert progress.ready_to_implement(graph)["ready"] is True
        warm_up = LearningNode(
            title="warm-up",
            code_anchor=CodeAnchor(file="a.py", line_start=1, line_end=2),
            lesson_brief={"priority": "required", "origin": "system_remediation"},
        )
        graph.insert_before(anchor, warm_up)
        assert progress.ready_to_implement(graph)["ready"] is True
