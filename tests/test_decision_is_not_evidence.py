"""M0 — a learner decision is never evidence of understanding.

One invariant, three mechanisms that were breaking it, and the two dimensions
that already existed to express it properly (`understanding.py`):

    UNDERSTANDING   what the evidence demonstrates
    DISPOSITION     what the learner decided to do

Everything here asserts the same rule from a different side: a decision moves the
second dimension and never the first, and the first is the only one goal
readiness may read.

The three defects this file pins down, all found by manual E2E and all verified
by execution before the fix:

  B  `continue_past` fired only where OPEN BLOCKING GAPS existed. An `off-topic`
     answer opens no gaps by policy, and a `confused` answer naming no false
     statement opens none either — so "Move on anyway" recorded NOTHING on the
     commonest failure the system sees. The stop never became `is_settled`, so
     `is_complete()` was permanently unreachable for the whole session, silently.

  C  The stop then rendered `insufficient` with disposition `active` — the exact
     pin a stop nobody had ever opened gets. The learner's answer, and their
     decision, were both invisible.

  G  `override("mark_understood")` wrote `understanding_state = "understood"`
     directly on a gap-free node. On an ASSESSED one that turned a failed stop
     into a `strength` and goal readiness from 0.0 to 1.0 — on a button press.

Run with: uv run pytest tests/test_decision_is_not_evidence.py -v
"""
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import TEST_USER_ID, start_session
from fastapi.testclient import TestClient

import backend.api as api
from backend.learning import progress, store as learning_store, understanding
from backend.learning.gaps import Gap
from backend.learning.graph import (
    SETTLING_OVERRIDES,
    CodeAnchor,
    LearningGraph,
    LearningNode,
    is_settled,
    understanding_of,
)

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


def _node(title: str = "A", state: str = "not_started", **brief) -> LearningNode:
    node = LearningNode(
        title=title,
        code_anchor=CodeAnchor(file="requests/sessions.py", line_start=1, line_end=20),
        lesson_brief={
            "objective": f"Explain {title}",
            "priority": "required",
            "area_id": "a1",
            **brief,
        },
    )
    node.understanding_state = state
    node.cached_lesson = {"prompt": "q?", "setup": "…"}
    return node


def _chain(*nodes: LearningNode) -> LearningGraph:
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    for node in nodes:
        graph.add_node(node)
    for a, b in zip(nodes, nodes[1:]):
        graph.add_edge(a.id, b.id, kind="sequence")
    graph.set_current(nodes[0].id)
    return graph


def _answered(graph: LearningGraph, node: LearningNode, classification: str):
    """One graded answer, exactly as `/respond` records it.

    `off-topic` deliberately does not touch `understanding_state` — it is
    evidence of neither understanding nor misunderstanding — which is what makes
    the stop classify `insufficient` while genuinely having been attempted.
    """
    state = {"understood": "understood", "partial": "partial",
             "confused": "failed"}.get(classification)
    if state:
        graph.mark_understanding(node.id, state)
    graph.record_attempt(node.id, "an answer", classification, "mock rationale")


# ── B · "Move on anyway" records the decision ────────────────────────────────


@pytest.mark.parametrize("classification", ["off-topic", "confused", "partial"])
def test_moving_on_is_recorded_for_any_unmet_objective(classification):
    """The fix for B, across all three shortfalls — not just the gap-bearing one.

    Before this, only a node carrying open blocking gaps recorded anything, and
    none of these three opens one on its own.
    """
    graph = _chain(_node("A"), _node("B"))
    node = graph.nodes[graph.path_order()[0]]
    _answered(graph, node, classification)

    assert graph.continue_past(node.id) is True
    assert node.user_override == "continue"


def test_moving_on_needs_an_answer_not_merely_a_visit():
    """The property the old gap test was really protecting, kept explicitly.

    Presence is not a decision. A refresh, a scroll-past and a plain walk-through
    must all record nothing, or the override stops meaning anything and stops
    that nobody decided about get settled.
    """
    graph = _chain(_node("A"), _node("B"))
    node = graph.nodes[graph.path_order()[0]]
    graph.mark_visited(node.id)

    assert graph.continue_past(node.id) is False
    assert node.user_override is None


