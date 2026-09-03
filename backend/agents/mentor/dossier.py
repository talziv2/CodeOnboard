# Investigation Dossier → prompt text, and the evidence ranges that gate it.
#
# This module is the dossier half of the Mentor: it turns a dossier into the
# structured prompt the planner reasons over, and it computes the resolved
# anchor ranges that grounding checks a proposed anchor against. The planning
# itself lives in `curriculum.py`, which is the only caller.
#
# It used to also hold the pre-B3 node planner, reached when
# `CODEONBOARD_CURRICULUM` was `0`. That flag is gone and so is that planner:
# a second planner nobody could run was a choice the repository advertised and
# could not honour. What survives is the part both ever needed.
#
# What the rendering guarantees, on purpose:
#
#   EVIDENCE   The dossier is structured understanding — components with
#              role_in_goal / why_it_matters, ordered flows, relationships,
#              contracts, prerequisites, open questions — not a bag of chunks.
#              The rendering preserves that structure instead of flattening it.
#   SCOPE      No 24-chunk cap and no top_k under another name: the dossier
#              already IS the selected, goal-relevant evidence. The only limits
#              are per-anchor render caps so one 900-line class cannot crowd
#              out the rest of the prompt — a rendering safeguard at the
#              dossier/Mentor contract, not an evidence cap.
#   EVIDENCE GATE  The Mentor may anchor lessons only within code the
#              investigation verified — that is what `_dossier_evidence_ranges`
#              returns. It has seen no other code, so citing beyond the dossier
#              would mean reasoning from nothing.

from __future__ import annotations

import json

from backend.repo import anchors
from backend.repo.investigation import _entries
from backend.repo.skeleton import Skeleton

# Rendering safeguards — how much of each verified anchor's source reaches the
# prompt. These bound the *rendering of one entry*, never how many entries the
# dossier may contribute.
ANCHOR_RENDER_LINES = 120
PROMPT_SOFT_CAP_CHARS = 90_000


# ── dossier rendering ──────────────────────────────────────────────────────────


def _render_anchor_code(
    skeleton: Skeleton, file: str, symbol: str, seen: set[tuple[str, int, int]]
) -> str:
    """The verified source for one dossier anchor, render-capped, once."""
    resolution = anchors.resolve(skeleton, str(file), symbol=str(symbol))
    if not resolution.ok:
        return ""
    a = resolution.anchor
    if a.as_tuple() in seen:
        return f"    (code for {a.symbol or symbol} shown above)\n"
    seen.add(a.as_tuple())
    source = skeleton.read_lines(a.file, a.line_start, a.line_end) or ""
    lines = source.splitlines()
    shown = lines[:ANCHOR_RENDER_LINES]
    body = "\n".join(shown)
    truncated = ""
    if len(lines) > ANCHOR_RENDER_LINES:
        truncated = f"\n    ... ({len(lines) - ANCHOR_RENDER_LINES} more lines not shown)"
    return (
        f"    [{a.file} lines {a.line_start}-{a.line_end}"
        f"{' — ' + a.symbol if a.symbol else ''}]\n{body}{truncated}\n"
    )


