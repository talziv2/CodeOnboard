"""
Pytest tests for backend/rag/retrieval.py.
Run with: uv run pytest tests/test_retrieval.py -v
"""
from unittest.mock import patch

from backend.pipeline.state import OnboardState
from backend.rag.retrieval import (
    RRF_K,
    build_retrieval_query,
    drop_redundant_class_chunks,
    retrieve_chunks,
    rrf_fuse,
    select_with_file_cap,
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


def _make_state(goal: dict | None = FAKE_GOAL_UNDERSTAND_COMPONENT) -> OnboardState:
    state = OnboardState(repo_url=FAKE_REPO_URL)
    state.repo_path = FAKE_REPO_PATH
    state.goal = goal
    state.module_map = FAKE_MODULE_MAP
    state.chunks_embedded = True
    return state


# ── retrieve_chunks ────────────────────────────────────────────────────────────


@patch("backend.rag.retrieval.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.rag.retrieval.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.rag.retrieval.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_retrieve_chunks_returns_flattened_dicts(mock_sha, mock_embed, mock_query):
    chunks = retrieve_chunks(_make_state())
    assert len(chunks) == 2
    assert chunks[0]["file"] == "requests/auth.py"
    assert chunks[0]["start_line"] == 72
    assert chunks[0]["end_line"] == 100
    assert chunks[0]["name"] == "HTTPBasicAuth"
    assert chunks[0]["content"] == "class HTTPBasicAuth: ..."


@patch("backend.rag.retrieval.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.rag.retrieval.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.rag.retrieval.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_retrieve_chunks_focused_understand_component_query(mock_sha, mock_embed, mock_query):
    retrieve_chunks(_make_state())
    query_text = mock_embed.call_args.args[0]
    assert FAKE_GOAL_UNDERSTAND_COMPONENT["primary_goal"] in query_text
    assert FAKE_GOAL_UNDERSTAND_COMPONENT["focus_area"] in query_text


@patch("backend.rag.retrieval.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.rag.retrieval.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.rag.retrieval.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_retrieve_chunks_contribute_code_decomposes_into_subqueries(mock_sha, mock_embed, mock_query):
    retrieve_chunks(_make_state(goal=FAKE_GOAL_CONTRIBUTE_CODE))
    embed_texts = [call.args[0] for call in mock_embed.call_args_list]
    assert mock_embed.call_count == 2
    assert any(FAKE_GOAL_CONTRIBUTE_CODE["primary_goal"] in t for t in embed_texts)
    assert any(FAKE_GOAL_CONTRIBUTE_CODE["contribution_context"] in t for t in embed_texts)


@patch("backend.rag.retrieval.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.rag.retrieval.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.rag.retrieval.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_retrieve_chunks_debug_issue_decomposes_into_subqueries(mock_sha, mock_embed, mock_query):
    retrieve_chunks(_make_state(goal=FAKE_GOAL_DEBUG_ISSUE))
    embed_texts = [call.args[0] for call in mock_embed.call_args_list]
    assert mock_embed.call_count == 3
    assert any(FAKE_GOAL_DEBUG_ISSUE["primary_goal"] in t for t in embed_texts)
    assert any(FAKE_GOAL_DEBUG_ISSUE["error_description"] in t for t in embed_texts)
    assert any(FAKE_GOAL_DEBUG_ISSUE["tried_so_far"] in t for t in embed_texts)


@patch("backend.rag.retrieval.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.rag.retrieval.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.rag.retrieval.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_retrieve_chunks_focused_queries_each_pool_separately(mock_sha, mock_embed, mock_query):
    retrieve_chunks(_make_state())  # understand_component, 1 sub-query, source-only
    assert mock_query.call_count == 1
    component_where = mock_query.call_args.kwargs["where"]
    assert component_where == {"role": "source"}

    mock_query.reset_mock()
    retrieve_chunks(_make_state(goal=FAKE_GOAL_DEBUG_ISSUE))
    assert mock_query.call_count == 6  # 3 sub-queries × 2 roles
    wheres = [call.kwargs["where"] for call in mock_query.call_args_list]
    assert {"role": "source"} in wheres
    assert {"role": "test"} in wheres
    assert sum(1 for w in wheres if w == {"role": "source"}) == 3
    assert sum(1 for w in wheres if w == {"role": "test"}) == 3


def test_build_retrieval_query_falls_back_when_optional_fields_missing():
    goal = {
        "primary_goal": "add OAuth2 support",
        "goal_type": "contribute_code",
    }
    query = build_retrieval_query(goal)
    assert query == "add OAuth2 support"


@patch("backend.rag.retrieval.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.rag.retrieval.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.rag.retrieval.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_retrieve_chunks_per_module_calls_query_once_per_module(mock_sha, mock_embed, mock_query):
    retrieve_chunks(_make_state(goal=FAKE_GOAL_UNDERSTAND_SYSTEM))
    assert mock_embed.call_count == len(FAKE_MODULE_MAP)
    assert mock_query.call_count == len(FAKE_MODULE_MAP)
    embed_texts = [call.args[0] for call in mock_embed.call_args_list]
    assert any(FAKE_MODULE_MAP["sessions"]["purpose"] in t for t in embed_texts)
    assert any("Session" in t for t in embed_texts)
    assert any(FAKE_MODULE_MAP["auth"]["purpose"] in t for t in embed_texts)
    assert any("HTTPBasicAuth" in t for t in embed_texts)


@patch("backend.rag.retrieval.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.rag.retrieval.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.rag.retrieval.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_retrieve_chunks_per_module_dedupes(mock_sha, mock_embed, mock_query):
    chunks = retrieve_chunks(_make_state(goal=FAKE_GOAL_UNDERSTAND_SYSTEM))
    keys = [(c["file"], c["start_line"], c["end_line"]) for c in chunks]
    assert len(keys) == len(set(keys))
    assert len(chunks) == 2


@patch("backend.rag.retrieval.store.query", return_value=FAKE_CHROMA_RESULT)
@patch("backend.rag.retrieval.embedder.embed_query", return_value=FAKE_QUERY_EMBEDDING)
@patch("backend.rag.retrieval.get_commit_sha", return_value=FAKE_COMMIT_SHA)
def test_retrieve_chunks_uses_correct_collection_name(mock_sha, mock_embed, mock_query):
    retrieve_chunks(_make_state())
    call_collection_name = mock_query.call_args.args[0]
    assert "psf" in call_collection_name
    assert "requests" in call_collection_name
    assert FAKE_COMMIT_SHA[:12] in call_collection_name


# ── RRF fusion ────────────────────────────────────────────────────────────────


def _chunk(file: str, start: int, end: int, name: str = "x", **extra) -> dict:
    return {
        "file": file, "start_line": start, "end_line": end,
        "type": "function", "name": name, "content": f"def {name}: ...",
        **extra,
    }


def test_rrf_fuse_orders_by_summed_inverse_rank():
    a = _chunk("a.py", 1, 10, "A")
    b = _chunk("b.py", 1, 10, "B")
    c = _chunk("c.py", 1, 10, "C")
    pool1 = [a, b, c]  # A:rank1, B:rank2, C:rank3
    pool2 = [c, a, b]  # C:rank1, A:rank2, B:rank3
    fused = rrf_fuse([pool1, pool2])
    keys = [(ch["file"], ch["start_line"], ch["end_line"]) for ch in fused]
    # A: 1/61 + 1/62; C: 1/63 + 1/61; B: 1/62 + 1/63
    assert keys == [("a.py", 1, 10), ("c.py", 1, 10), ("b.py", 1, 10)]


def test_rrf_fuse_dedupes_same_chunk_across_pools():
    a = _chunk("a.py", 1, 10, "A")
    fused = rrf_fuse([[a], [a]])
    assert len(fused) == 1
    assert fused[0]["file"] == "a.py"


def test_rrf_fuse_handles_empty_pools():
    a = _chunk("a.py", 1, 10, "A")
    fused = rrf_fuse([[a], []])
    assert len(fused) == 1
    assert fused[0]["file"] == "a.py"


def test_rrf_fuse_empty_returns_empty():
    assert rrf_fuse([]) == []
    assert rrf_fuse([[], []]) == []


def test_rrf_k_constant_is_the_standard_value():
    # 60 is the canonical RRF constant from Cormack et al. 2009. The test
    # exists to make any change to this number deliberate, not accidental.
    assert RRF_K == 60


# ── File-diversity cap ────────────────────────────────────────────────────────


def test_select_with_file_cap_limits_per_file():
    big = [_chunk("big.py", i * 10, i * 10 + 5, f"f{i}") for i in range(5)]
    other = [_chunk("other.py", 1, 5, "g1"), _chunk("other.py", 10, 15, "g2")]
    selected = select_with_file_cap(big + other, top_k=10, max_per_file=2)
    big_count = sum(1 for c in selected if c["file"] == "big.py")
    other_count = sum(1 for c in selected if c["file"] == "other.py")
    assert big_count == 2
    assert other_count == 2


def test_select_with_file_cap_respects_top_k():
    chunks = [_chunk(f"f{i}.py", 1, 10, f"x{i}") for i in range(10)]
    selected = select_with_file_cap(chunks, top_k=4, max_per_file=3)
    assert len(selected) == 4


def test_select_with_file_cap_preserves_input_order():
    a = _chunk("a.py", 1, 10, "A")
    b = _chunk("b.py", 1, 10, "B")
    c = _chunk("c.py", 1, 10, "C")
    selected = select_with_file_cap([b, a, c], top_k=3, max_per_file=1)
    assert [s["name"] for s in selected] == ["B", "A", "C"]


# ── drop_redundant_class_chunks ───────────────────────────────────────────────


def test_drop_redundant_class_chunks_removes_class_when_method_present():
    chunks = [
        {"file": "submarine.py", "start_line": 12, "end_line": 116,
         "type": "class", "name": "GateSubmarineProblem", "content": "class ..."},
        {"file": "submarine.py", "start_line": 47, "end_line": 68,
         "type": "function", "name": "actions", "content": "def actions ..."},
    ]
    result = drop_redundant_class_chunks(chunks)
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
    result = drop_redundant_class_chunks(chunks)
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
    result = drop_redundant_class_chunks(chunks)
    names = [c["name"] for c in result]
    assert "Cls" not in names
    assert "m1" in names and "m2" in names


def test_drop_redundant_class_chunks_does_not_match_across_files():
    chunks = [
        {"file": "a.py", "start_line": 12, "end_line": 116,
         "type": "class", "name": "Cls", "content": "class ..."},
        {"file": "b.py", "start_line": 20, "end_line": 30,
         "type": "function", "name": "m1", "content": "def m1 ..."},
    ]
    result = drop_redundant_class_chunks(chunks)
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
    result = drop_redundant_class_chunks(chunks)
    names = [c["name"] for c in result]
    assert "top_level" in names
    assert "method" in names
    assert "Cls" not in names


def test_drop_redundant_class_chunks_empty_input():
    assert drop_redundant_class_chunks([]) == []
