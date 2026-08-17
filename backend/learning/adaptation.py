# How the system responds to a graded answer.
#
# Before this, adaptation was one-directional and one-shaped: any wrong answer
# inserted a prerequisite (learning-engine.md L9). "I don't know" and a confident
# misconception were treated identically, which is wrong in both directions — the
# first wants a nudge, the second wants correcting, and neither is served by
# growing the journey.
#
# This module owns the DECISION and nothing else. The policy is a table, not a
# model call: which response a gap deserves is a rule we are willing to state and
# test, and a model asked to choose would make it unpredictable for no gain. What
# each response then SAYS is generated (a hint, a correction, a follow-up) — that
# is judgement and belongs to a model.
#
# Everything here is pure: no IO, no LLM, no mutation of anything but the graph
# passed in. That is what makes the policy testable without an API key.

from dataclasses import dataclass, field
from typing import Literal

from backend.learning.gaps import (
    REMEDIATION_ROUND_CAP,
    Gap,
    by_precedence,
)
from backend.learning.graph import LearningGraph, understanding_of


# What the system does in response. `none` means the answer needs no response
# beyond being recorded.
Action = Literal["none", "hint", "reteach", "prerequisite", "followup"]

# The policy (§9.1). Keyed on the Grader's `gap_kind` — WHY the answer fell
# short — rather than on the verdict, which only says how far.
#
#   no_attempt                they did not try. A prerequisite would answer a
#                             question they never asked; a hint is the response
#                             to being stuck.
#   wrong_model               a confident misconception. The misconception itself
#                             is the thing to correct, and it must be NAMED —
#                             re-teaching the same lesson unchanged would leave
#                             them to make the same inference twice.
#   missing_prerequisite      a foundation is genuinely absent. This is the one
#                             case that earns a structural change.
#   right_idea_wrong_altitude the substance is right, pitched wrong. One
#                             clarifying exchange, then move on — restructuring a
#                             journey over a framing slip is an overreaction.
_ACTION_BY_GAP: dict[str, Action] = {
    "no_attempt": "hint",
    "wrong_model": "reteach",
    "missing_prerequisite": "prerequisite",
    "right_idea_wrong_altitude": "followup",
}


def decide(classification: str, gap_kind: str | None) -> Action:
    """What to do about this answer. Deterministic, and the whole policy.

    **A named `gap_kind` outranks the coarse classification.** The two are not
    competing verdicts: `classification` says how far the answer fell short and
    `gap_kind` says why, so the specific signal decides the response and the
    coarse one only fills in when no gap was named.

    That ordering is the whole fix for a defect found in live validation. A
    learner wrote "I can't follow this because I don't know what a function
    signature is" — genuinely stuck on a foundation. The Grader read it exactly
    right and reported `missing_prerequisite`, and the policy threw the signal
    away because the same answer had also been classified `off-topic`. An earlier
    version whitelisted which actions an off-topic answer could earn, which is
    the same mistake in smaller form: it treats the vaguer evidence as the
    stronger one.

    What the off-topic guard actually protects is the **unclassified** case. An
    answer that addresses nothing and names no gap is evidence of neither
    understanding nor misunderstanding, so it earns nothing and must not reshape
    a path — the 2026-08-14 decision, preserved exactly. Note that `off-topic`
    never changes `understanding_state` either way; that is the Grader's
    `_CLASSIFICATION_TO_STATE`, which this function does not touch.

    A gap the Grader did not classify falls back to `prerequisite` when the
    answer was `confused`, which is the pre-B5 behaviour: a session graded before
    `gap_kind` existed keeps working exactly as it did.
    """
    if classification == "understood":
        return "none"

    # The specific signal, when there is one.
    action = _ACTION_BY_GAP.get(gap_kind or "")
    if action is not None:
        return action

    # No gap named — now, and only now, the classification decides. `off-topic`
    # earns nothing: with no gap to point at, an unrelated answer says nothing.
    return "prerequisite" if classification == "confused" else "none"


# ── the plan: one answer, several gaps (M4) ───────────────────────────────────

# The operational bound on how many gaps are worked at once. NOT a bound on how
# many may be open, and NOT a bound on how many block `understood` — those are
# uncapped by §18.16.1, deliberately, so that a gap's meaning never depends on a
# queue limit. This number only decides how much is attempted in one cycle.
ACTIVE_SET_MAX = 3


