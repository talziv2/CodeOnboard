# The learning-mode Tutor — one Haiku call over a prebuilt context.
#
# Runs when `mode.mode_for(node)` says EXPLAIN: nothing is outstanding, so the
# learner may ask freely and the answer may go as deep as the context allows.
#
# WHAT MAKES THIS NOT A CHATBOT, in three rules the prompt states and our code
# enforces afterwards:
#
#   1. IT KNOWS ONLY WHAT IT WAS GIVEN. No claim about the repository the context
#      does not support. Where it cannot see something, it says which part and
#      reports `out_of_scope` — which is a useful answer, not a failure.
#   2. IT CITES BY FILE AND SYMBOL, NEVER BY LINE. A line a model chose is exactly
#      the hallucinated range the project's grounding rule exists to prevent; our
#      code derives every range from `context.citable`.
#   3. IT PROPOSES, IT DOES NOT ACT. A suggestion is validated against the graph
#      by `suggest.py` and rendered as a control the learner presses.
#
# Same conventions as every other agent: client injected, errors appended to
# `state.errors`, NEVER RAISES. A broken Tutor must not cost the learner their
# session — and, specifically, must not spend their question allowance, which is
# why the endpoint only charges for a turn that actually got written.
#
# Haiku, per CLAUDE.md: this is the most loop-shaped call in the system.

from __future__ import annotations

import json
import os

import anthropic
from pydantic import BaseModel

from backend.agents.teaching.agent import _text_of
from backend.agents.tutor.context import ExplainContext
from backend.learning.tutor import ANSWERED, OUT_OF_SCOPE, SCOPES


MODEL = "claude-haiku-4-5"
# A deliberate cost ceiling rather than a guess. §10's per-question figures are
# computed from it, and "under 150 words" in the prompt is what makes it a limit
# the model aims at rather than one it hits.
MAX_TOKENS = 512

# What comes back when the call fails. An apology and nothing else: no citation to
# check, no suggestion to press, and `grounded=False` so the surface can mark it.
UNAVAILABLE = (
    "I couldn't work that out just now. Try again in a moment — nothing about "
    "your session has changed."
)


class Citation(BaseModel):
    """A place in the repository. **The model names it; our code locates it.**"""

    file: str
    symbol: str | None = None


class RawSuggestion(BaseModel):
    kind: str
    node_id: str | None = None
    gap_id: str | None = None


class TutorAnswer(BaseModel):
    text: str
    citations: list[Citation] = []
    scope: str = ANSWERED
    suggestion: RawSuggestion | None = None


_SYSTEM = """\
You are a tutor sitting beside a developer who is working through a guided tour of
ONE repository. They are reading a lesson and have asked you something about it.

Everything you know is in the context below. It was assembled for this learner,
this repository, this goal and this stop.

RULES, in priority order:

1. YOU KNOW ONLY WHAT IS BELOW. Make no claim about this repository that the
   context does not support. If the answer is not in there, say which part you
   cannot see and name the closest thing you can — then set
   scope: "out_of_scope". Asked about a different library, a different codebase,
   or programming in general, say you can only see this repository.

2. CITE BY NAMING A FILE AND A SYMBOL. Never write a line number: the system
   derives ranges itself, and a number you choose is a number you invented. A
   citation is `{"file": "requests/sessions.py", "symbol": "Session.send"}`.
   Cite only what the context actually showed you.

3. BE SHORT. Under 150 words. No headings. No bullet lists unless you are
   genuinely enumerating. This is a side panel, not a lesson — the lesson is
   already on their screen.

4. DO NOT TEACH THE NEXT STOP. Answer what was asked. If the real answer is the
   subject of a later stop on their journey, say so and name it rather than
   delivering it early.

5. YOU MAY PROPOSE ONE ACTION, and only from this list. Omit `suggestion`
   entirely unless it is clearly the right next thing — most answers should not
   carry one.
     {"kind": "reassess"}                  they seem ready for another go at this
                                           stop's objective
     {"kind": "verify",  "gap_id": "..."}  a misconception listed in their record
                                           is what is blocking them
     {"kind": "jump",    "node_id": "..."} the answer really lives at another stop
                                           on their journey
     {"kind": "deepen"}                    they want more than this journey
                                           currently includes
   You are PROPOSING. Nothing happens unless the learner presses it.

You are not a grader. Nothing the learner types to you is marked, and you must
never imply that it is.

Return a JSON object with these keys:
  text        your answer, markdown, under 150 words
  citations   a list of {file, symbol} — may be empty
  scope       "answered" or "out_of_scope"
  suggestion  omit, or one object from rule 5
Return ONLY the JSON object — no markdown fences, no preamble.
"""


