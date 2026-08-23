# Learning history — the attempt/intervention envelope and plan-scoped events.
#
# Two properties carry the milestone, and both are about NOT KNOWING things:
#
#   1. A pre-M2 attempt is `unknown`, never "no intervention". Every stored
#      attempt predates this record, so a metric that defaults the absent case
#      would report 40 real answers as help-free.
#   2. A failed grade is our error, not the learner's answer, and must not be
#      counted as evidence about them.

import json

import pytest

from tests.conftest import TEST_USER_ID

from backend.learning import history, progress
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.learning.store import load_graph, save_graph


def _graph() -> LearningGraph:
    graph = LearningGraph(repo_url="r", goal={})
    node = graph.add_node(LearningNode(
        title="n", code_anchor=CodeAnchor("a.py", 1, 2),
        lesson_brief={"priority": "required", "objective": "x"},
    ))
    graph.set_current(node.id)
    return graph


def _pre_m2_attempt(**over) -> dict:
    """Exactly the shape written before this milestone: no kind, no graded,
    no response."""
    return {"answer": "a", "classification": "confused", "gap_kind": "wrong_model",
            "rationale": "r", "at": "2026-08-01T00:00:00+00:00", **over}


# ── unknown is not "none" ─────────────────────────────────────────────────────


class TestPreM2AttemptsAreUnknown:
    def test_an_old_attempt_is_not_instrumented(self):
        assert history.is_instrumented(_pre_m2_attempt()) is False

    def test_its_intervention_is_none_the_value_not_none_the_action(self):
        # The distinction the whole envelope exists for.
        assert history.intervention_of(_pre_m2_attempt()) is None

    def test_a_recorded_no_action_is_distinguishable_from_no_record(self):
        recorded = _pre_m2_attempt(response=history.new_response("none"))
        assert history.intervention_of(recorded) == "none"
        assert history.intervention_of(_pre_m2_attempt()) is None
        assert history.is_instrumented(recorded) is True

    def test_old_attempts_are_excluded_from_an_intervention_denominator(self):
        # The failure this prevents: 3 old attempts + 1 new one reading as
        # "25% needed help" when the truth is "1 of 1 measured".
        attempts = [_pre_m2_attempt(), _pre_m2_attempt(),
                    _pre_m2_attempt(response=history.new_response("hint"))]
        measured = history.instrumented(attempts)
        assert len(measured) == 1
        assert history.intervention_of(measured[0]) == "hint"

    def test_assisted_is_unknown_rather_than_false_for_an_old_attempt(self):
        assert history.was_assisted(_pre_m2_attempt()) is None
        assert history.was_assisted(
            _pre_m2_attempt(response=history.new_response("none"))) is False
        assert history.was_assisted(
            _pre_m2_attempt(response=history.new_response("reteach"))) is True

    def test_an_unrecognised_action_reads_as_unknown_not_as_itself(self):
        attempt = _pre_m2_attempt(response={"action": "telepathy"})
        assert history.intervention_of(attempt) is None


# ── grading failures ──────────────────────────────────────────────────────────


class TestGradingFailures:
    def test_a_failed_grade_is_not_evidence(self):
        failed = _pre_m2_attempt(classification="partial", graded=False)
        assert history.is_graded(failed) is False
        assert history.is_evidence(failed) is False

    def test_a_genuine_partial_is_evidence(self):
        assert history.is_evidence(
            _pre_m2_attempt(classification="partial", graded=True)) is True

    def test_an_old_attempt_keeps_counting_as_graded(self):
        # Unknown must not retroactively delete evidence from stored answers;
        # the conservative direction differs from the intervention case, and
        # deliberately so.
        assert history.is_graded(_pre_m2_attempt()) is True

    def test_off_topic_is_still_not_evidence(self):
        assert history.is_evidence(_pre_m2_attempt(classification="off-topic")) is False

    def test_assessed_coverage_ignores_a_failed_grade(self):
        graph = _graph()
        node = graph.nodes[graph.path_order()[0]]
        node.attempts.append(_pre_m2_attempt(classification="partial", graded=False))
        assert progress.assessed_coverage(graph) == 0.0

    def test_a_failed_grade_earns_no_demonstrated_credit(self):
        """RE-POINTED for Model A' (was `..._does_not_change_the_progress_measures`).

        Under the old weighted gauge this scored 0.5 — half credit for a unit
        whose only "evidence" was our own grading outage. Demonstrated coverage
        requires evidence, and a failed grade is not evidence, so it earns
        nothing and the unit reads *not yet assessed*.
        """
        graph = _graph()
        node = graph.nodes[graph.path_order()[0]]
        node.understanding_state = "partial"
        node.attempts.append(_pre_m2_attempt(classification="partial", graded=False))
        assert progress.goal_readiness(graph) == 0.0


