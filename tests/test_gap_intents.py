"""M8 — learner intents, resume, and journey completion.

gap-model.md M8. The learner gets agency over their own gaps: `continue` past
them, `waive` one, `waive_remaining` on a node. Two derived things follow —
`resume_point()` has to respect those decisions, and `is_complete()` becomes
reachable because of them.

**The risk this file exists to defend is STRANDING.** A learner who deliberately
moves past unresolved gaps must not be sent back to that node on every return.
It is the one failure the build plan names for M8, it is invisible in a unit test
of any single function, and a system that strands is worse than one that forgets:
the learner has no move left except answering the thing they just declined to
answer. The `stranding` section below walks the full journey rather than checking
one call.

Run with: uv run pytest tests/test_gap_intents.py -v
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import backend.api as api
from backend.learning import store as learning_store
from backend.learning.gaps import Gap
from backend.learning.graph import (
    SETTLING_OVERRIDES,
    CodeAnchor,
    LearningGraph,
    LearningNode,
    has_open_blocking_gaps,
    is_settled,
    understanding_of,
)

from tests.test_session_api import (
    FAKE_GOAL,
    FAKE_REPO_URL,
    _teaching_side_effect,
)


@pytest.fixture(autouse=True)
def _env_and_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("CODEONBOARD_GAPS", "1")
    monkeypatch.setattr(api, "SESSIONS_DB_PATH", tmp_path / "sessions.db")
    monkeypatch.setattr(api.anthropic, "Anthropic", lambda **kw: MagicMock())


@pytest.fixture
def client():
    return TestClient(api.app)


def _node(title: str, state: str = "not_started", **brief) -> LearningNode:
    node = LearningNode(
        title=title,
        code_anchor=CodeAnchor(file="requests/sessions.py", line_start=1, line_end=20),
        lesson_brief={"objective": f"Explain {title}", "priority": "required", **brief},
    )
    node.understanding_state = state
    node.cached_lesson = {"prompt": "q?", "setup": "…"}
    return node


def _chain(*nodes: LearningNode) -> LearningGraph:
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    for node in nodes:
        graph.add_node(node)
    for a, b in zip(nodes, nodes[1:]):
        graph.add_edge(a.id, b.id, kind="sequence")
    graph.set_current(nodes[0].id)
    return graph


def _gap(kind: str = "wrong_model", claim: str = "a false claim") -> Gap:
    return Gap.create(kind, claim)


# ── continue ─────────────────────────────────────────────────────────────────


def test_continue_is_recorded_only_where_gaps_are_open():
    """§5 test 15. Stamping every advance would settle stops nobody decided
    about, and make the record meaningless."""
    graph = _chain(_node("A"), _node("B"))
    clean = graph.nodes[graph.path_order()[0]]
    assert graph.continue_past(clean.id) is False
    assert clean.user_override is None

    clean.gap_state.gaps.append(_gap())
    assert graph.continue_past(clean.id) is True
    assert clean.user_override == "continue"


def test_continue_does_not_fire_for_a_non_blocking_gap():
    graph = _chain(_node("A"))
    node = graph.nodes[graph.path_order()[0]]
    node.gap_state.gaps.append(_gap("right_idea_wrong_altitude", "too low"))
    assert graph.continue_past(node.id) is False


def test_continue_does_not_fire_once_gaps_are_settled():
    graph = _chain(_node("A"))
    node = graph.nodes[graph.path_order()[0]]
    verified, waived = _gap(), _gap()
    verified.mark_verified(0)
    waived.waive()
    node.gap_state.gaps.extend([verified, waived])
    assert graph.continue_past(node.id) is False


def test_continue_leaves_the_gaps_open():
    """Moving on is not resolution. The work is still outstanding and visible."""
    graph = _chain(_node("A"))
    node = graph.nodes[graph.path_order()[0]]
    gap = _gap()
    node.gap_state.gaps.append(gap)
    graph.continue_past(node.id)
    assert gap.status == "open"
    assert understanding_of(node) != "understood"


def test_a_new_attempt_withdraws_a_prior_continue():
    """§5 test 17. "I moved on" and "I am working on this again" contradict; the
    later act wins, or the node stays settled while the learner works."""
    graph = _chain(_node("A"))
    node = graph.nodes[graph.path_order()[0]]
    node.gap_state.gaps.append(_gap())
    graph.continue_past(node.id)
    assert node.user_override == "continue"

    graph.record_attempt(node.id, "another go", "partial", "because")
    assert node.user_override is None


def test_a_new_attempt_does_not_withdraw_a_waiver():
    """Answering does not retract a decision to stop being asked. A waived gap
    stays waived until the learner asks to verify it."""
    graph = _chain(_node("A"))
    node = graph.nodes[graph.path_order()[0]]
    node.gap_state.gaps.append(_gap())
    graph.waive_remaining(node.id)
    graph.record_attempt(node.id, "hm", "partial", "because")
    assert node.user_override == "waive_remaining"


# ── waive ────────────────────────────────────────────────────────────────────


def test_waive_remaining_waives_every_open_blocking_gap_and_stays_partial():
    """§5 test 14."""
    graph = _chain(_node("A", "partial"))
    node = graph.nodes[graph.path_order()[0]]
    a, b = _gap("wrong_model", "A"), _gap("missing_prerequisite", "B")
    node.gap_state.gaps.extend([a, b])

    waived = graph.waive_remaining(node.id)

    assert set(waived) == {a.id, b.id}
    assert a.status == "waived" and b.status == "waived"
    assert understanding_of(node) == "partial"
    assert node.user_override == "waive_remaining"


def test_waive_remaining_returns_ids_so_they_can_be_named():
    """§18.16.3: "named, never a bare count" — the completion screen needs the
    ids, not a number."""
    graph = _chain(_node("A"))
    node = graph.nodes[graph.path_order()[0]]
    gap = _gap()
    node.gap_state.gaps.append(gap)
    assert graph.waive_remaining(node.id) == [gap.id]


def test_waive_remaining_leaves_non_blocking_gaps_alone():
    """They never held the node back, so waiving them records a decision the
    learner did not make."""
    graph = _chain(_node("A"))
    node = graph.nodes[graph.path_order()[0]]
    blocking = _gap()
    altitude = _gap("right_idea_wrong_altitude", "too low")
    node.gap_state.gaps.extend([blocking, altitude])
    graph.waive_remaining(node.id)
    assert blocking.status == "waived"
    assert altitude.status == "open"


def test_waive_remaining_does_not_touch_a_verified_gap():
    graph = _chain(_node("A"))
    node = graph.nodes[graph.path_order()[0]]
    verified = _gap()
    verified.mark_verified(0)
    node.gap_state.gaps.append(verified)
    assert graph.waive_remaining(node.id) == []
    assert verified.status == "verified"


def test_a_waived_gap_never_permits_understood():
    """The measure stays honest even though completion no longer depends on it."""
    graph = _chain(_node("A", "understood"))
    node = graph.nodes[graph.path_order()[0]]
    node.gap_state.gaps.append(_gap())
    graph.waive_remaining(node.id)
    assert understanding_of(node) == "partial"


def test_waiving_one_gap_of_two_settles_nothing_yet():
    graph = _chain(_node("A"))
    node = graph.nodes[graph.path_order()[0]]
    a, b = _gap("wrong_model", "A"), _gap("wrong_model", "B")
    node.gap_state.gaps.extend([a, b])
    assert graph.waive_gap(node.id, a.id) is True
    assert a.status == "waived" and b.status == "open"
    assert node.user_override is None       # there is still work here
    assert is_settled(node) is False


def test_waiving_the_last_open_gap_settles_the_node():
    """Otherwise a learner who waived one at a time could never complete:
    `/advance` records `continue` only where a gap is still OPEN, and by then
    none would be."""
    graph = _chain(_node("A"))
    node = graph.nodes[graph.path_order()[0]]
    a, b = _gap("wrong_model", "A"), _gap("wrong_model", "B")
    node.gap_state.gaps.extend([a, b])
    graph.waive_gap(node.id, a.id)
    graph.waive_gap(node.id, b.id)
    assert node.user_override == "waive_remaining"
    assert is_settled(node) is True


def test_waiving_an_unknown_or_settled_gap_changes_nothing():
    graph = _chain(_node("A"))
    node = graph.nodes[graph.path_order()[0]]
    gap = _gap()
    node.gap_state.gaps.append(gap)
    assert graph.waive_gap(node.id, "not-an-id") is False
    assert graph.waive_gap(node.id, gap.id) is True
    assert graph.waive_gap(node.id, gap.id) is False   # already waived
    assert node.gaps[0].status == "waived"


# ── the mark_understood migration ────────────────────────────────────────────


def test_mark_understood_on_a_gap_bearing_node_behaves_as_waive_remaining():
    """§5 test 20, §18.16.2. The learner is saying "stop asking me", not "I have
    demonstrated this", so the action is recorded as what it actually means."""
    graph = _chain(_node("A", "partial"))
    node = graph.nodes[graph.path_order()[0]]
    gap = _gap()
    node.gap_state.gaps.append(gap)

    graph.override(node.id, "mark_understood")

    assert node.user_override == "waive_remaining"
    assert gap.status == "waived"
    assert node.understanding_state == "partial"     # never overwritten
    assert understanding_of(node) != "understood"


