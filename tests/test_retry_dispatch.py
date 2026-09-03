"""M2 — one retry action, and the backend decides what it does.

The learner sees *Ask me again*. Which machinery serves it — verify a gap,
re-assess the objective, or answer a prompt nobody has answered yet — is our
bookkeeping, and asking a learner to choose between those is asking them to
diagnose themselves before they are allowed another go.

**The invariant every case here is a face of:**

    A retry question NEVER ships its own answer.

`cached_lesson.prompt` always does. Teaching's contract for `reveal` is *"the
explanation — now you may answer it"*, and `lessonView` opens it after ANY graded
answer — `off-topic` included. A re-teach does not escape it: it regenerates the
whole lesson, so its new prompt arrives with a new `reveal` that answers it. So
the unit's own prompt is answerable exactly once, before its reveal has ever been
shown, and every later assessment comes from `/verify` or `/reassess`.

That is also what closes the revisit back door: `revealed` in the panel is
`Boolean(result) || attempts.length > 0`, so navigating away from a graded stop
and back used to re-open the composer with the explanation on screen. The rule
was enforced against the learner who read the action row and not against the one
who wandered.

Run with: uv run pytest tests/test_retry_dispatch.py -v
"""
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import TEST_USER_ID, start_session
from fastapi.testclient import TestClient

import backend.api as api
from backend.learning import history, retry, store as learning_store
from backend.learning.gaps import REASSESSMENT_CAP, VERIFICATION_ATTEMPT_CAP, Gap
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode

from tests.test_session_api import (
    FAKE_GOAL,
    FAKE_REPO_URL,
    _grader_side_effect,
    _teaching_side_effect,
)


@pytest.fixture(autouse=True)
def _env_and_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(api, "SESSIONS_DB_PATH", tmp_path / "sessions.db")
    monkeypatch.setattr(api.anthropic, "Anthropic", lambda **kw: MagicMock())


@pytest.fixture
def client():
    return TestClient(api.app)


def _node(title: str = "A", prompt: str = "What does Session own?") -> LearningNode:
    node = LearningNode(
        title=title,
        code_anchor=CodeAnchor(file="requests/sessions.py", line_start=1, line_end=20),
        lesson_brief={"objective": f"Explain {title}", "priority": "required",
                      "area_id": "a1"},
    )
    node.cached_lesson = {"prompt": prompt, "setup": "…", "reveal": "the answer"}
    return node


def _chain(*nodes: LearningNode) -> LearningGraph:
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    for node in nodes:
        graph.add_node(node)
    for a, b in zip(nodes, nodes[1:]):
        graph.add_edge(a.id, b.id, kind="sequence")
    graph.set_current(nodes[0].id)
    return graph


def _answered(graph, node, classification="confused", graded=True):
    state = {"understood": "understood", "partial": "partial",
             "confused": "failed"}.get(classification)
    if state:
        graph.mark_understanding(node.id, state)
    graph.record_attempt(
        node.id, "an answer", classification, "fell short", graded=graded,
        question=(node.cached_lesson or {}).get("prompt", ""),
        question_source=history.SOURCE_LESSON,
    )


def _start(client, graph) -> str:
    def _pipeline(repo_url, goal, client=None, progress_id=""):
        state = MagicMock()
        state.graph = graph
        state.errors = []
        return state

    with patch("backend.api.run_pipeline", side_effect=_pipeline), \
         patch("backend.api.run_teaching", side_effect=_teaching_side_effect):
        return start_session(client, FAKE_REPO_URL, FAKE_GOAL)["session_id"]


# ── the unit's own prompt is answerable exactly once ─────────────────────────


def test_an_unanswered_prompt_is_the_first_attempt_not_a_retry():
    graph = _chain(_node())
    node = graph.nodes[graph.path_order()[0]]
    assert retry.prompt_is_unanswered(node) is True
    assert retry.offer(node).mechanism == retry.ANSWER


def test_one_graded_answer_spends_the_prompt_for_good():
    """The reveal has now been shown, so this prompt can never again produce
    evidence — whatever the verdict was, and even for `off-topic`, which is the
    case a learner is most likely to want another go at."""
    for verdict in ("off-topic", "confused", "partial", "understood"):
        graph = _chain(_node())
        node = graph.nodes[graph.path_order()[0]]
        _answered(graph, node, verdict)
        assert retry.prompt_is_unanswered(node) is False, verdict


