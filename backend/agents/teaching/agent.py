# Teaching Agent — expands one learning-graph node into the actual lesson.
#
# Where the Mentor produces a *brief* (one-sentence why / understand), the
# Teaching Agent produces the *lesson* the user reads: a walkthrough plus one
# active-learning prompt. Runs once per node visit; one Haiku call per lesson.
#
# Entry point:
#   run(state, client) → renders the lesson for state.graph.current_node_id,
#                        writes it to node.cached_lesson AND state.current_lesson.
#
# Caching: if the node already has a cached_lesson (a prior visit), reuse it —
# no LLM call. Regeneration on demand is a Part 4 concern (a refresh flag).
#
# Mirrors the other agents: client injected, errors appended to state.errors,
# never raises.

import json
import os
import random
from pathlib import Path
from typing import Literal

import anthropic
from pydantic import BaseModel, field_validator

from backend.learning.graph import LearningGraph, LearningNode
from backend.pipeline.state import OnboardState
from backend.learning.graph import understanding_of
from backend.repo import dossier_context, dossier_store, structure
from backend.repo.skeleton import build_skeleton


MODEL = "claude-haiku-4-5"
# Walkthroughs are the longest prose in the system. 2048 was too tight — a long
# lesson would get truncated mid-JSON-string ("Unterminated string" on parse).
# Match the Mentor's budget so the JSON always closes.
MAX_TOKENS = 8192



# The question forms a lesson can take. Chosen by OUR code from the unit's
# `kind`, never by the model — deriving the form from the kind is the mechanism
# that ends "one locked pedagogical form" (learning-engine.md L7, §7.2).
PromptKind = Literal[
    "predict-then-reveal",  # what does this do? — the original, and the fallback
    "compare",              # what belongs here, and what deliberately does not?
    "predict-next",         # given this call, where does control go, and why?
    "blast-radius",         # what breaks if this changes?
    "locate",               # where would you add X, and what must it provide?
    "explain-back",         # tie these together at system level
    "critique",             # here is a plausible change — what is wrong with it?
]

# kind → form. An unmapped kind falls back to the original form, which is
# well-tuned and correct for "explain this piece" (LR5).
_FORM_BY_KIND: dict[str, PromptKind] = {
    "architecture": "compare",
    "flow": "predict-next",
    "component": "predict-then-reveal",
    # The AI-critique form (§7.4). `risk` units are where it fits best and where
    # it is most reliably generatable: the unit already names an invariant, so
    # there is a concrete thing for a plausible change to violate. Critiquing a
    # specific broken change subsumes "what breaks if this changes?" and cannot
    # be answered from the walkthrough's wording, which `blast-radius` sometimes
    # could.
    #
    # DELIBERATELY ONE KIND. This is the first implementation of a form that has
    # to invent a flaw, which is a harder generation task than any other form
    # asks for; widening it before it has been seen on real repositories would be
    # LR5's "eight forms, each worse than the one good one". Reverting is this
    # single dict entry.
    "risk": "critique",
    "extension_point": "locate",
    "synthesis": "explain-back",
    # A test guards against a class of regression; asking which class is a
    # prediction about the code shown, so the original form fits. What makes
    # the lesson different is the FRAMING block, not the shape of the question.
    "test_coverage": "predict-then-reveal",
}
_DEFAULT_FORM: PromptKind = "predict-then-reveal"

# The forms whose answer is a single statable claim, so a four-option rendering
# of the prompt stays faithful to it. `critique` (name the flaw and what it
# breaks) and `explain-back` (connect several units at system level) have no
# one-phrase answer — a multiple-choice version would be a different, easier
# exercise — so they never carry options however the model responds. Empty
# `choices` is valid for every form; this only bounds where a NON-empty list is
# allowed to survive. Deciding this here rather than in the prompt is the same
# move as `_FORM_BY_KIND`: the policy is testable code, not a sentence a model
# may drift from.
_CHOICE_FORMS: frozenset[str] = frozenset({
    "predict-then-reveal",
    "compare",
    "predict-next",
    "blast-radius",
    "locate",
})

# What each form asks for, injected into the user turn for the chosen one only.
# The model is never shown the other five: a menu invites blending.
_FORM_BRIEF: dict[str, str] = {
    "predict-then-reveal": (
        "Ask the developer to PREDICT what this code does or returns, before "
        "your explanation gives it away. Answerable from the code shown."
    ),
    "compare": (
        "Ask the developer to DELINEATE: what belongs to this part, and what "
        "deliberately does NOT — the responsibility it holds versus the ones it "
        "refuses. A correct answer names both sides of the line."
    ),
    "predict-next": (
        "Ask the developer to PREDICT WHERE CONTROL GOES next from a specific "
        "point in the path, and why. A correct answer names the destination and "
        "the reason it is that one, not merely the next function alphabetically."
    ),
    # Retained and reachable: it is the one-word revert for `risk`, and remains
    # correct for any kind later mapped to it.
    "blast-radius": (
        "Ask the developer what BREAKS if the invariant is violated or the code "
        "changes. A correct answer names a consequence somewhere else in the "
        "system, not a restatement of what the code does."
    ),
    "critique": (
        "SHOW THE DEVELOPER A PLAUSIBLE BUT FLAWED CHANGE to this repository, and "
        "ask what is wrong with it.\n"
        "\n"
        "  Write the change as a short concrete diff or replacement snippet "
        "inside the `prompt`, in a fenced code block, using THIS repository's "
        "real names — the actual functions, attributes and types visible in the "
        "code you were shown. Then ask: what is wrong with this change, and what "
        "would it break?\n"
        "\n"
        "  THE FLAW MUST BE REPOSITORY-SPECIFIC. It has to violate something this "
        "system actually guarantees — an invariant, a contract, an ownership "
        "boundary, an ordering requirement, a caching or lifecycle rule. A "
        "developer who has read this code can catch it; a competent stranger who "
        "has not, cannot.\n"
        "\n"
        "  NOT a style, naming, typo, formatting or generic-best-practice "
        "problem. Not a missing null check or an unused import. If the flaw would "
        "be caught by a linter, or by anyone reading the diff without knowing "
        "this codebase, you have written the wrong exercise.\n"
        "\n"
        "  THE CHANGE MUST LOOK REASONABLE. It should be the kind of thing an AI "
        "assistant or a competent newcomer would confidently produce: it reads as "
        "a sensible simplification, optimisation or feature addition. A change "
        "that is obviously wrong on its face teaches nothing.\n"
        "\n"
        "  ANSWERABLE FROM WHAT THEY HAVE BEEN TAUGHT. The flaw must be "
        "detectable from the code shown in this unit plus the units they have "
        "already understood — never from a part of the system they have not met. "
        "If catching it needs knowledge this lesson has not given them, choose a "
        "different flaw.\n"
        "\n"
        "  A correct answer names WHAT the change breaks and WHY — the guarantee "
        "it violates — and that answer must be the objective's claim in applied "
        "form. If a developer could reach the objective and still not spot this "
        "flaw, the exercise is testing something other than the objective."
    ),
    "locate": (
        "Ask the developer WHERE they would add a specific new capability, and "
        "what their addition must provide to satisfy the contract. A correct "
        "answer names the seam and its obligations."
    ),
    "explain-back": (
        "Ask the developer to CONNECT the units they have already learned into "
        "one claim at system level. Introduce no new code. A correct answer is "
        "about relationships between parts, not about any single part."
    ),
}


