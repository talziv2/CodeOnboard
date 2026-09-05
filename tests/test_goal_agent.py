import json
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from backend.agents.goal import (
    CORE_QUESTIONS,
    FOLLOWUP_QUESTIONS,
    GoalOutput,
    GoalSession,
    Question,
    process_answer,
    question_progress,
    start_session,
    step_back,
)
from backend.agents.goal.agent import _synthesize_goal
from backend.agents.goal.questions import (
    CODE_DEPTH_OPTIONS,
    CONTRIBUTION_SCOPE_MAP,
    CONTRIBUTION_SCOPE_OPTIONS,
)

REPO_URL = "https://github.com/psf/requests"

# Valid option strings
ANS_FAMILIARITY = "Starting fresh — never looked at it"
ANS_GOAL_UNDERSTAND = "Understand how it works (reading/learning)"
ANS_GOAL_DEBUG = "Debug an issue I'm hitting"
ANS_GOAL_CONTRIBUTE = "Contribute code / open a PR"
ANS_GOAL_USE = "Use it in my own project"
ANS_GOAL_ARCHITECTURE = "Understand the architecture (layers, boundaries, design)"
ANS_GOAL_IMPROVE = "Improve or extend the codebase safely"
ANS_PRIMARY_GOAL = "understand the request lifecycle"
ANS_CODE_DEPTH = (
    "I'll be working in here — the map, plus what I'd need to change things safely"
)
ANS_BACKGROUND = "Python, Flask, some Java"

VALID_GOAL_JSON = {
    "primary_goal": "understand the request lifecycle",
    "goal_type": "understand_system",
    "focus_area": "HTTP session and adapters",
    "target_repo": REPO_URL,
    "familiarity": "starting fresh",
    "background": "Python, Flask",
}


def make_mock_client(json_payload: dict) -> MagicMock:
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(json_payload))]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    return mock_client


# ── start_session ─────────────────────────────────────────────────────────────

def test_start_session():
    session = start_session(REPO_URL)
    assert isinstance(session, GoalSession)
    assert session.repo_url == REPO_URL
    assert session.answers == {}
    assert session.goal_type is None
    assert len(session.session_id) > 0


# ── Q1 — familiarity ──────────────────────────────────────────────────────────

def test_first_question_has_options():
    assert CORE_QUESTIONS[0].options is not None
    assert len(CORE_QUESTIONS[0].options) == 4


def test_q1_answer_returns_q2_with_options():
    session = start_session(REPO_URL)
    next_q, goal = process_answer(session, ANS_FAMILIARITY, client=None)
    assert isinstance(next_q, Question)
    assert next_q.options is not None
    assert goal is None


# ── Q2 — goal_type routing ────────────────────────────────────────────────────

def test_q2_understand_sets_goal_type():
    session = start_session(REPO_URL)
    process_answer(session, ANS_FAMILIARITY, client=None)
    process_answer(session, ANS_GOAL_UNDERSTAND, client=None)
    assert session.goal_type == "understand_system"


def test_q2_debug_sets_goal_type():
    session = start_session(REPO_URL)
    process_answer(session, ANS_FAMILIARITY, client=None)
    process_answer(session, ANS_GOAL_DEBUG, client=None)
    assert session.goal_type == "debug_issue"


def test_q2_contribute_sets_goal_type():
    session = start_session(REPO_URL)
    process_answer(session, ANS_FAMILIARITY, client=None)
    process_answer(session, ANS_GOAL_CONTRIBUTE, client=None)
    assert session.goal_type == "contribute_code"


def test_q2_use_sets_goal_type():
    # "Use it in my own project" routed to `understand_component` until
    # 2026-08-15, which optimised the investigation for internal components and
    # never required a caller-facing entry point (LQ5).
    session = start_session(REPO_URL)
    process_answer(session, ANS_FAMILIARITY, client=None)
    process_answer(session, ANS_GOAL_USE, client=None)
    assert session.goal_type == "use_library"


def test_q2_architecture_sets_goal_type():
    session = start_session(REPO_URL)
    process_answer(session, ANS_FAMILIARITY, client=None)
    process_answer(session, ANS_GOAL_ARCHITECTURE, client=None)
    assert session.goal_type == "understand_architecture"


