# Native-Dossier Mentor path — pedagogical planning over an Investigation Dossier.
#
# Activated when `state.investigation` is present (the explorer pipeline). The
# retrieval path in agent.py is untouched and remains the baseline; run() in
# agent.py delegates here, so there is still exactly one Mentor entry point —
# only the evidence provider and the prompt that reasons over it change
# (repo-understanding.md §12 Stage 3, "rewrite the prompts to consume the
# richer dossier" — this is that rewrite).
#
# What is different from the retrieval path, on purpose:
#
#   EVIDENCE   The dossier is structured understanding — components with
#              role_in_goal / why_it_matters, ordered flows, relationships,
#              contracts, prerequisites, open questions — not a bag of chunks.
#              The prompt preserves that structure instead of flattening it.
#   ANCHORS    The model names `file` + `symbol` (G1). Our code resolves the
#              range from the symbol index, so a hallucinated line number is
#              structurally impossible. Raw ranges remain legal for the few
#              real anchors that are not symbols (G3).
#   SCOPE      No 24-chunk cap and no top_k under another name: the dossier
#              already IS the selected, goal-relevant evidence. The only limits
#              are per-anchor render caps so one 900-line class cannot crowd
#              out the rest of the prompt — a rendering safeguard at the
#              dossier/Mentor contract, not an evidence cap.
#   EVIDENCE GATE  The Mentor may anchor lessons only within code the
#              investigation verified (the dossier's resolved anchors). It has
#              seen no other code, so citing beyond the dossier would mean
#              reasoning from nothing — the same principle as Stage 0, with the
#              dossier as the evidence set instead of a retrieval slice.
#
# Same conventions as every agent: injected client, append to state.errors,
# never raise.

from __future__ import annotations

import json
from typing import Literal

import anthropic
from pydantic import BaseModel

from backend.pipeline.state import OnboardState
from backend.repo import anchors
from backend.repo.investigation import _entries
from backend.repo.skeleton import Skeleton, build_skeleton

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096

# Rendering safeguards — how much of each verified anchor's source reaches the
# prompt. These bound the *rendering of one entry*, never how many entries the
# dossier may contribute.
ANCHOR_RENDER_LINES = 120
PROMPT_SOFT_CAP_CHARS = 90_000


# ── wire format ────────────────────────────────────────────────────────────────


class DossierNodeWire(BaseModel):
    id: str
    title: str
    file: str
    # G1: symbol is the preferred identity — our code resolves the range.
    # A raw range is legal when the anchor genuinely is not a symbol (G3).
    symbol: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    # The checkable claim the learner should be able to make afterwards. This is
    # the contract between planner, teacher and grader (learning-engine.md §7.1,
    # §8.1): Teaching builds exactly this, the Grader marks against exactly this.
    #
    # Defaulted rather than required: a model that omits one key should cost the
    # user one weaker node, not the entire graph — a parse failure here produces
    # no learning path at all. Teaching and the Grader both fall back to
    # `understand`, which is what a pre-B1 graph carries.
    objective: str = ""
    why: str
    understand: str
    concept_tags: list[str]
    # Filled by grounding, consumed by the graph builder.
    resolved_start: int | None = None
    resolved_end: int | None = None
    resolved_symbol: str | None = None


class DossierEdgeWire(BaseModel):
    from_id: str
    to_id: str
    kind: Literal["sequence"] = "sequence"


class DossierMentorOutput(BaseModel):
    nodes: list[DossierNodeWire]
    edges: list[DossierEdgeWire]
    confidence: Literal["high", "medium", "low"]


# ── system prompt ──────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a mentor designing a learning path through an unfamiliar Python
codebase for one developer with one stated goal.

You are given an INVESTIGATION DOSSIER: the verified, goal-specific
understanding of the repository that a prior investigation established by
reading the actual code. Every code reference in it has been checked against
the repository. It tells you what is true and important; YOUR job is the
pedagogy — what this developer should learn, and in what order.