def test_mark_understood_is_unchanged_on_a_node_with_no_gap_records():
    """The compatibility rule: vacuously nothing is bypassed, so every session
    written before this phase is unaffected."""
    graph = _chain(_node("A"))
    node = graph.nodes[graph.path_order()[0]]
    graph.override(node.id, "mark_understood")
    assert node.user_override == "mark_understood"
    assert node.understanding_state == "understood"
    assert understanding_of(node) == "understood"


def test_mark_understood_migrates_even_when_every_gap_is_non_blocking():
    """`node.gaps` is the trigger, not `has_open_blocking_gaps`: the rule is
    "a gap-bearing node", and a learner clicking it there is still not claiming
    demonstrated mastery."""
    graph = _chain(_node("A", "partial"))
    node = graph.nodes[graph.path_order()[0]]
    node.gap_state.gaps.append(_gap("right_idea_wrong_altitude", "too low"))
    graph.override(node.id, "mark_understood")
    assert node.user_override == "waive_remaining"
    assert node.understanding_state == "partial"


def test_mark_weak_is_not_a_settling_override():
    """"I don't get this" is the opposite of having dealt with it."""
    assert "mark_weak" not in SETTLING_OVERRIDES
    graph = _chain(_node("A"))
    node = graph.nodes[graph.path_order()[0]]
    graph.override(node.id, "mark_weak")
    assert is_settled(node) is False


