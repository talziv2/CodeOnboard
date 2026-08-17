# Gap-derived observations — M3b.
#
# M3a.2's templates read ANSWERS (classification, the scalar `gap_kind`). These
# read the GAP OBJECTS the Gap Model persists: named misconceptions with an
# identity that survives re-grades (M3), a lifecycle (M6), and a resolution
# (`verified` / `waived`). That is a different evidence base answering a
# different question — not "how did answers go" but "what did the learner
# actually believe that was false, and what happened to it".
#
# THE SAME LINE APPLIES AS IN `patterns.py`
#
# These describe what happened to misconceptions. They never describe the
# learner. There is deliberately NO shared-cause inference: two gaps of the same
# kind are two gaps of the same kind, and claiming they share a root needs
# cross-node concept identity, which does not exist (LG M5).
#
# TWO DELIBERATE NON-USES, both worth stating because the fields are right there:
#
#   `Gap.foundational` is NOT used. The Grader records it as an observation
#   ("does a foundation look genuinely absent?") and gap-model M1 is explicit
#   that it is "observed, not decisive" — what a gap DOES is decided by
#   `is_blocking`, in code, from `kind` alone. Generating an insight from the
#   soft signal would give a model's aside the weight of a policy.
#
#   VERIFICATION ATTEMPTS ARE NEVER POOLED WITH ASSESSMENTS. A verification
#   answer is evidence about one gap; an assessment answer is evidence about the
#   objective. Averaging them would misreport both, so every population here is
#   built from gap objects or from explicitly-filtered attempt kinds.
#
# EMPIRICAL STATUS: implemented and contract-tested against fixtures. The stored
# corpus holds 2 gaps and 0 verification attempts, so real-world firing
# frequency and threshold quality are UNVALIDATED until the manual E2E round.
#
# Pure: no IO, no model calls.

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.learning import history, progress
from backend.learning.patterns import Pattern

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle
    from backend.learning.gaps import Gap
    from backend.learning.graph import LearningGraph, LearningNode


# ── thresholds ────────────────────────────────────────────────────────────────
#
# Set at the same conservative bar as the M3a.2 templates, and for the same
# reason: no insight is better than a weakly supported one. They are the part
# most likely to move after the manual E2E round produces the first real gap
# volume — recorded here so the tuning has a stated starting point.

# A lifecycle tally is only worth stating once several misconceptions exist.
OUTCOMES_MIN_GAPS = 3
# A backlog is a pattern across objectives, not one unit going badly.
BACKLOG_MIN_GAPS = 2
BACKLOG_MIN_NODES = 2
# A rate needs a denominator that can carry one.
VERIFICATION_MIN_TESTED = 3
REMEDIATION_MIN_WARMUPS = 3


def _walk_gaps(graph: "LearningGraph") -> list[tuple["LearningNode", "Gap"]]:
    """Every gap on the promised journey, paired with the unit carrying it.

    Scoped to `progress.walk_nodes` for the same reason every other aggregate
    is: one population, shared with the profile and both progress measures.
    Gaps on remedial warm-ups are excluded — a warm-up's own misconceptions are
    part of the detour, not of the journey being reported.
    """
    return [(node, gap) for node in progress.walk_nodes(graph) for gap in node.gaps]


def _ref(node: "LearningNode", gap: "Gap") -> dict:
    """An evidence reference that resolves to the answer which opened the gap.

    `origin_attempt` is the audit link the Gap Model records at mint time. It can
    point one past the end when a gap was minted with no grading call in flight,
    so it is clamped rather than trusted — an unresolvable reference would make a
    card unauditable, which is the one thing a pattern may not be.
    """
    index = gap.origin_attempt
    if not (0 <= index < len(node.attempts)):
        index = max(len(node.attempts) - 1, 0)
    return {"node_id": node.id, "attempt_index": index, "gap_id": gap.id}


# ── G1 · what happened to the misconceptions ──────────────────────────────────


def gap_outcomes(graph: "LearningGraph") -> Pattern | None:
    """How many named misconceptions were found, and what became of them.

    A lifecycle tally, not a judgement: `verified` is the only status earned by
    evidence, `waived` is a decision the learner made, and `open` is neither.
    Reporting all three keeps the count honest — a screen that showed only
    "3 resolved" would let a waiver read as mastery.
    """
    pairs = _walk_gaps(graph)
    if len(pairs) < OUTCOMES_MIN_GAPS:
        return None

    verified = [(n, g) for n, g in pairs if g.status == "verified"]
    waived = [(n, g) for n, g in pairs if g.status == "waived"]
    still_open = [(n, g) for n, g in pairs if g.is_open]
    return Pattern(
        template="gap_outcomes",
        detail={
            "total": len(pairs),
            "verified": len(verified),
            "waived": len(waived),
            "open": len(still_open),
        },
        evidence=[_ref(n, g) for n, g in pairs],
    )


