# The Understanding Profile — two dimensions, four states (M3a.1).
#
# The properties these tests exist to hold, all of them about NOT over-claiming:
#
#   1. A recovered node NEVER appears as work outstanding. `weak_spot` is
#      sticky, so before this the UI captioned mastered units "marked weak"
#      permanently.
#   2. Unresolved understanding survives a decision to stop remediating. Waiving
#      is a choice about effort, not evidence about the learner.
#   3. Absence of evidence is its own state, and is neither a strength nor a
#      weakness.
#   4. Nothing here re-derives understanding: `understanding_of` owns it.

import pytest

from backend.learning import history, progress, understanding
from backend.learning.gaps import Gap
from backend.learning.graph import (
    CodeAnchor, LearningGraph, LearningNode, understanding_of,
)


def _graph(count: int = 1) -> LearningGraph:
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


def _answer(graph, node_id, classification, **over):
    """One graded assessment, instrumented as M2 would write it."""
    graph.record_attempt(node_id, "an answer", classification, "because", **over)
    mapping = {"understood": "understood", "partial": "partial", "confused": "failed"}
    if classification in mapping:
        graph.mark_understanding(node_id, mapping[classification])
    graph.record_response(node_id, history.new_response("none"))


def _blocking() -> Gap:
    return Gap.create("wrong_model", "a false claim")


# ── the four states ───────────────────────────────────────────────────────────


class TestClassification:
    def test_understood_without_ever_falling_short_is_a_strength(self):
        graph = _graph()
        node_id = graph.path_order()[0]
        _answer(graph, node_id, "understood")
        assert understanding.classify(graph.nodes[node_id]) == understanding.STRENGTH

    @pytest.mark.parametrize("first", ["partial", "confused"])
    def test_falling_short_then_understanding_is_recovered(self, first):
        # BOTH routes count. `weak_spot` is set only on `confused`, so a
        # partial -> understood recovery is invisible to it — which is why the
        # discriminator is the attempt history.
        graph = _graph()
        node_id = graph.path_order()[0]
        _answer(graph, node_id, first)
        _answer(graph, node_id, "understood")
        assert understanding.classify(graph.nodes[node_id]) == understanding.RECOVERED

    def test_a_recovered_node_is_never_needs_work(self):
        """The defect this milestone exists to fix."""
        graph = _graph()
        node_id = graph.path_order()[0]
        _answer(graph, node_id, "confused")
        _answer(graph, node_id, "understood")
        node = graph.nodes[node_id]

        assert understanding.is_needs_work(node) is False
        assert understanding.is_set_aside(node) is False
        assert node.weak_spot is True          # history is preserved…
        assert understanding.classify(node) == understanding.RECOVERED   # …not presented as current

    @pytest.mark.parametrize("verdict", ["partial", "confused"])
    def test_an_assessed_node_that_fell_short_is_unresolved(self, verdict):
        graph = _graph()
        node_id = graph.path_order()[0]
        _answer(graph, node_id, verdict)
        node = graph.nodes[node_id]
        assert understanding.classify(node) == understanding.UNRESOLVED
        assert understanding.is_needs_work(node) is True

    def test_an_unassessed_node_is_insufficient_evidence(self):
        graph = _graph()
        node = graph.nodes[graph.path_order()[0]]
        assert understanding.classify(node) == understanding.INSUFFICIENT
        assert understanding.is_needs_work(node) is False

    def test_a_visited_but_unanswered_node_is_still_insufficient(self):
        graph = _graph()
        node = graph.nodes[graph.path_order()[0]]
        node.visited = True
        assert understanding.classify(node) == understanding.INSUFFICIENT

    def test_off_topic_only_is_insufficient_not_a_weakness(self):
        graph = _graph()
        node_id = graph.path_order()[0]
        _answer(graph, node_id, "off-topic")
        assert understanding.classify(graph.nodes[node_id]) == understanding.INSUFFICIENT

    def test_ungraded_only_is_insufficient_not_a_weakness(self):
        # A grading failure is our error. Presenting it as the learner's
        # difficulty attributes an outage to them.
        graph = _graph()
        node_id = graph.path_order()[0]
        _answer(graph, node_id, "partial", graded=False)
        assert understanding.classify(graph.nodes[node_id]) == understanding.INSUFFICIENT

    def test_a_verification_answer_is_not_assessment_evidence(self):
        graph = _graph()
        node_id = graph.path_order()[0]
        _answer(graph, node_id, "understood", kind=history.VERIFICATION)
        assert understanding.classify(graph.nodes[node_id]) == understanding.INSUFFICIENT


