"""M2 — the Grader emits a gap list.

gap-model.md M2. What M2 must prove is narrower than it looks:

  1. Several misconceptions in one answer become several gaps, and two that
     share a `kind` stay two.
  2. The scalar `gap_kind` still says exactly what the single-gap Grader said —
     because everything downstream (`/respond`, the attempt record, the
     Mutator's `Diagnosis`, `adaptation.decide`) still reads it.
  3. The gap addendum is exactly an addendum — the prompt is the base text plus
     that block and nothing else, which is what makes the recorded 48-case
     evaluation of the base prompt still readable against today's.

Arbitration order is asserted here too (§18.12 test 2), because it is a pure
function of the vocabulary and this is where it first has a consumer.

Run with: uv run pytest tests/test_grader_gaps.py -v
"""
import json
from unittest.mock import MagicMock

from tests.conftest import TEST_USER_ID

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
    out = {"kind": kind, "claim": claim, "objective_part": kw.get("part", ""),
           "foundational": kw.get("foundational", False)}
    if "refers_to" in kw:
        out["refers_to"] = kw["refers_to"]
    return out


def _sent_user_content(client: MagicMock) -> str:
    return client.messages.create.call_args.kwargs["messages"][0]["content"]


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


def test_gap_out_can_reference_an_id_but_never_mint_one():
    """Identity is ours; `blocking` is derived. Neither is the model's to assign.

    `refers_to` is the one id-shaped field, and it is a *pointer at a value we
    supplied* — validated against the open set in `_record_gaps`, never written
    through to a gap. There is still no field through which the model can create
    an identity.
    """
    fields = set(GapOut.model_fields)
    assert "id" not in fields
    assert "blocking" not in fields
    assert fields == {"kind", "claim", "objective_part", "foundational", "refers_to"}
    assert GapOut(kind="wrong_model", claim="x").refers_to == "new"


# ── the addendum is exactly an addendum ──────────────────────────────────────


def test_the_prompt_is_the_base_text_plus_the_addendum():
    """Gap detection is *additive*, and the seam is load-bearing evidence.

    `CODEONBOARD_GAPS` used to make this a pair — one test per side, proving the
    flag-off prompt was the base text and not one byte more. The flag is gone and
    gap detection is unconditional, but the concatenation is still asserted here
    because the recorded 48-case grader evaluation was run against exactly this
    seam: keep the two halves separable and the old numbers stay comparable to
    the current prompt.
    """
    assert _system_prompt() == _SYSTEM_PROMPT + _GAPS_ADDENDUM


# ── detection: several gaps from one answer ──────────────────────────────────


def test_two_misconceptions_of_the_same_kind_become_two_gaps():
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


def test_recorded_gaps_carry_our_id_and_the_objective_key():
    state, node_id = _state()
    run(state, "…", client=_client("confused", gaps=[_gap("wrong_model", CLAIM_A)]))
    gap = state.graph.nodes[node_id].gaps[0]
    assert gap.id and len(gap.id) == 32  # uuid4().hex, minted by us
    assert gap.objective_key == objective_key(OBJECTIVE)
    assert gap.opened_at


def test_foundational_is_recorded_as_observed():
    """Observed by the model; `blocking` is still computed from `kind`."""
    state, node_id = _state()
    run(state, "…", client=_client("confused", gaps=[
        _gap("missing_prerequisite", "no idea what a frontier is", foundational=True),
    ]))
    gap = state.graph.nodes[node_id].gaps[0]
    assert gap.foundational is True
    assert gap.is_blocking is True  # derived from kind, not from foundational


def test_a_non_blocking_kind_is_still_recorded():
    """`right_idea_wrong_altitude` is a real gap that does not block."""
    state, node_id = _state()
    run(state, "…", client=_client("partial", gaps=[
        _gap("right_idea_wrong_altitude", "described the loop instead of the ownership"),
    ]))
    gap = state.graph.nodes[node_id].gaps[0]
    assert gap.is_blocking is False
    assert gap.is_open is True


def test_gaps_are_recorded_even_when_the_answer_is_understood():
    """The loss-point-5 precondition.

    M7 makes an open blocking gap prevent `understood`; it can only do that if
    detection does not throw the gap away first because the verdict was kind.
    """
    state, node_id = _state()
    run(state, "…", client=_client("understood", gaps=[_gap("wrong_model", CLAIM_B)]))
    assert len(state.graph.nodes[node_id].gaps) == 1
    assert state.graph.nodes[node_id].understanding_state == "understood"  # M7 changes this


