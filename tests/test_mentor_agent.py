"""
Pytest tests for Mentor Agent using mocks.
Run with: uv run pytest tests/test_mentor_agent.py -v
"""
import json
from unittest.mock import MagicMock, patch

from backend.pipeline.state import OnboardState
from backend.agents.mentor import run
from backend.agents.mentor.agent import (
    RRF_K,
    _PROMPT_BUILDERS,
    _build_contribute_code_prompt,
    _build_debug_issue_prompt,
    _build_retrieval_query,
    _build_understand_component_prompt,
    _build_understand_system_prompt,
    _drop_redundant_class_chunks,
    _find_duplicate_anchors,
    _parse_output,
    _retrieve_chunks,
    _rrf_fuse,
    _select_with_file_cap,
)
from backend.agents.mentor.agent import MentorOutput


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


# A learning path where step 1 and step 2 reuse the SAME (file, line_range).
FAKE_LEARNING_PATH_OUTPUT_WITH_DUPES = {
    "steps": [
        {
            "step": 1,
            "title": "Understand HTTPBasicAuth — first look",
            "file": "requests/auth.py",
            "line_range": [72, 100],
            "why": "Establishes the auth handler interface",
            "understand": "How __call__ modifies the PreparedRequest",
            "concepts": ["callable classes"],
        },
        {
            "step": 2,
            "title": "Understand HTTPBasicAuth — second look (duplicate anchor!)",
            "file": "requests/auth.py",
            "line_range": [72, 100],
            "why": "Same chunk, used again",
            "understand": "Same as before",
            "concepts": ["request signing"],
        },
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
def test_retrieve_chunks_contribute_code_decomposes_into_subqueries(mock_sha, mock_embed, mock_query):
    # contribute_code decomposes the goal into primary_goal + contribution_context
    _retrieve_chunks(_make_state(goal=FAKE_GOAL_CONTRIBUTE_CODE))
    embed_texts = [call.args[0] for call in mock_embed.call_args_list]
    assert mock_embed.call_count == 2
    assert any(FAKE_GOAL_CONTRIBUTE_CODE["primary_goal"] in t for t in embed_texts)
    assert any(FAKE_GOAL_CONTRIBUTE_CODE["contribution_context"] in t for t in embed_texts)


@patch("backend.agents.mentor.agent.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.agents.mentor.agent.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.agents.mentor.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_retrieve_chunks_debug_issue_decomposes_into_subqueries(mock_sha, mock_embed, mock_query):
    # debug_issue decomposes into primary_goal + error_description + tried_so_far
    _retrieve_chunks(_make_state(goal=FAKE_GOAL_DEBUG_ISSUE))
    embed_texts = [call.args[0] for call in mock_embed.call_args_list]
    assert mock_embed.call_count == 3
    assert any(FAKE_GOAL_DEBUG_ISSUE["primary_goal"] in t for t in embed_texts)
    assert any(FAKE_GOAL_DEBUG_ISSUE["error_description"] in t for t in embed_texts)
    assert any(FAKE_GOAL_DEBUG_ISSUE["tried_so_far"] in t for t in embed_texts)


@patch("backend.agents.mentor.agent.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.agents.mentor.agent.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.agents.mentor.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_retrieve_chunks_focused_queries_each_pool_separately(mock_sha, mock_embed, mock_query):
    # The focused strategy now queries each role independently so RRF can fuse
    # by rank rather than letting larger pools dominate. understand_component
    # has one pool {source} and one sub-query → 1 call with where={"role":
    # "source"}. debug_issue has pools {source, test} and 3 sub-queries → 6
    # calls, one per (sub_query, role).
    _retrieve_chunks(_make_state())  # understand_component, 1 sub-query
    assert mock_query.call_count == 1
    component_where = mock_query.call_args.kwargs["where"]
    assert component_where == {"role": "source"}

    mock_query.reset_mock()
    _retrieve_chunks(_make_state(goal=FAKE_GOAL_DEBUG_ISSUE))
    assert mock_query.call_count == 6  # 3 sub-queries × 2 roles
    wheres = [call.kwargs["where"] for call in mock_query.call_args_list]
    assert {"role": "source"} in wheres
    assert {"role": "test"} in wheres
    # Each role should appear exactly once per sub-query.
    assert sum(1 for w in wheres if w == {"role": "source"}) == 3
    assert sum(1 for w in wheres if w == {"role": "test"}) == 3


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


# ── RRF fusion + diversity cap ────────────────────────────────────────────────

def _chunk(file: str, start: int, end: int, name: str = "x", **extra) -> dict:
    return {
        "file": file, "start_line": start, "end_line": end,
        "type": "function", "name": name, "content": f"def {name}: ...",
        **extra,
    }


def test_rrf_fuse_orders_by_summed_inverse_rank():
    # Two pools, each ranking a different chunk first. Both #1s should fuse
    # ahead of chunks that appear only once or only at lower ranks.
    a = _chunk("a.py", 1, 10, "A")
    b = _chunk("b.py", 1, 10, "B")
    c = _chunk("c.py", 1, 10, "C")
    pool1 = [a, b, c]  # A:rank1, B:rank2, C:rank3
    pool2 = [c, a, b]  # C:rank1, A:rank2, B:rank3
    fused = _rrf_fuse([pool1, pool2])
    keys = [(ch["file"], ch["start_line"], ch["end_line"]) for ch in fused]
    # A appears at rank 1 + rank 2 → highest combined score
    # C appears at rank 3 + rank 1 → ties A on rank positions (1+2 vs 1+3)?
    # Actually A: 1/(60+1) + 1/(60+2) = 0.01639+0.01613 = 0.03252
    #         C: 1/(60+3) + 1/(60+1) = 0.01587+0.01639 = 0.03226
    #         B: 1/(60+2) + 1/(60+3) = 0.01613+0.01587 = 0.03200
    # So order should be A, C, B.
    assert keys == [("a.py", 1, 10), ("c.py", 1, 10), ("b.py", 1, 10)]


def test_rrf_fuse_dedupes_same_chunk_across_pools():
    a = _chunk("a.py", 1, 10, "A")
    fused = _rrf_fuse([[a], [a]])
    assert len(fused) == 1
    assert fused[0]["file"] == "a.py"


def test_rrf_fuse_handles_empty_pools():
    a = _chunk("a.py", 1, 10, "A")
    fused = _rrf_fuse([[a], []])
    assert len(fused) == 1
    assert fused[0]["file"] == "a.py"


def test_rrf_fuse_empty_returns_empty():
    assert _rrf_fuse([]) == []
    assert _rrf_fuse([[], []]) == []


def test_rrf_k_constant_is_the_standard_value():
    # 60 is the canonical RRF constant from Cormack et al. 2009. The test
    # exists to make any change to this number deliberate, not accidental.
    assert RRF_K == 60


def test_select_with_file_cap_limits_per_file():
    # Five chunks from the same big file, two from another. With max_per_file=2
    # the selection should take 2 from the big file, then continue with the
    # other file.
    big = [_chunk("big.py", i * 10, i * 10 + 5, f"f{i}") for i in range(5)]
    other = [_chunk("other.py", 1, 5, "g1"), _chunk("other.py", 10, 15, "g2")]
    selected = _select_with_file_cap(big + other, top_k=10, max_per_file=2)
    big_count = sum(1 for c in selected if c["file"] == "big.py")
    other_count = sum(1 for c in selected if c["file"] == "other.py")
    assert big_count == 2
    assert other_count == 2


def test_select_with_file_cap_respects_top_k():
    chunks = [_chunk(f"f{i}.py", 1, 10, f"x{i}") for i in range(10)]
    selected = _select_with_file_cap(chunks, top_k=4, max_per_file=3)
    assert len(selected) == 4


def test_select_with_file_cap_preserves_input_order():
    a = _chunk("a.py", 1, 10, "A")
    b = _chunk("b.py", 1, 10, "B")
    c = _chunk("c.py", 1, 10, "C")
    selected = _select_with_file_cap([b, a, c], top_k=3, max_per_file=1)
    assert [s["name"] for s in selected] == ["B", "A", "C"]


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


# ── redundant class-chunk filter ──────────────────────────────────────────────

def test_drop_redundant_class_chunks_removes_class_when_method_present():
    chunks = [
        {"file": "submarine.py", "start_line": 12, "end_line": 116,
         "type": "class", "name": "GateSubmarineProblem", "content": "class ..."},
        {"file": "submarine.py", "start_line": 47, "end_line": 68,
         "type": "function", "name": "actions", "content": "def actions ..."},
    ]
    result = _drop_redundant_class_chunks(chunks)
    names = [c["name"] for c in result]
    assert "GateSubmarineProblem" not in names
    assert "actions" in names


def test_drop_redundant_class_chunks_keeps_class_when_no_method_present():
    chunks = [
        {"file": "submarine.py", "start_line": 12, "end_line": 116,
         "type": "class", "name": "GateSubmarineProblem", "content": "class ..."},
        {"file": "other.py", "start_line": 5, "end_line": 20,
         "type": "function", "name": "unrelated", "content": "def unrelated ..."},
    ]
    result = _drop_redundant_class_chunks(chunks)
    names = [c["name"] for c in result]
    assert "GateSubmarineProblem" in names
    assert "unrelated" in names


def test_drop_redundant_class_chunks_handles_multiple_methods():
    chunks = [
        {"file": "submarine.py", "start_line": 12, "end_line": 116,
         "type": "class", "name": "Cls", "content": "class ..."},
        {"file": "submarine.py", "start_line": 20, "end_line": 30,
         "type": "function", "name": "m1", "content": "def m1 ..."},
        {"file": "submarine.py", "start_line": 40, "end_line": 50,
         "type": "function", "name": "m2", "content": "def m2 ..."},
    ]
    result = _drop_redundant_class_chunks(chunks)
    names = [c["name"] for c in result]
    assert "Cls" not in names
    assert "m1" in names and "m2" in names


def test_drop_redundant_class_chunks_does_not_match_across_files():
    # Function with same line range but different file should NOT trigger removal
    chunks = [
        {"file": "a.py", "start_line": 12, "end_line": 116,
         "type": "class", "name": "Cls", "content": "class ..."},
        {"file": "b.py", "start_line": 20, "end_line": 30,
         "type": "function", "name": "m1", "content": "def m1 ..."},
    ]
    result = _drop_redundant_class_chunks(chunks)
    names = [c["name"] for c in result]
    assert "Cls" in names
    assert "m1" in names


def test_drop_redundant_class_chunks_preserves_top_level_functions():
    chunks = [
        {"file": "x.py", "start_line": 1, "end_line": 5,
         "type": "function", "name": "top_level", "content": "def top_level ..."},
        {"file": "x.py", "start_line": 10, "end_line": 50,
         "type": "class", "name": "Cls", "content": "class ..."},
        {"file": "x.py", "start_line": 20, "end_line": 30,
         "type": "function", "name": "method", "content": "def method ..."},
    ]
    result = _drop_redundant_class_chunks(chunks)
    names = [c["name"] for c in result]
    # top_level is outside the class range → kept
    # Cls's range covers method → Cls dropped, method kept
    assert "top_level" in names
    assert "method" in names
    assert "Cls" not in names


def test_drop_redundant_class_chunks_empty_input():
    assert _drop_redundant_class_chunks([]) == []


# ── distinct-anchor validation + retry ────────────────────────────────────────

def test_find_duplicate_anchors_empty_when_distinct():
    output = MentorOutput(**FAKE_LEARNING_PATH_OUTPUT)
    assert _find_duplicate_anchors(output) == []


def test_find_duplicate_anchors_detects_same_file_and_range():
    output = MentorOutput(**FAKE_LEARNING_PATH_OUTPUT_WITH_DUPES)
    dupes = _find_duplicate_anchors(output)
    assert dupes == [("requests/auth.py", (72, 100))]


def test_find_duplicate_anchors_ignores_same_range_different_files():
    payload = {
        "steps": [
            {**FAKE_LEARNING_PATH_OUTPUT["steps"][0], "file": "a.py"},
            {**FAKE_LEARNING_PATH_OUTPUT["steps"][0], "file": "b.py"},
        ],
        "confidence": "low",
    }
    output = MentorOutput(**payload)
    assert _find_duplicate_anchors(output) == []


@patch("backend.agents.mentor.agent.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.agents.mentor.agent.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.agents.mentor.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_run_retries_when_llm_returns_duplicate_anchors(mock_sha, mock_embed, mock_query):
    # First call: duplicate anchors. Second call (retry): clean output.
    bad = MagicMock()
    bad.content = [MagicMock(text=json.dumps(FAKE_LEARNING_PATH_OUTPUT_WITH_DUPES))]
    good = MagicMock()
    good.content = [MagicMock(text=json.dumps(FAKE_LEARNING_PATH_OUTPUT))]
    client = MagicMock()
    client.messages.create.side_effect = [bad, good]

    result = run(_make_state(), client=client)

    assert client.messages.create.call_count == 2
    assert result.learning_path is not None
    # Final learning_path should be the retry's clean output
    assert result.learning_path[0]["title"] == "Understand HTTPBasicAuth"
    assert result.learning_path[1]["title"] == "Trace Session.send to the auth handler"


@patch("backend.agents.mentor.agent.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.agents.mentor.agent.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.agents.mentor.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_run_keeps_original_when_retry_still_has_duplicates(mock_sha, mock_embed, mock_query):
    # Both calls return duplicates → keep original output, log warning.
    bad = MagicMock()
    bad.content = [MagicMock(text=json.dumps(FAKE_LEARNING_PATH_OUTPUT_WITH_DUPES))]
    client = MagicMock()
    client.messages.create.side_effect = [bad, bad]

    result = run(_make_state(), client=client)

    assert client.messages.create.call_count == 2
    assert result.learning_path is not None  # We accept partial output
    assert any("duplicate anchors persisted" in e for e in result.errors)


@patch("backend.agents.mentor.agent.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.agents.mentor.agent.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.agents.mentor.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_run_does_not_retry_when_output_is_clean(mock_sha, mock_embed, mock_query):
    client = _make_mock_client(json.dumps(FAKE_LEARNING_PATH_OUTPUT))
    result = run(_make_state(), client=client)
    assert client.messages.create.call_count == 1
    assert result.learning_path is not None
    # No duplicate-related error
    assert not any("duplicate" in e.lower() for e in result.errors)


@patch("backend.agents.mentor.agent.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.agents.mentor.agent.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.agents.mentor.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_retry_message_includes_duplicate_chunk_identifier(mock_sha, mock_embed, mock_query):
    bad = MagicMock()
    bad.content = [MagicMock(text=json.dumps(FAKE_LEARNING_PATH_OUTPUT_WITH_DUPES))]
    good = MagicMock()
    good.content = [MagicMock(text=json.dumps(FAKE_LEARNING_PATH_OUTPUT))]
    client = MagicMock()
    client.messages.create.side_effect = [bad, good]

    run(_make_state(), client=client)

    # The retry call (second invocation) should mention the duplicate file/range
    retry_messages = client.messages.create.call_args_list[1].kwargs["messages"]
    # Last message is the correction prompt
    correction = retry_messages[-1]["content"]
    assert "requests/auth.py" in correction
    assert "72" in correction and "100" in correction


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
