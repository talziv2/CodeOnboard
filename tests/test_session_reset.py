"""Start over restores the plan and discards the walk.

Run with: uv run pytest tests/test_session_reset.py -v

M2 of session-reset.md. M1 made the plan exist; this is the restore.

## The acceptance assertion

`test_a_reset_graph_equals_a_graph_built_from_the_plan` is the phase's whole
claim, as one equality: simulate a full session against a planned graph — answers,
gaps in every status, a re-teach, a waiver, an override, prune-ahead, scope in
both directions, a spliced warm-up — reset, and the live graph's wire payload
equals the plan's, node for node and edge for edge.

Everything else here is either a property that equality cannot see (the plan is
still unmutated; no model was called) or a boundary case (a session with no plan,
a reset of a pristine session, a warm-up spliced before the head).

No network, no LLM, no API key: real SQLite against a temp file.
"""
import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import TEST_USER_ID
from fastapi.testclient import TestClient

import backend.api as api
from backend.learning import adaptation, history, scope
from backend.learning import store as learning_store
from backend.learning.gaps import Gap
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.learning.reset import ResetSummary, learner_state, reset_to_plan


REPO = "https://github.com/psf/requests"
GOAL = {"primary_goal": "understand sessions", "goal_type": "understand_component"}


@pytest.fixture
def db_path(tmp_path) -> Path:
    return tmp_path / "sessions.db"


def _lesson(marker: str) -> dict:
    return {"walkthrough": f"walkthrough {marker}", "prompt": f"about {marker}?",
            "expected_answer": marker, "prompt_kind": "predict-then-reveal"}


def _planned(db_path: Path) -> LearningGraph:
    """Four stops, one area, sequence plus a planned dependency. Lessons recorded."""
    graph = LearningGraph(
        repo_url=REPO, goal=GOAL,
        areas=[{"id": "a1", "title": "Sessions", "why": "core", "order": 1}],
    )
    for index, priority in enumerate(
        ["required", "required", "recommended", "recommended"], start=1
    ):
        graph.add_node(LearningNode(
            title=f"Stop {index}",
            code_anchor=CodeAnchor(file="requests/sessions.py", line_start=index * 10,
                                   line_end=index * 10 + 8, symbol=f"S.p{index}"),
            concept_tags=["component"],
            lesson_brief={"objective": f"explain stop {index}", "kind": "component",
                          "priority": priority, "area_id": "a1"},
        ))
    ids = list(graph.nodes)
    for a, b in zip(ids, ids[1:]):
        graph.add_edge(a, b, kind="sequence")
    graph.add_edge(ids[0], ids[2], kind="prerequisite")  # PLANNED dependency
    graph.set_current(ids[0])
    learning_store.create_session(graph, db_path, user_id=TEST_USER_ID)
    for index, node_id in enumerate(ids, start=1):
        learning_store.record_plan_lesson(
            graph.session_id, node_id, _lesson(f"stop{index}"), db_path
        )
    return graph


def _work_the_session(live: LearningGraph, node_ids: list[str]) -> Gap:
    """Every learner-driven mutation the live graph supports. Returns the open gap."""
    first, second, third, fourth = node_ids

    live.record_attempt(first, "a Session is a dict", "confused", "not quite",
                        gap_kind="wrong_model")
    live.mark_understanding(first, "failed")
    node = live.nodes[first]
    opened = Gap.create("wrong_model", "a Session is a dict of headers")
    verified = Gap.create("missing_prerequisite", "pooling is per-request")
    waived = Gap.create("wrong_model", "adapters are optional")
    verified.mark_verified(0)
    node.gap_state.gaps.extend([opened, verified, waived])
    node.gap_state.remediation_rounds = 3
    node.gap_state.pending_verification = {"question": "why reuse?",
                                           "targets": [opened.id], "at": "now"}
    # A re-teach replaces the live lesson; the original survives only in the plan.
    node.cached_lesson = _lesson("RETAUGHT")
    live.record_response(first, {"action": "reteach", "retaught": True,
                                 "superseded_lesson": _lesson("stop1")})
    live.waive_gap(first, waived.id)
    live.mark_visited(first)

    live.override(second, "skip")
    live.record_attempt(second, "an answer", "understood", "yes")
    live.mark_understanding(second, "understood")
    live.mark_understanding(third, "understood")
    live.mark_visited(third)

    # Scope and prune-ahead are recorded by the ENDPOINTS, not by the graph
    # helpers, so the events are written here exactly as `/scope` and `/respond`
    # write them. Without this the fixture would under-represent a real session's
    # history — which is the thing a reset has to clear.
    live.record_journey_event(history.SCOPE_SHORTER, nodes=scope.shorten(live))
    live.record_journey_event(history.SCOPE_DEEPER, nodes=scope.deepen(live))
    pruned = adaptation.prune_ahead(live)
    if pruned:
        live.record_journey_event(history.PRUNE_AHEAD, nodes=pruned)

    warm_up = LearningNode(
        title="What a connection pool is",
        code_anchor=CodeAnchor(file="requests/adapters.py", line_start=1, line_end=20),
        lesson_brief={"objective": "explain pooling", "priority": "required",
                      "origin": "system_remediation", "remediates": [opened.id]},
    )
    live.insert_before(first, warm_up, kind="prerequisite")
    live.set_current(warm_up.id)
    live.record_arrival(warm_up.id, kind="jumped", from_node_id=first)
    live.record_journey_event(history.JUMPED, nodes=[warm_up.id], from_node_id=first)
    return opened


