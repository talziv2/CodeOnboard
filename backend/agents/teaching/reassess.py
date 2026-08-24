# Re-assessment — a FRESH question about the OBJECTIVE, after a shortfall.
#
# `verify.py` asks whether one diagnosed false belief has been corrected. This
# asks the larger question: can the learner now make the claim the unit exists to
# teach? Same act, one level up — and deliberately the same shape, because the
# shape is what makes a second question trustworthy.
#
# WHY THIS EXISTS AT ALL (learning-loop.md §3)
#
# The commonest shortfall in the system names no gap. An `off-topic` answer opens
# none by policy; a `confused` or `partial` answer whose Grader found no FALSE
# STATEMENT opens none either. Measured over the stored sessions: 27 of 34 real
# unmet stops have no open blocking gap. For all of them `/verify` has nothing to
# aim at, so before this there was no route from "fell short" back to
# "demonstrated" — the node was uncreditable for the rest of the session, whatever
# the learner did.
#
# THE RULE THAT SHAPES EVERYTHING HERE, and it is sharper than "ask something new"
#
#   The unit's own prompt is answerable exactly ONCE — before its `reveal` has
#   been shown. Every later assessment comes from a question that ships no answer.
#
# That is not a stylistic preference. Teaching's contract for `reveal` is "the
# explanation — now you may answer it", and `lessonView` opens it after ANY graded
# answer. So by the time a retry is offered, the answer to the unit's prompt is on
# screen one tab away — and a re-teach does not escape it either, since it
# regenerates the whole lesson and its new prompt arrives with a new `reveal` that
# answers it. Re-asking anything from `cached_lesson` is a memory check.
#
# WHAT ANCHORS THE SECOND QUESTION TO THE FIRST ONE'S KNOWLEDGE
#
# The decision gate rejected decomposing the objective (§3). What replaces it is
# `verify.py`'s own mechanism: name the thing under test, and give the same name
# to the generator and the grader. Here that is four inputs, and each rules out a
# specific way a "different question" could quietly become a different subject:
#
#   the objective     the marking standard, unchanged — so the Grader marks this
#                     answer by exactly the standard it marked the first one by
#   the questions
#   already asked     may not be repeated or paraphrased (M1 put these on record;
#                     before it, they were unrecoverable)
#   the shortfall     the previous answer and the Grader's rationale. The question
#                     must be one a learner still holding that shortfall gets
#                     WRONG — `verify.py`'s test, applied to a shortfall instead
#                     of to a named false belief
#   the source        grounded, or refused (§4.1.2)
#
# `probes` is returned and stored so coverage becomes auditable after the fact:
# what this question was actually aimed at, in one line. It is deliberately NOT a
# decomposition asserted up front — see §3, "the one thing borrowed".
#
# Same conventions as every other agent: client injected, errors appended to
# state.errors, never raises.

import json
import os
from datetime import datetime, timezone

import anthropic
from pydantic import BaseModel

from backend.agents.teaching.agent import MODEL, _text_of, lesson_form
from backend.learning import history
from backend.learning.graph import LearningNode
from backend.pipeline.state import OnboardState


MAX_TOKENS = 640


class ReassessmentPrompt(BaseModel):
    """A question, and what it was aimed at. Deliberately no answer.

    No `reveal`, no `expected_answer`, no `takeaway` — excluded by design rather
    than omitted for brevity, exactly as in `verify.VerificationPrompt`. The
    Grader marks this against the node's objective, which it already holds; an
    answer stored here would eventually be rendered beside the question by some
    later UI change, and then this would be a memory check too.
    """

    question: str
    # One line: which part of the claim this question requires. Recorded, never
    # enforced — it makes coverage measurable without asserting a decomposition.
    probes: str = ""


_SYSTEM = """\
A developer was asked to demonstrate one specific claim about code they are
learning, and fell short. They have since read the explanation.

Write ONE new question that determines whether they can make that claim NOW.

THE MARKING STANDARD IS THE OBJECTIVE, AND IT DOES NOT CHANGE.
  - Your question must be answerable ONLY by someone who can make the
    objective's claim. It is being marked against that same objective, so a
    question about something adjacent produces a verdict about the wrong thing.
  - Aim at the SUBSTANCE of the claim, not at a detail beside it.

IT MUST BE A NEW QUESTION, NOT A REPHRASING.
  - You are shown every question this developer has already been asked here. Do
    not reuse or paraphrase any of them.
  - They have READ THE EXPLANATION for those questions. Anything answerable by
    repeating what they read tests memory, which is exactly what this replaces.
  - Put the claim in a DIFFERENT concrete situation: a different call site, a
    different starting state, a change someone might make and its consequence, a
    decision they would have to justify.
  - The situation must be answerable from the source shown. Do not invent
    functions, files or behaviour that are not there.

THE EARLIER SHORTFALL MUST BE FATAL TO IT.
  - You are shown what they answered and why it fell short. A developer who
    still has that specific gap must get this question WRONG — not vaguer,
    actually wrong.
  - Test this before you answer: work out what someone with that shortfall would
    say. If it would pass, the question has not done its job; write a different
    one.

DO NOT GIVE ANYTHING AWAY.
  - Do not state the claim in the question and do not hint at it.
  - Do not mention that they got something wrong, quote their answer back, or
    describe what was missing.
  - Ask for reasoning, not a yes/no or a term.

Keep it under 90 words. One question, not a list of sub-questions.

Return a JSON object with exactly these keys:
  question: the question
  probes:   one short line naming which part of the claim this question
            requires. This is a record of what you aimed at, for later review —
            it is never shown to the developer.
Return ONLY the JSON object — no markdown fences, no preamble.
"""


