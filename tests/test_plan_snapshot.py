"""The original plan is persisted at creation and never mutated by learning.

Run with: uv run pytest tests/test_plan_snapshot.py -v

M1 of session-reset.md. It builds NO reset — it makes the plan exist, so that M2
can restore from it instead of reconstructing it by inverting every mutation.

## What these tests are actually defending

The rejected design inverted mutations, and its failure mode was silent: a field
nobody classified survived a reset and looked like plan data. This design's
failure mode is the opposite, and these tests are aimed at it — **plan data that
never reaches `plan_nodes` is lost at reset**, so the tests that matter are the
ones proving (a) everything the planner wrote is in the plan, and (b) nothing the
learner does can change it.

`test_the_plan_does_not_move_while_the_learner_works` is the important one. It
runs every mutation the live graph supports — answers, gaps at every status, a
re-teach, a waiver, an override, prune-ahead, scope in both directions, and a
spliced warm-up — and asserts the plan tables come out byte-identical apart from
lesson slots being filled.

No network, no LLM, no API key: real SQLite against a temp file.
"""
import ast
import json
import sqlite3
from pathlib import Path

import pytest

from tests.conftest import TEST_USER_ID

from backend.learning import adaptation, scope
from backend.learning.gaps import Gap
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.learning.store import (
    SCHEMA_VERSION,
    create_session,
    load_graph,
    load_plan,
    record_plan_lesson,
    save_graph,
)


@pytest.fixture
def db_path(tmp_path) -> Path:
    return tmp_path / "sessions.db"


def _lesson(marker: str) -> dict:
    return {
        "walkthrough": f"the original walkthrough — {marker}",
        "prompt": f"what does {marker} own?",
        "expected_answer": marker,
        "prompt_kind": "predict-then-reveal",
    }


def _planned_graph() -> LearningGraph:
    """Three stops in one area, in sequence, with a dependency — a small B3 graph."""
    graph = LearningGraph(
        repo_url="https://github.com/psf/requests",
        goal={"primary_goal": "understand sessions", "goal_type": "understand_component"},
        areas=[{"id": "a1", "title": "Sessions", "why": "the core", "order": 1}],
    )
    for index, (title, priority) in enumerate(
        [("Session object", "required"),
         ("Adapters", "recommended"),
         ("Cookie persistence", "recommended")],
        start=1,
    ):
        graph.add_node(LearningNode(
            title=title,
            code_anchor=CodeAnchor(
                file="requests/sessions.py",
                line_start=index * 10,
                line_end=index * 10 + 8,
                symbol=f"Session.part{index}",
            ),
            concept_tags=["component", f"tag{index}"],
            lesson_brief={
                "objective": f"explain {title}",
                "why": "it is on the path",
                "kind": "component",
                "priority": priority,
                "area_id": "a1",
                "anchors": [{"file": "requests/sessions.py", "symbol": f"Session.part{index}"}],
            },
        ))
    ids = list(graph.nodes)
    graph.add_edge(ids[0], ids[1], kind="sequence")
    graph.add_edge(ids[1], ids[2], kind="sequence")
    graph.add_edge(ids[0], ids[2], kind="prerequisite")  # a PLANNED dependency
    graph.set_current(ids[0])
    return graph


