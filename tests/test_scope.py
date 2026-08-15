"""
Pytest tests for U4 — scope control (backend/learning/scope.py).
Run with: uv run pytest tests/test_scope.py -v

No client and no API key: scope control moves existing units between priority
buckets and is pure Python. What must hold is that it cannot damage the
curriculum — `required` is untouchable, dependency closure survives, traversal
stays correct, and adaptation never silently undoes what the learner chose.
"""
import pytest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import backend.api as api
from backend.learning import scope
from backend.learning.adaptation import prune_ahead
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode


def _graph(units: list[tuple[str, str, str]]) -> LearningGraph:
    """units: (area_id, priority, understanding_state), chained in order."""
    graph = LearningGraph(repo_url="r", goal={})
    previous = None
    for i, (area, priority, state) in enumerate(units):
        node = graph.add_node(LearningNode(
            title=f"n{i}",
            code_anchor=CodeAnchor(file="a.py", line_start=1, line_end=2),
            lesson_brief={"area_id": area, "priority": priority, "objective": "x"},
        ))
        node.understanding_state = state
        if state != "not_started":
            node.visited = True
        if previous:
            graph.add_edge(previous.id, node.id, kind="sequence")
        previous = node
    graph.set_current(graph.path_order()[0])
    return graph


def priorities(graph: LearningGraph) -> list[str]:
    return [graph.nodes[i].lesson_brief["priority"] for i in graph.path_order()]


# ── shorter ───────────────────────────────────────────────────────────────────

def test_shorter_demotes_the_recommended_bucket():
    graph = _graph([
        ("a1", "required", "not_started"),
        ("a1", "recommended", "not_started"),
        ("a1", "recommended", "not_started"),
    ])
    assert len(scope.shorten(graph)) == 2
    assert priorities(graph) == ["required", "optional", "optional"]


def test_shorter_never_touches_required():
    # The required set is the curriculum's floor: removing any of it leaves a
    # journey that cannot deliver the goal it was planned for.
    graph = _graph([("a1", "required", "not_started")] * 4)
    assert scope.shorten(graph) == []
    assert priorities(graph) == ["required"] * 4


def test_shorter_cannot_break_dependency_closure():
    # `select()` promotes every dependency of a required unit INTO the required
    # set, so nothing still required can depend on what `shorter` demotes.
    graph = _graph([
        ("a1", "required", "not_started"),
        ("a1", "required", "not_started"),
        ("a1", "recommended", "not_started"),
    ])
    order = graph.path_order()
    graph.add_edge(order[0], order[1], kind="prerequisite")
    scope.shorten(graph)

    still_required = {i for i in order if graph.nodes[i].lesson_brief["priority"] == "required"}
    for edge in graph.edges:
        if edge.kind == "prerequisite" and edge.to_node_id in still_required:
            assert edge.from_node_id in still_required


def test_shorter_leaves_work_already_done_alone():
    # Re-labelling a unit the learner already walked would rewrite their history.
    graph = _graph([
        ("a1", "recommended", "understood"),
        ("a1", "recommended", "not_started"),
    ])
    assert len(scope.shorten(graph)) == 1
    assert priorities(graph) == ["recommended", "optional"]


def test_shorter_shortens_the_walked_journey_not_just_the_label():
    graph = _graph([
        ("a1", "required", "not_started"),
        ("a1", "recommended", "not_started"),
    ])
    assert scope.journey_size(graph) == 2
    scope.shorten(graph)
    assert scope.journey_size(graph) == 1


# ── deeper ────────────────────────────────────────────────────────────────────

def test_deeper_promotes_existing_optional_material():
    graph = _graph([
        ("a1", "required", "not_started"),
        ("a1", "optional", "not_started"),
    ])
    assert len(scope.deepen(graph)) == 1
    assert priorities(graph) == ["required", "recommended"]


def test_deeper_generates_nothing_when_there_is_nothing_left():
    # A journey with no optional material has nothing further to offer. Saying so
    # is the honest answer; inventing a unit would be a second planning system.
    graph = _graph([("a1", "required", "not_started")] * 3)
    before = len(graph.nodes)
    assert scope.deepen(graph) == []
    assert len(graph.nodes) == before


def test_deeper_is_the_exact_inverse_of_shorter():
    graph = _graph([
        ("a1", "required", "not_started"),
        ("a1", "recommended", "not_started"),
        ("a1", "recommended", "not_started"),
    ])
    before = priorities(graph)
    scope.shorten(graph)
    scope.deepen(graph)
    assert priorities(graph) == before


# ── the user's choice is not silently undone ──────────────────────────────────

def test_prune_ahead_does_not_re_demote_what_the_learner_promoted():
    # The silent undo §9.2 forbids: prune-ahead demotes in the same direction as
    # `shorter`, so without the lock it would quietly re-take a unit the learner
    # had just asked to keep.
    graph = _graph([
        ("a1", "required", "understood"),
        ("a1", "required", "understood"),
        ("a1", "optional", "not_started"),
    ])
    scope.deepen(graph)
    assert priorities(graph)[2] == "recommended"

    assert prune_ahead(graph) == []
    assert priorities(graph)[2] == "recommended"


