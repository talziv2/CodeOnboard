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

from typing import Literal

from backend.learning.graph import LearningGraph


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


# What an `off-topic` answer may earn. It is evidence of neither understanding
# nor misunderstanding, so it must never reshape a path — but "I don't know"
# grades as off-topic with a `no_attempt` gap, and offering a way in is the whole
# point of that gap. Withholding one because the answer was also off-topic would
# be applying a guard meant for the graph to a response that never touches it.
_OFFERABLE_TO_OFF_TOPIC: tuple[Action, ...] = ("hint", "followup")


def decide(classification: str, gap_kind: str | None) -> Action:
    """What to do about this answer. Deterministic, and the whole policy.

    An answer that reached the objective needs no response.

    `off-topic` may be offered help but never restructured around — the
    2026-08-14 decision, preserved: an unrelated answer says nothing about
    understanding, so it cannot earn a prerequisite. It can earn a hint, because
    a hint changes nothing except what is on screen.

    A gap the Grader did not classify falls back to `prerequisite` when the
    answer was `confused`, which is the pre-B5 behaviour: a session graded before
    `gap_kind` existed keeps working exactly as it did.
    """
    if classification == "understood":
        return "none"

    action = _ACTION_BY_GAP.get(gap_kind or "")
    if classification == "off-topic":
        return action if action in _OFFERABLE_TO_OFF_TOPIC else "none"
    if action is not None:
        return action
    return "prerequisite" if classification == "confused" else "none"


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
        (§9.2), and this is a system opinion, not a user one.

    Returns the ids demoted, for the caller to report.
    """
    understood_by_area: dict[str, int] = {}
    for node_id in graph.path_order():
        node = graph.nodes[node_id]
        area = (node.lesson_brief or {}).get("area_id")
        if not area:
            continue
        if node.understanding_state == "understood":
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
        brief["priority"] = "optional"
        node.lesson_brief = brief
        demoted.append(node.id)
    return demoted