def _parse(raw: str) -> TutorAnswer:
    """Tolerant of a fence the prompt asked for and did not get."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return TutorAnswer.model_validate(json.loads(text))


def ground_citations(
    citations: list[Citation], context: ExplainContext | object
) -> list[dict]:
    """Every citation resolved against what the context actually rendered.

    A citation that does not resolve **keeps its text and loses the citation** —
    the rule `briefing/agent.py` applies to `notes[].file`, for the same reason:
    the sentence was still worth reading, only the pointer was wrong.

    The range is OURS. `citable` was derived from the anchors the builder put on
    screen, so a hallucinated line number is not merely rejected, it is
    unexpressible — the model was never asked for one.

    Matching is on file, then on symbol when the model named one. A file-only
    match is allowed because a multi-anchor unit legitimately cites a file the
    learner is looking at without naming a symbol inside it.
    """
    citable = getattr(context, "citable", ()) or ()
    resolved: list[dict] = []
    seen: set[tuple] = set()
    for citation in citations:
        wanted_file = (citation.file or "").strip()
        wanted_symbol = (citation.symbol or "").strip()
        if not wanted_file:
            continue
        match = None
        for candidate in citable:
            if candidate.file != wanted_file:
                continue
            if wanted_symbol and candidate.symbol and candidate.symbol != wanted_symbol:
                continue
            match = candidate
            break
        if match is None:
            continue
        key = (match.file, match.symbol, match.line_start, match.line_end)
        if key in seen:
            continue
        seen.add(key)
        resolved.append(match.to_dict())
    return resolved


def _usage_of(response) -> dict:
    """Per-turn cost accounting, so §10's estimate is checkable rather than argued.

    A `cache_read_input_tokens` of zero across two questions on one stop means a
    silent invalidator got in — the block ordering broke, or something unsorted
    reached the prefix.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    return {
        key: value
        for key, value in (
            ("input_tokens", getattr(usage, "input_tokens", None)),
            ("output_tokens", getattr(usage, "output_tokens", None)),
            ("cache_read_input_tokens", getattr(usage, "cache_read_input_tokens", None)),
            ("cache_creation_input_tokens",
             getattr(usage, "cache_creation_input_tokens", None)),
        )
        if isinstance(value, int)
    }


def answer(
    question: str,
    context: ExplainContext,
    client: anthropic.Anthropic | None = None,
    errors: list[str] | None = None,
) -> dict:
    """One Haiku call. Returns the answer payload; never raises.

    `errors` mirrors `state.errors` without requiring an `OnboardState` — this
    agent has no pipeline to belong to, and taking a list keeps the failure
    reporting identical to every other agent's.
    """
    if client is None:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    user_content = (
        f"{context.as_prompt()}\n\n"
        "## What the learner just asked you\n"
        f"{question.strip()}"
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
        )
        output = _parse(_text_of(response))
    except Exception as e:
        if errors is not None:
            errors.append(f"tutor_explain: {e}")
        return {
            "text": UNAVAILABLE,
            "citations": [],
            "scope": ANSWERED,
            "suggestion": None,
            "grounded": False,
            "usage": {},
        }

    scope = output.scope if output.scope in SCOPES else ANSWERED
    # THE SOURCE WAS UNREADABLE, so nothing said about it is grounded. Reported as
    # a fact on the turn rather than corrected in the text: the context already
    # told the model to say it cannot see the file, and marking the turn is what
    # lets a surface show that without re-reading the prose.
    grounded = context.source_available
    if not grounded and scope == ANSWERED:
        scope = OUT_OF_SCOPE

    return {
        "text": output.text.strip(),
        "citations": ground_citations(output.citations, context),
        "scope": scope,
        "suggestion": output.suggestion.model_dump() if output.suggestion else None,
        "grounded": grounded,
        "usage": _usage_of(response),
    }
