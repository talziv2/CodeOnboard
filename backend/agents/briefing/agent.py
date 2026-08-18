# Briefing Agent — the welcome page's paragraph: what this repository is, and
# what THIS reader needs to know about it before the tour starts.
#
# Entry point:
#   build_briefing(repo_url, goal, survey, doc_context, repo_path, client) -> dict
#
# Why this is not a pipeline node: it reads only material the pipeline already
# produced and paid for (the Layer B survey, the Documentation Agent's README)
# and nothing downstream depends on it. Running it lazily at welcome time and
# caching the result on the session keeps a failed briefing from ever costing
# somebody the learning path they waited minutes for.
#
# Output shape:
#   {
#     "paragraph":    str,          # 3-5 sentences, pitched at this reader
#     "notes":        [{"text": str, "file": str | None}],
#     "personalized": bool,         # False when this is the survey's own prose
#     "available":    bool,         # False when there was no material to write from
#   }
#
# GROUNDING. The model is given the survey account and the README and nothing
# else, and is told that is all it knows. Two rules make that hold rather than
# hope:
#   - No material, no briefing. With no survey and no README the model has only
#     the reader's goal, and from a goal alone it will write a fluent, confident
#     description of a repository it has never seen — the same failure mode as a
#     lesson written from its objective (learning-engine.md §4.1.2). This returns
#     `available: False` instead, and the welcome page shows the profile alone.
#   - A cited path is checked against the checkout. `notes[].file` survives only
#     if that file actually exists; otherwise the note keeps its text and loses
#     the citation.
#
# Mirrors the other agents: client injected, never raises.

import json
import logging

import anthropic
from pydantic import BaseModel, ValidationError

from backend.repo.skeleton import normalize_path, safe_repo_path

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5"
MAX_TOKENS = 1024

# Every cap below exists because the survey is an inventory: it enumerates every
# subsystem of a repository the size of FastAPI, and handing all of that to a
# call that writes five sentences pays for breadth nobody reads.
MAX_SUBSYSTEMS = 14
MAX_ENTRY_POINTS = 5
MAX_ABSTRACTIONS = 5
MAX_FLOWS = 4
MAX_BOUNDARIES = 4
README_CHARS = 1200
MAX_NOTES = 4

# How the four familiarity answers change what an orienting paragraph should do.
# Keyed on the verbatim option strings, which is what `goal["familiarity"]`
# carries — the Goal Agent is told to copy them exactly, for this reason.
_FAMILIARITY_GUIDANCE: dict[str, str] = {
    "Starting fresh — never looked at it": (
        "They have never seen this code. Establish the shape and the vocabulary "
        "before any specific name: what problem it solves, what the main pieces "
        "are called, how a call travels through it."
    ),
    "Skimmed the README or docs": (
        "They know the pitch, not the code. Do not restate the README — say how "
        "the advertised behaviour is actually arranged in the source."
    ),
    "Looked at some code but still confused": (
        "They have read some of this and it did not cohere. Give them the "
        "organising idea the files do not state: what routes through what, and "
        "which piece is the centre."
    ),
    "Used it before, now diving into the source": (
        "They know the outside and are now reading the inside. Skip the "
        "introduction; tell them how the internals are laid out and what "
        "surprises a caller who assumes the API's shape is the code's shape."
    ),
}

_DEPTH_GUIDANCE: dict[str, str] = {
    "map": (
        "They asked for the map — responsibilities, boundaries, flows. Stay at "
        "that altitude."
    ),
    "working": (
        "They intend to work in here, so name the parts they would touch and "
        "what guards them."
    ),
    "implementation": (
        "They asked to master the internals, so naming concrete types and "
        "critical paths is fair."
    ),
}


class Note(BaseModel):
    text: str
    file: str | None = None


class BriefingOutput(BaseModel):
    paragraph: str
    notes: list[Note] = []


