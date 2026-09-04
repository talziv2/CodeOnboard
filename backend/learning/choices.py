# Deterministic grading of a multiple-choice SELECTION.
#
# The decision this module holds: when a learner PICKS an option rather than
# typing, the option's own verdict — `correct` / `partial` / `wrong`, assigned by
# the question's author at generation time — decides the classification. It is
# NOT re-graded against the objective.
#
# The defect that decision prevents: "picked the right option, still marked
# partial". The Grader is calibrated for a written paragraph; a single-phrase
# option is structurally thinner than that whatever it says, so a correct option
# graded as free text lands at `partial` for being incomplete rather than wrong.
# A coherent multiple choice already knows which option is correct — grading the
# pick against that is honest, and it is the only way "pick the correct answer →
# pass" can hold.
#
# A TYPED answer never reaches here. `api.py` routes to this only on an EXACT
# match between the submitted text and one of the options the question shipped;
# anything else goes to `run_grader` exactly as before.

_VERDICT_TO_CLASSIFICATION: dict[str, str] = {
    "correct": "understood",
    "partial": "partial",
    "wrong": "confused",
}

# What the attempt records as the Grader's rationale would-have-been. Short and
# factual: the learner chose from a fixed set, and this says which kind.
RATIONALE: dict[str, str] = {
    "correct": "Selected the option that fully states the objective's claim.",
    "partial": "Selected an option that gets the main idea but leaves part of the claim out.",
    "wrong": "Selected an option that contains a definite error about the code.",
}


def classification_for_choice(verdict: str) -> str | None:
    """`understood` / `partial` / `confused` for a `correct` / `partial` / `wrong`
    option verdict, or None for an unrecognised verdict (grade it the normal way).
    """
    return _VERDICT_TO_CLASSIFICATION.get(verdict)
