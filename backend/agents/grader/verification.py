# Grading a verification answer — the ONLY producer of `verified`.
#
# `agent.py` grades an assessment answer: how far did it fall short, and why.
# This grades a different act, and asks a different question: of the gaps still
# open on this node, which does this answer DEMONSTRATE the learner no longer
# holds? (learning-engine.md §18.7, §18.16.2)
#
# The rule that shapes everything here:
#
#   SILENCE NEVER CLOSES A GAP.
#
# §18.7 calls it "the single most important rule in §18": a gap is closed only by
# evidence that it is closed, never by absence of evidence. An answer that is
# correct about A and says nothing about B closes A and leaves B open. So the
# model is asked to return a verdict PER GAP, keyed by an id we supplied, and
# anything it does not vouch for stays open by default rather than by inference.
#
# Two things this module deliberately does NOT do:
#
#   - It does not touch `classification` or `understanding_state`. A verification
#     answer is evidence about specific false beliefs, not a re-assessment of the
#     objective. Whether the NODE is understood is derived (M7) from the latest
#     assessment plus the gap list, and this only moves the second half.
#   - It does not decide what to do next. That is `decide_all`.

import json
import os
from collections.abc import Sequence

import anthropic
from pydantic import BaseModel

from backend.agents.grader.agent import MODEL, GapOut
from backend.learning.gaps import GAP_KINDS, Gap, objective_key
from backend.learning.graph import LearningNode
from backend.pipeline.state import OnboardState


MAX_TOKENS = 768


class GapVerdict(BaseModel):
    """One gap, and whether this answer showed the learner no longer holds it."""

    gap_id: str
    resolved: bool
    # One clause on what in the answer decided it. Surfaced to the learner, so
    # it has to read as a reason rather than a verdict.
    rationale: str = ""


class VerificationOutput(BaseModel):
    verdicts: list[GapVerdict] = []
    # A verification answer can reveal a NEW false belief — the learner has let
    # go of the old one and picked up another. Recorded like any other detection
    # (M2/M3), so remediation can address it instead of it being lost because it
    # arrived during the wrong kind of call.
    gaps: list[GapOut] = []
    rationale: str = ""


_SYSTEM = """\
A developer previously held one or more FALSE BELIEFS about code they are
learning. Each was explained to them, and they have now answered a fresh
question designed to test whether the correction landed.

You are given the objective, the question, the developer's answer, and the
OUTSTANDING FALSE BELIEFS, each with an id.

For EACH id you are given, decide whether this answer DEMONSTRATES that the
developer no longer holds that belief.

  resolved: true   — the answer shows they now hold the correct model. They do
                     not have to use particular words, and they do not have to
                     mention the old belief at all. What is required is that the
                     reasoning they DO show is incompatible with holding it.
  resolved: false   — anything else. Use this when the answer still shows the
                     belief, when it is too vague to tell, when it dodges, AND
                     WHEN IT SIMPLY DOES NOT TOUCH THAT BELIEF AT ALL.

THE LAST CASE IS THE ONE THAT MATTERS MOST. An answer that is excellent about
one belief and silent about another resolves ONLY the one it addressed. Do not
credit a belief because the rest of the answer was strong, because the developer
seems to understand the area, or because it would be reasonable to assume they
also got that part right. No evidence is not evidence. Return a verdict for
every id you were given, and return `false` when you were shown nothing.

Do NOT invent ids. Return a verdict for each id you were given and no others.

If the answer reveals a NEW false belief — one not in the list — report it in
`gaps`, with:
  kind:           one of "missing_prerequisite", "wrong_model",
                  "right_idea_wrong_altitude"
  claim:          the new false statement, in one sentence, as a paraphrase of
                  what the developer actually asserted
  objective_part: which clause of the objective it violates
  foundational:   true if it must be corrected before this node can land
Only a statement they MADE and that is FALSE. An omission is not a gap, and a
correct-but-incomplete answer contains none. Return `gaps: []` normally.

Return a JSON object with exactly these keys:
  verdicts:  [{gap_id, resolved, rationale}]  — one per id you were given
  gaps:      []  — new false beliefs, usually empty
  rationale: one short sentence on the answer overall
Return ONLY the JSON object — no markdown fences, no preamble.
"""


def _user_content(
    node: LearningNode, question: str, answer: str, gaps: Sequence[Gap]
) -> str:
    listed = "\n".join(
        f"  id={g.id}\n    belief: {g.claim}"
        + (f"\n    violates: {g.objective_part.strip()}" if g.objective_part.strip() else "")
        for g in gaps
    )
    return (
        f"The objective:\n{node.objective()}\n\n"
        f"OUTSTANDING FALSE BELIEFS (return a verdict for each id):\n{listed}\n\n"
        f"The verification question they were asked:\n{question}\n\n"
        f"Their answer:\n{answer}"
    )