def _normalize_choices(raw: object) -> list[str]:
    """Exactly four distinct, non-empty options — or none.

    One malformed field costs only the options, never the lesson — the same
    reason `GapOut.kind` is a plain `str`. A list that is not four clean,
    distinct strings is discarded whole rather than repaired: a three-option or
    duplicate-laden question is a worse artefact than the plain text prompt it
    would replace. Runs as a `mode="before"` validator so even a non-list value
    from the model is coerced to `[]` rather than failing the parse of an
    OPTIONAL field.
    """
    if not isinstance(raw, list):
        return []
    cleaned = [c.strip() for c in raw if isinstance(c, str) and c.strip()]
    if len(cleaned) != 4 or len(set(cleaned)) != 4:
        return []
    return cleaned


def _normalize_verdicts(choices: list[str], raw: object) -> dict[str, str]:
    """One verdict per option — exactly one `correct`, one `partial`, two `wrong`.

    The learner's PICK is graded by this, not re-graded against the objective
    (`learning/choices.py`), so it must be exactly one clean correct answer or
    nothing: a map that does not cover all four options, or has zero / two
    `correct`, is discarded, and the caller then drops the options. Without a
    trustworthy verdict map a multiple choice is back to "any pick might be
    partial", which is the whole thing this feature exists to stop.
    """
    if not choices or not isinstance(raw, dict):
        return {}
    cleaned = {
        str(k).strip(): str(v).strip().lower()
        for k, v in raw.items()
        if str(k).strip() in choices and str(v).strip().lower() in {"correct", "partial", "wrong"}
    }
    if set(cleaned) != set(choices):
        return {}
    counts = sorted(cleaned.values())
    if counts != ["correct", "partial", "wrong", "wrong"]:
        return {}
    return cleaned


class LessonOutput(BaseModel):
    # The active-learning halves. `setup` frames the code WITHOUT answering the
    # prompt; `reveal` is the explanation, shown only after the developer has
    # answered. Splitting them is what makes the active-learning claim true —
    # before this the prompt asked for a prediction while the full explanation
    # sat above it on screen (L8, §7.3).
    setup: str = ""
    prompt: str        # the active-learning question
    reveal: str = ""
    # One line connecting to the unit just finished, so the path reads as a path.
    why_now: str = ""
    # The objective restated as something to remember.
    takeaway: str = ""
    # What to hold yourself here versus what you can safely delegate to an
    # assistant (LP5). Lesson content, not node metadata — LD4 keeps it off the
    # node; nothing aggregates it yet.
    ownership: str = ""
    expected_answer: str  # a calibration reference for the Grader, not the standard
    # Set by our code from the unit's kind after parsing; a value the model
    # supplies is overwritten.
    prompt_kind: PromptKind = _DEFAULT_FORM
    # A four-option rendering of `prompt`, so the learner can answer by picking
    # OR by typing — the choice of input is theirs, the marking is the same
    # either way. Required for every form in `_CHOICE_FORMS` and empty for the
    # rest (`critique`, `explain-back` — no one-phrase answer); `_choices_directive`
    # tells the model which, and `run` re-applies the split after the form is
    # set. Empty is also every lesson taught before choices existed, and a
    # degraded fallback lesson. One correct option a developer who reached the
    # objective would recognise, three plausible and wrong for a nameable
    # reason. The option text is graded against the OBJECTIVE exactly as typed
    # text is (D4) — this is not an answer key and the Grader is never told
    # which option is right. `_normalize_choices` drops anything that is not
    # four clean, distinct strings, because one bad field must cost only the
    # options and never the lesson.
    choices: list[str] = []
    # One verdict per option: `correct` / `partial` / `wrong`. Server-side ONLY —
    # `api.py` strips it before any lesson reaches the browser. When the learner
    # PICKS an option, `learning/choices.py` maps its verdict straight to a
    # classification instead of re-grading a one-phrase option against the
    # objective (which is what made a correct pick land at `partial`). A TYPED
    # answer is unaffected — it still goes to the Grader. Empty when the model
    # did not return a clean one-correct/one-partial/two-wrong map, and `run`
    # then drops `choices` too: a multiple choice with no known-correct option
    # is worse than a text box.
    choice_verdicts: dict[str, str] = {}
    # Kept, and synthesized from setup + reveal when the model did not write one.
    # Every pre-B4 cached lesson has this and nothing else, and the current UI
    # renders only this — so it stays the compatibility surface until B6 teaches
    # the panel to use the two halves (§12).
    walkthrough: str = ""

    @field_validator("choices", mode="before")
    @classmethod
    def _clean_choices(cls, v: object) -> list[str]:
        return _normalize_choices(v)


