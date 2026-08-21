# Learning history — what the learner did, and what the system did about it.
#
# M1 measured where the learner is. This records HOW THEY GOT THERE, which is
# what every later insight is computed from (learning-graph.md §4.1, §6.2).
#
# THE OWNERSHIP RULE THIS MODULE EXISTS TO ENFORCE
#
# Two different histories were about to be put in one place because one place
# already existed. They are separated here, by lifecycle rather than by
# convenience:
#
#   ATTEMPT-SCOPED     one learner answer, and the ONE response it earned.
#                      Caused by that answer, describes that answer, dies with
#                      it. Lives in the attempt dict (§18.9: a hint is not a peer
#                      of an answer, it is a property of the answer that caused
#                      it).
#
#   JOURNEY-SCOPED     something happened to the JOURNEY rather than to an
#                      answer. Affects many nodes, outlives the answer, and —
#                      decisively — `scope.shorten()` and `scope.deepen()` happen
#                      at `/session/{id}/scope` where THERE IS NO ATTEMPT AT ALL.
#                      A field that cannot be written for half its producers is
#                      in the wrong place. Lives in
#                      `LearningGraph.journey_events`.
#
# THIS CATEGORY WAS WIDENED, DELIBERATELY, AND HERE IS THE ARGUMENT
#
# It was called PLAN-SCOPED and defined as "the journey changed shape", which is
# what its first four kinds are. `jumped` is not: a jump moves the learner
# through the route without altering it. The category is now movement OR shape,
# for one reason — `/jump` was the only navigation act in the system that left no
# trace at all, while `/advance`'s skip stamped `user_override` and every scope
# change wrote an event here. A learner who jumped around all session was
# indistinguishable, afterwards, from one who walked the path.
#
# The alternative was a second list beside this one, holding a single kind and
# read by the same log for the same purpose. The lifecycle split this module
# exists to enforce is ATTEMPT vs JOURNEY, and a jump is unambiguously the second
# — it happens with no answer to hang from, which is the test stated below. So
# the boundary that matters is intact; only the narrower name for one side of it
# was wrong.
#
# The test that settles which is which: *could this have happened without a
# learner answering something?* A hint could not. A scope change could, and
# routinely does.
#
# THE `unknown` DISTINCTION, AND WHY IT IS STRUCTURAL
#
# Every attempt recorded before this milestone has no response record. That must
# read as **"we do not know what the system did"**, never as **"the system did
# nothing"** — the difference between an unmeasured session and a session where
# the learner needed no help. Getting this wrong would not produce an error; it
# would produce a plausible, confident, wrong intervention rate over the 40
# attempts already stored.
#
# So the accessors below return `None` for unknown rather than a default, and
# `instrumented` is the only supported way to build a denominator. A metric
# written against `intervention_of` cannot silently count a pre-M2 attempt,
# because `None` is not one of the action names it would be comparing against.

from __future__ import annotations

from datetime import datetime, timezone


# --- attempt kinds ------------------------------------------------------------

# An answer to the lesson's own question — the assessment of the objective.
ASSESSMENT = "assessment"
# An answer to a FRESH question asked about one gap (gap-model M6). Recorded so
# the two can never be pooled: a verification answer is evidence about a gap, not
# a second attempt at the objective, and averaging them would misreport both.
VERIFICATION = "verification"

# Absent on every pre-M2 attempt. Those are all assessments — verification did
# not exist when they were written — so this default is a fact about history
# rather than a guess.
DEFAULT_KIND = ASSESSMENT


# --- the response envelope ----------------------------------------------------

# The key whose PRESENCE means "this attempt was instrumented". `action` is
# always set when it is present, including `"none"`, which is what makes
# "the system deliberately did nothing" expressible and therefore distinct from
# "we have no record".
RESPONSE = "response"

ACTION = "action"
# Actions mirror `adaptation.Action` exactly. Not imported, to keep this module
# free of the policy: history records what happened, it does not decide.
ACTIONS = frozenset({"none", "hint", "reteach", "prerequisite", "followup"})

