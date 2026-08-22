# Start over — restore the plan, discard the walk.
#
# `Start over` used to re-run the entire repository-analysis pipeline: two to four
# minutes, a Sonnet planning call, and a DIFFERENT curriculum than the learner was
# looking at. A learner asking to start over is asking to walk the same path
# again, so this restores the plan instead of rebuilding it.
#
# ── WHY THIS MODULE IS SO SHORT ───────────────────────────────────────────────
#
# Because M1 did the work. The original plan is on disk, written once at creation
# and unmutatable afterwards, so restoring it is a REPLACEMENT rather than an
# inversion. There is no priority to derive from the event log, no original lesson
# to recover from `superseded_lesson`, no remedial edge surgery, no ordering
# constraint between clearing one field and reading another — every one of those
# was in the rejected design (session-reset.md §1), and every one of them is a
# place a missed case would leave learner state behind while looking clean.
#
# The load-bearing consequence, stated once: **anything not in the plan is gone by
# construction.** `load_plan` builds fresh `LearningNode`s whose state fields are
# at their dataclass defaults, so a state field added to `LearningNode` tomorrow is
# handled by this module today, without a line changing. That is the whole reason
# the architecture was chosen, and it is why there is no list of fields to clear
# here — a list is exactly what rots.
#
# ── WHAT IS NOT RESET, AND WHY IT IS NOT AN OVERSIGHT ─────────────────────────
#
# `repo_url`, `goal`, `doc_context`, `areas`, `briefing`, `created_at`. Every one
# is written by the pipeline or by the first welcome GET, and nothing in the
# learning loop writes them — so they are plan-side, and `load_plan` reads them
# from the same `sessions` row the live graph uses rather than from a duplicate
# that could disagree.
#
# The Dossier (`investigation`, keyed by session_id) is likewise kept. It is
# goal-specific repository understanding, not learner progress, and it is the
# reason `Start over` restores IN PLACE rather than forking a new session: a new
# session id would start with no Dossier, and every later lesson, re-teach and
# warm-up would silently fall back to the Skeleton.
#
# Deterministic by construction: no model call, no clone, no network, no new
# session id, and nothing read from the learner's own history.

from __future__ import annotations

from dataclasses import dataclass

from backend.learning import history
from backend.learning.graph import LearningGraph


@dataclass(frozen=True)
class ResetSummary:
    """What the reset discarded, for the endpoint's log line and its response.

    Counts, not content. Nothing is persisted (session-reset.md D4): no product
    surface consumes previous attempts, and a half-complete archive nobody reads
    is worse than none. The numbers exist so the act leaves a trace in the log,
    and so the UI can say what happened rather than only that it happened.

    Frozen because it is a report, and a report that its own caller can edit is
    not evidence of anything.
    """

    stops: int
    attempts: int
    gaps: int
    remedial_nodes: int
    lessons_restored: int

    def to_dict(self) -> dict:
        return {
            "stops": self.stops,
            "attempts": self.attempts,
            "gaps": self.gaps,
            "remedial_nodes": self.remedial_nodes,
            "lessons_restored": self.lessons_restored,
        }


def learner_state(graph: LearningGraph) -> dict:
    """Everything about this session that the learner produced, as counts.

    The enumeration the archive decision (D4) said to keep even though nothing is
    persisted: the boundary has to be describable to be testable, and this is the
    description. It is also the only thing that has to be updated if the shape of
    learner state changes — the reset itself does not, because it replaces rather
    than clears.

    Pure. Reads nothing but the graph.
    """
    attempts = sum(len(n.attempts) for n in graph.nodes.values())
    gaps = sum(len(n.gaps) for n in graph.nodes.values())
    return {
        "stops": sum(
            1 for n in graph.nodes.values()
            if n.visited or n.attempts or n.user_override
        ),
        "attempts": attempts,
        "gaps": gaps,
        "journey_events": len(graph.journey_events),
        "remediation_rounds": sum(
            n.gap_state.remediation_rounds for n in graph.nodes.values()
        ),
        "pending_verifications": sum(
            1 for n in graph.nodes.values() if n.gap_state.pending_verification
        ),
    }


def reset_to_plan(live: LearningGraph, plan: LearningGraph) -> ResetSummary:
    """Restore `live` to `plan`, in place. The whole of `Start over`.

    Mutates `live` rather than returning the plan graph, for one reason: the
    caller holds the object the rest of the request works with, and handing back
    a different object would leave two graphs for the same session in one process
    — with the losing one still writable.

    `plan` is treated as READ-ONLY, and its node and edge objects are moved rather
    than copied. That is safe because `load_plan` reads fresh objects out of
    SQLite on every call: this function never holds a reference the plan tables
    can see, so nothing here can write back to them. It is also why the caller
    must pass a freshly loaded plan and not a cached one.

    Position: `path_head()` of the RESTORED edges, so the learner lands on stop 1
    of the plan rather than wherever the previous walk had wandered to — and it is
    computed after the swap, because before the swap it would answer about the
    mutated graph.
    """
    before = learner_state(live)
    remedial = len(live.nodes) - len(plan.nodes)

    # Wholesale replacement. Not a per-field clear: remedial nodes have to
    # disappear, the edges they rerouted have to come back, and every state field
    # has to return to its default — and one assignment does all three, whereas a
    # clearing pass does the first two only if someone remembered to write them.
    live.nodes = plan.nodes
    live.edges = plan.edges

    # The learner's position and the record of how they moved through the journey.
    # Cleared here rather than in `load_plan`, because these are facts about the
    # SESSION and the plan legitimately has no opinion about them.
    live.journey_events = []
    live.arrival = None
    live.current_node_id = live.path_head()

    # The single boundary marker, on the now-empty list. Written after the clear,
    # obviously — but worth stating, because writing it before would be a record
    # the very next line deletes.
    live.record_journey_event(history.RESET)

    return ResetSummary(
        stops=before["stops"],
        attempts=before["attempts"],
        gaps=before["gaps"],
        # Negative is impossible — the plan is a subset of the live graph by
        # construction, since only `insert_before` adds nodes and nothing removes
        # them — but `max` costs nothing and a negative count in a log line would
        # send someone hunting for a bug that is really an arithmetic slip.
        remedial_nodes=max(remedial, 0),
        lessons_restored=sum(
            1 for n in plan.nodes.values() if n.cached_lesson is not None
        ),
    )