# ── the derived scalar ───────────────────────────────────────────────────────


def test_one_gap_derives_exactly_the_single_gap_graders_answer():
    """The M2 compatibility invariant, stated as directly as it can be."""
    for kind in ("missing_prerequisite", "wrong_model", "right_idea_wrong_altitude"):
        state, _ = _state()
        run(state, "…", client=_client("confused", gaps=[_gap(kind, "a claim")]))
        assert state.last_grade["gap_kind"] == kind


def test_the_scalar_is_the_highest_precedence_gap_not_the_first():
    state, _ = _state()
    run(state, "…", client=_client("confused", gaps=[
        _gap("right_idea_wrong_altitude", "too low"),
        _gap("missing_prerequisite", "foundation absent"),
    ]))
    assert state.last_grade["gap_kind"] == "missing_prerequisite"


def test_the_derived_scalar_overrides_what_the_model_claimed():
    """Models observe, code decides — including about its own scalar."""
    state, _ = _state()
    run(state, "…", client=_client(
        "confused",
        gap_kind="right_idea_wrong_altitude",
        gaps=[_gap("missing_prerequisite", "foundation absent")],
    ))
    assert state.last_grade["gap_kind"] == "missing_prerequisite"


def test_the_scalar_describes_this_answer_not_the_accumulated_node():
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


def test_origin_attempt_points_at_the_attempt_about_to_be_recorded():
    """The audit link between a gap and the answer that opened it."""
    state, node_id = _state()
    node = state.graph.nodes[node_id]
    node.attempts.append({"answer": "an earlier one"})

    run(state, "…", client=_client("confused", gaps=[_gap("wrong_model", CLAIM_A)]))
    assert node.gaps[0].origin_attempt == 1


# ── what must never become a gap ─────────────────────────────────────────────


def test_off_topic_opens_no_gaps_whatever_the_model_listed():
    """F2 one layer up: declining to guess must not earn a sticky penalty."""
    state, node_id = _state()
    run(state, "no idea", client=_client("off-topic", gap_kind="no_attempt", gaps=[
        _gap("missing_prerequisite", "they know nothing about search"),
    ]))
    assert state.graph.nodes[node_id].gaps == []
    assert state.last_grade["gap_kind"] == "no_attempt"


def test_no_attempt_and_none_are_dropped_as_gap_kinds():
    state, node_id = _state()
    run(state, "…", client=_client("partial", gap_kind="no_attempt", gaps=[
        _gap("no_attempt", "did not try"), _gap("none", "nothing"),
    ]))
    assert state.graph.nodes[node_id].gaps == []
    # Nothing minted, so the model's scalar stands rather than being erased.
    assert state.last_grade["gap_kind"] == "no_attempt"


def test_an_unknown_kind_is_dropped_without_losing_the_others():
    state, node_id = _state()
    run(state, "…", client=_client("confused", gaps=[
        _gap("severity_9", "invented"), _gap("wrong_model", CLAIM_A),
    ]))
    gaps = state.graph.nodes[node_id].gaps
    assert [g.claim for g in gaps] == [CLAIM_A]
    assert state.last_grade["gap_kind"] == "wrong_model"


def test_an_empty_claim_is_dropped():
    """A gap with no claim is not a misconception, it is a blank."""
    state, node_id = _state()
    run(state, "…", client=_client("confused", gaps=[
        _gap("wrong_model", "   "), _gap("wrong_model", CLAIM_B),
    ]))
    assert [g.claim for g in state.graph.nodes[node_id].gaps] == [CLAIM_B]


def test_a_grading_failure_records_no_gaps():
    """The fallback verdict is `partial` with no diagnosis — and no gap."""
    state, node_id = _state()
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("boom")
    run(state, "…", client=client)
    assert state.graph.nodes[node_id].gaps == []
    assert state.last_grade["classification"] == "partial"


# ── persistence, end to end through the store ────────────────────────────────


# ── M3: identity across re-grades ────────────────────────────────────────────


def _with_two_open_gaps() -> tuple[OnboardState, str, Gap, Gap]:
    state, node_id = _state()
    node = state.graph.nodes[node_id]
    a = Gap.create("wrong_model", CLAIM_A, objective_part="what a Node holds")
    b = Gap.create("wrong_model", CLAIM_B, objective_part="what solution() returns")
    node.gap_state.gaps.extend([a, b])
    return state, node_id, a, b


