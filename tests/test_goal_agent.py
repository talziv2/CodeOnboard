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
    start_session,
)
from backend.agents.goal.agent import _synthesize_goal
from backend.agents.goal.questions import CODE_DEPTH_OPTIONS

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
    session = start_session(REPO_URL)
    process_answer(session, ANS_FAMILIARITY, client=None)
    process_answer(session, ANS_GOAL_USE, client=None)
    assert session.goal_type == "understand_component"


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


def test_contribute_flow_5_questions_triggers_synthesis():
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
    next_q, goal = process_answer(session, "issue #123", client=mock_client)

    assert next_q is None
    assert goal is not None
    mock_client.messages.create.assert_called_once()


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
