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

# How each classification updates the node.
# "confused" and "off-topic" both map to "failed" — the user didn't demonstrate understanding.
_CLASSIFICATION_TO_STATE: dict[str, str] = {
    "understood": "understood",
    "partial": "partial",
    "confused": "failed",
    "off-topic": "failed",
}


class GraderOutput(BaseModel):
    classification: Classification
    rationale: str  # one sentence — for debugging, not shown to the user in v1


# The rationale is surfaced in the UI, so even this fallback — used when the
# call never reached the model — has to read as a sentence.
_GRADING_FAILED = "grading failed; defaulted to partial"


_SYSTEM_PROMPT = """\
You grade a developer's answer to a system-level question about one node in
their understanding graph of a codebase. The node represents a concept the
developer needs to grasp to reason about, critique, or safely change this
system — not a piece of code they need to be able to write.

You are given:
  - the node's title (its learning objective)
  - the node's concept tags (which dictate the kind of understanding to check)
  - what the node intends the developer to take away
  - the active-learning question they were asked
  - a model answer (what a developer who understood this node would say)
  - the developer's actual response

Classify the response as EXACTLY one of:
  understood — correct and substantial; they clearly grasp the idea
  partial    — partially correct; some grasp but with gaps or imprecision
  confused   — incorrect, or shows a real misunderstanding
  off-topic  — does not address the question (e.g. "I don't know", blank,
               or an unrelated answer)

Return a JSON object with exactly these keys:
  classification: one of "understood", "partial", "confused", "off-topic"
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
    brief = node.lesson_brief or {}
    tags = ", ".join(node.concept_tags) if node.concept_tags else "(none)"
    takeaway = brief.get("understand") or "(none provided)"
    return (
        f"Node title:\n{node.title}\n\n"
        f"Concept tags:\n{tags}\n\n"
        f"What the developer should take away from this node:\n{takeaway}\n\n"
        f"Question:\n{lesson.get('prompt', '')}\n\n"
        f"Model answer:\n{lesson.get('expected_answer', '')}\n\n"
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
    state.last_grade = {"classification": output.classification, "rationale": output.rationale}
    return state


def _apply_grade(state: OnboardState, node_id: str, classification: str) -> None:
    # "off-topic" leaves understanding_state untouched — no grasp signal either
    # way. Everything else maps through _CLASSIFICATION_TO_STATE; "confused"
    # → "failed" trips weak_spot inside LearningGraph.mark_understanding.
    new_state = _CLASSIFICATION_TO_STATE.get(classification)
    if new_state is not None:
        state.graph.mark_understanding(node_id, new_state)
