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
# Deferred (see phase3.md Part 6): "deeper" (needs a return pointer), "simpler"
# (a Teaching re-render, not a structural change), reorder, auto-raise-depth.

import json
import os

import anthropic
from pydantic import BaseModel

from backend.agents.language import language_instruction
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.pipeline.state import OnboardState
from backend.rag.retrieval import retrieve_supporting_chunks


MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024

# How many candidate chunks to offer Sonnet when generating a prerequisite.
CANDIDATE_COUNT = 5


class _NodeWire(BaseModel):
    title: str
    file: str
    line_start: int
    line_end: int
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


def _generate_prerequisite_node(
    state: OnboardState, anchor: LearningNode, client: anthropic.Anthropic
) -> LearningNode | None:
    tags = ", ".join(anchor.concept_tags) if anchor.concept_tags else ""
    query = f"foundational concepts needed before understanding {anchor.title}. {tags}"

    existing = {
        (n.code_anchor.file, n.code_anchor.line_start, n.code_anchor.line_end)
        for n in state.graph.nodes.values()
    }
    try:
        candidates = retrieve_supporting_chunks(
            state, query, exclude=existing, top_k=CANDIDATE_COUNT
        )
    except Exception as e:
        state.errors.append(f"mutator: prerequisite retrieval failed: {e}")
        return None
    if not candidates:
        return None

    user_content = _build_prereq_prompt(anchor, candidates, state.goal or {})
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_PREREQ_SYSTEM_PROMPT + language_instruction(state.goal),
            messages=[{"role": "user", "content": user_content}],
        )
        wire = _parse_node(response.content[0].text)
    except Exception as e:
        state.errors.append(f"mutator: prerequisite generation failed: {e}")
        return None

    grounded_file = _ground_node(wire, candidates)
    if grounded_file is None:
        state.errors.append(
            f"mutator: generated prerequisite anchor not in candidates "
            f"({wire.file}:{wire.line_start}-{wire.line_end}); skipping insert"
        )
        return None

    return LearningNode(
        title=wire.title,
        code_anchor=CodeAnchor(
            file=grounded_file,
            line_start=wire.line_start,
            line_end=wire.line_end,
        ),
        concept_tags=list(wire.concept_tags),
        lesson_brief={"why": wire.why, "understand": wire.understand},
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
  why:          one sentence — why this is a prerequisite for the confused node
  understand:   one sentence — what the developer should take away
  concept_tags: list of short concept tags (≤ 4)

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
    anchor: LearningNode, candidates: list[dict], goal: dict
) -> str:
    brief = anchor.lesson_brief or {}
    chunk_lines = []
    for c in candidates:
        chunk_lines.append(
            f"[{c['type'].upper()}] {c['name']} — "
            f"{c['file']} (lines {c['start_line']}–{c['end_line']})\n{c['content']}"
        )
    return (
        f"Developer profile:\n"
        f"  familiarity with THIS codebase: {goal.get('familiarity', 'unknown')}\n"
        f"  background: {goal.get('background', 'unknown')}\n"
        f"  experience level: {goal.get('experience_level', 'unknown')}\n\n"
        f"The developer was confused while learning this node:\n"
        f"  title: {anchor.title}\n"
        f"  why: {brief.get('why', '')}\n"
        f"  understand: {brief.get('understand', '')}\n"
        f"  concepts: {', '.join(anchor.concept_tags) if anchor.concept_tags else '—'}\n\n"
        f"Candidate chunks for the prerequisite:\n" + "\n\n".join(chunk_lines)
    )


def _parse_node(raw: str) -> _NodeWire:
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
    return _NodeWire(**decoded)


def _normalize_path(p: str) -> str:
    return p.replace("\\", "/")


def _ground_node(wire: _NodeWire, candidates: list[dict]) -> str | None:
    """Return the canonical file path if the wire anchor matches a candidate
    chunk (exact or package-prefix-suffix), else None."""
    sf = _normalize_path(wire.file)
    start, end = wire.line_start, wire.line_end
    by_range: dict[tuple[int, int], list[str]] = {}
    exact: set[tuple[str, int, int]] = set()
    for c in candidates:
        cf = _normalize_path(c["file"])
        exact.add((cf, c["start_line"], c["end_line"]))
        by_range.setdefault((c["start_line"], c["end_line"]), []).append(cf)

    if (sf, start, end) in exact:
        return sf
    matches = [
        cf
        for cf in by_range.get((start, end), [])
        if cf == sf or cf.endswith("/" + sf) or sf.endswith("/" + cf)
    ]
    if len(matches) == 1:
        return matches[0]
    return None