def test_q2_improve_sets_goal_type():
    session = start_session(REPO_URL)
    process_answer(session, ANS_FAMILIARITY, client=None)
    process_answer(session, ANS_GOAL_IMPROVE, client=None)
    assert session.goal_type == "improve_existing_system"


def test_q2_invalid_option_raises():
    session = start_session(REPO_URL)
    process_answer(session, ANS_FAMILIARITY, client=None)
    with pytest.raises(ValueError, match="invalid_goal_type_option"):
        process_answer(session, "something random", client=None)


# ── Conditional follow-ups ────────────────────────────────────────────────────

def test_understand_path_gets_focus_area_followup():
    session = start_session(REPO_URL)
    process_answer(session, ANS_FAMILIARITY, client=None)
    process_answer(session, ANS_GOAL_UNDERSTAND, client=None)
    process_answer(session, ANS_PRIMARY_GOAL, client=None)
    process_answer(session, ANS_CODE_DEPTH, client=None)
    next_q, _ = process_answer(session, ANS_BACKGROUND, client=None)
    assert next_q is not None
    assert next_q.key == "focus_area"
    assert next_q.options is None  # free text


def test_debug_path_gets_error_description_followup():
    session = start_session(REPO_URL)
    process_answer(session, ANS_FAMILIARITY, client=None)
    process_answer(session, ANS_GOAL_DEBUG, client=None)
    process_answer(session, ANS_PRIMARY_GOAL, client=None)
    process_answer(session, ANS_CODE_DEPTH, client=None)
    next_q, _ = process_answer(session, ANS_BACKGROUND, client=None)
    assert next_q is not None
    assert next_q.key == "error_description"


def test_debug_path_gets_tried_so_far_after_error():
    session = start_session(REPO_URL)
    process_answer(session, ANS_FAMILIARITY, client=None)
    process_answer(session, ANS_GOAL_DEBUG, client=None)
    process_answer(session, ANS_PRIMARY_GOAL, client=None)
    process_answer(session, ANS_CODE_DEPTH, client=None)
    process_answer(session, ANS_BACKGROUND, client=None)
    next_q, _ = process_answer(session, "ConnectionError on retry", client=None)
    assert next_q is not None
    assert next_q.key == "tried_so_far"


def test_contribute_path_gets_contribution_context_followup():
    session = start_session(REPO_URL)
    process_answer(session, ANS_FAMILIARITY, client=None)
    process_answer(session, ANS_GOAL_CONTRIBUTE, client=None)
    process_answer(session, ANS_PRIMARY_GOAL, client=None)
    process_answer(session, ANS_CODE_DEPTH, client=None)
    next_q, _ = process_answer(session, ANS_BACKGROUND, client=None)
    assert next_q is not None
    assert next_q.key == "contribution_context"


# ── Full flows (synthesis triggered) ─────────────────────────────────────────

def test_understand_flow_5_questions_triggers_synthesis():
    session = start_session(REPO_URL)
    mock_client = make_mock_client(VALID_GOAL_JSON)

    process_answer(session, ANS_FAMILIARITY, client=None)
    process_answer(session, ANS_GOAL_UNDERSTAND, client=None)
    process_answer(session, ANS_PRIMARY_GOAL, client=None)
    process_answer(session, ANS_CODE_DEPTH, client=None)
    process_answer(session, ANS_BACKGROUND, client=None)
    next_q, goal = process_answer(session, "the session handling part", client=mock_client)

    assert next_q is None
    assert goal is not None
    assert isinstance(goal, GoalOutput)
    mock_client.messages.create.assert_called_once()


def test_debug_flow_6_questions_triggers_synthesis():
    session = start_session(REPO_URL)
    debug_goal_json = {
        **VALID_GOAL_JSON,
        "goal_type": "debug_issue",
        "error_description": "ConnectionError on retry",
        "tried_so_far": "checked adapters",
    }
    mock_client = make_mock_client(debug_goal_json)

    process_answer(session, ANS_FAMILIARITY, client=None)
    process_answer(session, ANS_GOAL_DEBUG, client=None)
    process_answer(session, ANS_PRIMARY_GOAL, client=None)
    process_answer(session, ANS_CODE_DEPTH, client=None)
    process_answer(session, ANS_BACKGROUND, client=None)
    process_answer(session, "ConnectionError on retry", client=None)
    next_q, goal = process_answer(session, "checked adapters", client=mock_client)

    assert next_q is None
    assert goal is not None
    mock_client.messages.create.assert_called_once()