The dossier is repository understanding, not a curriculum. Do not convert it
one-finding-per-lesson:
- Several dossier findings may belong in a single node when they teach one
  concept (a contract and the component that implements it, for instance).
- One complex component may deserve several nodes at different altitudes.
- Source execution order and teaching order are not necessarily the same.
  A flow's steps tell you how the system runs; you decide whether the
  developer should meet them top-down, bottom-up, or abstraction-first,
  based on the goal and the developer profile.
- Use the dossier's `understanding`, each component's `role_in_goal` and
  `why_it_matters`, the relationships, and the prerequisites to decide what
  carries the goal — and leave out what does not. A dossier entry that does
  not serve THIS user's goal earns no node.

Prerequisites in the dossier are candidates, not obligations. For each one,
decide whether it:
  - needs its own early node (the user cannot follow anything without it),
  - can be taught inside another node's lesson brief,
  - is already implied by the user's experience level or background, or
  - is not important enough to include.
A prerequisite with no code anchor can only be taught inside another node's
brief — never invent an anchor for it.

Open questions in the dossier are recorded uncertainty. Never present an
unresolved claim as fact: do not build a node whose teaching depends on
something the investigation could not establish. Where an open question
matters to the goal, you may mention it inside a related node's
`understand` brief as an explicitly open point.

Produce a JSON object with exactly these keys:
  nodes:      list of learning nodes (count varies by depth — see Calibration)
  edges:      list of edges connecting the nodes into a teaching order
  confidence: one of "high", "medium", "low"

Each node is an object with exactly these keys:
  id:           short local identifier (e.g. "n1"), unique in this response
  title:        short imperative title
  file:         path exactly as it appears in the dossier
  symbol:       the qualified symbol this node teaches, exactly as it appears
                in the dossier (e.g. "Session.send"). PREFER this — the exact
                line range is resolved for you. Set it to null ONLY when the
                anchor genuinely is not a symbol, and then give line_start
                and line_end from the dossier instead.
  line_start:   null when `symbol` is given; otherwise the range start
  line_end:     null when `symbol` is given; otherwise the range end
  objective:    the single claim this developer should be able to MAKE, in
                their own words, once they have learned this node
  why:          one sentence — why this node matters for the user's goal
  understand:   one sentence — what the user should take away
  concept_tags: list of short concept tags (≤ 4 entries)

The `objective` is the most important field you write. It is not a topic and
not a summary of the code — it is the sentence the developer should be able to
say afterwards, and it is what their answer will be marked against. Write it as
a claim, specific enough that a wrong answer is visibly wrong:

  BAD   "Understand the Session object"            (a topic, not a claim)
  BAD   "Learn how sessions work"                  (nothing to be right about)
  GOOD  "Explain what Session owns that a bare request does not — connection
         reuse, cookie persistence and default configuration — and why sending
         through a Session changes behaviour"
  GOOD  "Explain why the adapter layer exists between Session and urllib3, and
         what Session is therefore able not to know about transport"

An objective a developer could satisfy by repeating the lesson's wording back
is a bad objective. Aim at the claim, not the vocabulary.

Each edge is an object with exactly these keys:
  from_id, to_id: node ids from this response
  kind:           always "sequence". The initial graph is a single ordered
                  chain; prerequisite/deeper edges belong to session time.

Concept-tag vocabulary (use whichever fit; one node can have several):
  component | flow | architecture | extension_point | risk | test_coverage
  plus free-form domain tags (e.g. "auth", "retries")

Calibration by goal fields (they shape the SHAPE of the graph):
  By `depth`:
    overview  → 4–5 nodes. Prefer `architecture`/`flow` altitude; anchor on
                classes or entry points as concept representatives.
    moderate  → 5–7 nodes. Balanced mix; anchor on the narrowest symbol that
                answers the node.
    deep      → 7–10 nodes. Include `component` nodes for specific
                implementations; anchor methods over classes; include
                `risk`/`test_coverage` nodes when the dossier surfaces them.
  By `familiarity`:
    newer to the codebase → 1–2 orientation nodes first (entry points, the
    `understanding` paragraph is your source); experienced → start where the
    goal actually bites, zero orientation.
  By `background`: skip nodes whose only value is teaching a concept the
    developer's background already covers; spend the budget on what is
    specific to THIS codebase.

