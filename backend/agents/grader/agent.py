# Grader Agent — classifies a developer's free-text answer to a lesson prompt.
#
# The Teaching Agent ends each lesson with an active-learning prompt and a model
# answer (`expected_answer`). When the user responds, the Grader decides how well
# they did and records it on the node. That signal drives the understanding graph
# — and, from Part 6 on, drives the Mentor's mutator (confusion → prerequisite).
#
# Entry point:
#   run(state, user_response, client) → grades the current node's prompt against
#       user_response, updates the node's understanding_state / weak_spot, and
#       writes {classification, rationale} to state.last_grade.
#
# Graceful by design: a parse failure falls back to "partial" rather than
# blocking the session. One Haiku call — classification is cheap.

import json
import os
from typing import Literal

import anthropic
from pydantic import BaseModel

from backend.learning.flags import gaps_enabled
from backend.learning.gaps import (
    GAP_KINDS,
    Gap,
    dominant_kind,
    objective_key,
)
from backend.learning.graph import LearningNode
from backend.pipeline.state import OnboardState


MODEL = "claude-haiku-4-5"
MAX_TOKENS = 512

Classification = Literal["understood", "partial", "confused", "off-topic"]
GapKind = Literal[
    "none",
    "no_attempt",
    "missing_prerequisite",
    "wrong_model",
    "right_idea_wrong_altitude",
]

# How each classification updates the node.
# An off-topic answer is deliberately ABSENT from this map, not mapped to
# anything: it is evidence of neither understanding nor misunderstanding, so the
# node keeps whatever state it already had. Mapping it to "failed" (as this table
# did) marked the node failed, tripped `weak_spot`, and made it eligible for a
# prerequisite insertion — all on the strength of the user typing something
# unrelated. `_apply_grade` skips any classification missing from here.
_CLASSIFICATION_TO_STATE: dict[str, str] = {
    "understood": "understood",
    "partial": "partial",
    "confused": "failed",
}


class GapOut(BaseModel):
    """One misconception, as the model reports it (gap-model.md M2).

    Deliberately NOT the stored `Gap`. The model reports what it can see in the
    answer; our code decides what that becomes. Two fields are absent for that
    reason and their absence is the design:

      - `id` — identity is ours. `Gap.create` mints it, so the model cannot
        re-open a closed gap or merge two distinct ones by naming an id (M3
        shows it ids and asks it to reference them; it never invents one).
      - `blocking` — a pure function of `kind`, computed by `Gap.is_blocking`.
        A model-assigned severity would be the invented `depth` dial again.

    `kind` is a plain `str`, not the `GapKind` enum, on purpose: an unknown or
    disallowed kind must cost us that one gap, not the whole verdict. Typed
    strictly, a single stray value would fail the parse and throw away a
    perfectly good classification.
    """

    kind: str
    claim: str  # the misconception in one sentence, in the learner's own terms
    objective_part: str = ""  # the clause of the objective it violates
    # Observed, not decisive: "does a foundation look genuinely absent?"
    foundational: bool = False


class GraderOutput(BaseModel):
    classification: Classification
    rationale: str  # one sentence — surfaced in the UI
    # WHY the answer fell short, not just how far (learning-engine.md §8.3).
    # The verdict alone cannot choose a response: "I don't know" and a confident
    # misconception are both wrong, and want a hint and a correction
    # respectively — not the same prerequisite insertion. B5 branches on this;
    # B1 records it, so the signal exists before anything depends on it.
    #
    # Defaulted because it is additive: a model that omits it, and every attempt
    # recorded before this field existed, read as an unclassified gap.
    #
    # RETAINED, and from M2 onward DERIVED: when `gaps` is non-empty this is
    # overwritten with the highest-precedence gap's kind (§18.5). With exactly
    # one gap that is the gap's own kind, which is what the single-gap Grader
    # reported — so `/respond`, the attempt record and the Mutator's `Diagnosis`
    # all keep working untouched.
    gap_kind: GapKind = "none"
    # Every distinct misconception the answer contains, not just the dominant
    # one. This is the whole point of the phase: one answer can hold several
    # independent false claims, and before this the scalar above could carry
    # exactly one of them (§18.1).
    #
    # Defaulted, so an omission is not a parse failure and every pre-M2 payload
    # still parses.
    gaps: list[GapOut] = []


# The rationale is surfaced in the UI, so even this fallback — used when the
# call never reached the model — has to read as a sentence.
_GRADING_FAILED = "grading failed; defaulted to partial"