def lesson_form(node: LearningNode) -> PromptKind:
    """The question form for this unit, from its kind.

    `kind` leads `concept_tags` on objective-first graphs, and older graphs have
    only tags — so the first canonical tag is read either way, and anything
    unrecognised falls back to the original form.
    """
    brief = node.lesson_brief or {}
    kind = brief.get("kind")
    if kind in _FORM_BY_KIND:
        return _FORM_BY_KIND[kind]
    for tag in node.concept_tags:
        if tag in _FORM_BY_KIND:
            return _FORM_BY_KIND[tag]
    return _DEFAULT_FORM


_SYSTEM_PROMPT = """\
You are a patient programming mentor guiding a developer through one specific
piece of an unfamiliar Python codebase. You are given:
  - the developer's profile (experience level, familiarity with THIS codebase,
    background — known languages/frameworks)
  - their overall goal and the depth they requested
  - what they already understand (so you don't re-explain it)
  - the LEARNING OBJECTIVE for this lesson (see below)
  - a "lesson brief": why this piece matters and what they should take away
  - the actual source code for this piece
  - system context: how this piece connects to the rest of the codebase
  - the node's concept tags (frame your walkthrough around the dominant tag)

THE OBJECTIVE IS YOUR BRIEF. It is the claim the developer should be able to
make, in their own words, when the lesson ends — written by the planner who
designed their whole path, and the same claim their answer will be marked
against. Build exactly that claim. If the code shown would support a more
interesting lesson than the objective asks for, you still build the objective:
the path depends on this node delivering what the next ones assume. Teach
whatever the objective requires and no more.

CRITICAL: Your ENTIRE response must be under 600 words. Be very concise.

THE DEVELOPER ANSWERS BEFORE THEY SEE THE EXPLANATION. `setup` and `prompt` are
shown first; `reveal` appears only after they have committed to an answer. So:

  NOTHING IN `setup` MAY ANSWER THE PROMPT. If a developer could read `setup`
  and produce the expected answer without thinking, the lesson has taught them
  nothing and you have wasted the one moment where they were engaged.

Produce a JSON object with exactly these keys:
  why_now:         ONE short sentence connecting this unit to the one they just
                   finished. If this is their first unit, say what the path is
                   about to build instead. If the user turn says this unit is a
                   WARM-UP, connect it to the stop it unblocks instead — the
                   developer did not arrive here by finishing the previous unit,
                   they arrived because they got stuck, and telling them "now that
                   you know <earlier unit>" describes a journey they did not take.
                   No preamble, no "in this lesson".
  setup:           markdown. Frame the code and orient the developer — what they
                   are looking at, what to attend to, what question it is about
                   to answer. WITHOUT answering the prompt below.
  prompt:          ONE active-learning question, in the FORM named in the user
                   content under "PROMPT FORM". Answering it well must require
                   the objective's claim, not a detail beside it.
  reveal:          markdown. The explanation — now you may answer it. Reference
                   key identifiers only; no exhaustive walkthrough.
  takeaway:        ONE or TWO sentences: the objective restated as something to
                   remember. Not a summary of the code — the claim itself, in a
                   form that survives forgetting the details.
  ownership:       ONE sentence naming what the developer must hold THEMSELVES
                   here, and what they could safely delegate to an AI assistant
                   while still being able to supervise the result. Be specific
                   to this unit. Judgement, boundaries and invariants are
                   usually theirs to hold; mechanical detail usually is not.
  expected_answer: a concise model answer to your prompt — one way a developer
                   who reached the objective might phrase it. This is a
                   calibration reference for the grader, not the marking
                   standard: the objective is what gets marked.
  choices:         A JSON array of strings. The "CHOICES" line in the user
                   content says which of two things to return:
                     - EXACTLY FOUR options with this exact composition —
                       ONE correct, ONE partial, TWO wrong:
                       1. CORRECT — the complete answer a developer who reached
                          the objective gives. Nothing missing, nothing wrong.
                       2. PARTIAL — a real but INCOMPLETE grasp: it gets the
                          main idea right, then omits or softens something the
                          objective requires, or answers only one side of a
                          "what it does / what it does NOT do" question. Not
                          wrong — just not the whole claim. It must be clearly
                          weaker than the correct option, not a paraphrase of it.
                       3-4. WRONG — each contains a definite error: a clause
                          that is factually wrong about the code shown (wrong
                          order, wrong owner, wrong mechanism, a responsibility
                          it does not have). A developer who knows the material
                          can point at the wrong clause.
                       All four must be the same kind of thing (all name a
                       responsibility, or all describe an order) and roughly the
                       same length, so the composition cannot be read off shape.
                       Return them in RANDOM order; do NOT place the correct one
                       first. One phrase each. No "All of the above", no "None of
                       these", no letter or number prefixes, no option that only
                       negates another. The correct option must NOT be inferable
                       from `setup`.
                     - [] — an empty array, when the line says this form has no
                       one-phrase answer. Do not invent options in that case.
  choice_verdicts: an object mapping EACH of the four option strings (verbatim)
                   to one of "correct", "partial", "wrong" — exactly one
                   "correct", exactly one "partial", two "wrong". This is what
                   marks the learner's pick, so the "correct" one must be a
                   COMPLETE answer to the objective, not merely the best of four.
                   Return {} when `choices` is [].

Do NOT emit a "walkthrough" key and do NOT emit "prompt_kind" — the first is
assembled from your setup and reveal, and the second is decided for you.

LESSON SHAPE by the unit's kind. This governs what the lesson is ABOUT; the
question's shape is governed separately by PROMPT FORM in the user content.
  - `architecture`    — what this layer OWNS and what it does NOT own. Frame
                        around responsibility, not line-by-line behaviour.
  - `flow`            — trace the path, entry to exit, IN THE ORDER THE ANCHORS
                        ARE GIVEN. Each anchor is a step; say what happens at
                        it and what carries to the next. A flow lesson that
                        describes only the first anchor has failed.
  - `component`       — the abstraction and its contract. This is the one kind
                        where implementation detail IS the objective.
  - `risk`            — establish the MECHANISM and what depends on it: the
                        guarantee this code quietly provides, and who relies on
                        it. Do NOT announce that it is violated or name the
                        failure — the prompt is what asks the developer to find
                        it, and a `setup` that states the flaw has answered its
                        own question.
  - `extension_point` — how this is meant to be EXTENDED. Identify the contract
                        (ABC, protocol, callback shape) and show one concrete
                        extension if visible.
  - `test_coverage`   — what this test GUARDS, or what is left unguarded.
  - `synthesis`       — connect units the developer has ALREADY learned. Teach
                        no new code: the anchors are there to remind them what
                        they saw, not to introduce anything. The lesson is the
                        relationships between the parts.
  - anything else     — explain the piece in service of the goal.

Calibration by goal fields (read these from the user content):

  By `Depth requested` — a budget for `setup` and `reveal` TOGETHER:
    overview  → ~100 words. Focus on the WHY only.
    moderate  → ~150 words (current default). Balanced explanation.
    deep      → ~250 words. Walk through the code. Stay under 250 words regardless.

  By `familiarity with THIS codebase`:
    "Starting fresh"      → define repo-specific terms on first use; do not
                            assume any working model of THIS codebase.
    "Skimmed the README"  → define internal terms; assume the developer
                            knows what the library does and roughly why.
    "Looked at some code" → assume working vocabulary; define only the
                            non-obvious internal terms.
    "Diving into source"  → terse expert framing; no re-explanation of
                            anything they could find by reading.

  By `background`:
    If the developer's background suggests fluency with a concept this
    lesson would otherwise re-explain (e.g. Python decorators for a 5-year
    Python developer, REST middleware for a web-backend engineer), OMIT
    that re-explanation and spend the saved words on what's specific to
    THIS codebase. This is information elision — DO NOT force analogies.
    Analogies are decoration; only use one if it makes the concept land
    materially faster, and never more than one per lesson.

Rules:
- Teach only what the shown code supports. Do not invent behavior, file paths,
  or relationships not visible in the code or the system context.
- Keep the walkthrough focused on THIS piece — the system context is
  context, not a second lesson. The target word count is set by
  `Depth requested` (see Calibration above).
- Return ONLY the JSON object — no markdown fences, no preamble.
"""


