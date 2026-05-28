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

from backend.pipeline.state import OnboardState


MODEL = "claude-haiku-4-5"
MAX_TOKENS = 512

Classification = Literal["understood", "partial", "confused", "off-topic"]

# How each classification updates the node. "off-topic" is intentionally absent
# — an answer that doesn't address the prompt leaves understanding_state alone.
# "confused" maps to "not-yet", which flips weak_spot via the graph's own logic.
_CLASSIFICATION_TO_STATE: dict[str, str] = {
    "understood": "understood",
    "partial": "partial",
    "confused": "not-yet",
}


class GraderOutput(BaseModel):
    classification: Classification
    rationale: str  # one sentence — for debugging, not shown to the user in v1


_SYSTEM_PROMPT = """\
You grade a developer's answer to a comprehension question about code.

You are given the question, a model answer, and the developer's response.
Classify the response as EXACTLY one of:
  understood — correct and substantial; they clearly grasp the idea
  partial    — partially correct; some grasp but with gaps or imprecision
  confused   — incorrect, or shows a real misunderstanding
  off-topic  — does not address the question (e.g. "I don't know", blank,
               or an unrelated answer)

Return a JSON object with exactly these keys:
  classification: one of "understood", "partial", "confused", "off-topic"
  rationale:      one short sentence explaining the call

Grade the understanding, not the wording. A correct idea in clumsy words is
"understood". Return ONLY the JSON object — no markdown fences, no preamble.
"""


def _build_user_content(prompt: str, expected_answer: str, user_response: str) -> str:
    return (
        f"Question:\n{prompt}\n\n"
        f"Model answer:\n{expected_answer}\n\n"
        f"Developer's response:\n{user_response}"
    )


def _parse_output(raw: str) -> GraderOutput:
    raw = raw.strip()
    if "```json" in raw:
        raw = raw.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in raw:
        parts = raw.split("```")
        if len(parts) >= 2:
            raw = parts[1]
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

    prompt = node.cached_lesson.get("prompt", "")
    expected = node.cached_lesson.get("expected_answer", "")
    user_content = _build_user_content(prompt, expected, user_response)

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
        output = GraderOutput(classification="partial", rationale="grading failed; defaulted to partial")

    _apply_grade(state, current_id, output.classification)
    state.last_grade = {"classification": output.classification, "rationale": output.rationale}
    return state


def _apply_grade(state: OnboardState, node_id: str, classification: str) -> None:
    # "off-topic" leaves understanding_state untouched — no grasp signal either
    # way. Everything else maps through _CLASSIFICATION_TO_STATE; "confused"
    # → "not-yet" trips weak_spot inside LearningGraph.mark_understanding.
    new_state = _CLASSIFICATION_TO_STATE.get(classification)
    if new_state is not None:
        state.graph.mark_understanding(node_id, new_state)