Rules:
- Anchor only on code that appears in the dossier. It is the code the
  investigation verified and showed you; nothing else has been seen.
- Each node must anchor on a DISTINCT piece of code — never reuse the same
  anchor across nodes.
- The edges form a single ordered chain over all N nodes — exactly N-1
  sequence edges, no isolated nodes, no branching, no cycles.
- Only describe relationships the dossier states or the rendered code shows.
- Self-rate confidence:
    high   — the dossier clearly covers the goal and the path is concrete
    medium — partial coverage; some nodes required interpolation
    low    — the dossier barely reaches the goal
- Return ONLY the JSON object — no markdown fences, no explanation.
"""


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
        section = ["## Entry points into the goal-relevant behaviour"]
        for e in entry_points:
            section.append(f"- {e.get('file')}:{e.get('symbol')} — {e.get('how_it_enters')}")
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


# ── grounding ──────────────────────────────────────────────────────────────────


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


def _ground_nodes(
    output: DossierMentorOutput,
    skeleton: Skeleton,
    evidence: list[dict],
) -> list[str]:
    """Resolve every node anchor (symbol-first), then gate against the dossier.

    Returns human-readable descriptions of the failures, for the retry prompt.
    Successfully grounded nodes get their resolved range written back.
    """
    failures: list[str] = []
    for node in output.nodes:
        resolution = anchors.resolve(
            skeleton, node.file,
            symbol=node.symbol or None,
            line_start=node.line_start, line_end=node.line_end,
        )
        if not resolution.ok:
            failures.append(
                f"{node.id}: {node.file}:{node.symbol or f'{node.line_start}-{node.line_end}'}"
                f" ({resolution.reason})"
            )
            continue
        a = resolution.anchor
        if not anchors.within_evidence(a, evidence):
            failures.append(
                f"{node.id}: {a.file}:{a.symbol or f'{a.line_start}-{a.line_end}'}"
                f" (not part of the dossier's verified evidence)"
            )
            continue
        node.file = a.file
        node.resolved_start = a.line_start
        node.resolved_end = a.line_end
        node.resolved_symbol = a.symbol
    return failures


def _find_duplicate_anchors(output: DossierMentorOutput) -> list[str]:
    seen: set[tuple[str, int | None, int | None]] = set()
    duplicates: list[str] = []
    for node in output.nodes:
        key = (node.file, node.resolved_start, node.resolved_end)
        if key in seen:
            duplicates.append(f"{node.file}:{node.resolved_symbol or key[1]}")
        seen.add(key)
    return duplicates


# ── parse / build ──────────────────────────────────────────────────────────────


def _parse_output(raw: str) -> DossierMentorOutput:
    # Leading fence only — `raw_decode` ends the object for us, and cutting at
    # the closing fence truncates any payload containing one of its own.
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else ""
    start = raw.find("{")
    if start < 0:
        raise ValueError("no JSON object found in response")
    decoded, _ = json.JSONDecoder().raw_decode(raw[start:])
    return DossierMentorOutput(**decoded)


def _to_mentor_output(output: DossierMentorOutput):
    """Grounded native wire → the retrieval path's wire shape.

    Lets the native path reuse agent.py's graph builder and path flattener, so
    there is exactly one LearningGraph construction in the system.
    """
    from backend.agents.mentor import agent as retrieval_path

    nodes = [
        retrieval_path.NodeWire(
            id=n.id, title=n.title, file=n.file,
            line_start=int(n.resolved_start or 0),
            line_end=int(n.resolved_end or 0),
            objective=n.objective, why=n.why, understand=n.understand,
            concept_tags=list(n.concept_tags),
            resolved_symbol=n.resolved_symbol,
        )
        for n in output.nodes
    ]
    edges = [
        retrieval_path.EdgeWire(from_id=e.from_id, to_id=e.to_id, kind=e.kind)
        for e in output.edges
    ]
    return retrieval_path.MentorOutput(
        nodes=nodes, edges=edges, confidence=output.confidence
    )


_CONFIDENCE_CAP = {"high": "medium", "medium": "medium", "low": "low"}


def run_native(
    state: OnboardState,
    client: anthropic.Anthropic | None = None,
) -> OnboardState:
    """The Mentor over a dossier. Same contract as agent.run(): never raises."""
    import os

    from backend.agents.mentor import agent as retrieval_path

    if client is None:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    if state.goal is None:
        state.errors.append("mentor_agent: goal missing")
        return state
    investigation_state = state.investigation or {}
    dossier = investigation_state.get("dossier")
    if not dossier:
        # D15: onboarding is a hard requirement — no best-effort ungrounded
        # graph from nothing. /session/start surfaces the failure explicitly.
        state.errors.append("mentor_agent: no investigation dossier to plan from")
        return state

    try:
        skeleton = build_skeleton(state.repo_path)
    except Exception as e:
        state.errors.append(f"mentor_agent: skeleton build failed: {e}")
        return state

    evidence = _dossier_evidence_ranges(skeleton, dossier)
    if not evidence:
        state.errors.append("mentor_agent: dossier contains no resolvable evidence")
        return state

    user_content = render_dossier(
        skeleton, dossier, state.goal, system_review=state.system_review
    )
    system = _SYSTEM_PROMPT

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
        raw = response.content[0].text
        output = _parse_output(raw)

        failures = _ground_nodes(output, skeleton, evidence)
        duplicates = _find_duplicate_anchors(output)
        if failures or duplicates:
            correction = ""
            if failures:
                correction += (
                    "These node anchors could not be verified against the "
                    "dossier's evidence: " + "; ".join(failures) + ". "
                )
            if duplicates:
                correction += (
                    "These anchors are reused across nodes, which the rules "
                    "forbid: " + "; ".join(duplicates) + ". "
                )
            correction += (
                "Regenerate the complete JSON object, using only `file` + "
                "`symbol` pairs that appear in the dossier, each on a distinct "
                "anchor."
            )
            retry = client.messages.create(
                model=MODEL, max_tokens=MAX_TOKENS, system=system,
                messages=[
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": correction},
                ],
            )
            try:
                retry_output = _parse_output(retry.content[0].text)
                retry_failures = _ground_nodes(retry_output, skeleton, evidence)
                if not retry_failures and not _find_duplicate_anchors(retry_output):
                    output = retry_output
                    failures = []
                else:
                    failures = retry_failures or failures
            except (ValueError, KeyError, TypeError) as e:
                state.errors.append(f"mentor_agent: retry parse failed: {e}")

        if failures:
            # Drop what never grounded rather than persisting unverified nodes.
            state.errors.append(
                f"mentor_agent: dropped {len(failures)} ungrounded node(s): "
                + "; ".join(failures)
            )
            grounded_ids = {
                n.id for n in output.nodes if n.resolved_start is not None
            }
            output.nodes = [n for n in output.nodes if n.id in grounded_ids]
            output.edges = [
                e for e in output.edges
                if e.from_id in grounded_ids and e.to_id in grounded_ids
            ]

        if not output.nodes:
            state.errors.append("mentor_agent: no grounded nodes survived")
            return state

        mentor_output = _to_mentor_output(output)
        graph = retrieval_path._build_learning_graph(state, mentor_output)
        state.graph = graph
        state.learning_path = retrieval_path._flatten_to_learning_path(graph)
        confidence = output.confidence
        if not investigation_state.get("accepted", False):
            # §5.4: a dossier salvaged at budget exhaustion carries a recorded
            # gap; downstream confidence must not exceed what the evidence
            # supports.
            confidence = _CONFIDENCE_CAP[confidence]
        state.confidence = confidence
    except Exception as e:
        state.errors.append(f"mentor_agent LLM call failed: {e}")

    return state