_SYSTEM_PROMPT = """\
You are writing the welcome briefing a developer reads before starting a guided
tour of a repository they do not know.

You are given three things: who the reader is (in their own words, from a short
interview), an account of the repository produced by an earlier pass over its
actual source, and an excerpt of its README.

Produce a JSON object with exactly these keys:

  paragraph — 3 to 5 sentences. What this repository is, how it is put together,
              and what that means for THIS reader's goal. One paragraph of plain
              prose: no lists, no headings.
  notes     — 2 to 4 items, each one sentence this reader specifically would
              want to know before starting. Prefer the non-obvious: an
              abstraction everything routes through, a boundary that will
              surprise them, a naming convention, where the tests are. Each note
              is {"text": "...", "file": "path or null"}.

Rules:
- The material you are given is the ONLY thing you know about this repository.
  If a fact is not in it, do not write it. Never guess at a file, a symbol, a
  version, a dependency or a history.
- Spell any file or symbol exactly as the material spells it. When a note is
  about one place in the code, put that path in its `file` field rather than only
  in its prose.
- Write to the reader as "you", in the present tense. No greeting, no "welcome
  to", no sign-off, no encouragement.
- Do not describe the tour, the lessons, or what happens next. You are
  explaining the repository, not the product.
- Return ONLY the JSON object — no markdown fences, no explanation.
"""


def _profile_block(goal: dict) -> str:
    """The reader, in their own words, plus how that changes the pitch."""
    lines = [
        f"Their goal: {goal.get('primary_goal') or 'not stated'}",
        f"Focus: {goal.get('focus_area') or 'the whole system'}",
        f"Why they are here (goal type): {goal.get('goal_type') or 'unknown'}",
        f"Familiarity with this code: {goal.get('familiarity') or 'unknown'}",
        f"What they already know: {goal.get('background') or 'not stated'}",
    ]
    # The goal-type follow-ups. Present only for the type that asked them, and
    # each is the reader's own sentence about what they are trying to do — often
    # the most specific thing in the whole profile.
    for key, label in (
        ("contribution_context", "The contribution they are working on"),
        ("change_target", "The change they want to make"),
        ("risk_tolerance", "How safety-critical that change is"),
        ("error_description", "The error they are hitting"),
        ("tried_so_far", "What they have already tried"),
    ):
        if goal.get(key):
            lines.append(f"{label}: {goal[key]}")

    for guidance in (
        _FAMILIARITY_GUIDANCE.get(str(goal.get("familiarity") or "")),
        _DEPTH_GUIDANCE.get(str(goal.get("code_depth") or "")),
    ):
        if guidance:
            lines.append(f"How to pitch it: {guidance}")
    return "\n".join(lines)


def _survey_block(survey: dict) -> str:
    """The Layer B account, trimmed to what a five-sentence briefing can use."""
    parts: list[str] = []

    architecture = str(survey.get("architecture") or "").strip()
    if architecture:
        parts.append(f"Architecture:\n{architecture}")

    subsystems = [s for s in (survey.get("subsystems") or []) if isinstance(s, dict)]
    if subsystems:
        listed = "\n".join(
            f"- {s.get('name')}: {s.get('responsibility')} ({s.get('key_file')})"
            for s in subsystems[:MAX_SUBSYSTEMS]
        )
        remaining = len(subsystems) - MAX_SUBSYSTEMS
        overflow = f"\n- (+{remaining} further subsystems)" if remaining > 0 else ""
        parts.append(f"Subsystems ({len(subsystems)} in total):\n{listed}{overflow}")

    entry_points = [e for e in (survey.get("entry_points") or []) if isinstance(e, dict)]
    if entry_points:
        parts.append(
            "Entry points:\n"
            + "\n".join(
                f"- [{e.get('perspective')}] {e.get('file')}::{e.get('symbol')}"
                f" — {e.get('what_it_starts')}"
                for e in entry_points[:MAX_ENTRY_POINTS]
            )
        )

    abstractions = [
        a for a in (survey.get("core_abstractions") or []) if isinstance(a, dict)
    ]
    if abstractions:
        parts.append(
            "Core abstractions:\n"
            + "\n".join(
                f"- {a.get('file')}::{a.get('symbol')} — {a.get('role')}"
                for a in abstractions[:MAX_ABSTRACTIONS]
            )
        )

    flows = [f for f in (survey.get("flows") or []) if isinstance(f, dict)]
    if flows:
        # Names and lengths only. The steps are the tour's material, not the
        # briefing's, and they are the largest thing in the survey.
        parts.append(
            "End-to-end flows:\n"
            + "\n".join(
                f"- {f.get('name')} ({len(f.get('steps') or [])} steps)"
                for f in flows[:MAX_FLOWS]
            )
        )

    boundaries = [b for b in (survey.get("boundaries") or []) if isinstance(b, dict)]
    if boundaries:
        parts.append(
            "Boundaries:\n"
            + "\n".join(
                f"- [{b.get('kind')}] {b.get('file')}::{b.get('symbol')}"
                f" — {b.get('note')}"
                for b in boundaries[:MAX_BOUNDARIES]
            )
        )

    testing = str(survey.get("testing_posture") or "").strip()
    if testing:
        parts.append(f"Testing posture:\n{testing}")

    return "\n\n".join(parts)


