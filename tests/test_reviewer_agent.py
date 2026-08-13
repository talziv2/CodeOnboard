"""
Pytest tests for the Reviewer Agent.
Run with: uv run pytest tests/test_reviewer_agent.py -v
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from backend.repo.skeleton import Skeleton
from backend.agents.reviewer.agent import (
    ReviewerOutput,
    _SYSTEM_PROMPT,
    _drop_ungrounded_anchors,
    _parse_output,
    run,
    should_run,
)
from backend.pipeline.state import OnboardState


FAKE_REPO_URL = "https://github.com/psf/requests"
FAKE_REPO_PATH = "data/repos/requests"
FAKE_COMMIT_SHA = "abcdef1234567890abcdef1234567890abcdef12"
FAKE_QUERY_EMBEDDING = [0.1, 0.2, 0.3]


FAKE_GOAL_IMPROVE = {
    "primary_goal": "safely add custom auth scheme",
    "goal_type": "improve_existing_system",
    "focus_area": "session auth",
    "experience_level": "intermediate",
    "depth": "moderate",
    "target_repo": FAKE_REPO_URL,
    "familiarity": "new",
    "background": "Python",
    "change_target": "add CustomAuth subclass",
    "risk_tolerance": "production",
}

FAKE_GOAL_DEBUG = {**FAKE_GOAL_IMPROVE, "goal_type": "debug_issue"}


# Stage 0: anchors are verified against the REPOSITORY (a Skeleton), not against
# the retrieval slice. Tests supply a synthetic Layer-A index covering the two
# files the fixtures anchor on.
def _fake_skeleton() -> Skeleton:
    return Skeleton.from_chunks(
        [
            {"file": "requests/sessions.py", "start_line": 394, "end_line": 470,
             "type": "class", "name": "Session", "role": "source"},
            {"file": "requests/auth.py", "start_line": 72, "end_line": 100,
             "type": "class", "name": "AuthBase", "role": "source"},
        ],
        file_lines={"requests/sessions.py": 800, "requests/auth.py": 320},
    )


@pytest.fixture(autouse=True)
def _patch_skeleton():
    with patch(
        "backend.agents.reviewer.agent.build_skeleton",
        side_effect=lambda repo_path: _fake_skeleton(),
    ):
        yield


FAKE_MODULE_MAP = {
    "sessions": {
        "purpose": "Session lifecycle",
        "key_files": ["requests/sessions.py"],
        "exports": ["Session"],
        "dependencies": ["adapters", "auth"],
    },
    "auth": {
        "purpose": "Auth schemes",
        "key_files": ["requests/auth.py"],
        "exports": ["AuthBase", "HTTPBasicAuth"],
        "dependencies": [],
    },
}


FAKE_CHROMA_RESULT = {
    "ids": [["requests/sessions.py:394-470:Session", "requests/auth.py:72-100:AuthBase"]],
    "distances": [[0.12, 0.34]],
    "documents": [[
        "class Session: ...",
        "class AuthBase: ...",
    ]],
    "metadatas": [[
        {"file": "requests/sessions.py", "start_line": 394, "end_line": 470,
         "type": "class", "name": "Session", "language": "python", "role": "source"},
        {"file": "requests/auth.py", "start_line": 72, "end_line": 100,
         "type": "class", "name": "AuthBase", "language": "python", "role": "source"},
    ]],
}


# The dossier's rendered evidence, in the chunk shape `dossier_as_chunks` emits.
DOSSIER_CHUNKS = [
    {"file": "requests/sessions.py", "start_line": 394, "end_line": 470,
     "type": "class", "name": "Session", "role": "source", "content": "class Session: ..."},
    {"file": "requests/auth.py", "start_line": 72, "end_line": 100,
     "type": "class", "name": "AuthBase", "role": "source", "content": "class AuthBase: ..."},
]

FAKE_REVIEWER_OUTPUT = {
    "strengths": [
        {"area": "auth_layer_isolated", "note": "AuthBase isolates the auth contract.",
         "anchor": {"file": "requests/auth.py", "line_start": 72, "line_end": 100}}
    ],
    "risks": [
        {"area": "auth_on_redirect", "note": "Auth header is rebuilt on redirect.",
         "anchor": {"file": "requests/sessions.py", "line_start": 394, "line_end": 470}}
    ],
    "extension_points": [
        {"area": "auth_base", "note": "Subclass AuthBase to inject custom headers.",
         "anchor": {"file": "requests/auth.py", "line_start": 72, "line_end": 100}}
    ],
    "test_gaps": [
        {"area": "custom_auth_subclasses", "note": "No tests cover AuthBase subclasses."}
    ],
    "boundaries": [
        {"between": ["sessions", "auth"], "note": "auth is applied just before send"}
    ],
}


# ── should_run gate ───────────────────────────────────────────────────────────


def test_should_run_for_review_worthy_goal_types():
    for gt in ("improve_existing_system", "understand_architecture"):
        assert should_run({"goal_type": gt}) is True


def test_should_not_run_for_other_goal_types():
    for gt in (
        "understand_system",
        "understand_component",
        "contribute_code",
        "debug_issue",
    ):
        assert should_run({"goal_type": gt}) is False


def test_should_not_run_for_missing_or_empty_goal():
    assert should_run(None) is False
    assert should_run({}) is False


# ── parse + grounding ────────────────────────────────────────────────────────


def test_parse_output_strips_markdown_fences():
    wrapped = "```json\n" + json.dumps(FAKE_REVIEWER_OUTPUT) + "\n```"
    output = _parse_output(wrapped)
    assert isinstance(output, ReviewerOutput)
    assert output.risks[0].area == "auth_on_redirect"


def test_parse_output_coerces_string_boundary_between():
    # Haiku occasionally emits between: "sessions and auth" instead of
    # ["sessions", "auth"]. The validator should split it so one malformed
    # boundary does not tank the whole review.
    payload = {
        **FAKE_REVIEWER_OUTPUT,
        "boundaries": [
            {"between": "sessions and auth", "note": "auth applied just before send"},
            {"between": "adapters <-> models", "note": "transport vs. data"},
            {"between": "models / hooks", "note": "request lifecycle handoff"},
        ],
    }
    output = _parse_output(json.dumps(payload))
    assert output.boundaries[0].between == ["sessions", "auth"]
    assert output.boundaries[1].between == ["adapters", "models"]
    assert output.boundaries[2].between == ["models", "hooks"]


def test_drop_ungrounded_anchors_keeps_grounded_ones():
    output = _parse_output(json.dumps(FAKE_REVIEWER_OUTPUT))
    chunks = [
        {"file": "requests/sessions.py", "start_line": 394, "end_line": 470,
         "type": "class", "name": "Session", "content": "..."},
        {"file": "requests/auth.py", "start_line": 72, "end_line": 100,
         "type": "class", "name": "AuthBase", "content": "..."},
    ]
    result = _drop_ungrounded_anchors(output, chunks, _fake_skeleton())
    assert result.risks[0].anchor is not None
    assert result.risks[0].anchor.file == "requests/sessions.py"
    assert result.extension_points[0].anchor is not None


def test_drop_ungrounded_anchors_strips_invented_anchors_but_keeps_note():
    fake_with_bad_anchor = {
        **FAKE_REVIEWER_OUTPUT,
        "risks": [
            {"area": "made_up", "note": "An invented concern.",
             "anchor": {"file": "fake/file.py", "line_start": 1, "line_end": 99}}
        ],
    }
    output = _parse_output(json.dumps(fake_with_bad_anchor))
    chunks = [
        {"file": "requests/sessions.py", "start_line": 394, "end_line": 470,
         "type": "class", "name": "Session", "content": "..."},
    ]
    result = _drop_ungrounded_anchors(output, chunks, _fake_skeleton())
    # The finding stays, the anchor is dropped.
    assert len(result.risks) == 1
    assert result.risks[0].anchor is None
    assert result.risks[0].note == "An invented concern."


def test_drop_ungrounded_anchors_rejects_real_code_outside_the_evidence():
    """Stage-0 boundary: real is not the same as shown.

    auth.py:72-100 exists in the skeleton, so it resolves — but it was not among
    the chunks the Reviewer received, so the anchor must still be dropped.
    """
    real_but_unseen = {
        **FAKE_REVIEWER_OUTPUT,
        "risks": [
            {"area": "unseen_but_real", "note": "A concern about code not shown.",
             "anchor": {"file": "requests/auth.py", "line_start": 72, "line_end": 100}}
        ],
    }
    output = _parse_output(json.dumps(real_but_unseen))
    chunks = [
        {"file": "requests/sessions.py", "start_line": 394, "end_line": 470,
         "type": "class", "name": "Session", "content": "..."},
    ]
    result = _drop_ungrounded_anchors(output, chunks, _fake_skeleton())
    assert result.risks[0].anchor is None
    assert result.risks[0].note == "A concern about code not shown."


# ── system-prompt calibration regression guard ──────────────────────────────


def test_system_prompt_has_risk_tolerance_calibration():
    # Reviewer must weight findings by risk_tolerance — safety-critical at
    # the upper bound of risks/test_gaps, prototype trimmed to the
    # critical-path findings only.
    assert "Risk tolerance" in _SYSTEM_PROMPT
    assert "SAFETY-CRITICAL" in _SYSTEM_PROMPT
    assert "PROTOTYPE" in _SYSTEM_PROMPT
    assert "UPPER bound" in _SYSTEM_PROMPT
    # Default regime must still work.
    assert "UNSPECIFIED" in _SYSTEM_PROMPT


# ── run() wiring ─────────────────────────────────────────────────────────────


def _make_state(goal: dict) -> OnboardState:
    state = OnboardState(repo_url=FAKE_REPO_URL, goal=goal)
    state.repo_path = FAKE_REPO_PATH
    state.module_map = FAKE_MODULE_MAP
    # D11: the Reviewer reads the shared investigation and has no other evidence
    # source since Stage 5. The dossier's contents do not matter to these tests —
    # `_evidence` below substitutes the rendered chunks — but its presence does,
    # because without one the Reviewer correctly refuses to review anything.
    state.investigation = {"dossier": {"components": []}, "accepted": True}
    return state


def _evidence(chunks=None):
    """Stand in for the dossier's rendered evidence.

    The Reviewer resolves each finding's anchor against the repository AND
    against the code it was shown; these tests are about the review output, so
    the evidence is supplied directly rather than through a real checkout.
    """
    return patch("backend.repo.investigation.dossier_as_chunks",
                 return_value=DOSSIER_CHUNKS if chunks is None else chunks)


def _make_mock_client(raw_text: str) -> MagicMock:
    client = MagicMock()
    response = MagicMock()
    response.content = [MagicMock(text=raw_text)]
    client.messages.create.return_value = response
    return client


def test_run_skips_when_goal_type_does_not_need_review():
    client = _make_mock_client(json.dumps(FAKE_REVIEWER_OUTPUT))
    state = _make_state(FAKE_GOAL_DEBUG)
    run(state, client=client)
    # No LLM call, no system_review set.
    client.messages.create.assert_not_called()
    assert state.system_review is None


def test_run_populates_system_review_for_improve_existing_system():
    client = _make_mock_client(json.dumps(FAKE_REVIEWER_OUTPUT))
    state = _make_state(FAKE_GOAL_IMPROVE)
    with _evidence(), patch("backend.repo.skeleton.build_skeleton",
                            return_value=_fake_skeleton()):
        run(state, client=client)
    client.messages.create.assert_called_once()
    assert state.system_review is not None
    # Findings round-tripped through Pydantic + model_dump.
    assert state.system_review["risks"][0]["area"] == "auth_on_redirect"
    assert state.system_review["risks"][0]["anchor"]["file"] == "requests/sessions.py"


def test_run_leaves_review_none_on_llm_failure():
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("boom")
    state = _make_state(FAKE_GOAL_IMPROVE)
    run(state, client=client)
    assert state.system_review is None
    assert any("reviewer_agent" in e for e in state.errors)