def test_an_unlocked_unit_is_still_prunable():
    # The lock is targeted, not a blanket exemption for the whole graph.
    graph = _graph([
        ("a1", "required", "understood"),
        ("a1", "required", "understood"),
        ("a1", "recommended", "not_started"),
    ])
    assert len(prune_ahead(graph)) == 1


def test_scope_changes_are_marked_as_the_learners_own():
    graph = _graph([("a1", "recommended", "not_started")])
    moved = scope.shorten(graph)
    assert scope.is_locked(graph, moved[0])


# ── traversal and resume ──────────────────────────────────────────────────────

def test_resume_skips_optional_units():
    # Returning someone into a unit that is not on their journey would resume a
    # path they never left.
    graph = _graph([
        ("a1", "required", "understood"),
        ("a1", "optional", "not_started"),
        ("a1", "required", "not_started"),
    ])
    order = graph.path_order()
    assert graph.resume_point() == order[2]


def test_optional_units_stay_in_the_graph_and_in_walk_order():
    # Collapsed in the rail and stepped over by advance — never deleted, and
    # still reachable deliberately.
    graph = _graph([
        ("a1", "required", "not_started"),
        ("a1", "recommended", "not_started"),
    ])
    scope.shorten(graph)
    assert len(graph.nodes) == 2
    assert len(graph.path_order()) == 2


def test_readiness_rises_when_the_journey_is_shortened():
    # Shortening must not punish the learner: the same understanding over a
    # smaller journey is more progress, not less.
    graph = _graph([
        ("a1", "required", "understood"),
        ("a1", "recommended", "not_started"),
        ("a1", "recommended", "not_started"),
    ])
    before = graph.readiness()
    scope.shorten(graph)
    assert graph.readiness() > before


# ── through the endpoint ──────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _env_and_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(api, "SESSIONS_DB_PATH", tmp_path / "sessions.db")
    monkeypatch.setattr(api.anthropic, "Anthropic", lambda **kw: MagicMock())


@pytest.fixture
def client():
    return TestClient(api.app)


def _persisted(graph) -> str:
    api.learning_store.save_graph(graph, api.SESSIONS_DB_PATH)
    return graph.session_id


def test_the_endpoint_reports_what_it_moved(client):
    sid = _persisted(_graph([
        ("a1", "required", "not_started"),
        ("a1", "recommended", "not_started"),
    ]))
    body = client.post(f"/session/{sid}/scope", json={"direction": "shorter"}).json()

    assert body["applied"] is True
    assert body["changed"] == 1
    assert body["journey_size_before"] == 2
    assert body["journey_size"] == 1


def test_the_endpoint_says_plainly_when_there_is_nothing_to_do(client):
    sid = _persisted(_graph([("a1", "required", "not_started")]))
    body = client.post(f"/session/{sid}/scope", json={"direction": "deeper"}).json()

    assert body["applied"] is False
    assert body["changed"] == 0


def test_an_unsupported_direction_is_rejected(client):
    sid = _persisted(_graph([("a1", "required", "not_started")]))
    resp = client.post(f"/session/{sid}/scope", json={"direction": "sideways"})
    assert resp.status_code == 400


def test_scope_survives_a_round_trip(client):
    sid = _persisted(_graph([
        ("a1", "required", "not_started"),
        ("a1", "recommended", "not_started"),
    ]))
    client.post(f"/session/{sid}/scope", json={"direction": "shorter"})

    graph = client.get(f"/session/{sid}").json()
    demoted = [n for n in graph["nodes"] if n["priority"] == "optional"]
    assert len(demoted) == 1


def _teaching(state, client=None):
    node = state.graph.nodes[state.graph.current_node_id]
    node.cached_lesson = {"walkthrough": "w", "prompt": "q", "expected_answer": "a"}
    state.current_lesson = node.cached_lesson
    return state


@patch("backend.api.clone_repo", return_value="data/repos/x")
@patch("backend.api.run_teaching", side_effect=_teaching)
def test_advance_steps_over_an_optional_unit(mock_teach, mock_clone, client):
    # The mismatch this closes: the counter has always excluded optional units,
    # so walking into one contradicted the number on screen.
    graph = _graph([
        ("a1", "required", "not_started"),
        ("a1", "optional", "not_started"),
        ("a1", "required", "not_started"),
    ])
    order = graph.path_order()
    sid = _persisted(graph)

    body = client.post(
        f"/session/{sid}/advance", json={"signal": "next", "node_id": order[0]}
    ).json()

    assert body["node_id"] == order[2]


def test_a_unit_with_no_priority_is_treated_as_part_of_the_journey():
    """Pre-B3 nodes, and warm-ups written before priority was set on them.

    Absent is not `optional`: such a unit stays on the walk, counts toward the
    journey, and `shorter` leaves it alone because it is not in the
    `recommended` bucket. Pinned because scope control now depends on it.
    """
    graph = LearningGraph(repo_url="r", goal={})
    node = graph.add_node(LearningNode(
        title="legacy",
        code_anchor=CodeAnchor(file="a.py", line_start=1, line_end=2),
        lesson_brief={"why": "x", "understand": "y"},   # no priority at all
    ))
    graph.set_current(node.id)

    assert scope.shorten(graph) == []
    assert scope.deepen(graph) == []
    assert scope.journey_size(graph) == 1
    assert graph.is_optional(node) is False