def test_a_first_detection_shows_no_open_gaps_section():
    """No section, no ids: a first detection is recognisably not a re-grade."""
    state, _ = _state()
    client = _client("confused", gaps=[_gap("wrong_model", CLAIM_A)])
    run(state, "…", client=client)
    assert "OPEN GAPS" not in _sent_user_content(client)


def test_a_re_grade_shows_every_open_gap_with_its_id():
    state, _, a, b = _with_two_open_gaps()
    client = _client("partial")
    run(state, "another go", client=client)
    sent = _sent_user_content(client)
    assert "OPEN GAPS" in sent
    for gap in (a, b):
        assert gap.id in sent
        assert gap.claim in sent


def test_settled_gaps_are_never_offered_for_matching():
    """A verified gap is closed and a waived one is set aside; neither is a
    candidate for 'the developer said this again'."""
    state, node_id, a, b = _with_two_open_gaps()
    a.status = "verified"
    b.status = "waived"
    client = _client("partial")
    run(state, "…", client=client)
    sent = _sent_user_content(client)
    assert "OPEN GAPS" not in sent
    assert a.id not in sent and b.id not in sent


def test_a_matched_id_does_not_duplicate_the_gap():
    """The point of identity: one misconception stays one gap across attempts."""
    state, node_id, a, b = _with_two_open_gaps()
    run(state, "same mistake again", client=_client("confused", gaps=[
        _gap("wrong_model", "the child's cost is filled in later", refers_to=a.id),
    ]))
    gaps = state.graph.nodes[node_id].gaps
    assert len(gaps) == 2
    assert state.last_grade["gap_report"] == {"matched": 1, "new": 0, "rejected": 0}


def test_a_matched_gap_keeps_its_id_and_its_original_claim():
    """A gap id never changes, and a re-report does not rewrite the record."""
    state, node_id, a, _ = _with_two_open_gaps()
    run(state, "…", client=_client("confused", gaps=[
        _gap("wrong_model", "reworded entirely", refers_to=a.id),
    ]))
    same = [g for g in state.graph.nodes[node_id].gaps if g.id == a.id][0]
    assert same.claim == CLAIM_A
    assert same.status == "open"


def test_a_new_declaration_mints_alongside_the_open_ones():
    state, node_id, a, b = _with_two_open_gaps()
    run(state, "…", client=_client("confused", gaps=[
        _gap("wrong_model", "a third, different false claim", refers_to="new"),
    ]))
    gaps = state.graph.nodes[node_id].gaps
    assert len(gaps) == 3
    assert state.last_grade["gap_report"] == {"matched": 0, "new": 1, "rejected": 0}


def test_matched_and_new_in_one_answer():
    state, node_id, a, b = _with_two_open_gaps()
    run(state, "…", client=_client("confused", gaps=[
        _gap("wrong_model", "still wrong about the same thing", refers_to=b.id),
        _gap("missing_prerequisite", "and a fresh foundation gap", refers_to="new"),
    ]))
    assert len(state.graph.nodes[node_id].gaps) == 3
    assert state.last_grade["gap_report"] == {"matched": 1, "new": 1, "rejected": 0}


def test_an_invented_id_is_rejected_and_changes_nothing():
    """§18.12 test 12. Not minted as new either: an entry claiming to be an
    existing gap is a claim we cannot verify, and guessing is worse than losing
    it."""
    state, node_id, a, b = _with_two_open_gaps()
    before = [(g.id, g.claim, g.status) for g in state.graph.nodes[node_id].gaps]
    run(state, "…", client=_client("confused", gaps=[
        _gap("wrong_model", "claims to be an existing gap", refers_to="deadbeef00"),
    ]))
    after = [(g.id, g.claim, g.status) for g in state.graph.nodes[node_id].gaps]
    assert after == before
    assert state.last_grade["gap_report"] == {"matched": 0, "new": 0, "rejected": 1}


def test_one_rejected_entry_does_not_cost_the_others():
    state, node_id, a, _ = _with_two_open_gaps()
    run(state, "…", client=_client("confused", gaps=[
        _gap("wrong_model", "bogus reference", refers_to="not-an-id"),
        _gap("wrong_model", "a genuinely new claim", refers_to="new"),
    ]))
    assert len(state.graph.nodes[node_id].gaps) == 3
    assert state.last_grade["gap_report"] == {"matched": 0, "new": 1, "rejected": 1}
    assert state.last_grade["classification"] == "confused"


