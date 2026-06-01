# Mentor Agent — owns the learning graph for the session.
#
# Phase 3 evolution: emits nodes + edges instead of a flat list of steps. The
# agent's job grows over future parts:
#   - Part 2 (this file): generate the initial sequence graph from goal +
#     module_map + RAG. All edges are "sequence".
#   - Part 6: gain a mutator that reacts to user signals — inserts
#     prerequisite nodes when the Grader flags confusion, hangs "deeper"
#     detours when the user asks to dive in, reorders or skips.
#
# Single Sonnet call per generation. The Phase 1 `learning_path` list is now
# *derived* from the graph (flatten the sequence) so /onboard still returns the
# same shape — no second LLM call.
#
# Mirrors the Code Structure Agent pattern: client injected, errors appended
# to state.errors, never raises.

import json
import os
from typing import Callable, Literal

import anthropic
from pydantic import BaseModel

from backend.learning.graph import (
    CodeAnchor,
    LearningGraph,
    LearningNode,
)
from backend.pipeline.state import OnboardState
from backend.rag.retrieval import effective_module_map, retrieve_chunks


MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096


# ── Wire-format Pydantic models ────────────────────────────────────────────────
#
# These mirror Sonnet's JSON output exactly. The agent translates them into
# the real LearningGraph dataclasses (with UUID node IDs) before writing to
# state. Keeping the wire shape separate from the persisted shape means
# Sonnet works with simple positional IDs ("n1", "n2") instead of UUIDs.


class NodeWire(BaseModel):
    id: str                  # local identifier, only valid within this response
    title: str
    file: str
    line_start: int
    line_end: int
    why: str                 # → lesson_brief["why"]
    understand: str          # → lesson_brief["understand"]
    concept_tags: list[str]


class EdgeWire(BaseModel):
    from_id: str
    to_id: str
    # Only "sequence" in Part 2. "prerequisite" and "deeper" arrive with the
    # Part 6 mutator. Keeping the field permissive now means the wire format
    # is stable when the mutator lands.
    kind: Literal["sequence", "prerequisite", "deeper"] = "sequence"


class MentorOutput(BaseModel):
    nodes: list[NodeWire]
    edges: list[EdgeWire]
    confidence: Literal["high", "medium", "low"]


# ── Anchor-quality checks (operate on the wire format) ─────────────────────────


def _find_duplicate_anchors(
    output: MentorOutput,
) -> list[tuple[str, tuple[int, int]]]:
    """Distinct-anchor rule: each node must reference a different chunk."""
    seen: set[tuple[str, tuple[int, int]]] = set()
    duplicates: list[tuple[str, tuple[int, int]]] = []
    for node in output.nodes:
        key = (node.file, (node.line_start, node.line_end))
        if key in seen and key not in duplicates:
            duplicates.append(key)
        seen.add(key)
    return duplicates


def _normalize_path(p: str) -> str:
    """Fold Windows backslashes to forward slashes for cross-run comparison."""
    return p.replace("\\", "/")


def _ground_anchors(
    output: MentorOutput, chunks: list[dict]
) -> list[tuple[str, tuple[int, int]]]:
    """Match every node anchor against a retrieved chunk; auto-correct prefix
    stripping; return any anchors that still cannot be grounded.

    Two grounding rules:
      1. Exact:  (normalized node.file, start, end) is a known chunk anchor.
      2. Suffix: line range matches a chunk's range and the node's file is a
                 path-suffix of the chunk's file (LLM dropped the package
                 prefix). Auto-corrected by rewriting node.file.
    """
    chunk_files_by_range: dict[tuple[int, int], list[str]] = {}
    valid_keys: set[tuple[str, int, int]] = set()
    for c in chunks:
        cf = _normalize_path(c["file"])
        valid_keys.add((cf, c["start_line"], c["end_line"]))
        chunk_files_by_range.setdefault(
            (c["start_line"], c["end_line"]), []
        ).append(cf)

    invalid: list[tuple[str, tuple[int, int]]] = []
    for node in output.nodes:
        sf = _normalize_path(node.file)
        start, end = node.line_start, node.line_end

        if (sf, start, end) in valid_keys:
            node.file = sf  # canonicalize separators
            continue

        candidates = [
            cf
            for cf in chunk_files_by_range.get((start, end), [])
            if cf == sf or cf.endswith("/" + sf) or sf.endswith("/" + cf)
        ]
        if len(candidates) == 1:
            node.file = candidates[0]
            continue

        invalid.append((node.file, (start, end)))

    return invalid