def test_moving_on_records_nothing_once_the_objective_is_met():
    """There is nothing to continue PAST. Stamping it would claim a decision the
    learner never made about work that does not exist."""
    graph = _chain(_node("A", "understood"), _node("B"))
    node = graph.nodes[graph.path_order()[0]]
    _answered(graph, node, "understood")

    assert graph.continue_past(node.id) is False
    assert node.user_override is None


def test_a_verification_answer_alone_is_not_an_attempt_at_the_objective():
    """`history.assessments` is the shared definition of "they tried", and this
    is why it is shared: a verification answer is evidence about one gap, not an
    attempt at the objective, and counting it here would make this function
    disagree with `understanding.classify` about the same word."""
    graph = _chain(_node("A"))
    node = graph.nodes[graph.path_order()[0]]
    graph.record_attempt(node.id, "about a gap", "", "r", kind="verification")

    assert graph.continue_past(node.id) is False


def test_the_old_gap_rule_still_fires():
    """The widening is strictly additive. Anything that recorded a decision
    before still records one, whatever else changed around it."""
    graph = _chain(_node("A", "partial"))
    node = graph.nodes[graph.path_order()[0]]
    node.gap_state.gaps.append(Gap.create("wrong_model", "a false claim"))

    assert graph.continue_past(node.id) is True


# ── B · and the journey can now finish ───────────────────────────────────────


def test_an_off_topic_stop_no_longer_blocks_completion_forever():
    """The silent half of B, and the worst of it.

    `is_settled` needs `understood` or a settling override. An off-topic answer
    produces neither, `continue_past` recorded nothing, and so `is_complete()`
    could never fire again for the rest of the session — with nothing on screen
    saying why the completion screen never arrived.
    """
    a, b = _node("A"), _node("B")
    graph = _chain(a, b)
    _answered(graph, a, "off-topic")
    graph.mark_visited(a.id)
    graph.continue_past(a.id)

    assert is_settled(a) is True
    _answered(graph, b, "understood")
    graph.mark_visited(b.id)
    assert graph.is_complete() is True


def test_completing_that_way_earns_no_credit():
    """Completion and mastery are separate measures and neither gates the other.
    Walking to the end by moving on must finish the journey and must not claim
    the goal was met."""
    a, b = _node("A"), _node("B")
    graph = _chain(a, b)
    for node in (a, b):
        _answered(graph, node, "off-topic")
        graph.mark_visited(node.id)
        graph.continue_past(node.id)

    assert graph.is_complete() is True
    assert graph.readiness() == 0.0


# ── the invariant itself ─────────────────────────────────────────────────────


@pytest.mark.parametrize("classification", ["off-topic", "confused", "partial"])
def test_moving_on_changes_no_evidence(classification):
    """THE RULE, stated as one assertion set.

    Everything about what the learner demonstrated is identical either side of
    the decision. Only the disposition moves.
    """
    graph = _chain(_node("A"), _node("B"))
    node = graph.nodes[graph.path_order()[0]]
    _answered(graph, node, classification)

    before = (
        understanding_of(node),
        understanding.classify(node),
        progress.is_demonstrated(node),
        progress.goal_readiness(graph),
        len(node.attempts),
    )
    graph.continue_past(node.id)
    after = (
        understanding_of(node),
        understanding.classify(node),
        progress.is_demonstrated(node),
        progress.goal_readiness(graph),
        len(node.attempts),
    )

    assert before == after
    assert understanding.disposition_of(node) == understanding.CONTINUED


def test_the_failed_attempt_survives_the_decision():
    """Choosing to continue must not erase what happened. The attempt is the
    evidence record and it is append-only."""
    graph = _chain(_node("A"))
    node = graph.nodes[graph.path_order()[0]]
    _answered(graph, node, "off-topic")
    graph.continue_past(node.id)

    assert [a["classification"] for a in node.attempts] == ["off-topic"]
    assert node.attempts[0]["answer"] == "an answer"


def test_answering_again_withdraws_the_decision_on_a_gap_free_node():
    """"I moved on" and "I am working on this again" contradict, and the later
    act wins. Already true on the gap path; asserted here for the path M0 opened,
    where there is no gap to have triggered it."""
    graph = _chain(_node("A"))
    node = graph.nodes[graph.path_order()[0]]
    _answered(graph, node, "off-topic")
    graph.continue_past(node.id)
    assert node.user_override == "continue"

    _answered(graph, node, "partial")
    assert node.user_override is None


