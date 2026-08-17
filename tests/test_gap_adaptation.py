"""M4 — the adaptation policy over a whole set of gaps.

gap-model.md M4. `decide_all` generalises `decide` from one gap to many, and the
load-bearing claim is that it does so without changing any existing behaviour:
**with zero or one gap the two agree exactly**, asserted below against the
existing policy table rather than against a re-typed copy of it.

What is genuinely new is only the multi-gap arbitration of §18.5 — precedence
picks the response, one mutation but many corrections, and overflow collapses.

Run with: uv run pytest tests/test_gap_adaptation.py -v
"""
import itertools

import pytest

from backend.learning.adaptation import (
    ACTIVE_SET_MAX,
    _ACTION_BY_GAP,
    Plan,
    decide,
    decide_all,
)
from backend.learning.gaps import GAP_KINDS, Gap


CLASSIFICATIONS = ("understood", "partial", "confused", "off-topic")


def _gap(kind: str, claim: str = "a false claim") -> Gap:
    return Gap.create(kind, claim)


# ── the compatibility invariant ──────────────────────────────────────────────


@pytest.mark.parametrize("classification", CLASSIFICATIONS)
@pytest.mark.parametrize("kind", sorted(GAP_KINDS))
def test_one_gap_decides_exactly_what_decide_decides(classification, kind):
    """The M4 invariant, against the live table — not a copy of it.

    Parametrised over every (classification, kind) pair rather than a sample, so
    a future edit to `_ACTION_BY_GAP` cannot make the two functions disagree
    without failing here.
    """
    assert decide_all(classification, [_gap(kind)]).action == decide(classification, kind)


@pytest.mark.parametrize("classification", CLASSIFICATIONS)
def test_no_gaps_decides_exactly_what_decide_decides(classification):
    """Including `off-topic` earning nothing, and `confused` falling back to
    `prerequisite` the way every pre-B5 session did."""
    assert decide_all(classification, []).action == decide(classification, None)
    assert decide_all(classification, None).action == decide(classification, None)


def test_the_off_topic_plus_named_gap_rule_survives():
    """The B5 defect, re-asserted at the new entry point.

    A learner who says "I can't follow this, I don't know what a function
    signature is" is classified `off-topic` AND diagnosed
    `missing_prerequisite`. The specific signal must still outrank the coarse
    one, or the fix regresses through the new door.
    """
    plan = decide_all("off-topic", [_gap("missing_prerequisite")])
    assert plan.action == "prerequisite"


def test_off_topic_with_no_gap_still_earns_nothing():
    assert decide_all("off-topic", []).action == "none"


def test_understood_earns_nothing_even_with_an_open_blocking_gap():
    """Not a re-teach: an answer that reached the objective is VERIFIED, which
    is a different act with a different producer (§18.16.2). The gap stays open
    and stays blocking — that is M7's business, not this function's."""
    gap = _gap("wrong_model")
    plan = decide_all("understood", [gap])
    assert plan.action == "none"
    assert plan.active_set == (gap,)
    assert gap.status == "open"


# ── precedence picks the response ────────────────────────────────────────────


def test_the_highest_precedence_gap_picks_the_action():
    plan = decide_all("confused", [
        _gap("right_idea_wrong_altitude"), _gap("missing_prerequisite"),
    ])
    assert plan.action == "prerequisite"


def test_precedence_is_independent_of_detection_order():
    kinds = ["missing_prerequisite", "wrong_model", "right_idea_wrong_altitude"]
    for order in itertools.permutations(kinds):
        plan = decide_all("confused", [_gap(k) for k in order])
        assert plan.action == "prerequisite", order


def test_wrong_model_leads_when_no_foundation_is_missing():
    plan = decide_all("confused", [
        _gap("right_idea_wrong_altitude"), _gap("wrong_model"),
    ])
    assert plan.action == "reteach"


# ── one mutation, many corrections ───────────────────────────────────────────


def test_a_prerequisite_targets_exactly_one_gap():
    """Two foundational gaps must not grow two warm-ups from one answer."""
    a, b = _gap("missing_prerequisite", "A"), _gap("missing_prerequisite", "B")
    plan = decide_all("confused", [a, b])
    assert plan.action == "prerequisite"
    assert plan.targets == (a,)


def test_a_reteach_targets_every_open_gap_of_its_kind():
    """The traced case: two `wrong_model` gaps, one lesson naming both."""
    a, b = _gap("wrong_model", "A"), _gap("wrong_model", "B")
    plan = decide_all("confused", [a, b])
    assert plan.action == "reteach"
    assert {g.id for g in plan.targets} == {a.id, b.id}


def test_a_followup_targets_every_open_gap_of_its_kind():
    a, b = _gap("right_idea_wrong_altitude", "A"), _gap("right_idea_wrong_altitude", "B")
    plan = decide_all("partial", [a, b])
    assert plan.action == "followup"
    assert {g.id for g in plan.targets} == {a.id, b.id}


def test_gaps_of_different_kinds_are_never_merged_into_one_response():
    """A hint and a correction are not the same act (§18.5)."""
    reteachable = _gap("wrong_model")
    altitude = _gap("right_idea_wrong_altitude")
    plan = decide_all("confused", [reteachable, altitude])
    assert plan.action == "reteach"
    assert plan.targets == (reteachable,)
    assert altitude not in plan.targets


def test_targets_are_in_precedence_order():
    a, b = _gap("wrong_model", "first"), _gap("wrong_model", "second")
    assert decide_all("confused", [b, a]).targets == (b, a)  # stable within a rank