def test_a_reteach_does_not_make_the_prompt_answerable_again():
    """**The subtle one.** A re-taught prompt is a genuinely better question —
    built so it cannot be answered while holding the diagnosed misconception —
    and it arrives with a new `reveal` that answers it. Better question, same
    leak."""
    graph = _chain(_node())
    node = graph.nodes[graph.path_order()[0]]
    _answered(graph, node, "confused")
    graph.record_response(node.id, history.new_response("reteach", retaught=True))
    node.cached_lesson = {"prompt": "REWRITTEN", "setup": "…", "reveal": "the answer"}

    assert retry.prompt_is_unanswered(node) is False


def test_a_failed_grade_does_not_spend_the_prompt():
    """A grading outage is our error. Charging the learner for it takes away an
    attempt they never got — the same reasoning `history.is_evidence` uses."""
    graph = _chain(_node())
    node = graph.nodes[graph.path_order()[0]]
    _answered(graph, node, "partial", graded=False)
    assert retry.prompt_is_unanswered(node) is True


def test_a_verification_answer_does_not_spend_the_prompt():
    graph = _chain(_node())
    node = graph.nodes[graph.path_order()[0]]
    graph.record_attempt(node.id, "about a gap", "", "r", kind=history.VERIFICATION)
    assert retry.prompt_is_unanswered(node) is True


# ── the dispatch ─────────────────────────────────────────────────────────────


def test_a_gap_outranks_the_objective():
    """A gap is a sharper target, and it is the ONLY thing that can produce
    `verified` — which is what lifts M7's demotion. Re-assessing first would
    produce an `understood` the node could not keep."""
    graph = _chain(_node())
    node = graph.nodes[graph.path_order()[0]]
    _answered(graph, node, "confused")
    gap = Gap.create("wrong_model", "adapters own cookie state")
    node.gap_state.gaps.append(gap)

    result = retry.offer(node)
    assert result.mechanism == retry.VERIFY
    assert result.gap_id == gap.id


def test_no_gap_falls_through_to_the_objective():
    """27 of the 34 real unmet stops in the stored sessions look like this: the
    learner fell short and the Grader named no false statement, so `/verify` has
    nothing to aim at. Before M2 there was no route at all."""
    graph = _chain(_node())
    node = graph.nodes[graph.path_order()[0]]
    _answered(graph, node, "off-topic")

    result = retry.offer(node)
    assert result.mechanism == retry.REASSESS
    assert result.reassessments_left == REASSESSMENT_CAP


def test_an_exhausted_gap_falls_through_rather_than_blocking():
    """The cap ends the SYSTEM's offering for that gap; it does not end the
    learner's route. The objective is still assessable, and the gap stays open
    and still blocking — which is what keeps the node honestly short of
    `understood`."""
    graph = _chain(_node())
    node = graph.nodes[graph.path_order()[0]]
    _answered(graph, node, "confused")
    gap = Gap.create("wrong_model", "a false claim")
    for _ in range(VERIFICATION_ATTEMPT_CAP):
        gap.record_failed_verification()
    node.gap_state.gaps.append(gap)

    assert gap.is_open and gap.is_blocking
    assert retry.offer(node).mechanism == retry.REASSESS


def test_a_pending_question_wins_over_offering_another():
    """Answer what is in front of you. Offering a second would abandon a budget
    already spent."""
    graph = _chain(_node())
    node = graph.nodes[graph.path_order()[0]]
    _answered(graph, node, "confused")
    node.gap_state.pending_reassessment = {"question": "a fresh one", "at": "now"}

    result = retry.offer(node)
    assert result.available is False
    assert result.reason == retry.PENDING


def test_a_stop_that_was_never_taught_offers_nothing():
    """Found by running `offer` over all 968 stored nodes, not by reading it.

    A node with no `cached_lesson` fell through every branch and was offered a
    RE-ASSESSMENT — a second question about material the learner has not been
    shown once. Unreachable from `/lesson`, which renders before it reports, and
    wrong everywhere else.
    """
    graph = _chain(_node())
    node = graph.nodes[graph.path_order()[0]]
    node.cached_lesson = None

    result = retry.offer(node)
    assert result.available is False
    assert result.reason == retry.NOT_APPLICABLE


def test_an_untaught_stop_carrying_a_gap_is_still_reachable():
    """The guard must not strand a warm-up whose lesson failed to render but
    which already carries a diagnosed misconception. A gap is a target whether or
    not there is prose beside it."""
    graph = _chain(_node())
    node = graph.nodes[graph.path_order()[0]]
    node.cached_lesson = None
    node.gap_state.gaps.append(Gap.create("wrong_model", "a false claim"))

    assert retry.offer(node).mechanism == retry.VERIFY


