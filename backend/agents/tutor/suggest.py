# Turning a model's proposal into a control the learner may press — or into nothing.
#
# THE TIER-3 BOUNDARY LIVES HERE (tutor.md §5.3).
#
#     The Tutor never mutates. It can only put an existing button in front of the
#     learner, and the button is the same button that already exists elsewhere in
#     the UI, posting to the same endpoint, with the same validation, the same
#     caps and the same records.
#
# Two properties make that true, and both are in this file:
#
#   1. THE VOCABULARY IS CLOSED and maps 1:1 onto endpoints that already exist.
#      There is no `open_gap`, no `insert_prerequisite`, no `mark_understood` —
#      not because a model would abuse them, but because those are decisions the
#      learning engine makes from graded evidence and a conversation is not that.
#
#   2. EVERY TARGET IS VALIDATED AGAINST THE GRAPH, deterministically, here. A
#      suggestion that would be refused by the endpoint it names is dropped before
#      the learner ever sees it — because an offer that errors when pressed is
#      worse than no offer.
#
# `shorter` is deliberately absent from the vocabulary. Demoting a journey on the
# strength of a conversation is the system deciding the learner has had enough,
# which is exactly what `scope.py`'s "user overrides always win" refuses.
#
# An invalid suggestion is DROPPED SILENTLY AND THE ANSWER TEXT IS KEPT — the same
# rule `briefing/agent.py` applies to a note whose file will not resolve. The
# sentence was still worth reading; only the citation was wrong.
#
# Pure: no IO, no model call, no mutation.

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from backend.learning import retry as retry_model, scope as scope_model
from backend.learning.tutor import (
    SUGGEST_DEEPEN,
    SUGGEST_JUMP,
    SUGGEST_REASSESS,
    SUGGEST_VERIFY,
    SUGGESTION_KINDS,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from backend.learning.graph import LearningGraph, LearningNode


@dataclass(frozen=True)
class Suggestion:
    """A validated offer. Everything the client needs to render one control.

    `label_key` names a string in `frontend/lib/strings.ts` rather than carrying
    prose: the backend decides WHICH action is offered, and the frontend decides
    what it is called — the same split as `retry.mechanism`.
    """

    kind: str
    label_key: str
    node_id: str | None = None
    gap_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "label_key": self.label_key,
            "node_id": self.node_id,
            "gap_id": self.gap_id,
        }


def _verify(graph: "LearningGraph", node: "LearningNode", raw: dict) -> Suggestion | None:
    """A fresh question about ONE named misconception.

    The target must be the gap `retry.py` would actually aim at. Checking it
    against `to_wire` rather than against the gap list is what stops this module
    growing a second opinion about which gap is next: precedence, the active-set
    bound and the per-gap verification cap are all `adaptation`'s and
    `retry`'s business, and a suggestion that disagreed with them would be an
    offer the endpoint refuses.
    """
    offer = retry_model.offer(node)
    if offer.mechanism != retry_model.VERIFY or not offer.gap_id:
        return None
    wanted = str(raw.get("gap_id") or "").strip()
    # A model that named a different gap is not granted it — but naming none, or
    # naming the right one, both resolve to the one gap the engine would pick.
    if wanted and wanted != offer.gap_id:
        return None
    return Suggestion(SUGGEST_VERIFY, "checkGap", node_id=node.id, gap_id=offer.gap_id)


def _reassess(graph: "LearningGraph", node: "LearningNode", raw: dict) -> Suggestion | None:
    """A fresh question about the objective.

    Refused while anything is pending — the learner already has a question in
    front of them — and while the node has never been taught, because there is
    nothing to re-assess.
    """
    if node.gap_state.pending_verification or node.gap_state.pending_reassessment:
        return None
    if retry_model.reassessments_left(node) <= 0:
        return None
    if not node.objective().strip():
        return None
    if not (node.cached_lesson or {}).get("prompt"):
        return None
    return Suggestion(SUGGEST_REASSESS, "askAgain", node_id=node.id)


def _jump(graph: "LearningGraph", node: "LearningNode", raw: dict) -> Suggestion | None:
    """Go to a stop that already exists.

    The target must EXIST and must not be the stop they are already on — a
    control that navigates nowhere reads as broken.

    Deliberately no route check beyond existence, because `/jump` has none:
    "jumping stays UNCONDITIONAL … the learner may study the codebase in whatever
    order they like". Adding one here would refuse an offer the endpoint would
    honour, which is the same defect as offering one it would refuse, pointing the
    other way. (`path_order()` would not supply one anyway — it appends every
    off-path node at the end, so it is an existence check restated.)
    """
    target = str(raw.get("node_id") or "").strip()
    if not target or target == node.id:
        return None
    if target not in graph.nodes:
        return None
    return Suggestion(SUGGEST_JUMP, "goToStop", node_id=target)


def _deepen(graph: "LearningGraph", node: "LearningNode", raw: dict) -> Suggestion | None:
    """Promote optional material the planner already produced.

    `scope.py` is explicit that a journey with nothing optional left has nothing
    deeper to offer, so this asks the same question rather than inventing one.
    """
    if not scope_model.can_deepen(graph):
        return None
    return Suggestion(SUGGEST_DEEPEN, "goDeeper")


_VALIDATORS = {
    SUGGEST_VERIFY: _verify,
    SUGGEST_REASSESS: _reassess,
    SUGGEST_JUMP: _jump,
    SUGGEST_DEEPEN: _deepen,
}


def validate(
    graph: "LearningGraph",
    node: "LearningNode" | None,
    raw: dict | None,
) -> Suggestion | None:
    """The model's proposal, or None. **Never raises, never mutates.**

    Returning None is the ordinary case, not an error: most answers propose
    nothing, and a proposal the graph refuses is indistinguishable from one that
    was never made — which is the point.
    """
    if not raw or node is None:
        return None
    kind = str(raw.get("kind") or "").strip()
    if kind not in SUGGESTION_KINDS:
        return None
    validator = _VALIDATORS.get(kind)
    if validator is None:  # pragma: no cover - unreachable while the sets agree
        return None
    try:
        return validator(graph, node, raw)
    except Exception:
        # A malformed proposal costs the proposal, never the answer. This module
        # sits between a model and a learner's screen; it does not get to raise.
        return None
