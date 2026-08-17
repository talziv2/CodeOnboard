"""M2 — the Grader emits a gap list.

gap-model.md M2. What M2 must prove is narrower than it looks:

  1. Several misconceptions in one answer become several gaps, and two that
     share a `kind` stay two.
  2. The scalar `gap_kind` still says exactly what the single-gap Grader said —
     because everything downstream (`/respond`, the attempt record, the
     Mutator's `Diagnosis`, `adaptation.decide`) still reads it.
  3. Flag-off, nothing changed at all. Not "changed compatibly" — the prompt is
     byte-identical and no gap is recorded.

Arbitration order is asserted here too (§18.12 test 2), because it is a pure
function of the vocabulary and this is where it first has a consumer.

Run with: uv run pytest tests/test_grader_gaps.py -v
"""
import json
from unittest.mock import MagicMock

import pytest

from backend.agents.grader import run
from backend.agents.grader.agent import (
    _GAPS_ADDENDUM,
    _SYSTEM_PROMPT,
    GapOut,
    GraderOutput,
    _parse_output,
    _system_prompt,
)
from backend.learning.gaps import (
    Gap,
    by_precedence,
    dominant_kind,
    objective_key,
    precedence_rank,
)
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.pipeline.state import OnboardState


REPO = "https://github.com/psf/requests"
GOAL = {"primary_goal": "x", "goal_type": "understand_component"}

OBJECTIVE = "Explain what data a Node holds and what solution() reconstructs from it"

# The answer that motivated the whole phase (AIMA search.py, session 9d432157):
# one response, two independent false claims, both `wrong_model`.
CLAIM_A = "child path_cost and depth are filled in later by the search algorithm"
CLAIM_B = "solution() returns both the states and the actions"


@pytest.fixture(autouse=True)
def _flag_off(monkeypatch):
    """Default every test to flag-off, so a test that wants gaps says so.

    The env var leaks between tests otherwise, and a gap test that passes only
    because a previous test set the flag is worse than no test.
    """
    monkeypatch.delenv("CODEONBOARD_GAPS", raising=False)


@pytest.fixture
def flag_on(monkeypatch):
    monkeypatch.setenv("CODEONBOARD_GAPS", "1")


def _state() -> tuple[OnboardState, str]:
    graph = LearningGraph(repo_url=REPO, goal=GOAL)
    node = graph.add_node(LearningNode(
        title="Understand Node as the universal search tree unit",
        code_anchor=CodeAnchor(file="search.py", line_start=68, line_end=130),
        concept_tags=["component", "search"],
        lesson_brief={"why": "why-text", "objective": OBJECTIVE},
    ))
    node.cached_lesson = {"prompt": "What does Node.expand build?", "expected_answer": "…"}
    graph.set_current(node.id)
    state = OnboardState(repo_url=REPO, goal=GOAL)
    state.graph = graph
    return state, node.id


def _client(classification: str, *, gaps=None, gap_kind: str | None = None) -> MagicMock:
    payload: dict = {"classification": classification, "rationale": "because"}
    if gap_kind is not None:
        payload["gap_kind"] = gap_kind
    if gaps is not None:
        payload["gaps"] = gaps
    message = MagicMock()
    message.content = [MagicMock(text=json.dumps(payload))]
    client = MagicMock()
    client.messages.create.return_value = message
    return client


def _gap(kind: str, claim: str, **kw) -> dict:
    return {"kind": kind, "claim": claim, "objective_part": kw.get("part", ""),
            "foundational": kw.get("foundational", False)}


# ── arbitration order (§18.5, §18.12 test 2) ─────────────────────────────────


def test_precedence_is_the_stated_order():
    assert precedence_rank("missing_prerequisite") < precedence_rank("wrong_model")
    assert precedence_rank("wrong_model") < precedence_rank("right_idea_wrong_altitude")
    assert precedence_rank("right_idea_wrong_altitude") < precedence_rank("no_attempt")


def test_an_unknown_kind_never_outranks_a_known_one():
    """Same conservative direction as `is_blocking`: what we cannot read loses."""
    assert precedence_rank("something_new") > precedence_rank("no_attempt")