def test_nothing_is_offered_once_the_objective_is_met():
    """Not a refusal. There is nothing to retry, and a surface should say so
    rather than hiding the control and leaving the learner guessing."""
    graph = _chain(_node())
    node = graph.nodes[graph.path_order()[0]]
    _answered(graph, node, "understood")

    result = retry.offer(node)
    assert result.available is False
    assert result.reason == retry.MET


def test_the_budget_runs_out_and_says_so():
    graph = _chain(_node())
    node = graph.nodes[graph.path_order()[0]]
    _answered(graph, node, "confused")
    node.gap_state.reassessments = REASSESSMENT_CAP

    result = retry.offer(node)
    assert result.available is False
    assert result.reason == retry.EXHAUSTED
    assert result.reassessments_left == 0


def test_running_out_does_not_settle_the_node():
    """The caps end the offering, never the obligation (§18.16.1). The stop stays
    outstanding, which is the honest state: nobody has demonstrated it and nobody
    has chosen to stop."""
    from backend.learning import understanding
    from backend.learning.graph import is_settled

    graph = _chain(_node())
    node = graph.nodes[graph.path_order()[0]]
    _answered(graph, node, "confused")
    node.gap_state.reassessments = REASSESSMENT_CAP

    assert retry.offer(node).available is False
    assert is_settled(node) is False
    assert understanding.is_needs_work(node) is True


# ── /reassess ────────────────────────────────────────────────────────────────


def _reassess_ok(question="A FRESH OBJECTIVE QUESTION"):
    from backend.agents.teaching.reassess import ReassessmentPrompt
    return lambda state, node, source, client=None: ReassessmentPrompt(
        question=question, probes="the boundary clause"
    )


def test_reassess_issues_a_question_and_charges_it(client):
    graph = _chain(_node())
    node_id = graph.path_order()[0]
    _answered(graph, graph.nodes[node_id], "off-topic")
    session_id = _start(client, graph)

    with patch("backend.api._node_source", return_value="def send(): ..."), \
         patch("backend.api.teaching_reassess.reassess", side_effect=_reassess_ok()):
        body = client.post(f"/session/{session_id}/reassess", json={}).json()

    assert body["question"] == "A FRESH OBJECTIVE QUESTION"
    stored = learning_store.load_graph(session_id, TEST_USER_ID, api.SESSIONS_DB_PATH)
    state = stored.nodes[node_id].gap_state
    assert state.pending_reassessment["question"] == "A FRESH OBJECTIVE QUESTION"
    assert state.reassessments == 1
    # Charged on ISSUE. A learner who could refresh their way to fresh questions
    # would turn the measure from mastery into persistence.
    assert body["retry"]["reassessments_left"] == REASSESSMENT_CAP - 1


def test_a_question_we_could_not_generate_is_not_charged(client):
    graph = _chain(_node())
    node_id = graph.path_order()[0]
    _answered(graph, graph.nodes[node_id], "off-topic")
    session_id = _start(client, graph)

    with patch("backend.api._node_source", return_value="def send(): ..."), \
         patch("backend.api.teaching_reassess.reassess", return_value=None):
        resp = client.post(f"/session/{session_id}/reassess", json={})

    assert resp.status_code == 503
    stored = learning_store.load_graph(session_id, TEST_USER_ID, api.SESSIONS_DB_PATH)
    assert stored.nodes[node_id].gap_state.reassessments == 0


def test_reassess_refuses_without_source(client):
    """§4.1.2, and it matters more here than for a verification: this answer is an
    ordinary assessment, so failing an imaginary question would move
    `understanding_state` on the strength of imaginary code."""
    graph = _chain(_node())
    _answered(graph, graph.nodes[graph.path_order()[0]], "off-topic")
    session_id = _start(client, graph)

    with patch("backend.api._node_source", side_effect=OSError("gone")):
        resp = client.post(f"/session/{session_id}/reassess", json={})
    assert resp.status_code == 409
    assert resp.json()["detail"] == "source_unavailable"


def test_reassess_refuses_past_the_cap(client):
    graph = _chain(_node())
    node_id = graph.path_order()[0]
    _answered(graph, graph.nodes[node_id], "off-topic")
    graph.nodes[node_id].gap_state.reassessments = REASSESSMENT_CAP
    session_id = _start(client, graph)

    resp = client.post(f"/session/{session_id}/reassess", json={})
    assert resp.status_code == 409
    assert resp.json()["detail"] == "reassessment_budget_spent"