# ── Prompts ────────────────────────────────────────────────────────────────────


_SYSTEM_PROMPT = """\
You are a mentor guiding a developer through an unfamiliar Python codebase.

Given the user's goal, the repository's module map, and a set of code chunks
retrieved via semantic search, produce a JSON object with exactly these keys:
  nodes:      list of 5–8 learning nodes (each anchored on one retrieved chunk)
  edges:      list of edges connecting the nodes into a teaching order
  confidence: one of "high", "medium", "low"

Each node is an object with exactly these keys:
  id:           a short local identifier you choose (e.g. "n1", "n2") — used
                only inside this response so edges can reference nodes; must
                be unique across all nodes
  title:        short imperative title
  file:         path to the file (must come from the retrieved chunks)
  line_start:   start line — copied VERBATIM from a retrieved chunk
  line_end:     end line — copied VERBATIM from the SAME chunk
  why:          one sentence — why this node matters for the user's goal
  understand:   one sentence — what the user should take away
  concept_tags: list of short concept tags (≤ 4 entries)

Each edge is an object with exactly these keys:
  from_id:  id of the source node (must match a node id above)
  to_id:    id of the destination node (must match a node id above)
  kind:     always "sequence" in this response

Rules:
- Use only files that appear in the retrieved chunks. Never invent file paths.
- Copy file paths VERBATIM from the retrieved chunk metadata, including any
  package prefix (e.g. "fastapi/params.py", not just "params.py").
- Copy line_start and line_end VERBATIM from the chunk's start_line / end_line
  — do NOT pick round numbers or guess ranges.
- Source code is the implementation truth. Tests and examples are supporting
  behavioral evidence — anchor nodes on source whenever both source and a
  test/example chunk can answer a node. Cite a test or example only when it
  reproduces the exact failure mode, shows a concrete usage idiom, or
  illustrates the extension surface the user must touch.
- 5–8 nodes total. Each node must anchor on a DISTINCT chunk — never reuse
  the same (file, line_start, line_end) across nodes.
- The edges must form a single ordered chain over all nodes — exactly N-1
  edges of kind="sequence" if there are N nodes. Each node appears exactly
  once in the chain. The first node is the starting point; the last node is
  where the user ends up. No isolated nodes, no branching, no cycles.
- Order matters: each node builds on the previous one in the sequence.
- Prefer the narrowest chunk that answers the node. When both an enclosing
  class and one of its methods are retrieved, anchor on the method's
  line range — a whole class is rarely the right teaching unit.
- Only describe inheritance, imports, or call relationships that are
  visible in the retrieved chunks. Do not infer relationships from class
  names alone.
- Self-rate confidence:
    high   — retrieved chunks clearly cover the user's goal and the path is concrete
    medium — chunks partially cover the goal, some nodes required interpolation
    low    — chunks barely related to the goal; you are mostly guessing
- Return ONLY the JSON object — no markdown fences, no explanation.
"""


def _format_module_map(module_map: dict) -> str:
    lines = []
    for name, entry in module_map.items():
        lines.append(
            f"- {name}: {entry['purpose']} "
            f"(exports: {', '.join(entry['exports'])})"
        )
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


def _common_context(goal: dict, module_map: dict, chunks: list[dict]) -> str:
    return (
        f"User goal: {goal['primary_goal']}\n"
        f"Experience level: {goal['experience_level']}\n"
        f"Depth requested: {goal['depth']}\n\n"
        f"Module map:\n{_format_module_map(module_map)}\n\n"
        f"Retrieved code chunks:\n{_format_chunks(chunks)}"
    )


