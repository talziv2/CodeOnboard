"""The re-assessment agent's multiple-choice pipeline (D10, revised 2026-09-03).

A re-assessment is a NEW question about the objective, and it MAY now carry four
options. Those options go through the same form gate, drift gate and shuffle as
the first-attempt lesson's `choices` — plus, here, one regeneration and a
soundness check so a retry that ships options always has exactly one correct one.
Nothing here gives the agent a stored answer — `ReassessmentPrompt` still has no
`reveal` / `expected_answer` field, and the pick is graded against the objective.

No real model: `client.messages.create` is stubbed. `reassess()` makes one call
for the question, then a drift-gate call, then (for a choice form with options) a
soundness call — and repeats all three once if either gate rejects.
"""
import json
from unittest.mock import MagicMock

from backend.agents.teaching.reassess import ReassessmentPrompt, reassess
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.pipeline.state import OnboardState


FOUR = [
    "It owns the connection pool, cookie jar and defaults",
    "It owns the cookie jar it carries across calls",
    "It owns nothing — a thin wrapper with no state",
    "It owns retry and redirect policy for every call",
]
VERDICTS = {
    FOUR[0]: "correct",
    FOUR[1]: "partial",
    FOUR[2]: "wrong",
    FOUR[3]: "wrong",
}


def _q(question="on topic", *, choices=FOUR, verdicts=VERDICTS, probes="p") -> str:
    """A generation payload with a clean options + verdict map by default."""
    return json.dumps({
        "question": question, "probes": probes,
        "choices": choices, "choice_verdicts": verdicts,
    })


def _node(kind: str | None = None) -> LearningNode:
    brief = {"objective": "Explain what a Session owns and what it delegates."}
    if kind:
        brief["kind"] = kind
    return LearningNode(
        title="Session ownership",
        code_anchor=CodeAnchor(file="requests/sessions.py", line_start=1, line_end=40),
        concept_tags=["session"],
        lesson_brief=brief,
    )


def _state_and_node(kind: str | None = None):
    state = OnboardState(repo_url="https://github.com/psf/requests")
    graph = LearningGraph(repo_url="https://github.com/psf/requests", goal={})
    node = graph.add_node(_node(kind))
    graph.set_current(node.id)
    state.graph = graph
    return state, node


def _client(*texts: str) -> MagicMock:
    client = MagicMock()
    client.messages.create.side_effect = [
        MagicMock(content=[MagicMock(text=t)]) for t in texts
    ]
    return client


_QUESTION = _q("At a fresh call site, what must the Session still own?",
               probes="the ownership boundary")


def test_a_choice_form_reassessment_keeps_a_sound_option_set():
    # question, then ALIGNED, then SOUND → options kept, with their verdict map.
    state, node = _state_and_node()
    prompt = reassess(state, node, "class Session: ...", client=_client(_QUESTION, "ALIGNED", "SOUND"))
    assert prompt is not None
    assert set(prompt.choices) == set(FOUR)
    assert len(prompt.choices) == 4
    assert prompt.choice_verdicts == VERDICTS


def test_a_drifted_question_is_regenerated_once_then_kept():
    # First drifts; the regenerated one is aligned and sound.
    state, node = _state_and_node()
    client = _client(_QUESTION, "DRIFTED", _q("on-objective now", probes="the boundary"), "ALIGNED", "SOUND")
    prompt = reassess(state, node, "class Session: ...", client=client)
    assert prompt is not None
    assert prompt.question == "on-objective now"
    assert set(prompt.choices) == set(FOUR)


def test_an_unsound_option_set_is_regenerated_once_then_kept():
    # First question is on-topic but its options have no single correct answer;
    # the regenerated set is sound.
    state, node = _state_and_node()
    client = _client(_QUESTION, "ALIGNED", "UNSOUND", _q("still on topic"), "ALIGNED", "SOUND")
    prompt = reassess(state, node, "class Session: ...", client=client)
    assert prompt is not None
    assert set(prompt.choices) == set(FOUR)
    assert not state.errors


def test_options_are_dropped_when_no_sound_set_can_be_built():
    state, node = _state_and_node()
    client = _client(_QUESTION, "ALIGNED", "UNSOUND", _q("on topic"), "ALIGNED", "UNSOUND")
    prompt = reassess(state, node, "class Session: ...", client=client)
    assert prompt is not None
    assert prompt.question == "on topic"
    assert prompt.choices == []
    assert any("no single" in e or "drifted" in e for e in state.errors)


def test_options_are_dropped_when_the_verdict_map_is_malformed():
    # A verdict map that is not one-correct/one-partial/two-wrong makes the set
    # unacceptable → regenerate once → still malformed → options dropped, text kept.
    state, node = _state_and_node()
    bad = _q("on topic", verdicts={c: "correct" for c in FOUR})
    bad2 = _q("still on topic", verdicts={c: "correct" for c in FOUR})
    client = _client(bad, "ALIGNED", bad2, "ALIGNED")
    prompt = reassess(state, node, "class Session: ...", client=client)
    assert prompt is not None
    assert prompt.choices == []
    assert prompt.choice_verdicts == {}
    assert any("multiple-choice dropped" in e for e in state.errors)


def test_a_question_that_still_drifts_after_the_retry_keeps_text_drops_options():
    state, node = _state_and_node()
    client = _client(_QUESTION, "DRIFTED", _q("still off"), "DRIFTED")
    prompt = reassess(state, node, "class Session: ...", client=client)
    assert prompt is not None
    assert prompt.question == "still off"
    assert prompt.choices == []
    assert any("drifted" in e for e in state.errors)


def test_a_non_choice_form_reassessment_never_ships_options():
    # `risk` → the `critique` form. The form gate empties `choices` regardless of
    # the model's output; the soundness check never runs (no options to check).
    state, node = _state_and_node(kind="risk")
    prompt = reassess(state, node, "class Session: ...", client=_client(_QUESTION, "ALIGNED"))
    assert prompt is not None
    assert prompt.choices == []


def test_options_are_shuffled_but_stable_for_one_reassessment():
    state, node = _state_and_node()
    opts = ["a one", "b two", "c three", "d four"]
    verdicts = {"a one": "correct", "b two": "partial", "c three": "wrong", "d four": "wrong"}
    ordered = _q("q", choices=opts, verdicts=verdicts)
    first = reassess(state, node, "src", client=_client(ordered, "ALIGNED", "SOUND"))
    second = reassess(state, node, "src", client=_client(ordered, "ALIGNED", "SOUND"))
    assert first.choices == second.choices
    node.gap_state.reassessments += 1
    third = reassess(state, node, "src", client=_client(ordered, "ALIGNED", "SOUND"))
    assert set(third.choices) == set(first.choices)


def test_reassessment_prompt_still_has_no_answer_field():
    # The part of D10 that stops a memory check is intact: no reveal, no
    # expected_answer, no takeaway.
    fields = set(ReassessmentPrompt.model_fields)
    assert "reveal" not in fields
    assert "expected_answer" not in fields
    assert "takeaway" not in fields