def test_ordering_is_independent_of_detection_order():
    """The point of a stated precedence: 'first gap wins' was an accident."""
    late_foundation = [
        Gap.create("right_idea_wrong_altitude", "too low"),
        Gap.create("wrong_model", CLAIM_A),
        Gap.create("missing_prerequisite", "does not know what a search tree is"),
    ]
    assert [g.kind for g in by_precedence(late_foundation)] == [
        "missing_prerequisite", "wrong_model", "right_idea_wrong_altitude",
    ]


def test_ties_are_broken_by_detection_order():
    """Stable sort, so two gaps of one kind keep the order they were found in."""
    gaps = [Gap.create("wrong_model", CLAIM_A), Gap.create("wrong_model", CLAIM_B)]
    assert [g.claim for g in by_precedence(gaps)] == [CLAIM_A, CLAIM_B]


def test_dominant_kind_of_nothing_is_none():
    assert dominant_kind([]) == "none"


# ── the objective key ────────────────────────────────────────────────────────


def test_objective_key_is_stable_across_formatting():
    """Same objective, re-wrapped or re-cased, is the same key."""
    assert objective_key(OBJECTIVE) == objective_key(
        "  Explain what data a Node holds\n  and what SOLUTION() reconstructs from it "
    )


def test_objective_key_distinguishes_different_objectives():
    assert objective_key(OBJECTIVE) != objective_key("Explain how BFS orders the frontier")


def test_objective_key_of_nothing_is_empty():
    """An unplanned node has no objective; an empty key reads as 'unkeyed'."""
    assert objective_key("") == ""
    assert objective_key("   ") == ""


# ── the wire format ──────────────────────────────────────────────────────────


def test_a_payload_without_gaps_still_parses():
    """Every pre-M2 payload, and any model that omits the field."""
    out = _parse_output('{"classification": "partial", "gap_kind": "wrong_model", '
                        '"rationale": "close"}')
    assert out.gaps == []
    assert out.gap_kind == "wrong_model"


def test_a_stray_gap_kind_does_not_fail_the_parse():
    """One bad entry costs that entry, never the classification.

    `GapOut.kind` is a plain str for exactly this: typed as the enum, a single
    unrecognised value would throw away a good verdict.
    """
    out = _parse_output(json.dumps({
        "classification": "confused", "rationale": "r",
        "gaps": [_gap("invented_kind", "something"), _gap("wrong_model", CLAIM_A)],
    }))
    assert out.classification == "confused"
    assert [g.kind for g in out.gaps] == ["invented_kind", "wrong_model"]


def test_gap_out_carries_no_id_and_no_blocking_field():
    """Identity is ours; `blocking` is derived. Neither is the model's to send."""
    fields = set(GapOut.model_fields)
    assert "id" not in fields
    assert "blocking" not in fields
    assert fields == {"kind", "claim", "objective_part", "foundational"}


# ── the flag: off changes nothing ────────────────────────────────────────────


def test_flag_off_adds_nothing_to_the_prompt():
    """Flag-off, the Grader sends the base prompt and not one byte more.

    This is the flag contract at the prompt layer: gap detection is *additive*,
    so anything flag-off sees is the base prompt's own behaviour and can be
    reasoned about without reference to this phase. (The base prompt is not
    frozen — the `no_attempt` / `missing_prerequisite` boundary was corrected as
    a standalone defect, which is why this asserts "adds nothing" rather than
    "equals the pre-M2 text".)
    """
    assert _system_prompt() == _SYSTEM_PROMPT
    assert _GAPS_ADDENDUM not in _system_prompt()


def test_flag_on_appends_the_addendum_and_nothing_else(flag_on):
    assert _system_prompt() == _SYSTEM_PROMPT + _GAPS_ADDENDUM


def test_flag_off_records_no_gaps_even_if_the_model_volunteers_them():
    state, node_id = _state()
    run(state, "wrong", client=_client(
        "confused", gaps=[_gap("wrong_model", CLAIM_A)], gap_kind="wrong_model",
    ))
    assert state.graph.nodes[node_id].gaps == []
    # And the scalar is untouched — the pre-M2 path exactly.
    assert state.last_grade["gap_kind"] == "wrong_model"


