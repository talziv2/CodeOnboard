"""
Pytest tests for Code Structure Agent using mocks.
Run with: uv run pytest tests/test_code_structure_agent.py -v
"""
import json
from unittest.mock import MagicMock

from backend.pipeline.state import OnboardState
from backend.agents.code_structure import run

FAKE_REPO_URL = "https://github.com/psf/requests"
FAKE_REPO_PATH = "data/repos/requests"

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


def _make_mock_client(content: str) -> MagicMock:
    message = MagicMock()
    message.content = [MagicMock(text=content)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = message
    return mock_client


def _make_state() -> OnboardState:
    return OnboardState(repo_url=FAKE_REPO_URL)


# ── happy path ────────────────────────────────────────────────────────────────

from unittest.mock import patch


@patch("backend.agents.code_structure.agent.chunk_repo", return_value=FAKE_CHUNKS)
@patch("backend.agents.code_structure.agent.clone_repo", return_value=FAKE_REPO_PATH)
def test_run_sets_repo_path(mock_clone, mock_chunk):
    client = _make_mock_client(json.dumps(FAKE_MODULE_MAP))
    result = run(_make_state(), client=client)
    assert result.repo_path == FAKE_REPO_PATH


@patch("backend.agents.code_structure.agent.chunk_repo", return_value=FAKE_CHUNKS)
@patch("backend.agents.code_structure.agent.clone_repo", return_value=FAKE_REPO_PATH)
def test_run_sets_module_map(mock_clone, mock_chunk):
    client = _make_mock_client(json.dumps(FAKE_MODULE_MAP))
    result = run(_make_state(), client=client)
    assert result.module_map is not None
    assert "sessions" in result.module_map
    assert "auth" in result.module_map
    assert "adapters" in result.module_map


@patch("backend.agents.code_structure.agent.chunk_repo", return_value=FAKE_CHUNKS)
@patch("backend.agents.code_structure.agent.clone_repo", return_value=FAKE_REPO_PATH)
def test_run_module_map_entries_have_expected_keys(mock_clone, mock_chunk):
    client = _make_mock_client(json.dumps(FAKE_MODULE_MAP))
    result = run(_make_state(), client=client)
    entry = result.module_map["sessions"]
    assert "purpose" in entry
    assert "key_files" in entry
    assert "exports" in entry
    assert "dependencies" in entry


@patch("backend.agents.code_structure.agent.chunk_repo", return_value=FAKE_CHUNKS)
@patch("backend.agents.code_structure.agent.clone_repo", return_value=FAKE_REPO_PATH)
def test_run_handles_markdown_fenced_json(mock_clone, mock_chunk):
    fenced = f"```json\n{json.dumps(FAKE_MODULE_MAP)}\n```"
    client = _make_mock_client(fenced)
    result = run(_make_state(), client=client)
    assert result.module_map is not None
    assert "sessions" in result.module_map


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


@patch("backend.agents.code_structure.agent.chunk_repo", return_value=FAKE_CHUNKS)
@patch("backend.agents.code_structure.agent.clone_repo", return_value=FAKE_REPO_PATH)
def test_run_handles_invalid_llm_json(mock_clone, mock_chunk):
    client = _make_mock_client("not valid json at all")
    result = run(_make_state(), client=client)
    assert result.module_map is None
    assert any("LLM call failed" in e for e in result.errors)