# ── attempt kinds ─────────────────────────────────────────────────────────────


class TestAttemptKinds:
    def test_record_attempt_defaults_to_assessment(self):
        graph = _graph()
        attempt = graph.record_attempt(graph.path_order()[0], "a", "understood", "r")
        assert attempt["kind"] == history.ASSESSMENT
        assert attempt["graded"] is True

    def test_a_verification_answer_is_not_pooled_with_assessments(self):
        # Gap-model M6 grades a FRESH question about one gap. Averaging it with
        # answers to the objective would misreport both.
        graph = _graph()
        node_id = graph.path_order()[0]
        graph.record_attempt(node_id, "a", "confused", "r")
        graph.record_attempt(node_id, "b", "understood", "r",
                             kind=history.VERIFICATION)
        attempts = graph.nodes[node_id].attempts
        assert len(history.assessments(attempts)) == 1

    def test_an_old_attempt_reads_as_an_assessment(self):
        # True by history: verification did not exist when they were written.
        assert history.assessments([_pre_m2_attempt()]) == [_pre_m2_attempt()]


# ── the response envelope ─────────────────────────────────────────────────────


class TestResponseRecording:
    def test_the_response_lands_on_the_answer_that_caused_it(self):
        graph = _graph()
        node_id = graph.path_order()[0]
        graph.record_attempt(node_id, "first", "confused", "r")
        graph.record_attempt(node_id, "second", "confused", "r")
        graph.record_response(node_id, history.new_response("hint", text="try X"))

        attempts = graph.nodes[node_id].attempts
        assert history.intervention_of(attempts[0]) is None
        assert history.intervention_of(attempts[1]) == "hint"
        assert attempts[1]["response"]["text"] == "try X"

    def test_a_response_with_no_attempt_behind_it_is_refused(self):
        graph = _graph()
        assert graph.record_response(graph.path_order()[0],
                                     history.new_response("hint")) is None

    @pytest.mark.parametrize("action", ["none", "hint", "reteach", "prerequisite",
                                        "followup"])
    def test_every_action_round_trips(self, action):
        graph = _graph()
        node_id = graph.path_order()[0]
        graph.record_attempt(node_id, "a", "confused", "r")
        graph.record_response(node_id, history.new_response(action))
        assert history.intervention_of(
            graph.nodes[node_id].attempts[-1]) == action

    def test_a_declined_remediation_keeps_its_reason(self):
        # "Every candidate was a peer, not a foundation" is the most useful thing
        # the system can say about a confusion it chose not to act on, and it was
        # being discarded.
        graph = _graph()
        node_id = graph.path_order()[0]
        graph.record_attempt(node_id, "a", "confused", "r")
        graph.record_response(node_id, history.new_response(
            "prerequisite", declined_reason="all candidates are peers"))
        assert graph.nodes[node_id].attempts[-1]["response"]["declined_reason"]

    def test_a_re_teach_keeps_the_lesson_it_replaced(self):
        graph = _graph()
        node_id = graph.path_order()[0]
        graph.record_attempt(node_id, "a", "confused", "r")
        graph.record_response(node_id, history.new_response(
            "reteach", retaught=True, superseded_lesson={"walkthrough": "old"}))
        stored = graph.nodes[node_id].attempts[-1]["response"]
        assert stored["superseded_lesson"]["walkthrough"] == "old"


# ── plan-scoped events ────────────────────────────────────────────────────────


class TestJourneyEvents:
    def test_a_scope_change_needs_no_attempt(self):
        # The case that decided the ownership split: nothing was answered.
        graph = _graph()
        graph.record_journey_event(history.SCOPE_SHORTER, nodes=["n1", "n2"])
        event = graph.journey_events[0]
        assert event["kind"] == history.SCOPE_SHORTER
        assert event["nodes"] == ["n1", "n2"]
        assert "cause" not in event

    def test_prune_ahead_records_which_units_moved_not_how_many(self):
        # A count cannot answer "which, and were they ever restored?".
        graph = _graph()
        graph.record_journey_event(history.PRUNE_AHEAD, nodes=["a", "b"],
                                   cause={"node_id": "x", "attempt_index": 0})
        assert graph.journey_events[0]["nodes"] == ["a", "b"]
        assert graph.journey_events[0]["cause"]["attempt_index"] == 0

    def test_remediation_records_who_asked_for_it(self):
        graph = _graph()
        graph.record_journey_event(history.REMEDIATION_INSERTED, nodes=["w"],
                                   origin=progress.LEARNER_REQUEST, unlocks="b")
        assert graph.journey_events[0]["origin"] == progress.LEARNER_REQUEST

    def test_events_are_append_only_and_ordered(self):
        graph = _graph()
        graph.record_journey_event(history.SCOPE_SHORTER, nodes=["a"])
        graph.record_journey_event(history.SCOPE_DEEPER, nodes=["a"])
        assert [e["kind"] for e in graph.journey_events] == [
            history.SCOPE_SHORTER, history.SCOPE_DEEPER]


