# Mentor mutator — reshapes the learning graph in response to signals.
#
# This is the Mentor's second life (Part 6). The initial-graph generator
# (agent.py) runs once at session start; the mutator runs on each user/Grader
# signal and decides whether to change the graph's structure.
#
# Entry point:
#   mutate(state, signal, client) → applies the signal, records what happened
#       in state.last_mutation, returns state. Never raises — a failed mutation
#       leaves the graph untouched.
#
# Signals handled in v1:
#   - "skip"          → pure Python: mark the current node skipped, advance.
#   - "prerequisite"  → Sonnet: generate a foundational node from real chunks
#                       and splice it in before the current node (triggered when
#                       the Grader classifies a response as "confused").
#
# Candidate evidence comes from two grounded sources and NO retrieval: the
# Dossier first (goal-specific), then the Skeleton (whole-repository structure)
# when the graph has already consumed the dossier's local neighbourhood. See
# `candidate_pool`. Declining to insert is a supported outcome, distinct from a
# failure to produce one.
#
# Deferred (see phase3.md Part 6): "deeper" (needs a return pointer), "simpler"
# (a Teaching re-render, not a structural change), reorder, auto-raise-depth.

import json
import os
from dataclasses import dataclass

import anthropic
from pydantic import BaseModel

from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.pipeline.state import OnboardState
from backend.repo import anchors, dossier_context, dossier_store, structure
from backend.repo.skeleton import Skeleton, build_skeleton, normalize_path


MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024

# How many candidate chunks to offer Sonnet when generating a prerequisite.
CANDIDATE_COUNT = 5


class _NodeWire(BaseModel):
    title: str
    file: str
    line_start: int
    line_end: int
    # An inserted node is taught and graded like any other, so it carries the
    # same contract (learning-engine.md §8.1). Defaulted for the same reason the
    # planner's is: an omission costs one weaker warm-up, not the remediation.
    objective: str = ""
    why: str
    understand: str
    concept_tags: list[str]


# ── dispatcher ──────────────────────────────────────────────────────────────


def mutate(
    state: OnboardState,
    signal: str,
    client: anthropic.Anthropic | None = None,
) -> OnboardState:
    if state.graph is None:
        state.errors.append("mutator: graph missing")
        state.last_mutation = {"kind": "none"}
        return state

    current = state.graph.current_node_id
    if current is None or current not in state.graph.nodes:
        state.errors.append("mutator: no current node")
        state.last_mutation = {"kind": "none"}
        return state

    if signal == "skip":
        return _mutate_skip(state, current)
    if signal == "prerequisite":
        if client is None:
            client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        return _mutate_prerequisite(state, current, client)

    state.errors.append(f"mutator: unknown signal {signal!r}")
    state.last_mutation = {"kind": "none"}
    return state


# ── skip (pure Python) ────────────────────────────────────────────────────────


def _mutate_skip(state: OnboardState, current: str) -> OnboardState:
    graph = state.graph
    graph.override(current, "skip")  # marks visited + records the override
    nxt = graph.next_in_path(current)
    if nxt is not None:
        graph.set_current(nxt)
    state.last_mutation = {"kind": "skip", "anchor_node_id": current, "advanced_to": nxt}
    return state


# ── prerequisite (Sonnet) ──────────────────────────────────────────────────────


def _has_prerequisite(graph: LearningGraph, node_id: str) -> bool:
    # True if a prerequisite node has already been spliced in before this one.
    return any(
        e.kind == "prerequisite" and e.to_node_id == node_id for e in graph.edges
    )


def _mutate_prerequisite(
    state: OnboardState, current: str, client: anthropic.Anthropic
) -> OnboardState:
    graph = state.graph

    # Guard: at most one prerequisite per node. Repeated confusion shouldn't
    # stack endless prereqs (and shouldn't burn a Sonnet call each time).
    if _has_prerequisite(graph, current):
        state.last_mutation = {"kind": "none", "reason": "prerequisite_exists"}
        return state

    anchor = graph.nodes[current]
    new_node = _generate_prerequisite_node(state, anchor, client)
    if isinstance(new_node, _Declined):
        # A real answer, not a failure: candidates were offered and none was a
        # smaller foundation than the node the developer is already on. Inserting
        # something anyway would pad the path to look responsive.
        state.last_mutation = {
            "kind": "none",
            "reason": "no_useful_prerequisite",
            "rationale": new_node.reason,
        }
        return state
    if new_node is None:
        # Generation failed or produced nothing groundable — leave graph as-is.
        state.last_mutation = {"kind": "none", "reason": "generation_failed"}
        return state

    graph.insert_before(current, new_node, kind="prerequisite")
    graph.set_current(new_node.id)  # teach the prerequisite first
    state.last_mutation = {
        "kind": "prerequisite",
        "new_node_id": new_node.id,
        "anchor_node_id": current,
    }
    return state


