# The understanding profile — what the evidence says the learner understands.
#
# M1 answered "where am I". M2 recorded "how did I get here". This answers
# **"what do I actually understand, and what still needs work"** — the first
# surface that reads the evidence rather than the plan.
#
# TWO DIMENSIONS, NOT ONE (learning-graph.md M3a, decided 2026-08-18)
#
# Understanding and remediation disposition are independent facts, and gap-model
# M8 makes that observable rather than theoretical: a learner can waive a gap,
# later pass verification on it, and end with a node that is genuinely
# `understood` while `user_override` still records `waive_remaining`. One
# variable would have to report either "demonstrated" or "waived" and would be
# wrong either way.
#
#   UNDERSTANDING   what the evidence demonstrates. Four states. Never changed
#                   by a decision the learner made about remediation.
#   DISPOSITION     what the learner decided to DO about remediation here.
#                   Never changes what was demonstrated.
#
# The product rule this pair exists to satisfy: *preserve the truth about
# unresolved understanding without presenting it as an active task the learner
# is still expected to fix.*
#
# EVIDENCE RULES, ALL INHERITED RATHER THAN RE-DECIDED
#
#   - `understanding_of` is the SINGLE owner of the state question (gap-model
#     M7). Nothing here re-derives it, and the AST test in
#     `test_gap_understanding.py` enforces that structurally.
#   - `history.is_evidence` decides what counts: off-topic answers and failed
#     grades are excluded, for reasons that belong to M2 and are stated there.
#   - Missing instrumentation stays `unknown`. A pre-M2 attempt never implies
#     "no help was given".
#
# Pure: no IO, no model calls, no mutation. Same contract as `progress.py`.

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.learning import history, progress
from backend.learning.graph import understanding_of

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle
    from backend.learning.graph import LearningGraph, LearningNode


# ── the four understanding states ─────────────────────────────────────────────

# Demonstrated, and never fell short here.
STRENGTH = "strength"
# Fell short at least once, and then demonstrated it. **This is not a weakness**,
# and the whole reason the milestone exists: `weak_spot` is sticky, so before
# this the UI captioned recovered units "⚑ marked weak" forever.
RECOVERED = "recovered"
# Assessed, and not demonstrated. The only state that can be "needs work".
UNRESOLVED = "unresolved"
# No usable evidence: never answered, answered only off-topic, or only ever
# graded by the fallback. Deliberately NOT a weakness — nobody has been shown to
# lack anything — and deliberately not a strength.
INSUFFICIENT = "insufficient"


# ── disposition: what the learner decided about remediation ───────────────────

# Nothing decided; the system would still offer to help here.
ACTIVE = "active"
# "I'll move on" — withdrawn automatically by a new attempt (M8).
CONTINUED = "continued"
# "Stop asking me about this." Survives later answers.
WAIVED = "waived"
# Never engaged, deliberately.
SKIPPED = "skipped"
# The learner asserted understanding on a gap-free node — an assertion, not a
# demonstration, and shown as such (§10 R9).
ASSERTED = "asserted"

# Dispositions that mean "the learner has closed this question". A node carrying
# one is never presented as work outstanding, whatever its understanding state.
SETTLING_DISPOSITIONS = frozenset({CONTINUED, WAIVED, SKIPPED})

_DISPOSITION_BY_OVERRIDE = {
    "continue": CONTINUED,
    "waive_remaining": WAIVED,
    "skip": SKIPPED,
    "mark_understood": ASSERTED,
    # `mark_weak` is the learner AGREEING they have not got it — an active
    # difficulty, not a decision to stop. It leaves the disposition `active`.
    "mark_weak": ACTIVE,
}


def disposition_of(node: "LearningNode") -> str:
    """What the learner decided to do about remediation here.

    Read from `user_override`, which is the explicit-intent channel M8 extended
    and which M1 already put on the wire. Never inferred from state: an
    unanswered node and a deliberately skipped one look identical in
    `understanding_state` and are completely different decisions.
    """
    return _DISPOSITION_BY_OVERRIDE.get(node.user_override or "", ACTIVE)


# ── evidence ──────────────────────────────────────────────────────────────────


def _assessment_evidence(node: "LearningNode") -> list[dict]:
    """Answers to the objective that say something about understanding.

    Assessments only — a verification answer is evidence about one gap, not a
    second attempt at the objective (M2). Off-topic and failed grades excluded.
    """
    return [
        a for a in history.assessments(node.attempts) if history.is_evidence(a)
    ]


