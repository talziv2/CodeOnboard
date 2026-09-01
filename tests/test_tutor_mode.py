"""Which Tutor runs here — the dispatch, and the two `retry.py` clauses it rests on.

Run with: uv run pytest tests/test_tutor_mode.py -v

`mode_for` is SCAFFOLD when, and only when, an UNANSWERED QUESTION IS OUTSTANDING.
Everything below is that sentence, case by case — plus the two clauses this feature
added to `retry.py`, which are asserted here rather than in the retry suite because
they only exist because of the Tutor.

Pure: no API key, no database, no checkout.
"""
import pytest

from backend.agents.tutor.mode import (
    ASKING_LESSON,
    ASKING_REASSESSMENT,
    ASKING_VERIFICATION,
    NO_NODE,
    NOT_ASKING,
    mode_for,
)
from backend.learning import history, retry as retry_model
from backend.learning.gaps import REASSESSMENT_CAP, Gap
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.learning.tutor import EXPLAIN, HINT_LADDER_MAX, SCAFFOLD


PROMPT = "What does Session.send return?"


def _node(taught: bool = True) -> LearningNode:
    node = LearningNode(
        title="The Session object",
        code_anchor=CodeAnchor("requests/sessions.py", 1, 80, symbol="Session"),
        lesson_brief={"objective": "Explain what Session owns"},
    )
    if taught:
        node.cached_lesson = {
            "prompt": PROMPT,
            "reveal": "It returns a Response.",
            "expected_answer": "A Response.",
        }
    return node


def _graded(node: LearningNode, classification: str = "partial") -> LearningNode:
    node.attempts.append({
        "answer": "something",
        "classification": classification,
        "rationale": "r",
        "kind": history.ASSESSMENT,
        "graded": True,
    })
    node.understanding_state = classification if classification != "off-topic" else "not_started"
    return node


# ── SCAFFOLD: the three ways a question is outstanding ────────────────────────


def test_the_units_own_live_prompt_is_scaffold():
    mode = mode_for(_node())
    assert mode.mode == SCAFFOLD
    assert mode.reason == ASKING_LESSON
    assert mode.question == PROMPT
    assert mode.question_source == history.SOURCE_LESSON
    assert mode.hints_left == HINT_LADDER_MAX
    assert mode.can_hint is True
    assert mode.can_reveal is True


def test_a_pending_verification_is_scaffold_and_wins():
    """A verification outranks the lesson prompt — it is what is on screen."""
    node = _graded(_node())
    node.gap_state.pending_verification = {"question": "Where does the pool live?"}
    mode = mode_for(node)
    assert mode.mode == SCAFFOLD
    assert mode.reason == ASKING_VERIFICATION
    assert mode.question == "Where does the pool live?"
    assert mode.question_source == history.SOURCE_VERIFICATION


def test_a_pending_reassessment_is_scaffold():
    node = _graded(_node())
    node.gap_state.pending_reassessment = {"question": "Say it again, differently."}
    mode = mode_for(node)
    assert mode.mode == SCAFFOLD
    assert mode.reason == ASKING_REASSESSMENT
    assert mode.question_source == history.SOURCE_REASSESSMENT


def test_a_re_taught_prompt_reports_its_real_source():
    node = _node()
    node.attempts.append({
        "answer": "wrong", "classification": "confused", "rationale": "r",
        "kind": history.ASSESSMENT, "graded": True,
        "response": {"action": "reteach", "retaught": True, "at": "now"},
    })
    node.cached_lesson = {"prompt": "A better question", "reveal": "x"}
    # The re-teach installed a new prompt, but the old one was graded, so the
    # prompt is spent and this is EXPLAIN — the reveal is already on screen.
    assert mode_for(node).mode == EXPLAIN


# ── EXPLAIN: everything else ──────────────────────────────────────────────────


def test_no_node_is_explain():
    mode = mode_for(None)
    assert mode.mode == EXPLAIN
    assert mode.reason == NO_NODE
    assert mode.can_hint is False
    assert mode.can_reveal is False


def test_an_untaught_stop_is_explain():
    """Nothing has been asked yet, so there is nothing to scaffold."""
    assert mode_for(_node(taught=False)).mode == EXPLAIN


def test_a_graded_stop_is_explain():
    """The reveal is on screen after any graded answer — refusing to explain there
    would be theatre, and `retry.py` already says the prompt is spent."""
    mode = mode_for(_graded(_node()))
    assert mode.mode == EXPLAIN
    assert mode.reason == NOT_ASKING
    assert mode.can_hint is False


def test_a_revisited_stop_is_explain():
    node = _graded(_node(), "understood")
    node.visited = True
    assert mode_for(node).mode == EXPLAIN


# ── the reveal clause in retry.py ─────────────────────────────────────────────


def test_revealing_spends_the_prompt():
    """tutor.md §6.3 — the one clause this feature added to `prompt_is_unanswered`."""
    node = _node()
    assert retry_model.prompt_is_unanswered(node) is True
    assert retry_model.offer(node).mechanism == retry_model.ANSWER

    node.tutor_state.revealed = True

    assert retry_model.prompt_is_unanswered(node) is False
    assert mode_for(node).mode == EXPLAIN, "a spent prompt is not something to scaffold"


