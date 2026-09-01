# "Ask me again" — which mechanism, decided in one place.
#
# THE LEARNER SEES ONE ACTION. Which machinery serves it is an implementation
# detail, and one they should never have to reason about: "verify a gap" and
# "re-assess the objective" are our vocabulary for our own bookkeeping, and a
# learner asked to choose between them is being asked to diagnose themselves
# before they are allowed another go.
#
# WHY THIS IS A MODULE AND NOT A CONDITION IN THE ENDPOINT
#
# The decision used to live in the frontend, spread across `canAnswerAgain`,
# `checkAvailable`, `canRequestWarmUp` and `warmUpDeclined`, each derived from a
# different slice of the grading response. Every defect this pass found was a
# seam between them:
#
#   - `canAnswerAgain` was computed, was TRUE after a hint, and the row that read
#     it was unreachable because `FAILED` short-circuited first. The system wrote
#     a scaffold whose prompt forbids it from containing the answer, then removed
#     the only button that could use it.
#   - `checkAvailable` could not see verification budget, so an exhausted gap was
#     offered and the refusal arrived as an error.
#   - `warmUpDeclined` was derived two different ways and was wrong on one.
#
# The facts those flags were approximating all live here: gaps and their budgets,
# `remediation_rounds`, `reassessments`, and what the attempt record says about
# which questions have been answered. So the decision belongs here too, and the
# frontend renders it.
#
# THE RULE THIS MODULE ENFORCES, and it is the whole reason the dispatch is small
#
#   A retry question NEVER ships its own answer.
#
# `cached_lesson.prompt` always does: Teaching's contract for `reveal` is "the
# explanation — now you may answer it", and `lessonView` opens the reveal after
# ANY graded answer. A re-teach does not escape it — it regenerates the whole
# lesson, so its new prompt arrives with a new `reveal` that answers it. So the
# unit's own prompt is answerable exactly once, before its reveal has ever been
# shown, and every later assessment comes from `/verify` or `/reassess`, both of
# which ship a question and nothing else.
#
# Pure: no IO, no model calls, no mutation. Same contract as `progress.py`,
# `adaptation.py` and `understanding.py` — which is what lets the whole policy be
# tested without an API key.

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from backend.learning import adaptation, history, tutor as tutor_model
from backend.learning.gaps import REASSESSMENT_CAP
from backend.learning.graph import understanding_of

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle
    from backend.learning.graph import LearningNode


# ── mechanisms ────────────────────────────────────────────────────────────────

# A fresh question aimed at ONE named false belief (gap-model M6). Preferred
# wherever it applies: a gap is a sharper target than the whole objective, and it
# is the only thing that can produce `verified` and lift M7's demotion.
VERIFY = "verify"
# A fresh question aimed at the OBJECTIVE (learning-loop M2). The route for the
# shortfall that named no gap — which is most of them.
REASSESS = "reassess"
# The unit's own prompt, never yet answered and its reveal never shown. Not a
# retry at all; it is the first attempt, and it is here so that "what should the
# learner do about this stop" has ONE answer rather than two half-answers.
ANSWER = "answer"

# ── reasons nothing is offered ────────────────────────────────────────────────

# The objective is met and nothing is outstanding. Not a refusal.
MET = "objective_met"
# Every open blocking gap has spent its verification budget AND the node has spent
# its re-assessment budget. The caps end the offering, never the obligation — the
# gaps stay open, the node stays short of `understood`, and `is_needs_work` still
# reports it (§18.16.1).
EXHAUSTED = "budget_spent"
# The learner already has an unanswered question in front of them.
PENDING = "already_asked"
# Nothing to assess: no objective, or a node that has never been taught.
NOT_APPLICABLE = "not_applicable"
# The objective was reached under substantial assistance, so a fresh question is
# still worth offering (tutor.md §6.5). NOT a refusal and NOT a demotion — the
# learner is `understood`, `understanding_of` says so, readiness counts it, and
# `is_complete` is satisfied. All this changes is that the surface keeps offering
# instead of reporting the matter closed.
ASSISTED = "assisted"


@dataclass(frozen=True)
class RetryOffer:
    """What "Ask me again" would do here, and why not when it would not.

    `reason` is populated on BOTH paths, not only on refusal. A surface that can
    say *why* an action is unavailable is the difference between a button that is
    missing and a button that was considered — and the reasons here are all things
    the learner can act on or accept, never internal failures.
    """

    mechanism: str | None
    reason: str
    # The gap `/verify` would aim at. None for every other mechanism.
    gap_id: str | None = None
    # How many fresh objective-scoped questions remain. Reported even when the
    # offer is a `verify`, because it is what tells a surface whether the learner
    # is near the end of their attempts at this stop.
    reassessments_left: int = 0

    @property
    def available(self) -> bool:
        return self.mechanism is not None