def _build_understand_system_prompt(
    goal: dict, module_map: dict, chunks: list[dict]
) -> str:
    return (
        f"{_common_context(goal, module_map, chunks)}\n\n"
        f"Goal type: understand_system. The user wants a high-level tour. "
        f"Pick nodes that span the major modules and show how they connect. "
        f"Favour breadth over depth — touch entry points, not internals."
    )


def _build_understand_component_prompt(
    goal: dict, module_map: dict, chunks: list[dict]
) -> str:
    return (
        f"{_common_context(goal, module_map, chunks)}\n\n"
        f"Goal type: understand_component. Focus area: {goal['focus_area']}. "
        f"Go deep into this area. Prefer fewer files at greater depth over "
        f"a broad tour. Each node should explain a specific abstraction or flow."
    )


def _build_contribute_code_prompt(
    goal: dict, module_map: dict, chunks: list[dict]
) -> str:
    contribution = goal.get("contribution_context", "(none provided)")
    return (
        f"{_common_context(goal, module_map, chunks)}\n\n"
        f"Goal type: contribute_code. Contribution context: {contribution}\n"
        f"Order nodes so the user understands extension points first, then "
        f"the file(s) most likely to need editing. The final node should "
        f"land at the most likely insertion site."
    )


def _build_debug_issue_prompt(
    goal: dict, module_map: dict, chunks: list[dict]
) -> str:
    error = goal.get("error_description", "(none provided)")
    tried = goal.get("tried_so_far", "(none provided)")
    return (
        f"{_common_context(goal, module_map, chunks)}\n\n"
        f"Goal type: debug_issue.\n"
        f"Error: {error}\n"
        f"Tried so far: {tried}\n"
        f"Trace the execution path that produces this error. Each node should "
        f"narrow the search — start at the entry point, end at the most likely "
        f"source of the bug."
    )


_PROMPT_BUILDERS: dict[str, Callable[[dict, dict, list[dict]], str]] = {
    "understand_system": _build_understand_system_prompt,
    "understand_component": _build_understand_component_prompt,
    "contribute_code": _build_contribute_code_prompt,
    "debug_issue": _build_debug_issue_prompt,
}


def _parse_output(raw: str) -> MentorOutput:
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
    return MentorOutput(**decoded)


# ── Wire → LearningGraph translation ───────────────────────────────────────────


def _build_learning_graph(state: OnboardState, output: MentorOutput) -> LearningGraph:
    """Construct a LearningGraph from validated wire output.

    Wire IDs (Sonnet's "n1", "n2", ...) get remapped to fresh UUIDs so
    LearningNode.id holds a real graph-wide identifier. The mapping is local
    to this function — the wire IDs never leave the agent.
    """
    graph = LearningGraph(repo_url=state.repo_url, goal=state.goal)
    graph.doc_context = state.doc_context  # may be None if doc agent was skipped

    wire_to_uuid: dict[str, str] = {}
    for wire_node in output.nodes:
        node = LearningNode(
            title=wire_node.title,
            code_anchor=CodeAnchor(
                file=wire_node.file,
                line_start=wire_node.line_start,
                line_end=wire_node.line_end,
            ),
            concept_tags=list(wire_node.concept_tags),
            lesson_brief={"why": wire_node.why, "understand": wire_node.understand},
        )
        graph.add_node(node)
        wire_to_uuid[wire_node.id] = node.id

    for wire_edge in output.edges:
        from_uuid = wire_to_uuid.get(wire_edge.from_id)
        to_uuid = wire_to_uuid.get(wire_edge.to_id)
        if from_uuid is None or to_uuid is None:
            # Edge references an unknown node id — skip silently. The
            # prompt's "edges over all nodes" rule should prevent this; if it
            # happens we'd rather have a slightly incomplete graph than
            # crash the whole pipeline.
            continue
        graph.add_edge(from_uuid, to_uuid, kind=wire_edge.kind)

    # Set current_node_id to the head of the sequence — the node with no
    # incoming sequence edge. If there are multiple heads (shouldn't happen
    # given the prompt rule, but defend anyway), pick the first wire node.
    head = _find_sequence_head(graph, output)
    if head is not None:
        graph.set_current(head)

    return graph


