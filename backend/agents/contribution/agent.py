# The contribution stage's three model calls — plan, review, PR summary.
#
# ── THE ONE RULE THIS FILE IS BUILT AROUND ────────────────────────────────────
#
#     NOTHING HERE EVER WRITES CODE.
#
# The plan is prose and step titles. The review is an opinion about code the
# learner wrote. The PR summary describes a change that already exists. No
# function in this module returns a patch, a diff, a file body, or a snippet
# long enough to be pasted in as one — and `tests/test_contribution_boundary.py`
# asserts the prompts say so.
#
# That is what keeps the contribution stage the last step of a learning journey
# rather than a coding agent with a lesson bolted on the front. The learner is
# the contributor; this file helps them think and then tells them what it sees.
#
# ── AND THE THREE CLAIMS, KEPT APART ──────────────────────────────────────────
#
# `review` produces an OPINION and is labelled as one everywhere it surfaces.
# The scope comparison is decided in `learning/contribution.py` by Python, and
# whether the repository still passes its tests is decided by NOBODY, because
# nothing here runs anything. A review that said "this is correct" would collapse
# all three into one word, so the prompt is told what it may and may not claim.
#
# Conventions, as everywhere in `agents/`: the client is injected, the model is
# Haiku, and a failure degrades to an honest empty result rather than raising at
# the caller.

from __future__ import annotations

import json
import logging

import anthropic
from pydantic import BaseModel, ValidationError

from backend.learning.contribution import PatchFile

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5"
MAX_TOKENS = 1536

# How much learner-authored code reaches a prompt. Bounds the request, not the
# patch — `contribution.MAX_PATCH_BYTES` already refused anything larger, and
# this only keeps a legitimate ten-file patch from crowding out its own review.
PATCH_RENDER_CHARS = 6000


# ── wire formats ──────────────────────────────────────────────────────────────


class _PlanStep(BaseModel):
    title: str
    detail: str = ""


class PlanOutput(BaseModel):
    steps: list[_PlanStep]


class ReviewOutput(BaseModel):
    # Deliberately not `correct`. The question is whether the change does what
    # the developer said they wanted, which is a reading of two texts — not a
    # claim about whether the code works, which nothing here can support.
    meets_task: bool
    observations: list[str] = []
    concerns: list[str] = []


class PrOutput(BaseModel):
    title: str
    body: str
    testing_notes: str = ""


# ── shared rendering ──────────────────────────────────────────────────────────


def _boundary_text(boundary: dict) -> str:
    """The change boundary as prompt text. Empty when there is none."""
    if not boundary:
        return ""
    lines: list[str] = []
    for section, label in (
        ("target", "Where the change belongs"),
        ("must_not_change", "What it must NOT touch"),
        ("edge_cases", "Edge cases it must respect"),
        ("existing_tests", "Tests that already guard this behaviour"),
        ("conventions", "Conventions this repository follows"),
    ):
        entries = boundary.get(section)
        if not isinstance(entries, list) or not entries:
            continue
        lines.append(f"{label}:")
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if section == "conventions":
                lines.append(
                    f"  - {entry.get('convention')} (see {entry.get('evidence_file')})"
                )
            elif section == "edge_cases":
                lines.append(f"  - {entry.get('case')} — {entry.get('why_it_bites')}")
            else:
                reason = (
                    entry.get("why_here")
                    or entry.get("why_not")
                    or entry.get("what_it_guards")
                    or ""
                )
                lines.append(f"  - {entry.get('file')}:{entry.get('symbol')} — {reason}")
    return "\n".join(lines)


def _patch_text(patch: list[PatchFile]) -> str:
    """The learner's proposed files, capped for the prompt."""
    out: list[str] = []
    budget = PATCH_RENDER_CHARS
    for entry in patch:
        body = entry.contents[:budget]
        budget -= len(body)
        out.append(f"--- {entry.path} ({entry.intent}) ---\n{body}")
        if budget <= 0:
            out.append("(remaining files not shown — the patch is long)")
            break
    return "\n\n".join(out)


def _call(client: anthropic.Anthropic, system: str, user: str, model_cls):
    """One Haiku call, parsed. Returns None on any failure — never raises."""
    try:
        response = client.messages.create(
            model=MODEL, max_tokens=MAX_TOKENS, system=system,
            messages=[{"role": "user", "content": user}],
        )
        raw = "".join(
            block.text for block in response.content
            if isinstance(getattr(block, "text", None), str)
        ).strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else ""
        start = raw.find("{")
        if start < 0:
            raise ValueError("no JSON object in response")
        decoded, _ = json.JSONDecoder().raw_decode(raw[start:])
        return model_cls(**decoded)
    except (json.JSONDecodeError, ValidationError, ValueError, KeyError,
            IndexError, TypeError) as e:
        logger.warning("contribution: unparseable %s: %s", model_cls.__name__, e)
    except Exception as e:                                        # noqa: BLE001
        logger.warning("contribution: %s call failed: %s", model_cls.__name__, e)
    return None