def test_contribute_flow_7_questions_triggers_synthesis():
    """Five core questions, then the task and how large it is expected to be.

    The second follow-up arrived with the contribution journey: the task now
    reaches the INVESTIGATION rather than only the planner, so a vague answer
    costs a vague dossier — and the size is one line of context beside it.
    """
    session = start_session(REPO_URL)
    contribute_goal_json = {
        **VALID_GOAL_JSON,
        "goal_type": "contribute_code",
        "contribution_context": "issue #123",
    }
    mock_client = make_mock_client(contribute_goal_json)

    process_answer(session, ANS_FAMILIARITY, client=None)
    process_answer(session, ANS_GOAL_CONTRIBUTE, client=None)
    process_answer(session, ANS_PRIMARY_GOAL, client=None)
    process_answer(session, ANS_CODE_DEPTH, client=None)
    process_answer(session, ANS_BACKGROUND, client=None)
    next_q, goal = process_answer(session, "issue #123", client=None)
    assert next_q is not None and next_q.key == "contribution_scope"

    next_q, goal = process_answer(
        session, CONTRIBUTION_SCOPE_OPTIONS[0], client=mock_client,
    )

    assert next_q is None
    assert goal is not None
    # Ours, not the model's — set in Python from the option the learner picked.
    assert goal.contribution_scope == CONTRIBUTION_SCOPE_MAP[CONTRIBUTION_SCOPE_OPTIONS[0]]
    mock_client.messages.create.assert_called_once()


def test_an_invalid_contribution_scope_is_refused():
    session = start_session(REPO_URL)
    for answer in (ANS_FAMILIARITY, ANS_GOAL_CONTRIBUTE, ANS_PRIMARY_GOAL,
                   ANS_CODE_DEPTH, ANS_BACKGROUND, "issue #123"):
        process_answer(session, answer, client=None)
    with pytest.raises(ValueError, match="invalid_contribution_scope_option"):
        process_answer(session, "whatever I like", client=None)


# ── _synthesize_goal ──────────────────────────────────────────────────────────

def test_synthesize_goal_valid_json():
    mock_client = make_mock_client(VALID_GOAL_JSON)
    qa_pairs = [
        (CORE_QUESTIONS[0].text, ANS_FAMILIARITY),
        (CORE_QUESTIONS[1].text, ANS_GOAL_UNDERSTAND),
        (CORE_QUESTIONS[2].text, ANS_PRIMARY_GOAL),
        (CORE_QUESTIONS[3].text, ANS_CODE_DEPTH),
        (CORE_QUESTIONS[4].text, ANS_BACKGROUND),
        (FOLLOWUP_QUESTIONS["understand_system"][0].text, "session handling"),
    ]
    result = _synthesize_goal(REPO_URL, qa_pairs, client=mock_client, code_depth="working")
    assert result.primary_goal == "understand the request lifecycle"
    assert result.goal_type == "understand_system"
    assert result.target_repo == REPO_URL


def test_synthesize_goal_invalid_json():
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="not valid json")]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with pytest.raises(ValueError, match="synthesis_failed"):
        _synthesize_goal(REPO_URL, [("Q", "A")], client=mock_client, code_depth="map")


# ── GoalOutput validation ─────────────────────────────────────────────────────

# VALID_GOAL_JSON is what the MODEL returns, and the model is no longer asked
# for depth or code_depth — our code supplies both. Constructing a GoalOutput
# directly therefore has to add them.
COMPLETE_GOAL = {**VALID_GOAL_JSON, "code_depth": "working", "depth": "moderate"}


def test_goal_type_validation_rejects_invalid_value():
    with pytest.raises(ValidationError):
        GoalOutput(**{**COMPLETE_GOAL, "goal_type": "read_documentation"})


def test_goal_type_accepts_all_valid_values():
    for valid_type in (
        "understand_system",
        "understand_component",
        "understand_architecture",
        "contribute_code",
        "improve_existing_system",
        "debug_issue",
    ):
        obj = GoalOutput(**{**COMPLETE_GOAL, "goal_type": valid_type})
        assert obj.goal_type == valid_type