def _find_sequence_head(graph: LearningGraph, output: MentorOutput) -> str | None:
    if not graph.nodes:
        return None
    incoming = {e.to_node_id for e in graph.edges if e.kind == "sequence"}
    for wire_node in output.nodes:
        # output.nodes preserves the order Sonnet emitted; the first one with
        # no incoming sequence edge is the natural head.
        candidate = None
        for nid, n in graph.nodes.items():
            if n.title == wire_node.title and (
                n.code_anchor.file == wire_node.file
                and n.code_anchor.line_start == wire_node.line_start
                and n.code_anchor.line_end == wire_node.line_end
            ):
                candidate = nid
                break
        if candidate and candidate not in incoming:
            return candidate
    # Fallback: any node not pointed at by a sequence edge.
    for nid in graph.nodes:
        if nid not in incoming:
            return nid
    return next(iter(graph.nodes))


def _flatten_to_learning_path(graph: LearningGraph) -> list[dict]:
    """Walk sequence edges in order, render each node as Phase 1 step JSON.

    The /onboard endpoint still wants the flat step list, so we derive it
    from the graph rather than asking Sonnet for it twice. Same data, same
    Sonnet call.
    """
    if not graph.nodes:
        return []
    next_id: dict[str, str] = {
        e.from_node_id: e.to_node_id for e in graph.edges if e.kind == "sequence"
    }
    incoming = {e.to_node_id for e in graph.edges if e.kind == "sequence"}
    heads = [nid for nid in graph.nodes if nid not in incoming]
    if not heads:
        # No clear head — fall back to current_node_id, then any node.
        current = graph.current_node_id or next(iter(graph.nodes))
    else:
        current = heads[0]

    path: list[dict] = []
    seen: set[str] = set()
    step = 1
    while current is not None and current not in seen:
        seen.add(current)
        node = graph.nodes[current]
        path.append({
            "step": step,
            "title": node.title,
            "file": node.code_anchor.file,
            "line_range": [node.code_anchor.line_start, node.code_anchor.line_end],
            "why": node.lesson_brief.get("why", ""),
            "understand": node.lesson_brief.get("understand", ""),
            "concepts": list(node.concept_tags),
        })
        step += 1
        current = next_id.get(current)
    return path


# ── run ────────────────────────────────────────────────────────────────────────


def run(
    state: OnboardState,
    client: anthropic.Anthropic | None = None,
) -> OnboardState:
    if client is None:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    if state.goal is None:
        state.errors.append("mentor_agent: goal missing")
        return state

    if state.module_map is None:
        state.errors.append("mentor_agent: module_map missing")
        return state

    if not state.chunks_embedded:
        state.errors.append("mentor_agent: chunks not embedded")
        return state

    goal_type = state.goal.get("goal_type")
    if goal_type not in _PROMPT_BUILDERS:
        state.errors.append(f"mentor_agent: unknown goal_type {goal_type!r}")
        return state

    try:
        chunks = retrieve_chunks(state)
    except Exception as e:
        state.errors.append(f"mentor_agent retrieval failed: {e}")
        return state

    builder = _PROMPT_BUILDERS[goal_type]
    user_content = builder(state.goal, effective_module_map(state), chunks)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        raw = response.content[0].text
        output = _parse_output(raw)

        # Distinct-anchor retry: the prompt forbids reusing a chunk across
        # nodes; Sonnet still does it occasionally. Showing it its own bad
        # output usually fixes the second pass.
        duplicates = _find_duplicate_anchors(output)
        if duplicates:
            retry_raw, retry_output = _retry_distinct_anchors(
                client, user_content, raw, duplicates
            )
            if retry_output is not None and not _find_duplicate_anchors(retry_output):
                output = retry_output
                raw = retry_raw
            else:
                state.errors.append(
                    f"mentor_agent: duplicate anchors persisted after retry: "
                    f"{[f'{f}:{r[0]}-{r[1]}' for f, r in duplicates]}"
                )

        # Grounding retry: every node must anchor on a real retrieved chunk.
        # _ground_anchors fixes prefix-stripped paths silently; anything that
        # still doesn't match triggers a corrective retry.
        invalid = _ground_anchors(output, chunks)
        if invalid:
            retry_raw, retry_output = _retry_grounded_anchors(
                client, user_content, raw, invalid, chunks
            )
            if retry_output is not None and not _ground_anchors(retry_output, chunks):
                output = retry_output
            else:
                state.errors.append(
                    f"mentor_agent: ungrounded anchors persisted after retry: "
                    f"{[f'{f}:{r[0]}-{r[1]}' for f, r in invalid]}"
                )

        graph = _build_learning_graph(state, output)
        state.graph = graph
        state.learning_path = _flatten_to_learning_path(graph)
        state.confidence = output.confidence
    except Exception as e:
        state.errors.append(f"mentor_agent LLM call failed: {e}")

    return state