def _plan_rows(db_path: Path) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        return [tuple(r) for r in conn.execute(
            "SELECT session_id, node_id, title, file, line_start, line_end, symbol,"
            " concept_tags_json, lesson_brief_json, lesson_json"
            " FROM plan_nodes ORDER BY node_id")]
    finally:
        conn.close()


def _wire(graph: LearningGraph) -> dict:
    """The comparable projection: everything `to_dict` reports, minus the reset marker.

    `journey_events` is excluded because the reset legitimately writes one and a
    freshly-loaded plan has none — that difference is asserted on its own below,
    rather than being smuggled past this comparison.
    """
    payload = graph.to_dict()
    payload.pop("journey_events", None)
    return payload


# ── the acceptance assertion ─────────────────────────────────────────────────

def test_a_reset_graph_equals_a_graph_built_from_the_plan(db_path):
    """THE test of this phase (session-reset.md §5).

    One equality over the whole wire payload — nodes, edges, priorities, lessons,
    understanding, gaps, progress and readiness — after a session that touched
    every mutation the system has.
    """
    planned = _planned(db_path)
    node_ids = list(planned.nodes)
    live = learning_store.load_graph(planned.session_id, TEST_USER_ID, db_path)
    _work_the_session(live, node_ids)
    learning_store.save_graph(live, db_path, user_id=TEST_USER_ID)

    live = learning_store.load_graph(planned.session_id, TEST_USER_ID, db_path)
    plan = learning_store.load_plan(planned.session_id, TEST_USER_ID, db_path)
    reset_to_plan(live, plan)
    learning_store.save_graph(live, db_path, user_id=TEST_USER_ID)

    # Compared through a reload, so the assertion covers persistence too.
    after = learning_store.load_graph(planned.session_id, TEST_USER_ID, db_path)
    expected = learning_store.load_plan(planned.session_id, TEST_USER_ID, db_path)
    expected.current_node_id = expected.path_head()
    assert _wire(after) == _wire(expected)


def test_the_reset_marker_is_the_only_history_left(db_path):
    planned = _planned(db_path)
    live = learning_store.load_graph(planned.session_id, TEST_USER_ID, db_path)
    _work_the_session(live, list(planned.nodes))
    assert len(live.journey_events) > 1

    reset_to_plan(live, learning_store.load_plan(planned.session_id, TEST_USER_ID, db_path))

    assert [e["kind"] for e in live.journey_events] == [history.RESET]


def test_resetting_twice_leaves_exactly_one_marker(db_path):
    """Deterministic and idempotent: a second reset is not a second history."""
    planned = _planned(db_path)
    live = learning_store.load_graph(planned.session_id, TEST_USER_ID, db_path)

    reset_to_plan(live, learning_store.load_plan(planned.session_id, TEST_USER_ID, db_path))
    first = _wire(live)
    reset_to_plan(live, learning_store.load_plan(planned.session_id, TEST_USER_ID, db_path))

    assert [e["kind"] for e in live.journey_events] == [history.RESET]
    assert _wire(live) == first


