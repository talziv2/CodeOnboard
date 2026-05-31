"""
Pytest tests for the Grader Agent using mocks.
Run with: uv run pytest tests/test_grader_agent.py -v
"""
import json
from unittest.mock import MagicMock

from backend.agents.grader import run
from backend.agents.grader.agent import (
    _SYSTEM_PROMPT,
    GraderOutput,
    _parse_output,
)
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.pipeline.state import OnboardState


FAKE_REPO_URL = "https://github.com/psf/requests"
FAKE_GOAL = {"primary_goal": "x", "goal_type": "understand_component"}

FAKE_LESSON = {
    "walkthrough": "…",
    "prompt": "What does __call__ return?",
    "expected_answer": "The mutated PreparedRequest.",
    "prompt_kind": "predict-then-reveal",
}


def _make_state_with_lesson(
    *,
    title: str = "Understand HTTPBasicAuth",
    concept_tags: list[str] | None = None,
    understand: str = "AuthBase subclasses are callables that mutate and return a PreparedRequest.",
) -> tuple[OnboardState, str]:
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    node = graph.add_node(LearningNode(
        title=title,
        code_anchor=CodeAnchor(file="requests/auth.py", line_start=72, line_end=100),
        concept_tags=list(concept_tags or ["extension_point", "auth"]),
        lesson_brief={"why": "why-text", "understand": understand},
    ))
    node.cached_lesson = FAKE_LESSON
    graph.set_current(node.id)
    state = OnboardState(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    state.graph = graph
    return state, node.id


def _mock_client(classification: str, rationale: str = "because") -> MagicMock:
    payload = json.dumps({"classification": classification, "rationale": rationale})
    message = MagicMock()
    message.content = [MagicMock(text=payload)]
    client = MagicMock()
    client.messages.create.return_value = message
    return client


# ── classification → node state ───────────────────────────────────────────────

def test_understood_marks_node_understood():
    state, node_id = _make_state_with_lesson()
    run(state, "It returns the mutated PreparedRequest", client=_mock_client("understood"))
    assert state.graph.nodes[node_id].understanding_state == "understood"
    assert state.last_grade["classification"] == "understood"


def test_partial_marks_node_partial():
    state, node_id = _make_state_with_lesson()
    run(state, "It changes the request somehow", client=_mock_client("partial"))
    assert state.graph.nodes[node_id].understanding_state == "partial"


def test_confused_marks_not_yet_and_sets_weak_spot():
    state, node_id = _make_state_with_lesson()
    run(state, "It opens a socket?", client=_mock_client("confused"))
    node = state.graph.nodes[node_id]
    assert node.understanding_state == "not-yet"
    assert node.weak_spot is True


def test_off_topic_leaves_understanding_state_unchanged():
    state, node_id = _make_state_with_lesson()
    before = state.graph.nodes[node_id].understanding_state  # "not-yet" default
    run(state, "what's for lunch", client=_mock_client("off-topic"))
    node = state.graph.nodes[node_id]
    assert node.understanding_state == before
    assert node.weak_spot is False
    assert state.last_grade["classification"] == "off-topic"


def test_uses_haiku_model():
    state, _ = _make_state_with_lesson()
    client = _mock_client("understood")
    run(state, "answer", client=client)
    assert client.messages.create.call_args.kwargs["model"] == "claude-haiku-4-5"


def test_prompt_and_expected_answer_sent_to_model():
    state, _ = _make_state_with_lesson()
    client = _mock_client("understood")
    run(state, "my answer", client=client)
    user_msg = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert FAKE_LESSON["prompt"] in user_msg
    assert FAKE_LESSON["expected_answer"] in user_msg
    assert "my answer" in user_msg


def test_node_title_tags_and_takeaway_sent_to_model():
    state, _ = _make_state_with_lesson(
        title="Identify the AuthBase extension point",
        concept_tags=["extension_point", "auth"],
        understand="AuthBase is the seam for custom auth — subclass it.",
    )
    client = _mock_client("understood")
    run(state, "yes — subclass AuthBase", client=client)
    user_msg = client.messages.create.call_args.kwargs["messages"][0]["content"]
    # The Grader needs to know what KIND of understanding to evaluate.
    assert "Identify the AuthBase extension point" in user_msg
    assert "extension_point" in user_msg
    assert "AuthBase is the seam for custom auth" in user_msg


def test_node_with_no_tags_or_brief_still_renders_user_content():
    # Defensive: nodes built outside the new-vocabulary path still grade.
    state, _ = _make_state_with_lesson(
        concept_tags=[],
        understand="",
    )
    state.graph.nodes[state.graph.current_node_id].concept_tags = []
    state.graph.nodes[state.graph.current_node_id].lesson_brief = {}
    client = _mock_client("understood")
    run(state, "answer", client=client)
    user_msg = client.messages.create.call_args.kwargs["messages"][0]["content"]
    # Falls back to a "(none)" / "(none provided)" line rather than crashing.
    assert "(none)" in user_msg
    assert "(none provided)" in user_msg


def test_system_prompt_includes_per_tag_rubric():
    # Regression guard: the per-tag rubric block is the load-bearing change
    # for the new product direction. If a future edit drops it, the demo's
    # CONFUSED-on-flow-node story silently regresses to a generic rubric.
    for tag in (
        "architecture",
        "flow",
        "extension_point",
        "risk",
        "test_coverage",
        "component",
    ):
        assert tag in _SYSTEM_PROMPT


def test_system_prompt_frames_as_system_level_not_code_comprehension():
    # The opening line was reframed away from "comprehension question about
    # code" toward system-level / understanding-graph framing.
    assert "system-level" in _SYSTEM_PROMPT
    assert "understanding graph" in _SYSTEM_PROMPT
    assert "comprehension question about code" not in _SYSTEM_PROMPT


# ── graceful fallback ─────────────────────────────────────────────────────────

def test_parse_failure_defaults_to_partial():
    state, node_id = _make_state_with_lesson()
    bad = MagicMock()
    bad.content = [MagicMock(text="not json at all")]
    client = MagicMock()
    client.messages.create.return_value = bad

    run(state, "answer", client=client)

    assert state.last_grade["classification"] == "partial"
    assert state.graph.nodes[node_id].understanding_state == "partial"
    assert any("defaulting to partial" in e for e in state.errors)


# ── error paths ───────────────────────────────────────────────────────────────

def test_errors_when_graph_missing():
    state = OnboardState(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    run(state, "answer", client=MagicMock())
    assert state.last_grade is None
    assert any("graph missing" in e for e in state.errors)


def test_errors_when_no_current_node():
    state = OnboardState(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    state.graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    run(state, "answer", client=MagicMock())
    assert state.last_grade is None
    assert any("no current node" in e for e in state.errors)


def test_errors_when_node_has_no_lesson():
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    node = graph.add_node(LearningNode(
        title="X", code_anchor=CodeAnchor(file="a.py", line_start=1, line_end=5),
    ))
    graph.set_current(node.id)  # no cached_lesson
    state = OnboardState(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    state.graph = graph
    client = MagicMock()
    run(state, "answer", client=client)
    assert state.last_grade is None
    assert any("no lesson to grade" in e for e in state.errors)
    client.messages.create.assert_not_called()


# ── parsing ───────────────────────────────────────────────────────────────────

def test_parse_output_handles_fenced_json():
    fenced = '```json\n{"classification": "understood", "rationale": "ok"}\n```'
    out = _parse_output(fenced)
    assert isinstance(out, GraderOutput)
    assert out.classification == "understood"
