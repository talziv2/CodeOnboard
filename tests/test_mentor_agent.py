"""
Pytest tests for Mentor Agent using mocks.
Run with: uv run pytest tests/test_mentor_agent.py -v
"""
import json
from unittest.mock import MagicMock, patch

from backend.pipeline.state import OnboardState
from backend.agents.mentor import run
from backend.agents.mentor.agent import (
    _PROMPT_BUILDERS,
    _build_contribute_code_prompt,
    _build_debug_issue_prompt,
    _build_retrieval_query,
    _build_understand_component_prompt,
    _build_understand_system_prompt,
    _parse_output,
    _retrieve_chunks,
)


FAKE_REPO_URL = "https://github.com/psf/requests"
FAKE_REPO_PATH = "data/repos/requests"
FAKE_COMMIT_SHA = "abcdef1234567890abcdef1234567890abcdef12"
FAKE_QUERY_EMBEDDING = [0.1, 0.2, 0.3]


FAKE_MODULE_MAP = {
    "sessions": {
        "purpose": "Core abstraction managing persistent settings",
        "key_files": ["requests/sessions.py"],
        "exports": ["Session"],
        "dependencies": ["adapters", "auth"],
    },
    "auth": {
        "purpose": "Handles HTTP authentication schemes",
        "key_files": ["requests/auth.py"],
        "exports": ["HTTPBasicAuth", "HTTPDigestAuth"],
        "dependencies": ["models"],
    },
}


FAKE_GOAL_UNDERSTAND_COMPONENT = {
    "primary_goal": "understand how authentication works",
    "goal_type": "understand_component",
    "focus_area": "authentication",
    "experience_level": "intermediate",
    "depth": "deep",
    "target_repo": FAKE_REPO_URL,
    "familiarity": "new to requests",
    "background": "5 years Python",
}


FAKE_GOAL_UNDERSTAND_SYSTEM = {
    **FAKE_GOAL_UNDERSTAND_COMPONENT,
    "goal_type": "understand_system",
    "primary_goal": "get a high-level tour",
    "focus_area": "overall architecture",
    "depth": "overview",
}


FAKE_GOAL_CONTRIBUTE_CODE = {
    **FAKE_GOAL_UNDERSTAND_COMPONENT,
    "goal_type": "contribute_code",
    "primary_goal": "add OAuth2 support",
    "contribution_context": "want to add a new auth class for OAuth2 client credentials flow",
}


FAKE_GOAL_DEBUG_ISSUE = {
    **FAKE_GOAL_UNDERSTAND_COMPONENT,
    "goal_type": "debug_issue",
    "primary_goal": "fix SSL verification error",
    "error_description": "SSLError on every HTTPS request after upgrade",
    "tried_so_far": "verified certs are valid, downgraded urllib3, no luck",
}


FAKE_CHROMA_RESULT = {
    "ids": [["requests/auth.py:72-100:HTTPBasicAuth", "requests/sessions.py:394-470:Session"]],
    "distances": [[0.12, 0.34]],
    "documents": [
        ["class HTTPBasicAuth: ...", "class Session: ..."],
    ],
    "metadatas": [
        [
            {"file": "requests/auth.py", "start_line": 72, "end_line": 100, "type": "class", "name": "HTTPBasicAuth", "language": "python"},
            {"file": "requests/sessions.py", "start_line": 394, "end_line": 470, "type": "class", "name": "Session", "language": "python"},
        ],
    ],
}


FAKE_LEARNING_PATH_OUTPUT = {
    "steps": [
        {
            "step": 1,
            "title": "Understand HTTPBasicAuth",
            "file": "requests/auth.py",
            "line_range": [72, 100],
            "why": "Simplest auth scheme — establishes the auth handler interface",
            "understand": "How __call__ modifies the PreparedRequest",
            "concepts": ["callable classes", "request signing"],
        },
        {
            "step": 2,
            "title": "Trace Session.send to the auth handler",
            "file": "requests/sessions.py",
            "line_range": [394, 470],
            "why": "Shows where auth is invoked during request prep",
            "understand": "Order of merge_environment_settings and prepare_request",
            "concepts": ["request lifecycle"],
        },
    ],
    "confidence": "high",
}