# ── plan ──────────────────────────────────────────────────────────────────────

_PLAN_SYSTEM = """\
A developer has just finished a short, focused learning path about one part of an
unfamiliar codebase, and is about to make ONE specific change to it. They are
going to write the code themselves.

Write the plan they should follow. Three to six steps.

WHAT YOU MUST NOT DO
- Do NOT write the code. No function bodies, no diffs, no snippets to paste.
  A step says what to do and what to be careful of; the developer writes it.
- Do NOT introduce anything the change boundary does not mention. If the
  boundary does not name a file, the plan does not touch it.
- Do NOT teach the concepts again. They have just learned them, and the list of
  what they demonstrated is given to you so you can WRITE IN TERMS OF IT — refer
  to what they now know rather than re-explaining it.

WHAT MAKES A GOOD STEP
- It names the place: the file, and the symbol where it applies.
- It says what has to be true when the step is done.
- Where an edge case from the boundary bites on that step, it says which one and
  what it means for the code — without saying what to type.
- The last step is always about the test: which file, which existing test to
  imitate, and which cases it has to cover.

Return ONLY a JSON object: {"steps": [{"title": "...", "detail": "..."}]}
`title` is a short imperative. `detail` is one or two sentences. No markdown
fences, no commentary."""


def build_plan(
    *,
    task: str,
    boundary: dict,
    demonstrated: list[str],
    client: anthropic.Anthropic | None = None,
) -> dict | None:
    """The implementation plan. `None` when it could not be written.

    `demonstrated` is the objectives the learner has actually shown they can
    make — not the whole curriculum. That is the point of passing it: the plan is
    written in the vocabulary this developer has just earned, which is what makes
    the contribution stage read as the end of the journey rather than the start
    of a different product.
    """
    if client is None or not task.strip():
        return None
    known = "\n".join(f"- {o}" for o in demonstrated if o.strip())
    user = (
        f"THE CHANGE THEY ARE MAKING:\n{task.strip()}\n\n"
        f"THE CHANGE BOUNDARY (established by reading the repository):\n"
        f"{_boundary_text(boundary) or '(none recorded)'}\n\n"
        f"WHAT THEY HAVE DEMONSTRATED THEY UNDERSTAND:\n{known or '(nothing yet)'}"
    )
    output = _call(client, _PLAN_SYSTEM, user, PlanOutput)
    if output is None or not output.steps:
        return None
    return {
        "steps": [
            {"title": s.title.strip(), "detail": s.detail.strip()}
            for s in output.steps if s.title.strip()
        ],
    }


# ── review ────────────────────────────────────────────────────────────────────

_REVIEW_SYSTEM = """\
A developer has written a change to an unfamiliar codebase, by hand, after
learning the part of it the change touches. Review what they wrote.

WHAT YOU ARE BEING ASKED, AND WHAT YOU ARE NOT

You are being asked ONE question: does this do what they said they wanted, given
what the investigation established about the code around it?

You are NOT being asked whether it is correct, whether it is safe, or whether the
repository's tests still pass. Nothing has been run. Two other things answer
those questions and yours is not one of them, so never claim or imply any of
them. Write as a colleague reading a diff, not as a build system.

WHAT TO LOOK AT
- Does it address the task as stated? Name anything the task asked for that you
  cannot find in the change.
- Does it respect the edge cases the boundary lists? An edge case the change
  silently ignores is the most useful thing you can point at.
- Does it follow the conventions the boundary names, and does the test imitate
  the tests that are already there?
- Is anything here outside what the task asked for?

DO NOT REWRITE IT. Do not include corrected code, and do not include more than a
few words of theirs when quoting. Say what you see; they fix it.

Return ONLY a JSON object:
  {"meets_task": true|false,
   "observations": ["..."],     what the change does, as you read it
   "concerns": ["..."]}         what you would raise in review; [] if none
Each string is one sentence. No markdown fences, no commentary."""


def review_patch(
    *,
    task: str,
    boundary: dict,
    patch: list[PatchFile],
    client: anthropic.Anthropic | None = None,
) -> dict | None:
    """A reading of the learner's change. An OPINION, labelled as one everywhere."""
    if client is None or not patch:
        return None
    user = (
        f"THE TASK THEY SET OUT TO DO:\n{task.strip()}\n\n"
        f"THE CHANGE BOUNDARY:\n{_boundary_text(boundary) or '(none recorded)'}\n\n"
        f"WHAT THEY WROTE:\n{_patch_text(patch)}"
    )
    output = _call(client, _REVIEW_SYSTEM, user, ReviewOutput)
    if output is None:
        return None
    return {
        "meets_task": bool(output.meets_task),
        "observations": [o.strip() for o in output.observations if o.strip()],
        "concerns": [c.strip() for c in output.concerns if c.strip()],
    }