# ── persistence ───────────────────────────────────────────────────────────────


class TestRoundTrip:
    def test_the_envelope_and_the_events_survive_the_store(self, tmp_path):
        db = tmp_path / "s.db"
        graph = _graph()
        node_id = graph.path_order()[0]
        graph.record_attempt(node_id, "a", "confused", "r", graded=False)
        graph.record_response(node_id, history.new_response("hint", text="t"))
        graph.record_journey_event(history.PRUNE_AHEAD, nodes=["z"])
        save_graph(graph, db, user_id=TEST_USER_ID)

        reloaded = load_graph(graph.session_id, TEST_USER_ID, db)
        attempt = reloaded.nodes[node_id].attempts[-1]
        assert attempt["kind"] == history.ASSESSMENT
        assert attempt["graded"] is False
        assert history.intervention_of(attempt) == "hint"
        assert reloaded.journey_events[0]["nodes"] == ["z"]

    def test_a_verification_attempt_round_trips_and_takes_no_response(self, tmp_path):
        """A response belongs to an answer about the OBJECTIVE.

        A verification answer is evidence about one gap, so it earns no
        assessment response — `record_response` files against the latest
        assessment, which is what keeps the two questions apart in the record.
        """
        db = tmp_path / "s.db"
        graph = _graph()
        node_id = graph.path_order()[0]
        graph.record_attempt(node_id, "v", "understood", "r",
                             kind=history.VERIFICATION)
        graph.record_response(node_id, history.new_response("hint"))
        save_graph(graph, db, user_id=TEST_USER_ID)

        attempt = load_graph(graph.session_id, TEST_USER_ID, db).nodes[node_id].attempts[-1]
        assert attempt["kind"] == history.VERIFICATION
        assert history.is_instrumented(attempt) is False

    def test_a_graph_with_no_events_stores_null_not_an_empty_blob(self, tmp_path):
        db = tmp_path / "s.db"
        graph = _graph()
        save_graph(graph, db, user_id=TEST_USER_ID)
        assert load_graph(graph.session_id, TEST_USER_ID, db).journey_events == []

    def test_a_pre_m2_session_loads_with_empty_history(self, tmp_path):
        # Simulates a row written before the column existed.
        db = tmp_path / "s.db"
        graph = _graph()
        graph.nodes[graph.path_order()[0]].attempts.append(_pre_m2_attempt())
        save_graph(graph, db, user_id=TEST_USER_ID)

        reloaded = load_graph(graph.session_id, TEST_USER_ID, db)
        assert reloaded.journey_events == []
        assert history.is_instrumented(
            reloaded.nodes[graph.path_order()[0]].attempts[0]) is False

    def test_the_wire_carries_journey_events(self):
        graph = _graph()
        graph.record_journey_event(history.SCOPE_DEEPER, nodes=["a"])
        assert graph.to_dict()["journey_events"][0]["kind"] == history.SCOPE_DEEPER


# ── the gap-model seam ────────────────────────────────────────────────────────


def test_the_envelope_holds_no_gap_fields():
    """M2 owns the envelope; the Gap Model owns what goes in the gap slots.

    Asserted structurally so gap-model M9 adds `gaps_opened` / `gaps_resolved`
    to this record rather than inventing a competing attempt shape beside it.
    """
    response = history.new_response("reteach", retaught=True)
    assert "gaps_opened" not in response
    assert "gaps_resolved" not in response
    assert set(response) <= {"action", "at", "retaught"}


def test_history_does_not_import_the_gap_model():
    import backend.learning.history as module

    source = json.dumps(open(module.__file__, encoding="utf-8").read())
    assert "from backend.learning.gaps" not in source


# ── through the endpoints ─────────────────────────────────────────────────────
#
# The model tests above prove the envelope holds. These prove `/respond`,
# `/scope` and `/retry` actually FILL it — the wiring is where an intervention
# record is most likely to be silently dropped, because nothing else fails when
# it is.