def test_reassess_refuses_once_the_objective_is_met(client):
    graph = _chain(_node())
    _answered(graph, graph.nodes[graph.path_order()[0]], "understood")
    session_id = _start(client, graph)

    resp = client.post(f"/session/{session_id}/reassess", json={})
    assert resp.status_code == 409
    assert resp.json()["detail"] == "objective_already_met"


# ── answering a re-assessment ────────────────────────────────────────────────


def test_a_reassessment_answer_is_an_ordinary_assessment(client):
    """The whole design in one test. A second question about the objective is not
    a special kind of evidence — it is more of the same kind, marked by the same
    standard, moving the same state."""
    graph = _chain(_node())
    node_id = graph.path_order()[0]
    _answered(graph, graph.nodes[node_id], "confused")
    graph.nodes[node_id].gap_state.pending_reassessment = {
        "question": "A FRESH OBJECTIVE QUESTION", "probes": "x", "at": "now",
    }
    session_id = _start(client, graph)

    with patch("backend.api.run_grader", side_effect=_grader_side_effect("understood")), \
         patch("backend.api.clone_repo", return_value="data/repos/requests"), \
         patch("backend.api.run_teaching", side_effect=_teaching_side_effect):
        body = client.post(
            f"/session/{session_id}/respond",
            json={"response": "a good answer", "kind": history.SOURCE_REASSESSMENT},
        ).json()

    assert body["classification"] == "understood"
    stored = learning_store.load_graph(session_id, TEST_USER_ID, api.SESSIONS_DB_PATH)
    node = stored.nodes[node_id]
    attempt = node.attempts[-1]
    # An ASSESSMENT, so it counts as evidence about the objective.
    assert attempt["kind"] == history.ASSESSMENT
    assert history.question_of(attempt) == "A FRESH OBJECTIVE QUESTION"
    assert history.question_source_of(attempt) == history.SOURCE_REASSESSMENT
    # And the question is spent.
    assert node.gap_state.pending_reassessment is None


def test_answering_a_reassessment_makes_recovery_reachable(client):
    """**What this milestone exists for.** `RECOVERED` is defined as "fell short,
    then demonstrated it" and `is_demonstrated` credits it in full — and before
    M2 there was no mechanism on a gap-free node that could produce one."""
    from backend.learning import progress, understanding

    graph = _chain(_node())
    node_id = graph.path_order()[0]
    _answered(graph, graph.nodes[node_id], "confused")
    assert understanding.classify(graph.nodes[node_id]) == understanding.UNRESOLVED
    graph.nodes[node_id].gap_state.pending_reassessment = {
        "question": "A FRESH OBJECTIVE QUESTION", "probes": "x", "at": "now",
    }
    session_id = _start(client, graph)

    with patch("backend.api.run_grader", side_effect=_grader_side_effect("understood")), \
         patch("backend.api.clone_repo", return_value="data/repos/requests"), \
         patch("backend.api.run_teaching", side_effect=_teaching_side_effect):
        client.post(
            f"/session/{session_id}/respond",
            json={"response": "a good answer", "kind": history.SOURCE_REASSESSMENT},
        )

    stored = learning_store.load_graph(session_id, TEST_USER_ID, api.SESSIONS_DB_PATH)
    node = stored.nodes[node_id]
    assert understanding.classify(node) == understanding.RECOVERED
    assert progress.is_demonstrated(node) is True
    assert stored.readiness() == 1.0


def test_a_reassessment_cannot_credit_over_an_unverified_gap(client):
    """M7 is untouched, and this is the guard that makes gap-first dispatch more
    than a preference: even reached by name, a re-assessment cannot lift a node
    over a blocking gap nobody has verified."""
    graph = _chain(_node())
    node_id = graph.path_order()[0]
    _answered(graph, graph.nodes[node_id], "confused")
    graph.nodes[node_id].gap_state.gaps.append(
        Gap.create("wrong_model", "a false claim")
    )
    graph.nodes[node_id].gap_state.pending_reassessment = {
        "question": "A FRESH OBJECTIVE QUESTION", "probes": "x", "at": "now",
    }
    session_id = _start(client, graph)

    with patch("backend.api.run_grader", side_effect=_grader_side_effect("understood")), \
         patch("backend.api.clone_repo", return_value="data/repos/requests"), \
         patch("backend.api.run_teaching", side_effect=_teaching_side_effect):
        body = client.post(
            f"/session/{session_id}/respond",
            json={"response": "a good answer", "kind": history.SOURCE_REASSESSMENT},
        ).json()

    assert body["classification"] == "understood"
    assert body["understanding_state"] != "understood"