# ── the second dimension ──────────────────────────────────────────────────────


class TestDisposition:
    def test_a_fresh_node_is_active(self):
        graph = _graph()
        assert understanding.disposition_of(
            graph.nodes[graph.path_order()[0]]) == understanding.ACTIVE

    def test_continue_does_not_change_what_was_demonstrated(self):
        graph = _graph()
        node_id = graph.path_order()[0]
        node = graph.nodes[node_id]
        node.gap_state.gaps.append(_blocking())
        _answer(graph, node_id, "partial")
        before = understanding.classify(node)

        graph.continue_past(node_id)

        assert understanding.classify(node) == before == understanding.UNRESOLVED
        assert understanding.disposition_of(node) == understanding.CONTINUED

    def test_a_continued_node_leaves_needs_work_but_stays_unresolved(self):
        # The product requirement: preserve the truth, stop nagging.
        graph = _graph()
        node_id = graph.path_order()[0]
        node = graph.nodes[node_id]
        node.gap_state.gaps.append(_blocking())
        _answer(graph, node_id, "partial")
        graph.continue_past(node_id)

        assert understanding.is_needs_work(node) is False
        assert understanding.is_set_aside(node) is True
        assert understanding.classify(node) == understanding.UNRESOLVED

    def test_waiving_does_not_change_what_was_demonstrated(self):
        graph = _graph()
        node_id = graph.path_order()[0]
        node = graph.nodes[node_id]
        node.gap_state.gaps.append(_blocking())
        _answer(graph, node_id, "partial")

        graph.waive_remaining(node_id)

        assert understanding.classify(node) == understanding.UNRESOLVED
        assert understanding.disposition_of(node) == understanding.WAIVED
        assert understanding.is_set_aside(node) is True

    def test_a_new_attempt_withdraws_continue_and_returns_it_to_needs_work(self):
        # M8 withdraws `continue` on a new answer; the disposition must follow,
        # or the learner would be working on something the UI calls set aside.
        graph = _graph()
        node_id = graph.path_order()[0]
        node = graph.nodes[node_id]
        node.gap_state.gaps.append(_blocking())
        _answer(graph, node_id, "partial")
        graph.continue_past(node_id)
        assert understanding.is_set_aside(node) is True

        _answer(graph, node_id, "partial")

        assert understanding.disposition_of(node) == understanding.ACTIVE
        assert understanding.is_needs_work(node) is True

    def test_the_two_dimensions_may_legitimately_disagree(self):
        """The case that decided model B over a single fifth state.

        A waived gap can later be verified; the node then genuinely IS
        demonstrated while the record still says the learner had chosen to stop.
        One variable would have to report one of those and be wrong about the other.
        """
        graph = _graph()
        node_id = graph.path_order()[0]
        node = graph.nodes[node_id]
        gap = _blocking()
        node.gap_state.gaps.append(gap)
        _answer(graph, node_id, "understood")
        graph.waive_remaining(node_id)
        gap.mark_verified(0)

        assert understanding_of(node) == "understood"
        assert understanding.classify(node) == understanding.STRENGTH
        assert understanding.disposition_of(node) == understanding.WAIVED
        assert understanding.is_set_aside(node) is False

    def test_skip_is_a_disposition_not_a_weakness(self):
        graph = _graph()
        node_id = graph.path_order()[0]
        graph.override(node_id, "skip")
        node = graph.nodes[node_id]
        assert understanding.classify(node) == understanding.INSUFFICIENT
        assert understanding.disposition_of(node) == understanding.SKIPPED
        assert understanding.is_needs_work(node) is False

    def test_mark_weak_leaves_the_node_actionable(self):
        # Agreeing you have not got it is not a decision to stop.
        graph = _graph()
        node_id = graph.path_order()[0]
        _answer(graph, node_id, "partial")
        graph.override(node_id, "mark_weak")
        node = graph.nodes[node_id]
        assert understanding.disposition_of(node) == understanding.ACTIVE
        assert understanding.is_needs_work(node) is True


# ── agreement with the single owner ───────────────────────────────────────────