# An intervention the learner READ (as opposed to one that reshaped the graph).
ASSISTIVE_ACTIONS = frozenset({"hint", "reteach", "followup"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_response(action: str, **detail) -> dict:
    """The record of what the system did about one answer.

    `detail` carries only what the action actually produced — `text` for a hint
    or follow-up, `retaught` for a re-teach, `declined_reason` when remediation
    was considered and refused, `remediation_node_id` when a warm-up was spliced
    in. Absent keys mean the action did not produce that thing, which is why they
    are omitted rather than nulled.
    """
    return {ACTION: action, "at": _now(), **detail}


def is_instrumented(attempt: dict) -> bool:
    """Do we have a record of what the system did about this answer?

    False for every attempt written before this milestone. **This is the only
    correct denominator filter for any intervention metric.**
    """
    return isinstance(attempt.get(RESPONSE), dict)


def intervention_of(attempt: dict) -> str | None:
    """The action this answer earned, or None when unknown.

    `None` is deliberately not `"none"`. The first means "not recorded"; the
    second means "recorded, and the system chose to do nothing". A caller that
    conflates them reports pre-M2 sessions as help-free.
    """
    if not is_instrumented(attempt):
        return None
    action = attempt[RESPONSE].get(ACTION)
    return action if action in ACTIONS else None


def was_assisted(attempt: dict) -> bool | None:
    """Did the learner receive help in response to this answer? None if unknown."""
    action = intervention_of(attempt)
    if action is None:
        return None
    return action in ASSISTIVE_ACTIONS or action == "prerequisite"


def is_graded(attempt: dict) -> bool:
    """Did grading actually succeed, or is this the fallback verdict?

    A grading failure is recorded as `partial` with a fixed rationale, and is
    otherwise indistinguishable from a genuine partial answer — so it scores half
    in every measure that reads `understanding_state`.

    Absent means True, and that is deliberate: a pre-M2 attempt is *not known* to
    have failed grading, and treating unknown as failure would retroactively
    delete evidence from 40 stored answers. The unknown-vs-known distinction that
    matters for correctness is the intervention one above; here the conservative
    direction is to keep what was already counted.
    """
    return bool(attempt.get("graded", True))


def is_evidence(attempt: dict) -> bool:
    """Does this attempt say anything about whether the learner understood?

    Excludes two things, for different reasons:
      - `off-topic`, which the Grader itself refuses to let change
        `understanding_state`: it is evidence of neither understanding nor
        misunderstanding. A quarter of every attempt stored to date is one.
      - a FAILED GRADE, which is the system's error and not the learner's
        answer. Counting it as evidence attributes our outage to them.
    """
    return attempt.get("classification") != "off-topic" and is_graded(attempt)


def assessments(attempts: list[dict]) -> list[dict]:
    """Answers to the objective itself, excluding verification answers."""
    return [a for a in attempts if a.get("kind", DEFAULT_KIND) == ASSESSMENT]


def instrumented(attempts: list[dict]) -> list[dict]:
    """Attempts whose system response is known. The denominator, always."""
    return [a for a in attempts if is_instrumented(a)]


# --- plan-scoped history ------------------------------------------------------

# The journey changed shape. Deliberately NOT on an attempt — see the header.
PRUNE_AHEAD = "prune_ahead"
SCOPE_SHORTER = "scope_shorter"
SCOPE_DEEPER = "scope_deeper"
REMEDIATION_INSERTED = "remediation_inserted"
# The learner moved to a stop that is not the next one. The only kind here that
# does not change the journey's shape — see the header for why it lives here
# anyway. `nodes` is the stop landed on; `from_node_id` the one left behind, or
# absent when there was no current stop to leave.
JUMPED = "jumped"

JOURNEY_EVENT_KINDS = frozenset({
    PRUNE_AHEAD, SCOPE_SHORTER, SCOPE_DEEPER, REMEDIATION_INSERTED, JUMPED,
})

# Why the learner moved. `study` is an ordinary jump — they chose a stop and went
# to it. `resume` is the return offered by the arrival notice, and it is recorded
# distinctly because it is the OPPOSITE act: rejoining the route rather than
# leaving it, which is why it clears the notice instead of raising another one.
JUMP_STUDY = "study"
JUMP_RESUME = "resume"
JUMP_INTENTS = frozenset({JUMP_STUDY, JUMP_RESUME})


def new_journey_event(kind: str, *, nodes=None, cause=None, **detail) -> dict:
    """One change to the shape of the journey.

    `nodes`  the units this changed, by id — NOT a count. "3 units were demoted"
             cannot answer "which, and were they ever restored?", and M3 has to
             be able to explain a shrinking journey rather than only report it.
    `cause`  {node_id, attempt_index} when an answer triggered it; absent when
             the learner acted on the journey directly, which is exactly the case
             the attempt envelope could not represent.
    """
    event = {"kind": kind, "at": _now()}
    if nodes is not None:
        event["nodes"] = list(nodes)
    if cause is not None:
        event["cause"] = cause
    event.update(detail)
    return event