def _plan_rows(db_path: Path) -> tuple[list[tuple], list[tuple]]:
    """The plan tables, as comparable tuples. The byte-identity oracle."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        nodes = [tuple(r) for r in conn.execute(
            "SELECT session_id, node_id, title, file, line_start, line_end, symbol,"
            " concept_tags_json, lesson_brief_json, lesson_json"
            " FROM plan_nodes ORDER BY node_id")]
        edges = [tuple(r) for r in conn.execute(
            "SELECT session_id, from_node_id, to_node_id, kind"
            " FROM plan_edges ORDER BY from_node_id, to_node_id, kind")]
    finally:
        conn.close()
    return nodes, edges


# --- creation -----------------------------------------------------------------

def test_create_session_writes_the_plan_alongside_the_live_graph(db_path):
    graph = _planned_graph()

    create_session(graph, db_path, user_id=TEST_USER_ID)

    plan = load_plan(graph.session_id, TEST_USER_ID, db_path)
    assert plan is not None
    assert set(plan.nodes) == set(graph.nodes)
    assert {(e.from_node_id, e.to_node_id, e.kind) for e in plan.edges} == {
        (e.from_node_id, e.to_node_id, e.kind) for e in graph.edges
    }


def test_the_plan_carries_every_planned_field(db_path):
    """The guard against plan data silently not being persisted (see the docstring)."""
    graph = _planned_graph()
    create_session(graph, db_path, user_id=TEST_USER_ID)

    plan = load_plan(graph.session_id, TEST_USER_ID, db_path)

    for node_id, original in graph.nodes.items():
        restored = plan.nodes[node_id]
        assert restored.title == original.title
        assert restored.concept_tags == original.concept_tags
        assert restored.lesson_brief == original.lesson_brief
        assert restored.code_anchor == original.code_anchor


def test_a_planned_node_comes_back_with_no_learner_state(db_path):
    graph = _planned_graph()
    create_session(graph, db_path, user_id=TEST_USER_ID)

    node = next(iter(load_plan(graph.session_id, TEST_USER_ID, db_path).nodes.values()))

    assert node.understanding_state == "not_started"
    assert node.visited is False
    assert node.weak_spot is False
    assert node.user_override is None
    assert node.attempts == []
    assert node.gaps == []
    assert node.gap_state.remediation_rounds == 0
    assert node.gap_state.pending_verification is None


def test_the_plan_carries_no_position_and_no_history(db_path):
    """Position and history are what a reset discards, so the plan must not hold them."""
    graph = _planned_graph()
    graph.record_journey_event("jumped", nodes=[next(iter(graph.nodes))])
    graph.record_arrival(next(iter(graph.nodes)), kind="jumped")
    create_session(graph, db_path, user_id=TEST_USER_ID)

    plan = load_plan(graph.session_id, TEST_USER_ID, db_path)

    assert plan.current_node_id is None
    assert plan.arrival is None
    assert plan.journey_events == []


def test_session_level_plan_columns_come_across(db_path):
    graph = _planned_graph()
    graph.doc_context = {"readme": "requests is an HTTP library"}
    create_session(graph, db_path, user_id=TEST_USER_ID)
    # Written after creation, by the welcome page rather than the planner.
    live = load_graph(graph.session_id, TEST_USER_ID, db_path)
    live.briefing = {"paragraph": "what this repository is"}
    save_graph(live, db_path, user_id=TEST_USER_ID)

    plan = load_plan(graph.session_id, TEST_USER_ID, db_path)

    assert plan.repo_url == graph.repo_url
    assert plan.goal == graph.goal
    assert plan.areas == graph.areas
    assert plan.doc_context == {"readme": "requests is an HTTP library"}
    assert plan.briefing == {"paragraph": "what this repository is"}


def test_creation_is_one_transaction(db_path, monkeypatch):
    """No path may leave a session on disk without a plan (§4.2).

    Forced by making the plan write raise: if the two writes were in separate
    transactions the session row would survive alone, which is the permanently
    un-resettable session this design exists to make unrepresentable.
    """
    import backend.learning.store as store

    def explode(conn, graph):
        raise RuntimeError("plan write failed")

    monkeypatch.setattr(store, "_write_plan", explode)
    graph = _planned_graph()

    with pytest.raises(RuntimeError):
        create_session(graph, db_path, user_id=TEST_USER_ID)

    assert load_graph(graph.session_id, TEST_USER_ID, db_path) is None


def test_save_graph_alone_writes_no_plan(db_path):
    """`save_graph` is every other caller's entry point and must not create a plan.

    A plan written by a later save would be a snapshot of an ALREADY-MUTATED
    graph — the reset would then restore the learner's own detours as if the
    planner had produced them.
    """
    graph = _planned_graph()

    save_graph(graph, db_path, user_id=TEST_USER_ID)

    assert load_plan(graph.session_id, TEST_USER_ID, db_path) is None


# --- the write-once lesson slot -----------------------------------------------

def test_the_first_lesson_fills_the_slot(db_path):
    graph = _planned_graph()
    create_session(graph, db_path, user_id=TEST_USER_ID)
    node_id = graph.current_node_id

    assert record_plan_lesson(graph.session_id, node_id, _lesson("first"), db_path) is True

    assert load_plan(graph.session_id, TEST_USER_ID, db_path).nodes[node_id].cached_lesson == _lesson("first")


def test_a_second_recording_cannot_overwrite(db_path):
    graph = _planned_graph()
    create_session(graph, db_path, user_id=TEST_USER_ID)
    node_id = graph.current_node_id
    record_plan_lesson(graph.session_id, node_id, _lesson("first"), db_path)

    assert record_plan_lesson(graph.session_id, node_id, _lesson("retaught"), db_path) is False

    assert load_plan(graph.session_id, TEST_USER_ID, db_path).nodes[node_id].cached_lesson == _lesson("first")


def test_an_unrendered_stop_has_no_lesson(db_path):
    """None, not a fabricated one — the same state a fresh session is in there."""
    graph = _planned_graph()
    create_session(graph, db_path, user_id=TEST_USER_ID)

    plan = load_plan(graph.session_id, TEST_USER_ID, db_path)

    assert all(n.cached_lesson is None for n in plan.nodes.values())


def test_recording_for_a_node_outside_the_plan_is_a_no_op(db_path):
    """A remedial warm-up renders like any stop, and must not enter the plan.

    An upsert here would add learner-created nodes to the plan, and `Start over`
    would then restore the very warm-ups it exists to remove.
    """
    graph = _planned_graph()
    create_session(graph, db_path, user_id=TEST_USER_ID)
    before_nodes, before_edges = _plan_rows(db_path)

    assert record_plan_lesson(graph.session_id, "not-a-planned-node", _lesson("x"), db_path) is False

    assert _plan_rows(db_path) == (before_nodes, before_edges)


def test_recording_against_a_missing_database_is_survivable(db_path):
    assert record_plan_lesson("nope", "nope", _lesson("x"), db_path) is False


# --- immutability under a full session ----------------------------------------

def test_the_plan_does_not_move_while_the_learner_works(db_path):
    """THE test of this milestone.

    Every mutation the live graph supports, then a byte-comparison of the plan
    tables. The only permitted difference is lesson slots going from NULL to a
    lesson.
    """
    graph = _planned_graph()
    create_session(graph, db_path, user_id=TEST_USER_ID)
    first, second, third = list(graph.nodes)

    # Lessons render as the learner arrives; the plan records each once.
    for node_id, marker in ((first, "one"), (second, "two")):
        record_plan_lesson(graph.session_id, node_id, _lesson(marker), db_path)
    baseline_nodes, baseline_edges = _plan_rows(db_path)

    live = load_graph(graph.session_id, TEST_USER_ID, db_path)

    # ── an answer, graded, with gaps in every status ──────────────────────────
    live.record_attempt(first, "sessions are just a dict", "confused", "not quite",
                        gap_kind="wrong_model")
    live.mark_understanding(first, "failed")
    node = live.nodes[first]
    opened = Gap.create("wrong_model", "a Session is a dict of headers")
    verified = Gap.create("missing_prerequisite", "connection pooling is per-request")
    waived = Gap.create("wrong_model", "adapters are optional")
    verified.mark_verified(0)
    waived.waive()
    node.gap_state.gaps.extend([opened, verified, waived])
    node.gap_state.remediation_rounds = 2
    node.gap_state.pending_verification = {"question": "why reuse a connection?",
                                           "targets": [opened.id], "at": "now"}

    # ── a re-teach replaces the live lesson ──────────────────────────────────
    node.cached_lesson = _lesson("RETAUGHT — the corrected version")
    live.record_response(first, {"action": "reteach", "retaught": True,
                                 "superseded_lesson": _lesson("one")})

    # ── learner intents, overrides, position ─────────────────────────────────
    live.waive_gap(first, waived.id)
    live.override(second, "skip")
    live.mark_visited(first)
    live.set_current(second)
    live.record_arrival(second, kind="jumped", from_node_id=first)
    live.record_journey_event("jumped", nodes=[second], from_node_id=first)

    # ── the plan-shaped mutations: scope, prune-ahead, a spliced warm-up ─────
    scope.shorten(live)
    scope.deepen(live)
    live.nodes[third].lesson_brief = {**live.nodes[third].lesson_brief,
                                      "priority": "recommended"}
    live.mark_understanding(third, "understood")
    adaptation.prune_ahead(live)
    warm_up = LearningNode(
        title="What a connection pool is",
        code_anchor=CodeAnchor(file="requests/adapters.py", line_start=1, line_end=20),
        lesson_brief={"objective": "explain pooling", "priority": "required",
                      "origin": "system_remediation", "remediates": [opened.id]},
    )
    live.insert_before(first, warm_up, kind="prerequisite")
    live.set_current(warm_up.id)
    save_graph(live, db_path, user_id=TEST_USER_ID)
    # The warm-up renders too — the no-op path, exercised in situ.
    record_plan_lesson(graph.session_id, warm_up.id, _lesson("warm-up"), db_path)

    # ── the plan has not moved ───────────────────────────────────────────────
    assert _plan_rows(db_path) == (baseline_nodes, baseline_edges)

    # And it still describes the ORIGINAL journey, not the mutated one.
    plan = load_plan(graph.session_id, TEST_USER_ID, db_path)
    assert set(plan.nodes) == {first, second, third}
    assert plan.nodes[first].cached_lesson == _lesson("one")
    assert plan.nodes[third].cached_lesson is None
    assert [plan.nodes[n].lesson_brief["priority"] for n in (first, second, third)] == [
        "required", "recommended", "recommended"
    ]
    assert all("scope_locked" not in n.lesson_brief for n in plan.nodes.values())
    assert all("remediates" not in n.lesson_brief for n in plan.nodes.values())
    assert plan.nodes[first].attempts == []
    assert plan.nodes[first].gaps == []
    assert plan.nodes[second].user_override is None

    # ...while the LIVE graph kept every one of those mutations.
    reloaded = load_graph(graph.session_id, TEST_USER_ID, db_path)
    assert len(reloaded.nodes) == 4
    assert reloaded.nodes[first].attempts
    assert len(reloaded.nodes[first].gaps) == 3
    assert reloaded.nodes[first].cached_lesson["walkthrough"].startswith("the original walkthrough — RETAUGHT")
    assert reloaded.nodes[second].user_override == "skip"


# --- schema -------------------------------------------------------------------

def test_schema_version_is_three():
    """v3 is what makes pre-plan sessions invisible rather than half-loadable (D8)."""
    assert SCHEMA_VERSION == 3


def test_a_session_from_an_older_schema_has_no_plan(db_path):
    """No backfill, no reconstruction: `load_plan` says None and the caller decides."""
    graph = _planned_graph()
    create_session(graph, db_path, user_id=TEST_USER_ID)
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE sessions SET schema_version = 2 WHERE session_id = ?",
                 (graph.session_id,))
    conn.commit()
    conn.close()

    # THE SECOND ASSERTION CHANGED (multi-user.md OPEN-14, decided 2026-08-22).
    #
    # It used to require that a version-2 session did not load AT ALL, and that
    # cost more than it protected: all 91 sessions in the live database are
    # version 2, so the bump made the entire manual-E2E corpus invisible rather
    # than merely un-resettable.
    #
    # The rule now separates the two questions it had conflated. A v2 session
    # LOADS and RESUMES with its state exactly as it is; it simply has no plan,
    # so `Start over` is unavailable — which is what the `load_plan` assertion,
    # the one that matters to this feature, has always said. Nothing is
    # synthesised either way.
    #
    # The fixture builds a GENUINE v2 session: relabelled AND without plan rows.
    # Relabelling alone leaves the plan behind, which is a state that cannot
    # exist — the plan tables arrived WITH version 3.
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM plan_nodes WHERE session_id = ?", (graph.session_id,))
    conn.execute("DELETE FROM plan_edges WHERE session_id = ?", (graph.session_id,))
    conn.commit()
    conn.close()

    assert load_plan(graph.session_id, TEST_USER_ID, db_path) is None
    restored = load_graph(graph.session_id, TEST_USER_ID, db_path)
    assert restored is not None
    assert restored.has_plan is False


def test_the_plan_cascades_when_a_session_is_deleted(db_path):
    from backend.learning.store import delete_session

    graph = _planned_graph()
    create_session(graph, db_path, user_id=TEST_USER_ID)

    delete_session(graph.session_id, TEST_USER_ID, db_path)

    assert _plan_rows(db_path) == ([], [])


def test_load_plan_is_none_for_an_unknown_session(db_path):
    graph = _planned_graph()
    create_session(graph, db_path, user_id=TEST_USER_ID)

    assert load_plan("no-such-session", TEST_USER_ID, db_path) is None


def test_the_plan_tables_hold_no_learner_state_columns(db_path):
    """The partition is the schema (see the store's header), so assert the schema.

    A learner-state column added to `plan_nodes` would make the plan mutable by
    learning again, which is the whole thing this design removes.
    """
    graph = _planned_graph()
    create_session(graph, db_path, user_id=TEST_USER_ID)
    conn = sqlite3.connect(db_path)
    try:
        columns = {r[1] for r in conn.execute("PRAGMA table_info(plan_nodes)")}
    finally:
        conn.close()

    forbidden = {
        "understanding_state", "visited", "weak_spot", "user_override",
        "attempts_json", "gaps_json", "current_node_id", "arrival_json",
        "journey_events_json", "tutor_json",
    }
    assert columns & forbidden == set()
    assert columns == {
        "session_id", "node_id", "title", "file", "line_start", "line_end",
        "symbol", "concept_tags_json", "lesson_brief_json", "lesson_json",
    }


def test_every_learning_node_field_is_planned_or_defaulted(db_path):
    """A new field must be a deliberate choice, not an accident.

    Fails when someone adds a field to `LearningNode` without deciding whether it
    is plan (persist it in `plan_nodes`) or state (it defaults on restore). The
    failure direction is the safe one — plan data that is not persisted is LOST at
    reset, and this is what makes that loud instead of silent.
    """
    graph = _planned_graph()
    create_session(graph, db_path, user_id=TEST_USER_ID)
    record_plan_lesson(graph.session_id, graph.current_node_id, _lesson("one"), db_path)
    plan_node = load_plan(graph.session_id, TEST_USER_ID, db_path).nodes[graph.current_node_id]

    # Carried by the plan.
    planned = {"id", "title", "code_anchor", "concept_tags", "lesson_brief",
               "cached_lesson"}
    # Learner state: absent from the plan tables, so it arrives at its default.
    # `tutor_state` is STATE, deliberately: it counts hints written for the
    # question in front of THIS learner and whether they asked to see an answer,
    # which is a fact about a walk rather than about a plan. Carrying it into
    # `plan_nodes` would restore a spent hint ladder onto a freshly started route.
    stateful = {"understanding_state", "visited", "weak_spot", "user_override",
                "attempts", "gap_state", "tutor_state"}

    assert planned | stateful == set(LearningNode.__dataclass_fields__), (
        "a LearningNode field is neither planned nor known-stateful — classify it "
        "in session-reset.md §3 and in this test"
    )

    fresh = LearningNode(title="x", code_anchor=CodeAnchor(file="f", line_start=1, line_end=2))
    for field in stateful:
        assert getattr(plan_node, field) == getattr(fresh, field), field


# --- the one creation path ----------------------------------------------------

def test_create_session_is_called_from_exactly_one_place():
    """A second creation path is how a v3 session ends up with no plan.

    `SCHEMA_VERSION` 3 guarantees that every *loadable* session was written by
    code that has the plan tables — but not that it went through
    `create_session`. Any endpoint that persisted a brand-new graph with
    `save_graph` would produce a session that loads perfectly and can never be
    reset, and nothing at runtime would notice.

    Structural, in the style of `test_gap_understanding.py`'s reader check, and
    audited when written: `/session/start` is the only creation path. `_try_resume`
    and the welcome briefing both save an EXISTING session, and `/onboard` does
    not persist at all.
    """
    calls = []
    for path in sorted(Path("backend").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name == "create_session":
                calls.append((str(path).replace("\\", "/"), node.lineno))

    assert len(calls) == 1, (
        f"expected exactly one create_session call site, found {calls}. A new one "
        "must be a deliberate decision: see session-reset.md §4.2"
    )
    assert calls[0][0] == "backend/api.py"


# --- can this session be started over? ----------------------------------------
#
# The gate is PLAN-ROW PRESENCE, not `schema_version`. Coordinated with the
# multi-user workstream, which is widening `load_graph` to accept v2 sessions so
# the manual-E2E corpus stays loadable: a v2 session has no plan rows, so it
# reports `has_plan` false and the UI disables `Start over` with a reason. That
# stays correct however the version numbers move, which a comparison would not.

def test_a_created_session_knows_it_has_a_plan(db_path):
    graph = _planned_graph()

    create_session(graph, db_path, user_id=TEST_USER_ID)

    # On the in-memory object too, because that is the payload /session/start
    # returns — it must not claim a fresh session cannot be started over.
    assert graph.has_plan is True
    assert load_graph(graph.session_id, TEST_USER_ID, db_path).has_plan is True
    assert load_graph(graph.session_id, TEST_USER_ID, db_path).to_dict()["has_plan"] is True


def test_a_session_with_no_plan_rows_says_so(db_path):
    """The shape of every session written before the plan tables existed."""
    graph = _planned_graph()
    save_graph(graph, db_path, user_id=TEST_USER_ID)  # deliberately not create_session

    loaded = load_graph(graph.session_id, TEST_USER_ID, db_path)

    assert loaded.has_plan is False
    assert loaded.to_dict()["has_plan"] is False


def test_has_plan_is_never_persisted(db_path):
    """It is a fact about the database, not a column in it.

    Persisting it would create a second source of truth that could disagree with
    the plan tables — and the disagreement would surface as a `Start over` button
    that 409s, or one that is hidden on a session that could be restored.
    """
    graph = _planned_graph()
    create_session(graph, db_path, user_id=TEST_USER_ID)
    conn = sqlite3.connect(db_path)
    try:
        columns = {r[1] for r in conn.execute("PRAGMA table_info(sessions)")}
    finally:
        conn.close()
    assert "has_plan" not in columns

    # A lie on the in-memory object does not survive a round trip.
    live = load_graph(graph.session_id, TEST_USER_ID, db_path)
    live.has_plan = False
    save_graph(live, db_path, user_id=TEST_USER_ID)
    assert load_graph(graph.session_id, TEST_USER_ID, db_path).has_plan is True


def test_a_graph_built_from_the_plan_has_a_plan(db_path):
    graph = _planned_graph()
    create_session(graph, db_path, user_id=TEST_USER_ID)

    assert load_plan(graph.session_id, TEST_USER_ID, db_path).has_plan is True
