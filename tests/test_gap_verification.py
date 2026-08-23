"""M6 — verification: the only way a gap ever closes.

gap-model.md M6. Three invariants, and every test here exists to defend one:

  1. A gap reaches `verified` HERE and nowhere else (§18.16.2).
  2. **Silence never closes a gap** — §18.7 calls this "the single most important
     rule in §18". An answer correct about A and silent about B closes A only.
  3. The caps stop the system PROPOSING without ever closing anything. Reaching
     one writes neither `verified` nor `waived`.

Run with: uv run pytest tests/test_gap_verification.py -v
"""
import json
from unittest.mock import MagicMock

import pytest

from tests.conftest import TEST_USER_ID

from backend.agents.grader import verification
from backend.agents.teaching import verify as teaching_verify
from backend.learning import store as learning_store
from backend.learning.adaptation import decide_all
from backend.learning.gaps import (
    REMEDIATION_ROUND_CAP,
    VERIFICATION_ATTEMPT_CAP,
    Gap,
    GapState,
)
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.pipeline.state import OnboardState


REPO = "https://github.com/psf/requests"
GOAL = {"primary_goal": "x", "goal_type": "understand_component"}

CLAIM_A = "child path_cost and depth are filled in later by the search algorithm"
CLAIM_B = "solution() returns both the states and the actions"
SOURCE = "class Node:\n    def expand(self, problem): ..."


def _node() -> LearningNode:
    node = LearningNode(
        title="Understand Node as the universal search tree unit",
        code_anchor=CodeAnchor(file="search.py", line_start=68, line_end=130),
        concept_tags=["component"],
        lesson_brief={"objective": "Explain what a Node holds"},
    )
    node.cached_lesson = {"prompt": "What does expand() build?", "setup": "…"}
    return node


def _state(node: LearningNode) -> OnboardState:
    graph = LearningGraph(repo_url=REPO, goal=GOAL)
    graph.add_node(node)
    graph.set_current(node.id)
    state = OnboardState(repo_url=REPO, goal=GOAL)
    state.graph = graph
    return state


def _two_gaps(node: LearningNode) -> tuple[Gap, Gap]:
    a = Gap.create("wrong_model", CLAIM_A, objective_part="what a Node holds")
    b = Gap.create("wrong_model", CLAIM_B, objective_part="what solution() returns")
    node.gap_state.gaps.extend([a, b])
    return a, b


def _client(payload: dict) -> MagicMock:
    message = MagicMock()
    message.content = [MagicMock(text=json.dumps(payload))]
    client = MagicMock()
    client.messages.create.return_value = message
    return client


def _sent(client: MagicMock) -> str:
    return client.messages.create.call_args.kwargs["messages"][0]["content"]


def _pend(node: LearningNode, question: str, targets: list[str]) -> None:
    node.gap_state.pending_verification = {
        "question": question, "targets": targets, "at": "2026-08-17T00:00:00+00:00",
    }


# ── generating the question ──────────────────────────────────────────────────


def test_a_verification_prompt_carries_no_answer_of_any_kind():
    """No `reveal`, no `expected_answer`. Excluded by design, not for brevity:
    shipping the answer beside the question is what made re-asking pointless."""
    fields = set(teaching_verify.VerificationPrompt.model_fields)
    assert fields == {"question", "targets"}


def test_the_question_targets_the_gaps_it_was_built_from():
    node = _node()
    state = _state(node)
    a, b = _two_gaps(node)
    prompt = teaching_verify.verify(
        state, node, [a], SOURCE, client=_client({"question": "q?"}),
    )
    assert prompt.targets == [a.id]
    assert b.id not in prompt.targets


def test_the_original_question_is_shown_so_it_can_be_avoided():
    node = _node()
    state = _state(node)
    a, _ = _two_gaps(node)
    client = _client({"question": "q?"})
    teaching_verify.verify(state, node, [a], SOURCE, client=client)
    sent = _sent(client)
    assert "DO NOT REUSE OR PARAPHRASE" in sent
    assert "What does expand() build?" in sent
    assert CLAIM_A in sent


def test_the_prompt_forbids_a_question_the_false_belief_could_pass():
    system = teaching_verify._SYSTEM
    flat = " ".join(system.split())
    assert "NEW APPLICATION OF THE SAME IDEA" in flat
    assert "must get the question WRONG" in flat
    # It must also not leak the correction into the question.
    assert "Do not state the correct model in the question" in flat


