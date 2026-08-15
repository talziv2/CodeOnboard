# Mentor Agent — the learning graph's wire format and construction.
#
# After Stage 5 this module owns three things and no prompt:
#   - the wire shape Sonnet answers in (NodeWire / EdgeWire / MentorOutput),
#   - turning that wire shape into a real LearningGraph with UUID ids and
#     resolved anchors,
#   - flattening the graph back to the Phase-1 `learning_path` list, which the
#     /onboard response still returns.
#
# The planning itself lives in `dossier.py`, which reasons over the Investigation
# Dossier. `run()` here is the single entry point every caller keeps using.
#
# Mirrors every other agent: client injected, errors appended to state.errors,
# never raises.

import json
from typing import Literal

import anthropic
from pydantic import BaseModel

from backend.learning.graph import (
    CodeAnchor,
    LearningGraph,
    LearningNode,
)
from backend.pipeline.state import OnboardState
from backend.repo.skeleton import normalize_path


MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096


def curriculum_enabled() -> bool:
    """Whether to plan objectives-first (B3) or with the pre-B3 node planner.

    `0` is the old planner, byte-identical — the migration discipline this
    codebase already used for the repository-understanding rewrite. Both paths
    produce a `LearningGraph` whose new fields are optional keys in JSON that
    already existed, so a graph from either path loads under either setting, and
    Teaching and the Grader have one implementation each (§12).

    Read per call rather than cached at import so tests can flip it with
    monkeypatch, which is the only place it changes mid-process.
    """
    import os

    return os.environ.get("CODEONBOARD_CURRICULUM", "0") == "1"


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
    objective: str = ""      # → lesson_brief["objective"] — see dossier.py
    why: str                 # → lesson_brief["why"]
    understand: str          # → lesson_brief["understand"]
    concept_tags: list[str]
    # Not emitted by the model — filled in by _ground_anchors from the symbol
    # index, and carried onto CodeAnchor.symbol. Keeping it on the wire model
    # avoids threading a parallel dict through the graph builder.
    resolved_symbol: str | None = None


class EdgeWire(BaseModel):
    from_id: str
    to_id: str
    # The Mentor only produces sequence chains at creation time. `prerequisite`
    # edges are introduced LATER by the Mutator in response to a real user
    # confusion signal (graph.insert_before with kind="prerequisite"), and
    # `deeper` is reserved for future user-driven detours. Keeping the wire
    # format restricted here means a Mentor that tries to invent prerequisite
    # edges fails fast at parse, not at semantic review.
    kind: Literal["sequence"] = "sequence"


class MentorOutput(BaseModel):
    nodes: list[NodeWire]
    edges: list[EdgeWire]
    confidence: Literal["high", "medium", "low"]


# ── Anchor-quality checks (operate on the wire format) ─────────────────────────


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
                symbol=wire_node.resolved_symbol,
            ),
            concept_tags=list(wire_node.concept_tags),
            lesson_brief={
                "objective": wire_node.objective,
                "why": wire_node.why,
                "understand": wire_node.understand,
            },
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
            "objective": node.lesson_brief.get("objective", ""),
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
    """Plan the learning graph. One entry point, one evidence provider.

    Stage 5: the retrieval path is gone, so this is a delegation and a
    precondition. `state.investigation` is written by the `goal_investigation`
    node (D11) and is the Mentor's only evidence — it never explores, and there
    is nothing left for it to retrieve.
    """
    if state.investigation is None:
        # D15: no dossier, no graph. Fabricating one from the module map is the
        # behaviour this migration existed to remove.
        state.errors.append("mentor_agent: no investigation to plan from")
        return state

    if curriculum_enabled():
        from backend.agents.mentor import curriculum

        return curriculum.run(state, client)

    from backend.agents.mentor import dossier as dossier_path

    return dossier_path.run_native(state, client)
