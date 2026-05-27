# LearningGraph — the data model for an interactive learning session.
#
# This module is the single source of truth for the *shape* of a graph; the
# Planner builds it, the Teaching Agent reads its nodes, the Grader updates
# understanding state, the store persists it. No LLM calls, no IO — pure data
# and in-place mutation. The mutation style matches OnboardState (mutate in
# place, return self) to keep the codebase consistent.
#
# Identity: graph_id is implicit — equal to the owning session_id (one graph
# per session in v1, see docs/planning/phases/phase3.md "graph scope"). Node
# IDs are uuid4 hex, stable across mutations so the UI can keep pointing at
# "this node" even after a prerequisite is inserted before it.
#
# Edge kinds:
#   - "sequence":     the default linear ordering produced by the Planner
#   - "prerequisite": inserted by the mutator when the Grader detects confusion
#                     and the user needs to learn something else first
#   - "deeper":       inserted when the user asks to dive into a sub-topic
#                     hanging off a node already in the graph

import uuid
from dataclasses import dataclass, field
from typing import Literal


UnderstandingState = Literal["not-yet", "partial", "understood"]
EdgeKind = Literal["sequence", "prerequisite", "deeper"]


def _new_id() -> str:
    # uuid4 hex (no dashes) — URL-safe and short. Used for both session and
    # node IDs. Lives here, not in a separate ids module, because there is
    # no other identity concern in Phase 3 Part 1 (user identity and repo
    # URL normalization are deferred to Part 7 — persistence + resume).
    return uuid.uuid4().hex


@dataclass
class CodeAnchor:
    file: str
    line_start: int
    line_end: int


@dataclass
class LearningNode:
    # `title` and `code_anchor` are required by every caller; `id` defaults to
    # a fresh uuid so most callers never think about IDs.
    title: str
    code_anchor: CodeAnchor
    id: str = field(default_factory=_new_id)
    concept_tags: list[str] = field(default_factory=list)
    # The Planner's lesson brief — the old Phase 1 step JSON minus title/file/
    # line_range, which are top-level here. Teaching expands this into the
    # actual lesson at delivery time.
    lesson_brief: dict = field(default_factory=dict)
    understanding_state: UnderstandingState = "not-yet"
    visited: bool = False
    # Grader marked the user as "confused" on this node at least once. Survives
    # later "understood" updates so the system remembers a rough patch even
    # after the user works through it.
    weak_spot: bool = False
    # User-driven override on understanding_state — set when the user clicks
    # "mark understood" / "mark weak" / "skip" on the graph itself. None means
    # the system's understanding_state is authoritative.
    user_override: str | None = None
    # Cached rendered lesson from the Teaching Agent. None until first render.
    # Stored on the node so revisits are free; regenerated only on explicit
    # refresh.
    cached_lesson: dict | None = None


@dataclass
class LearningEdge:
    from_node_id: str
    to_node_id: str
    kind: EdgeKind = "sequence"


@dataclass
class LearningGraph:
    # Phase 3 Part 1 skeleton: a graph belongs to a repo + goal. User identity
    # (multi-user / auth) is deferred to Part 7, when persistence + resume
    # actually need to disambiguate whose graph this is.
    repo_url: str
    goal: dict
    session_id: str = field(default_factory=_new_id)
    nodes: dict[str, LearningNode] = field(default_factory=dict)
    edges: list[LearningEdge] = field(default_factory=list)
    current_node_id: str | None = None

    # --- construction helpers ---

    def add_node(self, node: LearningNode) -> LearningNode:
        if node.id in self.nodes:
            raise ValueError(f"node id {node.id} already exists in graph")
        self.nodes[node.id] = node
        return node

    def add_edge(self, from_id: str, to_id: str, kind: EdgeKind = "sequence") -> None:
        if from_id not in self.nodes or to_id not in self.nodes:
            raise ValueError("both endpoints must exist before adding an edge")
        self.edges.append(LearningEdge(from_id, to_id, kind))

    # --- session-state mutations ---

    def set_current(self, node_id: str) -> None:
        if node_id not in self.nodes:
            raise ValueError(f"unknown node {node_id}")
        self.current_node_id = node_id

    def mark_visited(self, node_id: str) -> None:
        self.nodes[node_id].visited = True

    def mark_understanding(self, node_id: str, state: UnderstandingState) -> None:
        node = self.nodes[node_id]
        node.understanding_state = state
        if state == "partial" or state == "not-yet":
            # "confused" upstream maps to "not-yet" here; both flag a weak spot.
            # Sticky: once a weak spot, always a weak spot — useful signal for
            # the Planner even after the user later marks the node understood.
            if state == "not-yet":
                node.weak_spot = True

    def override(self, node_id: str, action: str) -> None:
        # User-driven graph edit ("mark understood" / "mark weak" / "skip").
        # We record the override and reflect it in understanding_state so the
        # rest of the system doesn't need a special code path for overrides.
        node = self.nodes[node_id]
        node.user_override = action
        if action == "mark_understood":
            node.understanding_state = "understood"
        elif action == "mark_weak":
            node.understanding_state = "not-yet"
            node.weak_spot = True
        elif action == "skip":
            node.visited = True

    # --- graph mutations (used by the Phase 3 Part 6 mutator) ---

    def insert_before(
        self,
        anchor_id: str,
        new_node: LearningNode,
        kind: EdgeKind = "prerequisite",
    ) -> LearningNode:
        # Insert new_node so it teaches *before* anchor_id. Reroute any sequence
        # edges ending at anchor_id to land on new_node instead, then chain
        # new_node → anchor_id with the given edge kind.
        self.add_node(new_node)
        for edge in self.edges:
            if edge.to_node_id == anchor_id and edge.kind == "sequence":
                edge.to_node_id = new_node.id
        self.edges.append(LearningEdge(new_node.id, anchor_id, kind))
        return new_node

    def insert_after(
        self,
        anchor_id: str,
        new_node: LearningNode,
        kind: EdgeKind = "deeper",
    ) -> LearningNode:
        # Hang new_node off anchor_id without disturbing the existing sequence.
        # Used for "deeper" detours — the user can come back to the main path
        # after exploring.
        self.add_node(new_node)
        self.edges.append(LearningEdge(anchor_id, new_node.id, kind))
        return new_node

    # --- derived metrics ---

    def readiness(self) -> float:
        # Heuristic progress signal — understood_count / total. Communicates
        # progress without overclaiming. The roadmap calls for
        # "goal_relevant_count" in the denominator; for v1 every node in the
        # graph is goal-relevant by construction (the Planner only emits
        # relevant nodes), so total works.
        if not self.nodes:
            return 0.0
        understood = sum(1 for n in self.nodes.values() if n.understanding_state == "understood")
        return understood / len(self.nodes)