class TestAgreesWithUnderstandingOf:
    def test_an_open_blocking_gap_makes_a_demonstrated_node_unresolved(self):
        graph = _graph()
        node_id = graph.path_order()[0]
        node = graph.nodes[node_id]
        _answer(graph, node_id, "understood")
        assert understanding.classify(node) == understanding.STRENGTH

        node.gap_state.gaps.append(_blocking())

        assert understanding_of(node) == "partial"
        assert understanding.classify(node) == understanding.UNRESOLVED

    def test_the_profile_never_disagrees_with_the_derivation(self):
        graph = _graph(3)
        ids = graph.path_order()
        _answer(graph, ids[0], "understood")
        _answer(graph, ids[1], "partial")
        graph.nodes[ids[1]].gap_state.gaps.append(_blocking())
        payload = graph.to_dict()

        for row in payload["understanding"]["nodes"]:
            node = graph.nodes[row["node_id"]]
            assert row["state"] == understanding_of(node)
            wire = next(n for n in payload["nodes"] if n["id"] == row["node_id"])
            assert wire["understanding_state"] == understanding_of(node)

    def test_the_discrepancy_flag_fires_when_m7_holds_a_node_back(self):
        # Without gaps on the wire (M9) the UI cannot say WHY; it must still be
        # able to say THAT, rather than showing a contradiction unexplained.
        graph = _graph()
        node_id = graph.path_order()[0]
        _answer(graph, node_id, "understood")
        graph.nodes[node_id].gap_state.gaps.append(_blocking())

        summary = understanding.node_summary(graph.nodes[node_id])
        assert summary["state_matches_latest_answer"] is False


# ── the profile ───────────────────────────────────────────────────────────────


class TestProfile:
    def test_buckets_are_disjoint(self):
        graph = _graph(4)
        ids = graph.path_order()
        _answer(graph, ids[0], "understood")
        _answer(graph, ids[1], "confused")
        _answer(graph, ids[1], "understood")
        _answer(graph, ids[2], "partial")
        prof = graph.to_dict()["understanding"]

        assert set(prof["needs_work"]) & set(prof["recovered"]) == set()
        assert set(prof["needs_work"]) & set(prof["set_aside"]) == set()
        assert prof["totals"] == {
            understanding.STRENGTH: 1, understanding.RECOVERED: 1,
            understanding.UNRESOLVED: 1, understanding.INSUFFICIENT: 1,
        }

    def test_assessed_is_the_honest_denominator(self):
        graph = _graph(4)
        _answer(graph, graph.path_order()[0], "understood")
        prof = graph.to_dict()["understanding"]
        assert prof["assessed"] == 1
        assert prof["total"] == 4

    def test_remedial_and_optional_units_are_out_of_scope(self):
        # Scoped to the promised journey, matching both progress measures.
        graph = _graph(2)
        warm_up = LearningNode(
            title="warm-up", code_anchor=CodeAnchor("w.py", 1, 2),
            lesson_brief={"priority": "required", "origin": "system_remediation"})
        graph.insert_before(graph.path_order()[1], warm_up, kind="prerequisite")
        assert graph.to_dict()["understanding"]["total"] == 2

    def test_interventions_are_unknown_for_pre_m2_attempts(self):
        graph = _graph()
        node_id = graph.path_order()[0]
        graph.nodes[node_id].attempts.append({
            "answer": "a", "classification": "partial", "rationale": "r",
            "at": "2026-08-01T00:00:00+00:00",
        })
        assert understanding.node_summary(graph.nodes[node_id])["interventions"] is None


# ── the evidence drawer ───────────────────────────────────────────────────────