def candidate_pool(
    state: OnboardState, anchor: LearningNode
) -> list[dossier_context.PrereqCandidate]:
    """D8, step 1 of 3: the STRUCTURAL CANDIDATE SET, from two grounded sources.

    THE DOSSIER COMES FIRST. It is the goal-specific understanding: the
    prerequisites the investigation recorded for this node, what it depends on,
    the contracts it is written against, the flow step before it. Those
    candidates carry a reason tied to the user's goal, which nothing derived from
    structure alone can.

    THE SKELETON WIDENS IT. The dossier is selective by design and the Mentor
    consumes most of it into nodes, so once the taught nodes are excluded the
    goal-specific neighbourhood is frequently empty — measured at 7 of 8 real
    confusion events. Layer A still knows the whole repository: base classes,
    methods, callees, callers, module dependencies. That is where to look when
    goal-specific evidence has run out, and it is grounded rather than similar.

    Neither source decides anything. Ordering here is provenance, not ranking:
    the choice is the model's, in step 2, and "none of these" is a legal answer.
    """
    skeleton = build_skeleton(state.repo_path)
    existing_ranges, existing_symbols = _taught(state.graph)

    candidates: list[dossier_context.PrereqCandidate] = []
    dossier = _session_dossier(state)
    if dossier is not None:
        try:
            candidates = dossier_context.prerequisite_candidates(
                skeleton, dossier,
                anchor.code_anchor.file,
                symbol=anchor.code_anchor.symbol,
                line_start=anchor.code_anchor.line_start,
                line_end=anchor.code_anchor.line_end,
                exclude=existing_ranges,
            )
        except Exception as e:
            state.errors.append(f"mutator: dossier candidates failed: {e}")

    if len(candidates) < CANDIDATE_COUNT:
        already = {(c.file, c.symbol) for c in candidates}
        try:
            widened = structure.neighbour_candidates(
                skeleton,
                anchor.code_anchor.file,
                symbol=anchor.code_anchor.symbol,
                line_start=anchor.code_anchor.line_start,
                line_end=anchor.code_anchor.line_end,
                exclude=existing_ranges,
                exclude_symbols=existing_symbols,
                limit=CANDIDATE_COUNT - len(candidates),
            )
        except Exception as e:
            state.errors.append(f"mutator: skeleton candidates failed: {e}")
            widened = []
        candidates.extend(c for c in widened if (c.file, c.symbol) not in already)
    return candidates


def _taught(graph: LearningGraph) -> tuple[set[tuple], set[tuple]]:
    """What the graph already covers, by range AND by symbol identity.

    Two keys because ranges are commit-derived and symbols are not: a node
    persisted before the checkout moved can hold a stale range for code the
    graph genuinely already teaches. Deliberately NOT containment-based — a
    different symbol that happens to live inside a taught class is a different
    lesson, and discarding it would make the pool emptier than the evidence
    warrants.
    """
    ranges = {
        (n.code_anchor.file, n.code_anchor.line_start, n.code_anchor.line_end)
        for n in graph.nodes.values()
    }
    symbols = {
        (n.code_anchor.file, n.code_anchor.symbol)
        for n in graph.nodes.values() if n.code_anchor.symbol
    }
    return ranges, symbols


@dataclass(frozen=True)
class _Declined:
    """The selection step judged that no candidate is a smaller foundation."""

    reason: str


