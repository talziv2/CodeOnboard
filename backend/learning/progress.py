# Progress — what the learner has demonstrated, and how far along they are.
#
# Two measures, deliberately not one (learning-graph.md §5.4, decision OQ-1):
#
#   GOAL READINESS    mastery over the units the goal actually requires.
#                     Evidence-weighted. Answers "how ready am I for the goal".
#   JOURNEY PROGRESS  how much of the planned walk has been dealt with.
#                     Coverage, not mastery. Answers "how far along am I".
#
# One number cannot be both. A single mastery gauge reads 0% for a learner who
# walked the whole journey without answering anything — `/advance` marks a node
# visited without grading it — and a single coverage gauge would claim
# understanding nobody demonstrated.
#
# THE INVARIANT THIS MODULE EXISTS TO HOLD (§5.3, decision OQ-3):
#
#   Goal readiness may fall ONLY when evidence about the learner changes.
#   It must NEVER fall because the system changed the plan.
#
# That is why remedial nodes are excluded from both sides of the fraction. The
# previous `readiness()` put the Mutator's warm-up — marked `priority: required`
# so scope control cannot take it away — straight into its denominator, so the
# gauge dropped from 0.50 to 0.33 at the exact moment the system decided to help.
# `tests/test_progress.py` pins every mutation against this rule.
#
# Pure: no IO, no model calls, no mutation of the graph. Same contract as
# `scope.py` and `adaptation.py`, and for the same reason — the whole progress
# model is then testable without an API key.

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.learning import history
from backend.learning.graph import understanding_of

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle
    from backend.learning.graph import LearningGraph, LearningNode


# Where a unit came from. A key in `lesson_brief`, which is already a free-form
# JSON payload — no column, no migration (learning-engine.md LD6).
ORIGIN_KEY = "origin"

PLANNED = "planned"
SYSTEM_REMEDIATION = "system_remediation"
LEARNER_REQUEST = "learner_request"

# Both kinds of warm-up are detours off the promised journey. They are kept
# distinct because §18.11 protects a learner-requested one from demotion for a
# different reason than a system-selected one, not because progress treats them
# differently — progress excludes both.
REMEDIAL_ORIGINS = frozenset({SYSTEM_REMEDIATION, LEARNER_REQUEST})

# A unit with no `priority` at all is NOT optional and is not enrichment — it is
# an ordinary required stop. Every pre-B3 graph is in that shape (the pre-B3
# planner writes no priority), so this default is what makes the two measures
# defined on all 62 stored sessions rather than only on B3 ones.
DEFAULT_PRIORITY = "required"

REQUIRED = "required"
OPTIONAL = "optional"

# `partial` scores half. Honest for a genuinely partial answer, and wrong for a
# grading failure, which also defaults to `partial` — the Grader cannot yet tell
# us which it was. Recorded as a known limitation (§10 R3) rather than papered
# over here; the fix is an `attempt["graded"]` marker in M2.
_WEIGHT = {"understood": 1.0, "partial": 0.5}

_STATES = ("understood", "partial", "failed", "not_started")


# ── provenance ────────────────────────────────────────────────────────────────


def remedial_ids(graph: "LearningGraph") -> set[str]:
    """Ids of every warm-up spliced in off the promised journey.

    Explicit `lesson_brief["origin"]` wins. Graphs written before that key
    existed — all 62 stored sessions — fall back to the STRUCTURAL rule the
    codebase already relies on in two places (`mutator._has_prerequisite` and
    the frontend's `unlockTargetOf`): `insert_before` reroutes the incoming
    sequence edge onto the spliced node, so a remedial node has NO OUTGOING
    SEQUENCE EDGE while still pointing at the unit it unblocks by a
    `prerequisite` edge. A planned unit sits on the chain and keeps its sequence
    edge, however many `depends_on` edges it carries.

    Requiring BOTH halves matters. The last unit of a planned chain also has no
    outgoing sequence edge; it has no outgoing prerequisite edge either, because
    the planner orders dependencies before dependents, so nothing later can
    depend on it. Testing only the missing sequence edge would classify the final
    stop of every journey as a warm-up.
    """
    remedial: set[str] = set()
    unmarked: list[str] = []
    for node in graph.nodes.values():
        declared = (node.lesson_brief or {}).get(ORIGIN_KEY)
        if declared in REMEDIAL_ORIGINS:
            remedial.add(node.id)
        elif declared != PLANNED:
            unmarked.append(node.id)

    if not unmarked:
        return remedial

    sequence_out = {e.from_node_id for e in graph.edges if e.kind == "sequence"}
    prerequisite_out = {e.from_node_id for e in graph.edges if e.kind == "prerequisite"}
    for node_id in unmarked:
        if node_id not in sequence_out and node_id in prerequisite_out:
            remedial.add(node_id)
    return remedial


