# The gap model — M1 of the gap-model phase (docs/planning/phases/gap-model.md).
#
# A gap is a CLAIM THE LEARNER MADE THAT IS FALSE, attached to the objective
# clause it violates. Not a topic, not a score. It exists because one answer can
# contain several independent misconceptions: the Grader already detects them
# all, and before this everything downstream could carry exactly one
# (learning-engine.md §18.1).
#
# M1 is write-only and inert. Nothing reads gaps yet — no blocking, no
# remediation, no verification, no API surface. This module is the model and its
# JSON round-trip, nothing else. Blocking takes effect in M7, deliberately after
# M6 makes closure possible: a build where gaps block before verification exists
# would accumulate gaps no learner could ever close.
#
# Two rules from the approved policy (§18.16) are enforced HERE, at the point of
# construction, because they are properties of a gap rather than decisions about
# one:
#
#   1. `no_attempt` and `none` never become gaps. Silence is not a misconception,
#      and a blocking gap earned by "I don't know" would be unclosable.
#   2. `blocking` is a pure function of `kind`. The model never votes on it —
#      the same rule that governs `depth` (LD2) and curriculum size: models
#      observe, code decides.
#
# Identity is OURS. `Gap.create` mints the id; a model is only ever shown ids and
# asked to reference them (M3). Nothing here accepts a model-supplied id.

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Literal


# The lifecycle. Three values, and the whole semantics (§18.16):
#   open      detected, unresolved
#   verified  closed by positive evidence on a FRESH verification question —
#             the only status that permits `understood`, and the only one no
#             learner action can produce
#   waived    the learner explicitly chose to stop remediating. Stops the system
#             asking; never counts as evidence; reversible.
GapStatus = Literal["open", "verified", "waived"]

# Kinds that can BE a gap. `no_attempt` and `none` are absent by design — see
# rule 1 above. This is the vocabulary the Grader will import in M2, which is why
# it lives here rather than in the agent: the model layer owns the noun.
GapKind = Literal["missing_prerequisite", "wrong_model", "right_idea_wrong_altitude"]

GAP_KINDS: frozenset[str] = frozenset(
    {"missing_prerequisite", "wrong_model", "right_idea_wrong_altitude"}
)

# Kinds that prevent a node reaching `understood`. Uncapped: EVERY gap of these
# kinds is blocking. The bound belongs to the remediation queue, which is a
# separate, operational idea — conflating them would make a gap's meaning depend
# on a queue limit (§18.16.1).
BLOCKING_KINDS: frozenset[str] = frozenset({"missing_prerequisite", "wrong_model"})

# Kinds a Grader verdict may name that must NOT produce a gap.
NON_GAP_KINDS: frozenset[str] = frozenset({"none", "no_attempt"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Gap:
    """One false claim, with its lifecycle.

    Constructed through `create` in application code; `from_dict` exists for the
    store and is deliberately permissive — see its docstring.
    """

    id: str
    kind: str
    claim: str
    objective_part: str = ""
    # Observed by the Grader ("does a foundation look genuinely absent?"), never
    # decisive. What a gap DOES is decided by `is_blocking`, in code.
    foundational: bool = False
    status: GapStatus = "open"
    # Bounded at 2 (§18.16 LQ10). Reaching the cap removes the gap from the
    # active set — it never writes `verified` and never writes `waived`.
    verification_attempts: int = 0
    # Stable identity for a LATER cross-session query. Nothing reads it yet;
    # cross-session interpretation stays deferred until learner identity exists
    # (LQ7). Storing it now is what keeps that a query rather than a redesign.
    objective_key: str = ""
    origin_attempt: int = -1
    resolved_by: int | None = None
    opened_at: str = ""
    closed_at: str | None = None

    @property
    def is_blocking(self) -> bool:
        """Does this gap prevent its node reaching `understood`?

        Pure function of `kind`. An UNKNOWN kind is deliberately non-blocking:
        the conservative direction is to let the learner progress, never to
        block them on something we cannot interpret.
        """
        return self.kind in BLOCKING_KINDS

    @property
    def is_open(self) -> bool:
        return self.status == "open"

    @classmethod
    def create(
        cls,
        kind: str,
        claim: str,
        *,
        objective_part: str = "",
        foundational: bool = False,
        objective_key: str = "",
        origin_attempt: int = -1,
    ) -> "Gap":
        """Mint a new gap. The ONLY way application code should make one.

        Raises on a kind that must not become a gap, rather than quietly
        dropping it: a caller trying to open a gap for `no_attempt` has
        misunderstood the policy, and silence would hide that.
        """
        if kind in NON_GAP_KINDS:
            raise ValueError(
                f"{kind!r} never becomes a gap — silence and 'nothing fell short' "
                "are not misconceptions (learning-engine.md §18.16 LQ9)"
            )
        if kind not in GAP_KINDS:
            raise ValueError(f"unknown gap kind {kind!r}; expected one of {sorted(GAP_KINDS)}")
        if not claim.strip():
            raise ValueError("a gap needs a claim — the misconception in one sentence")
        return cls(
            id=uuid.uuid4().hex,
            kind=kind,
            claim=claim.strip(),
            objective_part=objective_part.strip(),
            foundational=foundational,
            objective_key=objective_key,
            origin_attempt=origin_attempt,
            opened_at=_now(),
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> "Gap":
        """Rebuild from storage, PRESERVING whatever was written.

        Deliberately permissive where `create` is strict. Validation belongs at
        the point a gap is opened; at load time the only correct behaviour is to
        return what is stored. Dropping or rewriting a gap we cannot interpret
        would be exactly the silent data loss the flag contract forbids (§3.8) —
        and an unknown kind is already harmless, because `is_blocking` is false
        for it.
        """
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in payload.items() if k in known})


@dataclass
class GapState:
    """Everything gap-related that hangs off one node.

    A container rather than a bare list because the per-node remediation counter
    belongs with the gaps and nothing queries either — the same reasoning that
    kept `objective`, `kind`, `priority` and `area_id` inside existing JSON
    payloads rather than spending columns on them (LD6).
    """

    gaps: list[Gap] = field(default_factory=list)
    # Bounded at 4 (§18.16 LQ10). Reset by a deliberate return to the node.
    remediation_rounds: int = 0

    def __bool__(self) -> bool:
        return bool(self.gaps) or self.remediation_rounds > 0

    def to_dict(self) -> dict:
        return {
            "gaps": [g.to_dict() for g in self.gaps],
            "remediation_rounds": self.remediation_rounds,
        }

    @classmethod
    def from_dict(cls, payload: dict | list | None) -> "GapState":
        """Accepts the container, a bare list, or nothing.

        The bare-list form is not a format we write; it is accepted so that a
        hand-edited or externally-produced payload degrades to "these gaps, no
        counter" instead of losing the gaps entirely.
        """
        if not payload:
            return cls()
        if isinstance(payload, list):
            return cls(gaps=[Gap.from_dict(g) for g in payload])
        return cls(
            gaps=[Gap.from_dict(g) for g in payload.get("gaps", [])],
            remediation_rounds=int(payload.get("remediation_rounds", 0) or 0),
        )
