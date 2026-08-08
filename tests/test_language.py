# Multilingual output — the parts that fail silently if they regress.
#
# The risk this covers is not "is the Hebrew correct" but "does choosing Hebrew
# break the machine-read contracts": the option→goal_type routing, the
# familiarity phrase the Teaching Agent calibrates on, and the enum values the
# frontend switches on.

import json
from unittest.mock import MagicMock

import pytest

from backend.agents.goal import (
    CORE_QUESTIONS,
    FOLLOWUP_QUESTIONS,
    GOAL_TYPE_MAP,
    localize,
    option_key,
    process_answer,
    start_session,
)
from backend.agents.goal.agent import _synthesize_goal
from backend.agents.language import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    language_instruction,
    language_of,
)

REPO_URL = "https://github.com/psf/requests"


# --- language resolution -----------------------------------------------------


def test_english_adds_no_directive():
    # The English path must send byte-identical prompts to what it always did,
    # so enabling multilingual support costs nothing on the default path.
    assert language_instruction({"language": "en"}) == ""
    assert language_instruction(None) == ""
    assert language_instruction({}) == ""


def test_hebrew_directive_pins_machine_read_values_to_english():
    directive = language_instruction({"language": "he"})
    assert "Hebrew" in directive
    assert "JSON key" in directive
    assert "concept tags" in directive


def test_unknown_language_falls_back_to_english():
    assert language_of({"language": "klingon"}) == DEFAULT_LANGUAGE
    assert language_instruction({"language": "klingon"}) == ""


# --- question localization ---------------------------------------------------


@pytest.mark.parametrize("locale", sorted(SUPPORTED_LANGUAGES))
def test_every_question_is_translated_in_every_locale(locale):
    followups = [q for group in FOLLOWUP_QUESTIONS.values() for q in group]
    for question in CORE_QUESTIONS + followups:
        assert locale in question.text, f"{question.key} missing {locale}"
        if question.options is not None:
            assert locale in question.options, f"{question.key} options missing {locale}"


def test_hebrew_questions_differ_from_english():
    # Guards against a locale silently falling through to the English text.
    for question in CORE_QUESTIONS:
        assert localize(question, "he").text != localize(question, "en").text


def test_unknown_locale_falls_back_to_english_text():
    assert localize(CORE_QUESTIONS[0], "klingon").text == localize(
        CORE_QUESTIONS[0], "en"
    ).text


# --- option routing ----------------------------------------------------------


def test_hebrew_goal_type_options_route_to_the_same_goal_types():
    english = localize(CORE_QUESTIONS[1], "en").options
    hebrew = localize(CORE_QUESTIONS[1], "he").options
    assert len(english) == len(hebrew)
    for en_label, he_label in zip(english, hebrew):
        assert GOAL_TYPE_MAP[option_key(he_label)] == GOAL_TYPE_MAP[option_key(en_label)]


def test_free_text_answers_pass_through_option_key_untouched():
    assert option_key("some answer I typed") == "some answer I typed"


def test_hebrew_interview_routes_followups_correctly():
    session = start_session(REPO_URL, language="he")
    familiarity = localize(CORE_QUESTIONS[0], "he").options[0]
    goal_type = localize(CORE_QUESTIONS[1], "he").options[4]  # "Debug an issue"

    process_answer(session, familiarity, client=None)
    process_answer(session, goal_type, client=None)

    assert session.goal_type == "debug_issue"
    # Answers are stored as stable English keys so downstream calibration works.
    assert session.answers["familiarity"] == "Starting fresh — never looked at it"


def test_hebrew_interview_asks_hebrew_followups():
    session = start_session(REPO_URL, language="he")
    process_answer(session, localize(CORE_QUESTIONS[0], "he").options[0], client=None)
    next_q, _ = process_answer(
        session, localize(CORE_QUESTIONS[1], "he").options[4], client=None
    )
    assert localize(next_q, session.language).text == localize(next_q, "he").text
    assert localize(next_q, "he").text != localize(next_q, "en").text


# --- synthesis ---------------------------------------------------------------


def _stub_client(payload: dict) -> MagicMock:
    client = MagicMock()
    message = MagicMock()
    message.content = [MagicMock(text=json.dumps(payload))]
    client.messages.create.return_value = message
    return client


_SYNTHESIZED = {
    "primary_goal": "להבין את מחזור החיים של בקשה",
    "goal_type": "understand_system",
    "focus_area": "ניתוב",
    "experience_level": "intermediate",
    "depth": "moderate",
    "target_repo": REPO_URL,
    "familiarity": "Starting fresh — never looked at it",
    "background": "Python",
}


def test_synthesis_stamps_the_language_on_the_goal():
    # The language must come from the request, not from whatever the model
    # decided to emit — it is a fact about the session, not a judgement call.
    client = _stub_client(_SYNTHESIZED)
    goal = _synthesize_goal(REPO_URL, [("Q", "A")], client=client, language="he")
    assert goal.language == "he"


def test_synthesis_sends_the_language_directive():
    client = _stub_client(_SYNTHESIZED)
    _synthesize_goal(REPO_URL, [("Q", "A")], client=client, language="he")
    system = client.messages.create.call_args.kwargs["system"]
    assert "OUTPUT LANGUAGE — Hebrew" in system