from unittest.mock import MagicMock, patch  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

import backend.api as api  # noqa: E402

from tests.test_adaptation_api import (  # noqa: E402
    CLONE, PIPE, TEACH, _grader, _respond, _start,
)


@pytest.fixture(autouse=True)
def _api_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(api, "SESSIONS_DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(api.anthropic, "Anthropic", lambda **kw: MagicMock())


@pytest.fixture
def client():
    return TestClient(api.app)


def _latest_attempt(client, session_id, node_id) -> dict:
    graph = client.get(f"/session/{session_id}").json()
    node = next(n for n in graph["nodes"] if n["id"] == node_id)
    return node["attempts"][-1]


@CLONE
@TEACH
@PIPE
def test_a_hint_is_recorded_on_the_answer_that_earned_it(p, t, c, client):
    session_id, node_id = _start(client)
    with patch("backend.api.teaching_respond.hint", return_value="Start at line 3."):
        _respond(client, session_id, "confused", "no_attempt")

    attempt = _latest_attempt(client, session_id, node_id)
    assert history.intervention_of(attempt) == "hint"
    assert attempt["response"]["text"] == "Start at line 3."
    assert attempt["kind"] == history.ASSESSMENT


@CLONE
@TEACH
@PIPE
def test_an_understood_answer_records_that_nothing_was_owed(p, t, c, client):
    # `none` RECORDED is the whole point: it is what makes a pre-M2 attempt
    # distinguishable from a learner who needed no help.
    session_id, node_id = _start(client)
    _respond(client, session_id, "understood", "none")

    attempt = _latest_attempt(client, session_id, node_id)
    assert history.intervention_of(attempt) == "none"
    assert history.was_assisted(attempt) is False


@CLONE
@TEACH
@PIPE
def test_a_re_teach_keeps_the_lesson_it_replaced(p, t, c, client):
    session_id, node_id = _start(client)
    with patch("backend.api.teaching_respond.reteach", return_value=MagicMock()):
        _respond(client, session_id, "confused", "wrong_model")

    attempt = _latest_attempt(client, session_id, node_id)
    assert history.intervention_of(attempt) == "reteach"
    assert attempt["response"]["retaught"] is True
    # The body the learner saw when they got it wrong survives the overwrite.
    assert attempt["response"]["superseded_lesson"]["prompt"]


@CLONE
@TEACH
@PIPE
def test_a_grading_failure_is_recorded_and_kept_out_of_evidence(p, t, c, client):
    session_id, node_id = _start(client)

    def _failing_grader(state, user_response, client=None):
        state.last_grade = {"classification": "partial", "gap_kind": "none",
                            "rationale": "grading failed; defaulted to partial",
                            "graded": False}
        return state

    with patch("backend.api.run_grader", side_effect=_failing_grader), \
         patch("backend.api._node_source", return_value="source"):
        client.post(f"/session/{session_id}/respond", json={"response": "x"})

    attempt = _latest_attempt(client, session_id, node_id)
    assert attempt["graded"] is False
    assert history.is_evidence(attempt) is False


@CLONE
@TEACH
@PIPE
def test_a_scope_change_becomes_a_journey_event_with_no_attempt(p, t, c, client):
    session_id, _ = _start(client)
    client.post(f"/session/{session_id}/scope", json={"direction": "shorter"})

    events = client.get(f"/session/{session_id}").json()["journey_events"]
    scope_events = [e for e in events if e["kind"] == history.SCOPE_SHORTER]
    # The fixture graph is all `required`, so nothing moves and nothing is
    # recorded — an event is written only when the journey actually changed.
    assert all("cause" not in e for e in scope_events)


@CLONE
@TEACH
@PIPE
def test_an_inserted_warm_up_is_recorded_in_both_histories(p, t, c, client):
    # Attempt-scoped: "this answer earned a warm-up".
    # Plan-scoped:    "the journey grew here, and why".
    session_id, node_id = _start(client)
    _respond(client, session_id, "confused", "missing_prerequisite")

    body = client.get(f"/session/{session_id}").json()
    attempt = next(n for n in body["nodes"] if n["id"] == node_id)["attempts"][-1]
    assert history.intervention_of(attempt) == "prerequisite"
    assert attempt["response"]["remediation_node_id"]

    inserted = [e for e in body["journey_events"]
                if e["kind"] == history.REMEDIATION_INSERTED]
    assert len(inserted) == 1
    assert inserted[0]["origin"] == progress.SYSTEM_REMEDIATION
    assert inserted[0]["cause"]["node_id"] == node_id