def _read_source_lines(repo_path: str, file: str, start: int, end: int) -> str:
    """Read lines [start, end] (1-indexed, inclusive) from {repo_path}/{file}."""
    path = Path(repo_path) / file
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    # start/end are 1-indexed and inclusive; slice is 0-indexed half-open.
    return "\n".join(lines[start - 1:end])


def _read_node_source(repo_path: str, node: LearningNode) -> str:
    """Every anchor's source, in order — not just the displayed one.

    A unit may be grounded in several equally real locations: a flow across
    three files, a boundary on both sides of a seam. Reading only the display
    anchor would hand the model one file and ask it to teach three, which is the
    exact failure the single-anchor model used to force (learning-engine.md L5).

    Falls back to the display anchor for every graph planned before multi-anchor
    units existed — which is what `anchors` being absent means.
    """
    stored = (node.lesson_brief or {}).get("anchors") or []
    if len(stored) < 2:
        return _read_source_lines(
            repo_path,
            node.code_anchor.file,
            node.code_anchor.line_start,
            node.code_anchor.line_end,
        )

    parts: list[str] = []
    failures: list[str] = []
    for i, anchor in enumerate(stored, start=1):
        try:
            body = _read_source_lines(
                repo_path,
                anchor["file"],
                int(anchor["line_start"]),
                int(anchor["line_end"]),
            )
        except Exception as e:
            # One stale anchor must not cost the whole lesson; the others are
            # still verified, and the unit is still grounded by them.
            failures.append(f"{anchor.get('file')}: {e}")
            continue
        label = anchor.get("symbol") or f"lines {anchor['line_start']}-{anchor['line_end']}"
        parts.append(
            f"--- anchor {i} of {len(stored)}: {anchor['file']} — {label} ---\n{body}"
        )

    if not parts:
        # EVERY anchor failed. Tolerating this would hand the model an empty
        # source and an objective, and it would write a confident lesson out of
        # nothing — the precise failure this system's grounding exists to make
        # impossible (LP7). A multi-anchor unit with no readable anchor is in
        # exactly the same position as a single-anchor unit whose file is gone,
        # and must fail the same way.
        raise FileNotFoundError(
            f"no anchor could be read for this unit: {'; '.join(failures)}"
        )
    return "\n\n".join(parts)


def _choices_directive(node: LearningNode) -> str:
    """Whether THIS question must ship four options, phrased for the user turn.

    The learner is always offered both ways to answer — a radio group and a text
    box — so for every form that CAN carry options, the model is required to
    produce them, not merely allowed to. `critique` and `explain-back` have no
    one-phrase answer (see `_CHOICE_FORMS`), so those are told to return `[]`.
    `run` enforces the same split after parsing; this is the instruction half.
    """
    if lesson_form(node) in _CHOICE_FORMS:
        return (
            "Return EXACTLY FOUR options — the learner will be offered them as a "
            "multiple-choice alongside the text box, and their pick is graded "
            "against the LEARNING OBJECTIVE above, not against the wording of "
            "your question. So the CORRECT option must be the objective's claim "
            "in applied form: a learner who picks it has demonstrated the "
            "objective. The PARTIAL option is that same claim with a piece "
            "missing. If your question cannot be answered by stating the "
            "objective, the question has drifted — rewrite it so it can. "
            "Follow every rule for the `choices` key in the system prompt."
        )
    return (
        "Return [] — this form has no single-phrase answer, so there is no "
        "faithful multiple-choice version. The learner answers in text only."
    )


def _build_prior_context(graph: LearningGraph, current_id: str) -> str:
    """What the developer already understands — as CLAIMS, not as titles.

    Passing each earlier unit's objective rather than its title costs the same
    tokens and buys real continuity: "they can already explain what Session owns"
    is something to build on, where "they saw a node called Session" is not
    (learning-engine.md §7.1).
    """
    understood = [
        n
        for nid, n in graph.nodes.items()
        if nid != current_id and understanding_of(n) == "understood"
    ]
    if not understood:
        return "This is the developer's first lesson in this session — assume no prior nodes covered."
    lines = []
    for n in understood:
        claim = n.objective()
        tags = ", ".join(n.concept_tags) if n.concept_tags else "—"
        lines.append(
            f"- {n.title} (concepts: {tags})"
            + (f"\n    they can now: {claim}" if claim else "")
        )
    return "The developer already understands these earlier nodes:\n" + "\n".join(lines)


