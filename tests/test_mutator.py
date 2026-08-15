"""
Pytest tests for the Mentor mutator (Phase 3 Part 6).
Run with: uv run pytest tests/test_mutator.py -v

The candidate pool and the Sonnet client are mocked. `candidate_pool` is the
seam because it is where the two grounded evidence sources (Dossier, then
Skeleton) are combined — there is no retrieval below it any more.
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from backend.repo.dossier_context import PrereqCandidate
from backend.repo.skeleton import Skeleton
from backend.agents.mentor.mutator import (
    _PREREQ_SYSTEM_PROMPT,
    _build_prereq_prompt,
    mutate,
)
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

# What `candidate_pool` hands the selection step: structural candidates, whose
# source is read from the repository at the resolved anchor.
FAKE_POOL = [
    PrereqCandidate(
        file="requests/models.py", symbol="PreparedRequest",
        source="calls", rationale="the confused node builds one of these",
    ),
]

# Stage 0: a generated prerequisite is verified against the REPOSITORY (a
# Skeleton) as well as against the candidate chunks. Tests supply a synthetic
# Layer-A index covering the candidate file.
def _fake_skeleton() -> Skeleton:
    return Skeleton.from_chunks(
        [{**c, "content": None} for c in FAKE_CANDIDATES],
        file_lines={"requests/models.py": 900},
    )


@pytest.fixture(autouse=True)
def _patch_skeleton():
    # Rendering a candidate reads its source from the checkout, and a synthetic
    # skeleton has none — so the render step is stubbed to hand back the fake
    # chunks whenever the pool is non-empty. What these tests are about is the
    # selection and grounding that happen after rendering, not rendering itself.
    with patch(
        "backend.agents.mentor.mutator.build_skeleton",
        side_effect=lambda repo_path: _fake_skeleton(),
    ), patch(
        "backend.agents.mentor.mutator._candidates_as_chunks",
        side_effect=lambda repo_path, pool: FAKE_CANDIDATES if pool else [],
    ):
        yield


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

@patch("backend.agents.mentor.mutator.candidate_pool", return_value=FAKE_POOL)
def test_prerequisite_inserts_node_before_current(mock_pool):
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


@patch("backend.agents.mentor.mutator.candidate_pool", return_value=FAKE_POOL)
def test_prerequisite_uses_sonnet(mock_pool):
    state, *_ = _make_state()
    client = _mock_client(FAKE_PREREQ_NODE)
    mutate(state, "prerequisite", client=client)
    assert client.messages.create.call_args.kwargs["model"] == "claude-sonnet-4-6"


@patch("backend.agents.mentor.mutator.candidate_pool", return_value=FAKE_POOL)
def test_prerequisite_guard_no_double_insert(mock_pool):
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


@patch("backend.agents.mentor.mutator.candidate_pool", return_value=[])
def test_prerequisite_no_candidates_is_noop(mock_pool):
    state, graph, a_id, x_id = _make_state()
    before = len(graph.nodes)
    mutate(state, "prerequisite", client=MagicMock())
    assert state.last_mutation["kind"] == "none"
    assert len(graph.nodes) == before


@patch("backend.agents.mentor.mutator.candidate_pool", return_value=FAKE_POOL)
def test_prerequisite_ungrounded_anchor_is_rejected(mock_pool):
    # Sonnet returns an anchor that isn't among the candidates → no insert.
    state, graph, a_id, x_id = _make_state()
    bad_node = {**FAKE_PREREQ_NODE, "file": "requests/hallucinated.py", "line_start": 999, "line_end": 1000}
    client = _mock_client(bad_node)
    before = len(graph.nodes)

    mutate(state, "prerequisite", client=client)

    assert state.last_mutation["kind"] == "none"
    assert len(graph.nodes) == before
    assert any("not in candidates" in e for e in state.errors)


@patch("backend.agents.mentor.mutator.candidate_pool", return_value=FAKE_POOL)
def test_prerequisite_llm_failure_is_noop(mock_pool):
    state, graph, *_ = _make_state()
    client = MagicMock()
    client.messages.create.side_effect = Exception("sonnet down")
    before = len(graph.nodes)

    mutate(state, "prerequisite", client=client)

    assert state.last_mutation["kind"] == "none"
    assert len(graph.nodes) == before
    assert any("generation failed" in e for e in state.errors)


@patch("backend.agents.mentor.mutator.candidate_pool", return_value=FAKE_POOL)
def test_declining_to_insert_is_an_answer_not_a_failure(mock_pool):
    """Success is not "always insert something".

    Candidates were offered and none was a smaller foundation than the node the
    developer is already on. Padding the path to look responsive is worse than
    leaving it alone, and the outcome must be distinguishable from a breakage.
    """
    state, graph, _, _ = _make_state()
    client = _mock_client({"decision": "none", "reason": "already the simplest step"})
    before = len(graph.nodes)

    mutate(state, "prerequisite", client=client)

    assert state.last_mutation["kind"] == "none"
    assert state.last_mutation["reason"] == "no_useful_prerequisite"
    # The reason is kept, not discarded — it is the most useful thing the system
    # can say about a confusion it deliberately chose not to act on.
    assert state.last_mutation["rationale"] == "already the simplest step"
    assert len(graph.nodes) == before
    assert not state.errors        # declining is not an error condition


@patch("backend.agents.mentor.mutator.candidate_pool", return_value=[])
def test_an_empty_pool_is_reported_as_a_different_outcome(mock_pool):
    """"I found nothing to offer" and "I judged none useful" are not the same."""
    state, graph, _, _ = _make_state()
    mutate(state, "prerequisite", client=MagicMock())
    assert state.last_mutation["reason"] == "generation_failed"
    assert state.last_mutation["reason"] != "no_useful_prerequisite"


def test_the_prompt_offers_declining_as_a_legal_answer():
    prompt = " ".join(_PREREQ_SYSTEM_PROMPT.split())
    assert '"decision": "none"' in prompt
    assert "not required to insert something" in prompt


def test_the_mutator_holds_no_retrieval_dependency():
    """Stage 5 precondition: the candidate pool is Dossier + Skeleton, nothing else.

    `backend.repo.cloner` is fine and deliberately not caught here — it is a git
    clone helper that survives Stage 5. What must be gone is retrieval.
    """
    import pathlib

    import backend.agents.mentor.mutator as module

    source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
    assert "retrieve_supporting_chunks" not in source
    assert "backend.rag.retrieval" not in source


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


# ── prereq prompt: developer profile + background tiebreaker ─────────────────


def test_prereq_prompt_includes_developer_profile_fields():
    anchor = LearningNode(
        title="A confused node",
        code_anchor=CodeAnchor(file="a.py", line_start=1, line_end=5),
        concept_tags=["request signing"],
        lesson_brief={"why": "x", "understand": "y"},
    )
    goal = {
        "familiarity": "Skimmed the README or docs",
        "background": "Embedded C++, learning Python",
    }
    prompt = _build_prereq_prompt(anchor, FAKE_CANDIDATES, goal)
    # Both profile lines must reach the Mutator so background can act as a
    # tiebreaker. `experience_level` used to be a third: it was invented by
    # Haiku from answers that never mentioned it, and is gone.
    assert "Skimmed the README or docs" in prompt
    assert "Embedded C++, learning Python" in prompt
    assert "experience" not in prompt


def test_prereq_system_prompt_has_background_tiebreaker_rule():
    # Background is a tiebreaker, not a primary signal — the rule must say so
    # to avoid the LLM picking a "background-appropriate" prereq that doesn't
    # actually unblock the confused node.
    assert "TIEBREAKER" in _PREREQ_SYSTEM_PROMPT or "tiebreaker" in _PREREQ_SYSTEM_PROMPT.lower()


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


# ── Stage 0: repository-backed grounding, unchanged evidence scope ────────────


@patch("backend.agents.mentor.mutator.candidate_pool")
def test_prerequisite_records_the_resolved_symbol(mock_pool):
    mock_pool.return_value = FAKE_POOL
    state, graph, _, x_id = _make_state()
    client = _mock_client(FAKE_PREREQ_NODE)

    mutate(state, "prerequisite", client=client)

    new_id = state.last_mutation["new_node_id"]
    assert graph.nodes[new_id].code_anchor.symbol == "PreparedRequest"


@patch("backend.agents.mentor.mutator.candidate_pool")
def test_prerequisite_on_real_but_unoffered_code_is_rejected(mock_pool):
    """Stage-0 boundary for the Mutator.

    utils.py:5-20 is in the skeleton, so it resolves as real. It was not among
    the candidate chunks Sonnet was offered, so it must not become a
    prerequisite: an invented location is worse than no remediation.
    """
    skeleton_with_extra = Skeleton.from_chunks(
        [{**c, "content": None} for c in FAKE_CANDIDATES]
        + [{"file": "requests/utils.py", "start_line": 5, "end_line": 20,
            "type": "function", "name": "guess_json_utf", "role": "source"}],
        file_lines={"requests/models.py": 900, "requests/utils.py": 400},
    )
    mock_pool.return_value = FAKE_POOL
    unoffered = {**FAKE_PREREQ_NODE, "file": "requests/utils.py",
                 "line_start": 5, "line_end": 20}
    state, graph, _, x_id = _make_state()
    client = _mock_client(unoffered)
    before = len(graph.nodes)

    with patch(
        "backend.agents.mentor.mutator.build_skeleton",
        side_effect=lambda repo_path: skeleton_with_extra,
    ):
        mutate(state, "prerequisite", client=client)

    assert len(graph.nodes) == before, "no node may be inserted"
    assert state.last_mutation["kind"] == "none"
    assert any("not in candidates" in e for e in state.errors)


@patch("backend.agents.mentor.mutator.candidate_pool", return_value=FAKE_POOL)
def test_an_inserted_warm_up_is_marked_required(mock_pool):
    """A warm-up the learner demonstrably needed is not up for demotion.

    Scope control's "make it shorter" moves the `recommended` bucket, so marking
    remediation `required` keeps it out of reach explicitly rather than by the
    accident of an absent key.
    """
    from backend.learning import scope

    state, graph, _, _ = _make_state()
    mutate(state, "prerequisite", client=_mock_client(FAKE_PREREQ_NODE))

    new_id = state.last_mutation["new_node_id"]
    assert graph.nodes[new_id].lesson_brief["priority"] == "required"
    assert new_id not in scope.shorten(graph)
