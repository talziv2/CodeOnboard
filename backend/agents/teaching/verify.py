# Verification — a FRESH question that closes a gap, or does not.
#
# `respond.py` writes what the system says when an answer falls short. This
# module writes the question that decides whether the correction landed, and it
# is deliberately a separate act with separate rules (learning-engine.md §18.7).
#
# What was wrong before this existed: after a hint, a follow-up or a re-teach,
# the frontend's "Try again" re-showed THE SAME PROMPT — after `reveal` had
# already given away the reasoning. A learner could pass by remembering the
# sentence they had just read. That is a memory check, and it was the only thing
# standing between "the system corrected me" and "I understand this".
#
# Three rules make this different from a lesson, and all three are load-bearing:
#
#   NO REVEAL.        A verification prompt carries the question and nothing
#                     else. Shipping the answer beside the question is exactly
#                     what made re-asking meaningless.
#   A NEW APPLICATION. Same objective clause, same diagnosed gap, DIFFERENT
#                     scenario. A paraphrase of the original question tests
#                     recall of the correction, not the understanding.
#   ONE GAP AT A TIME. §18.7's own argument: "a blanket question invites exactly
#                     the partial answer that would otherwise look like
#                     completion." Asking about three misconceptions at once lets
#                     an answer address one and appear to have addressed all
#                     three. Grading still looks at every open gap — but the
#                     QUESTION is aimed, so silence is visible.
#
# Same conventions as every other agent: client injected, errors appended to
# state.errors, never raises.

import json
import os
from collections.abc import Sequence
from datetime import datetime, timezone

import anthropic
from pydantic import BaseModel

from backend.agents.teaching.agent import MODEL, _text_of
from backend.learning.gaps import Gap
from backend.learning.graph import LearningNode
from backend.pipeline.state import OnboardState


MAX_TOKENS = 512


class VerificationPrompt(BaseModel):
    """A question, and the gaps it was built to test. Deliberately no answer.

    There is no `reveal`, no `expected_answer` and no `takeaway` — not omitted
    for brevity but excluded by design. The Grader marks a verification answer
    against the gap `claim`s themselves (which are false statements, so
    "does the answer still assert this?" is a sharper test than similarity to a
    model answer), and anything resembling an answer stored here would eventually
    be rendered next to the question by some future UI change.
    """

    question: str
    # The gap ids under test. Our code fills this in — the model is shown claims
    # and never ids, so it cannot mislabel what its own question tests.
    targets: list[str] = []


_SYSTEM = """\
A developer held a specific FALSE BELIEF about code they are learning. It has
since been corrected — they have read an explanation of why it was wrong.

Write ONE question that determines whether the correction actually landed.

THE QUESTION MUST BE A NEW APPLICATION OF THE SAME IDEA.
  - Do NOT restate the question they already answered. They have read the
    correct reasoning; asking again tests whether they remember reading it.
  - Instead, put the same idea in a DIFFERENT concrete situation: a different
    call site, a different sequence of operations, a different starting state,
    a change someone might make and its consequence.
  - The situation must be answerable from the source shown. Do not invent
    functions, files or behaviour that are not there.

THE FALSE BELIEF MUST BE FATAL TO IT.
  - A developer who STILL HOLDS the belief must get the question WRONG. Not
    "give a vaguer answer" — actually wrong.
  - A developer who has understood the correction must be able to answer it from
    the idea alone, without having memorised the explanation.
  - Test this before you answer: work out what someone holding the false belief
    would say. If that answer would pass, the question has not done its job and
    you must write a different one.

DO NOT GIVE ANYTHING AWAY.
  - Do not state the correct model in the question, and do not hint at it.
  - Do not mention that a misconception was diagnosed, quote it back, or say
    what they got wrong. The question stands on its own; a learner who reads it
    should not be able to infer the answer from how it is asked.
  - Ask for reasoning, not a yes/no or a term. "What happens to X, and why?"
    beats "Is X mutated?" — the second can be guessed.

Keep it under 80 words. One question, not a list of sub-questions.

Return a JSON object with exactly one key:
  question: the question
Return ONLY the JSON object — no markdown fences, no preamble.
"""


def _user_content(node: LearningNode, gaps: Sequence[Gap], source: str) -> str:
    lesson = node.cached_lesson or {}
    claims = "\n".join(f"  - {g.claim}" for g in gaps)
    parts = [
        f"The objective they must be able to reach:\n{node.objective()}",
        f"The FALSE BELIEF to test (they must not be able to answer while "
        f"holding it):\n{claims}",
    ]
    clause = " / ".join(g.objective_part.strip() for g in gaps if g.objective_part.strip())
    if clause:
        parts.append(f"The clause of the objective it violates:\n{clause}")
    if lesson.get("prompt"):
        # Given so it can be AVOIDED. Without it the model cannot tell whether
        # its "new application" is new.
        parts.append(
            f"The question they were already asked — DO NOT REUSE OR PARAPHRASE "
            f"IT:\n{lesson['prompt']}"
        )
    parts.append(f"The source code they can see:\n{source}")
    return "\n\n".join(parts)


def verify(
    state: OnboardState,
    node: LearningNode,
    gaps: Sequence[Gap],
    source: str,
    client: anthropic.Anthropic | None = None,
) -> VerificationPrompt | None:
    """A fresh question testing whether `gaps` have actually closed.

    Returns None on any failure, having appended to `state.errors` — a
    verification we could not generate must never be reported as one the learner
    failed. It also does not touch the gaps: this function asks, and
    `backend/agents/grader/verification.py` is the only place that answers.

    Refuses an empty gap list rather than inventing something to test. "Verify
    nothing" has no meaning, and a question generated without a target would be
    graded against the objective as a whole — which is the assessment the
    learner already took.
    """
    if not gaps:
        state.errors.append("verification: no gap to verify")
        return None
    if not source.strip():
        # The read-time grounding guarantee (§4.1.2), applied here: with no
        # source the model has only the claim, and it will invent a scenario to
        # test it in. An ungrounded question is worse than no question, because
        # failing it would record real evidence about imaginary code.
        state.errors.append("verification: no source to build a question from")
        return None

    if client is None:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_SYSTEM,
            messages=[{"role": "user", "content": _user_content(node, gaps, source)}],
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
            raise ValueError("verification prompt came back empty")
    except Exception as e:
        state.errors.append(f"verification: question generation failed: {e}")
        return None

    return VerificationPrompt(question=question, targets=[g.id for g in gaps])


def store(node: LearningNode, prompt: VerificationPrompt) -> dict:
    """Park the question on the node, awaiting an answer.

    In `gap_state`, never in `cached_lesson`: a re-teach replaces the cached
    lesson wholesale, and these two artifacts have different lifetimes (§18.7).
    """
    payload = {
        "question": prompt.question,
        "targets": list(prompt.targets),
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    node.gap_state.pending_verification = payload
    # A QUESTION THE LEARNER HAS NOT SEEN (tutor.md §4.2). The Tutor's hint
    # ladder is per question, so it resets here: carrying a spent ladder onto a
    # new question would deny hints on something nobody has had a hint about, and
    # carrying `revealed` would leave a fresh question already marked as spent.
    #
    # `turns` is deliberately NOT cleared — dwelling is a fact about the stop, not
    # about any one question.
    node.tutor_state.new_question()
    return payload
