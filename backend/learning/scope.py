# Scope control — the learner adjusting the journey after seeing it.
#
# §5.3's claim is that scope is *derived* from evidence and then *adjusted against
# a visible plan*, because predicting your own appetite before seeing the
# repository is harder than reacting to fifteen named stops. B3 shipped the
# derivation; this is the adjustment.
#
# IT IS NOT A SECOND PLANNER. Nothing here proposes, grounds, orders or invents a
# unit. It moves existing units between `priority` buckets that the planner
# already assigned and that four other things already read — the rail's collapse,
# the stop counter, `readiness()`, and prune-ahead. Scope control is the same
# vocabulary, driven by the user instead of by the guard band.
#
# The two directions are deliberately asymmetric in what they may touch:
#
#   SHORTER  demotes `recommended` -> `optional`. Never `required`: that set is
#            the curriculum's floor and its dependency closure (§6.3), so
#            removing any of it would leave a journey that cannot deliver the
#            goal it was planned for.
#   DEEPER   promotes `optional` -> `recommended`. It EXPOSES material the
#            planner already produced rather than generating more; a journey with
#            nothing optional left has nothing deeper to offer, and says so.

from backend.learning.graph import LearningGraph


# Set on any unit the learner moved by hand. Adaptation must not silently undo a
# decision the user made about their own journey — prune-ahead in particular
# demotes in the same direction as `shorter` and would otherwise quietly re-take
# a unit the user had just promoted (§9.2: user overrides always win).
#
# A key in `lesson_brief`, which is already a free-form JSON payload — no column,
# no migration (LD6).
SCOPE_LOCK = "scope_locked"


def _brief(graph: LearningGraph, node_id: str) -> dict:
    return graph.nodes[node_id].lesson_brief or {}


def _set_priority(graph: LearningGraph, node_id: str, priority: str) -> None:
    node = graph.nodes[node_id]
    brief = dict(node.lesson_brief or {})
    brief["priority"] = priority
    brief[SCOPE_LOCK] = True
    node.lesson_brief = brief


def _adjustable(graph: LearningGraph, node_id: str) -> bool:
    """Units the learner has not already worked through.

    Re-labelling something already visited or answered would rewrite what
    happened to them, and the point of scope control is the road ahead.
    """
    node = graph.nodes[node_id]
    return not node.visited and not node.attempts


def shorten(graph: LearningGraph) -> list[str]:
    """Demote the remaining `recommended` units to `optional`.

    `recommended` means "included if there is room" (§6.3). A learner asking for
    a shorter journey is saying there is not room — so the whole bucket moves,
    which makes the action predictable and its inverse exact. Anything more
    selective would need a target number, and a target number is the planning
    knob this phase exists to remove (L1).

    `required` is untouched, so the dependency closure cannot break: `select()`
    already promoted every dependency of a required unit into the required set,
    which means nothing still required can depend on what this demotes.
    """
    moved = [
        node_id
        for node_id in graph.path_order()
        if _brief(graph, node_id).get("priority") == "recommended"
        and _adjustable(graph, node_id)
    ]
    for node_id in moved:
        _set_priority(graph, node_id, "optional")
    return moved


def deepen(graph: LearningGraph) -> list[str]:
    """Promote `optional` units back onto the walked journey.

    Deliberately only exposes what the planner already produced — the overflow
    the guard band demoted, the units it labelled optional itself, and anything
    prune-ahead set aside. Generating new material would be a second planning
    system, and would also invent objectives the guard band never sized.

    Returns the ids promoted; an empty list means the journey has no further
    material, which the caller should say plainly rather than paper over.
    """
    moved = deepenable(graph)
    for node_id in moved:
        _set_priority(graph, node_id, "recommended")
    return moved


def deepenable(graph: LearningGraph) -> list[str]:
    """Which units `deepen` WOULD promote, without promoting them.

    Extracted from `deepen` rather than written beside it, so there is exactly one
    definition of "material this journey still has in reserve". A second copy is
    how an offer comes to disagree with the endpoint it offers — the Tutor asks
    this before proposing `deepen`, and an offer the endpoint would answer with
    an empty list is an offer that reads as broken when pressed.
    """
    return [
        node_id
        for node_id in graph.path_order()
        if _brief(graph, node_id).get("priority") == "optional"
        and _adjustable(graph, node_id)
    ]


def can_deepen(graph: LearningGraph) -> bool:
    """Has this journey anything deeper left to offer?"""
    return bool(deepenable(graph))


def is_locked(graph: LearningGraph, node_id: str) -> bool:
    return bool(_brief(graph, node_id).get(SCOPE_LOCK))


def journey_size(graph: LearningGraph) -> int:
    """Units the learner will actually walk — what "stop N of M" counts."""
    return sum(
        1
        for node_id in graph.nodes
        if (graph.nodes[node_id].lesson_brief or {}).get("priority") != "optional"
    )