# ── is_complete ──────────────────────────────────────────────────────────────


def test_is_complete_is_true_with_waived_gaps_while_readiness_stays_below_one():
    """§5 test 18 — the §18.16.3 target state, asserted directly.

    "Journey complete — verified understanding 92%, 1 gap waived." Two measures,
    neither gating the other.
    """
    a, b = _node("A", "understood"), _node("B", "understood")
    graph = _chain(a, b)
    b.gap_state.gaps.append(_gap())
    graph.waive_remaining(b.id)

    assert graph.is_complete() is True
    assert graph.readiness() < 1.0


def test_is_complete_is_false_while_a_stop_is_merely_visited():
    """Plain `visited` is deliberately not settled: intent must be recorded,
    never inferred."""
    a, b = _node("A", "understood"), _node("B")
    graph = _chain(a, b)
    graph.mark_visited(b.id)
    assert is_settled(b) is False
    assert graph.is_complete() is False


def test_is_complete_ignores_optional_stops():
    a = _node("A", "understood")
    optional = _node("Opt", priority="optional")
    graph = _chain(a, optional)
    assert graph.is_complete() is True


def test_is_complete_is_false_on_an_empty_journey():
    """A graph with nothing on the walk has not been completed; it has not
    started. Returning True would report completion for a failed plan."""
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    assert graph.is_complete() is False


def test_continuing_past_every_stop_completes_the_journey():
    """What makes completion reachable at all (§18.16.3): walking to the end
    settles every stop by construction."""
    a, b = _node("A"), _node("B")
    graph = _chain(a, b)
    for node in (a, b):
        node.gap_state.gaps.append(_gap())
        graph.continue_past(node.id)
    assert graph.is_complete() is True
    assert graph.readiness() < 1.0


# ── stranding: the risk M8 must not ship ─────────────────────────────────────