# ── what the equality cannot see ─────────────────────────────────────────────

def test_the_reset_does_not_touch_the_stored_plan(db_path):
    """The plan is the restore source, so a reset that mutated it would be a
    one-way door: the second `Start over` would restore the first one's damage."""
    planned = _planned(db_path)
    before = _plan_rows(db_path)
    live = learning_store.load_graph(planned.session_id, TEST_USER_ID, db_path)
    _work_the_session(live, list(planned.nodes))

    reset_to_plan(live, learning_store.load_plan(planned.session_id, TEST_USER_ID, db_path))
    learning_store.save_graph(live, db_path, user_id=TEST_USER_ID)
    # And keep working afterwards, on the restored graph.
    live.record_attempt(live.current_node_id, "again", "partial", "some of it")
    learning_store.save_graph(live, db_path, user_id=TEST_USER_ID)

    assert _plan_rows(db_path) == before


def test_the_restored_graph_can_be_reset_again(db_path):
    """The property the previous test protects, exercised end to end."""
    planned = _planned(db_path)
    live = learning_store.load_graph(planned.session_id, TEST_USER_ID, db_path)
    _work_the_session(live, list(planned.nodes))
    reset_to_plan(live, learning_store.load_plan(planned.session_id, TEST_USER_ID, db_path))
    learning_store.save_graph(live, db_path, user_id=TEST_USER_ID)

    live = learning_store.load_graph(planned.session_id, TEST_USER_ID, db_path)
    _work_the_session(live, [n for n in planned.nodes])
    reset_to_plan(live, learning_store.load_plan(planned.session_id, TEST_USER_ID, db_path))

    assert len(live.nodes) == 4
    assert all(n.attempts == [] for n in live.nodes.values())


# ── the specifics, one per thing that used to need its own inversion ─────────

def test_remedial_nodes_are_gone_and_the_rerouted_edge_is_restored(db_path):
    planned = _planned(db_path)
    original_edges = {(e.from_node_id, e.to_node_id, e.kind) for e in planned.edges}
    live = learning_store.load_graph(planned.session_id, TEST_USER_ID, db_path)
    _work_the_session(live, list(planned.nodes))
    assert len(live.nodes) == 5  # four planned plus the warm-up

    reset_to_plan(live, learning_store.load_plan(planned.session_id, TEST_USER_ID, db_path))

    assert set(live.nodes) == set(planned.nodes)
    assert {(e.from_node_id, e.to_node_id, e.kind) for e in live.edges} == original_edges


def test_a_warm_up_spliced_before_the_head_is_removed(db_path):
    """The case with no incoming sequence edge to repair — it was the head."""
    planned = _planned(db_path)
    head = planned.path_head()
    live = learning_store.load_graph(planned.session_id, TEST_USER_ID, db_path)
    warm_up = LearningNode(
        title="Before the beginning",
        code_anchor=CodeAnchor(file="requests/__init__.py", line_start=1, line_end=5),
        lesson_brief={"origin": "system_remediation"},
    )
    live.insert_before(head, warm_up, kind="prerequisite")
    assert live.path_head() == warm_up.id

    reset_to_plan(live, learning_store.load_plan(planned.session_id, TEST_USER_ID, db_path))

    assert live.path_head() == head
    assert live.current_node_id == head


def test_priority_comes_back_for_both_producers(db_path):
    """Scope control and prune-ahead both move `priority`; neither survives.

    This is the one the rejected design needed a `journey_events` derivation for.
    Here it is a consequence of restoring `lesson_brief` wholesale.
    """
    planned = _planned(db_path)
    original = {n: planned.nodes[n].lesson_brief["priority"] for n in planned.nodes}
    live = learning_store.load_graph(planned.session_id, TEST_USER_ID, db_path)
    scope.shorten(live)                      # recommended -> optional, scope_locked
    live.mark_understanding(list(planned.nodes)[0], "understood")
    adaptation.prune_ahead(live)
    assert any(n.lesson_brief.get("priority") == "optional"
               for n in live.nodes.values())

    reset_to_plan(live, learning_store.load_plan(planned.session_id, TEST_USER_ID, db_path))

    assert {n: live.nodes[n].lesson_brief["priority"] for n in live.nodes} == original
    assert all("scope_locked" not in n.lesson_brief for n in live.nodes.values())