def test_an_id_is_ignored_when_no_list_was_offered():
    """First detection: we showed no ids, so none can be legitimately named.

    Rejecting here would lose a real first detection over a field the model was
    never given the data to fill in.
    """
    state, node_id = _state()
    run(state, "…", client=_client("confused", gaps=[
        _gap("wrong_model", CLAIM_A, refers_to="some-id-we-never-supplied"),
    ]))
    assert len(state.graph.nodes[node_id].gaps) == 1
    assert state.last_grade["gap_report"] == {"matched": 0, "new": 1, "rejected": 0}


def test_the_scalar_reflects_a_matched_gap_with_nothing_new():
    """Repeating an old misconception is still why THIS answer fell short."""
    state, node_id = _state()
    node = state.graph.nodes[node_id]
    foundation = Gap.create("missing_prerequisite", "does not know what a frontier is")
    node.gap_state.gaps.append(foundation)
    run(state, "…", client=_client("confused", gap_kind="wrong_model", gaps=[
        _gap("missing_prerequisite", "same foundation missing", refers_to=foundation.id),
    ]))
    assert state.last_grade["gap_kind"] == "missing_prerequisite"


def test_an_unreported_open_gap_is_left_open_and_untouched():
    """§18.5: 'What happens to the rest. Nothing.' Silence is not resolution."""
    state, node_id, a, b = _with_two_open_gaps()
    run(state, "…", client=_client("partial", gaps=[
        _gap("wrong_model", "only about A", refers_to=a.id),
    ]))
    untouched = [g for g in state.graph.nodes[node_id].gaps if g.id == b.id][0]
    assert untouched.status == "open"
    assert untouched.resolved_by is None


def test_gap_report_is_always_present():
    """It used to be absent flag-off, which is why the key was optional.

    Nothing reads it — it exists so the re-grade duplication rate is observable
    in a harness. With recording unconditional it is unconditional too, and a
    harness can stop asking whether the key is there.
    """
    state, _ = _state()
    run(state, "…", client=_client("confused", gaps=[_gap("wrong_model", CLAIM_A)]))
    assert state.last_grade["gap_report"]["new"]


def test_two_same_kind_gaps_survive_save_load_and_a_re_grade(tmp_path):
    """§18.12 test 11, end to end through the store.

    Two `wrong_model` gaps go in, a round trip happens, the reloaded graph is
    re-graded, and they are still two gaps with the ids they started with.
    """
    from backend.learning import store as learning_store

    db = tmp_path / "sessions.db"
    state, node_id = _state()
    run(state, "first", client=_client("confused", gaps=[
        _gap("wrong_model", CLAIM_A), _gap("wrong_model", CLAIM_B),
    ]))
    original = [(g.id, g.claim) for g in state.graph.nodes[node_id].gaps]
    assert len(original) == 2
    learning_store.save_graph(state.graph, db, user_id=TEST_USER_ID)

    reloaded = learning_store.load_graph(state.graph.session_id, TEST_USER_ID, db)
    resumed = OnboardState(repo_url=REPO, goal=GOAL)
    resumed.graph = reloaded
    client = _client("confused", gaps=[
        _gap("wrong_model", "A again, reworded", refers_to=original[0][0]),
    ])
    run(resumed, "second", client=client)

    # The reloaded ids were offered for matching, and matching kept the count.
    assert original[0][0] in _sent_user_content(client)
    assert [(g.id, g.claim) for g in reloaded.nodes[node_id].gaps] == original
    assert resumed.last_grade["gap_report"] == {"matched": 1, "new": 0, "rejected": 0}


# ── persistence, end to end through the store ────────────────────────────────


def test_detected_gaps_survive_a_save_and_load(tmp_path):
    """Detection is only useful if it lands in the database intact."""
    from backend.learning import store as learning_store

    db = tmp_path / "sessions.db"
    state, node_id = _state()
    run(state, "…", client=_client("confused", gaps=[
        _gap("wrong_model", CLAIM_A, part="what data a Node holds"),
        _gap("wrong_model", CLAIM_B, part="what solution() reconstructs"),
    ]))
    learning_store.save_graph(state.graph, db, user_id=TEST_USER_ID)

    reloaded = learning_store.load_graph(state.graph.session_id, TEST_USER_ID, db)
    gaps = reloaded.nodes[node_id].gaps
    assert [(g.id, g.kind, g.claim, g.objective_part) for g in gaps] == [
        (g.id, g.kind, g.claim, g.objective_part) for g in state.graph.nodes[node_id].gaps
    ]