# ── code_depth (B2) ───────────────────────────────────────────────────────────

def test_code_depth_is_asked_with_outcome_shaped_options():
    q = next(q for q in CORE_QUESTIONS if q.key == "code_depth")
    assert q.options is not None and len(q.options) == 3
    # Phrased as outcomes, not as levels — "how deep?" invites everyone to
    # answer "deep".
    assert all(len(o.split()) > 4 for o in q.options)


def test_an_invalid_code_depth_option_is_rejected():
    session = start_session(REPO_URL)
    process_answer(session, ANS_FAMILIARITY, client=None)
    process_answer(session, ANS_GOAL_UNDERSTAND, client=None)
    process_answer(session, ANS_PRIMARY_GOAL, client=None)
    with pytest.raises(ValueError, match="invalid_code_depth_option"):
        process_answer(session, "very deep please", client=None)


@pytest.mark.parametrize(
    "answer,expected_code_depth,expected_depth",
    [
        (CODE_DEPTH_OPTIONS[0], "map", "overview"),
        (CODE_DEPTH_OPTIONS[1], "working", "moderate"),
        (CODE_DEPTH_OPTIONS[2], "implementation", "deep"),
    ],
)
def test_depth_is_derived_from_the_answer_not_invented(
    answer, expected_code_depth, expected_depth
):
    session = start_session(REPO_URL)
    mock_client = make_mock_client(VALID_GOAL_JSON)
    process_answer(session, ANS_FAMILIARITY, client=None)
    process_answer(session, ANS_GOAL_UNDERSTAND, client=None)
    process_answer(session, ANS_PRIMARY_GOAL, client=None)
    process_answer(session, answer, client=None)
    process_answer(session, ANS_BACKGROUND, client=None)
    _, goal = process_answer(session, "session handling", client=mock_client)

    assert goal.code_depth == expected_code_depth
    assert goal.depth == expected_depth


def test_a_model_that_volunteers_a_depth_does_not_get_to_keep_it():
    # The whole point of LD2: depth decided how much got taught, and was
    # invented by a model from answers that never mentioned it.
    session = start_session(REPO_URL)
    mock_client = make_mock_client(
        {**VALID_GOAL_JSON, "depth": "deep", "code_depth": "implementation"}
    )
    process_answer(session, ANS_FAMILIARITY, client=None)
    process_answer(session, ANS_GOAL_UNDERSTAND, client=None)
    process_answer(session, ANS_PRIMARY_GOAL, client=None)
    process_answer(session, CODE_DEPTH_OPTIONS[0], client=None)  # "give me the map"
    process_answer(session, ANS_BACKGROUND, client=None)
    _, goal = process_answer(session, "session handling", client=mock_client)

    assert goal.code_depth == "map"
    assert goal.depth == "overview"


def test_the_model_is_no_longer_asked_for_depth_or_experience_level():
    from backend.agents.goal.agent import _SYSTEM_PROMPT

    assert "experience_level" not in _SYSTEM_PROMPT
    assert "depth must be one of" not in _SYSTEM_PROMPT


# ── use_library (LQ5) ─────────────────────────────────────────────────────────

def test_the_use_option_reaches_the_interview_as_use_library():
    from backend.agents.goal.questions import GOAL_TYPE_MAP

    assert GOAL_TYPE_MAP["Use it in my own project"] == "use_library"


def test_use_library_has_a_follow_up_so_the_interview_does_not_crash():
    # `_get_question_sequence` looks the goal type up unguarded; a missing entry
    # is a KeyError in the middle of a user's interview.
    from backend.agents.goal.questions import FOLLOWUP_QUESTIONS

    assert FOLLOWUP_QUESTIONS["use_library"]
    # Keyed on focus_area so everything downstream that reads it keeps working.
    assert FOLLOWUP_QUESTIONS["use_library"][0].key == "focus_area"