def test_the_original_lesson_replaces_a_retaught_one(db_path):
    """The other thing the rejected design needed recovery logic for."""
    planned = _planned(db_path)
    first = list(planned.nodes)[0]
    live = learning_store.load_graph(planned.session_id, TEST_USER_ID, db_path)
    live.nodes[first].cached_lesson = _lesson("RETAUGHT")

    reset_to_plan(live, learning_store.load_plan(planned.session_id, TEST_USER_ID, db_path))

    assert live.nodes[first].cached_lesson == _lesson("stop1")


def test_a_stop_that_was_never_reached_has_no_lesson(db_path):
    """None, not a fabricated one: exactly a fresh session's state for that stop."""
    graph = LearningGraph(repo_url=REPO, goal=GOAL)
    node = graph.add_node(LearningNode(
        title="Never reached",
        code_anchor=CodeAnchor(file="requests/api.py", line_start=1, line_end=9),
    ))
    graph.set_current(node.id)
    learning_store.create_session(graph, db_path, user_id=TEST_USER_ID)
    live = learning_store.load_graph(graph.session_id, TEST_USER_ID, db_path)
    live.nodes[node.id].cached_lesson = _lesson("rendered later")

    reset_to_plan(live, learning_store.load_plan(graph.session_id, TEST_USER_ID, db_path))

    assert live.nodes[node.id].cached_lesson is None


def test_gap_machinery_is_gone_entirely(db_path):
    """Not just the gaps: the round counter and the outstanding question too.

    A surviving `remediation_rounds` would give a reset learner LESS help than a
    new one; a surviving `pending_verification` would offer a question about a gap
    that no longer exists.
    """
    planned = _planned(db_path)
    live = learning_store.load_graph(planned.session_id, TEST_USER_ID, db_path)
    _work_the_session(live, list(planned.nodes))

    reset_to_plan(live, learning_store.load_plan(planned.session_id, TEST_USER_ID, db_path))

    for node in live.nodes.values():
        assert node.gaps == []
        assert node.gap_state.remediation_rounds == 0
        assert node.gap_state.pending_verification is None


def test_sticky_state_is_gone(db_path):
    """`weak_spot` survives later `understood` updates by design, so it needs saying."""
    planned = _planned(db_path)
    live = learning_store.load_graph(planned.session_id, TEST_USER_ID, db_path)
    first = list(planned.nodes)[0]
    live.mark_understanding(first, "failed")   # sets weak_spot
    assert live.nodes[first].weak_spot is True

    reset_to_plan(live, learning_store.load_plan(planned.session_id, TEST_USER_ID, db_path))

    assert live.nodes[first].weak_spot is False
    assert live.nodes[first].user_override is None
    assert live.nodes[first].visited is False


def test_position_returns_to_the_first_stop(db_path):
    planned = _planned(db_path)
    head = planned.path_head()
    live = learning_store.load_graph(planned.session_id, TEST_USER_ID, db_path)
    live.set_current(list(planned.nodes)[3])
    live.record_arrival(list(planned.nodes)[3], kind="jumped", from_node_id=head)

    reset_to_plan(live, learning_store.load_plan(planned.session_id, TEST_USER_ID, db_path))

    assert live.current_node_id == head
    assert live.arrival is None


def test_what_is_not_learner_state_survives(db_path):
    """The goal, the repository, the briefing and the chapter list are the plan."""
    planned = _planned(db_path)
    live = learning_store.load_graph(planned.session_id, TEST_USER_ID, db_path)
    live.briefing = {"paragraph": "what this repository is"}
    live.doc_context = {"readme": "an HTTP library"}
    learning_store.save_graph(live, db_path, user_id=TEST_USER_ID)

    live = learning_store.load_graph(planned.session_id, TEST_USER_ID, db_path)
    reset_to_plan(live, learning_store.load_plan(planned.session_id, TEST_USER_ID, db_path))
    learning_store.save_graph(live, db_path, user_id=TEST_USER_ID)

    after = learning_store.load_graph(planned.session_id, TEST_USER_ID, db_path)
    assert after.repo_url == REPO
    assert after.goal == GOAL
    assert after.areas == planned.areas
    assert after.briefing == {"paragraph": "what this repository is"}
    assert after.doc_context == {"readme": "an HTTP library"}
    assert after.session_id == planned.session_id  # no new session id