def test_resume_returns_to_unfinished_remediation():
    """The other half of the requirement: a refresh must not drop the learner
    past work they had not finished."""
    a, b = _node("A", "partial"), _node("B")
    graph = _chain(a, b)
    graph.mark_visited(a.id)
    a.gap_state.gaps.append(_gap())
    graph.set_current(b.id)
    assert graph.resume_point() == a.id


def test_resume_does_NOT_return_to_a_node_the_learner_continued_past():
    """**The stranding guarantee.** Without this, "I'll come back to it" sends
    them straight back on every return, with no move left except answering the
    thing they had just declined to answer."""
    a, b = _node("A", "partial"), _node("B")
    graph = _chain(a, b)
    graph.mark_visited(a.id)
    a.gap_state.gaps.append(_gap())
    graph.continue_past(a.id)
    graph.set_current(b.id)
    assert graph.resume_point() == b.id


def test_resume_does_NOT_return_to_a_node_whose_gaps_were_waived():
    a, b = _node("A", "partial"), _node("B")
    graph = _chain(a, b)
    graph.mark_visited(a.id)
    a.gap_state.gaps.append(_gap())
    graph.waive_remaining(a.id)
    graph.set_current(b.id)
    assert graph.resume_point() == b.id


def test_resume_comes_back_once_the_learner_answers_again():
    """The withdrawal has teeth: returning to work on it makes it the resume
    point again, because the `continue` is gone."""
    a, b = _node("A", "partial"), _node("B")
    graph = _chain(a, b)
    graph.mark_visited(a.id)
    a.gap_state.gaps.append(_gap())
    graph.continue_past(a.id)
    graph.record_attempt(a.id, "trying again", "partial", "because")
    graph.set_current(b.id)
    assert graph.resume_point() == a.id


def test_a_continued_prerequisite_does_not_block_the_node_behind_it():
    """The second stranding shape, and the subtler one.

    A waived or continued prerequisite can NEVER become `understood` — a waived
    gap is unverified forever — so a resume rule requiring mastery of
    prerequisites would leave everything behind it permanently unreachable and
    fall through to the saved position for the rest of the session.
    """
    warm_up, main = _node("Warm-up", "partial"), _node("Main")
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    graph.add_node(warm_up)
    graph.add_node(main)
    graph.add_edge(warm_up.id, main.id, kind="prerequisite")
    graph.mark_visited(warm_up.id)
    warm_up.gap_state.gaps.append(_gap())
    graph.continue_past(warm_up.id)
    graph.set_current(warm_up.id)

    assert graph.resume_point() == main.id


def test_stranding_end_to_end_over_repeated_resumes():
    """The behavioural check no single-function test covers.

    A learner continues past a gap-bearing stop, then resumes repeatedly. Every
    resume must move forward, and the journey must still be completable — a
    system that strands would return the same node forever and never complete.
    """
    a, b, c = _node("A", "partial"), _node("B"), _node("C")
    graph = _chain(a, b, c)
    a.gap_state.gaps.append(_gap())
    graph.mark_visited(a.id)
    graph.continue_past(a.id)
    graph.set_current(b.id)

    seen = []
    for _ in range(3):
        point = graph.resume_point()
        seen.append(point)
        assert point != a.id, "sent back to a stop the learner chose to leave"
    assert set(seen) == {b.id}

    # And the journey can still be finished.
    graph.mark_visited(b.id)
    graph.mark_understanding(b.id, "understood")
    graph.mark_visited(c.id)
    graph.mark_understanding(c.id, "understood")
    assert graph.is_complete() is True


def test_resume_survives_a_round_trip(tmp_path):
    """The decision has to be persisted, or the next session strands anyway."""
    db = tmp_path / "s.db"
    a, b = _node("A", "partial"), _node("B")
    graph = _chain(a, b)
    a.gap_state.gaps.append(_gap())
    graph.mark_visited(a.id)
    graph.continue_past(a.id)
    graph.set_current(b.id)
    learning_store.save_graph(graph, db)

    reloaded = learning_store.load_graph(graph.session_id, db)
    assert reloaded.nodes[a.id].user_override == "continue"
    assert reloaded.resume_point() == b.id


# ── /advance and the refresh guarantee ───────────────────────────────────────


