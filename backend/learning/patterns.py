# Learning patterns — repeated observations across the evidence (M3a.2).
#
# Level 2 of the evidence hierarchy (learning-graph.md §7.1):
#
#   L0  raw evidence          one attempt, shown verbatim
#   L1  deterministic         a count with its denominator
#   L2  REPEATED PATTERN      a named template, fired on a stated threshold  ← here
#   L3  interpretation        a claim about the learner                      ← NOT built
#
# THE LINE THIS MODULE MUST NOT CROSS
#
# A pattern describes WHAT HAPPENED IN THE EVIDENCE. It never describes who the
# learner is. "Flow objectives needed more than one answer more often than
# component objectives (3 of 4 vs 0 of 5)" is a count. "You struggle with
# cross-component reasoning" is a claim about a person, needs evidence this
# system does not have, and is L3.
#
# Three consequences that are load-bearing rather than stylistic:
#
#   1. **No prose here.** Templates return the NUMBERS; the sentence is composed
#      in `frontend/lib/strings.ts`, where all user-facing wording lives
#      (CLAUDE.md). That keeps every phrasing decision in one reviewable file
#      instead of scattered through aggregation code.
#   2. **Every pattern carries its evidence**, as concrete (node_id,
#      attempt_index) references. A claim the learner cannot audit is a claim
#      the product should not make, so a template that cannot enumerate its
#      support does not fire.
#   3. **No shared-cause inference.** Two shortfalls sharing a `gap_kind` are two
#      shortfalls of the same kind — not two symptoms of one misconception.
#      `gap_kind` is a category with several unrelated members; saying otherwise
#      needs cross-node concept identity, which does not exist.
#
# Deterministic and pure: no model call, no IO. At the measured session size
# (≤ 8 graded answers) an LLM asked for "learning patterns" would produce fluent,
# confident, unfalsifiable prose — the failure mode §4.1.2 refuses for lessons,
# applied to the learner instead of the code.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from backend.learning import history, progress, understanding

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle
    from backend.learning.graph import LearningGraph, LearningNode


# ── thresholds ────────────────────────────────────────────────────────────────
#
# Deliberately strict. Measured against the real corpus, a session carries ≤ 8
# graded answers, so most sessions will fire NOTHING — which is the intended
# outcome. No insight is better than a weakly supported one.

# A contrast needs two populations that can each be a rate rather than an anecdote.
CONTRAST_MIN_ASSESSED = 2
# …and the leading side needs more than one unit behind it, so a single rough
# unit cannot manufacture a "kind" difference.
CONTRAST_MIN_SUPPORT = 2

# A repetition is three occurrences, and it must cross objectives: three
# shortfalls on ONE unit is one unit going badly, not a recurring pattern.
RECURRING_MIN_ATTEMPTS = 3
RECURRING_MIN_NODES = 2

# An area needs enough assessed units for "none of them" to mean anything.
AREA_MIN_ASSESSED = 2

# `gap_kind` values that describe a MISCONCEPTION. Deliberately excludes:
#   none        nothing fell short
#   no_attempt  they did not engage — a fact about engagement, not understanding
#   (absent)    9 of the 40 stored attempts predate the field entirely
SHORTFALL_KINDS = frozenset({
    "missing_prerequisite", "wrong_model", "right_idea_wrong_altitude",
})

# Verdicts that mean the answer did not reach the objective.
FELL_SHORT = frozenset({"confused", "partial"})


@dataclass
class Pattern:
    """One repeated observation, with the evidence it was computed from.

    `detail` carries NUMBERS ONLY. The frontend composes the sentence, so the
    wording — the part that can over-claim — is reviewed in one place.
    """

    template: str
    detail: dict
    evidence: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "template": self.template,
            "detail": self.detail,
            "evidence": self.evidence,
        }


# ── shared evidence access ────────────────────────────────────────────────────


def _assessment_evidence(node: "LearningNode") -> list[tuple[int, dict]]:
    """Evidence-bearing assessments with their index in `node.attempts`.

    The index is what makes a pattern auditable — it points at the exact answer
    the drawer will show. Filtering is `history`'s, not re-decided here:
    assessments only (a verification answer is evidence about one gap), graded
    only (a grading failure is our error), and never off-topic.
    """
    return [
        (index, attempt)
        for index, attempt in enumerate(node.attempts)
        if attempt.get("kind", history.DEFAULT_KIND) == history.ASSESSMENT
        and history.is_evidence(attempt)
    ]


def _assessed(graph: "LearningGraph") -> list[tuple["LearningNode", list[tuple[int, dict]]]]:
    """Units on the promised journey that carry real evidence.

    Scoped to `progress.walk_nodes` for the same reason the profile is: a third
    opinion about which units count is exactly what reusing that avoids.
    """
    out = []
    for node in progress.walk_nodes(graph):
        evidence = _assessment_evidence(node)
        if evidence:
            out.append((node, evidence))
    return out


def _kind_of(node: "LearningNode") -> str:
    brief = node.lesson_brief or {}
    return brief.get("kind") or (node.concept_tags[0] if node.concept_tags else "")


def _landed_first_time(evidence: list[tuple[int, dict]]) -> bool:
    return evidence[0][1].get("classification") == "understood"


# ── P1 · kind contrast ────────────────────────────────────────────────────────