# ── the summary ──────────────────────────────────────────────────────────────

def test_the_summary_counts_what_was_discarded(db_path):
    planned = _planned(db_path)
    live = learning_store.load_graph(planned.session_id, TEST_USER_ID, db_path)
    _work_the_session(live, list(planned.nodes))

    summary = reset_to_plan(live, learning_store.load_plan(planned.session_id, TEST_USER_ID, db_path))

    assert isinstance(summary, ResetSummary)
    assert summary.attempts == 2
    assert summary.gaps == 3
    assert summary.remedial_nodes == 1
    assert summary.lessons_restored == 4
    assert summary.stops >= 2


def test_the_summary_of_a_pristine_session_is_empty(db_path):
    planned = _planned(db_path)
    live = learning_store.load_graph(planned.session_id, TEST_USER_ID, db_path)

    summary = reset_to_plan(live, learning_store.load_plan(planned.session_id, TEST_USER_ID, db_path))

    assert summary.attempts == 0
    assert summary.gaps == 0
    assert summary.remedial_nodes == 0
    assert summary.stops == 0


def test_learner_state_describes_the_boundary(db_path):
    planned = _planned(db_path)
    live = learning_store.load_graph(planned.session_id, TEST_USER_ID, db_path)
    _work_the_session(live, list(planned.nodes))

    state = learner_state(live)

    assert state["attempts"] == 2
    assert state["gaps"] == 3
    assert state["remediation_rounds"] == 3
    assert state["pending_verifications"] == 1
    assert state["journey_events"] >= 1


# ── the endpoint ─────────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(api, "SESSIONS_DB_PATH", tmp_path / "sessions.db")
    monkeypatch.setattr(api.anthropic, "Anthropic", lambda **kw: MagicMock())
    return TestClient(api.app)


def test_the_endpoint_restores_and_returns_the_graph(client):
    db = api.SESSIONS_DB_PATH
    planned = _planned(db)
    live = learning_store.load_graph(planned.session_id, TEST_USER_ID, db)
    _work_the_session(live, list(planned.nodes))
    learning_store.save_graph(live, db, user_id=TEST_USER_ID)

    resp = client.post(f"/session/{planned.session_id}/reset")

    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == planned.session_id          # no new session id
    assert len(body["graph"]["nodes"]) == 4                  # the warm-up is gone
    assert body["graph"]["current_node_id"] == planned.path_head()
    assert body["discarded"]["attempts"] == 2
    # The same payload `GET /session/{id}` would give, so no second fetch.
    assert body["graph"] == client.get(f"/session/{planned.session_id}").json()


def test_the_endpoint_makes_no_model_call_and_no_clone(client):
    """Determinism, asserted rather than assumed — this is the whole point of M2.

    `Start over` used to run the pipeline. If any of these three is ever reached
    again, the two-to-four-minute wait is back.
    """
    db = api.SESSIONS_DB_PATH
    planned = _planned(db)

    with patch.object(api, "run_pipeline") as pipeline, \
         patch.object(api, "clone_repo") as clone, \
         patch.object(api, "run_teaching") as teaching, \
         patch.object(api, "_new_client") as new_client:
        resp = client.post(f"/session/{planned.session_id}/reset")

    assert resp.status_code == 200
    pipeline.assert_not_called()
    clone.assert_not_called()
    teaching.assert_not_called()
    new_client.assert_not_called()


def test_the_endpoint_404s_for_an_unknown_session(client):
    assert client.post("/session/nope/reset").status_code == 404


def test_the_endpoint_409s_when_there_is_no_plan(client):
    """A pre-v3 session: found, but not resettable. No reconstruction attempted."""
    db = api.SESSIONS_DB_PATH
    planned = _planned(db)
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM plan_nodes WHERE session_id = ?", (planned.session_id,))
    conn.commit()
    conn.close()

    resp = client.post(f"/session/{planned.session_id}/reset")

    assert resp.status_code == 409
    assert resp.json()["detail"] == "no_plan_snapshot"


