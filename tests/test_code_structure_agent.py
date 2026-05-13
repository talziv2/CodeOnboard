"""
Pytest tests for Code Structure Agent using mocks.
Run with: uv run pytest tests/test_code_structure_agent.py -v
"""
import json
from unittest.mock import MagicMock, patch

from backend.pipeline.state import OnboardState
from backend.agents.code_structure import run
from backend.agents.code_structure.agent import _top_level_chunks

FAKE_REPO_URL = "https://github.com/psf/requests"
FAKE_REPO_PATH = "data/repos/requests"
FAKE_COMMIT_SHA = "abcdef1234567890abcdef1234567890abcdef12"

FAKE_CHUNKS = [
    {"file": "requests/sessions.py", "start_line": 394, "end_line": 470, "type": "class",  "name": "Session",        "language": "python", "content": "class Session: ..."},
    {"file": "requests/auth.py",     "start_line": 72,  "end_line": 100, "type": "class",  "name": "HTTPBasicAuth",  "language": "python", "content": "class HTTPBasicAuth: ..."},
    {"file": "requests/auth.py",     "start_line": 102, "end_line": 140, "type": "class",  "name": "HTTPDigestAuth", "language": "python", "content": "class HTTPDigestAuth: ..."},
    {"file": "requests/adapters.py", "start_line": 80,  "end_line": 300, "type": "class",  "name": "HTTPAdapter",    "language": "python", "content": "class HTTPAdapter: ..."},
    {"file": "requests/models.py",   "start_line": 1,   "end_line": 50,  "type": "import", "name": "import urllib3", "language": "python", "content": "import urllib3"},
]

FAKE_MODULE_MAP = {
    "sessions": {"purpose": "Core abstraction managing persistent settings", "key_files": ["requests/sessions.py"], "exports": ["Session"],       "dependencies": ["adapters", "auth"]},
    "auth":     {"purpose": "Handles HTTP authentication schemes",           "key_files": ["requests/auth.py"],     "exports": ["HTTPBasicAuth"], "dependencies": ["models"]},
    "adapters": {"purpose": "Transport layer sending HTTP requests",         "key_files": ["requests/adapters.py"], "exports": ["HTTPAdapter"],   "dependencies": ["models"]},
}

FAKE_EMBEDDINGS = [[0.1, 0.2, 0.3]] * 4  # one per non-import chunk