def kind_contrast(graph: "LearningGraph") -> Pattern | None:
    """Did one kind of understanding need more than one answer, more often?

    Compares the rate at which units of each kind FAILED TO LAND ON THE FIRST
    ANSWER. That is the reading the recorded example carries ("taken more
    attempts"), and it is a fact about answers rather than about mastery — a
    unit the learner recovered still took an extra pass, and that is the thing
    being counted.

    Deliberately NOT "not demonstrated": that would fold the two dimensions
    together, because a waived unit is not demonstrated for reasons that have
    nothing to do with how the first answer went.
    """
    groups: dict[str, list[tuple["LearningNode", list[tuple[int, dict]]]]] = {}
    for node, evidence in _assessed(graph):
        kind = _kind_of(node)
        if kind:
            groups.setdefault(kind, []).append((node, evidence))

    stats = {}
    for kind, members in groups.items():
        if len(members) < CONTRAST_MIN_ASSESSED:
            continue
        extra = [(n, ev) for n, ev in members if not _landed_first_time(ev)]
        stats[kind] = (len(extra), len(members), extra)

    best: tuple[float, str, str] | None = None
    for lead, (lead_extra, lead_n, _) in stats.items():
        if lead_extra < CONTRAST_MIN_SUPPORT:
            continue
        for base, (base_extra, base_n, _) in stats.items():
            if base == lead:
                continue
            lead_rate, base_rate = lead_extra / lead_n, base_extra / base_n
            if lead_rate <= base_rate:
                continue
            gap = lead_rate - base_rate
            if best is None or gap > best[0]:
                best = (gap, lead, base)

    if best is None:
        return None

    _, lead, base = best
    lead_extra, lead_n, lead_members = stats[lead]
    base_extra, base_n, _ = stats[base]
    return Pattern(
        template="kind_contrast",
        detail={
            "lead_kind": lead, "lead_extra": lead_extra, "lead_total": lead_n,
            "base_kind": base, "base_extra": base_extra, "base_total": base_n,
        },
        # The units that needed a second answer, each pointing at the first
        # answer that fell short — the observation itself.
        evidence=[
            {"node_id": n.id, "attempt_index": ev[0][0]} for n, ev in lead_members
        ],
    )


# ── P2 · recurring shortfall ──────────────────────────────────────────────────


def recurring_shortfall(graph: "LearningGraph") -> Pattern | None:
    """Did answers fall short the same way, across more than one objective?

    Counts attempts by the Grader's `gap_kind` — WHY an answer fell short. The
    cross-objective requirement is what separates a recurring shortfall from one
    unit going badly three times.

    **This is not a shared-cause claim.** Three `wrong_model` shortfalls are
    three answers of the same category; whether they share one misconception is
    a question about meaning that needs cross-node concept identity, which does
    not exist. The wording says "the same kind of shortfall", never "the same
    misconception".
    """
    by_kind: dict[str, list[dict]] = {}
    for node, evidence in _assessed(graph):
        for index, attempt in evidence:
            if attempt.get("classification") not in FELL_SHORT:
                continue
            kind = attempt.get("gap_kind")
            if kind not in SHORTFALL_KINDS:
                continue
            by_kind.setdefault(kind, []).append(
                {"node_id": node.id, "attempt_index": index}
            )

    for kind, hits in sorted(by_kind.items()):
        nodes = {h["node_id"] for h in hits}
        if len(hits) >= RECURRING_MIN_ATTEMPTS and len(nodes) >= RECURRING_MIN_NODES:
            return Pattern(
                template="recurring_shortfall",
                detail={
                    "gap_kind": kind,
                    "attempts": len(hits),
                    "nodes": len(nodes),
                },
                evidence=hits,
            )
    return None


# ── P3 · area evidence ────────────────────────────────────────────────────────


def area_evidence(graph: "LearningGraph") -> Pattern | None:
    """An area where several units were assessed and none was demonstrated.

    RENAMED from the recorded `area_thin` / "area needs work", and the rename is
    the point. A waived or continued unit counts here — it genuinely has not
    been demonstrated, and hiding that would let a decision about remediation
    rewrite the evidence. But calling the result "needs work" would do the
    opposite error: turn an aggregate into an obligation the learner has
    explicitly declined.

    So the template reports the count and nothing else, and the wording that
    renders it says "0 of 3 assessed objectives demonstrated" rather than
    anything about what the learner should now do.
    """
    by_area: dict[str, list[tuple["LearningNode", list[tuple[int, dict]]]]] = {}
    for node, evidence in _assessed(graph):
        area_id = (node.lesson_brief or {}).get("area_id") or ""
        by_area.setdefault(area_id, []).append((node, evidence))

    for area_id, members in by_area.items():
        if len(members) < AREA_MIN_ASSESSED:
            continue
        demonstrated = [
            n for n, _ in members
            if understanding.classify(n) in (understanding.STRENGTH, understanding.RECOVERED)
        ]
        if demonstrated:
            continue
        title = next(
            (a.get("title", "") for a in graph.areas if a.get("id") == area_id), ""
        )
        return Pattern(
            template="area_evidence",
            detail={
                "area_id": area_id,
                "area_title": title,
                "demonstrated": 0,
                "assessed": len(members),
                # Reported so the wording can stay descriptive: an area whose
                # units were set aside is a different story from one still being
                # worked, and the sentence should not imply the wrong one.
                "set_aside": sum(
                    1 for n, _ in members if understanding.is_set_aside(n)
                ),
            },
            evidence=[
                {"node_id": n.id, "attempt_index": ev[-1][0]} for n, ev in members
            ],
        )
    return None


TEMPLATES = (kind_contrast, recurring_shortfall, area_evidence)


def detect(graph: "LearningGraph") -> list[dict]:
    """Every pattern whose threshold the evidence meets. Often empty, by design.

    An empty list is the expected result for most sessions: the corpus shows a
    ceiling of eight graded answers, and the thresholds are set so that a
    handful of answers produces nothing. The UI is built to render that honestly
    rather than to fill space.
    """
    found = [template(graph) for template in TEMPLATES]
    return [p.to_dict() for p in found if p is not None]