_SYSTEM_PROMPT = """\
You grade a developer's answer to a system-level question about one node in
their understanding graph of a codebase. The node represents a concept the
developer needs to grasp to reason about, critique, or safely change this
system — not a piece of code they need to be able to write.

You are given:
  - the LEARNING OBJECTIVE — the claim this node exists to make the developer
    able to make. THIS IS THE MARKING STANDARD.
  - the node's title and concept tags (the tags dictate the KIND of
    understanding to check)
  - the active-learning question they were asked
  - a calibration reference: one way a developer who reached the objective
    might have phrased it
  - the developer's actual response

MARK AGAINST THE OBJECTIVE, NOT AGAINST THE REFERENCE. The reference shows you
roughly what reaching the objective sounds like; it is one phrasing among many,
written by the teacher rather than by the planner who designed this developer's
path. An answer that makes the objective's claim in completely different words,
covering none of the reference's specific examples, is "understood". An answer
that echoes the reference's wording without making the claim is not.

Classify the response as EXACTLY one of:
  understood — they can make the objective's claim; correct and substantial
  partial    — partially there; some grasp but with gaps or imprecision
  confused   — incorrect, or shows a real misunderstanding
  off-topic  — does not address the question (e.g. "I don't know", blank,
               or an unrelated answer)

Then say WHY the answer fell short, so the system can respond to this
developer's actual difficulty instead of treating every wrong answer the same.
Return `gap_kind` as EXACTLY one of:
  none                       — nothing fell short (use this with "understood")
  no_attempt                 — they did not try AND gave nothing to work with:
                               blank, a bare "I don't know", or an answer about
                               something else entirely. They need a hint, not a
                               diagnosis.
  missing_prerequisite       — a foundation this node builds on is genuinely
                               absent; something must be taught BEFORE this
                               node can land. This INCLUDES declining to answer
                               while NAMING the foundation they lack ("I can't
                               follow this, I don't know what a decorator is").
                               A bare "I don't know" is no_attempt; one that
                               says what is missing is a diagnosis, and the
                               thing they named is what to teach next. This does
                               NOT make it an attempt: classify such an answer
                               exactly as you would any other non-answer.
                               gap_kind records WHY they fell short, never how
                               well they did.
  wrong_model                — they answered confidently with an incorrect
                               mental model. The misconception itself is the
                               thing to correct.
  right_idea_wrong_altitude  — the substance is right but pitched at the wrong
                               level: implementation detail where the objective
                               asked for responsibility, or vice versa.

Return a JSON object with exactly these keys:
  classification: one of "understood", "partial", "confused", "off-topic"
  gap_kind:       one of "none", "no_attempt", "missing_prerequisite",
                  "wrong_model", "right_idea_wrong_altitude"
  rationale:      one short sentence explaining the call

Rubric by dominant concept tag (pick the first tag from this vocabulary that
appears in the node's tags; otherwise use the "other" rubric):
  architecture     — did they name the layer's responsibility or boundary —
                     what this part of the system owns and what it does NOT
                     own — rather than just describing its code?
  flow             — did they identify the order of operations and where
                     data moves through the system, not just trace function
                     calls line by line?
  extension_point  — did they identify WHERE and HOW the system is meant to
                     be extended (the contract, the seam, what a new
                     extension must provide and what it can rely on)?
  risk             — did they identify what can break, the invariant at
                     stake, or the unsafe assumption a change might violate?
  test_coverage    — did they identify what IS or IS NOT guarded by tests,
                     or which class of regression the coverage catches?
  component        — for this one tag, implementation-level detail (specific
                     functions, attributes, return values) IS the learning
                     objective and may legitimately be required for credit.
  other            — did they grasp the lesson's central idea, expressed at
                     the altitude of the prompt?

A correct system-level answer is "understood" even when it does not cite
specific line numbers, function names, or low-level implementation details —
UNLESS the dominant tag is `component`, in which case those details may be
the point. Grade the understanding, not the wording. A correct idea in
clumsy words is "understood". Return ONLY the JSON object — no markdown
fences, no preamble.
"""