# ── C · the stop is distinguishable ──────────────────────────────────────────


def test_an_attempted_stop_is_distinguishable_from_an_untouched_one():
    """C, at the wire. `understanding` cannot tell these apart — `insufficient`
    covers both — so the third fact has to be on the wire for any surface to
    render them differently."""
    a, b = _node("A"), _node("B")
    graph = _chain(a, b)
    _answered(graph, a, "off-topic")

    wire = {n["id"]: n for n in graph.to_dict()["nodes"]}
    assert wire[a.id]["understanding"] == wire[b.id]["understanding"] == "insufficient"
    assert wire[a.id]["attempted"] is True
    assert wire[b.id]["attempted"] is False


def test_attempted_counts_assessments_only():
    """A verification answer is about one gap, not about the objective. Counting
    it would let a stop read as attempted on the strength of a question it was
    never asked."""
    graph = _chain(_node("A"))
    node = graph.nodes[graph.path_order()[0]]
    graph.record_attempt(node.id, "about a gap", "", "r", kind="verification")

    wire = graph.to_dict()["nodes"][0]
    assert wire["attempted"] is False


@pytest.mark.parametrize("classification", ["off-topic", "confused"])
def test_a_continued_stop_lands_in_the_set_aside_band(classification):
    """It was in NEITHER band before: not needing work, not set aside, simply
    absent from the profile the learner reads."""
    graph = _chain(_node("A"))
    node = graph.nodes[graph.path_order()[0]]
    _answered(graph, node, classification)
    graph.continue_past(node.id)

    assert understanding.is_set_aside(node) is True
    assert understanding.is_needs_work(node) is False
    assert node.id in graph.to_dict()["understanding"]["set_aside"]


def test_a_deliberately_skipped_stop_is_also_set_aside():
    """Same defect, different door: `skip` produces `insufficient` too, so it
    fell through the old `UNRESOLVED`-only band in exactly the same way."""
    graph = _chain(_node("A"))
    node = graph.nodes[graph.path_order()[0]]
    graph.override(node.id, "skip")

    assert understanding.is_set_aside(node) is True


def test_an_unopened_stop_is_not_work_outstanding():
    """The asymmetry between the two bands, asserted so it cannot be "tidied".

    `is_set_aside` takes `INSUFFICIENT`; `is_needs_work` must not, or every stop
    the learner has not reached yet reads as an open task.
    """
    graph = _chain(_node("A"))
    node = graph.nodes[graph.path_order()[0]]

    assert understanding.is_needs_work(node) is False
    assert understanding.is_set_aside(node) is False


# ── G · an assertion is not a demonstration ──────────────────────────────────


def test_mark_understood_cannot_move_goal_readiness_on_an_assessed_node():
    """G, measured. This is the exact before/after that found the defect."""
    graph = _chain(_node("A"))
    node = graph.nodes[graph.path_order()[0]]
    _answered(graph, node, "confused")
    assert progress.goal_readiness(graph) == 0.0

    graph.override(node.id, "mark_understood")

    assert understanding.classify(node) == understanding.UNRESOLVED
    assert progress.is_demonstrated(node) is False
    assert progress.goal_readiness(graph) == 0.0
    assert understanding.disposition_of(node) == understanding.ASSERTED


def test_mark_understood_settles_without_crediting():
    """Both halves at once. The learner has dealt with the stop — so it must not
    block completion or drag them back on resume — and has demonstrated nothing,
    so the gauge must not move."""
    a, b = _node("A"), _node("B")
    graph = _chain(a, b)
    _answered(graph, a, "confused")
    graph.override(a.id, "mark_understood")
    _answered(graph, b, "understood")
    graph.mark_visited(b.id)

    assert "mark_understood" in SETTLING_OVERRIDES
    assert graph.is_complete() is True
    assert graph.readiness() == 0.5
    assert understanding.is_set_aside(a) is True


def test_mark_weak_is_still_allowed_to_write_state():
    """The asymmetry. Agreeing with a shortfall can only ever lower the claim
    being made about the learner, so it is not the act this milestone restricts —
    and its disposition stays `active`, because "I don't get this" is not a
    decision to stop."""
    graph = _chain(_node("A"))
    node = graph.nodes[graph.path_order()[0]]
    graph.override(node.id, "mark_weak")

    assert node.understanding_state == "failed"
    assert understanding.disposition_of(node) == understanding.ACTIVE
    assert understanding.is_needs_work(node) is False  # no evidence yet, so not a task


