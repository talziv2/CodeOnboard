# The Tutor's record and its caps — the model layer, and nothing else.
#
# `agents/tutor/` decides what to SAY. This module owns what is STORED and what
# the numbers mean, in the same relationship `gaps.py` has to the Grader: the
# model layer owns the noun, the agent imports it.
#
# THE ONE LAW THIS MODULE EXISTS TO SERVE (tutor.md §5.1)
#
#     A conversation turn is not evidence about the learner.
#
# Nothing here writes `understanding_state`, opens a `Gap`, records an attempt or
# touches readiness. The counters below describe WHAT HAPPENED — how many hints
# were written, whether the learner asked to see the answer — and two consumers
# read them: `retry.py`, to decide what to OFFER next, and the attempt record, as
# metadata about the conditions an answer was given under. Neither is a claim
# about understanding, and `tests/test_tutor_boundary.py` asserts the import
# boundary that keeps it that way.
#
# WHY THE LADDER IS STATE AND NOT A FOLD OVER THE TRANSCRIPT
#
# "How many hints has this learner had on the question in front of them" could be
# recomputed by walking `graph.tutor` and counting turns since the last question
# was issued. It is not, for the reason `graph.py` gives about `gap_state`: a fold
# recomputed on every read loses the fact silently the first time it is wrong, and
# the first time it is wrong is the first time a question is issued by a path the
# fold did not know about. `new_question()` is one call at three sites; a fold is
# a rule every future site has to re-derive.

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle
    from backend.learning.graph import LearningGraph, LearningNode


# ── modes ─────────────────────────────────────────────────────────────────────
#
# Named here rather than in `agents/tutor/mode.py` because they are stored on
# every turn, so they are part of the record's vocabulary rather than part of the
# agent's dispatch.

# Free contextual tutoring. The stop is not asking anything.
EXPLAIN = "explain"
# A question is outstanding. Socratic assistance only, from a context that
# physically cannot hold the answer (§7.3).
SCAFFOLD = "scaffold"

MODES: frozenset[str] = frozenset({EXPLAIN, SCAFFOLD})


# ── caps ──────────────────────────────────────────────────────────────────────

# How many hints the system will WRITE for one question.
#
# Three, because each rung is a different kind of help — orient, narrow, guide —
# rather than the same help louder. A fourth would be padding; two would jump from
# orientation to a guiding question with nothing in between.
#
# It bounds the hints, NOT the learner: an off-ladder question in SCAFFOLD mode is
# answered at any rung and does not spend one, and `reveal` is available from rung
# zero. A learner who already knows they want the explanation should not have to
# climb a ladder to ask for it.
HINT_LADDER_MAX = 3

# How many Tutor calls one session may make. Hints count (they cost a call);
# `reveal` does not (it makes none).
#
# Per session rather than per stop (tutor.md OQ-4): a per-stop allowance penalises
# the one stop that genuinely confuses somebody, which is the stop the feature
# exists for. Reaching it is a hard stop with a visible counter, because a spend
# limit the learner cannot see is worse than one they can.
TUTOR_QUESTION_CAP = 20

# The question was answered under substantial assistance. Consumed by exactly one
# thing — `retry.to_wire`, which keeps the offer of a fresh question open instead
# of reporting the objective met.
#
# It does NOT lower `understanding_state`, `understanding_of()` or readiness.
# Needing a hint is a decision, not a false claim, and the evidence is the same
# correct answer either way (tutor.md §6.5).
HEAVY_SCAFFOLD = 2

# Turns on ONE stop, in EXPLAIN, after which the system offers a fresh question.
# High enough that a couple of clarifying questions is just reading.
DWELLING_TURNS = 4

# Turns on a stop the learner has already settled, after which the system offers
# to check it. Lower, because returning at all is the signal.
RETURNING_TURNS = 2

# How many recent turns reach a prompt, and how much of each answer.
CONTEXT_TURNS = 6
CONTEXT_ANSWER_CHARS = 400

# The longest question the endpoint accepts.
MAX_QUESTION_CHARS = 500


# ── scope, as the agent reports it ────────────────────────────────────────────

# Answered from the assembled context.
ANSWERED = "answered"
# The context does not support an answer — a different repository, a later stop,
# something outside what the Tutor can see.
OUT_OF_SCOPE = "out_of_scope"
# The model believes it was asked the assessment question. Trusted as a LABEL
# only; the real enforcement is that a scaffold context has no answer in it.
IS_THE_ASSESSMENT = "is_the_assessment"

SCOPES: frozenset[str] = frozenset({ANSWERED, OUT_OF_SCOPE, IS_THE_ASSESSMENT})


# ── suggestions ───────────────────────────────────────────────────────────────
#
# A closed vocabulary that maps 1:1 onto endpoints that already exist. The Tutor
# proposes; `agents/tutor/suggest.py` validates against the graph; the learner
# clicks. Nothing here is a mutation.
#
# `shorter` is deliberately absent. Demoting a journey on the strength of a
# conversation is the system deciding the learner has had enough, which is exactly
# what `scope.py`'s "user overrides always win" refuses.
SUGGEST_VERIFY = "verify"
SUGGEST_REASSESS = "reassess"
SUGGEST_JUMP = "jump"
SUGGEST_DEEPEN = "deepen"