def classify(node: "LearningNode") -> str:
    """One of the four understanding states. Reads evidence, never disposition."""
    evidence = _assessment_evidence(node)
    if not evidence:
        return INSUFFICIENT

    state = understanding_of(node)
    if state != "understood":
        return UNRESOLVED

    # Demonstrated. Was it hard-won? `partial` counts as falling short exactly as
    # `confused` does — both mean the objective was not reached on that answer,
    # and a learner who went partial → understood worked through something real.
    #
    # Derived from the ATTEMPT HISTORY rather than from `weak_spot`, which is set
    # only on `confused` and would therefore miss every partial recovery. The
    # sticky flag remains useful corroboration; it is not the discriminator.
    fell_short = any(
        a.get("classification") in ("confused", "partial") for a in evidence[:-1]
    )
    return RECOVERED if fell_short else STRENGTH


def is_needs_work(node: "LearningNode") -> bool:
    """Is this an OPEN task the learner is still expected to act on?

    Unresolved understanding AND no settling decision. The conjunction is the
    product requirement: a learner who chose to continue or waive still has
    unresolved understanding — that truth is preserved in `classify` — but they
    are not nagged about a decision they already made.
    """
    return classify(node) == UNRESOLVED and disposition_of(node) not in SETTLING_DISPOSITIONS


def is_set_aside(node: "LearningNode") -> bool:
    """Unresolved, and the learner deliberately closed the question.

    A third band rather than a filter on either side: dropping these from view
    would hide real unresolved understanding, and leaving them in `needs work`
    would nag about a decision already taken.
    """
    return classify(node) == UNRESOLVED and disposition_of(node) in SETTLING_DISPOSITIONS


# ── per-node summary ──────────────────────────────────────────────────────────


def node_summary(node: "LearningNode") -> dict:
    """Everything a profile row or an evidence drawer header needs.

    `state_matches_latest_answer` is the one honesty flag: gap-model M7 can hold
    a node at `partial` although its latest answer reached the objective, and
    without gap content on the wire (M9) the UI cannot say *why*. Reporting the
    discrepancy is truthful; inventing a reason for it would not be.
    """
    evidence = _assessment_evidence(node)
    latest = evidence[-1] if evidence else None
    instrumented = history.instrumented(history.assessments(node.attempts))
    return {
        "node_id": node.id,
        "title": node.title,
        "objective": node.objective(),
        "understanding": classify(node),
        "disposition": disposition_of(node),
        "state": understanding_of(node),
        "attempts": len(history.assessments(node.attempts)),
        "evidence_count": len(evidence),
        # None when nothing is instrumented — "unknown", never "no help".
        "interventions": (
            [history.intervention_of(a) for a in instrumented] if instrumented else None
        ),
        "first_answer": evidence[0].get("classification") if evidence else None,
        "state_matches_latest_answer": (
            latest is None
            or latest.get("classification") != "understood"
            or understanding_of(node) == "understood"
        ),
        "area_id": (node.lesson_brief or {}).get("area_id", ""),
        "kind": (node.lesson_brief or {}).get("kind", ""),
        # WHY the state is what it is, when the answer alone does not explain it
        # (gap-model M9). `state_matches_latest_answer` above reports the
        # discrepancy honestly; these report its cause, which is what this
        # docstring said was missing until M9 put gap content on the wire.
        "gaps_open": sum(1 for g in node.gaps if g.is_open),
        "gaps_blocking": sum(
            1 for g in node.gaps if g.is_blocking and g.status != "verified"
        ),
        "gaps_verified": sum(1 for g in node.gaps if g.status == "verified"),
        "gaps_waived": sum(1 for g in node.gaps if g.status == "waived"),
        # Awaiting an answer to a fresh question. The precise reason a node can
        # sit at `unresolved` with an `understood` latest answer.
        "verification_pending": bool(node.gap_state.pending_verification),
    }


# ── the profile ───────────────────────────────────────────────────────────────


def _tally() -> dict[str, int]:
    return {STRENGTH: 0, RECOVERED: 0, UNRESOLVED: 0, INSUFFICIENT: 0}


