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
    localize,
    process_answer,
    start_session,
)
from backend.agents.goal.agent import _synthesize_goal

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
ANS_BACKGROUND = "Python, Flask, some Java"

VALID_GOAL_JSON = {
    "primary_goal": "understand the request lifecycle",
    "goal_type": "understand_system",
    "focus_area": "HTTP session and adapters",
    "experience_level": "intermediate",
    "depth": "deep",
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
    # Options are keyed by locale now; every locale offers the same four.
    assert CORE_QUESTIONS[0].options is not None
    assert len(localize(CORE_QUESTIONS[0], "en").options) == 4
    assert len(localize(CORE_QUESTIONS[0], "he").options) == 4


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
    next_q, _ = process_answer(session, ANS_BACKGROUND, client=None)
    assert next_q is not None
    assert next_q.key == "focus_area"
    assert next_q.options is None  # free text


def test_debug_path_gets_error_description_followup():
    session = start_session(REPO_URL)
    process_answer(session, ANS_FAMILIARITY, client=None)
    process_answer(session, ANS_GOAL_DEBUG, client=None)
    process_answer(session, ANS_PRIMARY_GOAL, client=None)
    next_q, _ = process_answer(session, ANS_BACKGROUND, client=None)
    assert next_q is not None
    assert next_q.key == "error_description"


def test_debug_path_gets_tried_so_far_after_error():
    session = start_session(REPO_URL)
    process_answer(session, ANS_FAMILIARITY, client=None)
    process_answer(session, ANS_GOAL_DEBUG, client=None)
    process_answer(session, ANS_PRIMARY_GOAL, client=None)
    process_answer(session, ANS_BACKGROUND, client=None)
    next_q, _ = process_answer(session, "ConnectionError on retry", client=None)
    assert next_q is not None
    assert next_q.key == "tried_so_far"


def test_contribute_path_gets_contribution_context_followup():
    session = start_session(REPO_URL)
    process_answer(session, ANS_FAMILIARITY, client=None)
    process_answer(session, ANS_GOAL_CONTRIBUTE, client=None)
    process_answer(session, ANS_PRIMARY_GOAL, client=None)
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
        (CORE_QUESTIONS[3].text, ANS_BACKGROUND),
        (FOLLOWUP_QUESTIONS["understand_system"][0].text, "session handling"),
    ]
    result = _synthesize_goal(REPO_URL, qa_pairs, client=mock_client)
    assert result.primary_goal == "understand the request lifecycle"
    assert result.goal_type == "understand_system"
    assert result.target_repo == REPO_URL


def test_synthesize_goal_invalid_json():
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="not valid json")]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with pytest.raises(ValueError, match="synthesis_failed"):
        _synthesize_goal(REPO_URL, [("Q", "A")], client=mock_client)


# ── GoalOutput validation ─────────────────────────────────────────────────────

def test_goal_type_validation_rejects_invalid_value():
    with pytest.raises(ValidationError):
        GoalOutput(**{**VALID_GOAL_JSON, "goal_type": "read_documentation"})


def test_goal_type_accepts_all_valid_values():
    for valid_type in (
        "understand_system",
        "understand_component",
        "understand_architecture",
        "contribute_code",
        "improve_existing_system",
        "debug_issue",
    ):
        obj = GoalOutput(**{**VALID_GOAL_JSON, "goal_type": valid_type})
        assert obj.goal_type == valid_type
