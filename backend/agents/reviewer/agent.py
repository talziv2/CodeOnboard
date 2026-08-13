# Reviewer Agent — produces a structured system review for the Mentor.
#
# Runs between Prioritization and Mentor, but only for goal types where the
# user wants to reason about, critique, or change the system:
#   - improve_existing_system  (the user plans to change the code)
#   - understand_architecture  (the user wants layers, boundaries, risks)
#
# A single Haiku call. Reads the (prioritized) module map + RAG-retrieved
# chunks for the goal and emits a structured `system_review` JSON the Mentor
# can use to emit graph nodes tagged `risk` / `extension_point` / `architecture`
# / `test_coverage`.
#
# This is NOT a separate user-facing artifact. The Mentor consumes it. The
# Reviewer just gives the Mentor better raw material than module names alone.
#
# Mirrors the other agents: client injected, errors appended to state.errors,
# never raises. On any failure, leaves state.system_review as None and the
# Mentor falls back to its pre-Reviewer behaviour.

import json
import os

import anthropic
from pydantic import BaseModel, field_validator

from backend.pipeline.state import OnboardState
from backend.repo import anchors
from backend.repo.skeleton import Skeleton, build_skeleton, normalize_path


MODEL = "claude-haiku-4-5"
MAX_TOKENS = 2048

# Goal types that need a Reviewer pass. Everything else skips it to save
# tokens and avoid pulling the Mentor's emphasis off-goal.
_REVIEWER_GOAL_TYPES = frozenset({"improve_existing_system", "understand_architecture"})


# ── Wire format ───────────────────────────────────────────────────────────────


class _AnchorWire(BaseModel):
    file: str
    line_start: int
    line_end: int


class _Finding(BaseModel):
    area: str             # short label (e.g. "session_auth_redirect")
    note: str             # one or two sentences
    anchor: _AnchorWire | None = None


class _Boundary(BaseModel):
    between: list[str]    # two area labels — the seam runs between them
    note: str

    # Haiku occasionally returns `between` as a single string ("sessions and
    # auth") instead of a two-element list. Coerce that shape rather than
    # tank the whole review payload over one item. Tried separators cover
    # the natural-language ("and"), formal ("<->"), and prose-list (",", "/")
    # forms; if none match we wrap the whole string in a single-element
    # list so the finding still surfaces.
    @field_validator("between", mode="before")
    @classmethod
    def _split_string_between(cls, v):
        if isinstance(v, str):
            for sep in (" <-> ", " -> ", " <- ", " and ", ", ", " / "):
                if sep in v:
                    return [s.strip() for s in v.split(sep, 1)]
            return [v.strip()]
        return v


class ReviewerOutput(BaseModel):
    strengths: list[_Finding]
    risks: list[_Finding]
    extension_points: list[_Finding]
    test_gaps: list[_Finding]
    boundaries: list[_Boundary]


# ── Prompt ────────────────────────────────────────────────────────────────────


_SYSTEM_PROMPT = """\
You are a senior engineer doing a structured review of an unfamiliar Python
codebase on behalf of a developer who needs to reason about, critique, or
safely extend it.

You are given:
  - the developer's goal
  - the module map (module name → purpose + key exports)
  - a set of retrieved code chunks (file, line range, content)

Produce a JSON object with exactly these keys:
  strengths:        list of architectural strengths (≤ 3 items)
  risks:            list of fragilities, hidden coupling, or invariants the
                    developer must respect before changing nearby code (≤ 4)
  extension_points: list of seams designed to be extended (hooks, plugin
                    registries, ABCs, registered handlers) (≤ 4)
  test_gaps:        areas that lack test coverage and would be unsafe to
                    change without first adding tests (≤ 3)
  boundaries:       major seams between subsystems (≤ 3)

Each strengths/risks/extension_points/test_gaps item is an object:
  area:    short snake_case label naming the concern (e.g. "session_lifecycle")
  note:    one or two sentences — what the developer needs to know
  anchor:  OPTIONAL object {file, line_start, line_end}. Include it when the
           concern is anchored on a specific piece of code you were shown.
           Copy file path and line range VERBATIM from a retrieved chunk.
           Omit anchor entirely for cross-cutting concerns (e.g. "no tests
           cover the auth helpers at all").

Each boundaries item is an object:
  between: a list of EXACTLY TWO short strings, naming the subsystems on
           either side of the seam. Example: ["sessions", "adapters"].
           Do NOT use a single string like "sessions and adapters".
  note:    one sentence — what crosses the boundary and what it isolates

Rules:
- Be specific and grounded. Vague items ("code could be cleaner") are useless.
- If a finding has an anchor, the (file, line_start, line_end) MUST come from
  the retrieved chunks. Never invent anchors.
- Prefer fewer, high-signal findings over filling every list to the cap.
- Empty lists are valid — if you do not see a clear architectural strength,
  return an empty strengths list rather than padding.

Calibration by `Risk tolerance` (read it from the user content when present;
this overrides the "prefer fewer" default for safety-critical work):

  SAFETY-CRITICAL — answer mentions production / must not regress / safety /
                    can't break / safety-critical:
    • Aim for the UPPER bound of `risks` (4 items). Every anchored
      fragility, hidden coupling, or invariant the user must respect.
    • Aim for the upper bound of `test_gaps` (3). Coverage holes around
      the planned change area are first-class findings.
    • `strengths` MAY be empty if no architecturally significant ones
      exist — do not pad.
    • `extension_points` and `boundaries` as normal.

  PROTOTYPE / EXPERIMENTAL — answer mentions prototype / experimental / can
                             break / throwaway:
    • `risks`: only the 1–2 findings that would BLOCK the planned change.
      Omit everything that is just nice-to-know.
    • `test_gaps` optional — include only if the user might actually want
      tests for this change.
    • `strengths` optional.

  UNSPECIFIED / IN BETWEEN (the default — no `Risk tolerance` line, or it
                            does not signal either extreme):
    • Use the "prefer fewer, high-signal" rule above.

- Return ONLY the JSON object — no markdown fences, no preamble.
"""


