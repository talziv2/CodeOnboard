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
    gap_kind: GapKind = "none"


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
  no_attempt                 — they did not try: "I don't know", blank, or an
                               answer about something else entirely. They need
                               a hint, not a diagnosis.
  missing_prerequisite       — the answer shows a foundation is genuinely
                               absent; something must be taught BEFORE this
                               node can land.
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
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        raw = response.content[0].text
        output = _parse_output(raw)
    except Exception as e:
        # Never block the session on a grading hiccup — assume partial.
        state.errors.append(f"grader_agent: classification failed, defaulting to partial: {e}")
        output = GraderOutput(classification="partial", rationale=_GRADING_FAILED)

    _apply_grade(state, current_id, output.classification)
    state.last_grade = {
        "classification": output.classification,
        "gap_kind": output.gap_kind,
        "rationale": output.rationale,
    }
    return state


def _apply_grade(state: OnboardState, node_id: str, classification: str) -> None:
    # "off-topic" leaves understanding_state untouched — no grasp signal either
    # way. Everything else maps through _CLASSIFICATION_TO_STATE; "confused"
    # → "failed" trips weak_spot inside LearningGraph.mark_understanding.
    new_state = _CLASSIFICATION_TO_STATE.get(classification)
    if new_state is not None:
        state.graph.mark_understanding(node_id, new_state)