# ── PR summary ────────────────────────────────────────────────────────────────

_PR_SYSTEM = """\
Write the pull request description for a change a developer has just made to an
open-source repository.

The change already exists — you are describing it, not proposing it. Write what
a maintainer needs in order to review it.

  title          one line, imperative, under 70 characters, no ticket prefix
  body           two or three short paragraphs: what changes, why it belongs
                 where it is, and what behaviour it preserves. Plain markdown
                 paragraphs — no headings, no bullet lists of file names.
  testing_notes  THREE THINGS, KEPT APART, in this order:
                   1. what the contributor added or covered;
                   2. what was CHECKED AUTOMATICALLY — you are given the exact
                      list; report it as checks that were performed, naming
                      what each one means;
                   3. the command a maintainer should run, and the plain
                      statement that those tests HAVE NOT BEEN RUN.

WHAT THE AUTOMATIC CHECKS ARE AND ARE NOT. They compare file paths and parse the
submitted files. They do not run anything, and they do not read the original
source at symbol granularity. So report them as what they are — "no files
outside the planned boundary", "both files parse" — and never as evidence the
change works.

Do not claim the tests pass. Do not write "all tests pass", "tests are green" or
anything a reader could mistake for a test result. Do not claim the change is
correct. You are describing a proposal a human will review.

Return ONLY a JSON object with those three keys. No markdown fences."""


def _checks_text(check) -> str:
    """The deterministic findings, as prompt text. Says so when there are none.

    THE SUMMARY HAS TO DISTINGUISH THREE THINGS — what CodeOnboard checked, what
    it recommends, and what nobody ran — and it cannot report the first unless it
    is given it. Without this the notes said only "not executed", which is honest
    and incomplete: it understates the change by omitting the checks that DID
    pass, and leaves a reader to assume nothing was verified at all.
    """
    if check is None:
        return "(no automatic checks were run on this change)"
    lines = []
    if check.passed:
        lines.append("- path scope: PASSED — no files outside the planned "
                     "contribution boundary")
    else:
        outside = ", ".join(check.outside_boundary + check.forbidden)
        lines.append(f"- path scope: FAILED — {outside} outside the boundary")
    if check.unparseable:
        lines.append("- syntax: could not be parsed: "
                     + ", ".join(check.unparseable))
    else:
        lines.append("- syntax: every submitted Python file parses")
    if check.symbol_expected:
        found = "is defined in the change" if check.symbol_found else "was NOT found"
        lines.append(f"- symbol: `{check.symbol_expected}` {found}")
    if check.test_files:
        lines.append("- test file: " + ", ".join(check.test_files)
                     + " is included in the change")
    else:
        lines.append("- test file: no test file in the change")
    if check.unchecked_symbols:
        lines.append(
            f"- NOT checked: {len(check.unchecked_symbols)} protected symbol(s) "
            f"({', '.join(check.unchecked_symbols[:4])}). These are symbol-level "
            f"constraints and this check compares file paths, so nothing verified "
            f"they are untouched."
        )
    return "\n".join(lines)


def build_pr(
    *,
    task: str,
    patch: list[PatchFile],
    review: dict | None,
    validation_command: str,
    scope_check=None,
    client: anthropic.Anthropic | None = None,
) -> dict | None:
    """Title, body and testing notes for a PR-ready contribution."""
    if client is None or not patch:
        return None
    files = ", ".join(entry.path for entry in patch) or "(none)"
    concerns = "; ".join((review or {}).get("concerns") or []) or "(none raised)"
    user = (
        f"THE TASK:\n{task.strip()}\n\n"
        f"FILES CHANGED: {files}\n\n"
        f"THE CHANGE:\n{_patch_text(patch)}\n\n"
        f"CONCERNS RAISED IN REVIEW: {concerns}\n\n"
        f"CHECKS CODEONBOARD PERFORMED AUTOMATICALLY (no code was executed):\n"
        f"{_checks_text(scope_check)}\n\n"
        f"THE TESTS THAT COVER THIS AREA: "
        f"{validation_command or '(none identified)'}\n"
        f"WHETHER THEY WERE RUN: no — CodeOnboard does not execute repository "
        f"tests, and nobody has reported running them."
    )
    output = _call(client, _PR_SYSTEM, user, PrOutput)
    if output is None or not output.title.strip():
        return None
    return {
        "title": output.title.strip(),
        "body": output.body.strip(),
        "testing_notes": output.testing_notes.strip(),
    }