def _generate_prerequisite_node(
    state: OnboardState, anchor: LearningNode, client: anthropic.Anthropic
) -> LearningNode | _Declined | None:
    """A prerequisite node, a `_Declined`, or None on failure.

    The three outcomes are genuinely different and the caller reports them
    differently: "no useful prerequisite exists here" is a correct answer, not a
    malfunction, and must not read as one.
    """
    structural = candidate_pool(state, anchor)
    if not structural:
        return None

    try:
        candidates = _candidates_as_chunks(state.repo_path, structural)
    except Exception as e:
        state.errors.append(f"mutator: candidate rendering failed: {e}")
        return None
    if not candidates:
        return None

    # D8, step 2 of 3: PEDAGOGICAL SELECTION — a reasoning step, not a lookup.
    user_content = _build_prereq_prompt(
        anchor, candidates, state.goal or {}, structural=structural
    )
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_PREREQ_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        raw = response.content[0].text
        declined = _declined_reason(raw)
        if declined is not None:
            return _Declined(declined)
        wire = _parse_node(raw)
    except Exception as e:
        state.errors.append(f"mutator: prerequisite generation failed: {e}")
        return None

    try:
        skeleton = build_skeleton(state.repo_path)
    except Exception as e:
        state.errors.append(f"mutator: skeleton build failed: {e}")
        return None

    grounded = _ground_node(wire, candidates, skeleton)
    if grounded is not None and grounded.as_tuple() == (
        anchor.code_anchor.file,
        anchor.code_anchor.line_start,
        anchor.code_anchor.line_end,
    ):
        # A warm-up anchored on the very code the developer just failed on is
        # not a foundation — it re-shows the same snippet under a new title.
        state.errors.append(
            "mutator: prerequisite resolved to the confused node's own anchor "
            f"({grounded.file}:{grounded.line_start}-{grounded.line_end}); skipping insert"
        )
        return None
    if grounded is None:
        state.errors.append(
            f"mutator: generated prerequisite anchor not in candidates "
            f"({wire.file}:{wire.line_start}-{wire.line_end}); skipping insert"
        )
        return None

    return LearningNode(
        title=wire.title,
        code_anchor=CodeAnchor(
            file=grounded.file,
            line_start=grounded.line_start,
            line_end=grounded.line_end,
            symbol=grounded.symbol,
        ),
        concept_tags=list(wire.concept_tags),
        lesson_brief={
            "objective": wire.objective,
            "why": wire.why,
            "understand": wire.understand,
        },
    )


_PREREQ_SYSTEM_PROMPT = """\
A developer got confused while learning one node of a code-onboarding path. Your
job is to choose ONE foundational concept they likely need to understand FIRST,
anchored on one of the candidate code chunks provided.

Return a JSON object with exactly these keys:
  title:        short imperative title for the prerequisite node
  file:         path of the chosen candidate chunk (copied VERBATIM)
  line_start:   start line of the chosen chunk (copied VERBATIM)
  line_end:     end line of the chosen chunk (copied VERBATIM)
  objective:    the claim the developer should be able to MAKE once they have
                learned this warm-up — written as a claim, not a topic, and
                narrow enough that reaching it plausibly unblocks the node they
                got wrong. This is what their answer will be marked against.
  why:          one sentence — why this is a prerequisite for the confused node
  understand:   one sentence — what the developer should take away
  concept_tags: list of short concept tags (≤ 4)

If none of the candidates is genuinely more foundational than the node the
developer is already on, say so instead of choosing the least bad one. Return
exactly {"decision": "none", "reason": "<one sentence>"}. A path that grows a
warm-up nobody needed is worse than one that stays as it was — you are not
required to insert something.

Rules:
- Anchor on exactly ONE of the candidate chunks. Copy its file path and line
  range verbatim — never invent an anchor.
- The concept must be genuinely MORE foundational than the node the developer
  was confused about — something that, once understood, makes the harder node
  click.
- The developer's background and familiarity (in the user content) are a
  TIEBREAKER, not a primary signal. First, ensure the chosen prerequisite
  teaches the foundational concept that actually unblocks the confused node.
  AMONG candidates that do, prefer the one that aligns with what the developer
  reports knowing — skip prerequisites whose concept the developer's
  background suggests they already understand.
- Return ONLY the JSON object — no markdown fences, no preamble.
"""