# APPENDED to `_SYSTEM_PROMPT` when CODEONBOARD_GAPS=1, never woven into it.
#
# Two reasons it is a separate block rather than an edit. First, the flag-off
# prompt stays BYTE-IDENTICAL to the pre-M2 one, so "flag off changes nothing"
# is true by construction rather than by review. Second, the calibration gate
# (the 48-case evaluation, re-run flag-on) is then measuring exactly one
# difference.
#
# It amends the key list above deliberately: `classification`, `gap_kind` and
# `rationale` keep their meaning, and `gaps` is added alongside them.
_GAPS_ADDENDUM = """\

ADDITIONALLY, add one more key to the JSON object:
  gaps: an array of the FALSE STATEMENTS the developer actually made.

FIRST, decide `classification`, `gap_kind` and `rationale` exactly as you would
without this section. This list does not change any of them. It records what
was wrong in the answer; it does not re-grade it.

AN EMPTY `gaps` LIST IS NOT EVIDENCE THAT THE ANSWER WAS A NON-ANSWER. Finding
no false statement is the normal case, including for answers that fall well
short: an answer can be entirely accurate about the code and still miss the
objective's altitude, and that is `partial` with `right_idea_wrong_altitude`,
NOT "off-topic". Reserve "off-topic" for an answer that is genuinely about
something else.

A GAP IS A STATEMENT THE DEVELOPER MADE THAT IS FALSE.

The test, applied to every entry before you include it: can you point at
something the developer asserted and say "this is not true"? If not, it is not
a gap and it does not go in the list.

THESE ARE NOT GAPS. Most answers that fall short contain none of them:
  - Something the developer did not mention. An omission is not a false
    statement. "The developer does not mention X", "no explanation of Y", "did
    not identify Z", "does not describe the consequence" — NONE of these are
    gaps, however important X, Y or Z are. Their absence is already reflected
    in the classification.
  - A statement that is CORRECT but incomplete, vague, or thinner than the
    objective wanted. If what they said is true, it is not a gap.
  - The answer being pitched at the wrong level, in general. That is
    `gap_kind`. It becomes a gap only if a specific thing they said is wrong.

MOST ANSWERS HAVE ZERO OR ONE GAP. An answer that is merely incomplete, thin or
unfocused has ZERO. Return two or more only when the developer made two
separately false statements — and then it is important that you return them
all, because each needs correcting on its own.

Each entry has:
  kind:           one of "missing_prerequisite", "wrong_model",
                  "right_idea_wrong_altitude", chosen for THIS statement:
                  missing_prerequisite      — what they said reveals a false
                                              belief about a foundation this
                                              node builds on. NOT "a foundation
                                              went unmentioned".
                  wrong_model               — they stated confidently how
                                              something works, and it does not
                                              work that way.
                  right_idea_wrong_altitude — what they said is true of the
                                              implementation but false as a
                                              statement about responsibility,
                                              or the reverse.
  claim:          the false statement, in ONE sentence, as a paraphrase of what
                  the developer actually asserted. "child path_cost and depth
                  are filled in later by the search algorithm" is a claim: it is
                  something they said, and it is wrong. "confusion about Node
                  construction" is a topic. "the developer does not explain
                  expand()" is an omission. Only the first belongs here.
  objective_part: which clause of the LEARNING OBJECTIVE this statement violates
  foundational:   true if this false belief must be corrected BEFORE this node
                  can land; false otherwise

Two more rules:

  - TWO FALSE STATEMENTS ABOUT DIFFERENT THINGS ARE TWO GAPS EVEN WHEN THEY
    SHARE A `kind`. Do not merge them because both are "wrong_model", and do
    not merge them because they are in the same sentence. They are separate if
    correcting one would leave the other standing. One false statement restated
    in different words is ONE gap.
  - An answer containing no false statement gets `gaps: []`. That includes a
    correct answer, a thin one, and one that declines to try.

`gaps` AND `gap_kind` ANSWER DIFFERENT QUESTIONS, and they are allowed to
diverge. `gap_kind` says why the answer fell short; `gaps` lists false
statements. An answer can fall short without containing one, and the categories
above keep their meanings unchanged — a `missing_prerequisite` answer whose
developer simply lacks a foundation has made no false statement, and gets
`gaps: []`.

Do NOT return an id for a gap, and do NOT return whether it is blocking. Those
are not yours to assign.
"""


def _system_prompt() -> str:
    """The prompt for this call. Flag-off it is the pre-M2 prompt, unchanged."""
    return _SYSTEM_PROMPT + _GAPS_ADDENDUM if gaps_enabled() else _SYSTEM_PROMPT


def _build_user_content(node: LearningNode, user_response: str) -> str:
    lesson = node.cached_lesson or {}
    tags = ", ".join(node.concept_tags) if node.concept_tags else "(none)"
    objective = node.objective() or "(none stated — mark against the question)"
    return (
        f"LEARNING OBJECTIVE (the marking standard):\n{objective}\n\n"
        f"Node title:\n{node.title}\n\n"
        f"Concept tags:\n{tags}\n\n"
        f"Question:\n{lesson.get('prompt', '')}\n\n"
        f"Calibration reference (one phrasing, NOT the standard):\n"
        f"{lesson.get('expected_answer', '')}\n\n"
        f"Developer's response:\n{user_response}"
    )


def _parse_output(raw: str) -> GraderOutput:
    # Leading fence only. Cutting at the closing fence truncates a payload whose
    # own strings contain one — a rationale quoting the user's fenced answer is
    # exactly that case. `raw_decode` ends the object without help.
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else ""
    start = raw.find("{")
    if start < 0:
        raise ValueError("no JSON object found in response")
    decoded, _ = json.JSONDecoder().raw_decode(raw[start:])
    return GraderOutput(**decoded)