def render_dossier(
    skeleton: Skeleton, dossier: dict, goal: dict,
    system_review: dict | None = None,
) -> str:
    """The dossier as structured prompt text, code attached to each anchor.

    Structure is preserved deliberately: the whole point of the native path is
    that `why_it_matters`, flow order, prerequisites and open questions reach
    the Mentor instead of being flattened away.
    """
    seen: set[tuple[str, int, int]] = set()
    parts: list[str] = []

    parts.append("## The user's goal\n" + json.dumps(goal, indent=2))

    understanding = str(dossier.get("understanding") or "").strip()
    if understanding:
        parts.append("## What the investigation established (its own summary)\n"
                     + understanding)

    components = _entries(dossier, "components")[0]
    if components:
        section = ["## Goal-relevant components (most important first)"]
        for c in components:
            section.append(
                f"- {c.get('symbol')} in {c.get('file')}\n"
                f"  role in this goal: {c.get('role_in_goal')}\n"
                f"  why it matters: {c.get('why_it_matters')}"
            )
            code = _render_anchor_code(skeleton, c.get("file"), c.get("symbol"), seen)
            if code:
                section.append(code)
        parts.append("\n".join(section))

    entry_points = _entries(dossier, "entry_points")[0]
    if entry_points:
        section = [
            "## Entry points into the goal-relevant behaviour",
            "`public_api` is what a developer USING this code imports and calls; "
            "`runtime` is what invokes the behaviour when the system runs. They "
            "are often different definitions, and which one a learner should meet "
            "first depends on the goal.",
        ]
        for e in entry_points:
            # The perspective was collected by the investigation and dropped
            # here, so the planner could not tell a caller-facing entry point
            # from a runtime one for ANY goal type. Phase A gathered the
            # distinction; this is what makes it usable.
            perspective = str(e.get("perspective") or "").strip()
            label = f" [{perspective}]" if perspective else ""
            section.append(
                f"- {e.get('file')}:{e.get('symbol')}{label} — {e.get('how_it_enters')}"
            )
        parts.append("\n".join(section))

    flows = _entries(dossier, "flows")[0]
    if flows:
        section = ["## Verified flows (steps in EXECUTION order — teaching order is yours to choose)"]
        for flow in flows:
            section.append(f"Flow: {flow.get('name')}")
            for i, step in enumerate(flow.get("steps") or [], start=1):
                if not isinstance(step, dict):
                    continue
                section.append(
                    f"  {i}. {step.get('file')}:{step.get('symbol')} — {step.get('what_happens')}"
                )
        parts.append("\n".join(section))

    relationships = _entries(dossier, "relationships")[0]
    if relationships:
        section = ["## Confirmed relationships"]
        for r in relationships:
            section.append(
                f"- {r.get('from_symbol')} --{r.get('kind')}--> {r.get('to_symbol')}"
                f"  ({r.get('note')})"
            )
        parts.append("\n".join(section))

    contracts = _entries(dossier, "contracts")[0]
    if contracts:
        section = ["## Contracts and abstractions"]
        for c in contracts:
            section.append(f"- {c.get('file')}:{c.get('symbol')} — {c.get('contract')}")
            code = _render_anchor_code(skeleton, c.get("file"), c.get("symbol"), seen)
            if code:
                section.append(code)
        parts.append("\n".join(section))

    prerequisites = _entries(dossier, "prerequisites")[0]
    if prerequisites:
        section = ["## Prerequisite concepts (candidates — apply the prerequisite rules)"]
        for p in prerequisites:
            anchor = f" (anchored: {p.get('file')}:{p.get('symbol')})" if p.get("symbol") else " (no code anchor)"
            section.append(f"- {p.get('concept')}: {p.get('why_needed')}{anchor}")
        parts.append("\n".join(section))

    evidence_refs = _entries(dossier, "evidence_refs")[0]
    if evidence_refs:
        section = ["## Tests and docs the investigation found clarifying"]
        for e in evidence_refs:
            section.append(f"- {e.get('path')} — {e.get('clarifies')}")
        parts.append("\n".join(section))

    context = [str(c) for c in dossier.get("context") or []]
    if context:
        parts.append("## Context the investigation noted\n" + "\n".join(f"- {c}" for c in context))

    if system_review:
        # The Reviewer runs for goal types that turn on architectural judgement
        # and writes `state.system_review`. Its only consumer used to be the
        # retrieval path's prompt builders; deleting those at Stage 5 would have
        # left an agent making a Sonnet call nobody read. Its findings belong
        # here — they are exactly the `risk` and `extension_point` material the
        # node vocabulary already has tags for.
        section = ["## System review (for `risk` / `extension_point` nodes)"]
        for key, label in (
            ("strengths", "Strengths"),
            ("risks", "Risks"),
            ("extension_points", "Extension points"),
            ("recommendations", "Recommendations"),
        ):
            entries = system_review.get(key) or []
            if not entries:
                continue
            section.append(f"{label}:")
            for entry in entries:
                if isinstance(entry, dict):
                    detail = entry.get("detail") or entry.get("why") or ""
                    section.append(f"  - {entry.get('title') or entry.get('area')}: {detail}")
                else:
                    section.append(f"  - {entry}")
        if len(section) > 1:
            parts.append("\n".join(section))

    open_questions = _entries(dossier, "open_questions")[0]
    if open_questions:
        section = ["## OPEN QUESTIONS — recorded uncertainty, NOT facts. "
                   "Do not build a lesson that depends on these."]
        for q in open_questions:
            section.append(f"- {q.get('question')} (matters because: {q.get('why_it_matters')})")
        parts.append("\n".join(section))

    text = "\n\n".join(parts)
    if len(text) > PROMPT_SOFT_CAP_CHARS:
        # A dossier so large it breaches the soft cap is a dossier/Mentor
        # contract problem to solve upstream; here we degrade by trimming the
        # rendered code blocks hardest-first rather than dropping findings.
        text = text[:PROMPT_SOFT_CAP_CHARS] + "\n... (rendering soft cap reached)"
    return text


# ── evidence ranges ──────────────────────────────────────────────────────────────────


def _dossier_evidence_ranges(skeleton: Skeleton, dossier: dict) -> list[dict]:
    """The dossier's resolved anchors, as within_evidence-shaped ranges."""
    from backend.repo.investigation import cited_anchors

    ranges: list[dict] = []
    seen: set[tuple[str, int, int]] = set()
    for _, file, symbol in cited_anchors(dossier):
        if not file or not symbol:
            continue
        resolution = anchors.resolve(skeleton, file, symbol=symbol)
        if not resolution.ok:
            continue
        a = resolution.anchor
        if a.as_tuple() in seen:
            continue
        seen.add(a.as_tuple())
        ranges.append({
            "file": a.file, "start_line": a.line_start, "end_line": a.line_end,
        })
    return ranges