SUGGESTION_KINDS: frozenset[str] = frozenset(
    {SUGGEST_VERIFY, SUGGEST_REASSESS, SUGGEST_JUMP, SUGGEST_DEEPEN}
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── the per-node counters ─────────────────────────────────────────────────────


@dataclass
class TutorState:
    """What the Tutor has done on ONE stop.

    Two lifetimes in one object, deliberately, because they are persisted
    together and always read together:

      `hints_used` / `revealed`  belong to THE CURRENT QUESTION and are cleared by
                                 `new_question()`. A re-teach, a verification and a
                                 re-assessment each install a question the learner
                                 has not seen, and carrying a spent ladder onto it
                                 would deny hints on a question nobody has had a
                                 hint about.
      `turns`                    belongs to THE STOP and is never cleared. It is
                                 what `dwelling` reads, and dwelling is a fact
                                 about how long somebody has been here rather than
                                 about any one question.

    Defaults are the pre-Tutor state exactly, so every stored node loads correct
    without a migration.
    """

    hints_used: int = 0
    revealed: bool = False
    turns: int = 0

    def new_question(self) -> None:
        """A question the learner has not seen has been issued here.

        Called from the three sites that install one — `teaching/respond.reteach`,
        `teaching/verify.store`, `teaching/reassess.store`. Not from `/advance`:
        arriving at a stop does not issue anything, the lesson's own prompt was
        already there, and a learner who walks away and back has not earned three
        more hints.
        """
        self.hints_used = 0
        self.revealed = False

    @property
    def hints_left(self) -> int:
        return max(0, HINT_LADDER_MAX - self.hints_used)

    @property
    def ladder_spent(self) -> bool:
        return self.hints_used >= HINT_LADDER_MAX

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict | None) -> "TutorState":
        """Tolerant by construction: anything unreadable loads as a fresh state.

        A corrupt counter must not cost the learner their session, and the honest
        degraded value is "no hints recorded here" rather than an exception.
        """
        if not isinstance(raw, dict):
            return cls()
        def _int(key: str) -> int:
            value = raw.get(key)
            return value if isinstance(value, int) and value >= 0 else 0
        return cls(
            hints_used=_int("hints_used"),
            revealed=raw.get("revealed") is True,
            turns=_int("turns"),
        )


# ── the transcript record ─────────────────────────────────────────────────────


def new_turn(
    *,
    node_id: str | None,
    mode: str,
    question: str,
    answer: str,
    scope: str,
    hint_level: int = 0,
    citations: list[dict] | None = None,
    suggestion: dict | None = None,
    grounded: bool = True,
    usage: dict | None = None,
) -> dict:
    """One exchange, as it is stored. The ONLY constructor of a turn.

    `node_id` is which stop the question was asked FROM, and it is what makes the
    transcript a record of the journey rather than a flat log — the panel filters
    by it, and a turn whose node has since gone renders as "earlier in this
    session" rather than disappearing.

    Optional keys are OMITTED when empty rather than nulled, following
    `history.new_response`: absent means "this turn produced none", which is a
    different claim from "we do not know", and the two must stay distinguishable
    for any later measurement.
    """
    turn: dict = {
        "id": uuid.uuid4().hex,
        "at": _now(),
        "node_id": node_id,
        "mode": mode if mode in MODES else EXPLAIN,
        "hint_level": hint_level,
        "question": question,
        "answer": answer,
        "scope": scope if scope in SCOPES else ANSWERED,
        "grounded": grounded,
        "pinned": False,
    }
    if citations:
        turn["citations"] = citations
    if suggestion:
        turn["suggestion"] = suggestion
    if usage:
        turn["usage"] = usage
    return turn


def turns_for_node(transcript: list[dict], node_id: str | None) -> list[dict]:
    """The turns asked from one stop, oldest first."""
    if node_id is None:
        return []
    return [t for t in transcript if t.get("node_id") == node_id]


def pinned_turns(transcript: list[dict], node_id: str | None) -> list[dict]:
    """The turns the learner kept, for one stop (§11.2)."""
    return [t for t in turns_for_node(transcript, node_id) if t.get("pinned") is True]


def questions_asked(transcript: list[dict]) -> int:
    """How much of the cap has been spent.

    Every stored turn counts, including a `reveal`-adjacent one and an
    `out_of_scope` answer — each cost a model call. A turn that FAILED never
    reaches the transcript at all, which is what keeps the system's own outages
    off the learner's allowance.
    """
    return len(transcript)


def remaining(transcript: list[dict]) -> int:
    return max(0, TUTOR_QUESTION_CAP - questions_asked(transcript))


# ── signals (tutor.md §5.2) ───────────────────────────────────────────────────
#
# Every one of these is a fact about what happened, computed from persisted
# counters. None of them is a model's judgement about the learner, and that
# distinction is the whole of the tier-2 boundary: a signal may open an OFFER and
# may never move a state.


def heavily_scaffolded(node: "LearningNode") -> bool:
    """Was the question in front of this learner substantially scaffolded?"""
    return node.tutor_state.hints_used >= HEAVY_SCAFFOLD


def was_revealed(node: "LearningNode") -> bool:
    """Did the learner ask for, and receive, the answer to the current question?"""
    return node.tutor_state.revealed


def dwelling(node: "LearningNode") -> bool:
    """Has the learner spent an unusual number of turns on this one stop?"""
    return node.tutor_state.turns >= DWELLING_TURNS


def returning(node: "LearningNode", settled: bool) -> bool:
    """Are they asking about a stop they had already dealt with?

    `settled` is passed in rather than computed, because settlement is
    `graph.is_settled`'s question and importing it here would put a policy call
    inside the record layer.
    """
    return settled and node.tutor_state.turns >= RETURNING_TURNS


def assistance_summary(node: "LearningNode") -> dict:
    """The assistance record for an answer about to be graded (§6.4).

    Written onto the attempt by the endpoint, never by this module — recording an
    attempt is `graph.record_attempt`'s job and this is only the shape.
    """
    return {
        "hints": node.tutor_state.hints_used,
        "revealed": node.tutor_state.revealed,
    }