def run(
    state: OnboardState,
    user_response: str,
    client: anthropic.Anthropic | None = None,
) -> OnboardState:
    if client is None:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    if state.graph is None:
        state.errors.append("grader_agent: graph missing")
        return state

    current_id = state.graph.current_node_id
    if current_id is None or current_id not in state.graph.nodes:
        state.errors.append("grader_agent: no current node to grade")
        return state

    node = state.graph.nodes[current_id]
    if not node.cached_lesson:
        state.errors.append("grader_agent: current node has no lesson to grade against")
        return state

    user_content = _build_user_content(node, user_response)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_system_prompt(),
            messages=[{"role": "user", "content": user_content}],
        )
        raw = response.content[0].text
        output = _parse_output(raw)
    except Exception as e:
        # Never block the session on a grading hiccup — assume partial.
        state.errors.append(f"grader_agent: classification failed, defaulting to partial: {e}")
        output = GraderOutput(classification="partial", rationale=_GRADING_FAILED)

    # Flag-off, the model was never asked for gaps and anything it volunteered is
    # ignored: the whole path below is skipped, so the pre-M2 behaviour is exact
    # rather than merely equivalent.
    if gaps_enabled():
        _record_gaps(node, output)

    _apply_grade(state, current_id, output.classification)
    state.last_grade = {
        "classification": output.classification,
        "gap_kind": output.gap_kind,
        "rationale": output.rationale,
    }
    return state


def _record_gaps(node: LearningNode, output: GraderOutput) -> None:
    """Mint the reported misconceptions onto the node, and derive `gap_kind`.

    Two policy rules are enforced here rather than trusted to the prompt, because
    both have a failure mode that outlives the answer that caused it:

      - An `off-topic` answer opens NO gaps, whatever the model listed. "I don't
        know" earning a blocking gap is the F2 defect one layer up — a sticky
        penalty for declining to guess (§18.16 LQ9).
      - A kind outside `GAP_KINDS` is dropped, not coerced. `no_attempt` and
        `none` are not misconceptions, and an unrecognised value is not something
        to guess at.

    Everything survivable is survived: one bad entry costs that entry, never the
    grade. Gaps are appended, and M2 has no re-grade identity yet, so a second
    answer on the same node can duplicate a gap — bounded, measured and closed
    by M3, which is where the model is shown the open ids.
    """
    if output.classification == "off-topic":
        return

    reported = [g for g in output.gaps if g.kind in GAP_KINDS]
    if not reported:
        # Leave the model's scalar alone. This is the pre-M2 shape — including
        # `no_attempt`, which has no gap to derive from and must not be erased.
        return

    key = objective_key(node.objective())
    # The caller records the attempt for this answer immediately after grading,
    # so the index it will take is the current length. Recorded rather than
    # computed later because `origin_attempt` is the audit link between a gap and
    # the answer that opened it; a gap minted without a grading call in flight
    # simply points one past the end, which reads as "no recorded answer".
    origin = len(node.attempts)

    minted: list[Gap] = []
    for reported_gap in reported:
        try:
            minted.append(Gap.create(
                reported_gap.kind,
                reported_gap.claim,
                objective_part=reported_gap.objective_part,
                foundational=reported_gap.foundational,
                objective_key=key,
                origin_attempt=origin,
            ))
        except ValueError:
            # A claim we cannot open a gap for (empty text, refused kind). One
            # gap lost; the classification and the others stand.
            continue

    if not minted:
        return

    node.gap_state.gaps.extend(minted)

    # DERIVED, not taken from the model: the highest-precedence gap decides the
    # scalar. With exactly one gap this equals what the single-gap Grader
    # returned, which is the M2 compatibility invariant.
    #
    # Derived from THIS answer's gaps, not from every gap open on the node. The
    # scalar is carried into the attempt record and into the Mutator's
    # `Diagnosis`, both of which describe one answer; letting a gap left by an
    # earlier attempt decide it would make the history say something the answer
    # did not. Arbitrating over the full open set is M4's `decide_all`, which is
    # a different question asked at a different moment.
    output.gap_kind = dominant_kind(minted)


def _apply_grade(state: OnboardState, node_id: str, classification: str) -> None:
    # "off-topic" leaves understanding_state untouched — no grasp signal either
    # way. Everything else maps through _CLASSIFICATION_TO_STATE; "confused"
    # → "failed" trips weak_spot inside LearningGraph.mark_understanding.
    new_state = _CLASSIFICATION_TO_STATE.get(classification)
    if new_state is not None:
        state.graph.mark_understanding(node_id, new_state)