def _previous_unit(graph: LearningGraph, current_id: str) -> LearningNode | None:
    """The unit immediately before this one on the walk, if any.

    `why_now` is written by the TEACHER, from this unit's objective — resolving
    LQ4. The planner knows the dependency structure but not what the previous
    lesson actually said; the teacher has both the objective and the position,
    and it costs no extra call. If continuity ever reads poorly, moving it to
    the planner is still open.
    """
    order = graph.path_order()
    try:
        index = order.index(current_id)
    except ValueError:
        return None
    return graph.nodes[order[index - 1]] if index > 0 else None


# Module names too generic to identify a docs page — matching on them produces
# a confidently wrong pairing rather than no pairing, which is worse.
_GENERIC_STEMS = frozenset({
    "__init__", "__main__", "main", "app", "base", "core", "utils", "util",
    "helpers", "common", "types", "compat", "constants", "config", "settings",
})
# How many times a module must be named in a docs page before we accept that
# page as being about it. One passing mention is not a topic.
_MIN_DOC_MENTIONS = 2


def _pick_extra_doc(file: str, extra: dict[str, str]) -> tuple[str, str] | None:
    """Pick the docs/ page most likely to be *about* `file`, or None.

    Two passes, strongest signal first:
      1. the module's name appears in the docs filename ("sessions" → sessions.rst)
      2. otherwise, the page that names the module most often in its body

    The second pass is what makes this fire at all. Projects name docs pages
    after topics ("advanced.rst", "quickstart.rst"), not after modules, so
    requiring the module name in the *path* — as this once did — meant the
    section was almost never emitted.
    """
    stem = Path(file).stem.lower()
    if len(stem) < 4 or stem in _GENERIC_STEMS:
        return None
    # Modules are named in the plural, prose is written in the singular:
    # `sessions.py` is documented as "the Session object". Searching for the
    # singular finds both, since it is a prefix of the plural.
    needle = stem[:-1] if stem.endswith("s") and len(stem) > 4 else stem

    for doc_path, content in extra.items():
        if needle in Path(doc_path).stem.lower():
            return doc_path, content

    best: tuple[str, str] | None = None
    best_mentions = _MIN_DOC_MENTIONS - 1
    for doc_path, content in extra.items():
        mentions = content.lower().count(needle)
        if mentions > best_mentions:
            best, best_mentions = (doc_path, content), mentions
    return best


def _format_doc_context(node: LearningNode, doc_context: dict | None) -> str:
    """Build the documentation-context section for the Teaching Agent prompt.

    Pulls four sources of real repo documentation (none LLM-generated):
      1. Module docstring for the node's file
      2. Class / function docstrings in that file
      3. README excerpt (first 400 chars)
      4. Relevant docs/ file excerpt if one matches the node's file path
    Returns "" when doc_context is absent or all sources are empty.
    """
    if not doc_context:
        return ""
    parts: list[str] = []

    file = node.code_anchor.file

    # 1. Module-level docstring
    file_doc = (doc_context.get("file_docs") or {}).get(file, "").strip()
    if file_doc:
        parts.append(f"Module docstring for {file}:\n{file_doc}")

    # 2. Class / function docstrings in this file
    symbols: dict[str, str] = (doc_context.get("symbol_docs") or {}).get(file, {})
    if symbols:
        lines = [f"  `{name}`: {doc.splitlines()[0]}" for name, doc in symbols.items()]
        parts.append(f"Docstrings in {file}:\n" + "\n".join(lines))

    # 3. README excerpt
    readme = (doc_context.get("readme") or "").strip()
    if readme:
        parts.append(f"README excerpt:\n{readme[:400]}")

    # 4. Relevant docs/ file
    picked = _pick_extra_doc(file, doc_context.get("extra_docs") or {})
    if picked is not None:
        doc_path, content = picked
        parts.append(f"Docs file ({doc_path}):\n{content[:500]}")

    if not parts:
        return ""
    return "\n\n".join(parts) + "\n\n"


def _source_header(node: LearningNode) -> str:
    stored = (node.lesson_brief or {}).get("anchors") or []
    if len(stored) < 2:
        return (
            f"Source code for this node ({node.code_anchor.file} lines "
            f"{node.code_anchor.line_start}–{node.code_anchor.line_end}):"
        )
    # Say that the ordering means something. A flow's anchors are its steps in
    # execution order, and a lesson that traces them out of order is wrong even
    # when every individual claim is right.
    return (
        f"Source code for this node — {len(stored)} anchors, in order. "
        f"Teach across all of them; the order is the order the lesson should "
        f"follow:"
    )


def _brief_line(label: str, value: str | None) -> str:
    return f"  {label}: {value}\n" if value else ""


def _unblocks(graph: LearningGraph, node_id: str) -> LearningNode | None:
    """The stop this unit was inserted to unblock, if it is a warm-up.

    `insert_before` chains the warm-up to the stop it precedes with a
    `prerequisite` edge, so the warm-up is the FROM side. Read from the edge
    rather than from position: a warm-up is also the structural predecessor of
    that stop, and "the node before me" cannot tell the two relationships apart.
    """
    for edge in graph.edges:
        if edge.kind == "prerequisite" and edge.from_node_id == node_id:
            return graph.nodes.get(edge.to_node_id)
    return None