# ── Retry helpers ──────────────────────────────────────────────────────────────


def _retry_distinct_anchors(
    client: anthropic.Anthropic,
    user_content: str,
    previous_raw: str,
    duplicates: list[tuple[str, tuple[int, int]]],
) -> tuple[str, MentorOutput | None]:
    """Ask the LLM to regenerate with distinct anchors.

    Returns ``(raw_text, parsed_output)``. ``parsed_output`` is ``None`` if
    the retry response failed to parse — callers should keep the original
    output in that case.
    """
    dupe_str = ", ".join(f"{f} lines {r[0]}-{r[1]}" for f, r in duplicates)
    correction = (
        f"Your previous response reused these (file, line range) anchors "
        f"across multiple nodes: {dupe_str}. The rules require each node "
        f"to anchor on a DISTINCT chunk. Regenerate the JSON object with "
        f"distinct (file, line_start, line_end) triples for every node. "
        f"Return ONLY the JSON object."
    )
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": previous_raw},
            {"role": "user", "content": correction},
        ],
    )
    raw = response.content[0].text
    try:
        return raw, _parse_output(raw)
    except Exception:
        return raw, None


def _format_anchor_inventory(chunks: list[dict]) -> str:
    """Compact list of (file, line range) anchors the LLM is allowed to use."""
    lines = []
    for c in chunks:
        lines.append(
            f"  - {_normalize_path(c['file'])} lines {c['start_line']}-{c['end_line']}"
        )
    return "\n".join(lines)


def _retry_grounded_anchors(
    client: anthropic.Anthropic,
    user_content: str,
    previous_raw: str,
    invalid: list[tuple[str, tuple[int, int]]],
    chunks: list[dict],
) -> tuple[str, MentorOutput | None]:
    """Ask the LLM to regenerate using anchors that come from real chunks."""
    bad = ", ".join(f"{f} lines {r[0]}-{r[1]}" for f, r in invalid)
    inventory = _format_anchor_inventory(chunks)
    correction = (
        f"Your previous response used these (file, line range) anchors that "
        f"are NOT in the retrieved chunks: {bad}. Every node must anchor on "
        f"a real retrieved chunk — both the file path (copied verbatim, "
        f"including the package prefix) and the line range (copied verbatim "
        f"from the chunk metadata, not rounded or invented).\n\n"
        f"The complete set of allowed anchors is:\n{inventory}\n\n"
        f"Regenerate the JSON object using only anchors from that list. "
        f"Return ONLY the JSON object."
    )
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": previous_raw},
            {"role": "user", "content": correction},
        ],
    )
    raw = response.content[0].text
    try:
        return raw, _parse_output(raw)
    except Exception:
        return raw, None