def _asked_before(node: LearningNode) -> list[str]:
    """Every question this node has already put, newest last, deduplicated.

    Read from the ATTEMPT RECORD rather than from `cached_lesson`, which is the
    whole reason M1 came first: a re-teach replaces the cached lesson, so the
    prompt a learner actually answered three attempts ago is not there any more.
    The current prompt is included too — it may never have been answered, and it
    is still a question we must not re-ask.
    """
    asked: list[str] = []
    for attempt in node.attempts:
        text = history.question_of(attempt)
        if text and text not in asked:
            asked.append(text)
    current = (node.cached_lesson or {}).get("prompt")
    if current and current.strip() and current not in asked:
        asked.append(current.strip())
    return asked


def _shortfall(node: LearningNode) -> tuple[str, str]:
    """The latest assessment that fell short: what they wrote, and why it missed.

    Assessments only — a verification answer is evidence about one gap, and
    treating it as the shortfall would aim this question at a diagnosis the
    objective was never marked against.

    Returns empty strings when there is nothing on record, which is a legitimate
    state (a pre-M1 session, or one graded before the field existed). The prompt
    handles it by simply having less to work with, rather than the caller
    refusing: a fresh question about the objective is still better than none.
    """
    for attempt in reversed(history.assessments(node.attempts)):
        if attempt.get("classification") in ("understood", ""):
            continue
        return attempt.get("answer", ""), attempt.get("rationale", "")
    return "", ""


def _user_content(node: LearningNode, source: str) -> str:
    parts = [
        f"The objective they must be able to make — THE MARKING STANDARD:\n"
        f"{node.objective()}"
    ]
    asked = _asked_before(node)
    if asked:
        listed = "\n".join(f"  {i}. {q}" for i, q in enumerate(asked, 1))
        parts.append(
            "Questions they have ALREADY been asked here, and have already read "
            "the explanation for — DO NOT REUSE OR PARAPHRASE ANY OF THEM:\n"
            + listed
        )
    answer, rationale = _shortfall(node)
    if answer:
        parts.append(f"What they wrote last time:\n{answer}")
    if rationale:
        parts.append(
            f"Why it fell short — the shortfall this question must be FATAL to:\n"
            f"{rationale}"
        )
    # The unit's own question form, so a re-assessment does not silently become a
    # different KIND of question. Which shape a question takes is decided in code
    # from the unit's `kind`, never by the model (`_FORM_BY_KIND`).
    parts.append(f"The question form to use:\n{lesson_form(node)}")
    parts.append(f"The source code they can see:\n{source}")
    return "\n\n".join(parts)


def reassess(
    state: OnboardState,
    node: LearningNode,
    source: str,
    client: anthropic.Anthropic | None = None,
) -> ReassessmentPrompt | None:
    """A fresh objective-scoped question, or None having appended to state.errors.

    Returns None rather than raising, and a re-assessment we could not generate
    must never be reported as one the learner failed.

    Refuses without source for the read-time grounding reason (§4.1.2): with only
    the objective the model will invent a plausible scenario, and failing an
    imaginary question would record real evidence about imaginary code. This is
    the same refusal `verify` makes, and it matters more here — this answer is an
    ordinary assessment and moves `understanding_state`.
    """
    if not node.objective().strip():
        state.errors.append("reassessment: node has no objective to assess")
        return None
    if not source.strip():
        state.errors.append("reassessment: no source to build a question from")
        return None

    if client is None:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_SYSTEM,
            messages=[{"role": "user", "content": _user_content(node, source)}],
        )
        raw = _text_of(response).strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else ""
        start = raw.find("{")
        if start < 0:
            raise ValueError("no JSON object found in response")
        decoded, _ = json.JSONDecoder().raw_decode(raw[start:])
        question = str(decoded.get("question") or "").strip()
        if not question:
            raise ValueError("re-assessment prompt came back empty")
    except Exception as e:
        state.errors.append(f"reassessment: question generation failed: {e}")
        return None

    return ReassessmentPrompt(
        question=question, probes=str(decoded.get("probes") or "").strip()
    )


def store(node: LearningNode, prompt: ReassessmentPrompt) -> dict:
    """Park the question on the node and CHARGE it.

    Spent on issue, not on answer: an unanswered question has still been asked,
    and a learner who could refresh their way to an unlimited supply of fresh
    questions would turn the measure from mastery into persistence. Same rule as
    `pending_verification`, and the caller checks the cap before calling here.
    """
    payload = {
        "question": prompt.question,
        "probes": prompt.probes,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    node.gap_state.pending_reassessment = payload
    node.gap_state.reassessments += 1
    return payload