def _material(survey: dict | None, doc_context: dict | None) -> tuple[str, str]:
    """(survey_text, readme) — the two grounded sources; either may be empty."""
    survey_text = _survey_block(survey) if isinstance(survey, dict) else ""
    readme = ""
    if isinstance(doc_context, dict):
        readme = str(doc_context.get("readme") or "").strip()[:README_CHARS]
    return survey_text, readme


def _user_content(repo_url: str, goal: dict, survey_text: str, readme: str) -> str:
    blocks = [f"Repository: {repo_url}", f"THE READER\n{_profile_block(goal)}"]
    if survey_text:
        blocks.append(f"WHAT AN EARLIER PASS OVER THE SOURCE FOUND\n{survey_text}")
    if readme:
        blocks.append(f"README EXCERPT\n{readme}")
    return "\n\n".join(blocks)


def _parse(raw: str) -> BriefingOutput:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return BriefingOutput(**json.loads(text.strip()))


def _ground_notes(notes: list[Note], repo_path: str | None) -> list[dict]:
    """Notes with their citations checked against the checkout.

    A path that does not resolve costs the citation, not the note: the sentence
    may still be true and useful, but a file reference we have not verified is a
    claim the reader would take on trust.
    """
    grounded: list[dict] = []
    for note in notes[:MAX_NOTES]:
        text = note.text.strip()
        if not text:
            continue
        file = normalize_path(note.file) if note.file else None
        if file:
            resolved = safe_repo_path(repo_path, file) if repo_path else None
            if resolved is None or not resolved.exists():
                file = None
        grounded.append({"text": text, "file": file})
    return grounded


def _from_survey_alone(survey_text: str) -> dict:
    """Fallback: the survey's own architecture prose, marked as not personalized.

    Reached when the call or its parse fails. Generic, but true — and the welcome
    page says which one the reader is looking at rather than presenting this as
    written for them.
    """
    architecture = ""
    if survey_text.startswith("Architecture:\n"):
        architecture = survey_text[len("Architecture:\n") :].split("\n\n")[0].strip()
    if not architecture:
        return {"paragraph": "", "notes": [], "personalized": False, "available": False}
    return {
        "paragraph": architecture,
        "notes": [],
        "personalized": False,
        "available": True,
    }


def build_briefing(
    *,
    repo_url: str,
    goal: dict,
    survey: dict | None,
    doc_context: dict | None,
    repo_path: str | None = None,
    client: anthropic.Anthropic | None = None,
) -> dict:
    """One Haiku call: the welcome paragraph and its notes, for this reader."""
    survey_text, readme = _material(survey, doc_context)
    if not survey_text and not readme:
        # No material, no briefing (see the module docstring).
        return {"paragraph": "", "notes": [], "personalized": False, "available": False}
    if client is None:
        return _from_survey_alone(survey_text)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": _user_content(repo_url, goal, survey_text, readme),
                }
            ],
        )
        raw = "".join(
            block.text
            for block in response.content
            if isinstance(getattr(block, "text", None), str)
        )
        output = _parse(raw)
    except (json.JSONDecodeError, ValidationError, KeyError, IndexError, TypeError) as e:
        logger.warning("briefing unparseable, falling back to the survey: %s", e)
        return _from_survey_alone(survey_text)
    except Exception as e:
        logger.warning("briefing call failed, falling back to the survey: %s", e)
        return _from_survey_alone(survey_text)

    paragraph = output.paragraph.strip()
    if not paragraph:
        return _from_survey_alone(survey_text)
    return {
        "paragraph": paragraph,
        "notes": _ground_notes(output.notes, repo_path),
        "personalized": True,
        "available": True,
    }