def profile(graph: "LearningGraph") -> dict:
    """The Understanding Profile, over the promised journey.

    Scoped to `progress.walk_nodes` — planned, non-optional units — so it counts
    exactly what the two progress measures count. A third opinion about which
    nodes matter is precisely what reusing that function avoids.

    Grouped by AREA rather than by file: areas are the curriculum's own grouping
    and already structure the rail, while a file is where code happens to live.
    """
    walk = progress.walk_nodes(graph)
    by_area: dict[str, dict[str, int]] = {}
    by_kind: dict[str, dict[str, int]] = {}
    rows: list[dict] = []

    for node in walk:
        summary = node_summary(node)
        rows.append(summary)
        state = summary["understanding"]
        area = summary["area_id"] or ""
        by_area.setdefault(area, _tally())[state] += 1
        kind = summary["kind"] or (node.concept_tags[0] if node.concept_tags else "")
        if kind:
            by_kind.setdefault(kind, _tally())[state] += 1

    order = {n.id: i for i, n in enumerate(walk)}
    rows.sort(key=lambda r: order[r["node_id"]])

    # Deferred import: `patterns` reads the classification this module owns, so
    # the dependency runs one way only.
    from backend.learning import gap_insight as gap_model
    from backend.learning import patterns as pattern_model

    return {
        # L2 observations over the same evidence. Usually empty — the thresholds
        # are set so a handful of answers produces nothing (M3a.2).
        "patterns": pattern_model.detect(graph),
        # Gap-derived observations (M3b). A SEPARATE list, not merged: these read
        # the misconceptions themselves rather than the answers, so a consumer
        # that has no gap data can ignore them wholesale — and the two evidence
        # bases stay distinguishable in reporting.
        "gap_patterns": gap_model.detect(graph),
        "totals": {
            state: sum(1 for r in rows if r["understanding"] == state)
            for state in (STRENGTH, RECOVERED, UNRESOLVED, INSUFFICIENT)
        },
        # `assessed` is the honest denominator for everything above: a profile
        # over 16 units where 3 carry evidence is a profile of 3.
        "assessed": sum(1 for r in rows if r["evidence_count"] > 0),
        "total": len(rows),
        "by_area": by_area,
        "by_kind": by_kind,
        "needs_work": [r["node_id"] for r in rows if is_needs_work(_node(graph, r))],
        "set_aside": [r["node_id"] for r in rows if is_set_aside(_node(graph, r))],
        "recovered": [r["node_id"] for r in rows if r["understanding"] == RECOVERED],
        "nodes": rows,
    }


def _node(graph: "LearningGraph", row: dict) -> "LearningNode":
    return graph.nodes[row["node_id"]]


# ── evidence drawer ───────────────────────────────────────────────────────────


def evidence(graph: "LearningGraph", node_id: str) -> dict:
    """The full chain behind one node's state, for the drawer.

    Every claim the profile makes about a node must be traceable to something
    persisted. This is that trace: the objective it was marked against, the
    derived state, each assessment with its verdict, and what the system did in
    response — with `intervention` left `null` where M2 has no record, so a
    pre-M2 session reads as unmeasured rather than as unassisted.
    """
    node = graph.nodes[node_id]
    timeline = []
    for index, attempt in enumerate(node.attempts):
        timeline.append({
            "index": index,
            "kind": attempt.get("kind", history.DEFAULT_KIND),
            "answer": attempt.get("answer", ""),
            "classification": attempt.get("classification", ""),
            "rationale": attempt.get("rationale", ""),
            "graded": history.is_graded(attempt),
            "counts_as_evidence": history.is_evidence(attempt),
            # None means UNKNOWN — no record — and never "nothing happened".
            "intervention": history.intervention_of(attempt),
            "intervention_text": (
                (attempt.get(history.RESPONSE) or {}).get("text")
                if history.is_instrumented(attempt) else None
            ),
            "superseded_lesson": (
                (attempt.get(history.RESPONSE) or {}).get("superseded_lesson")
                if history.is_instrumented(attempt) else None
            ),
            "at": attempt.get("at", ""),
        })

    return {
        **node_summary(node),
        # Every gap on the node, settled ones included — the drawer explains a
        # state, and "this was waived" and "this was verified" are as much a part
        # of that explanation as what is still open (gap-model M9).
        "gaps": [
            {
                "id": g.id,
                "kind": g.kind,
                "claim": g.claim,
                "objective_part": g.objective_part,
                "status": g.status,
                "blocking": g.is_blocking,
                "verification_attempts": g.verification_attempts,
                "exhausted": g.is_exhausted,
                "opened_at": g.opened_at,
                "closed_at": g.closed_at,
                # Which attempt opened it, and which closed it — the history of
                # the gap, expressed as indices into the timeline below rather
                # than as a second parallel record.
                "origin_attempt": g.origin_attempt,
                "resolved_by": g.resolved_by,
            }
            for g in node.gaps
        ],
        "timeline": timeline,
        # Plan-scoped events that touched this node — the remediation it caused
        # or received. Kept beside the attempts because "the journey grew here"
        # is part of the same story.
        "journey_events": [
            e for e in graph.journey_events
            if node_id in (e.get("nodes") or [])
            or (e.get("cause") or {}).get("node_id") == node_id
            or e.get("unlocks") == node_id
        ],
    }