def prompt_is_unanswered(node: "LearningNode") -> bool:
    """Is the unit's own question still live — asked, and never answered?

    **This is what closes the revisit back door.** `revealed` in the panel is
    `Boolean(result) || attempts.length > 0`, so navigating away from a graded
    stop and back re-opened the composer with the explanation on screen. The rule
    forbidding that was enforced against the learner who read the action row and
    not against the one who wandered.

    True only while NO assessment has been graded here. Deliberately not "the
    current prompt has not been answered *by that text*": a re-teach installs a
    new prompt, but it also installs a new `reveal` that answers it, so the
    replacement is not a fresh question either. Once anything has been graded, the
    reveal has been shown and this prompt is spent for good.

    A FAILED grade does not spend it. `history.is_graded` is false there, the
    verdict is our fallback rather than the learner's answer, and charging them
    for our outage would take away the attempt they never got.
    """
    if not (node.cached_lesson or {}).get("prompt"):
        return False
    # THE LEARNER ASKED TO SEE THE ANSWER (tutor.md §6.3).
    #
    # This is the same rule as the line below, reached a different way. The
    # docstring's claim is that "once anything has been graded, the reveal has
    # been shown and this prompt is spent for good" — `POST /tutor/reveal` shows
    # the reveal without anything being graded, so the antecedent is satisfied and
    # the consequent has to follow. A prompt whose explanation is on screen cannot
    # assess anything; leaving it answerable would let a learner read the reveal
    # and then submit it back as their answer.
    #
    # The assessment is not lost, it is deferred: with this False, `offer` falls
    # through to the gap and objective branches, so the learner is handed a
    # `verify` or a `reassess` — a fresh question that ships no answer, bounded by
    # the caps that already exist. Nothing about the objective changes.
    #
    # Inert when the Tutor is off: nothing can set `revealed` without the
    # endpoint, so this reads False on every session that never used it.
    if tutor_model.was_revealed(node):
        return False
    return not any(
        history.is_graded(a) for a in history.assessments(node.attempts)
    )


def reassessments_left(node: "LearningNode") -> int:
    return max(0, REASSESSMENT_CAP - node.gap_state.reassessments)


def offer(node: "LearningNode") -> RetryOffer:
    """The one retry this stop offers, or the reason it offers none.

    Order matters, and each step is a claim:

    1. **A question already on screen wins.** Answer that before asking for
       another; offering a second would abandon a budget already spent.
    2. **The objective being met ends it.** Not a refusal — there is nothing to
       retry, and the surface should say so rather than hiding the control.
    3. **Never taught, never asked** — nothing to assess.
    4. **The first attempt, if there has been none.** Not a retry; included so
       one function answers "what now" completely.
    5. **A gap outranks the objective.** It is a sharper target, and it is the
       only thing that can produce `verified` — which is what lifts M7's
       demotion. Re-assessing while a blocking gap is unverified would produce an
       `understood` the node could not keep.
    6. **Otherwise the objective**, while budget remains.
    """
    state = node.gap_state

    if state.pending_verification:
        return RetryOffer(None, PENDING, reassessments_left=reassessments_left(node))
    if state.pending_reassessment:
        return RetryOffer(None, PENDING, reassessments_left=reassessments_left(node))

    if understanding_of(node) == "understood":
        # REACHED WITH SUBSTANTIAL HELP (tutor.md §6.5). Offer another, do not
        # take anything away.
        #
        # The asymmetry is the point, and it is the same one `understanding.py`
        # draws: assistance is a DECISION the learner made, and a decision is
        # never evidence — so it may not move `understanding_state`, may not open
        # a gap, may not lower readiness and may not block completion. What it may
        # do is change what the system PUTS IN FRONT of them, which is this
        # function's entire job.
        #
        # It terminates: taking the offer calls `new_question()`, which clears
        # `hints_used`, so a re-assessment answered without help reports MET.
        left = reassessments_left(node)
        if tutor_model.heavily_scaffolded(node) and left > 0:
            return RetryOffer(REASSESS, ASSISTED, reassessments_left=left)
        return RetryOffer(None, MET, reassessments_left=left)

    if not node.objective().strip() and not node.gaps:
        return RetryOffer(None, NOT_APPLICABLE)

    # NEVER TAUGHT. Found by running this function over all 968 stored nodes: a
    # stop with no `cached_lesson` fell through every branch above and was offered
    # a RE-ASSESSMENT — a second question about material the learner has not been
    # shown once. Unreachable from `/lesson`, which renders before it reports, and
    # wrong everywhere else. There is nothing to re-assess until there is a lesson.
    if not (node.cached_lesson or {}).get("prompt") and not node.gaps:
        return RetryOffer(None, NOT_APPLICABLE)

    if prompt_is_unanswered(node):
        return RetryOffer(ANSWER, "", reassessments_left=reassessments_left(node))

    # `decide_all`'s active set is already precedence-ordered and cap-filtered, so
    # an exhausted gap is not offered — reusing it here is what keeps this module
    # from growing a second opinion about which gap is next (§18.5).
    plan = adaptation.decide_all(
        "partial", list(node.gaps), remediation_rounds=state.remediation_rounds
    )
    if plan.active_set:
        return RetryOffer(
            VERIFY, "", gap_id=plan.active_set[0].id,
            reassessments_left=reassessments_left(node),
        )

    left = reassessments_left(node)
    if left > 0:
        return RetryOffer(REASSESS, "", reassessments_left=left)

    return RetryOffer(None, EXHAUSTED, reassessments_left=0)


def to_wire(node: "LearningNode") -> dict:
    """The offer, for the client. One shape on every response that carries it."""
    result = offer(node)
    return {
        "available": result.available,
        "mechanism": result.mechanism,
        "reason": result.reason,
        "gap_id": result.gap_id,
        "reassessments_left": result.reassessments_left,
    }