def _make_mock_client(content: str) -> MagicMock:
    message = MagicMock()
    message.content = [MagicMock(text=content)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = message
    return mock_client


def _make_state(goal: dict | None = FAKE_GOAL_UNDERSTAND_COMPONENT) -> OnboardState:
    state = OnboardState(repo_url=FAKE_REPO_URL)
    state.repo_path = FAKE_REPO_PATH
    state.goal = goal
    state.module_map = FAKE_MODULE_MAP
    state.chunks_embedded = True
    return state


# ── happy path ────────────────────────────────────────────────────────────────

@patch("backend.agents.mentor.agent.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.agents.mentor.agent.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.agents.mentor.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_run_sets_learning_path(mock_sha, mock_embed, mock_query):
    client = _make_mock_client(json.dumps(FAKE_LEARNING_PATH_OUTPUT))
    result = run(_make_state(), client=client)
    assert result.learning_path is not None
    assert len(result.learning_path) == 2
    assert result.learning_path[0]["title"] == "Understand HTTPBasicAuth"


@patch("backend.agents.mentor.agent.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.agents.mentor.agent.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.agents.mentor.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_run_sets_confidence(mock_sha, mock_embed, mock_query):
    client = _make_mock_client(json.dumps(FAKE_LEARNING_PATH_OUTPUT))
    result = run(_make_state(), client=client)
    assert result.confidence == "high"


@patch("backend.agents.mentor.agent.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.agents.mentor.agent.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.agents.mentor.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_run_steps_have_expected_keys(mock_sha, mock_embed, mock_query):
    client = _make_mock_client(json.dumps(FAKE_LEARNING_PATH_OUTPUT))
    result = run(_make_state(), client=client)
    step = result.learning_path[0]
    for key in ("step", "title", "file", "line_range", "why", "understand", "concepts"):
        assert key in step


@patch("backend.agents.mentor.agent.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.agents.mentor.agent.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.agents.mentor.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_run_handles_markdown_fenced_json(mock_sha, mock_embed, mock_query):
    fenced = f"```json\n{json.dumps(FAKE_LEARNING_PATH_OUTPUT)}\n```"
    client = _make_mock_client(fenced)
    result = run(_make_state(), client=client)
    assert result.learning_path is not None


@patch("backend.agents.mentor.agent.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.agents.mentor.agent.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.agents.mentor.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_run_uses_sonnet_model(mock_sha, mock_embed, mock_query):
    client = _make_mock_client(json.dumps(FAKE_LEARNING_PATH_OUTPUT))
    run(_make_state(), client=client)
    assert client.messages.create.call_args.kwargs["model"] == "claude-sonnet-4-6"


# ── retrieval ─────────────────────────────────────────────────────────────────

@patch("backend.agents.mentor.agent.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.agents.mentor.agent.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.agents.mentor.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_retrieve_chunks_returns_flattened_dicts(mock_sha, mock_embed, mock_query):
    state = _make_state()
    chunks = _retrieve_chunks(state)
    assert len(chunks) == 2
    assert chunks[0]["file"] == "requests/auth.py"
    assert chunks[0]["start_line"] == 72
    assert chunks[0]["end_line"] == 100
    assert chunks[0]["name"] == "HTTPBasicAuth"
    assert chunks[0]["content"] == "class HTTPBasicAuth: ..."


@patch("backend.agents.mentor.agent.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.agents.mentor.agent.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.agents.mentor.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_retrieve_chunks_focused_understand_component_query(mock_sha, mock_embed, mock_query):
    _retrieve_chunks(_make_state())
    query_text = mock_embed.call_args.args[0]
    assert FAKE_GOAL_UNDERSTAND_COMPONENT["primary_goal"] in query_text
    assert FAKE_GOAL_UNDERSTAND_COMPONENT["focus_area"] in query_text


@patch("backend.agents.mentor.agent.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.agents.mentor.agent.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.agents.mentor.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_retrieve_chunks_focused_contribute_code_query(mock_sha, mock_embed, mock_query):
    _retrieve_chunks(_make_state(goal=FAKE_GOAL_CONTRIBUTE_CODE))
    query_text = mock_embed.call_args.args[0]
    assert FAKE_GOAL_CONTRIBUTE_CODE["primary_goal"] in query_text
    assert FAKE_GOAL_CONTRIBUTE_CODE["contribution_context"] in query_text


@patch("backend.agents.mentor.agent.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.agents.mentor.agent.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.agents.mentor.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_retrieve_chunks_focused_debug_issue_query(mock_sha, mock_embed, mock_query):
    _retrieve_chunks(_make_state(goal=FAKE_GOAL_DEBUG_ISSUE))
    query_text = mock_embed.call_args.args[0]
    assert FAKE_GOAL_DEBUG_ISSUE["primary_goal"] in query_text
    assert FAKE_GOAL_DEBUG_ISSUE["error_description"] in query_text
    assert FAKE_GOAL_DEBUG_ISSUE["tried_so_far"] in query_text


def test_build_retrieval_query_falls_back_when_optional_fields_missing():
    goal = {
        "primary_goal": "add OAuth2 support",
        "goal_type": "contribute_code",
        # no contribution_context
    }
    query = _build_retrieval_query(goal)
    assert query == "add OAuth2 support"


@patch("backend.agents.mentor.agent.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.agents.mentor.agent.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.agents.mentor.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_retrieve_chunks_per_module_calls_query_once_per_module(mock_sha, mock_embed, mock_query):
    _retrieve_chunks(_make_state(goal=FAKE_GOAL_UNDERSTAND_SYSTEM))
    # FAKE_MODULE_MAP has 2 entries → 2 embed/query calls
    assert mock_embed.call_count == len(FAKE_MODULE_MAP)
    assert mock_query.call_count == len(FAKE_MODULE_MAP)
    embed_texts = [call.args[0] for call in mock_embed.call_args_list]
    # Each module's purpose and one of its exports should appear in some query
    assert any(FAKE_MODULE_MAP["sessions"]["purpose"] in t for t in embed_texts)
    assert any("Session" in t for t in embed_texts)
    assert any(FAKE_MODULE_MAP["auth"]["purpose"] in t for t in embed_texts)
    assert any("HTTPBasicAuth" in t for t in embed_texts)


@patch("backend.agents.mentor.agent.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.agents.mentor.agent.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.agents.mentor.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_retrieve_chunks_per_module_dedupes(mock_sha, mock_embed, mock_query):
    # Both modules return the same two chunks → final list should still contain 2
    chunks = _retrieve_chunks(_make_state(goal=FAKE_GOAL_UNDERSTAND_SYSTEM))
    keys = [(c["file"], c["start_line"], c["end_line"]) for c in chunks]
    assert len(keys) == len(set(keys))
    assert len(chunks) == 2


@patch("backend.agents.mentor.agent.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.agents.mentor.agent.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.agents.mentor.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_retrieve_chunks_uses_correct_collection_name(mock_sha, mock_embed, mock_query):
    _retrieve_chunks(_make_state())
    call_collection_name = mock_query.call_args.args[0]
    # collection_name = lowercased "{owner}_{repo}_{sha[:12]}" (sanitized)
    assert "psf" in call_collection_name
    assert "requests" in call_collection_name
    assert FAKE_COMMIT_SHA[:12] in call_collection_name


# ── goal-type branching ───────────────────────────────────────────────────────

def test_prompt_builders_has_all_four_goal_types():
    assert set(_PROMPT_BUILDERS.keys()) == {
        "understand_system",
        "understand_component",
        "contribute_code",
        "debug_issue",
    }


def test_understand_system_prompt_mentions_breadth():
    prompt = _build_understand_system_prompt(
        FAKE_GOAL_UNDERSTAND_SYSTEM, FAKE_MODULE_MAP, []
    )
    # Should reference the user's primary_goal and the modules so Sonnet can pick across them
    assert FAKE_GOAL_UNDERSTAND_SYSTEM["primary_goal"] in prompt
    assert "sessions" in prompt
    assert "auth" in prompt


def test_understand_component_prompt_includes_focus_area():
    prompt = _build_understand_component_prompt(
        FAKE_GOAL_UNDERSTAND_COMPONENT, FAKE_MODULE_MAP, []
    )
    assert FAKE_GOAL_UNDERSTAND_COMPONENT["focus_area"] in prompt


def test_contribute_code_prompt_includes_contribution_context():
    prompt = _build_contribute_code_prompt(
        FAKE_GOAL_CONTRIBUTE_CODE, FAKE_MODULE_MAP, []
    )
    assert FAKE_GOAL_CONTRIBUTE_CODE["contribution_context"] in prompt


def test_debug_issue_prompt_includes_error_and_tried():
    prompt = _build_debug_issue_prompt(
        FAKE_GOAL_DEBUG_ISSUE, FAKE_MODULE_MAP, []
    )
    assert FAKE_GOAL_DEBUG_ISSUE["error_description"] in prompt
    assert FAKE_GOAL_DEBUG_ISSUE["tried_so_far"] in prompt


def test_prompt_includes_retrieved_chunk_files():
    chunks = [
        {"file": "requests/auth.py", "start_line": 72, "end_line": 100,
         "type": "class", "name": "HTTPBasicAuth", "content": "class HTTPBasicAuth: ..."},
    ]
    prompt = _build_understand_component_prompt(
        FAKE_GOAL_UNDERSTAND_COMPONENT, FAKE_MODULE_MAP, chunks
    )
    assert "requests/auth.py" in prompt
    assert "HTTPBasicAuth" in prompt


@patch("backend.agents.mentor.agent.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.agents.mentor.agent.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.agents.mentor.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_run_dispatches_to_correct_builder(mock_sha, mock_embed, mock_query):
    client = _make_mock_client(json.dumps(FAKE_LEARNING_PATH_OUTPUT))
    run(_make_state(goal=FAKE_GOAL_DEBUG_ISSUE), client=client)
    user_msg = client.messages.create.call_args.kwargs["messages"][0]["content"]
    # debug_issue builder must surface the error_description in the prompt
    assert FAKE_GOAL_DEBUG_ISSUE["error_description"] in user_msg


# ── parsing ───────────────────────────────────────────────────────────────────

def test_parse_output_handles_plain_json():
    output = _parse_output(json.dumps(FAKE_LEARNING_PATH_OUTPUT))
    assert output.confidence == "high"
    assert len(output.steps) == 2


def test_parse_output_strips_markdown_fence():
    fenced = f"```json\n{json.dumps(FAKE_LEARNING_PATH_OUTPUT)}\n```"
    output = _parse_output(fenced)
    assert output.confidence == "high"


def test_parse_output_handles_prose_preamble_then_fenced_json():
    response = (
        "# Learning Path Analysis\n\nHere's a summary of the auth flow...\n\n"
        f"```json\n{json.dumps(FAKE_LEARNING_PATH_OUTPUT)}\n```\n"
        "\nLet me know if you need more detail."
    )
    output = _parse_output(response)
    assert output.confidence == "high"
    assert len(output.steps) == 2


def test_parse_output_handles_prose_preamble_no_fence():
    response = (
        "Here is the JSON you requested:\n\n"
        f"{json.dumps(FAKE_LEARNING_PATH_OUTPUT)}"
    )
    output = _parse_output(response)
    assert output.confidence == "high"


# ── error handling ────────────────────────────────────────────────────────────

def test_run_errors_when_goal_missing():
    state = _make_state(goal=None)
    result = run(state, client=MagicMock())
    assert result.learning_path is None
    assert any("goal" in e.lower() for e in result.errors)


def test_run_errors_when_module_map_missing():
    state = _make_state()
    state.module_map = None
    result = run(state, client=MagicMock())
    assert result.learning_path is None
    assert any("module_map" in e for e in result.errors)


def test_run_errors_when_chunks_not_embedded():
    state = _make_state()
    state.chunks_embedded = False
    result = run(state, client=MagicMock())
    assert result.learning_path is None
    assert any("embedded" in e.lower() for e in result.errors)


@patch("backend.agents.mentor.agent.store.query", side_effect=Exception("chroma down"))
@patch("backend.agents.mentor.agent.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.agents.mentor.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_run_handles_retrieval_failure(mock_sha, mock_embed, mock_query):
    client = MagicMock()
    result = run(_make_state(), client=client)
    assert result.learning_path is None
    assert any("retrieval failed" in e for e in result.errors)
    # Sonnet should not be called if retrieval failed
    client.messages.create.assert_not_called()


@patch("backend.agents.mentor.agent.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.agents.mentor.agent.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.agents.mentor.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_run_handles_invalid_llm_json(mock_sha, mock_embed, mock_query):
    client = _make_mock_client("not valid json at all")
    result = run(_make_state(), client=client)
    assert result.learning_path is None
    assert any("LLM call failed" in e for e in result.errors)


@patch("backend.agents.mentor.agent.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.agents.mentor.agent.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.agents.mentor.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_run_handles_unknown_goal_type(mock_sha, mock_embed, mock_query):
    state = _make_state()
    state.goal = {**FAKE_GOAL_UNDERSTAND_COMPONENT, "goal_type": "alien_request"}
    client = _make_mock_client(json.dumps(FAKE_LEARNING_PATH_OUTPUT))
    result = run(state, client=client)
    assert result.learning_path is None
    assert any("goal_type" in e.lower() for e in result.errors)
    client.messages.create.assert_not_called()
