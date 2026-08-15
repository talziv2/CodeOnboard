"""The warm-up is chosen for the diagnosed misconception, not just for the node.

learning-engine.md §18.2. `hint`, `followup` and `reteach` have always received
the learner's answer and the Grader's rationale; `prerequisite` — the only
adaptation that reshapes the graph — received neither, and selected from
structural candidates alone.

The failure shape used here is the real one that exposed it (session `9d432157`,
node `63644c89`, AIMA `search.py`): one answer carrying TWO independent
misconceptions about `Node.expand()` and `solution()`. Acting on both is the
follow-up phase (§18.3–18.10); what is pinned here is that the text describing
both now reaches the Mutator instead of being dropped at the boundary.

Run with: uv run pytest tests/test_prerequisite_diagnosis.py -v
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from backend.agents.mentor.mutator import (
    _PREREQ_SYSTEM_PROMPT,
    Diagnosis,
    _build_prereq_prompt,
    mutate,
)
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.pipeline.state import OnboardState
from backend.repo.dossier_context import PrereqCandidate
from backend.repo.skeleton import Skeleton


FAKE_REPO_URL = "https://github.com/aimacode/aima-python"
FAKE_GOAL = {"primary_goal": "understand search", "goal_type": "understand_component"}

# The two misconceptions, verbatim from the live answer that exposed the defect.
GAP_A = "its `path_cost` and `depth` are recalculated later by the search algorithm"
GAP_B = "it collects both the states and actions stored in each Node"
LIVE_ANSWER = (
    "When `node.expand(problem)` is called, it asks the Problem for the available "
    "actions using `problem.actions(state)`. For each action, it calls "
    "`problem.result(state, action)` and creates a child `Node`. The child stores "
    f"the resulting state and the action that produced it, but {GAP_A} rather than "
    "during expansion. When `solution()` is later called on a goal node, it follows "
    f"the `parent` references backward from the goal node until it reaches the root. "
    f"As it walks backward, {GAP_B}. It then returns these in reverse order."
)
LIVE_RATIONALE = (
    "The developer correctly identifies the two Problem methods (actions and result) "
    "and traces the backward walk through parents, but fundamentally misunderstands "
    "WHEN path_cost and depth are computed—claiming they are 'recalculated later by "
    "the search algorithm' rather than set during child_node() construction, and "
    "conflates the return value of solution() with what it reconstructs internally."
)

CANDIDATES = [
    {
        "file": "search.py", "start_line": 78, "end_line": 86,
        "type": "function", "name": "Node.__init__", "role": "source",
        "content": "def __init__(self, state, parent=None, action=None, path_cost=0): ...",
    },
]
POOL = [
    PrereqCandidate(
        file="search.py", symbol="Node.__init__",
        source="calls", rationale="the confused node constructs these",
    ),
]
PREREQ_JSON = {
    "title": "Understand what a Node stores at construction time",
    "file": "search.py", "line_start": 78, "line_end": 86,
    "objective": "I can name the five fields set during Node.__init__",
    "why": "expand() relies on the child being complete the moment it is built",
    "understand": "depth and path_cost are derived at construction",
    "concept_tags": ["component"],
}


@pytest.fixture(autouse=True)
def _patch_repo_reads():
    with patch(
        "backend.agents.mentor.mutator.build_skeleton",
        side_effect=lambda repo_path: Skeleton.from_chunks(
            [{**c, "content": None} for c in CANDIDATES],
            file_lines={"search.py": 1500},
        ),
    ), patch(
        "backend.agents.mentor.mutator._candidates_as_chunks",
        side_effect=lambda repo_path, pool: CANDIDATES if pool else [],
    ):
        yield


def _state(attempts: list[dict] | None = None) -> tuple[OnboardState, str]:
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    first = graph.add_node(LearningNode(
        title="Problem contract",
        code_anchor=CodeAnchor(file="search.py", line_start=15, line_end=62),
    ))
    node = graph.add_node(LearningNode(
        title="Understand Node as the universal search tree unit",
        code_anchor=CodeAnchor(file="search.py", line_start=68, line_end=130),
        concept_tags=["component", "flow"],
        lesson_brief={"why": "everything walks Nodes", "understand": "what a Node holds"},
    ))
    node.attempts = list(attempts or [])
    graph.add_edge(first.id, node.id, kind="sequence")
    graph.set_current(node.id)
    state = OnboardState(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    state.repo_path = "data/repos/aima"
    state.graph = graph
    return state, node.id


def _client() -> MagicMock:
    message = MagicMock()
    message.content = [MagicMock(text=json.dumps(PREREQ_JSON))]
    client = MagicMock()
    client.messages.create.return_value = message
    return client


def _prompt_sent(client: MagicMock) -> str:
    return client.messages.create.call_args.kwargs["messages"][0]["content"]


# ── the diagnosis reaches the selection step ─────────────────────────────────

@patch("backend.agents.mentor.mutator.candidate_pool", return_value=POOL)
def test_the_learner_answer_and_rationale_reach_the_prompt(pool):
    state, _ = _state()
    client = _client()
    mutate(state, "prerequisite", client=client, diagnosis=Diagnosis(
        answer=LIVE_ANSWER, rationale=LIVE_RATIONALE, gap_kind="wrong_model",
    ))
    sent = _prompt_sent(client)
    assert LIVE_ANSWER in sent
    assert LIVE_RATIONALE in sent
    assert "wrong_model" in sent


@patch("backend.agents.mentor.mutator.candidate_pool", return_value=POOL)
def test_both_misconceptions_survive_the_boundary(pool):
    """The bounded guarantee of this phase: the text is no longer dropped.

    Acting on both is §18.3–18.10 and deliberately NOT implemented here. What
    must not happen again is the Mutator being handed a node id and nothing else
    while the Grader had already diagnosed both.
    """
    state, _ = _state()
    client = _client()
    mutate(state, "prerequisite", client=client, diagnosis=Diagnosis(
        answer=LIVE_ANSWER, rationale=LIVE_RATIONALE, gap_kind="wrong_model",
    ))
    sent = _prompt_sent(client)
    assert GAP_A in sent, "the child-metadata misconception was dropped"
    assert GAP_B in sent, "the solution() misconception was dropped"


# ── /retry: no grade in scope, diagnosis comes off the node ──────────────────

@patch("backend.agents.mentor.mutator.candidate_pool", return_value=POOL)
def test_a_learner_requested_warm_up_recovers_the_diagnosis_from_attempts(pool):
    """`/retry` passes no diagnosis — the learner asked after answering.

    This is also the first real consumer of `node.attempts` in the codebase:
    until now the history was written and never read (§18.1, loss point 4).
    """
    state, _ = _state(attempts=[{
        "answer": LIVE_ANSWER, "classification": "partial",
        "gap_kind": "wrong_model", "rationale": LIVE_RATIONALE,
    }])
    client = _client()
    mutate(state, "prerequisite", client=client)  # no diagnosis passed
    sent = _prompt_sent(client)
    assert LIVE_ANSWER in sent
    assert LIVE_RATIONALE in sent


@patch("backend.agents.mentor.mutator.candidate_pool", return_value=POOL)
def test_the_latest_attempt_is_the_one_that_counts(pool):
    state, _ = _state(attempts=[
        {"answer": "an older wrong answer", "rationale": "old reason",
         "gap_kind": "no_attempt"},
        {"answer": LIVE_ANSWER, "rationale": LIVE_RATIONALE,
         "gap_kind": "wrong_model"},
    ])
    client = _client()
    mutate(state, "prerequisite", client=client)
    sent = _prompt_sent(client)
    assert LIVE_ANSWER in sent
    assert "an older wrong answer" not in sent


# ── the previous behaviour is preserved where there is nothing to say ────────

@patch("backend.agents.mentor.mutator.candidate_pool", return_value=POOL)
def test_no_attempts_and_no_diagnosis_still_generates_a_warm_up(pool):
    """A node reached with no history at all behaves exactly as before."""
    state, node_id = _state()
    client = _client()
    mutate(state, "prerequisite", client=client)
    assert state.last_mutation["kind"] == "prerequisite"
    sent = _prompt_sent(client)
    assert "What the developer actually wrote" not in sent


def test_an_empty_diagnosis_is_falsy_and_adds_nothing():
    """Whitespace is not a diagnosis — an empty block would be noise in the prompt."""
    assert not Diagnosis()
    assert not Diagnosis(answer="   ", rationale="")
    assert Diagnosis(answer="something")
    assert Diagnosis.from_attempt(None) is None
    assert Diagnosis.from_attempt({"answer": "", "rationale": ""}) is None
    assert Diagnosis.from_attempt({"answer": "x"}) is not None


def test_a_diagnosis_block_is_absent_when_none_is_known():
    prompt = _build_prereq_prompt(
        LearningNode(title="X", code_anchor=CodeAnchor(
            file="search.py", line_start=1, line_end=2)),
        CANDIDATES, FAKE_GOAL, structural=POOL, diagnosis=None,
    )
    assert "What the developer actually wrote" not in prompt
    assert "Why it fell short" not in prompt


# ── the diagnosis must not lower the foundational bar ────────────────────────

def test_the_prompt_still_requires_a_genuine_foundation():
    """§18.2: the diagnosis decides BETWEEN candidates, it does not relax the rule.

    A warm-up that speaks to the misconception but is a peer of the confused
    node is still the wrong answer — the decline path stays reachable.
    """
    # The prompt is hard-wrapped, so match against a whitespace-normalised copy.
    flat = " ".join(_PREREQ_SYSTEM_PROMPT.split())
    assert "genuinely MORE foundational" in flat
    assert "does not lower the bar" in flat
    assert '{"decision": "none"}' in flat
    # and the model is told not to simply echo the misconception back as a topic
    assert "Never repeat the misconception back as a lesson topic" in flat


@patch("backend.agents.mentor.mutator.candidate_pool", return_value=POOL)
def test_declining_still_works_when_a_diagnosis_is_present(pool):
    """A diagnosis must not pressure the model into inserting something."""
    message = MagicMock()
    message.content = [MagicMock(text=json.dumps(
        {"decision": "none", "reason": "every candidate is a peer, not a foundation"}
    ))]
    client = MagicMock()
    client.messages.create.return_value = message

    state, _ = _state()
    mutate(state, "prerequisite", client=client, diagnosis=Diagnosis(
        answer=LIVE_ANSWER, rationale=LIVE_RATIONALE, gap_kind="wrong_model",
    ))
    assert state.last_mutation["kind"] == "none"
    assert state.last_mutation["reason"] == "no_useful_prerequisite"
    assert "peer" in state.last_mutation["rationale"]
