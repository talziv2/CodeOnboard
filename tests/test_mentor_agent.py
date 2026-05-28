"""
Pytest tests for Mentor Agent using mocks.
Run with: uv run pytest tests/test_mentor_agent.py -v

Retrieval-layer tests (RRF fusion, file-diversity cap, per-pool queries,
query decomposition, redundant-class drop) live in tests/test_retrieval.py.
This file covers what stays in the Mentor: prompt builders, output parsing,
grounding, duplicate-anchor retry, the run() flow, the wire→LearningGraph
translation, and the derived learning_path.
"""
import json
from unittest.mock import MagicMock, patch

from backend.pipeline.state import OnboardState
from backend.agents.mentor import run
from backend.agents.mentor.agent import (
    MentorOutput,
    _PROMPT_BUILDERS,
    _build_contribute_code_prompt,
    _build_debug_issue_prompt,
    _build_understand_component_prompt,
    _build_understand_system_prompt,
    _find_duplicate_anchors,
    _parse_output,
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


# ── Wire-format fixtures ──────────────────────────────────────────────────────
#
# These are nodes + edges in the new MentorOutput shape. The agent's job is to
# translate them into a LearningGraph with UUID node IDs and a derived
# learning_path.


FAKE_MENTOR_OUTPUT = {
    "nodes": [
        {
            "id": "n1",
            "title": "Understand HTTPBasicAuth",
            "file": "requests/auth.py",
            "line_start": 72,
            "line_end": 100,
            "why": "Simplest auth scheme — establishes the auth handler interface",
            "understand": "How __call__ modifies the PreparedRequest",
            "concept_tags": ["callable classes", "request signing"],
        },
        {
            "id": "n2",
            "title": "Trace Session.send to the auth handler",
            "file": "requests/sessions.py",
            "line_start": 394,
            "line_end": 470,
            "why": "Shows where auth is invoked during request prep",
            "understand": "Order of merge_environment_settings and prepare_request",
            "concept_tags": ["request lifecycle"],
        },
    ],
    "edges": [
        {"from_id": "n1", "to_id": "n2", "kind": "sequence"},
    ],
    "confidence": "high",
}


# Two nodes anchored on the SAME chunk → duplicate-anchor failure path.
FAKE_MENTOR_OUTPUT_WITH_DUPES = {
    "nodes": [
        {
            "id": "n1",
            "title": "Understand HTTPBasicAuth — first look",
            "file": "requests/auth.py",
            "line_start": 72,
            "line_end": 100,
            "why": "Establishes the auth handler interface",
            "understand": "How __call__ modifies the PreparedRequest",
            "concept_tags": ["callable classes"],
        },
        {
            "id": "n2",
            "title": "Understand HTTPBasicAuth — second look (duplicate anchor!)",
            "file": "requests/auth.py",
            "line_start": 72,
            "line_end": 100,
            "why": "Same chunk, used again",
            "understand": "Same as before",
            "concept_tags": ["request signing"],
        },
    ],
    "edges": [
        {"from_id": "n1", "to_id": "n2", "kind": "sequence"},
    ],
    "confidence": "medium",
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

@patch("backend.rag.retrieval.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.rag.retrieval.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.rag.retrieval.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_run_sets_graph(mock_sha, mock_embed, mock_query):
    client = _make_mock_client(json.dumps(FAKE_MENTOR_OUTPUT))
    result = run(_make_state(), client=client)
    assert result.graph is not None
    assert len(result.graph.nodes) == 2
    assert len(result.graph.edges) == 1
    assert result.graph.edges[0].kind == "sequence"


@patch("backend.rag.retrieval.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.rag.retrieval.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.rag.retrieval.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_run_sets_current_node_to_sequence_head(mock_sha, mock_embed, mock_query):
    client = _make_mock_client(json.dumps(FAKE_MENTOR_OUTPUT))
    result = run(_make_state(), client=client)
    head = result.graph.nodes[result.graph.current_node_id]
    # n1 has no incoming sequence edge — it's the head.
    assert head.title == "Understand HTTPBasicAuth"


@patch("backend.rag.retrieval.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.rag.retrieval.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.rag.retrieval.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_run_derives_learning_path_from_graph(mock_sha, mock_embed, mock_query):
    client = _make_mock_client(json.dumps(FAKE_MENTOR_OUTPUT))
    result = run(_make_state(), client=client)
    assert result.learning_path is not None
    assert len(result.learning_path) == 2
    assert result.learning_path[0]["step"] == 1
    assert result.learning_path[0]["title"] == "Understand HTTPBasicAuth"
    assert result.learning_path[1]["step"] == 2
    assert result.learning_path[1]["title"] == "Trace Session.send to the auth handler"


@patch("backend.rag.retrieval.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.rag.retrieval.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.rag.retrieval.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_run_sets_confidence(mock_sha, mock_embed, mock_query):
    client = _make_mock_client(json.dumps(FAKE_MENTOR_OUTPUT))
    result = run(_make_state(), client=client)
    assert result.confidence == "high"


@patch("backend.rag.retrieval.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.rag.retrieval.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.rag.retrieval.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_run_steps_have_expected_keys(mock_sha, mock_embed, mock_query):
    client = _make_mock_client(json.dumps(FAKE_MENTOR_OUTPUT))
    result = run(_make_state(), client=client)
    step = result.learning_path[0]
    for key in ("step", "title", "file", "line_range", "why", "understand", "concepts"):
        assert key in step


@patch("backend.rag.retrieval.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.rag.retrieval.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.rag.retrieval.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_run_handles_markdown_fenced_json(mock_sha, mock_embed, mock_query):
    fenced = f"```json\n{json.dumps(FAKE_MENTOR_OUTPUT)}\n```"
    client = _make_mock_client(fenced)
    result = run(_make_state(), client=client)
    assert result.graph is not None
    assert result.learning_path is not None


@patch("backend.rag.retrieval.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.rag.retrieval.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.rag.retrieval.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_run_uses_sonnet_model(mock_sha, mock_embed, mock_query):
    client = _make_mock_client(json.dumps(FAKE_MENTOR_OUTPUT))
    run(_make_state(), client=client)
    assert client.messages.create.call_args.kwargs["model"] == "claude-sonnet-4-6"


# ── wire → LearningGraph translation ──────────────────────────────────────────

@patch("backend.rag.retrieval.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.rag.retrieval.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.rag.retrieval.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_wire_ids_get_remapped_to_uuids(mock_sha, mock_embed, mock_query):
    # Sonnet emits ids like "n1"/"n2"; the LearningGraph must hold UUIDs.
    client = _make_mock_client(json.dumps(FAKE_MENTOR_OUTPUT))
    result = run(_make_state(), client=client)
    for node_id in result.graph.nodes:
        assert node_id not in {"n1", "n2"}
        # uuid4 hex is 32 chars, all lowercase hex
        assert len(node_id) == 32


@patch("backend.rag.retrieval.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.rag.retrieval.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.rag.retrieval.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_lesson_brief_assembled_from_wire_fields(mock_sha, mock_embed, mock_query):
    client = _make_mock_client(json.dumps(FAKE_MENTOR_OUTPUT))
    result = run(_make_state(), client=client)
    first_node = next(iter(result.graph.nodes.values()))
    assert "why" in first_node.lesson_brief
    assert "understand" in first_node.lesson_brief


@patch("backend.rag.retrieval.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.rag.retrieval.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.rag.retrieval.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_graph_repo_url_and_goal_match_state(mock_sha, mock_embed, mock_query):
    client = _make_mock_client(json.dumps(FAKE_MENTOR_OUTPUT))
    result = run(_make_state(), client=client)
    assert result.graph.repo_url == FAKE_REPO_URL
    assert result.graph.goal == FAKE_GOAL_UNDERSTAND_COMPONENT


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


@patch("backend.rag.retrieval.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.rag.retrieval.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.rag.retrieval.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_run_dispatches_to_correct_builder(mock_sha, mock_embed, mock_query):
    client = _make_mock_client(json.dumps(FAKE_MENTOR_OUTPUT))
    run(_make_state(goal=FAKE_GOAL_DEBUG_ISSUE), client=client)
    user_msg = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert FAKE_GOAL_DEBUG_ISSUE["error_description"] in user_msg


# ── distinct-anchor validation + retry ────────────────────────────────────────

def test_find_duplicate_anchors_empty_when_distinct():
    output = MentorOutput(**FAKE_MENTOR_OUTPUT)
    assert _find_duplicate_anchors(output) == []


def test_find_duplicate_anchors_detects_same_file_and_range():
    output = MentorOutput(**FAKE_MENTOR_OUTPUT_WITH_DUPES)
    dupes = _find_duplicate_anchors(output)
    assert dupes == [("requests/auth.py", (72, 100))]


def test_find_duplicate_anchors_ignores_same_range_different_files():
    payload = {
        "nodes": [
            {**FAKE_MENTOR_OUTPUT["nodes"][0], "file": "a.py"},
            {**FAKE_MENTOR_OUTPUT["nodes"][0], "file": "b.py", "id": "n2"},
        ],
        "edges": [{"from_id": "n1", "to_id": "n2", "kind": "sequence"}],
        "confidence": "low",
    }
    output = MentorOutput(**payload)
    assert _find_duplicate_anchors(output) == []


@patch("backend.rag.retrieval.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.rag.retrieval.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.rag.retrieval.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_run_retries_when_llm_returns_duplicate_anchors(mock_sha, mock_embed, mock_query):
    bad = MagicMock()
    bad.content = [MagicMock(text=json.dumps(FAKE_MENTOR_OUTPUT_WITH_DUPES))]
    good = MagicMock()
    good.content = [MagicMock(text=json.dumps(FAKE_MENTOR_OUTPUT))]
    client = MagicMock()
    client.messages.create.side_effect = [bad, good]

    result = run(_make_state(), client=client)

    assert client.messages.create.call_count == 2
    assert result.graph is not None
    titles = [n.title for n in result.graph.nodes.values()]
    assert "Understand HTTPBasicAuth" in titles
    assert "Trace Session.send to the auth handler" in titles


@patch("backend.rag.retrieval.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.rag.retrieval.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.rag.retrieval.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_run_keeps_original_when_retry_still_has_duplicates(mock_sha, mock_embed, mock_query):
    bad = MagicMock()
    bad.content = [MagicMock(text=json.dumps(FAKE_MENTOR_OUTPUT_WITH_DUPES))]
    client = MagicMock()
    client.messages.create.side_effect = [bad, bad]

    result = run(_make_state(), client=client)

    assert client.messages.create.call_count == 2
    # We accept partial output — graph still gets built, but with both nodes
    # pointing at the same anchor.
    assert result.graph is not None
    assert any("duplicate anchors persisted" in e for e in result.errors)


@patch("backend.rag.retrieval.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.rag.retrieval.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.rag.retrieval.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_run_does_not_retry_when_output_is_clean(mock_sha, mock_embed, mock_query):
    client = _make_mock_client(json.dumps(FAKE_MENTOR_OUTPUT))
    result = run(_make_state(), client=client)
    assert client.messages.create.call_count == 1
    assert result.graph is not None
    assert not any("duplicate" in e.lower() for e in result.errors)


@patch("backend.rag.retrieval.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.rag.retrieval.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.rag.retrieval.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_retry_message_includes_duplicate_chunk_identifier(mock_sha, mock_embed, mock_query):
    bad = MagicMock()
    bad.content = [MagicMock(text=json.dumps(FAKE_MENTOR_OUTPUT_WITH_DUPES))]
    good = MagicMock()
    good.content = [MagicMock(text=json.dumps(FAKE_MENTOR_OUTPUT))]
    client = MagicMock()
    client.messages.create.side_effect = [bad, good]

    run(_make_state(), client=client)

    retry_messages = client.messages.create.call_args_list[1].kwargs["messages"]
    correction = retry_messages[-1]["content"]
    assert "requests/auth.py" in correction
    assert "72" in correction and "100" in correction


# ── parsing ───────────────────────────────────────────────────────────────────

def test_parse_output_handles_plain_json():
    output = _parse_output(json.dumps(FAKE_MENTOR_OUTPUT))
    assert output.confidence == "high"
    assert len(output.nodes) == 2
    assert len(output.edges) == 1


def test_parse_output_strips_markdown_fence():
    fenced = f"```json\n{json.dumps(FAKE_MENTOR_OUTPUT)}\n```"
    output = _parse_output(fenced)
    assert output.confidence == "high"


def test_parse_output_handles_prose_preamble_then_fenced_json():
    response = (
        "# Learning Path Analysis\n\nHere's a summary of the auth flow...\n\n"
        f"```json\n{json.dumps(FAKE_MENTOR_OUTPUT)}\n```\n"
        "\nLet me know if you need more detail."
    )
    output = _parse_output(response)
    assert output.confidence == "high"
    assert len(output.nodes) == 2


def test_parse_output_handles_prose_preamble_no_fence():
    response = (
        "Here is the JSON you requested:\n\n"
        f"{json.dumps(FAKE_MENTOR_OUTPUT)}"
    )
    output = _parse_output(response)
    assert output.confidence == "high"


# ── error handling ────────────────────────────────────────────────────────────

def test_run_errors_when_goal_missing():
    state = _make_state(goal=None)
    result = run(state, client=MagicMock())
    assert result.graph is None
    assert result.learning_path is None
    assert any("goal" in e.lower() for e in result.errors)


def test_run_errors_when_module_map_missing():
    state = _make_state()
    state.module_map = None
    result = run(state, client=MagicMock())
    assert result.graph is None
    assert result.learning_path is None
    assert any("module_map" in e for e in result.errors)


def test_run_errors_when_chunks_not_embedded():
    state = _make_state()
    state.chunks_embedded = False
    result = run(state, client=MagicMock())
    assert result.graph is None
    assert result.learning_path is None
    assert any("embedded" in e.lower() for e in result.errors)


@patch("backend.rag.retrieval.store.query", side_effect=Exception("chroma down"))
@patch("backend.rag.retrieval.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.rag.retrieval.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_run_handles_retrieval_failure(mock_sha, mock_embed, mock_query):
    client = MagicMock()
    result = run(_make_state(), client=client)
    assert result.graph is None
    assert result.learning_path is None
    assert any("retrieval failed" in e for e in result.errors)
    client.messages.create.assert_not_called()


@patch("backend.rag.retrieval.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.rag.retrieval.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.rag.retrieval.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_run_handles_invalid_llm_json(mock_sha, mock_embed, mock_query):
    client = _make_mock_client("not valid json at all")
    result = run(_make_state(), client=client)
    assert result.graph is None
    assert result.learning_path is None
    assert any("LLM call failed" in e for e in result.errors)


@patch("backend.rag.retrieval.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.rag.retrieval.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.rag.retrieval.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_run_handles_unknown_goal_type(mock_sha, mock_embed, mock_query):
    state = _make_state()
    state.goal = {**FAKE_GOAL_UNDERSTAND_COMPONENT, "goal_type": "alien_request"}
    client = _make_mock_client(json.dumps(FAKE_MENTOR_OUTPUT))
    result = run(state, client=client)
    assert result.graph is None
    assert result.learning_path is None
    assert any("goal_type" in e.lower() for e in result.errors)
    client.messages.create.assert_not_called()