@dataclass(frozen=True)
class Plan:
    """The whole response to one graded answer.

    **`action` is singular, where gap-model.md M4 sketched `actions`.** That is a
    deliberate narrowing, and §18.5 is the reason: it permits *one structural
    mutation* per graded answer, and the remaining actions are each a piece of
    writing the learner reads — a hint, a correction, a follow-up question.
    Issuing two of those at once is not twice the teaching, it is two lessons
    competing for the same attention, and the precedence order exists precisely
    because the foundational one has to land first. So one answer earns one
    response, and the plural lives where it belongs: in `targets`.

    Fields:
      action      what the system does now. `none` means "recorded, nothing owed".
      targets     the gaps this action must address. Plural for `reteach` and
                  `followup` — "one mutation, many corrections" (§18.5).
      active_set  the open BLOCKING gaps being worked this cycle, ≤ 3, in
                  precedence order. Membership changes nothing about a gap:
                  one outside the set is still `open` and still blocking.
      deferred    open blocking gaps outside the active set. Exists so the count
                  can be shown rather than the gaps silently disappearing.
      collapsed   more blocking gaps are open than the queue holds, so the
                  response is one full re-teach instead of a fan-out of warm-ups.
    """

    action: Action
    targets: tuple[Gap, ...] = ()
    active_set: tuple[Gap, ...] = ()
    deferred: tuple[Gap, ...] = field(default=())
    collapsed: bool = False


def decide_all(
    classification: str,
    gaps: list[Gap] | None,
    gap_kind: str | None = None,
    remediation_rounds: int = 0,
) -> Plan:
    """What to do about an answer that may contain several misconceptions.

    The generalisation of `decide`, and it agrees with it exactly wherever
    `decide` has an opinion — with zero or one gap the two return the same
    action, which is asserted directly against the table in
    `tests/test_gap_adaptation.py`. What is genuinely new is only what happens
    when there is more than one.

    Three rules from §18.5, in the order they apply:

    1. **Precedence decides the response.** The highest-ranked open gap picks the
       action; foundational first, because remediating a higher-altitude gap
       while a foundation is missing lands on nothing.
    2. **One mutation, many corrections.** A `prerequisite` targets exactly one
       gap — the structural change is capped at one per answer. A `reteach` or
       `followup` targets *every* active gap of that kind, because a lesson can
       name several misconceptions and must, or the ones it omits are silently
       abandoned. Gaps of DIFFERENT kinds are never merged: a hint and a
       correction are not the same act.
    3. **Overflow collapses.** More than `ACTIVE_SET_MAX` blocking gaps open is
       itself one signal — the unit did not land — so the answer is a single
       full re-teach over all of them rather than a queue of warm-ups
       (§18.16.1).

    Everything not addressed stays `open`. Nothing here decays, resolves or
    reclassifies a gap; this function reads and returns, and mutates nothing.

    **`gap_kind` is a fallback for when there are no gap OBJECTS at all**, which
    is the flag-off world: `CODEONBOARD_GAPS=0` records no gaps, but the base
    Grader prompt still returns the scalar and it still means something. Without
    it, moving a call site from `decide` to `decide_all` would silently downgrade
    every flag-off `reteach` and `followup` to `none`. It is consulted **only**
    when `gaps` is empty, so wherever gap objects exist they remain the single
    source of truth and the scalar cannot override them.
    """
    # Deduplicated by id. `_record_gaps` cannot produce a repeat — matching an
    # existing gap creates nothing — but two reports naming one id are a shape
    # the model does produce (measured in M3), and a target list that mentioned
    # the same misconception twice would ask a lesson to correct it twice.
    seen: set[str] = set()
    unique = [g for g in (gaps or []) if not (g.id in seen or seen.add(g.id))]
    open_gaps = by_precedence([g for g in unique if g.is_open])

    # A gap that has used its verification budget leaves the ACTIVE SET but keeps
    # every other property: still open, still blocking, still counted as
    # outstanding work (§18.16.1). The system stops proposing for it; it does not
    # stop mattering. Same for a node that has run its remediation rounds — the
    # cap ends the offering, never the obligation.
    exhausted = [g for g in open_gaps if g.is_exhausted]
    eligible = [g for g in open_gaps if not g.is_exhausted]
    if remediation_rounds >= REMEDIATION_ROUND_CAP:
        eligible = []

    blocking = [g for g in eligible if g.is_blocking]
    active = tuple(blocking[:ACTIVE_SET_MAX])
    # Everything blocking and outstanding that is not being worked on now,
    # whichever reason it is waiting for. A capped gap belongs here rather than
    # nowhere, so the count the learner is shown stays truthful.
    deferred = tuple(blocking[ACTIVE_SET_MAX:]) + tuple(
        g for g in exhausted if g.is_blocking
    )
    collapsed = len(blocking) > ACTIVE_SET_MAX

    # `understood` earns no response, exactly as in `decide`. An answer that
    # reaches the objective while leaving a blocking gap open is not re-taught —
    # it is VERIFIED (M6), which is a different act with a different producer
    # (§18.16.2). Re-teaching here would answer a question the learner just
    # showed they could answer.
    if classification == "understood":
        return Plan("none", (), active, deferred, collapsed)

    if not open_gaps:
        # No gap to point at: fall back to the scalar and then to the coarse
        # signal, which is the whole of `decide`'s remaining behaviour, including
        # `off-topic` earning nothing. Delegated rather than restated so the two
        # cannot drift. `targets` stays empty — a scalar names no gap to remediate.
        return Plan(decide(classification, gap_kind), (), active, deferred, collapsed)

    if not eligible:
        # Gaps are open, but every one has spent its verification budget — or the
        # node has spent its rounds. The system stops proposing, which is the
        # entire purpose of the caps: they end the offering, not the obligation.
        #
        # Explicitly NOT the scalar fallback above: falling through to `decide`
        # here would hand back a `reteach` or a `prerequisite` with no target and
        # start the cycle again, which is exactly what the cap exists to stop.
        return Plan("none", (), active, deferred, collapsed)

    if collapsed:
        # A full re-teach of the unit, naming every blocking gap. Not the active
        # set: the lesson is being given again in full, so scoping it to three of
        # five would leave two corrections unmade with nothing queued to make them.
        return Plan("reteach", tuple(blocking), active, deferred, True)

    lead = eligible[0]
    action = _ACTION_BY_GAP.get(lead.kind)
    if action is None:
        # An unknown kind, from a store written by a future or foreign version.
        # Same conservative direction as `is_blocking` and `precedence_rank`:
        # what we cannot interpret earns nothing rather than a guessed response.
        #
        # `None`, NOT `gap_kind`: a gap object exists here, so gaps are the
        # source of truth and the scalar must not be allowed to answer over the
        # top of one we could not read.
        return Plan(decide(classification, None), (), active, deferred, collapsed)

    if action == "prerequisite":
        # ONE structural mutation per graded answer (§18.5). The others stay open
        # and are picked up on a later cycle — after the foundation has landed,
        # which is the entire reason precedence puts this first.
        return Plan(action, (lead,), active, deferred, collapsed)

    # A lesson may carry several corrections at once, but only of the lead's own
    # kind. Merging a `followup` into a `reteach` would answer two different
    # difficulties with one act.
    return Plan(action, tuple(g for g in eligible if g.kind == lead.kind),
                active, deferred, collapsed)


