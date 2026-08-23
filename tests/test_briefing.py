"""
Tests for the welcome briefing — the Briefing Agent and the endpoint that caches
its output on the session.
Run with: uv run pytest tests/test_briefing.py -v

No network: the Anthropic client is a MagicMock whose response text each test
sets. The grounding rules (no material → no briefing, an unresolvable citation
loses its path) are the reason most of these exist — they are the two places a
welcome paragraph could quietly become fiction.
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import TEST_USER_ID
from fastapi.testclient import TestClient

import backend.api as api
from backend.agents.briefing import build_briefing
from backend.agents.briefing.agent import MODEL
from backend.learning import store as learning_store
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode


GOAL = {
    "primary_goal": "understand how authentication works",
    "goal_type": "understand_component",
    "focus_area": "authentication",
    "code_depth": "working",
    "depth": "moderate",
    "familiarity": "Skimmed the README or docs",
    "background": "Django, some Flask",
}

SURVEY = {
    "architecture": "Requests is a synchronous HTTP client layered over urllib3.",
    "subsystems": [
        {
            "name": "sessions",
            "responsibility": "Owns connection reuse and cookie persistence.",
            "key_file": "requests/sessions.py",
            "key_symbol": "Session",
        }
    ],
    "entry_points": [
        {
            "file": "requests/api.py",
            "symbol": "request",
            "perspective": "public_api",
            "what_it_starts": "A one-shot request through a throwaway Session.",
        }
    ],
    "core_abstractions": [
        {"file": "requests/models.py", "symbol": "PreparedRequest", "role": "The wire form."}
    ],
    "flows": [{"name": "send a GET", "steps": [{"file": "a.py", "symbol": "b", "what_happens": "c"}]}],
    "testing_posture": "pytest, under tests/.",
}

DOC_CONTEXT = {"readme": "Requests is an elegant and simple HTTP library."}


def _client_returning(payload: dict | str) -> MagicMock:
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    block = MagicMock()
    block.text = raw
    response = MagicMock()
    response.content = [block]
    client = MagicMock()
    client.messages.create.return_value = response
    return client


# --- the grounding rules ------------------------------------------------------


def test_no_material_returns_no_briefing():
    """With no survey and no README the model knows nothing about the repo.

    A goal alone is enough for a model to write a confident description of a
    repository it has never seen, which is exactly what must not ship.
    """
    client = _client_returning({"paragraph": "should never be asked for", "notes": []})

    result = build_briefing(
        repo_url="https://github.com/psf/requests",
        goal=GOAL,
        survey=None,
        doc_context=None,
        client=client,
    )

    assert result["available"] is False
    assert result["paragraph"] == ""
    client.messages.create.assert_not_called()


def test_readme_alone_is_enough_material():
    client = _client_returning({"paragraph": "An HTTP client.", "notes": []})

    result = build_briefing(
        repo_url="https://github.com/psf/requests",
        goal=GOAL,
        survey=None,
        doc_context=DOC_CONTEXT,
        client=client,
    )

    assert result == {
        "paragraph": "An HTTP client.",
        "notes": [],
        "personalized": True,
        "available": True,
    }


def test_unresolvable_note_path_is_dropped_but_the_note_survives(tmp_path):
    (tmp_path / "requests").mkdir()
    (tmp_path / "requests" / "sessions.py").write_text("class Session: pass")
    client = _client_returning(
        {
            "paragraph": "An HTTP client.",
            "notes": [
                {"text": "Everything routes through Session.", "file": "requests/sessions.py"},
                {"text": "Retries live here.", "file": "requests/retry.py"},
            ],
        }
    )

    result = build_briefing(
        repo_url="https://github.com/psf/requests",
        goal=GOAL,
        survey=SURVEY,
        doc_context=DOC_CONTEXT,
        repo_path=str(tmp_path),
        client=client,
    )

    assert result["notes"] == [
        {"text": "Everything routes through Session.", "file": "requests/sessions.py"},
        {"text": "Retries live here.", "file": None},
    ]


def test_note_path_escaping_the_repo_is_dropped(tmp_path):
    client = _client_returning(
        {"paragraph": "An HTTP client.", "notes": [{"text": "Odd.", "file": "../../etc/passwd"}]}
    )

    result = build_briefing(
        repo_url="https://github.com/psf/requests",
        goal=GOAL,
        survey=SURVEY,
        doc_context=None,
        repo_path=str(tmp_path),
        client=client,
    )

    assert result["notes"] == [{"text": "Odd.", "file": None}]


def test_citation_is_dropped_when_there_is_no_checkout_to_check_it_against():
    client = _client_returning(
        {"paragraph": "An HTTP client.", "notes": [{"text": "Session matters.", "file": "requests/sessions.py"}]}
    )

    result = build_briefing(
        repo_url="https://github.com/psf/requests",
        goal=GOAL,
        survey=SURVEY,
        doc_context=None,
        repo_path=None,
        client=client,
    )

    assert result["notes"] == [{"text": "Session matters.", "file": None}]


# --- degradation --------------------------------------------------------------


def test_unparseable_response_falls_back_to_the_surveys_own_prose():
    result = build_briefing(
        repo_url="https://github.com/psf/requests",
        goal=GOAL,
        survey=SURVEY,
        doc_context=DOC_CONTEXT,
        client=_client_returning("I'd love to help! Here's a briefing:"),
    )

    assert result["available"] is True
    # Marked NOT personalized, because it is the goal-agnostic account verbatim.
    assert result["personalized"] is False
    assert result["paragraph"] == SURVEY["architecture"]


def test_failed_call_falls_back_to_the_surveys_own_prose():
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("overloaded")

    result = build_briefing(
        repo_url="https://github.com/psf/requests",
        goal=GOAL,
        survey=SURVEY,
        doc_context=DOC_CONTEXT,
        client=client,
    )

    assert result["personalized"] is False
    assert result["paragraph"] == SURVEY["architecture"]


def test_failed_call_with_no_survey_prose_is_unavailable_not_invented():
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("overloaded")

    result = build_briefing(
        repo_url="https://github.com/psf/requests",
        goal=GOAL,
        survey=None,
        doc_context=DOC_CONTEXT,   # material enough to try, nothing to fall back on
        client=client,
    )

    assert result["available"] is False
    assert result["paragraph"] == ""


def test_fenced_json_is_read():
    result = build_briefing(
        repo_url="https://github.com/psf/requests",
        goal=GOAL,
        survey=SURVEY,
        doc_context=None,
        client=_client_returning('```json\n{"paragraph": "An HTTP client.", "notes": []}\n```'),
    )

    assert result["paragraph"] == "An HTTP client."
    assert result["personalized"] is True


# --- the prompt carries the profile and only grounded material ----------------


def test_the_prompt_carries_the_profile_and_the_material():
    client = _client_returning({"paragraph": "An HTTP client.", "notes": []})

    build_briefing(
        repo_url="https://github.com/psf/requests",
        goal=GOAL,
        survey=SURVEY,
        doc_context=DOC_CONTEXT,
        client=client,
    )

    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["model"] == MODEL          # Haiku: never Sonnet outside the Mentor
    sent = kwargs["messages"][0]["content"]
    assert GOAL["primary_goal"] in sent
    assert GOAL["background"] in sent
    assert SURVEY["architecture"] in sent
    assert "requests/sessions.py" in sent
    assert DOC_CONTEXT["readme"] in sent
    # Familiarity is not just passed through — it changes what the paragraph does.
    assert "Do not restate the README" in sent


def test_goal_type_followups_reach_the_prompt():
    goal = {
        **GOAL,
        "goal_type": "debug_issue",
        "error_description": "ConnectionError on the second request",
        "tried_so_far": "bumped the timeout",
    }
    client = _client_returning({"paragraph": "An HTTP client.", "notes": []})

    build_briefing(
        repo_url="https://github.com/psf/requests",
        goal=goal,
        survey=SURVEY,
        doc_context=None,
        client=client,
    )

    sent = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "ConnectionError on the second request" in sent
    assert "bumped the timeout" in sent


# --- the endpoint -------------------------------------------------------------


@pytest.fixture(autouse=True)
def _env_and_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(api, "SESSIONS_DB_PATH", tmp_path / "sessions.db")


@pytest.fixture
def http():
    return TestClient(api.app)


def _saved_graph() -> LearningGraph:
    graph = LearningGraph(repo_url="https://github.com/psf/requests", goal=GOAL)
    graph.add_node(
        LearningNode(
            title="Understand HTTPBasicAuth",
            code_anchor=CodeAnchor(file="requests/auth.py", line_start=72, line_end=100),
            concept_tags=["request signing"],
            lesson_brief={"why": "core auth"},
        )
    )
    graph.doc_context = DOC_CONTEXT
    learning_store.save_graph(graph, api.SESSIONS_DB_PATH, user_id=TEST_USER_ID)
    return graph


def test_welcome_writes_the_briefing_once_and_reads_it_back(http, tmp_path):
    graph = _saved_graph()
    client = _client_returning(
        {"paragraph": "An HTTP client layered over urllib3.", "notes": []}
    )

    with patch.object(api, "_new_client", return_value=client), patch.object(
        api, "clone_repo", return_value=str(tmp_path)
    ), patch.object(api, "get_commit_sha", return_value="abc123"), patch.object(
        api.survey_store, "load_survey", return_value=SURVEY
    ):
        first = http.get(f"/session/{graph.session_id}/welcome")
        second = http.get(f"/session/{graph.session_id}/welcome")

    assert first.status_code == 200
    assert first.json()["briefing"]["paragraph"] == "An HTTP client layered over urllib3."
    assert second.json() == first.json()
    # Cached on the session: the second GET is free.
    assert client.messages.create.call_count == 1
    reloaded = learning_store.load_graph(graph.session_id, TEST_USER_ID, api.SESSIONS_DB_PATH)
    assert reloaded.briefing == first.json()["briefing"]


def test_welcome_survives_a_repo_that_cannot_be_cloned(http):
    """No checkout means no survey — the README and the profile are still there."""
    graph = _saved_graph()
    client = _client_returning({"paragraph": "An HTTP client.", "notes": []})

    with patch.object(api, "_new_client", return_value=client), patch.object(
        api, "clone_repo", side_effect=RuntimeError("network down")
    ):
        response = http.get(f"/session/{graph.session_id}/welcome")

    assert response.status_code == 200
    assert response.json()["briefing"]["available"] is True


def test_welcome_on_an_unknown_session_is_404(http):
    assert http.get("/session/nope/welcome").status_code == 404


def test_a_graph_written_before_briefings_existed_loads_with_none():
    graph = _saved_graph()
    reloaded = learning_store.load_graph(graph.session_id, TEST_USER_ID, api.SESSIONS_DB_PATH)
    assert reloaded.briefing is None