def _previous_unit_section(
    previous: LearningNode | None,
    unblocks: LearningNode | None = None,
) -> str:
    """What `why_now` is written off.

    A WARM-UP IS NOT A CONTINUATION, and telling the model it is produces prose
    that is plainly false to the learner who asked for it. Observed live in S0: a
    warm-up inserted because a learner misunderstood the auth extension point
    opened "Now that you know how to use Session safely with context managers,
    you need to understand…" — the model following this instruction faithfully,
    off a predecessor that had nothing to do with why the unit exists.

    Two things were wrong with pointing a warm-up at the previous unit. The
    learner did not just finish that unit — they got stuck on the one AFTER this
    warm-up, which is the reason it was created. And the warm-up's antecedent is
    the confusion, not the position: it was spliced into the middle of the walk,
    so "what came before" is an accident of where it landed.

    So a remediation is told what it is for. The stop it unblocks is what the
    learner was actually trying to do, and `why_now` written off that is the only
    version that is true — it says why they are here, which they already know they
    did not choose.
    """
    if unblocks is not None:
        claim = unblocks.objective()
        return (
            "THIS UNIT IS A WARM-UP, inserted because the developer got stuck on "
            "the stop that follows it. They did not choose to be here.\n"
            "Write `why_now` off the stop it unblocks — one sentence on what this "
            "gives them for that, NOT on what came before it in the path:\n"
            f"  the stop they were stuck on: {unblocks.title}\n"
            + (f"  what they were trying to claim: {claim}\n" if claim else "")
            + "\n"
        )
    if previous is None:
        return (
            "This is the first unit of the path — `why_now` should say what the "
            "path is about to build, not what came before.\n\n"
        )
    claim = previous.objective()
    return (
        f"The unit they just finished — write `why_now` off this:\n"
        f"  title: {previous.title}\n"
        + (f"  its claim: {claim}\n" if claim else "")
        + "\n"
    )


def _build_user_content(
    goal: dict,
    node: LearningNode,
    source: str,
    prior_context: str,
    doc_context: dict | None = None,
    system_context: str = "",
    previous: LearningNode | None = None,
    unblocks: LearningNode | None = None,
) -> str:
    brief = node.lesson_brief or {}
    doc_section = _format_doc_context(node, doc_context)
    # One slot, filled by whichever provider had something to say — the dossier
    # slice, the structural neighbourhood, or neither. A source-only lesson is a
    # supported mode, so an empty section stays empty rather than being padded
    # with a placeholder the model would try to interpret.
    context_section = f"{system_context}\n\n" if system_context else ""
    return (
        f"Developer profile:\n"
        f"  familiarity with THIS codebase: {goal.get('familiarity', 'unknown')}\n"
        f"  background: {goal.get('background', 'unknown')}\n"
        f"Overall goal: {goal.get('primary_goal', '')}\n"
        f"Depth requested: {goal.get('depth', 'normal')}\n\n"
        f"{prior_context}\n\n"
        f"{_previous_unit_section(previous, unblocks)}"
        f"{doc_section}"
        f"LEARNING OBJECTIVE — build exactly this claim:\n"
        f"  {node.objective() or '(none stated — build the brief below)'}\n\n"
        f"PROMPT FORM — your `prompt` must take this shape:\n"
        f"  {_FORM_BRIEF[lesson_form(node)]}\n\n"
        f"CHOICES — what to return for the `choices` key:\n"
        f"  {_choices_directive(node)}\n\n"
        f"Lesson brief for this node:\n"
        f"  title: {node.title}\n"
        # `understand` is absent on objective-first graphs, where it would only
        # restate the objective above. An empty labelled line reads as a gap the
        # model should fill, so it is omitted rather than blanked.
        f"{_brief_line('why', brief.get('why'))}"
        f"{_brief_line('understand', brief.get('understand'))}"
        f"  concepts: {', '.join(node.concept_tags) if node.concept_tags else '—'}\n\n"
        f"{_source_header(node)}\n"
        f"{source}\n\n"
        f"{context_section}"
    )


def _parse_output(raw: str) -> LessonOutput:
    """Decode the lesson JSON, tolerating a markdown fence around it.

    NEVER cut at the closing fence. A walkthrough is markdown and routinely
    contains its own ```python block, so splitting on the next ``` truncates the
    JSON mid-string — which surfaces as "Unterminated string" pointing at the
    walkthrough's opening quote and looks exactly like an output-limit
    truncation. Measured on a real lesson: `stop_reason=end_turn`, 674 output
    tokens, a complete response, and both the call and its retry "failed".
    `raw_decode` already stops at the end of the object, so trailing text —
    including the closing fence — needs no handling at all.
    """
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else ""
    start = raw.find("{")
    if start < 0:
        raise ValueError("no JSON object found in response")
    decoded, _ = json.JSONDecoder().raw_decode(raw[start:])
    output = LessonOutput(**decoded)
    # Verdicts are keyed by option text and validated against the normalised
    # `choices`; a map that is not exactly one correct / one partial / two wrong
    # becomes {}, and `run` then drops the options.
    output.choice_verdicts = _normalize_verdicts(
        output.choices, decoded.get("choice_verdicts")
    )
    if not output.setup and not output.walkthrough:
        # Neither half of the lesson body arrived. Caught here rather than by
        # Pydantic, because either field alone is legitimate: a pre-B4 cached
        # lesson has only `walkthrough`, and a new one has only `setup`.
        raise ValueError("lesson has neither a setup nor a walkthrough")
    if not output.walkthrough:
        # Assemble the compatibility surface. Any client that knows only
        # `walkthrough` — which today is all of them — renders the same lesson
        # it always did, in the same order, with the prompt below it. B6 is
        # what teaches the panel to withhold `reveal` until the answer (§12).
        output.walkthrough = "\n\n".join(
            part for part in (output.setup, output.reveal) if part
        )
    return output


def _session_dossier(state: OnboardState) -> dict | None:
    """The investigation for this session, from state or from the store.

    At onboarding time it rides on `state.investigation`; at session time the
    request is rebuilt from the persisted graph, so it is loaded by session id.
    Unavailable for any reason (absent, schema bump, moved commit, corrupt) is a
    supported state — the caller falls back (D12).
    """
    if state.investigation:
        return state.investigation.get("dossier")
    if state.graph is None:
        return None
    try:
        from backend.repo.cloner import get_commit_sha

        commit_sha = get_commit_sha(state.repo_path) if state.repo_path else None
    except Exception:
        commit_sha = None
    stored = dossier_store.load_investigation(state.graph.session_id, commit_sha)
    if stored is None:
        return None
    state.investigation = stored
    return stored.get("dossier")