def test_english_synthesis_sends_the_bare_prompt():
    client = _stub_client({**_SYNTHESIZED, "primary_goal": "understand routing"})
    _synthesize_goal(REPO_URL, [("Q", "A")], client=client, language="en")
    system = client.messages.create.call_args.kwargs["system"]
    assert "OUTPUT LANGUAGE" not in system


def test_goal_defaults_to_english_when_unspecified():
    client = _stub_client(_SYNTHESIZED)
    goal = _synthesize_goal(REPO_URL, [("Q", "A")], client=client)
    assert goal.language == DEFAULT_LANGUAGE


# --- the agents that write what the user reads --------------------------------
#
# A lesson in English under a Hebrew UI is the failure mode worth guarding: the
# chrome looks translated while every word of substance is not.


def _hebrew_state():
    from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
    from backend.pipeline.state import OnboardState

    goal = {**_SYNTHESIZED, "language": "he"}
    state = OnboardState(repo_url=REPO_URL)
    state.repo_path = "data/repos/requests"
    state.goal = goal
    graph = LearningGraph(repo_url=REPO_URL, goal=goal)
    node = graph.add_node(
        LearningNode(
            title="Understand HTTPBasicAuth",
            code_anchor=CodeAnchor(file="requests/auth.py", line_start=72, line_end=100),
            concept_tags=["component"],
            lesson_brief={"why": "central auth abstraction", "understand": "how it signs"},
        )
    )
    graph.set_current(node.id)
    state.graph = graph
    return state, node


def test_teaching_agent_writes_the_lesson_in_the_session_language():
    from unittest.mock import patch

    from backend.agents.teaching import run as run_teaching

    state, _ = _hebrew_state()
    client = _stub_client(
        {
            "walkthrough": "…",
            "prompt": "…",
            "expected_answer": "…",
            "prompt_kind": "predict-then-reveal",
        }
    )
    with patch(
        "backend.agents.teaching.agent.retrieve_supporting_chunks", return_value=[]
    ), patch("backend.agents.teaching.agent._read_source_lines", return_value="code"):
        run_teaching(state, client=client)

    system = client.messages.create.call_args.kwargs["system"]
    assert "OUTPUT LANGUAGE — Hebrew" in system


def test_grader_writes_its_rationale_in_the_session_language():
    from backend.agents.grader import run as run_grader

    state, node = _hebrew_state()
    node.cached_lesson = {"prompt": "…", "expected_answer": "…"}
    client = _stub_client({"classification": "understood", "rationale": "…"})

    run_grader(state, "my answer", client=client)

    system = client.messages.create.call_args.kwargs["system"]
    assert "OUTPUT LANGUAGE — Hebrew" in system
    # The classification is machine-read and must survive untranslated.
    assert state.last_grade["classification"] == "understood"


def test_english_session_sends_no_directive_to_the_teaching_agent():
    from unittest.mock import patch

    from backend.agents.teaching import run as run_teaching

    state, _ = _hebrew_state()
    state.goal = {**state.goal, "language": "en"}
    state.graph.goal = state.goal
    client = _stub_client(
        {
            "walkthrough": "…",
            "prompt": "…",
            "expected_answer": "…",
            "prompt_kind": "predict-then-reveal",
        }
    )
    with patch(
        "backend.agents.teaching.agent.retrieve_supporting_chunks", return_value=[]
    ), patch("backend.agents.teaching.agent._read_source_lines", return_value="code"):
        run_teaching(state, client=client)

    assert "OUTPUT LANGUAGE" not in client.messages.create.call_args.kwargs["system"]


# --- HTTP surface -------------------------------------------------------------
#
# Neither /goal/start nor a non-final /goal/answer calls the LLM, so this walks
# the real interview over HTTP without a client or a key.


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    import backend.api as api

    api.sessions.clear()
    return TestClient(api.app)


def test_languages_endpoint_advertises_hebrew(client):
    body = client.get("/languages").json()
    assert body["default"] == "en"
    assert body["languages"]["he"] == "Hebrew"


def test_goal_start_returns_hebrew_questions(client):
    body = client.post(
        "/goal/start", json={"repo_url": REPO_URL, "language": "he"}
    ).json()
    assert body["question"]["text"] == localize(CORE_QUESTIONS[0], "he").text
    assert body["question"]["options"] == localize(CORE_QUESTIONS[0], "he").options


def test_goal_start_defaults_to_english(client):
    body = client.post("/goal/start", json={"repo_url": REPO_URL}).json()
    assert body["question"]["text"] == localize(CORE_QUESTIONS[0], "en").text


def test_unknown_language_does_not_400(client):
    res = client.post("/goal/start", json={"repo_url": REPO_URL, "language": "klingon"})
    assert res.status_code == 200
    assert res.json()["question"]["text"] == localize(CORE_QUESTIONS[0], "en").text


def test_hebrew_interview_stays_hebrew_across_answers(client):
    start = client.post(
        "/goal/start", json={"repo_url": REPO_URL, "language": "he"}
    ).json()
    session_id = start["session_id"]

    # Answer Q1 with the Hebrew label the UI would have sent back.
    answer = localize(CORE_QUESTIONS[0], "he").options[0]
    body = client.post(
        "/goal/answer", json={"session_id": session_id, "answer": answer}
    ).json()

    assert body["done"] is False
    assert body["question"]["text"] == localize(CORE_QUESTIONS[1], "he").text
    assert body["question"]["options"] == localize(CORE_QUESTIONS[1], "he").options