def test_flag_off_the_grader_still_grades():
    """The classification path is unaffected by any of this."""
    state, node_id = _state()
    run(state, "right", client=_client("understood", gap_kind="none"))
    assert state.graph.nodes[node_id].understanding_state == "understood"


# ── detection: several gaps from one answer ──────────────────────────────────


def test_two_misconceptions_of_the_same_kind_become_two_gaps(flag_on):
    """The traced case. Under the scalar field one of these had nowhere to live."""
    state, node_id = _state()
    run(state, "…", client=_client("confused", gaps=[
        _gap("wrong_model", CLAIM_A, part="what data a Node holds"),
        _gap("wrong_model", CLAIM_B, part="what solution() reconstructs"),
    ]))
    gaps = state.graph.nodes[node_id].gaps
    assert len(gaps) == 2
    assert {g.claim for g in gaps} == {CLAIM_A, CLAIM_B}
    assert len({g.id for g in gaps}) == 2  # distinct identities
    assert all(g.status == "open" for g in gaps)


def test_recorded_gaps_carry_our_id_and_the_objective_key(flag_on):
    state, node_id = _state()
    run(state, "…", client=_client("confused", gaps=[_gap("wrong_model", CLAIM_A)]))
    gap = state.graph.nodes[node_id].gaps[0]
    assert gap.id and len(gap.id) == 32  # uuid4().hex, minted by us
    assert gap.objective_key == objective_key(OBJECTIVE)
    assert gap.opened_at


def test_foundational_is_recorded_as_observed(flag_on):
    """Observed by the model; `blocking` is still computed from `kind`."""
    state, node_id = _state()
    run(state, "…", client=_client("confused", gaps=[
        _gap("missing_prerequisite", "no idea what a frontier is", foundational=True),
    ]))
    gap = state.graph.nodes[node_id].gaps[0]
    assert gap.foundational is True
    assert gap.is_blocking is True  # derived from kind, not from foundational


def test_a_non_blocking_kind_is_still_recorded(flag_on):
    """`right_idea_wrong_altitude` is a real gap that does not block."""
    state, node_id = _state()
    run(state, "…", client=_client("partial", gaps=[
        _gap("right_idea_wrong_altitude", "described the loop instead of the ownership"),
    ]))
    gap = state.graph.nodes[node_id].gaps[0]
    assert gap.is_blocking is False
    assert gap.is_open is True


def test_gaps_are_recorded_even_when_the_answer_is_understood(flag_on):
    """The loss-point-5 precondition.

    M7 makes an open blocking gap prevent `understood`; it can only do that if
    detection does not throw the gap away first because the verdict was kind.
    """
    state, node_id = _state()
    run(state, "…", client=_client("understood", gaps=[_gap("wrong_model", CLAIM_B)]))
    assert len(state.graph.nodes[node_id].gaps) == 1
    assert state.graph.nodes[node_id].understanding_state == "understood"  # M7 changes this


# ── the derived scalar ───────────────────────────────────────────────────────


def test_one_gap_derives_exactly_the_single_gap_graders_answer(flag_on):
    """The M2 compatibility invariant, stated as directly as it can be."""
    for kind in ("missing_prerequisite", "wrong_model", "right_idea_wrong_altitude"):
        state, _ = _state()
        run(state, "…", client=_client("confused", gaps=[_gap(kind, "a claim")]))
        assert state.last_grade["gap_kind"] == kind


def test_the_scalar_is_the_highest_precedence_gap_not_the_first(flag_on):
    state, _ = _state()
    run(state, "…", client=_client("confused", gaps=[
        _gap("right_idea_wrong_altitude", "too low"),
        _gap("missing_prerequisite", "foundation absent"),
    ]))
    assert state.last_grade["gap_kind"] == "missing_prerequisite"


def test_the_derived_scalar_overrides_what_the_model_claimed(flag_on):
    """Models observe, code decides — including about its own scalar."""
    state, _ = _state()
    run(state, "…", client=_client(
        "confused",
        gap_kind="right_idea_wrong_altitude",
        gaps=[_gap("missing_prerequisite", "foundation absent")],
    ))
    assert state.last_grade["gap_kind"] == "missing_prerequisite"