def test_verifying_nothing_is_refused_rather_than_invented():
    node = _node()
    state = _state(node)
    assert teaching_verify.verify(state, node, [], SOURCE, client=_client({})) is None
    assert any("no gap to verify" in e for e in state.errors)


def test_a_question_is_refused_without_source():
    """§4.1.2 applied here: with no source the model invents a scenario, and
    failing an imaginary question would record real evidence about it."""
    node = _node()
    state = _state(node)
    a, _ = _two_gaps(node)
    assert teaching_verify.verify(state, node, [a], "   ", client=_client({})) is None
    assert any("no source" in e for e in state.errors)


def test_a_generation_failure_returns_none_and_never_raises():
    node = _node()
    state = _state(node)
    a, _ = _two_gaps(node)
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("boom")
    assert teaching_verify.verify(state, node, [a], SOURCE, client=client) is None
    assert a.status == "open"  # a failed question costs the gap nothing


def test_store_puts_the_question_outside_cached_lesson():
    """A re-teach replaces `cached_lesson` wholesale; the two artifacts have
    different lifetimes (§18.7)."""
    node = _node()
    prompt = teaching_verify.VerificationPrompt(question="q?", targets=["g1"])
    teaching_verify.store(node, prompt)
    assert node.gap_state.pending_verification["question"] == "q?"
    assert "pending_verification" not in (node.cached_lesson or {})


# ── silence never closes a gap ───────────────────────────────────────────────


def test_an_answer_about_a_closes_a_only_and_leaves_b_open():
    """AC1's core, at the unit level. The rule §18.7 calls the most important
    in the whole design."""
    node = _node()
    state = _state(node)
    a, b = _two_gaps(node)
    _pend(node, "q?", [a.id, b.id])
    client = _client({
        "verdicts": [
            {"gap_id": a.id, "resolved": True, "rationale": "correct model shown"},
            {"gap_id": b.id, "resolved": False, "rationale": "not addressed"},
        ],
        "gaps": [], "rationale": "half there",
    })
    result = verification.grade_verification(state, node, "an answer", client=client)

    assert a.status == "verified"
    assert b.status == "open"
    assert result["resolved"] == [a.id]
    assert result["unresolved"] == [b.id]


def test_a_gap_the_model_never_mentions_stays_open():
    """The default is unresolved. Not by inference — by never having been said."""
    node = _node()
    state = _state(node)
    a, b = _two_gaps(node)
    _pend(node, "q?", [a.id, b.id])
    client = _client({
        "verdicts": [{"gap_id": a.id, "resolved": True, "rationale": "shown"}],
        "gaps": [], "rationale": "r",
    })
    verification.grade_verification(state, node, "an answer", client=client)
    assert a.status == "verified"
    assert b.status == "open"


def test_an_unknown_gap_id_cannot_close_anything():
    node = _node()
    state = _state(node)
    a, b = _two_gaps(node)
    _pend(node, "q?", [a.id])
    client = _client({
        "verdicts": [{"gap_id": "deadbeef", "resolved": True, "rationale": "x"}],
        "gaps": [], "rationale": "r",
    })
    verification.grade_verification(state, node, "an answer", client=client)
    assert a.status == "open" and b.status == "open"


def test_verified_records_the_attempt_that_closed_it():
    node = _node()
    node.attempts.append({"answer": "earlier"})
    state = _state(node)
    a, _ = _two_gaps(node)
    _pend(node, "q?", [a.id])
    verification.grade_verification(state, node, "ans", client=_client({
        "verdicts": [{"gap_id": a.id, "resolved": True, "rationale": "r"}],
        "gaps": [], "rationale": "r",
    }))
    assert a.resolved_by == 1
    assert a.closed_at


def test_grading_does_not_touch_understanding_state():
    """A verification answer is evidence about specific beliefs, not a
    re-assessment of the objective. M7 derives the node's state."""
    node = _node()
    node.understanding_state = "partial"
    state = _state(node)
    a, _ = _two_gaps(node)
    _pend(node, "q?", [a.id])
    verification.grade_verification(state, node, "ans", client=_client({
        "verdicts": [{"gap_id": a.id, "resolved": True, "rationale": "r"}],
        "gaps": [], "rationale": "r",
    }))
    assert node.understanding_state == "partial"


def test_the_grader_is_shown_every_open_gap_with_its_id():
    node = _node()
    state = _state(node)
    a, b = _two_gaps(node)
    _pend(node, "the question", [a.id])
    client = _client({"verdicts": [], "gaps": [], "rationale": "r"})
    verification.grade_verification(state, node, "ans", client=client)
    sent = _sent(client)
    for gap in (a, b):
        assert gap.id in sent and gap.claim in sent
    assert "the question" in sent