def test_after_revealing_the_learner_is_offered_a_fresh_question():
    """The assessment is DEFERRED, not lost — and through the existing machinery."""
    node = _node()
    node.tutor_state.revealed = True
    offer = retry_model.offer(node)
    assert offer.mechanism == retry_model.REASSESS
    assert offer.available is True
    assert offer.reassessments_left == REASSESSMENT_CAP


def test_after_revealing_an_open_gap_still_wins():
    """`/verify` outranks `/reassess`; the reveal does not change the ordering."""
    node = _graded(_node())
    node.tutor_state.revealed = True
    gap = Gap.create(kind="wrong_model", claim="wrong", objective_part="o")
    node.gap_state.gaps.append(gap)
    offer = retry_model.offer(node)
    assert offer.mechanism == retry_model.VERIFY
    assert offer.gap_id == gap.id


def test_revealing_changes_nothing_about_understanding():
    """The invariant. A decision is never evidence."""
    from backend.learning.graph import understanding_of

    node = _node()
    before = (node.understanding_state, understanding_of(node), node.weak_spot,
              len(node.attempts), len(node.gaps))
    node.tutor_state.revealed = True
    after = (node.understanding_state, understanding_of(node), node.weak_spot,
             len(node.attempts), len(node.gaps))
    assert before == after


# ── the assisted clause in retry.py ───────────────────────────────────────────


def test_heavy_assistance_keeps_the_offer_open_after_understood():
    node = _graded(_node(), "understood")
    assert retry_model.offer(node).reason == retry_model.MET

    node.tutor_state.hints_used = 2
    offer = retry_model.offer(node)
    assert offer.mechanism == retry_model.REASSESS
    assert offer.reason == retry_model.ASSISTED
    assert offer.available is True


def test_one_hint_is_not_heavy():
    node = _graded(_node(), "understood")
    node.tutor_state.hints_used = 1
    assert retry_model.offer(node).reason == retry_model.MET


def test_assistance_does_not_demote_understanding():
    """§6.5 — offer, never demote. This is the assertion that keeps the Tutor out
    of the evidence model."""
    from backend.learning.graph import understanding_of
    from backend.learning import progress as progress_model

    graph = LearningGraph(repo_url="r", goal={})
    node = graph.add_node(_graded(_node(), "understood"))
    node.lesson_brief = {**node.lesson_brief, "priority": "required"}
    graph.current_node_id = node.id

    before_state = understanding_of(node)
    before_summary = progress_model.summary(graph)

    node.tutor_state.hints_used = 3

    assert understanding_of(node) == before_state == "understood"
    assert progress_model.summary(graph) == before_summary
    assert graph.is_complete() is True


def test_the_assisted_offer_terminates_when_budget_runs_out():
    node = _graded(_node(), "understood")
    node.tutor_state.hints_used = 3
    node.gap_state.reassessments = REASSESSMENT_CAP
    assert retry_model.offer(node).reason == retry_model.MET


def test_a_fresh_question_clears_the_ladder_so_the_offer_ends():
    """Taking the offer resets the counters, so an unassisted answer reports MET."""
    node = _graded(_node(), "understood")
    node.tutor_state.hints_used = 3
    assert retry_model.offer(node).reason == retry_model.ASSISTED

    node.tutor_state.new_question()
    assert retry_model.offer(node).reason == retry_model.MET


# ── the ladder ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("used,left,can_hint", [(0, 3, True), (1, 2, True),
                                                (2, 1, True), (3, 0, False)])
def test_the_ladder_reports_what_is_left(used, left, can_hint):
    node = _node()
    node.tutor_state.hints_used = used
    mode = mode_for(node)
    assert mode.hints_left == left
    assert mode.can_hint is can_hint


def test_reveal_is_available_from_rung_zero():
    """The ladder bounds hints, not honesty (§6.3)."""
    node = _node()
    assert mode_for(node).can_reveal is True
    node.tutor_state.hints_used = HINT_LADDER_MAX
    assert mode_for(node).can_hint is False
    assert mode_for(node).can_reveal is True


def test_reveal_is_not_offered_twice():
    node = _node()
    node.tutor_state.revealed = True
    assert mode_for(node).can_reveal is False


def test_new_question_clears_the_ladder_but_keeps_the_stop_turn_count():
    node = _node()
    node.tutor_state.hints_used = 3
    node.tutor_state.revealed = True
    node.tutor_state.turns = 7

    node.tutor_state.new_question()

    assert node.tutor_state.hints_used == 0
    assert node.tutor_state.revealed is False
    assert node.tutor_state.turns == 7, "dwelling is about the stop, not the question"


def test_the_wire_shape_carries_every_decision_the_client_renders():
    wire = mode_for(_node()).to_wire()
    assert set(wire) == {
        "mode", "reason", "question", "question_source",
        "hints_used", "hints_left", "revealed", "can_hint", "can_reveal",
    }