def _make_mock_client(content: str) -> MagicMock:
    message = MagicMock()
    message.content = [MagicMock(text=content)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = message
    return mock_client


def _make_state() -> OnboardState:
    return OnboardState(repo_url=FAKE_REPO_URL)


# ── happy path ────────────────────────────────────────────────────────────────

@patch("backend.agents.code_structure.agent.store.add_chunks")
@patch("backend.agents.code_structure.agent.store.collection_exists", return_value=False)
@patch("backend.agents.code_structure.agent.embedder.embed_documents", return_value=FAKE_EMBEDDINGS)
@patch("backend.agents.code_structure.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
@patch("backend.agents.code_structure.agent.chunk_repo", return_value=FAKE_CHUNKS)
@patch("backend.agents.code_structure.agent.clone_repo", return_value=FAKE_REPO_PATH)
def test_run_sets_repo_path(mock_clone, mock_chunk, mock_sha, mock_embed, mock_exists, mock_add):
    client = _make_mock_client(json.dumps(FAKE_MODULE_MAP))
    result = run(_make_state(), client=client)
    assert result.repo_path == FAKE_REPO_PATH


@patch("backend.agents.code_structure.agent.store.add_chunks")
@patch("backend.agents.code_structure.agent.store.collection_exists", return_value=False)
@patch("backend.agents.code_structure.agent.embedder.embed_documents", return_value=FAKE_EMBEDDINGS)
@patch("backend.agents.code_structure.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
@patch("backend.agents.code_structure.agent.chunk_repo", return_value=FAKE_CHUNKS)
@patch("backend.agents.code_structure.agent.clone_repo", return_value=FAKE_REPO_PATH)
def test_run_sets_module_map(mock_clone, mock_chunk, mock_sha, mock_embed, mock_exists, mock_add):
    client = _make_mock_client(json.dumps(FAKE_MODULE_MAP))
    result = run(_make_state(), client=client)
    assert result.module_map is not None
    assert "sessions" in result.module_map
    assert "auth" in result.module_map
    assert "adapters" in result.module_map


@patch("backend.agents.code_structure.agent.store.add_chunks")
@patch("backend.agents.code_structure.agent.store.collection_exists", return_value=False)
@patch("backend.agents.code_structure.agent.embedder.embed_documents", return_value=FAKE_EMBEDDINGS)
@patch("backend.agents.code_structure.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
@patch("backend.agents.code_structure.agent.chunk_repo", return_value=FAKE_CHUNKS)
@patch("backend.agents.code_structure.agent.clone_repo", return_value=FAKE_REPO_PATH)
def test_run_module_map_entries_have_expected_keys(mock_clone, mock_chunk, mock_sha, mock_embed, mock_exists, mock_add):
    client = _make_mock_client(json.dumps(FAKE_MODULE_MAP))
    result = run(_make_state(), client=client)
    entry = result.module_map["sessions"]
    assert "purpose" in entry
    assert "key_files" in entry
    assert "exports" in entry
    assert "dependencies" in entry


@patch("backend.agents.code_structure.agent.store.add_chunks")
@patch("backend.agents.code_structure.agent.store.collection_exists", return_value=False)
@patch("backend.agents.code_structure.agent.embedder.embed_documents", return_value=FAKE_EMBEDDINGS)
@patch("backend.agents.code_structure.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
@patch("backend.agents.code_structure.agent.chunk_repo", return_value=FAKE_CHUNKS)
@patch("backend.agents.code_structure.agent.clone_repo", return_value=FAKE_REPO_PATH)
def test_run_handles_markdown_fenced_json(mock_clone, mock_chunk, mock_sha, mock_embed, mock_exists, mock_add):
    fenced = f"```json\n{json.dumps(FAKE_MODULE_MAP)}\n```"
    client = _make_mock_client(fenced)
    result = run(_make_state(), client=client)
    assert result.module_map is not None
    assert "sessions" in result.module_map


@patch("backend.agents.code_structure.agent.store.add_chunks")
@patch("backend.agents.code_structure.agent.store.collection_exists", return_value=False)
@patch("backend.agents.code_structure.agent.embedder.embed_documents", return_value=FAKE_EMBEDDINGS)
@patch("backend.agents.code_structure.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
@patch("backend.agents.code_structure.agent.chunk_repo", return_value=FAKE_CHUNKS)
@patch("backend.agents.code_structure.agent.clone_repo", return_value=FAKE_REPO_PATH)
def test_run_handles_prose_preamble_then_fenced_json(mock_clone, mock_chunk, mock_sha, mock_embed, mock_exists, mock_add):
    response = (
        "# Architecture Analysis\n\n"
        "This codebase is the requests library...\n\n"
        f"```json\n{json.dumps(FAKE_MODULE_MAP)}\n```\n"
    )
    client = _make_mock_client(response)
    result = run(_make_state(), client=client)
    assert result.module_map is not None
    assert "sessions" in result.module_map
    assert "auth" in result.module_map


# ── embedding behavior ────────────────────────────────────────────────────────

@patch("backend.agents.code_structure.agent.store.add_chunks")
@patch("backend.agents.code_structure.agent.store.collection_exists", return_value=False)
@patch("backend.agents.code_structure.agent.embedder.embed_documents", return_value=FAKE_EMBEDDINGS)
@patch("backend.agents.code_structure.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
@patch("backend.agents.code_structure.agent.chunk_repo", return_value=FAKE_CHUNKS)
@patch("backend.agents.code_structure.agent.clone_repo", return_value=FAKE_REPO_PATH)
def test_run_embeds_chunks_and_writes_to_store(mock_clone, mock_chunk, mock_sha, mock_embed, mock_exists, mock_add):
    client = _make_mock_client(json.dumps(FAKE_MODULE_MAP))
    result = run(_make_state(), client=client)

    # Imports filtered out → 4 non-import chunks embedded
    embedded_texts = mock_embed.call_args[0][0]
    assert len(embedded_texts) == 4
    assert "import urllib3" not in embedded_texts

    mock_add.assert_called_once()
    assert result.chunks_embedded is True


@patch("backend.agents.code_structure.agent.store.add_chunks")
@patch("backend.agents.code_structure.agent.store.collection_exists", return_value=True)
@patch("backend.agents.code_structure.agent.embedder.embed_documents")
@patch("backend.agents.code_structure.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
@patch("backend.agents.code_structure.agent.chunk_repo", return_value=FAKE_CHUNKS)
@patch("backend.agents.code_structure.agent.clone_repo", return_value=FAKE_REPO_PATH)
def test_run_skips_embedding_when_collection_exists(mock_clone, mock_chunk, mock_sha, mock_embed, mock_exists, mock_add):
    client = _make_mock_client(json.dumps(FAKE_MODULE_MAP))
    result = run(_make_state(), client=client)

    mock_embed.assert_not_called()
    mock_add.assert_not_called()
    assert result.chunks_embedded is True


@patch("backend.agents.code_structure.agent.store.add_chunks")
@patch("backend.agents.code_structure.agent.store.collection_exists", return_value=False)
@patch("backend.agents.code_structure.agent.embedder.embed_documents", side_effect=Exception("model load failed"))
@patch("backend.agents.code_structure.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
@patch("backend.agents.code_structure.agent.chunk_repo", return_value=FAKE_CHUNKS)
@patch("backend.agents.code_structure.agent.clone_repo", return_value=FAKE_REPO_PATH)
def test_run_continues_when_embedding_fails(mock_clone, mock_chunk, mock_sha, mock_embed, mock_exists, mock_add):
    client = _make_mock_client(json.dumps(FAKE_MODULE_MAP))
    result = run(_make_state(), client=client)

    # Embedding failure should not block module_map
    assert result.module_map is not None
    assert result.chunks_embedded is False
    assert any("embedding failed" in e for e in result.errors)


# ── top-level chunk filter for module-map prompt ──────────────────────────────

def test_top_level_chunks_keeps_classes():
    chunks = [
        {"file": "a.py", "start_line": 1, "end_line": 20, "type": "class", "name": "C"},
    ]
    assert _top_level_chunks(chunks) == chunks


def test_top_level_chunks_keeps_top_level_functions():
    chunks = [
        {"file": "a.py", "start_line": 1, "end_line": 5, "type": "function", "name": "f"},
    ]
    assert _top_level_chunks(chunks) == chunks


def test_top_level_chunks_drops_methods_inside_classes():
    chunks = [
        {"file": "a.py", "start_line": 1, "end_line": 50, "type": "class", "name": "C"},
        {"file": "a.py", "start_line": 5, "end_line": 10, "type": "function", "name": "method"},
    ]
    result = _top_level_chunks(chunks)
    names = [c["name"] for c in result]
    assert "C" in names
    assert "method" not in names


def test_top_level_chunks_does_not_drop_function_with_same_range_in_different_file():
    chunks = [
        {"file": "a.py", "start_line": 1, "end_line": 50, "type": "class", "name": "C"},
        {"file": "b.py", "start_line": 5, "end_line": 10, "type": "function", "name": "top_fn"},
    ]
    result = _top_level_chunks(chunks)
    names = [c["name"] for c in result]
    assert "C" in names
    assert "top_fn" in names


def test_top_level_chunks_keeps_imports():
    chunks = [
        {"file": "a.py", "start_line": 1, "end_line": 1, "type": "import", "name": "import os"},
    ]
    assert _top_level_chunks(chunks) == chunks


def test_top_level_chunks_handles_multiple_methods_and_top_functions():
    chunks = [
        {"file": "x.py", "start_line": 1, "end_line": 5, "type": "function", "name": "before"},
        {"file": "x.py", "start_line": 10, "end_line": 60, "type": "class", "name": "C"},
        {"file": "x.py", "start_line": 15, "end_line": 25, "type": "function", "name": "m1"},
        {"file": "x.py", "start_line": 30, "end_line": 40, "type": "function", "name": "m2"},
        {"file": "x.py", "start_line": 70, "end_line": 80, "type": "function", "name": "after"},
    ]
    result = _top_level_chunks(chunks)
    names = [c["name"] for c in result]
    assert names == ["before", "C", "after"]


# ── module-map sampling actually uses _top_level_chunks ───────────────────────

@patch("backend.agents.code_structure.agent.store.add_chunks")
@patch("backend.agents.code_structure.agent.store.collection_exists", return_value=True)
@patch("backend.agents.code_structure.agent.embedder.embed_documents", return_value=FAKE_EMBEDDINGS)
@patch("backend.agents.code_structure.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
@patch("backend.agents.code_structure.agent.clone_repo", return_value=FAKE_REPO_PATH)
def test_run_excludes_method_chunks_from_module_map_prompt(
    mock_clone, mock_sha, mock_embed, mock_exists, mock_add
):
    # Build a chunk set where the first MAX_CHUNKS-equivalent slots would
    # otherwise be eaten by big_class's methods, crowding out submarine.
    chunks = [
        {"file": "big.py", "start_line": 1, "end_line": 200, "type": "class", "name": "Big"},
        *[
            {"file": "big.py", "start_line": i, "end_line": i + 1,
             "type": "function", "name": f"big_method_{i}"}
            for i in range(2, 100)
        ],
        {"file": "submarine.py", "start_line": 1, "end_line": 50, "type": "class",
         "name": "Submarine"},
    ]

    with patch(
        "backend.agents.code_structure.agent.chunk_repo", return_value=chunks
    ):
        client = _make_mock_client(json.dumps(FAKE_MODULE_MAP))
        run(_make_state(), client=client)

    # The prompt sent to the LLM should mention submarine.py — it is no longer
    # buried under big.py's 98 method chunks.
    sent_prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "submarine.py" in sent_prompt
    assert "Submarine" in sent_prompt
    # And no big_method_* names should appear (they're nested in Big)
    assert "big_method_" not in sent_prompt


# ── error handling ────────────────────────────────────────────────────────────

@patch("backend.agents.code_structure.agent.clone_repo", side_effect=Exception("network error"))
def test_run_handles_clone_failure(mock_clone):
    result = run(_make_state(), client=MagicMock())
    assert result.module_map is None
    assert any("cloner failed" in e for e in result.errors)


@patch("backend.agents.code_structure.agent.chunk_repo", side_effect=Exception("parse error"))
@patch("backend.agents.code_structure.agent.clone_repo", return_value=FAKE_REPO_PATH)
def test_run_handles_chunker_failure(mock_clone, mock_chunk):
    result = run(_make_state(), client=MagicMock())
    assert result.module_map is None
    assert any("chunker failed" in e for e in result.errors)


@patch("backend.agents.code_structure.agent.store.add_chunks")
@patch("backend.agents.code_structure.agent.store.collection_exists", return_value=False)
@patch("backend.agents.code_structure.agent.embedder.embed_documents", return_value=FAKE_EMBEDDINGS)
@patch("backend.agents.code_structure.agent.get_commit_sha", return_value=FAKE_COMMIT_SHA)
@patch("backend.agents.code_structure.agent.chunk_repo", return_value=FAKE_CHUNKS)
@patch("backend.agents.code_structure.agent.clone_repo", return_value=FAKE_REPO_PATH)
def test_run_handles_invalid_llm_json(mock_clone, mock_chunk, mock_sha, mock_embed, mock_exists, mock_add):
    client = _make_mock_client("not valid json at all")
    result = run(_make_state(), client=client)
    assert result.module_map is None
    assert any("LLM call failed" in e for e in result.errors)