# ── G2 · what is still standing in the way ────────────────────────────────────


def blocking_backlog(graph: "LearningGraph") -> Pattern | None:
    """Open BLOCKING misconceptions, spread across more than one objective.

    `blocking` rather than `foundational`: blocking is a pure function of `kind`,
    decided in code, and is exactly the property that keeps a unit off
    `understood`. It is the one gap attribute with policy behind it.

    The cross-objective requirement is what separates a backlog from one unit
    the learner is still working through — which the profile already shows as
    *Needs work* and does not need repeating as an insight.
    """
    open_blocking = [
        (n, g) for n, g in _walk_gaps(graph) if g.is_open and g.is_blocking
    ]
    nodes = {n.id for n, _ in open_blocking}
    if len(open_blocking) < BACKLOG_MIN_GAPS or len(nodes) < BACKLOG_MIN_NODES:
        return None

    return Pattern(
        template="blocking_backlog",
        detail={
            "gaps": len(open_blocking),
            "nodes": len(nodes),
            # Reaching the cap means the system has stopped proposing work on
            # it. Saying so is the difference between "still open" and
            # "abandoned by the system without telling you".
            "exhausted": sum(1 for _, g in open_blocking if g.is_exhausted),
        },
        evidence=[_ref(n, g) for n, g in open_blocking],
    )


# ── G3 · how verification went ────────────────────────────────────────────────


def verification_outcomes(graph: "LearningGraph") -> Pattern | None:
    """Of the misconceptions actually tested, how many closed.

    The population is gaps that HAVE been tested — `verification_attempts > 0`
    or already `verified`. A gap nobody asked about is not a verification
    failure, and including it would turn "we have not got to it" into "you did
    not pass it".

    Assessment answers are structurally absent from this: the population is gap
    objects, and the counters are written only by the verification path.
    """
    tested = [
        (n, g) for n, g in _walk_gaps(graph)
        if g.verification_attempts > 0 or g.status == "verified"
    ]
    if len(tested) < VERIFICATION_MIN_TESTED:
        return None

    closed = [(n, g) for n, g in tested if g.status == "verified"]
    return Pattern(
        template="verification_outcomes",
        detail={
            "tested": len(tested),
            "closed": len(closed),
            # Tested more than once and still not closed — the honest shape of
            # "this one is hard", without calling the learner anything.
            "retried": sum(1 for _, g in tested if g.verification_attempts > 1),
        },
        evidence=[_ref(n, g) for n, g in tested],
    )


# ── G4 · did stepping back close anything ─────────────────────────────────────


def remediation_closure(graph: "LearningGraph") -> Pattern | None:
    """Of the warm-ups built for a specific misconception, how many closed it.

    Uses `lesson_brief["remediates"]` — the gap ids the Mutator records on the
    warm-up it generates (gap-model M5) — and checks the CURRENT status of those
    gaps wherever they live. This is the one measure that connects the three
    phases: a warm-up (M5) built for a gap (M2/M3), closed by verification (M6).

    Distinct from M3a.2's structural `remediation effectiveness`, which asks
    whether the blocked UNIT later reached `understood`. This asks whether the
    specific misconception was closed — a sharper question that only gap data
    can answer.
    """
    by_id = {g.id: g for _, g in _walk_gaps(graph)}
    for node in graph.nodes.values():           # warm-ups are off the walk
        for gap in node.gaps:
            by_id.setdefault(gap.id, gap)

    warmups = [
        (node, [by_id[gid] for gid in (node.lesson_brief or {}).get("remediates", [])
                if gid in by_id])
        for node in graph.nodes.values()
        if (node.lesson_brief or {}).get("remediates")
    ]
    warmups = [(n, gaps) for n, gaps in warmups if gaps]
    if len(warmups) < REMEDIATION_MIN_WARMUPS:
        return None

    closed = [(n, gaps) for n, gaps in warmups
              if all(g.status == "verified" for g in gaps)]
    return Pattern(
        template="remediation_closure",
        detail={"warmups": len(warmups), "closed": len(closed)},
        evidence=[
            {"node_id": n.id, "attempt_index": max(len(n.attempts) - 1, 0),
             "gap_id": gaps[0].id}
            for n, gaps in warmups
        ],
    )


TEMPLATES = (gap_outcomes, blocking_backlog, verification_outcomes,
             remediation_closure)


def detect(graph: "LearningGraph") -> list[dict]:
    """Every gap-derived observation the evidence supports. Usually empty.

    Returns `[]` on any graph without gap records — every session written before
    the gap model, and every flag-off session — which is the backward-compatible
    case and by far the commonest one today.
    """
    found = [template(graph) for template in TEMPLATES]
    return [p.to_dict() for p in found if p is not None]
