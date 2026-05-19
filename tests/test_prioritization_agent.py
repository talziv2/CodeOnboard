"""
Pytest tests for the Prioritization Agent using mocks.
Run with: uv run pytest tests/test_prioritization_agent.py -v
"""
import json
from unittest.mock import MagicMock

from backend.agents.prioritization import run
from backend.agents.prioritization.agent import MIN_MODULES_TO_PRIORITIZE
from backend.pipeline.state import OnboardState

FAKE_REPO_URL = "https://github.com/fastapi/fastapi"

FAKE_GOAL = {
    "primary_goal": "understand request routing",
    "goal_type": "understand_component",
    "focus_area": "routing",
    "experience_level": "intermediate",
    "depth": "deep",
}


def _module(purpose: str) -> dict:
    return {"purpose": purpose, "key_files": [], "exports": [], "dependencies": []}


# A map large enough to cross MIN_MODULES_TO_PRIORITIZE.
FAKE_MODULE_MAP = {
    "routing": _module("HTTP request routing"),
    "params": _module("Request parameter extraction"),
    "responses": _module("Response construction"),
    "security": _module("Authentication and authorization"),
    "datastructures": _module("Internal data containers"),
    "encoders": _module("JSON encoding helpers"),
    "logger": _module("Logging configuration"),
}


def _make_mock_client(content: str) -> MagicMock:
    message = MagicMock()
    message.content = [MagicMock(text=content)]
    client = MagicMock()
    client.messages.create.return_value = message
    return client


def _make_state(module_map: dict | None = FAKE_MODULE_MAP) -> OnboardState:
    return OnboardState(
        repo_url=FAKE_REPO_URL,
        goal=FAKE_GOAL,
        module_map=module_map,
    )


# ── happy path ────────────────────────────────────────────────────────────────

def test_run_sets_relevant_modules_to_subset():
    client = _make_mock_client(json.dumps({"relevant_modules": ["routing", "params"]}))
    state = run(_make_state(), client=client)
    assert state.relevant_modules == ["routing", "params"]


def test_run_parses_json_inside_markdown_fence():
    fenced = "```json\n" + json.dumps({"relevant_modules": ["routing"]}) + "\n```"
    state = run(_make_state(), client=_make_mock_client(fenced))
    assert state.relevant_modules == ["routing"]


def test_run_drops_module_names_not_in_map():
    client = _make_mock_client(
        json.dumps({"relevant_modules": ["routing", "invented_module"]})
    )
    state = run(_make_state(), client=client)
    assert state.relevant_modules == ["routing"]


# ── no-op cases: relevant_modules stays None ──────────────────────────────────

def test_run_skips_small_module_map_without_calling_llm():
    small_map = dict(list(FAKE_MODULE_MAP.items())[: MIN_MODULES_TO_PRIORITIZE - 1])
    client = _make_mock_client("")
    state = run(_make_state(small_map), client=client)
    assert state.relevant_modules is None
    client.messages.create.assert_not_called()


def test_run_keeps_full_map_when_llm_returns_everything():
    client = _make_mock_client(
        json.dumps({"relevant_modules": list(FAKE_MODULE_MAP)})
    )
    state = run(_make_state(), client=client)
    assert state.relevant_modules is None


def test_run_keeps_full_map_when_no_valid_modules_returned():
    client = _make_mock_client(json.dumps({"relevant_modules": ["nonsense"]}))
    state = run(_make_state(), client=client)
    assert state.relevant_modules is None


# ── error handling ────────────────────────────────────────────────────────────

def test_run_records_error_when_goal_missing():
    state = OnboardState(repo_url=FAKE_REPO_URL, module_map=FAKE_MODULE_MAP)
    result = run(state, client=_make_mock_client(""))
    assert result.relevant_modules is None
    assert any("goal missing" in e for e in result.errors)


def test_run_records_error_when_module_map_missing():
    result = run(_make_state(module_map=None), client=_make_mock_client(""))
    assert result.relevant_modules is None
    assert any("module_map missing" in e for e in result.errors)


def test_run_records_error_when_llm_call_fails():
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("boom")
    result = run(_make_state(), client=client)
    assert result.relevant_modules is None
    assert any("LLM call failed" in e for e in result.errors)


def test_run_records_error_on_unparseable_response():
    result = run(_make_state(), client=_make_mock_client("not json at all"))
    assert result.relevant_modules is None
    assert any("LLM call failed" in e for e in result.errors)
