# What the system says back when an answer falls short.
#
# `backend/learning/adaptation.py` decides WHICH response a gap deserves — a
# deterministic table. This module writes what that response SAYS, which is
# judgement and belongs to a model.
#
# Three of them, one Haiku call each, none of which touches the graph:
#
#   HINT      for "I don't know". Scaffolds the question they were already
#             asked; never answers it.
#   RETEACH   for a confident misconception. Names the wrong model explicitly
#             and replaces the unit's cached lesson.
#   FOLLOWUP  for a right idea at the wrong altitude. One redirecting question.
#
# Prerequisite insertion is the fourth response and lives in the Mutator, where
# it always has — it is the only one that changes the graph.
#
# Same conventions as every other agent: client injected, errors appended to
# state.errors, never raises. A failed adaptation must never cost the grade that
# prompted it.

import json
import os

import anthropic
from pydantic import BaseModel

from backend.agents.teaching.agent import (
    MODEL,
    LessonOutput,
    _generate_lesson,
    _parse_output,
    _text_of,
    lesson_form,
)
from backend.learning.graph import LearningNode
from backend.pipeline.state import OnboardState


MAX_TOKENS = 1024


class Nudge(BaseModel):
    """A hint or a follow-up — one short piece of prose, no lesson rewrite."""

    text: str


_HINT_SYSTEM = """\
A developer was asked a question about code they are learning, and did not
attempt an answer — "I don't know", a blank, or something unrelated. They are
stuck, not wrong.

Write ONE short scaffold, under 60 words, that makes the question answerable.

  - Point at where in the shown code the answer lives, or restate the question
    in a smaller, more concrete form.
  - You may narrow it: "start with just the first line — what does it return?"
  - DO NOT answer it. A hint that contains the answer teaches nothing and
    wastes the only moment they were engaged.
  - Do not scold, do not reassure at length, do not explain why the question
    matters. They asked for a way in, not a preamble.

Return a JSON object with exactly one key:
  text: the scaffold
Return ONLY the JSON object — no markdown fences, no preamble.
"""

_FOLLOWUP_SYSTEM = """\
A developer answered a question about code they are learning. Their substance
is RIGHT but pitched at the wrong level — implementation detail where the
objective asked about responsibility, or a system-level gesture where the
objective asked for a specific mechanism.

Write ONE short redirecting question, under 50 words, that keeps what they got
right and moves them to the right altitude.

  - Acknowledge the correct part in a clause, not a paragraph.
  - Then ask the SAME objective again from the level it actually wants.
  - Do not answer it, and do not introduce new material.

Return a JSON object with exactly one key:
  text: the follow-up question
Return ONLY the JSON object — no markdown fences, no preamble.
"""

_RETEACH_SYSTEM = """\
You are re-teaching one unit to a developer who answered it with a CONFIDENT
MISCONCEPTION. They were not lost — they had a clear mental model and it was
wrong.

This is not the same lesson again. A developer who reasoned their way to a
wrong conclusion will reason their way there a second time unless the wrong
turn is named.

  - In `setup`, NAME THE MISCONCEPTION explicitly and say what makes it
    plausible — they had a reason, and treating it as carelessness is both
    wrong and insulting. Then point at what the code actually shows.
  - Your `prompt` must ask the objective again in a form that CANNOT be
    answered by the wrong model. If their misconception would still produce a
    passing answer, the question has not done its job.
  - `reveal` corrects the model directly: what they believed, what is true,
    and which detail in the shown code distinguishes them.
"""

_LESSON_KEYS = """
Produce a JSON object with exactly these keys:
  why_now, setup, prompt, reveal, takeaway, ownership, expected_answer
Do NOT emit "walkthrough" or "prompt_kind".
Return ONLY the JSON object — no markdown fences, no preamble.
"""


def _client(client: anthropic.Anthropic | None) -> anthropic.Anthropic:
    if client is not None:
        return client
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def _node_context(node: LearningNode, answer: str, rationale: str) -> str:
    lesson = node.cached_lesson or {}
    return (
        f"The objective they were meant to reach:\n{node.objective()}\n\n"
        f"The question they were asked:\n{lesson.get('prompt', '')}\n\n"
        f"What they wrote:\n{answer}\n\n"
        f"Why the grader marked it short:\n{rationale}\n\n"
        f"The material they were shown:\n{lesson.get('setup') or lesson.get('walkthrough', '')}"
    )


def _nudge(system: str, client, user_content: str) -> str:
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )
    raw = _text_of(response).strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else ""
    start = raw.find("{")
    if start < 0:
        raise ValueError("no JSON object found in response")
    decoded, _ = json.JSONDecoder().raw_decode(raw[start:])
    return Nudge(**decoded).text


def hint(
    state: OnboardState, node: LearningNode, answer: str, rationale: str,
    client: anthropic.Anthropic | None = None,
) -> str | None:
    """A way into the question they did not attempt. No graph change."""
    try:
        return _nudge(_HINT_SYSTEM, _client(client), _node_context(node, answer, rationale))
    except Exception as e:
        state.errors.append(f"adaptation: hint failed (non-fatal): {e}")
        return None


def followup(
    state: OnboardState, node: LearningNode, answer: str, rationale: str,
    client: anthropic.Anthropic | None = None,
) -> str | None:
    """The same objective, asked from the altitude it actually wants."""
    try:
        return _nudge(
            _FOLLOWUP_SYSTEM, _client(client), _node_context(node, answer, rationale)
        )
    except Exception as e:
        state.errors.append(f"adaptation: follow-up failed (non-fatal): {e}")
        return None


def reteach(
    state: OnboardState, node: LearningNode, answer: str, rationale: str,
    source: str, client: anthropic.Anthropic | None = None,
) -> LessonOutput | None:
    """Re-render this unit's lesson with the misconception named.

    Replaces `cached_lesson` — the corrected lesson is the lesson now, and a
    learner who returns should not meet the version that misled them. The
    attempt history keeps the record of what happened, which is where a record
    belongs.
    """
    user_content = (
        _node_context(node, answer, rationale)
        + f"\n\nThe source code for this unit:\n{source}\n"
        + _LESSON_KEYS
    )
    try:
        output = _generate_lesson(_client(client), user_content, _RETEACH_SYSTEM)
        output.prompt_kind = lesson_form(node)
        node.cached_lesson = output.model_dump()
        return output
    except Exception as e:
        state.errors.append(f"adaptation: re-teach failed (non-fatal): {e}")
        return None