def _parse(raw: str) -> VerificationOutput:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else ""
    start = raw.find("{")
    if start < 0:
        raise ValueError("no JSON object found in response")
    decoded, _ = json.JSONDecoder().raw_decode(raw[start:])
    return VerificationOutput(**decoded)


def grade_verification(
    state: OnboardState,
    node: LearningNode,
    answer: str,
    client: anthropic.Anthropic | None = None,
) -> dict:
    """Grade the node's pending verification answer and apply the outcome.

    Returns a summary: `{resolved: [ids], unresolved: [ids], new_gaps: n,
    rationale: str}`. Mutates the gaps — this is the one place `verified` is
    written — and clears `pending_verification`, because the question has now
    been spent whatever the outcome.

    On any failure NOTHING is resolved and no attempt is charged. A grading
    hiccup must not cost the learner a verification budget they never used, and
    it must certainly not close a gap.
    """
    pending = node.gap_state.pending_verification or {}
    question = str(pending.get("question") or "")
    if not question:
        state.errors.append("verification: no pending verification on this node")
        return {"resolved": [], "unresolved": [], "new_gaps": 0, "rationale": ""}

    # Graded against every gap still open, not only the ones the question was
    # aimed at: an answer can positively demonstrate the correct model for a
    # neighbouring belief, and that IS evidence. What it cannot do is close one
    # by saying nothing — hence a verdict per id, defaulting to unresolved.
    open_gaps = [g for g in node.gaps if g.is_open]
    if not open_gaps:
        node.gap_state.pending_verification = None
        state.errors.append("verification: no open gaps left to verify")
        return {"resolved": [], "unresolved": [], "new_gaps": 0, "rationale": ""}

    if client is None:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_SYSTEM,
            messages=[{
                "role": "user",
                "content": _user_content(node, question, answer, open_gaps),
            }],
        )
        output = _parse(response.content[0].text)
    except Exception as e:
        # Leave everything exactly as it was, pending question included, so the
        # learner can answer again without having spent an attempt.
        state.errors.append(f"verification: grading failed, nothing resolved: {e}")
        return {"resolved": [], "unresolved": [], "new_gaps": 0,
                "rationale": "", "failed": True}

    by_id = {g.id: g for g in open_gaps}
    # The index the attempt for this answer will take, for the audit link — the
    # same convention `_record_gaps` uses.
    attempt_index = len(node.attempts)

    resolved: list[str] = []
    for verdict in output.verdicts:
        gap = by_id.get(verdict.gap_id)
        if gap is None:
            # An id we did not supply. Dropped whole, exactly as in a re-grade
            # (§3.2): a verdict about a gap we cannot identify is not something
            # to guess at, least of all when the guess could close one.
            continue
        if verdict.resolved:
            gap.mark_verified(attempt_index)
            resolved.append(gap.id)

    # Everything the question was AIMED at and did not close costs an attempt.
    # Scoped to the targets rather than to every open gap: charging a gap the
    # question never asked about would burn its budget for someone else's
    # question, and the caps exist to stop the system proposing forever, not to
    # run the learner out of chances they were never given.
    targets = set(pending.get("targets") or [])
    unresolved: list[str] = []
    for gap in open_gaps:
        if gap.id in resolved:
            continue
        unresolved.append(gap.id)
        if gap.id in targets:
            gap.record_failed_verification()

    _record_new_gaps(node, output, attempt_index)

    # Spent either way: a verification question is asked once. Re-showing it
    # after a wrong answer would be the same "Try again" defect this replaces.
    node.gap_state.pending_verification = None

    return {
        "resolved": resolved,
        "unresolved": unresolved,
        "new_gaps": len(node.gaps) - len(open_gaps),
        "rationale": output.rationale,
    }


def _record_new_gaps(node: LearningNode, output: VerificationOutput, origin: int) -> None:
    """Open any genuinely new false belief the verification answer revealed.

    Same filtering as an assessment grade: a kind outside `GAP_KINDS` is dropped
    rather than coerced, and one unusable entry costs that entry alone.
    """
    key = objective_key(node.objective())
    for reported in output.gaps:
        if reported.kind not in GAP_KINDS:
            continue
        try:
            node.gap_state.gaps.append(Gap.create(
                reported.kind,
                reported.claim,
                objective_part=reported.objective_part,
                foundational=reported.foundational,
                objective_key=key,
                origin_attempt=origin,
            ))
        except ValueError:
            continue