def origin_of(node: "LearningNode", remedial: set[str]) -> str:
    """This unit's provenance, preserving the declared value where there is one.

    Takes the pre-computed remedial set rather than a graph, so a caller
    classifying every node pays for the structural pass once. The fallback
    reports `system_remediation` because that is what every warm-up in the 62
    stored sessions is — `/retry` began marking learner-requested ones only with
    this milestone, and inventing `learner_request` for an unmarked node would
    claim an intent nothing recorded.
    """
    declared = (node.lesson_brief or {}).get(ORIGIN_KEY)
    if declared in REMEDIAL_ORIGINS or declared == PLANNED:
        return declared
    return SYSTEM_REMEDIATION if node.id in remedial else PLANNED


def unlocks(graph: "LearningGraph", node_id: str) -> str | None:
    """The unit this warm-up was spliced in to unblock, if any."""
    for edge in graph.edges:
        if edge.kind == "prerequisite" and edge.from_node_id == node_id:
            return edge.to_node_id
    return None


def priority_of(node: "LearningNode") -> str:
    return (node.lesson_brief or {}).get("priority") or DEFAULT_PRIORITY


# ── the two populations ───────────────────────────────────────────────────────


def core_nodes(graph: "LearningGraph") -> list["LearningNode"]:
    """What the goal requires: planned units the planner marked `required`.

    `select()` defines that set as the model's required objectives PLUS their
    dependency closure PLUS one promoted unit per declared area
    (`curriculum.py`), which is by construction "the goal is not met without
    this". A fraction over it is a claim about the goal rather than about a node
    count — which is the whole reason this is not `completed / total`.
    """
    remedial = remedial_ids(graph)
    return [
        n for n in graph.nodes.values()
        if n.id not in remedial and priority_of(n) == REQUIRED
    ]


def walk_nodes(graph: "LearningGraph") -> list["LearningNode"]:
    """The promised journey: planned, non-optional units — what "stop N of M" counts.

    Matches `scope.journey_size` and the rail's stop counter, minus remedial
    detours, which are not stops on the promised journey.
    """
    remedial = remedial_ids(graph)
    return [
        n for n in graph.nodes.values()
        if n.id not in remedial and priority_of(n) != OPTIONAL
    ]


# ── state predicates ──────────────────────────────────────────────────────────


def is_settled(node: "LearningNode") -> bool:
    """Has the learner dealt with this stop at all?

    Coverage, not mastery: visited, answered, or explicitly acted on. This is
    deliberately weaker than gap-model §18.16.3's `settled` (which requires
    `understood` or an explicit override and is the input to `is_complete()`).
    The two answer different questions and gap-model M8 owns the stricter one.
    """
    return bool(node.visited or node.attempts or node.user_override)


def is_assessed(node: "LearningNode") -> bool:
    """Is there real evidence here?

    Delegates to `history.is_evidence`, which excludes two things: an `off-topic`
    answer (evidence of neither understanding nor misunderstanding — a quarter of
    every attempt stored to date) and a FAILED GRADE (our error, not the
    learner's answer).

    The grading-failure exclusion arrived with M2, which is the first milestone
    able to tell the two apart. It moves `assessed_coverage` only; the two
    progress measures read `understanding_state` and are untouched.
    """
    return any(history.is_evidence(a) for a in node.attempts)