def run(
    state: OnboardState,
    client: anthropic.Anthropic | None = None,
) -> OnboardState:
    if client is None:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    if state.graph is None:
        state.errors.append("teaching_agent: graph missing")
        return state

    current_id = state.graph.current_node_id
    if current_id is None or current_id not in state.graph.nodes:
        state.errors.append("teaching_agent: no current node to teach")
        return state

    if state.goal is None:
        state.errors.append("teaching_agent: goal missing")
        return state

    node = state.graph.nodes[current_id]

    # Cache hit — a prior visit already rendered this lesson.
    if node.cached_lesson is not None:
        state.current_lesson = node.cached_lesson
        return state

    try:
        source = _read_node_source(state.repo_path, node)
    except Exception as e:
        state.errors.append(f"teaching_agent: could not read source: {e}")
        return state

    # System context for this lesson, in strict preference order:
    #
    #   1. DOSSIER    the investigation's structured understanding, sliced to
    #                 THIS node deterministically (component role, flow
    #                 neighbourhood, relationships, contracts, prerequisites,
    #                 evidence). Preferred because it knows the user's GOAL.
    #   2. SKELETON   the repository's own structure around the node — what it
    #                 extends, what it uses, what uses it. Knows nothing about
    #                 the goal, but is grounded by construction and available
    #                 whenever the checkout is.
    #   3. NOTHING    a source-only lesson, which is a valid degraded mode.
    #
    # D12 is the reason rung 2 exists: an absent, stale or version-mismatched
    # dossier is a SUPPORTED state, not an error, and it must not fall through
    # to nothing when the repository can still say something true. The anchored
    # source is the lesson's evidence either way — everything here is
    # enrichment, and no failure in it may block a lesson.
    system_context = ""
    skeleton = None
    try:
        skeleton = build_skeleton(state.repo_path)
    except Exception as e:
        state.errors.append(f"teaching_agent: skeleton unavailable (non-fatal): {e}")

    dossier = _session_dossier(state)
    if dossier is not None and skeleton is not None:
        try:
            system_context = dossier_context.context_for_node(
                skeleton,
                dossier,
                node.code_anchor.file,
                symbol=node.code_anchor.symbol,
                line_start=node.code_anchor.line_start,
                line_end=node.code_anchor.line_end,
            ).as_prompt_section()
        except Exception as e:
            state.errors.append(
                f"teaching_agent: dossier context failed (non-fatal): {e}"
            )
    if not system_context and skeleton is not None:
        try:
            system_context = structure.neighbour_context(
                skeleton,
                node.code_anchor.file,
                symbol=node.code_anchor.symbol,
                line_start=node.code_anchor.line_start,
                line_end=node.code_anchor.line_end,
            )
        except Exception as e:
            state.errors.append(
                f"teaching_agent: structural context failed (non-fatal): {e}"
            )

    prior_context = _build_prior_context(state.graph, current_id)
    doc_context = state.doc_context if state.doc_context is not None else state.graph.doc_context
    user_content = _build_user_content(
        state.goal, node, source, prior_context,
        doc_context=doc_context, system_context=system_context,
        previous=_previous_unit(state.graph, current_id),
        # A warm-up gets told what it unblocks instead of what preceded it.
        unblocks=_unblocks(state.graph, current_id),
    )

    try:
        output = _generate_lesson(client, user_content, _SYSTEM_PROMPT)
        # The form is ours to decide, not the model's to report. Setting it here
        # rather than trusting the response is what makes "the form follows from
        # the kind" a property of the system instead of an instruction the model
        # may drift from.
        output.prompt_kind = lesson_form(node)
        # The form decides whether a four-option rendering is faithful to the
        # question. An unlisted form (critique, explain-back) keeps the text
        # prompt and drops any options the model offered.
        if output.prompt_kind not in _CHOICE_FORMS:
            output.choices = []
        # OPTION GATES. Options are only safe when the question actually tests the
        # objective (the pick is graded against the objective, so options written
        # for a drifted question grade wrong no matter what) AND exactly one of
        # the four is a complete correct answer. Either miss drops the options and
        # the stop keeps its text prompt — no worse than the pre-choice
        # behaviour. Unlike `reassess.py` this does not regenerate: a full lesson
        # re-render is far more expensive than a fresh re-assessment question.
        objective = node.objective() or ""
        # No trustworthy verdict map → a pick could not be graded from it, so the
        # options would be back to "any choice might mark partial". Checked first,
        # before the paid gates, because it needs no model call.
        if output.choices and not output.choice_verdicts:
            state.errors.append(
                "teaching_agent: option verdicts missing or malformed — "
                "multiple-choice dropped, text answer only"
            )
            output.choices = []
        if output.choices and not _question_serves_objective(
            client, objective, output.prompt, output.expected_answer
        ):
            state.errors.append(
                "teaching_agent: question drifted from objective — "
                "multiple-choice dropped, text answer only"
            )
            output.choices = []
        # Verify the model's OWN claimed-correct option really is the complete
        # answer — the label is what grades a pick, so a mislabelled "correct"
        # would pass a wrong answer.
        if output.choices and not _choices_are_sound(
            client, objective, output.prompt, output.choices,
            _correct_option(output.choice_verdicts),
        ):
            state.errors.append(
                "teaching_agent: marked-correct option was not a complete answer — "
                "multiple-choice dropped, text answer only"
            )
            output.choices = []
        if not output.choices:
            output.choice_verdicts = {}
        # Order is not a signal. The prompt asks for a random order, but a model
        # that drifts back to "correct one first" would leak the answer by
        # position — so shuffle it here regardless. Seeded by the node id so a
        # re-render of the same stop shows the same order. Verdicts are keyed by
        # option text, so the shuffle does not touch them.
        if output.choices:
            random.Random(node.id).shuffle(output.choices)
        lesson = output.model_dump()
        node.cached_lesson = lesson
        state.current_lesson = lesson
    except Exception as e:
        state.errors.append(f"teaching_agent LLM call failed: {e}")

    return state


def _generate_lesson(
    client: anthropic.Anthropic, user_content: str, system: str = _SYSTEM_PROMPT
) -> LessonOutput:
    """One Haiku call, with a single corrective retry on a parse failure.

    Haiku occasionally wraps the JSON in prose or emits malformed JSON. Like
    the Mentor's retries and the Grader's fallback, we don't let one bad
    response fail the lesson — we show the model its miss and ask once more.
    """
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )
    raw = _text_of(response)
    try:
        return _parse_output(raw)
    except Exception:
        retry = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[
                {"role": "user", "content": user_content},
                {"role": "assistant", "content": raw},
                {"role": "user", "content": _correction(response)},
            ],
        )
        return _parse_output(_text_of(retry))  # may raise → caller logs it