def test_answering_a_reassessment_that_was_never_issued_is_refused(client):
    graph = _chain(_node())
    _answered(graph, graph.nodes[graph.path_order()[0]], "confused")
    session_id = _start(client, graph)

    with patch("backend.api.clone_repo", return_value="data/repos/requests"), \
         patch("backend.api.run_teaching", side_effect=_teaching_side_effect):
        resp = client.post(
            f"/session/{session_id}/respond",
            json={"response": "x", "kind": history.SOURCE_REASSESSMENT},
        )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "no_pending_reassessment"


# ── the wire ─────────────────────────────────────────────────────────────────


def test_the_offer_survives_a_reload(client):
    """A refresh is not a decision about the learner's understanding, so it must
    not change what is on offer. Before this the offer existed only inside a
    grading reply."""
    graph = _chain(_node())
    node_id = graph.path_order()[0]
    _answered(graph, graph.nodes[node_id], "off-topic")
    graph.nodes[node_id].gap_state.pending_reassessment = {
        "question": "A FRESH OBJECTIVE QUESTION", "probes": "x", "at": "now",
    }
    session_id = _start(client, graph)

    with patch("backend.api.run_teaching", side_effect=_teaching_side_effect):
        body = client.get(f"/session/{session_id}/lesson").json()

    assert body["pending"]["kind"] == history.SOURCE_REASSESSMENT
    assert body["pending"]["question"] == "A FRESH OBJECTIVE QUESTION"
    assert body["retry"]["available"] is False
    assert body["retry"]["reason"] == retry.PENDING


def test_the_lesson_offers_the_retry_on_a_revisit(client):
    """The back door, from the door a learner uses. A revisit to a graded stop
    must not hand back the composer for a prompt whose reveal is on screen — it
    must hand back the retry."""
    graph = _chain(_node())
    node_id = graph.path_order()[0]
    _answered(graph, graph.nodes[node_id], "confused")
    session_id = _start(client, graph)

    with patch("backend.api.run_teaching", side_effect=_teaching_side_effect):
        body = client.get(f"/session/{session_id}/lesson").json()

    assert body["pending"] is None
    assert body["retry"]["available"] is True
    assert body["retry"]["mechanism"] == retry.REASSESS


def test_the_round_trip_keeps_the_budget(tmp_path):
    db = tmp_path / "s.db"
    graph = _chain(_node())
    node_id = graph.path_order()[0]
    graph.nodes[node_id].gap_state.reassessments = 1
    graph.nodes[node_id].gap_state.pending_reassessment = {"question": "q", "at": "now"}
    learning_store.save_graph(graph, db, user_id=TEST_USER_ID)

    reloaded = learning_store.load_graph(graph.session_id, TEST_USER_ID, db)
    state = reloaded.nodes[node_id].gap_state
    assert state.reassessments == 1
    assert state.pending_reassessment["question"] == "q"


# ── the whole loop, end to end ───────────────────────────────────────────────