def _format_module_map(module_map: dict) -> str:
    lines = []
    for name, entry in module_map.items():
        exports = ", ".join(entry.get("exports", []))
        lines.append(f"- {name}: {entry['purpose']} (exports: {exports})")
    return "\n".join(lines)


def _format_chunks(chunks: list[dict]) -> str:
    lines = []
    for c in chunks:
        lines.append(
            f"[{c['type'].upper()}] {c['name']} — "
            f"{c['file']} (lines {c['start_line']}–{c['end_line']})\n"
            f"{c['content']}"
        )
    return "\n\n".join(lines)


def _build_user_content(goal: dict, module_map: dict, chunks: list[dict]) -> str:
    extras = []
    if goal.get("focus_area"):
        extras.append(f"Focus area: {goal['focus_area']}")
    if goal.get("change_target"):
        extras.append(f"Planned change: {goal['change_target']}")
    if goal.get("risk_tolerance"):
        extras.append(f"Risk tolerance: {goal['risk_tolerance']}")
    extra_block = ("\n" + "\n".join(extras)) if extras else ""

    return (
        f"Developer goal: {goal['primary_goal']}\n"
        f"Goal type: {goal['goal_type']}{extra_block}\n\n"
        f"Module map:\n{_format_module_map(module_map)}\n\n"
        f"Retrieved code chunks:\n{_format_chunks(chunks)}"
    )


# ── Anchor grounding (drop ungrounded anchors silently) ───────────────────────


def _normalize_path(p: str) -> str:
    return normalize_path(p)


def _drop_ungrounded_anchors(
    output: ReviewerOutput, chunks: list[dict], skeleton: Skeleton
) -> ReviewerOutput:
    """Findings whose anchor fails verification lose the anchor, not the finding.

    Same two-question check as the Mentor (repo-understanding.md Stage 0): the
    anchor must resolve against the REPOSITORY, and — while the evidence set is
    still a retrieval slice — must lie inside code the Reviewer was shown.

    The finding itself stays either way. This is gentler than the Mentor's
    retry-on-bad-anchor flow because a Reviewer finding doesn't have to anchor:
    it's allowed to talk about cross-cutting concerns. We just refuse to pass
    through anchors we can't verify.
    """

    def _ground(anchor: _AnchorWire | None) -> _AnchorWire | None:
        if anchor is None:
            return None
        resolution = anchors.resolve_within_evidence(
            skeleton,
            chunks,
            anchor.file,
            line_start=anchor.line_start,
            line_end=anchor.line_end,
        )
        if not resolution.ok:
            return None
        resolved = resolution.anchor
        return _AnchorWire(
            file=resolved.file,
            line_start=resolved.line_start,
            line_end=resolved.line_end,
        )

    for finding in (
        output.strengths + output.risks + output.extension_points + output.test_gaps
    ):
        finding.anchor = _ground(finding.anchor)
    return output


# ── Parse / run ───────────────────────────────────────────────────────────────


def _parse_output(raw: str) -> ReviewerOutput:
    raw = raw.strip()
    if "```json" in raw:
        raw = raw.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in raw:
        parts = raw.split("```")
        if len(parts) >= 2:
            raw = parts[1]
    start = raw.find("{")
    if start < 0:
        raise ValueError("no JSON object found in response")
    decoded, _ = json.JSONDecoder().raw_decode(raw[start:])
    return ReviewerOutput(**decoded)


def should_run(goal: dict | None) -> bool:
    """Public predicate for the LangGraph router."""
    if not goal:
        return False
    return goal.get("goal_type") in _REVIEWER_GOAL_TYPES


def run(
    state: OnboardState,
    client: anthropic.Anthropic | None = None,
) -> OnboardState:
    if not should_run(state.goal):
        # Not a Reviewer goal type — leave system_review as None and let the
        # Mentor proceed unchanged.
        return state

    if client is None:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    if state.module_map is None:
        state.errors.append("reviewer_agent: module_map missing")
        return state

    if state.investigation is None:
        # D11: the Reviewer reads the shared investigation and never explores
        # or retrieves on its own. Without one there is nothing to review.
        state.errors.append("reviewer_agent: no investigation to review")
        return state

    try:
        from backend.repo.investigation import dossier_as_chunks
        from backend.repo.skeleton import build_skeleton as _build_skeleton

        chunks = dossier_as_chunks(
            _build_skeleton(state.repo_path),
            state.investigation.get("dossier") or {},
        )
    except Exception as e:
        state.errors.append(f"reviewer_agent: dossier rendering failed: {e}")
        return state

    user_content = _build_user_content(state.goal, state.module_map or {}, chunks)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        output = _parse_output(response.content[0].text)
    except Exception as e:
        state.errors.append(f"reviewer_agent LLM call failed: {e}")
        return state

    try:
        skeleton = build_skeleton(state.repo_path)
    except Exception as e:
        # Repository access is a HARD requirement during onboarding (D15). A
        # partial, anchor-less review is not a reason to soften that — the
        # Mentor will fail on the same unavailable repository, and a graph
        # whose anchors were never verified is worse than no graph. Leave
        # system_review unset and let the pipeline fail explicitly.
        state.errors.append(f"reviewer_agent: skeleton build failed: {e}")
        return state

    output = _drop_ungrounded_anchors(output, chunks, skeleton)
    state.system_review = output.model_dump()
    return state