def test_no_learner_decision_can_produce_demonstrated_understanding():
    """The invariant swept over every decision the learner can take.

    A single test that would have caught G, and would catch any future override
    that reaches for `understanding_state` again.
    """
    for action in ("mark_understood", "mark_weak", "skip"):
        graph = _chain(_node("A"))
        node = graph.nodes[graph.path_order()[0]]
        _answered(graph, node, "confused")
        graph.override(node.id, action)
        assert progress.is_demonstrated(node) is False, action
        assert progress.goal_readiness(graph) == 0.0, action

    graph = _chain(_node("A"))
    node = graph.nodes[graph.path_order()[0]]
    _answered(graph, node, "confused")
    graph.continue_past(node.id)
    assert progress.is_demonstrated(node) is False
    assert progress.goal_readiness(graph) == 0.0


# ── through the door a learner actually uses ─────────────────────────────────


def _start(client, graph) -> str:
    def _pipeline(repo_url, goal, client=None, progress_id=""):
        state = MagicMock()
        state.graph = graph
        state.errors = []
        return state

    with patch("backend.api.run_pipeline", side_effect=_pipeline), \
         patch("backend.api.run_teaching", side_effect=_teaching_side_effect):
        return start_session(client, FAKE_REPO_URL, FAKE_GOAL)["session_id"]


def test_off_topic_then_move_on_end_to_end(client):
    """**The manual E2E run that started this, as a test.**

    Answer off-topic, press "Move on anyway", and read back exactly what the rail
    reads: a stop that is attempted, set aside, not demonstrated, and no longer
    blocking the journey.
    """
    a, b = _node("A"), _node("B")
    graph = _chain(a, b)
    session_id = _start(client, graph)

    with patch("backend.api.run_grader", side_effect=_grader_side_effect("off-topic")), \
         patch("backend.api.clone_repo", return_value="data/repos/requests"), \
         patch("backend.api.run_teaching", side_effect=_teaching_side_effect):
        graded = client.post(
            f"/session/{session_id}/respond", json={"response": "bananas"}
        ).json()
    assert graded["classification"] == "off-topic"

    with patch("backend.api.run_teaching", side_effect=_teaching_side_effect):
        client.post(f"/session/{session_id}/advance", json={"signal": "next"})

    wire = client.get(f"/session/{session_id}").json()
    stop = next(n for n in wire["nodes"] if n["id"] == a.id)

    assert stop["attempted"] is True
    assert stop["disposition"] == "continued"
    assert stop["understanding"] == "insufficient"      # honestly: no evidence
    assert stop["understanding_state"] != "understood"
    assert stop["attempts"][-1]["classification"] == "off-topic"
    assert a.id in wire["understanding"]["set_aside"]
    assert a.id not in wire["understanding"]["needs_work"]

    stored = learning_store.load_graph(session_id, TEST_USER_ID, api.SESSIONS_DB_PATH)
    assert stored.nodes[a.id].user_override == "continue"
    assert is_settled(stored.nodes[a.id]) is True


def test_the_decision_survives_a_reload(client):
    """It is persisted through `user_override`, which the store already carries —
    so a refresh must not resurrect the stop as unfinished work."""
    a, b = _node("A"), _node("B")
    graph = _chain(a, b)
    session_id = _start(client, graph)

    with patch("backend.api.run_grader", side_effect=_grader_side_effect("confused")), \
         patch("backend.api.clone_repo", return_value="data/repos/requests"), \
         patch("backend.api.run_teaching", side_effect=_teaching_side_effect):
        client.post(f"/session/{session_id}/respond", json={"response": "wrong"})
    with patch("backend.api.run_teaching", side_effect=_teaching_side_effect):
        client.post(f"/session/{session_id}/advance", json={"signal": "next"})

    reloaded = learning_store.load_graph(session_id, TEST_USER_ID, api.SESSIONS_DB_PATH)
    assert reloaded.nodes[a.id].user_override == "continue"
    assert understanding.is_set_aside(reloaded.nodes[a.id]) is True
    assert reloaded.resume_point() != a.id
