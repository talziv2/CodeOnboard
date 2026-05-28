"""
Pytest tests for the Mentor mutator (Phase 3 Part 6).
Run with: uv run pytest tests/test_mutator.py -v

retrieve_supporting_chunks and the Sonnet client are mocked.
"""
import json
from unittest.mock import MagicMock, patch

from backend.agents.mentor.mutator import mutate
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.pipeline.state import OnboardState


FAKE_REPO_URL = "https://github.com/psf/requests"
FAKE_GOAL = {"primary_goal": "x", "goal_type": "understand_component"}

# A candidate chunk the mutator can ground a generated prerequisite on.
FAKE_CANDIDATES = [
    {
        "file": "requests/models.py",
        "start_line": 10,
        "end_line": 40,
        "type": "class",
        "name": "PreparedRequest",
        "role": "source",
        "content": "class PreparedRequest: ...",
    },
]

FAKE_PREREQ_NODE = {
    "title": "Understand PreparedRequest",
    "file": "requests/models.py",
    "line_start": 10,
    "line_end": 40,
    "why": "auth handlers mutate a PreparedRequest, so you must know it first",
    "understand": "what fields a PreparedRequest carries",
    "concept_tags": ["request model"],
}


def _make_state() -> tuple[OnboardState, LearningGraph, str, str]:
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    a = graph.add_node(LearningNode(
        title="A", code_anchor=CodeAnchor(file="requests/a.py", line_start=1, line_end=5),
    ))
    x = graph.add_node(LearningNode(
        title="Understand HTTPBasicAuth",
        code_anchor=CodeAnchor(file="requests/auth.py", line_start=72, line_end=100),
        concept_tags=["request signing"],
        lesson_brief={"why": "core auth", "understand": "how __call__ signs"},
    ))
    graph.add_edge(a.id, x.id, kind="sequence")
    graph.set_current(x.id)  # current = the (soon-to-be-confused) node X
    state = OnboardState(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    state.repo_path = "data/repos/requests"
    state.graph = graph
    return state, graph, a.id, x.id


def _mock_client(node_json: dict) -> MagicMock:
    message = MagicMock()
    message.content = [MagicMock(text=json.dumps(node_json))]
    client = MagicMock()
    client.messages.create.return_value = message
    return client


# ── prerequisite insertion ────────────────────────────────────────────────────

@patch("backend.agents.mentor.mutator.retrieve_supporting_chunks", return_value=FAKE_CANDIDATES)
def test_prerequisite_inserts_node_before_current(mock_retrieve):
    state, graph, a_id, x_id = _make_state()
    client = _mock_client(FAKE_PREREQ_NODE)

    mutate(state, "prerequisite", client=client)

    assert state.last_mutation["kind"] == "prerequisite"
    new_id = state.last_mutation["new_node_id"]
    assert new_id in graph.nodes
    assert graph.nodes[new_id].title == "Understand PreparedRequest"
    # Current now points at the prerequisite (taught first).
    assert graph.current_node_id == new_id
    # The walk: prereq → X (so the user returns to the confused node after).
    assert graph.next_in_path(new_id) == x_id
    # And A now flows into the prereq, not directly into X.
    assert graph.next_in_path(a_id) == new_id


@patch("backend.agents.mentor.mutator.retrieve_supporting_chunks", return_value=FAKE_CANDIDATES)
def test_prerequisite_uses_sonnet(mock_retrieve):
    state, *_ = _make_state()
    client = _mock_client(FAKE_PREREQ_NODE)
    mutate(state, "prerequisite", client=client)
    assert client.messages.create.call_args.kwargs["model"] == "claude-sonnet-4-6"


@patch("backend.agents.mentor.mutator.retrieve_supporting_chunks", return_value=FAKE_CANDIDATES)
def test_prerequisite_guard_no_double_insert(mock_retrieve):
    state, graph, a_id, x_id = _make_state()
    client = _mock_client(FAKE_PREREQ_NODE)

    mutate(state, "prerequisite", client=client)
    nodes_after_first = len(graph.nodes)

    # Confused again on the same node (current was moved to the prereq; move
    # it back to X to simulate the user returning and being confused again).
    graph.set_current(x_id)
    mutate(state, "prerequisite", client=client)

    assert state.last_mutation["kind"] == "none"
    assert state.last_mutation["reason"] == "prerequisite_exists"
    assert len(graph.nodes) == nodes_after_first  # no second prereq


@patch("backend.agents.mentor.mutator.retrieve_supporting_chunks", return_value=[])
def test_prerequisite_no_candidates_is_noop(mock_retrieve):
    state, graph, a_id, x_id = _make_state()
    before = len(graph.nodes)
    mutate(state, "prerequisite", client=MagicMock())
    assert state.last_mutation["kind"] == "none"
    assert len(graph.nodes) == before


@patch("backend.agents.mentor.mutator.retrieve_supporting_chunks", return_value=FAKE_CANDIDATES)
def test_prerequisite_ungrounded_anchor_is_rejected(mock_retrieve):
    # Sonnet returns an anchor that isn't among the candidates → no insert.
    state, graph, a_id, x_id = _make_state()
    bad_node = {**FAKE_PREREQ_NODE, "file": "requests/hallucinated.py", "line_start": 999, "line_end": 1000}
    client = _mock_client(bad_node)
    before = len(graph.nodes)

    mutate(state, "prerequisite", client=client)

    assert state.last_mutation["kind"] == "none"
    assert len(graph.nodes) == before
    assert any("not in candidates" in e for e in state.errors)


@patch("backend.agents.mentor.mutator.retrieve_supporting_chunks", return_value=FAKE_CANDIDATES)
def test_prerequisite_llm_failure_is_noop(mock_retrieve):
    state, graph, *_ = _make_state()
    client = MagicMock()
    client.messages.create.side_effect = Exception("sonnet down")
    before = len(graph.nodes)

    mutate(state, "prerequisite", client=client)

    assert state.last_mutation["kind"] == "none"
    assert len(graph.nodes) == before
    assert any("generation failed" in e for e in state.errors)


# ── skip (pure Python) ────────────────────────────────────────────────────────

def test_skip_marks_visited_and_advances():
    state, graph, a_id, x_id = _make_state()
    # current is X; X has no next → skipping X advances to None.
    # Put current on A so there's somewhere to advance to.
    graph.set_current(a_id)
    mutate(state, "skip")
    assert graph.nodes[a_id].visited is True
    assert graph.nodes[a_id].user_override == "skip"
    assert graph.current_node_id == x_id
    assert state.last_mutation["kind"] == "skip"


def test_skip_does_not_call_llm():
    state, graph, a_id, x_id = _make_state()
    graph.set_current(a_id)
    # No client passed — skip must not need one.
    mutate(state, "skip")
    assert state.last_mutation["kind"] == "skip"


# ── dispatcher guards ─────────────────────────────────────────────────────────

def test_mutate_no_graph_is_noop():
    state = OnboardState(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    mutate(state, "skip")
    assert state.last_mutation["kind"] == "none"
    assert any("graph missing" in e for e in state.errors)


def test_mutate_unknown_signal():
    state, *_ = _make_state()
    mutate(state, "teleport", client=MagicMock())
    assert state.last_mutation["kind"] == "none"
    assert any("unknown signal" in e for e in state.errors)