def test_the_prompt_states_that_no_evidence_is_not_evidence():
    flat = " ".join(verification._SYSTEM.split())
    assert "No evidence is not evidence" in flat
    assert "WHEN IT SIMPLY DOES NOT TOUCH THAT BELIEF AT ALL" in flat


# ── attempts, and what they are charged for ──────────────────────────────────


def test_an_unresolved_target_costs_an_attempt():
    node = _node()
    state = _state(node)
    a, _ = _two_gaps(node)
    _pend(node, "q?", [a.id])
    verification.grade_verification(state, node, "wrong", client=_client({
        "verdicts": [{"gap_id": a.id, "resolved": False, "rationale": "still wrong"}],
        "gaps": [], "rationale": "r",
    }))
    assert a.verification_attempts == 1
    assert a.status == "open"


def test_a_gap_the_question_did_not_target_is_not_charged():
    """Burning B's budget for a question about A would run the learner out of
    chances they were never given."""
    node = _node()
    state = _state(node)
    a, b = _two_gaps(node)
    _pend(node, "q?", [a.id])
    verification.grade_verification(state, node, "ans", client=_client({
        "verdicts": [{"gap_id": a.id, "resolved": False, "rationale": "x"},
                     {"gap_id": b.id, "resolved": False, "rationale": "silent"}],
        "gaps": [], "rationale": "r",
    }))
    assert a.verification_attempts == 1
    assert b.verification_attempts == 0


def test_a_resolved_gap_is_not_charged():
    node = _node()
    state = _state(node)
    a, _ = _two_gaps(node)
    _pend(node, "q?", [a.id])
    verification.grade_verification(state, node, "ans", client=_client({
        "verdicts": [{"gap_id": a.id, "resolved": True, "rationale": "r"}],
        "gaps": [], "rationale": "r",
    }))
    assert a.verification_attempts == 0


def test_a_grading_failure_charges_nothing_and_resolves_nothing():
    node = _node()
    state = _state(node)
    a, _ = _two_gaps(node)
    _pend(node, "q?", [a.id])
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("boom")
    result = verification.grade_verification(state, node, "ans", client=client)
    assert a.status == "open"
    assert a.verification_attempts == 0
    assert result["failed"] is True
    # The question survives, so the learner can answer again.
    assert node.gap_state.pending_verification is not None


def test_the_question_is_spent_once_graded():
    """Re-showing it after a wrong answer would be the 'Try again' defect that
    verification exists to replace."""
    node = _node()
    state = _state(node)
    a, _ = _two_gaps(node)
    _pend(node, "q?", [a.id])
    verification.grade_verification(state, node, "ans", client=_client({
        "verdicts": [{"gap_id": a.id, "resolved": False, "rationale": "r"}],
        "gaps": [], "rationale": "r",
    }))
    assert node.gap_state.pending_verification is None


def test_grading_without_a_pending_question_is_refused():
    node = _node()
    state = _state(node)
    _two_gaps(node)
    result = verification.grade_verification(state, node, "ans", client=_client({}))
    assert result["resolved"] == []
    assert any("no pending verification" in e for e in state.errors)


# ── a verification answer can reveal a new gap ───────────────────────────────


def test_a_new_false_belief_found_during_verification_is_recorded():
    node = _node()
    state = _state(node)
    a, _ = _two_gaps(node)
    _pend(node, "q?", [a.id])
    verification.grade_verification(state, node, "ans", client=_client({
        "verdicts": [{"gap_id": a.id, "resolved": True, "rationale": "r"}],
        "gaps": [{"kind": "wrong_model", "claim": "expand() sorts its children",
                  "objective_part": "what expand returns", "foundational": False}],
        "rationale": "r",
    }))
    claims = [g.claim for g in node.gaps]
    assert "expand() sorts its children" in claims
    assert a.status == "verified"


def test_an_unusable_new_gap_is_dropped_without_losing_the_verdicts():
    node = _node()
    state = _state(node)
    a, _ = _two_gaps(node)
    _pend(node, "q?", [a.id])
    verification.grade_verification(state, node, "ans", client=_client({
        "verdicts": [{"gap_id": a.id, "resolved": True, "rationale": "r"}],
        "gaps": [{"kind": "no_attempt", "claim": "nope"}],
        "rationale": "r",
    }))
    assert a.status == "verified"
    assert len(node.gaps) == 2  # nothing added