def test_a_use_library_goal_is_accepted_and_carried():
    session = start_session(REPO_URL)
    mock_client = make_mock_client({**VALID_GOAL_JSON, "goal_type": "use_library"})
    process_answer(session, ANS_FAMILIARITY, client=None)
    process_answer(session, ANS_GOAL_USE, client=None)
    process_answer(session, ANS_PRIMARY_GOAL, client=None)
    process_answer(session, CODE_DEPTH_OPTIONS[1], client=None)
    process_answer(session, ANS_BACKGROUND, client=None)
    _, goal = process_answer(session, "send authenticated requests", client=mock_client)

    assert goal is not None
    assert goal.goal_type == "use_library"
    assert goal.focus_area


def test_the_synthesis_prompt_describes_use_library():
    from backend.agents.goal.agent import _SYSTEM_PROMPT

    assert "use_library" in _SYSTEM_PROMPT
    assert "USE this code" in _SYSTEM_PROMPT


# ── step_back (interview navigation) ──────────────────────────────────────────

def test_step_back_returns_the_question_and_what_was_answered():
    session = start_session(REPO_URL)
    process_answer(session, ANS_FAMILIARITY, client=None)

    stepped = step_back(session)

    assert stepped is not None
    question, previous = stepped
    assert question.key == "familiarity"
    assert previous == ANS_FAMILIARITY


def test_step_back_at_the_first_question_has_nothing_to_return():
    session = start_session(REPO_URL)
    assert step_back(session) is None


def test_step_back_un_answers_so_the_same_question_comes_round_again():
    session = start_session(REPO_URL)
    process_answer(session, ANS_FAMILIARITY, client=None)
    process_answer(session, ANS_GOAL_UNDERSTAND, client=None)

    step_back(session)
    # Re-answering Q2 must land on Q3, not skip ahead: the answer was replaced,
    # not appended.
    next_q, _ = process_answer(session, ANS_GOAL_UNDERSTAND, client=None)

    assert next_q is not None
    assert next_q.key == "primary_goal"
    assert len(session.answers) == 2


def test_position_and_total_move_back_with_the_step():
    session = start_session(REPO_URL)
    process_answer(session, ANS_FAMILIARITY, client=None)
    process_answer(session, ANS_GOAL_DEBUG, client=None)
    assert question_progress(session)[0] == 3

    step_back(session)

    index, total = question_progress(session)
    assert index == 2
    # goal_type is no longer known, so the total drops back to its lower bound.
    assert total == len(CORE_QUESTIONS) + 1


def test_going_back_past_q2_lets_a_different_goal_type_change_the_followups():
    # The bug this guards: stepping back over Q2 without clearing goal_type
    # leaves the old goal_type's follow-ups queued, so a user who switches from
    # debugging to contributing is still asked what error they are seeing.
    session = start_session(REPO_URL)
    process_answer(session, ANS_FAMILIARITY, client=None)
    process_answer(session, ANS_GOAL_DEBUG, client=None)
    assert session.goal_type == "debug_issue"

    step_back(session)
    assert session.goal_type is None

    process_answer(session, ANS_GOAL_CONTRIBUTE, client=None)
    process_answer(session, ANS_PRIMARY_GOAL, client=None)
    process_answer(session, ANS_CODE_DEPTH, client=None)
    next_q, _ = process_answer(session, ANS_BACKGROUND, client=None)

    assert next_q is not None
    assert next_q.key == "contribution_context"


def test_step_back_reaches_a_followup_not_just_the_core_questions():
    session = start_session(REPO_URL)
    process_answer(session, ANS_FAMILIARITY, client=None)
    process_answer(session, ANS_GOAL_DEBUG, client=None)
    process_answer(session, ANS_PRIMARY_GOAL, client=None)
    process_answer(session, ANS_CODE_DEPTH, client=None)
    process_answer(session, ANS_BACKGROUND, client=None)
    process_answer(session, "ConnectionError on retry", client=None)

    stepped = step_back(session)

    assert stepped is not None
    question, previous = stepped
    assert question.key == "error_description"
    assert previous == "ConnectionError on retry"


def test_stepping_all_the_way_back_empties_the_interview():
    session = start_session(REPO_URL)
    process_answer(session, ANS_FAMILIARITY, client=None)
    process_answer(session, ANS_GOAL_USE, client=None)
    process_answer(session, ANS_PRIMARY_GOAL, client=None)

    while step_back(session) is not None:
        pass

    assert session.answers == {}
    assert session.goal_type is None
    assert question_progress(session)[0] == 1