# ── prune-ahead ────────────────────────────────────────────────────────────────

# How many consecutive understood units in one area before we believe it.
# Two is the smallest number that is not a coincidence; three would mean the
# signal arrives after the area is over on a typical three-unit area.
_SUSTAINED = 2


def prune_ahead(graph: LearningGraph) -> list[str]:
    """Demote the `recommended` remainder of an area the learner has proven.

    The only mechanism in the system that adapts UPWARD, and the only one that
    shortens a journey rather than lengthening it (§9.1). Sustained correct
    answers inside an area are evidence the learner did not need the rest of it
    at full length, and respecting their time is the point.

    Demotes, never deletes: the units stay on the same spine, collapsed in the
    rail, one click away. Nothing is lost and the decision is reversible by the
    learner simply opening them.

    Deliberately conservative about what it may touch:
      - `required` units are never demoted. They are the floor of the curriculum
        (§6.3) and prior performance is not evidence about a unit not yet seen.
      - units the learner has already visited or answered are left alone —
        demoting something already worked through would rewrite history.
      - a unit the learner OVERRODE is untouchable: user overrides always win
        (§9.2), and this is a system opinion, not a user one. That includes a
        unit moved by scope control (`scope_locked`), which is the same
        principle applied to a decision about the journey rather than about
        one node's state.

    Returns the ids demoted, for the caller to report.
    """
    understood_by_area: dict[str, int] = {}
    for node_id in graph.path_order():
        node = graph.nodes[node_id]
        area = (node.lesson_brief or {}).get("area_id")
        if not area:
            continue
        if understanding_of(node) == "understood":
            understood_by_area[area] = understood_by_area.get(area, 0) + 1
        elif node.visited:
            # A visited unit that was NOT understood breaks the streak: the
            # evidence has to be consecutive to mean anything.
            understood_by_area[area] = 0

    proven = {a for a, streak in understood_by_area.items() if streak >= _SUSTAINED}
    if not proven:
        return []

    demoted: list[str] = []
    for node_id in graph.path_order():
        node = graph.nodes[node_id]
        brief = node.lesson_brief or {}
        if brief.get("area_id") not in proven:
            continue
        if brief.get("priority") != "recommended":
            continue
        if node.visited or node.attempts or node.user_override:
            continue
        if brief.get("scope_locked"):
            # The learner moved this unit by hand. Prune-ahead demotes in the
            # same direction as "make it shorter", so without this it would
            # quietly re-take a unit the user had just asked to keep — the
            # silent undo §9.2 forbids.
            continue
        brief["priority"] = "optional"
        node.lesson_brief = brief
        demoted.append(node.id)
    return demoted