# ── the caps: stop proposing, never close ────────────────────────────────────


def test_reaching_the_verification_cap_writes_neither_verified_nor_waived():
    node = _node()
    state = _state(node)
    a, _ = _two_gaps(node)
    for _ in range(VERIFICATION_ATTEMPT_CAP):
        _pend(node, "q?", [a.id])
        verification.grade_verification(state, node, "wrong", client=_client({
            "verdicts": [{"gap_id": a.id, "resolved": False, "rationale": "r"}],
            "gaps": [], "rationale": "r",
        }))
    assert a.verification_attempts == VERIFICATION_ATTEMPT_CAP
    assert a.is_exhausted is True
    assert a.status == "open"


def test_an_exhausted_gap_still_blocks_and_is_still_reported():
    node = _node()
    a, _ = _two_gaps(node)
    a.verification_attempts = VERIFICATION_ATTEMPT_CAP
    plan = decide_all("confused", list(node.gaps))
    assert a.is_blocking is True
    assert a not in plan.active_set
    assert a in plan.deferred  # counted, not vanished


def test_an_exhausted_gap_leaves_the_active_set():
    node = _node()
    a, b = _two_gaps(node)
    a.verification_attempts = VERIFICATION_ATTEMPT_CAP
    plan = decide_all("confused", list(node.gaps))
    assert [g.id for g in plan.active_set] == [b.id]
    assert [g.id for g in plan.targets] == [b.id]


def test_when_every_gap_is_exhausted_the_system_stops_proposing():
    node = _node()
    a, b = _two_gaps(node)
    for gap in (a, b):
        gap.verification_attempts = VERIFICATION_ATTEMPT_CAP
    plan = decide_all("confused", list(node.gaps))
    assert plan.action == "none"
    assert plan.targets == ()
    # And nothing was closed to achieve that.
    assert a.status == "open" and b.status == "open"


def test_the_remediation_round_cap_stops_proposing_too():
    node = _node()
    _two_gaps(node)
    plan = decide_all("confused", list(node.gaps),
                      remediation_rounds=REMEDIATION_ROUND_CAP)
    assert plan.action == "none"
    assert all(g.status == "open" for g in node.gaps)


def test_below_the_round_cap_remediation_still_fires():
    node = _node()
    _two_gaps(node)
    plan = decide_all("confused", list(node.gaps),
                      remediation_rounds=REMEDIATION_ROUND_CAP - 1)
    assert plan.action == "reteach"


def test_a_verified_gap_is_never_offered_for_verification_again():
    node = _node()
    a, b = _two_gaps(node)
    a.mark_verified(0)
    plan = decide_all("confused", list(node.gaps))
    assert [g.id for g in plan.active_set] == [b.id]


# ── persistence ──────────────────────────────────────────────────────────────


def test_pending_verification_and_counters_round_trip(tmp_path):
    db = tmp_path / "sessions.db"
    node = _node()
    a, b = _two_gaps(node)
    a.mark_verified(1)
    b.record_failed_verification()
    node.gap_state.remediation_rounds = 2
    graph = LearningGraph(repo_url=REPO, goal=GOAL)
    graph.add_node(node)
    graph.set_current(node.id)
    teaching_verify.store(node, teaching_verify.VerificationPrompt(
        question="a fresh question", targets=[b.id],
    ))
    learning_store.save_graph(graph, db, user_id=TEST_USER_ID)

    reloaded = learning_store.load_graph(graph.session_id, TEST_USER_ID, db).nodes[node.id]
    assert reloaded.gap_state.pending_verification["question"] == "a fresh question"
    assert reloaded.gap_state.pending_verification["targets"] == [b.id]
    assert reloaded.gap_state.remediation_rounds == 2
    by_id = {g.id: g for g in reloaded.gaps}
    assert by_id[a.id].status == "verified" and by_id[a.id].resolved_by == 1
    assert by_id[b.id].verification_attempts == 1
    assert by_id[b.id].status == "open"


def test_a_pre_m6_gap_state_loads_with_no_pending_verification():
    """Every graph written by M1–M5 has no such key."""
    restored = GapState.from_dict({"gaps": [], "remediation_rounds": 1})
    assert restored.pending_verification is None
    assert restored.remediation_rounds == 1


def test_gap_state_is_truthy_when_only_a_question_is_outstanding():
    state = GapState(pending_verification={"question": "q", "targets": []})
    assert bool(state) is True
