"""M1 — every graded answer is traceable to the exact question it answered.

Before this, `record_attempt` stored the answer and not the question, and three
separate mechanisms made the question unrecoverable afterwards:

  - a re-teach REPLACES `cached_lesson`, so the prompt the learner answered
    survived only inside `response.superseded_lesson`, and only for the single
    attempt that caused the rewrite;
  - `grade_verification` clears `pending_verification` whatever the outcome — the
    question is spent once asked — so a verification question existed NOWHERE
    once answered;
  - M5 will put a third question against the same node.

So "which question produced this verdict?" was unanswerable for every stored
attempt. That is not only a reporting gap: it makes any claim about whether two
questions assess the same knowledge unfalsifiable, and that claim is the subject
of the objective-model decision this pass has to make.

The rule throughout: **absent means UNRECORDED, never "there was no question"**,
and no surface may substitute the node's current prompt for a missing one — after
a re-teach that is a different question, and captioning an old answer with it
would be a confident lie rather than a gap.

Run with: uv run pytest tests/test_question_traceability.py -v
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import backend.api as api
from backend.learning import history, store as learning_store, understanding
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
    monkeypatch.setenv("CODEONBOARD_GAPS", "1")
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
    node.cached_lesson = {"prompt": prompt, "setup": "…", "reveal": "…"}
    return node


def _chain(*nodes: LearningNode) -> LearningGraph:
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    for node in nodes:
        graph.add_node(node)
    for a, b in zip(nodes, nodes[1:]):
        graph.add_edge(a.id, b.id, kind="sequence")
    graph.set_current(nodes[0].id)
    return graph


def _start(client, graph) -> str:
    def _pipeline(repo_url, goal, client=None, progress_id=""):
        state = MagicMock()
        state.graph = graph
        state.errors = []
        return state

    with patch("backend.api.run_pipeline", side_effect=_pipeline), \
         patch("backend.api.run_teaching", side_effect=_teaching_side_effect):
        return client.post(
            "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
        ).json()["session_id"]


# ── the record ───────────────────────────────────────────────────────────────


def test_an_attempt_carries_the_question_and_who_asked_it():
    graph = _chain(_node())
    node = graph.nodes[graph.path_order()[0]]
    graph.record_attempt(
        node.id, "an answer", "partial", "r",
        question="What does Session own?", question_source=history.SOURCE_LESSON,
    )
    attempt = node.attempts[-1]
    assert history.question_of(attempt) == "What does Session own?"
    assert history.question_source_of(attempt) == history.SOURCE_LESSON


def test_an_unrecorded_question_reads_as_unknown_not_as_absent():
    """Every attempt written before M1. `None`, so a consumer cannot mistake it
    for "no question was asked" — the same rule `intervention_of` follows."""
    graph = _chain(_node())
    node = graph.nodes[graph.path_order()[0]]
    graph.record_attempt(node.id, "an answer", "partial", "r")
    attempt = node.attempts[-1]

    assert history.QUESTION not in attempt      # omitted, not nulled
    assert history.question_of(attempt) is None
    assert history.question_source_of(attempt) is None


def test_an_unrecognised_source_reads_as_unknown():
    """A store written by a future or foreign version. Same conservative
    direction as `intervention_of` and `precedence_rank`: what we cannot
    interpret is unknown, never guessed into a known value."""
    assert history.question_source_of({"question_source": "telepathy"}) is None


def test_a_blank_question_is_not_a_question():
    assert history.question_of({"question": "   "}) is None


# ── provenance ───────────────────────────────────────────────────────────────


def test_lesson_was_retaught_is_about_provenance_not_recency():
    """Distinct from the frontend's `materialIsNew`, which asks "did the LAST
    answer rewrite this" and must go stale on the next answer. Nothing ever puts
    the original lesson back, so once a re-teach has landed every later question
    off that lesson is a re-taught one."""
    graph = _chain(_node())
    node = graph.nodes[graph.path_order()[0]]

    graph.record_attempt(node.id, "one", "confused", "r")
    assert history.lesson_was_retaught(node.attempts) is False

    graph.record_response(node.id, history.new_response("reteach", retaught=True))
    assert history.lesson_was_retaught(node.attempts) is True

    # A later answer does not un-rewrite it.
    graph.record_attempt(node.id, "two", "partial", "r")
    graph.record_response(node.id, history.new_response("none"))
    assert history.lesson_was_retaught(node.attempts) is True


def test_a_failed_reteach_did_not_change_the_question():
    """`retaught: false` means the call raised and `cached_lesson` was never
    assigned. Counting it would label the ORIGINAL prompt as rewritten."""
    graph = _chain(_node())
    node = graph.nodes[graph.path_order()[0]]
    graph.record_attempt(node.id, "one", "confused", "r")
    graph.record_response(node.id, history.new_response("reteach", retaught=False))
    assert history.lesson_was_retaught(node.attempts) is False


def test_a_verification_response_never_counts_as_a_reteach():
    """`assessments()` filters it out — a verification produces no adaptation at
    all, and its envelope is filed on the verification attempt itself."""
    graph = _chain(_node())
    node = graph.nodes[graph.path_order()[0]]
    graph.record_attempt(node.id, "about a gap", "", "r", kind=history.VERIFICATION)
    node.attempts[-1][history.RESPONSE] = history.new_response("none")
    assert history.lesson_was_retaught(node.attempts) is False


# ── through /respond ─────────────────────────────────────────────────────────


def test_respond_records_the_prompt_that_was_on_screen(client):
    graph = _chain(_node(prompt="What does Session own that a bare request does not?"))
    node_id = graph.path_order()[0]
    session_id = _start(client, graph)

    with patch("backend.api.run_grader", side_effect=_grader_side_effect("partial")), \
         patch("backend.api.clone_repo", return_value="data/repos/requests"), \
         patch("backend.api.run_teaching", side_effect=_teaching_side_effect):
        client.post(f"/session/{session_id}/respond", json={"response": "cookies"})

    stored = learning_store.load_graph(session_id, api.SESSIONS_DB_PATH)
    attempt = stored.nodes[node_id].attempts[-1]
    assert history.question_of(attempt) == (
        "What does Session own that a bare request does not?"
    )
    assert history.question_source_of(attempt) == history.SOURCE_LESSON


def test_a_reteach_does_not_relabel_the_answer_that_caused_it(client):
    """**The misattribution this milestone exists to make impossible.**

    A re-teach in the SAME request assigns `node.cached_lesson` wholesale. Read
    the prompt after grading and every re-taught answer gets filed against the
    question that replaced the one it answered — a record that is not merely
    missing but actively wrong.
    """
    graph = _chain(_node(prompt="ORIGINAL QUESTION"))
    node_id = graph.path_order()[0]
    session_id = _start(client, graph)

    def _reteach(state, node, answer, rationale, source, client=None, gaps=()):
        node.cached_lesson = {"prompt": "REWRITTEN QUESTION", "setup": "…", "reveal": "…"}
        return MagicMock(prompt="REWRITTEN QUESTION")

    def _grade_wrong_model(state, user_response, client=None):
        # `wrong_model` is what earns a re-teach. The shared helper names no gap
        # kind, so `decide_all` picks `prerequisite` and the branch under test
        # never runs.
        node = state.graph.nodes[state.graph.current_node_id]
        state.graph.mark_understanding(node.id, "failed")
        state.last_grade = {"classification": "confused", "rationale": "mock",
                            "gap_kind": "wrong_model"}
        return state

    with patch("backend.api.run_grader", side_effect=_grade_wrong_model), \
         patch("backend.api.clone_repo", return_value="data/repos/requests"), \
         patch("backend.api._node_source", return_value="def send(): ..."), \
         patch("backend.api.teaching_respond.reteach", side_effect=_reteach), \
         patch("backend.api.run_teaching", side_effect=_teaching_side_effect):
        client.post(f"/session/{session_id}/respond", json={"response": "wrong"})

    stored = learning_store.load_graph(session_id, api.SESSIONS_DB_PATH)
    node = stored.nodes[node_id]
    assert history.question_of(node.attempts[-1]) == "ORIGINAL QUESTION"
    # And the lesson really was replaced, so the trap was live.
    assert node.cached_lesson["prompt"] == "REWRITTEN QUESTION"


def test_the_next_answer_is_labelled_as_answering_the_rewritten_question(client):
    """The other half. Both are assessments of the same objective and they are
    NOT the same question: a re-taught prompt is built so it cannot be answered
    while still holding the diagnosed misconception."""
    graph = _chain(_node(prompt="ORIGINAL QUESTION"))
    node_id = graph.path_order()[0]
    graph.nodes[node_id].attempts.append({
        "answer": "wrong", "classification": "confused", "rationale": "r",
        "kind": history.ASSESSMENT, "graded": True, "at": "2026-01-01T00:00:00+00:00",
        "question": "ORIGINAL QUESTION", "question_source": history.SOURCE_LESSON,
        history.RESPONSE: history.new_response("reteach", retaught=True),
    })
    graph.nodes[node_id].cached_lesson = {"prompt": "REWRITTEN QUESTION", "setup": "…"}
    session_id = _start(client, graph)

    with patch("backend.api.run_grader", side_effect=_grader_side_effect("understood")), \
         patch("backend.api.clone_repo", return_value="data/repos/requests"), \
         patch("backend.api.run_teaching", side_effect=_teaching_side_effect):
        client.post(f"/session/{session_id}/respond", json={"response": "better"})

    stored = learning_store.load_graph(session_id, api.SESSIONS_DB_PATH)
    attempts = stored.nodes[node_id].attempts
    assert history.question_of(attempts[-1]) == "REWRITTEN QUESTION"
    assert history.question_source_of(attempts[-1]) == history.SOURCE_RETEACH
    # The earlier one is untouched — the record is append-only.
    assert history.question_of(attempts[0]) == "ORIGINAL QUESTION"
    assert history.question_source_of(attempts[0]) == history.SOURCE_LESSON


# ── through /verify ──────────────────────────────────────────────────────────


def test_a_verification_question_survives_being_answered(client):
    """It existed nowhere afterwards. `grade_verification` clears
    `pending_verification` whatever the outcome — correctly, since the question
    is spent once asked — so the only place it can be kept is the attempt."""
    from backend.learning.gaps import Gap

    graph = _chain(_node())
    node_id = graph.path_order()[0]
    graph.nodes[node_id].gap_state.gaps.append(
        Gap.create("wrong_model", "adapters own cookie state")
    )
    graph.nodes[node_id].gap_state.pending_verification = {
        "question": "FRESH CHECK QUESTION", "targets": [], "at": "2026-01-01T00:00:00+00:00",
    }
    session_id = _start(client, graph)

    def _grade(state, node, answer, client=None):
        # Clears the pending question, exactly as `grade_verification` does. That
        # is the point of this test: if `/respond` read the question AFTER
        # grading it would find nothing, and the assertion below would fail.
        node.gap_state.pending_verification = None
        return {"resolved": [], "unresolved": [], "new_gaps": 0, "rationale": "not yet"}

    with patch("backend.api.grade_verification", side_effect=_grade), \
         patch("backend.api.run_teaching", side_effect=_teaching_side_effect):
        resp = client.post(
            f"/session/{session_id}/respond",
            json={"response": "a check answer", "kind": history.VERIFICATION},
        )
    assert resp.status_code == 200

    stored = learning_store.load_graph(session_id, api.SESSIONS_DB_PATH)
    node = stored.nodes[node_id]
    attempt = node.attempts[-1]
    assert attempt["kind"] == history.VERIFICATION
    assert history.question_of(attempt) == "FRESH CHECK QUESTION"
    assert history.question_source_of(attempt) == history.SOURCE_VERIFICATION
    # Still spent: re-showing it would be the "Try again" defect §18.7 removed.
    assert node.gap_state.pending_verification is None


# ── on the wire ──────────────────────────────────────────────────────────────


def test_the_evidence_timeline_carries_the_question():
    graph = _chain(_node())
    node_id = graph.path_order()[0]
    graph.record_attempt(
        node_id, "an answer", "partial", "r",
        question="What does Session own?", question_source=history.SOURCE_LESSON,
    )
    graph.record_attempt(node_id, "older style", "confused", "r")

    steps = understanding.evidence(graph, node_id)["timeline"]
    assert steps[0]["question"] == "What does Session own?"
    assert steps[0]["question_source"] == history.SOURCE_LESSON
    # Unrecorded reads as null, so the drawer shows nothing rather than guessing.
    assert steps[1]["question"] is None
    assert steps[1]["question_source"] is None


def test_the_node_wire_carries_the_question_on_each_attempt():
    graph = _chain(_node())
    node_id = graph.path_order()[0]
    graph.record_attempt(
        node_id, "an answer", "partial", "r",
        question="What does Session own?", question_source=history.SOURCE_LESSON,
    )
    wire = graph.to_dict()["nodes"][0]
    assert wire["attempts"][-1]["question"] == "What does Session own?"
    assert wire["attempts"][-1]["question_source"] == "lesson"


def test_the_question_survives_a_round_trip(tmp_path):
    db = tmp_path / "s.db"
    graph = _chain(_node())
    node_id = graph.path_order()[0]
    graph.record_attempt(
        node_id, "an answer", "partial", "r",
        question="What does Session own?", question_source=history.SOURCE_RETEACH,
    )
    learning_store.save_graph(graph, db)

    reloaded = learning_store.load_graph(graph.session_id, db)
    attempt = reloaded.nodes[node_id].attempts[-1]
    assert history.question_of(attempt) == "What does Session own?"
    assert history.question_source_of(attempt) == history.SOURCE_RETEACH