# ── the measures ──────────────────────────────────────────────────────────────


def goal_readiness(graph: "LearningGraph") -> float:
    """Evidence-weighted mastery of the required set. 0.0 when nothing is required.

    Cannot exceed 1.0 by construction — the numerator ranges over exactly the
    nodes in the denominator, so the old `min(..., 1.0)` clamp (which existed to
    contain optional-unit credit) is gone rather than merely unused.
    """
    core = core_nodes(graph)
    if not core:
        return 0.0
    earned = sum(_WEIGHT.get(understanding_of(n), 0.0) for n in core)
    return earned / len(core)


def journey_progress(graph: "LearningGraph") -> float:
    """Fraction of the promised journey the learner has dealt with."""
    walk = walk_nodes(graph)
    if not walk:
        return 0.0
    return sum(1 for n in walk if is_settled(n)) / len(walk)


def assessed_coverage(graph: "LearningGraph") -> float:
    """Fraction of the promised journey that carries real evidence.

    The honesty check on goal readiness: a high journey number beside a low
    assessed number means the learner walked past the questions.
    """
    walk = walk_nodes(graph)
    if not walk:
        return 0.0
    return sum(1 for n in walk if is_assessed(n)) / len(walk)


def state_mix(graph: "LearningGraph") -> dict[str, int]:
    """Understanding states across the promised journey."""
    mix = {state: 0 for state in _STATES}
    for node in walk_nodes(graph):
        state = understanding_of(node)
        if state in mix:
            mix[state] += 1
    return mix


def detours(graph: "LearningGraph") -> list[dict]:
    """Every warm-up, with the unit it was spliced in to unblock.

    This is where remedial work is represented, having been excluded from both
    measures (OQ-2). Reporting them as their own list says more than a silent
    bump in a percentage would.
    """
    remedial = remedial_ids(graph)
    out = []
    for node_id in graph.path_order():
        if node_id not in remedial:
            continue
        node = graph.nodes[node_id]
        out.append({
            "node_id": node.id,
            "title": node.title,
            "origin": origin_of(node, remedial),
            "unlocks": unlocks(graph, node.id),
            "understanding_state": understanding_of(node),
        })
    return out


def skipped(graph: "LearningGraph") -> int:
    """Stops the learner explicitly stepped past.

    Shown beside goal readiness because a skip scores zero and never expires:
    without the count, the number looks arbitrary.
    """
    return sum(1 for n in walk_nodes(graph) if n.user_override == "skip")


def summary(graph: "LearningGraph") -> dict:
    """Everything the UI needs, computed once, server-side.

    Server-side because there must be exactly one implementation of these
    definitions — the frontend recomputing its own aggregates from raw nodes is
    how the header and the map came to disagree — and because a later report or
    export is then a rendering job over an existing payload (OQ-9).
    """
    core = core_nodes(graph)
    walk = walk_nodes(graph)
    remedial = remedial_ids(graph)
    optional = [
        n for n in graph.nodes.values()
        if n.id not in remedial and priority_of(n) == OPTIONAL
    ]
    return {
        "goal_readiness": goal_readiness(graph),
        "core_total": len(core),
        "core_understood": sum(1 for n in core if understanding_of(n) == "understood"),
        "core_partial": sum(1 for n in core if understanding_of(n) == "partial"),
        "journey_progress": journey_progress(graph),
        "stops_settled": sum(1 for n in walk if is_settled(n)),
        "stops_total": len(walk),
        "assessed_coverage": assessed_coverage(graph),
        "assessed": sum(1 for n in walk if is_assessed(n)),
        "state_mix": state_mix(graph),
        "detours": detours(graph),
        "skipped": skipped(graph),
        "optional_total": len(optional),
        "optional_completed": sum(
            1 for n in optional if understanding_of(n) == "understood"
        ),
    }