def test_unaddressed_gaps_stay_open():
    """§18.5: 'What happens to the rest. Nothing.'"""
    lead = _gap("missing_prerequisite")
    rest = [_gap("wrong_model"), _gap("right_idea_wrong_altitude")]
    decide_all("confused", [lead] + rest)
    assert all(g.status == "open" for g in [lead] + rest)


# ── the active set is operational, not semantic ──────────────────────────────


def test_the_active_set_is_capped_and_the_overflow_is_reported():
    gaps = [_gap("wrong_model", f"claim {i}") for i in range(5)]
    plan = decide_all("confused", gaps)
    assert len(plan.active_set) == ACTIVE_SET_MAX
    assert len(plan.deferred) == 5 - ACTIVE_SET_MAX


def test_queue_membership_never_changes_a_gaps_status_or_blocking():
    """§18.16.1: a blocking gap outside the working set is still open and still
    blocking — it is simply not what is being taught right now."""
    gaps = [_gap("wrong_model", f"claim {i}") for i in range(5)]
    plan = decide_all("confused", gaps)
    for gap in plan.deferred:
        assert gap.status == "open"
        assert gap.is_blocking is True


def test_the_active_set_holds_blocking_gaps_only():
    """Derived from open BLOCKING gaps by §18.5 precedence."""
    blocking = _gap("wrong_model")
    non_blocking = _gap("right_idea_wrong_altitude")
    plan = decide_all("confused", [blocking, non_blocking])
    assert plan.active_set == (blocking,)


def test_a_non_blocking_gap_still_earns_a_response_with_an_empty_active_set():
    """The active set bounds remediation of gaps that block `understood`; it is
    not a precondition for responding to the learner at all."""
    plan = decide_all("partial", [_gap("right_idea_wrong_altitude")])
    assert plan.action == "followup"
    assert plan.active_set == ()


def test_settled_gaps_are_ignored_entirely():
    verified, waived = _gap("wrong_model"), _gap("missing_prerequisite")
    verified.status = "verified"
    waived.status = "waived"
    plan = decide_all("confused", [verified, waived])
    assert plan.action == "prerequisite"  # the no-gap `confused` fallback
    assert plan.targets == ()
    assert plan.active_set == ()


# ── overflow collapses to one re-teach ───────────────────────────────────────


def test_more_blocking_gaps_than_the_queue_holds_collapses_to_one_reteach():
    """§18.16.1: that many gaps is itself one signal — the unit did not land."""
    gaps = [_gap("wrong_model", f"claim {i}") for i in range(ACTIVE_SET_MAX + 1)]
    plan = decide_all("confused", gaps)
    assert plan.collapsed is True
    assert plan.action == "reteach"


def test_collapse_overrides_precedence_rather_than_fanning_out_warm_ups():
    """A foundational gap would normally win. With the unit this far from
    landing, a queue of warm-ups is the wrong shape of response."""
    gaps = [_gap("missing_prerequisite", f"claim {i}") for i in range(ACTIVE_SET_MAX + 1)]
    plan = decide_all("confused", gaps)
    assert plan.action == "reteach"
    assert plan.collapsed is True


def test_a_collapsed_reteach_names_every_blocking_gap_not_just_the_active_ones():
    """The lesson is being given again in full; scoping it to three of five
    would leave two corrections unmade with nothing queued to make them."""
    gaps = [_gap("wrong_model", f"claim {i}") for i in range(5)]
    plan = decide_all("confused", gaps)
    assert len(plan.targets) == 5
    assert len(plan.active_set) == ACTIVE_SET_MAX


def test_exactly_the_cap_does_not_collapse():
    gaps = [_gap("missing_prerequisite", f"claim {i}") for i in range(ACTIVE_SET_MAX)]
    plan = decide_all("confused", gaps)
    assert plan.collapsed is False
    assert plan.action == "prerequisite"  # precedence still applies
    assert len(plan.targets) == 1


def test_non_blocking_gaps_do_not_trigger_a_collapse():
    """Only blocking gaps fill the queue — the cap is about what must be closed."""
    gaps = [_gap("right_idea_wrong_altitude", f"claim {i}") for i in range(6)]
    plan = decide_all("partial", gaps)
    assert plan.collapsed is False
    assert plan.action == "followup"


# ── robustness ───────────────────────────────────────────────────────────────


def test_an_unknown_gap_kind_earns_the_no_gap_fallback():
    """A store written by a future version must not produce a guessed response."""
    strange = Gap(id="x", kind="something_new", claim="?")
    plan = decide_all("confused", [strange])
    assert plan.action == decide("confused", None)
    assert plan.targets == ()


def test_the_plan_is_immutable():
    """It is a decision, not a workspace. Nothing downstream may edit it."""
    plan = decide_all("confused", [_gap("wrong_model")])
    with pytest.raises(Exception):
        plan.action = "hint"


def test_decide_all_mutates_nothing():
    gaps = [_gap("wrong_model", "A"), _gap("missing_prerequisite", "B")]
    before = [(g.id, g.kind, g.claim, g.status, g.verification_attempts) for g in gaps]
    decide_all("confused", gaps)
    assert [(g.id, g.kind, g.claim, g.status, g.verification_attempts) for g in gaps] == before


def test_every_action_the_table_can_produce_is_reachable():
    """Guards against a kind being added to `_ACTION_BY_GAP` with no path to it."""
    reachable = set()
    for kind in GAP_KINDS:
        reachable.add(decide_all("confused", [_gap(kind)]).action)
    expected = {_ACTION_BY_GAP[k] for k in GAP_KINDS}
    assert reachable == expected


def test_plan_defaults_are_empty_rather_than_none():
    """Callers iterate these; `None` would make every consumer defensive."""
    plan = Plan("none")
    assert plan.targets == () and plan.active_set == () and plan.deferred == ()
    assert plan.collapsed is False