def _question_serves_objective(
    client: anthropic.Anthropic,
    objective: str,
    prompt: str,
    correct_answer: str,
) -> bool:
    """One cheap check: could a learner answer this question well and STILL not
    have shown the objective?

    The Teaching prompt is told to build the question from the objective, and it
    still drifts — a unit whose objective is "Session state persists across
    requests" has been seen shipping a question about response-body caching. The
    Grader marks the answer against the OBJECTIVE, never the question, so a
    drifted question fails every answer to it — including the correct option of a
    multiple choice, where the learner cannot route around the drift by writing
    about the objective instead. This gate runs before the options are shown; a
    DRIFTED verdict drops them and the stop falls back to text only, which is no
    worse than the pre-choice behaviour.

    Trusts the lesson on a pre-objective graph (nothing to check against) and on
    an unreadable verdict — the check is a safety net, and a flaky judge must not
    silently delete the feature.
    """
    if not objective.strip():
        return True
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=8,
            system=(
                "You check whether a lesson question tests its stated "
                "objective. Reply with exactly one word: ALIGNED or DRIFTED. "
                "DRIFTED means a developer could answer the question perfectly "
                "and still not have demonstrated the objective, because the "
                "question is about a different part of the system."
            ),
            messages=[{"role": "user", "content": (
                f"OBJECTIVE:\n{objective}\n\n"
                f"QUESTION:\n{prompt}\n\n"
                f"A CORRECT ANSWER TO THE QUESTION:\n{correct_answer}\n\n"
                "One word — ALIGNED or DRIFTED."
            )}],
        )
    except Exception:
        return True
    verdict = _text_of(resp).strip().upper()
    return "DRIFT" not in verdict


def _choices_are_sound(
    client: anthropic.Anthropic,
    objective: str,
    prompt: str,
    choices: list[str],
    correct_option: str = "",
) -> bool:
    """One cheap check: is EXACTLY ONE option a complete correct answer — and,
    when `correct_option` is given, is it THAT one?

    The composition rule (one correct, one partial, two wrong) is an instruction
    the model follows unreliably on a nuanced topic — it tends to ship one
    partial and three wrong, or two options a careful reader could defend. And
    the model's OWN verdict label can be wrong: it marks option A "correct" when
    the real answer is C. Since a learner's pick is graded straight from that
    label (`learning/choices.py`), an unverified label lets a wrong option pass.

    So the set is verified after generation against the model's claimed-correct
    option. Anything else is rejected; the caller regenerates once and then falls
    back to a text box. An unreadable verdict trusts the set — a flaky judge must
    not delete a good multiple choice.
    """
    if not objective.strip() or len(choices) != 4:
        return True
    numbered = "\n".join(f"{i}. {c}" for i, c in enumerate(choices, 1))
    if correct_option:
        system = (
            "You check whether the MARKED option is the one correct answer. "
            "Reply with exactly one word: SOUND or UNSOUND. SOUND means the "
            "marked option is a COMPLETE, correct answer to the objective and no "
            "other option is also fully correct. UNSOUND means the marked option "
            "is incomplete or wrong, or another option is equally defensible."
        )
        body = (
            f"OBJECTIVE:\n{objective}\n\n"
            f"QUESTION:\n{prompt}\n\n"
            f"OPTIONS:\n{numbered}\n\n"
            f"MARKED CORRECT:\n{correct_option}\n\n"
            "One word — SOUND or UNSOUND."
        )
    else:
        system = (
            "You check a multiple-choice set. Reply with exactly one word: "
            "SOUND or UNSOUND. SOUND means EXACTLY ONE option is a complete, "
            "correct answer to the objective, and the other three are not (one "
            "may be partially right, but only one is fully correct). UNSOUND "
            "means zero options are fully correct, or more than one could be "
            "defended as correct."
        )
        body = (
            f"OBJECTIVE:\n{objective}\n\n"
            f"QUESTION:\n{prompt}\n\n"
            f"OPTIONS:\n{numbered}\n\n"
            "One word — SOUND or UNSOUND."
        )
    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=8, system=system,
            messages=[{"role": "user", "content": body}],
        )
    except Exception:
        return True
    return "UNSOUND" not in _text_of(resp).strip().upper()


def _correct_option(verdicts: dict[str, str]) -> str:
    """The option the verdict map marks `correct`, or "" if the map is empty."""
    for option, verdict in verdicts.items():
        if verdict == "correct":
            return option
    return ""


def _text_of(response) -> str:
    """Every text block, joined — not just the first.

    `content[0].text` silently truncates a response the model split across
    blocks, and the resulting fragment fails to parse as "Unterminated string"
    at the very start of the JSON, which reads exactly like an output-limit
    truncation and is not one. Cheap to be right about; the harness has always
    joined blocks this way.
    """
    return "".join(
        block.text for block in response.content
        if isinstance(getattr(block, "text", None), str)
    )


# Two different faults present as the same "Unterminated string" parse error, and
# they need opposite corrections. Telling a model that ran out of output tokens
# that its JSON was malformed makes it emit the same too-long lesson again and
# truncate in the same place — observed on a 87-line doc-heavy anchor, where both
# the call and its retry failed and the session fell back to a placeholder.
_CORRECTION_MALFORMED = (
    "That was not a valid JSON object. Return ONLY the JSON object with keys "
    "walkthrough, prompt, expected_answer, prompt_kind — no markdown fences, no "
    "prose."
)
_CORRECTION_TRUNCATED = (
    "Your response hit the output limit and was cut off mid-JSON, so it could not "
    "be read. Write a SHORTER lesson this time — the same teaching, fewer words: "
    "trim the walkthrough hardest, quote less source, and close the JSON. Return "
    "ONLY the JSON object with keys walkthrough, prompt, expected_answer, "
    "prompt_kind."
)


def _correction(response) -> str:
    truncated = getattr(response, "stop_reason", None) == "max_tokens"
    return _CORRECTION_TRUNCATED if truncated else _CORRECTION_MALFORMED