def _session(client, graph) -> str:
    def _pipeline(repo_url, goal, client=None, progress_id=""):
        state = MagicMock()
        state.graph = graph
        state.errors = []
        return state

    with patch("backend.api.run_pipeline", side_effect=_pipeline), \
         patch("backend.api.run_teaching", side_effect=_teaching_side_effect):
        body = client.post(
            "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
        ).json()
    return body["session_id"]


def test_advance_records_continue_when_leaving_open_gaps(client):
    a, b = _node("A", "partial"), _node("B")
    graph = _chain(a, b)
    a.gap_state.gaps.append(_gap())
    session_id = _session(client, graph)

    with patch("backend.api.run_teaching", side_effect=_teaching_side_effect):
        client.post(f"/session/{session_id}/advance", json={"signal": "next"})

    stored = learning_store.load_graph(session_id, api.SESSIONS_DB_PATH)
    assert stored.nodes[a.id].user_override == "continue"


def test_advance_records_nothing_on_a_clean_node(client):
    """The named regression risk: `continue` recorded on nodes without gaps."""
    a, b = _node("A", "understood"), _node("B")
    graph = _chain(a, b)
    session_id = _session(client, graph)

    with patch("backend.api.run_teaching", side_effect=_teaching_side_effect):
        client.post(f"/session/{session_id}/advance", json={"signal": "next"})

    stored = learning_store.load_graph(session_id, api.SESSIONS_DB_PATH)
    assert stored.nodes[a.id].user_override is None


def test_stranding_through_the_real_resume_door(client):
    """**The behavioural validation for M8, through the door a learner uses.**

    `resume_point()` reaches production in exactly one place: `_try_resume`, off
    `/session/start` when a session for the same repo and goal already exists.
    Every other test here calls the function directly, which proves the rule but
    not the wiring — a learner who closes the tab and comes back hits this path,
    and if it strands, the unit tests would all still be green.

    The walk: gaps on stop A, continue past it, then come back three times.
    """
    a, b = _node("A", "partial"), _node("B")
    graph = _chain(a, b)
    a.gap_state.gaps.append(_gap())
    session_id = _session(client, graph)

    with patch("backend.api.run_teaching", side_effect=_teaching_side_effect):
        client.post(f"/session/{session_id}/advance", json={"signal": "next"})

    landed = []
    for _ in range(3):
        with patch("backend.api.run_teaching", side_effect=_teaching_side_effect):
            body = client.post(
                "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
            ).json()
        assert body.get("resumed") is True, "did not take the resume path"
        landed.append(body["graph"]["current_node_id"])

    assert landed == [b.id] * 3, f"stranded: resume kept returning {landed}"

    # The gap is still outstanding and still visible — moving on did not resolve
    # it, and the learner has not been told otherwise.
    stored = learning_store.load_graph(session_id, api.SESSIONS_DB_PATH)
    assert has_open_blocking_gaps(stored.nodes[a.id])
    assert understanding_of(stored.nodes[a.id]) != "understood"


def test_resume_through_the_real_door_DOES_return_to_unfinished_work(client):
    """The mirror of the above: without an explicit decision, resume goes back.

    Both halves have to hold, or "does not strand" would just mean "never
    returns", which loses the remediation instead.
    """
    a, b = _node("A", "partial"), _node("B")
    graph = _chain(a, b)
    a.gap_state.gaps.append(_gap())
    graph.mark_visited(a.id)
    graph.set_current(b.id)
    _session(client, graph)

    with patch("backend.api.run_teaching", side_effect=_teaching_side_effect):
        body = client.post(
            "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
        ).json()
    assert body["graph"]["current_node_id"] == a.id


def test_a_refresh_records_no_override_of_any_kind(client):
    """§5 test 16. A refresh does not advance, so it must not settle anything —
    the property that keeps "dealt with" from being inferred from presence."""
    a, b = _node("A", "partial"), _node("B")
    graph = _chain(a, b)
    a.gap_state.gaps.append(_gap())
    session_id = _session(client, graph)

    for _ in range(3):
        client.get(f"/session/{session_id}")

    stored = learning_store.load_graph(session_id, api.SESSIONS_DB_PATH)
    assert all(n.user_override is None for n in stored.nodes.values())
    assert has_open_blocking_gaps(stored.nodes[a.id])