class TestEvidence:
    def test_the_timeline_resolves_to_the_real_attempts(self):
        graph = _graph()
        node_id = graph.path_order()[0]
        graph.record_attempt(node_id, "my first answer", "confused", "missed it")
        graph.record_response(node_id, history.new_response("hint", text="look at line 3"))
        graph.mark_understanding(node_id, "failed")

        chain = understanding.evidence(graph, node_id)
        assert chain["objective"] == "claim 0"
        assert len(chain["timeline"]) == 1
        step = chain["timeline"][0]
        assert step["answer"] == "my first answer"
        assert step["classification"] == "confused"
        assert step["rationale"] == "missed it"
        assert step["intervention"] == "hint"
        assert step["intervention_text"] == "look at line 3"

    def test_pre_m2_steps_report_unknown_rather_than_no_intervention(self):
        graph = _graph()
        node_id = graph.path_order()[0]
        graph.nodes[node_id].attempts.append({
            "answer": "old", "classification": "partial", "rationale": "r",
            "at": "2026-08-01T00:00:00+00:00",
        })
        step = understanding.evidence(graph, node_id)["timeline"][0]
        assert step["intervention"] is None
        assert step["intervention_text"] is None

    def test_an_ungraded_step_is_shown_but_marked_as_non_evidence(self):
        # Visible for honesty — the learner did answer — but not counted.
        graph = _graph()
        node_id = graph.path_order()[0]
        _answer(graph, node_id, "partial", graded=False)
        step = understanding.evidence(graph, node_id)["timeline"][0]
        assert step["graded"] is False
        assert step["counts_as_evidence"] is False

    def test_a_re_teach_exposes_the_lesson_it_replaced(self):
        graph = _graph()
        node_id = graph.path_order()[0]
        graph.record_attempt(node_id, "wrong", "confused", "r")
        graph.record_response(node_id, history.new_response(
            "reteach", retaught=True, superseded_lesson={"walkthrough": "the old one"}))
        step = understanding.evidence(graph, node_id)["timeline"][0]
        assert step["superseded_lesson"]["walkthrough"] == "the old one"

    def test_journey_events_touching_the_node_are_included(self):
        graph = _graph(2)
        ids = graph.path_order()
        graph.record_journey_event(
            history.REMEDIATION_INSERTED, nodes=["w"], unlocks=ids[1])
        assert len(understanding.evidence(graph, ids[1])["journey_events"]) == 1
        assert understanding.evidence(graph, ids[0])["journey_events"] == []


# ── through the endpoints ─────────────────────────────────────────────────────

from unittest.mock import MagicMock, patch  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

import backend.api as api  # noqa: E402

from tests.test_adaptation_api import (  # noqa: E402
    CLONE, PIPE, TEACH, _respond, _start,
)