def test_the_endpoint_is_idempotent(client):
    db = api.SESSIONS_DB_PATH
    planned = _planned(db)
    live = learning_store.load_graph(planned.session_id, TEST_USER_ID, db)
    _work_the_session(live, list(planned.nodes))
    learning_store.save_graph(live, db, user_id=TEST_USER_ID)

    first = client.post(f"/session/{planned.session_id}/reset").json()["graph"]
    second = client.post(f"/session/{planned.session_id}/reset").json()["graph"]

    assert first == second


def test_the_session_is_usable_after_a_reset(client, monkeypatch):
    """It restores a WORKING session, not just a correct payload.

    The lesson served after a reset is the ORIGINAL one, out of the plan's cache —
    which is what makes a reset free. Teaching is deliberately NOT mocked here:
    the mechanism under test is its own early return on an already-cached lesson
    (`teaching/agent.py`), and stubbing it out would delete exactly the behaviour
    being asserted. What is asserted instead is the consequence that matters — the
    Anthropic client is never asked for anything.
    """
    llm = MagicMock()
    monkeypatch.setattr(api.anthropic, "Anthropic", lambda **kw: llm)
    db = api.SESSIONS_DB_PATH
    planned = _planned(db)
    live = learning_store.load_graph(planned.session_id, TEST_USER_ID, db)
    _work_the_session(live, list(planned.nodes))
    learning_store.save_graph(live, db, user_id=TEST_USER_ID)
    client.post(f"/session/{planned.session_id}/reset")

    # Cloning is `_render_current_lesson`'s own precondition and predates this
    # phase; it is stubbed so this test touches no git, not because a reset ought
    # to prevent it.
    monkeypatch.setattr(api, "clone_repo", lambda url: "/tmp/repo")
    resp = client.get(f"/session/{planned.session_id}/lesson")

    assert resp.status_code == 200
    assert resp.json()["lesson"] == _lesson("stop1")
    llm.messages.create.assert_not_called()


# ── availability, for the multi-user integration ─────────────────────────────
#
# `load_graph` is being widened by the multi-user workstream to accept schema v2,
# so that the 90 stored sessions behind docs/planning/phases/evidence/ stay
# loadable and resumable. These pin this feature's half of that contract: such a
# session is NOT resettable, the wire says so before the learner clicks, and
# nothing fabricates a plan for it.

def test_the_wire_says_whether_a_session_can_be_started_over(client):
    db = api.SESSIONS_DB_PATH
    planned = _planned(db)

    assert client.get(f"/session/{planned.session_id}").json()["has_plan"] is True


def test_a_planless_session_reports_unavailable_rather_than_failing_on_click(client):
    """The gate the UI reads, and the 409 behind it, must agree.

    Disagreement is the bad outcome in either direction: an offered button that
    409s, or a hidden button on a session that could be restored.
    """
    db = api.SESSIONS_DB_PATH
    planned = _planned(db)
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM plan_nodes WHERE session_id = ?", (planned.session_id,))
    conn.commit()
    conn.close()

    assert client.get(f"/session/{planned.session_id}").json()["has_plan"] is False
    assert client.post(f"/session/{planned.session_id}/reset").status_code == 409


def test_a_refused_reset_changes_nothing(client):
    """No half-reset, and no fabricated plan.

    The refusal happens before `reset_to_plan` is reached, so the learner's work
    is still there afterwards — which is what makes the 409 safe to surface as a
    disabled button rather than as a destructive attempt.
    """
    db = api.SESSIONS_DB_PATH
    planned = _planned(db)
    live = learning_store.load_graph(planned.session_id, TEST_USER_ID, db)
    _work_the_session(live, list(planned.nodes))
    learning_store.save_graph(live, db, user_id=TEST_USER_ID)
    # Dropping the plan rows is this test's SETUP — it is how a v2 session looks —
    # so the baseline is taken after it. Snapshotting first would compare across
    # the test's own edit and fail on `has_plan`, which is correct to change here.
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM plan_nodes WHERE session_id = ?", (planned.session_id,))
    conn.commit()
    conn.close()
    before = _wire(learning_store.load_graph(planned.session_id, TEST_USER_ID, db))

    assert client.post(f"/session/{planned.session_id}/reset").status_code == 409

    after = learning_store.load_graph(planned.session_id, TEST_USER_ID, db)
    assert _wire(after) == before
    # And still no plan: a refusal must never synthesise one from live state.
    assert learning_store.load_plan(planned.session_id, TEST_USER_ID, db) is None
