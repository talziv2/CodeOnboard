# Which Tutor is running here, and why — decided by the server, never the client.
#
# Two modes (tutor.md §3):
#
#   EXPLAIN   the stop is not asking anything. Free contextual tutoring, from a
#             context that includes the reveal.
#   SCAFFOLD  a question is outstanding. Socratic assistance only, from a context
#             that physically cannot hold the answer.
#
# THIS IS THE SERVER-SIDE TWIN OF `lessonPhase.isAsking()`, and it exists rather
# than trusting the client for one reason: a client that lied about the mode would
# be asking for the answer key. The frontend has the same predicate for rendering;
# the endpoint recomputes it from the graph on every call.
#
# WHY THE THIRD CLAUSE DELEGATES TO `retry.py`
#
# "Is the unit's own prompt still answerable" is a question with a long answer —
# it depends on whether anything has been graded, on whether a re-teach installed
# a new prompt (and a new reveal with it), on whether the learner has asked to see
# the answer, and on the failed-grade exemption. `retry.py` already holds all of
# that, in one place, because the four-flag version of the same decision is what
# it was written to replace. Re-deriving it here would rebuild the seam.
#
# Pure: no IO, no model call, no mutation. Same contract as `retry.py`,
# `adaptation.py` and `progress.py` — which is what lets the whole dispatch be
# tested without an API key.

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from backend.learning import history, retry as retry_model, tutor as tutor_model
from backend.learning.tutor import EXPLAIN, SCAFFOLD

if TYPE_CHECKING:  # pragma: no cover - typing only
    from backend.learning.graph import LearningNode


# ── why a mode was chosen. Shown to the learner, so each is a fact they can act on.

# A verification question is on screen.
ASKING_VERIFICATION = "asking_verification"
# A re-assessment question is on screen.
ASKING_REASSESSMENT = "asking_reassessment"
# The unit's own prompt, still answerable.
ASKING_LESSON = "asking_lesson"
# Nothing is outstanding: read, revisit, or already graded.
NOT_ASKING = "not_asking"
# There is no stop to talk about at all.
NO_NODE = "no_node"


@dataclass(frozen=True)
class TutorMode:
    """What the Tutor may do here, and everything a surface needs to say so.

    `reason` is populated on BOTH paths, exactly as `RetryOffer.reason` is: a mode
    strip that can say *why* it is scaffolding rather than explaining is the
    difference between a restriction and an explanation.

    `question` is the text of the outstanding prompt. It is carried because the
    scaffold agent needs it — a hint about a question you were not shown is not a
    hint — and it is safe to carry because a question is not an answer.
    """

    mode: str
    reason: str
    question: str = ""
    # `history.SOURCE_*` — which mechanism asked. Not stored on the turn; it is a
    # fact about the node at this moment, and `history.py` owns it.
    question_source: str = ""
    hints_used: int = 0
    hints_left: int = 0
    revealed: bool = False
    turns: int = 0

    @property
    def is_scaffold(self) -> bool:
        return self.mode == SCAFFOLD

    @property
    def can_hint(self) -> bool:
        """Is there a rung left to write?

        False in EXPLAIN by construction: there is no question to scaffold, and
        `POST /tutor/hint` answers 409 `not_asking` rather than inventing one.
        """
        return self.is_scaffold and self.hints_left > 0

    @property
    def can_reveal(self) -> bool:
        """May the learner spend this prompt to see the explanation?

        Available from rung ZERO, deliberately (tutor.md §6.3): the ladder bounds
        how many hints the system will WRITE, not when honesty becomes available.
        A learner who already knows they want the explanation should not have to
        climb three rungs to ask for it.

        False once already revealed — the prompt is spent and there is nothing
        left to spend.

        False on a VERIFICATION or RE-ASSESSMENT question, because those ship no
        answer by design and there is no stored reveal to give — `/tutor/reveal`
        already refuses one with `no_explanation_for_this_question`. Without this,
        the frontend renders the reveal control and its "this stops counting"
        warning for a fresh check, and the learner who presses it gets the
        refusal instead — the offer and its denial on screen at once.
        """
        return (
            self.is_scaffold
            and not self.revealed
            and self.question_source
            not in (history.SOURCE_VERIFICATION, history.SOURCE_REASSESSMENT)
        )

    def to_wire(self) -> dict:
        return {
            "mode": self.mode,
            "reason": self.reason,
            "question": self.question,
            "question_source": self.question_source,
            "hints_used": self.hints_used,
            "hints_left": self.hints_left,
            "revealed": self.revealed,
            "can_hint": self.can_hint,
            "can_reveal": self.can_reveal,
        }


def _explain(node: "LearningNode" | None, reason: str) -> TutorMode:
    state = node.tutor_state if node is not None else tutor_model.TutorState()
    return TutorMode(
        mode=EXPLAIN,
        reason=reason,
        hints_used=state.hints_used,
        hints_left=0,          # no question, so no rung to offer
        revealed=state.revealed,
        turns=state.turns,
    )


def mode_for(node: "LearningNode" | None) -> TutorMode:
    """Which Tutor this stop gets.

    SCAFFOLD when — and only when — an UNANSWERED QUESTION IS OUTSTANDING. Three
    ways that is true, checked in the order the learner would meet them:

      1. a verification question, aimed at one named gap;
      2. a re-assessment question, aimed at the objective;
      3. the unit's own prompt, still live.

    Anything else is EXPLAIN. That deliberately includes a stop the learner is
    revisiting after a verdict: the reveal is on screen there, so there is nothing
    a scaffold could protect and refusing to explain would be theatre.
    """
    if node is None:
        return _explain(None, NO_NODE)

    state = node.gap_state
    tutor_state = node.tutor_state

    def scaffolding(question: str, source: str) -> TutorMode:
        return TutorMode(
            mode=SCAFFOLD,
            reason={
                history.SOURCE_VERIFICATION: ASKING_VERIFICATION,
                history.SOURCE_REASSESSMENT: ASKING_REASSESSMENT,
            }.get(source, ASKING_LESSON),
            question=question,
            question_source=source,
            hints_used=tutor_state.hints_used,
            hints_left=tutor_state.hints_left,
            revealed=tutor_state.revealed,
            turns=tutor_state.turns,
        )

    if state.pending_verification:
        return scaffolding(
            str(state.pending_verification.get("question") or ""),
            history.SOURCE_VERIFICATION,
        )
    if state.pending_reassessment:
        return scaffolding(
            str(state.pending_reassessment.get("question") or ""),
            history.SOURCE_REASSESSMENT,
        )

    # The unit's own prompt. `retry.py` owns whether it is still live — including
    # the reveal rule this feature added, so a learner who has already spent it
    # gets EXPLAIN and the reveal they paid for, not a scaffold for a question
    # that is over.
    if retry_model.prompt_is_unanswered(node):
        prompt = str((node.cached_lesson or {}).get("prompt") or "")
        source = (
            history.SOURCE_RETEACH
            if history.lesson_was_retaught(node.attempts)
            else history.SOURCE_LESSON
        )
        return scaffolding(prompt, source)

    return _explain(node, NOT_ASKING)