def test_the_complete_learner_loop(client):
    """**The flow this pass exists to make coherent, walked once.**

        Lesson → Answer → Feedback → Move on anyway → come back
              → Ask me again → fresh question → Re-evaluation → RECOVERED

    Every invariant the pass set out to hold is asserted at the point it applies,
    in the order a learner meets them. Before this pass the walk stopped dead at
    step 3: an off-topic answer left a stop that recorded no decision, rendered
    like one nobody had opened, blocked completion for the whole session, and had
    no route back to `understood` at all.
    """
    from backend.learning import progress, understanding
    from backend.learning.graph import is_settled, understanding_of

    graph = _chain(_node("A"), _node("B"))
    a, b = graph.path_order()
    session_id = _start(client, graph)

    # 1 ── an off-topic answer. No gaps by policy, no grasp signal either way.
    with patch("backend.api.run_grader", side_effect=_grader_side_effect("off-topic")), \
         patch("backend.api.clone_repo", return_value="data/repos/requests"), \
         patch("backend.api.run_teaching", side_effect=_teaching_side_effect):
        graded = client.post(
            f"/session/{session_id}/respond", json={"response": "bananas"}
        ).json()
    assert graded["classification"] == "off-topic"
    # The retry exists immediately, and it is the objective route because there is
    # no gap to aim at.
    assert graded["retry"]["mechanism"] == retry.REASSESS

    # 2 ── "Move on anyway". A DECISION, recorded, and not evidence.
    with patch("backend.api.run_teaching", side_effect=_teaching_side_effect):
        client.post(f"/session/{session_id}/advance", json={"signal": "next"})
    stored = learning_store.load_graph(session_id, TEST_USER_ID, api.SESSIONS_DB_PATH)
    assert stored.nodes[a].user_override == "continue"
    assert understanding.classify(stored.nodes[a]) == understanding.INSUFFICIENT
    assert understanding.is_set_aside(stored.nodes[a]) is True
    assert is_settled(stored.nodes[a]) is True          # completion unblocked
    assert progress.goal_readiness(stored) == 0.0       # and nothing credited

    # 3 ── the walk moved on, and the next stop is untouched: its own prompt is
    #      live, because nothing has been graded there and no reveal has shown.
    with patch("backend.api.run_teaching", side_effect=_teaching_side_effect):
        onward = client.get(f"/session/{session_id}/lesson").json()
    assert onward["node_id"] == b
    assert onward["retry"]["mechanism"] == retry.ANSWER

    # 4 ── COMING BACK to the stop they left, through the door a learner uses.
    #      The prompt is SPENT — its reveal has been shown — so the composer is
    #      gone and the retry is what is offered instead. This is the back door
    #      closed: before, a revisit handed back the composer with the
    #      explanation on screen.
    with patch("backend.api.run_teaching", side_effect=_teaching_side_effect):
        client.post(f"/session/{session_id}/jump", json={"node_id": a})
        revisit = client.get(f"/session/{session_id}/lesson").json()
    assert revisit["node_id"] == a
    assert revisit["retry"]["mechanism"] == retry.REASSESS
    assert revisit["pending"] is None

    # 5 ── Ask me again. A fresh question, shipping no answer.
    with patch("backend.api._node_source", return_value="def send(): ..."), \
         patch("backend.api.teaching_reassess.reassess",
               side_effect=_reassess_ok("A DIFFERENT QUESTION, SAME OBJECTIVE")):
        asked = client.post(
            f"/session/{session_id}/reassess", json={"node_id": a}
        ).json()
    assert asked["question"] == "A DIFFERENT QUESTION, SAME OBJECTIVE"
    assert "reveal" not in asked and "expected_answer" not in asked

    # 6 ── answering it. An ORDINARY assessment of the same objective, and the
    #      decision to move on is withdrawn by the act of working on it again.
    with patch("backend.api.run_grader", side_effect=_grader_side_effect("understood")), \
         patch("backend.api.clone_repo", return_value="data/repos/requests"), \
         patch("backend.api.run_teaching", side_effect=_teaching_side_effect):
        client.post(
            f"/session/{session_id}/respond",
            json={"response": "A good answer.", "node_id": a,
                  "kind": history.SOURCE_REASSESSMENT},
        )

    stored = learning_store.load_graph(session_id, TEST_USER_ID, api.SESSIONS_DB_PATH)
    node = stored.nodes[a]
    assert node.user_override is None                    # withdrawn by the attempt
    assert understanding_of(node) == "understood"
    # STRENGTH, and that is right rather than a near miss. `history.is_evidence`
    # excludes an `off-topic` answer from evidence entirely — it is evidence of
    # neither understanding nor misunderstanding — so there is no recorded
    # shortfall for this demonstration to be a recovery FROM. A learner who said
    # something unrelated and then made the claim has demonstrated it, once.
    #
    # The `confused` path, which IS a recorded shortfall, produces `RECOVERED`;
    # that is `test_answering_a_reassessment_makes_recovery_reachable` above.
    assert understanding.classify(node) == understanding.STRENGTH
    assert progress.is_demonstrated(node) is True

    # 7 ── and every answer is traceable to the question it answered.
    asked_questions = [
        (history.question_source_of(x), history.question_of(x)) for x in node.attempts
    ]
    assert asked_questions == [
        (history.SOURCE_LESSON, "What does Session own?"),
        (history.SOURCE_REASSESSMENT, "A DIFFERENT QUESTION, SAME OBJECTIVE"),
    ]

    # 8 ── nothing further is offered, because there is nothing left to show.
    assert retry.offer(node).reason == retry.MET