def _build_prereq_prompt(
    anchor: LearningNode, candidates: list[dict], goal: dict,
    structural: list | None = None,
) -> str:
    brief = anchor.lesson_brief or {}
    # Why each candidate was offered, when the dossier supplied it. This is what
    # lets the selection step reason about foundations rather than guess from
    # code alone — "the confused node calls this" and "the investigation
    # recorded this concept as needed" are different kinds of evidence.
    reasons = {
        (c.file, c.symbol): f"[{c.source}] {c.rationale}"
        for c in (structural or [])
    }
    chunk_lines = []
    for c in candidates:
        why_offered = reasons.get((c["file"], c["name"]), "")
        header = (
            f"[{c['type'].upper()}] {c['name']} — "
            f"{c['file']} (lines {c['start_line']}–{c['end_line']})"
        )
        if why_offered:
            header += f"\n  offered because: {why_offered}"
        chunk_lines.append(f"{header}\n{c['content']}")
    return (
        f"Developer profile:\n"
        f"  familiarity with THIS codebase: {goal.get('familiarity', 'unknown')}\n"
        f"  background: {goal.get('background', 'unknown')}\n\n"
        f"The developer was confused while learning this node:\n"
        f"  title: {anchor.title}\n"
        f"  the claim they could not make: {anchor.objective() or '(none stated)'}\n"
        f"  why: {brief.get('why', '')}\n"
        f"  understand: {brief.get('understand', '')}\n"
        f"  concepts: {', '.join(anchor.concept_tags) if anchor.concept_tags else '—'}\n\n"
        f"Candidate chunks for the prerequisite:\n" + "\n\n".join(chunk_lines)
    )


def _declined_reason(raw: str) -> str | None:
    """The selection step's reason for answering "none of these", if it did.

    Checked before parsing, because a decline carries no anchor and would
    otherwise surface as a parse failure — reporting a correct judgement as a
    malfunction. The reason is kept rather than discarded: "every candidate is a
    peer-level helper, not a foundation" is the most useful thing the system can
    say about a confusion it chose not to act on.
    """
    try:
        start = raw.find("{")
        if start < 0:
            return None
        decoded, _ = json.JSONDecoder().raw_decode(raw[start:])
    except ValueError:
        return None
    if not isinstance(decoded, dict) or str(decoded.get("decision")) != "none":
        return None
    return str(decoded.get("reason") or "").strip() or "no reason given"


def _parse_node(raw: str) -> _NodeWire:
    # Strip a leading fence but never cut at the closing one: `raw_decode` stops
    # at the end of the object, and splitting on the next ``` truncates any
    # payload whose own strings contain a fence. See teaching's `_parse_output`,
    # where that cost a session its lesson.
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else ""
    start = raw.find("{")
    if start < 0:
        raise ValueError("no JSON object found in response")
    decoded, _ = json.JSONDecoder().raw_decode(raw[start:])
    return _NodeWire(**decoded)


def _normalize_path(p: str) -> str:
    return normalize_path(p)


def _candidates_as_chunks(repo_path: str, structural: list) -> list[dict]:
    """Structural candidates rendered in the chunk shape the prompt expects.

    Source is read from the repository at the resolved anchor, so the model
    still selects from real code — the dossier decides WHICH code is offered,
    not what the code says.
    """
    skeleton = build_skeleton(repo_path)
    chunks: list[dict] = []
    for candidate in structural:
        resolution = anchors.resolve(skeleton, candidate.file, symbol=candidate.symbol)
        if not resolution.ok:
            continue
        a = resolution.anchor
        content = skeleton.read_lines(a.file, a.line_start, a.line_end) or ""
        if not content.strip():
            continue
        chunks.append({
            "file": a.file,
            "start_line": a.line_start,
            "end_line": a.line_end,
            "type": "function",
            "name": a.symbol or candidate.symbol,
            "role": "source",
            "content": content,
        })
    return chunks


def _session_dossier(state: OnboardState) -> dict | None:
    """The investigation for this session, from state or from the store (D12)."""
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


def _ground_node(
    wire: _NodeWire, candidates: list[dict], skeleton: Skeleton
) -> anchors.ResolvedAnchor | None:
    """Verify a generated prerequisite anchor, or None if it cannot be trusted.

    Same two questions as the Mentor and Reviewer (repo-understanding.md
    Stage 0): does the anchor exist in the repository, and is it inside one of
    the candidate chunks the model was actually offered? A prerequisite that
    fails either check is dropped rather than inserted — an invented location is
    worse than no remediation.
    """
    resolution = anchors.resolve_within_evidence(
        skeleton,
        candidates,
        wire.file,
        line_start=wire.line_start,
        line_end=wire.line_end,
    )
    return resolution.anchor if resolution.ok else None