def test_the_scalar_describes_this_answer_not_the_accumulated_node(flag_on):
    """A gap left by an earlier attempt must not relabel a later answer.

    The scalar is carried into the attempt record and the Mutator's `Diagnosis`,
    which describe one answer each. Arbitrating over every open gap on the node
    is M4's job, asked at a different moment.
    """
    state, node_id = _state()
    run(state, "first", client=_client("confused", gaps=[
        _gap("missing_prerequisite", "foundation absent"),
    ]))
    state.graph.nodes[node_id].attempts.append({"answer": "first"})

    run(state, "second", client=_client("partial", gaps=[
        _gap("right_idea_wrong_altitude", "too low"),
    ]))
    assert state.last_grade["gap_kind"] == "right_idea_wrong_altitude"
    assert len(state.graph.nodes[node_id].gaps) == 2  # both still open


def test_origin_attempt_points_at_the_attempt_about_to_be_recorded(flag_on):
    """The audit link between a gap and the answer that opened it."""
    state, node_id = _state()
    node = state.graph.nodes[node_id]
    node.attempts.append({"answer": "an earlier one"})

    run(state, "…", client=_client("confused", gaps=[_gap("wrong_model", CLAIM_A)]))
    assert node.gaps[0].origin_attempt == 1


# ── what must never become a gap ─────────────────────────────────────────────


def test_off_topic_opens_no_gaps_whatever_the_model_listed(flag_on):
    """F2 one layer up: declining to guess must not earn a sticky penalty."""
    state, node_id = _state()
    run(state, "no idea", client=_client("off-topic", gap_kind="no_attempt", gaps=[
        _gap("missing_prerequisite", "they know nothing about search"),
    ]))
    assert state.graph.nodes[node_id].gaps == []
    assert state.last_grade["gap_kind"] == "no_attempt"


def test_no_attempt_and_none_are_dropped_as_gap_kinds(flag_on):
    state, node_id = _state()
    run(state, "…", client=_client("partial", gap_kind="no_attempt", gaps=[
        _gap("no_attempt", "did not try"), _gap("none", "nothing"),
    ]))
    assert state.graph.nodes[node_id].gaps == []
    # Nothing minted, so the model's scalar stands rather than being erased.
    assert state.last_grade["gap_kind"] == "no_attempt"


def test_an_unknown_kind_is_dropped_without_losing_the_others(flag_on):
    state, node_id = _state()
    run(state, "…", client=_client("confused", gaps=[
        _gap("severity_9", "invented"), _gap("wrong_model", CLAIM_A),
    ]))
    gaps = state.graph.nodes[node_id].gaps
    assert [g.claim for g in gaps] == [CLAIM_A]
    assert state.last_grade["gap_kind"] == "wrong_model"


def test_an_empty_claim_is_dropped(flag_on):
    """A gap with no claim is not a misconception, it is a blank."""
    state, node_id = _state()
    run(state, "…", client=_client("confused", gaps=[
        _gap("wrong_model", "   "), _gap("wrong_model", CLAIM_B),
    ]))
    assert [g.claim for g in state.graph.nodes[node_id].gaps] == [CLAIM_B]


def test_a_grading_failure_records_no_gaps(flag_on):
    """The fallback verdict is `partial` with no diagnosis — and no gap."""
    state, node_id = _state()
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("boom")
    run(state, "…", client=client)
    assert state.graph.nodes[node_id].gaps == []
    assert state.last_grade["classification"] == "partial"


# ── persistence, end to end through the store ────────────────────────────────


def test_detected_gaps_survive_a_save_and_load(flag_on, tmp_path):
    """Detection is only useful if it lands in the database intact."""
    from backend.learning import store as learning_store

    db = tmp_path / "sessions.db"
    state, node_id = _state()
    run(state, "…", client=_client("confused", gaps=[
        _gap("wrong_model", CLAIM_A, part="what data a Node holds"),
        _gap("wrong_model", CLAIM_B, part="what solution() reconstructs"),
    ]))
    learning_store.save_graph(state.graph, db)

    reloaded = learning_store.load_graph(state.graph.session_id, db)
    gaps = reloaded.nodes[node_id].gaps
    assert [(g.id, g.kind, g.claim, g.objective_part) for g in gaps] == [
        (g.id, g.kind, g.claim, g.objective_part) for g in state.graph.nodes[node_id].gaps
    ]
