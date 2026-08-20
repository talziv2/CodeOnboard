"""
Pytest tests for B4 — lesson forms by kind, the setup/reveal split, why-now,
takeaway and ownership framing.
Run with: uv run pytest tests/test_teaching_forms.py -v

What must hold: the question's FORM is derived from the unit's kind by our code
and not reported by the model; an unmapped kind falls back to the original
well-tuned form rather than to a gap; a lesson's two halves stay separate so the
developer can answer before the explanation appears; `walkthrough` is still
assembled so every pre-B6 client renders exactly what it renders today; and a
lesson cached before B4 is neither re-parsed into nonsense nor regenerated.

No network: scripted fake client.
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from backend.agents.teaching import run
from backend.agents.teaching.agent import (
    _SYSTEM_PROMPT,
    _build_prior_context,
    _build_user_content,
    _parse_output,
    _previous_unit,
    _unblocks,
    lesson_form,
)
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.pipeline.state import OnboardState

from tests.test_teaching_agent import (
    FAKE_GOAL,
    FAKE_LESSON_OUTPUT,
    FAKE_REPO_PATH,
    FAKE_REPO_URL,
    FAKE_SOURCE,
    _make_mock_client,
    _make_node,
    _make_state_with_current_node,
)


def _node_of_kind(kind: str, tags: list[str] | None = None) -> LearningNode:
    return LearningNode(
        title=f"A {kind} unit",
        code_anchor=CodeAnchor(file="requests/auth.py", line_start=1, line_end=5),
        concept_tags=tags if tags is not None else [kind],
        lesson_brief={"objective": "Explain the thing", "kind": kind},
    )


# ── the form follows from the kind ────────────────────────────────────────────

@pytest.mark.parametrize("kind,form", [
    ("architecture", "compare"),
    ("flow", "predict-next"),
    ("component", "predict-then-reveal"),
    ("risk", "critique"),
    ("extension_point", "locate"),
    ("synthesis", "explain-back"),
    ("test_coverage", "predict-then-reveal"),
])
def test_the_form_follows_from_the_kind(kind, form):
    assert lesson_form(_node_of_kind(kind)) == form


def test_a_journey_takes_at_least_four_distinct_forms():
    # "Done when" #11. These five kinds appeared together in the real
    # sanity-matrix journeys, so the mix is not hypothetical.
    forms = {
        lesson_form(_node_of_kind(k))
        for k in ("architecture", "flow", "component", "risk", "synthesis")
    }
    assert len(forms) >= 4


def test_an_unmapped_kind_falls_back_to_the_original_form():
    # LR5: today's well-tuned form is the fallback, never a gap.
    assert lesson_form(_node_of_kind("something_new")) == "predict-then-reveal"


def test_a_pre_b3_node_gets_its_form_from_concept_tags():
    # Graphs planned before `kind` existed carry only tags — and a domain tag
    # may sit ahead of the canonical one.
    node = LearningNode(
        title="Old node",
        code_anchor=CodeAnchor(file="a.py", line_start=1, line_end=2),
        concept_tags=["auth", "risk"],
        lesson_brief={"why": "x", "understand": "y"},
    )
    assert lesson_form(node) == "critique"


def test_only_the_chosen_form_is_shown_to_the_model():
    # A menu of six invites blending them.
    content = _build_user_content(
        FAKE_GOAL, _node_of_kind("risk"), "src", "no prior context", []
    )
    assert "PROMPT FORM" in content
    assert "PLAUSIBLE BUT FLAWED CHANGE" in content
    assert "DELINEATE" not in content


@patch("backend.agents.teaching.agent._read_source_lines", return_value=FAKE_SOURCE)
def test_the_form_is_set_by_our_code_not_by_the_model(mock_read):
    # The model reports the old form; the unit is a flow. Ours wins — that is
    # what makes "the form follows from the kind" a property of the system
    # rather than an instruction the model may drift from.
    state, node = _make_state_with_current_node()
    node.lesson_brief = {"objective": "Trace it", "kind": "flow"}
    payload = dict(FAKE_LESSON_OUTPUT, prompt_kind="predict-then-reveal")
    run(state, client=_make_mock_client(json.dumps(payload)))
    assert state.current_lesson["prompt_kind"] == "predict-next"


# ── the setup / reveal split ──────────────────────────────────────────────────

_SPLIT = {
    "why_now": "You just saw where auth is attached; this is what attaches it.",
    "setup": "Here is HTTPBasicAuth. Look at what __call__ receives.",
    "prompt": "What do you think __call__ returns?",
    "reveal": "It mutates the PreparedRequest and returns it.",
    "takeaway": "Auth is a callable that edits the request in place.",
    "ownership": "Hold the contract yourself; delegate the header encoding.",
    "expected_answer": "The mutated PreparedRequest.",
}


def test_a_split_lesson_keeps_its_halves_separate():
    output = _parse_output(json.dumps(_SPLIT))
    assert output.setup and output.reveal and output.setup != output.reveal
    assert output.why_now and output.takeaway and output.ownership


def test_walkthrough_is_assembled_so_todays_ui_keeps_working():
    # B6 is what teaches the panel to withhold `reveal`. Until then every client
    # reads `walkthrough`, and must see the lesson it always saw, in order.
    output = _parse_output(json.dumps(_SPLIT))
    assert _SPLIT["setup"] in output.walkthrough
    assert _SPLIT["reveal"] in output.walkthrough
    assert output.walkthrough.index(_SPLIT["setup"]) < output.walkthrough.index(
        _SPLIT["reveal"]
    )


def test_a_model_supplied_walkthrough_is_not_overwritten():
    payload = dict(_SPLIT, walkthrough="the model wrote this itself")
    assert _parse_output(json.dumps(payload)).walkthrough == "the model wrote this itself"


def test_a_lesson_with_neither_body_is_rejected():
    payload = {k: v for k, v in _SPLIT.items() if k not in ("setup", "reveal")}
    with pytest.raises(Exception):
        _parse_output(json.dumps(payload))


def test_the_prompt_forbids_answering_the_prompt_in_setup():
    assert "NOTHING IN `setup` MAY ANSWER THE PROMPT" in _SYSTEM_PROMPT


def test_the_prompt_asks_for_ownership_framing():
    assert "hold THEMSELVES" in _SYSTEM_PROMPT
    assert "delegate to an AI assistant" in _SYSTEM_PROMPT


def test_the_prompt_tells_a_flow_to_trace_its_anchors_in_order():
    assert "IN THE ORDER THE ANCHORS" in _SYSTEM_PROMPT
    assert "describes only the first anchor has failed" in _SYSTEM_PROMPT


# ── backwards compatibility ───────────────────────────────────────────────────

def test_a_pre_b4_lesson_still_parses_and_renders_as_today():
    old = {
        "walkthrough": "the whole lesson, one block",
        "prompt": "what does it return?",
        "expected_answer": "the request",
        "prompt_kind": "predict-then-reveal",
    }
    output = _parse_output(json.dumps(old))
    assert output.walkthrough == "the whole lesson, one block"
    assert output.setup == "" and output.reveal == ""


@patch("backend.agents.teaching.agent._read_source_lines", return_value=FAKE_SOURCE)
def test_a_cached_pre_b4_lesson_is_never_regenerated(mock_read):
    # No migration, no invalidation (§12).
    state, node = _make_state_with_current_node()
    node.cached_lesson = {"walkthrough": "old", "prompt": "q", "expected_answer": "a"}
    client = _make_mock_client(json.dumps(_SPLIT))
    run(state, client=client)
    assert state.current_lesson["walkthrough"] == "old"
    client.messages.create.assert_not_called()


# ── why now, and continuity as claims (resolving LQ4) ─────────────────────────

def test_the_previous_units_claim_is_what_why_now_is_written_from():
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    first = graph.add_node(LearningNode(
        title="Session basics",
        code_anchor=CodeAnchor(file="a.py", line_start=1, line_end=2),
        lesson_brief={"objective": "Explain what Session owns"},
    ))
    second = graph.add_node(_make_node())
    graph.add_edge(first.id, second.id, kind="sequence")

    assert _previous_unit(graph, second.id) is first
    content = _build_user_content(
        FAKE_GOAL, second, "src", "no prior context", [], previous=first
    )
    assert "Explain what Session owns" in content
    assert "just finished" in content


def test_a_warm_up_is_told_what_it_unblocks_not_what_preceded_it():
    """S0's finding. A warm-up inserted for an auth misconception opened "Now that
    you know how to use Session safely with context managers…" — the model
    faithfully following an instruction that is false for a remediation."""
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    earlier = graph.add_node(LearningNode(
        title="Use Session as a context manager",
        code_anchor=CodeAnchor(file="a.py", line_start=1, line_end=2),
        lesson_brief={"objective": "Explain why a Session should be closed"},
    ))
    stuck_on = graph.add_node(LearningNode(
        title="Write a custom auth handler",
        code_anchor=CodeAnchor(file="b.py", line_start=1, line_end=2),
        lesson_brief={"objective": "Explain how prepare_auth dispatches a callable"},
    ))
    graph.add_edge(earlier.id, stuck_on.id, kind="sequence")

    warm_up = LearningNode(
        title="Understand the callable protocol",
        code_anchor=CodeAnchor(file="b.py", line_start=10, line_end=20),
        lesson_brief={"objective": "Explain what makes an object callable"},
    )
    graph.insert_before(stuck_on.id, warm_up, kind="prerequisite")

    # Read off the edge, not off position: the warm-up is ALSO the structural
    # predecessor of the stop it unblocks, so position cannot tell them apart.
    assert _unblocks(graph, warm_up.id) is stuck_on
    assert _previous_unit(graph, warm_up.id) is earlier

    content = _build_user_content(
        FAKE_GOAL, warm_up, "src", "no prior context", [],
        previous=earlier, unblocks=stuck_on,
    )
    assert "WARM-UP" in content
    assert "Write a custom auth handler" in content
    assert "Explain how prepare_auth dispatches a callable" in content
    # And NOT the predecessor's framing, which is the whole bug.
    assert "just finished" not in content
    assert "Use Session as a context manager" not in content


def test_an_ordinary_unit_is_unaffected_by_the_warm_up_branch():
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    first = graph.add_node(LearningNode(
        title="Session basics",
        code_anchor=CodeAnchor(file="a.py", line_start=1, line_end=2),
        lesson_brief={"objective": "Explain what Session owns"},
    ))
    second = graph.add_node(_make_node())
    graph.add_edge(first.id, second.id, kind="sequence")

    assert _unblocks(graph, second.id) is None
    content = _build_user_content(
        FAKE_GOAL, second, "src", "no prior context", [], previous=first
    )
    assert "just finished" in content
    assert "WARM-UP" not in content


def test_the_first_unit_has_no_previous_claim_to_lean_on():
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    only = graph.add_node(_make_node())
    assert _previous_unit(graph, only.id) is None
    content = _build_user_content(FAKE_GOAL, only, "src", "no prior", [], previous=None)
    assert "first unit of the path" in content


def test_prior_units_are_carried_as_claims_not_just_titles():
    # Same tokens, real continuity: "they can already explain X" is something to
    # build on; "they saw a node called X" is not.
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    done = graph.add_node(LearningNode(
        title="Session basics",
        code_anchor=CodeAnchor(file="a.py", line_start=1, line_end=2),
        lesson_brief={"objective": "Explain what Session owns"},
    ))
    done.understanding_state = "understood"
    current = graph.add_node(_make_node())
    context = _build_prior_context(graph, current.id)
    assert "they can now: Explain what Session owns" in context


# ── the AI-critique form (§7.4) ───────────────────────────────────────────────

def _critique_brief() -> str:
    return _build_user_content(
        FAKE_GOAL, _node_of_kind("risk"), "src", "no prior context", []
    )


def test_a_risk_unit_asks_the_learner_to_critique_a_change():
    assert lesson_form(_node_of_kind("risk")) == "critique"


def test_the_critique_brief_demands_a_repository_specific_flaw():
    # The whole point: a flaw a competent stranger could catch is not a
    # supervision exercise, it is code-review trivia.
    brief = _critique_brief()
    assert "REPOSITORY-SPECIFIC" in brief
    assert "invariant" in brief and "contract" in brief
    assert "caught by a linter" in brief


def test_the_critique_brief_rules_out_generic_review_findings():
    brief = _critique_brief()
    for banned in ("style", "naming", "typo", "formatting", "unused import"):
        assert banned in brief, f"the brief should exclude {banned} explicitly"


def test_the_critique_brief_requires_the_change_to_look_reasonable():
    # A change that is obviously wrong teaches nothing — the exercise is
    # supervision of plausible work, which is what an assistant produces.
    assert "MUST LOOK REASONABLE" in _critique_brief()


def test_the_critique_brief_bounds_it_to_what_has_been_taught():
    brief = _critique_brief()
    assert "ANSWERABLE FROM WHAT THEY HAVE BEEN TAUGHT" in brief
    assert "already understood" in brief


def test_the_critique_brief_ties_the_answer_back_to_the_objective():
    brief = _critique_brief()
    assert "objective's claim in applied form" in brief


def test_a_risk_setup_must_not_announce_the_failure():
    # Otherwise the setup answers its own prompt and the critique is free.
    assert "Do NOT announce that it is violated" in _SYSTEM_PROMPT


def test_the_critique_form_is_one_dict_entry_away_from_reverting():
    # Narrow and reversible by construction: `blast-radius` stays reachable and
    # correct, so restoring it is a single mapping change.
    from backend.agents.teaching.agent import _FORM_BRIEF

    assert "blast-radius" in _FORM_BRIEF
    assert "critique" in _FORM_BRIEF


def test_only_risk_uses_the_critique_form_for_now():
    # LR5: a form that has to INVENT a flaw is the hardest generation task here,
    # so it is deliberately confined to one kind until seen on real repos.
    using = [k for k in ("architecture", "flow", "component", "extension_point",
                         "synthesis", "test_coverage", "risk")
             if lesson_form(_node_of_kind(k)) == "critique"]
    assert using == ["risk"]
