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
from collections.abc import Sequence

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
from backend.learning.gaps import Gap
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
You are re-teaching one unit to a developer who answered it with one or more
CONFIDENT MISCONCEPTIONS. They were not lost — they had a clear mental model
and parts of it were wrong.

This is not the same lesson again. A developer who reasoned their way to a
wrong conclusion will reason their way there a second time unless the wrong
turn is named.

The user message lists the MISCONCEPTIONS TO CORRECT. Every one of them was
detected in their answer, and every one must be corrected in this lesson.

  - In `setup`, NAME EACH MISCONCEPTION explicitly and say what makes it
    plausible — they had a reason, and treating it as carelessness is both
    wrong and insulting. Then point at what the code actually shows.
  - Your `prompt` must ask the objective again in a form that CANNOT be
    answered while still holding ANY of them. If any one of the listed
    misconceptions would still produce a passing answer, the question has not
    done its job.
  - `reveal` corrects each one directly: what they believed, what is true, and
    which detail in the shown code distinguishes them.

WHEN THERE IS MORE THAN ONE, WRITE ONE LESSON, NOT SEVERAL STACKED TOGETHER.
This is the difference between re-teaching and issuing a list of corrections:

  - DO NOT STRUCTURE THE LESSON AROUND THE LIST YOU WERE GIVEN. Never write
    "Misconception 1 / 2 / 3". Never give each one its own labelled section,
    heading or dedicated paragraph. Never follow the order they are listed in.
    That order is the order they happened to be detected in; mirroring it turns
    a lesson into a checklist.
  - FIND THE ROOT FIRST: the single wrong idea that produced several of these
    conclusions. If there is one, IT is the lesson — state it, correct it, and
    let the individual claims fall out of it as consequences. Naming the root
    and then enumerating anyway is the failure this rule exists to prevent.
  - Where they genuinely are independent, order them so each builds on the last
    and join them in prose. Never manufacture a shared root that is not there;
    a false unifying story is worse than none.
  - Never drop one because it did not fit the narrative.

LENGTH DOES NOT SCALE WITH THE NUMBER OF MISCONCEPTIONS. The whole response
stays under 600 words, with `setup` and `reveal` together under 300, whether
there is one misconception or four. More to correct means LESS room for
re-explaining what they already had right — cut that, never the corrections.
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


def _gap_block(gaps: Sequence[Gap]) -> str:
    """The misconceptions this response must correct, named one by one.

    These are the M4 `Plan`'s `targets` — gaps the policy SELECTED for this
    response — never "every gap on the node". A deferred gap is real and still
    open, but it is not what is being taught right now, and listing it here
    would have the lesson correct something the plan did not choose.

    Empty for a node with no gap records (every flag-off session, and every
    session written before the gap model), which is what keeps those prompts
    byte-identical to the ones they sent before M5.
    """
    if not gaps:
        return ""
    lines = []
    for i, gap in enumerate(gaps, 1):
        line = f"  {i}. {gap.claim}"
        if gap.objective_part.strip():
            line += f"\n     (violates: {gap.objective_part.strip()})"
        lines.append(line)
    header = (
        "The MISCONCEPTION to correct:" if len(gaps) == 1
        else f"The {len(gaps)} MISCONCEPTIONS to correct — all of them, in one lesson:"
    )
    return f"{header}\n" + "\n".join(lines) + "\n\n"


def _node_context(
    node: LearningNode, answer: str, rationale: str,
    gaps: Sequence[Gap] = (),
) -> str:
    lesson = node.cached_lesson or {}
    return (
        f"The objective they were meant to reach:\n{node.objective()}\n\n"
        f"The question they were asked:\n{lesson.get('prompt', '')}\n\n"
        f"What they wrote:\n{answer}\n\n"
        f"Why the grader marked it short:\n{rationale}\n\n"
        f"{_gap_block(gaps)}"
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
    gaps: Sequence[Gap] = (),
) -> str | None:
    """A way into the question they did not attempt. No graph change.

    `gaps` is always empty in practice — a hint answers `no_attempt`, which by
    policy opens no gaps at all. It is accepted so all three responses have one
    signature, and passed through rather than dropped so that a future policy
    change cannot make this the one path that silently ignores its targets.
    """
    try:
        return _nudge(
            _HINT_SYSTEM, _client(client), _node_context(node, answer, rationale, gaps)
        )
    except Exception as e:
        state.errors.append(f"adaptation: hint failed (non-fatal): {e}")
        return None


def followup(
    state: OnboardState, node: LearningNode, answer: str, rationale: str,
    client: anthropic.Anthropic | None = None,
    gaps: Sequence[Gap] = (),
) -> str | None:
    """The same objective, asked from the altitude it actually wants."""
    try:
        return _nudge(
            _FOLLOWUP_SYSTEM, _client(client),
            _node_context(node, answer, rationale, gaps),
        )
    except Exception as e:
        state.errors.append(f"adaptation: follow-up failed (non-fatal): {e}")
        return None


def reteach(
    state: OnboardState, node: LearningNode, answer: str, rationale: str,
    source: str, client: anthropic.Anthropic | None = None,
    gaps: Sequence[Gap] = (),
) -> LessonOutput | None:
    """Re-render this unit's lesson with every selected misconception named.

    Replaces `cached_lesson` — the corrected lesson is the lesson now, and a
    learner who returns should not meet the version that misled them. The
    attempt history keeps the record of what happened, which is where a record
    belongs.

    `gaps` are the M4 `Plan`'s targets: every open gap of the leading kind, so
    one lesson corrects all of them (§18.5, "one mutation, many corrections").
    Empty is the pre-M5 shape and produces the pre-M5 prompt.
    """
    user_content = (
        _node_context(node, answer, rationale, gaps)
        + f"\n\nThe source code for this unit:\n{source}\n"
        + _LESSON_KEYS
    )
    try:
        output = _generate_lesson(_client(client), user_content, _RETEACH_SYSTEM)
        output.prompt_kind = lesson_form(node)
        node.cached_lesson = output.model_dump()
        # A re-teach installs a prompt built so it CANNOT be answered while
        # still holding the diagnosed misconception — a genuinely new question
        # (`history.SOURCE_RETEACH`), so the Tutor's hint ladder resets with it.
        node.tutor_state.new_question()
        return output
    except Exception as e:
        state.errors.append(f"adaptation: re-teach failed (non-fatal): {e}")
        return None