@pytest.fixture(autouse=True)
def _api_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(api, "SESSIONS_DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(api.anthropic, "Anthropic", lambda **kw: MagicMock())


@pytest.fixture
def client():
    return TestClient(api.app)


@CLONE
@TEACH
@PIPE
def test_the_profile_is_on_the_session_payload(p, t, c, client):
    session_id, node_id = _start(client)
    with patch("backend.api.teaching_respond.hint", return_value="a hint"):
        _respond(client, session_id, "confused", "no_attempt")

    body = client.get(f"/session/{session_id}").json()
    prof = body["understanding"]
    row = next(r for r in prof["nodes"] if r["node_id"] == node_id)
    assert row["understanding"] == understanding.UNRESOLVED
    assert node_id in prof["needs_work"]
    # Per-node classification is on the node too, so the rail can render it.
    wire = next(n for n in body["nodes"] if n["id"] == node_id)
    assert wire["understanding"] == understanding.UNRESOLVED
    assert wire["disposition"] == understanding.ACTIVE


@CLONE
@TEACH
@PIPE
def test_a_recovered_node_leaves_needs_work_through_the_api(p, t, c, client):
    """End to end: the defect this milestone removes."""
    session_id, node_id = _start(client)
    with patch("backend.api.teaching_respond.reteach", return_value=MagicMock()):
        _respond(client, session_id, "confused", "wrong_model")
    _respond(client, session_id, "understood", "none")

    body = client.get(f"/session/{session_id}").json()
    prof = body["understanding"]
    assert node_id in prof["recovered"]
    assert node_id not in prof["needs_work"]
    assert node_id not in prof["set_aside"]
    # The sticky flag is still true — history preserved, just not presented as
    # a current weakness.
    wire = next(n for n in body["nodes"] if n["id"] == node_id)
    assert wire["weak_spot"] is True
    assert wire["understanding"] == understanding.RECOVERED


@CLONE
@TEACH
@PIPE
def test_the_evidence_endpoint_resolves_to_the_real_attempts(p, t, c, client):
    session_id, node_id = _start(client)
    with patch("backend.api.teaching_respond.hint", return_value="look at line 3"):
        _respond(client, session_id, "confused", "no_attempt")

    chain = client.get(f"/session/{session_id}/evidence/{node_id}").json()
    assert chain["node_id"] == node_id
    assert len(chain["timeline"]) == 1
    step = chain["timeline"][0]
    assert step["answer"] == "my answer"
    assert step["intervention"] == "hint"
    assert step["intervention_text"] == "look at line 3"


@CLONE
@TEACH
@PIPE
def test_the_evidence_endpoint_404s_on_an_unknown_node(p, t, c, client):
    session_id, _ = _start(client)
    assert client.get(f"/session/{session_id}/evidence/nope").status_code == 404


@CLONE
@TEACH
@PIPE
def test_existing_sessions_without_history_still_profile(p, t, c, client):
    session_id, _ = _start(client)
    prof = client.get(f"/session/{session_id}").json()["understanding"]
    assert prof["assessed"] == 0
    assert prof["needs_work"] == []
    assert prof["totals"][understanding.INSUFFICIENT] == prof["total"]


# ── M3a.3: one vocabulary, one definition ─────────────────────────────────────


class TestOneVocabularyOneDefinition:
    """AC1/AC2/AC14 — the contradictions the product review found.

    The review saw a screen reporting "4 of 5 required objectives demonstrated"
    directly above "0 of 5 units have evidence", because two modules had two
    definitions of the word. These pin the single definition.
    """

    def test_demonstrated_coverage_and_the_profile_never_disagree(self):
        # AC2, at the source: both surfaces read ONE classifier.
        graph = _graph(4)
        ids = graph.path_order()
        _answer(graph, ids[0], "understood")          # strength
        _answer(graph, ids[1], "confused")
        _answer(graph, ids[1], "understood")          # recovered
        _answer(graph, ids[2], "partial")             # unresolved
        # ids[3] left unassessed

        summary = progress.summary(graph)
        prof = graph.to_dict()["understanding"]

        assert summary["core_demonstrated"] == 2
        assert prof["totals"][understanding.STRENGTH] == 1
        assert prof["totals"][understanding.RECOVERED] == 1
        assert summary["core_demonstrated"] == (
            prof["totals"][understanding.STRENGTH]
            + prof["totals"][understanding.RECOVERED]
        )
        assert summary["goal_readiness"] == 0.5

    def test_state_without_evidence_is_never_demonstrated(self):
        """AC13 — the 80%-with-no-answers session, which is 8 of 69 stored.

        `understanding_state` set with no persisted attempt is what 21 of the 22
        divergent nodes look like: real sessions from before attempts were
        stored. They now read as *insufficient evidence* — never as failure, and
        never as mastery.
        """
        graph = _graph(2)
        for node_id in graph.path_order():
            graph.nodes[node_id].understanding_state = "understood"
            graph.nodes[node_id].visited = True

        assert progress.goal_readiness(graph) == 0.0
        prof = graph.to_dict()["understanding"]
        assert prof["totals"][understanding.INSUFFICIENT] == 2
        assert prof["totals"][understanding.UNRESOLVED] == 0   # not a weakness
        assert prof["needs_work"] == []

    def test_partial_earns_nothing_but_is_reported(self):
        graph = _graph(2)
        ids = graph.path_order()
        _answer(graph, ids[0], "understood")
        _answer(graph, ids[1], "partial")

        summary = progress.summary(graph)
        assert summary["core_demonstrated"] == 1
        assert summary["core_in_progress"] == 1        # visible, not credited
        assert summary["goal_readiness"] == 0.5

    def test_recovered_earns_full_credit(self):
        # "What the learner can demonstrate NOW", not "first time".
        graph = _graph(1)
        node_id = graph.path_order()[0]
        _answer(graph, node_id, "confused")
        _answer(graph, node_id, "understood")
        assert progress.goal_readiness(graph) == 1.0

    def test_a_learner_assertion_cannot_confer_demonstrated_mastery(self):
        """AC5. `mark_understood` writes state directly on a gap-free node."""
        graph = _graph(1)
        graph.override(graph.path_order()[0], "mark_understood")
        assert progress.goal_readiness(graph) == 0.0

    def test_no_plan_mutation_lowers_demonstrated_coverage(self):
        """AC14 — the M1 invariant, re-asserted under the new formula."""
        graph = _graph(3)
        ids = graph.path_order()
        _answer(graph, ids[0], "understood")
        before = progress.goal_readiness(graph)

        warm_up = LearningNode(
            title="warm-up", code_anchor=CodeAnchor("w.py", 1, 2),
            lesson_brief={"priority": "required", "origin": "system_remediation"})
        graph.insert_before(ids[1], warm_up, kind="prerequisite")
        assert progress.goal_readiness(graph) == before

        graph.nodes[ids[2]].lesson_brief["priority"] = "recommended"
        assert progress.goal_readiness(graph) >= before
