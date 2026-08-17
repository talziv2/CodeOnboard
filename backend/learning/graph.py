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
#   - "sequence":     the ordering the learner walks, produced by the Planner
#   - "prerequisite": "B cannot be understood before A". Written by TWO different
#                     producers, which mean different things — see below
#   - "deeper":       inserted when the user asks to dive into a sub-topic
#                     hanging off a node already in the graph
#
# TWO PRODUCERS OF `prerequisite`, AND WHY CONSUMERS MUST TELL THEM APART
#
#   PLANNED   the objective-first planner emits one per `depends_on`, so a normal
#             graph carries dozens. They describe the DEPENDENCY STRUCTURE of the
#             curriculum. Every unit they touch is an ordinary stop, planned
#             before the learner answered anything.
#   REMEDIAL  the Mutator splices a warm-up in after a wrong answer. This is an
#             EVENT in one learner's session: something went wrong here.
#
# A consumer that treats every prerequisite edge as remedial reports a planned
# curriculum as a sequence of failures — which is exactly what happened to the
# route rail, where a planned graph rendered with nearly every stop captioned
# "added after confusion".
#
# The structural tell is `insert_before`: it REROUTES the incoming sequence edge
# onto the new node, so a spliced warm-up has NO OUTGOING SEQUENCE EDGE. A
# planned unit sits on the chain and keeps one. Anything asking "was this
# inserted after a mistake?" must check that, not merely the edge kind.

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from backend.learning.gaps import Gap, GapState


UnderstandingState = Literal["not_started", "failed", "partial", "understood"]
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
    # Qualified symbol name ("Session.send") when the range corresponds to — or
    # sits inside — exactly one indexed symbol. Filled in by the anchor resolver
    # (backend/repo/anchors.py), never by a model.
    #
    # `file` + `symbol` is the STABLE SEMANTIC IDENTITY of what this node teaches;
    # line_start/line_end are the resolved LOCATION for the current commit. That
    # split is what makes a range re-resolvable if the checkout ever moves.
    #
    # Nullable and defaulted: nodes written before this field existed load with
    # symbol=None and behave exactly as before.
    symbol: str | None = None


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
    understanding_state: UnderstandingState = "not_started"
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
    # Every graded answer, oldest first:
    # {answer, classification, gap_kind, rationale, at}.
    # understanding_state only records where the user ended up; this records how
    # they got there, so revisiting a node adds to the record instead of
    # silently overwriting it.
    attempts: list[dict] = field(default_factory=list)
    # Outstanding gaps — the misconceptions this node's answers revealed, and
    # the per-node remediation counter (gap-model.md M1).
    #
    # EXPLICIT STATE, not derived from `attempts`. "Gap A was later closed" is
    # not a fact about the attempt that opened it, and a fold recomputed on
    # every read loses a gap silently the first time it is wrong — which is
    # exactly what the requirement that a refresh must not forget a remediation
    # forbids (§18.4). `attempts` stays the append-only evidence; this is the
    # current truth, on the same side of the line as `understanding_state`.
    #
    # M1 is INERT: nothing reads this yet. It does not block, does not appear in
    # `to_dict`, and does not reach the API. Persistence is unconditional and
    # never consults `CODEONBOARD_GAPS` — the flag gates behaviour, never
    # storage, which is what makes the round-trip contract true by construction.
    gap_state: GapState = field(default_factory=GapState)

    @property
    def gaps(self) -> list[Gap]:
        """Read-only view. Mutate through `gap_state.gaps`."""
        return self.gap_state.gaps

    def objective(self) -> str:
        """The claim this node must teach, and that the user's answer is marked against.

        The objective is the contract between the three agents that touch a node
        (learning-engine.md §8.1): the Planner writes it, Teaching builds exactly
        it, the Grader marks exactly it. Before it existed each agent aimed at
        its own target, so the system verified that the user had reproduced the
        teacher rather than reached what the planner intended.

        Falls back to the older `understand` brief — which is what every graph
        planned before the contract carries. Teaching and the Grader MUST share
        this fallback: if they disagreed about the target on old graphs, the
        drift the contract exists to end would simply move here.
        """
        brief = self.lesson_brief or {}
        return (brief.get("objective") or brief.get("understand") or "").strip()


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
    # Populated by the Documentation Agent during the pipeline run and carried
    # on the graph so Teaching Agent can access it during interactive sessions
    # (where state is reconstructed from the persisted graph, not from the pipeline).
    doc_context: dict | None = None
    # Ordered curriculum areas: [{id, title, why, order}]. One level of grouping
    # so a sixteen-stop journey is legible as a shape rather than a list
    # (learning-engine.md LD3). Deliberately metadata, not an entity: an area
    # has no state, no lifecycle and no traversal of its own — units point at
    # one by `lesson_brief["area_id"]`. Empty for every graph the objective-first
    # planner did not build.
    areas: list[dict] = field(default_factory=list)

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

    def record_attempt(
        self,
        node_id: str,
        answer: str,
        classification: str,
        rationale: str,
        gap_kind: str = "none",
    ) -> dict:
        # Append-only: a re-answer on a revisited node adds to the record rather
        # than replacing it, so the history survives a change of state.
        attempt = {
            "answer": answer,
            "classification": classification,
            # Why the answer fell short, so a later attempt can be compared with
            # this one on more than its verdict. Defaulted, so attempts recorded
            # before the field existed load unchanged.
            "gap_kind": gap_kind,
            "rationale": rationale,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self.nodes[node_id].attempts.append(attempt)
        return attempt

    def mark_understanding(self, node_id: str, state: UnderstandingState) -> None:
        node = self.nodes[node_id]
        node.understanding_state = state
        if state == "failed":
            # Mark as weak spot — prerequisite nodes get cleared later in insert_before
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
            node.understanding_state = "failed"
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
        # Prerequisite nodes are helpers, not original topics — clear weak_spot
        new_node.weak_spot = False
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

    # --- traversal ---
    #
    # The "path" the user walks is made of two edge kinds:
    #   - sequence:     the Mentor's planned order
    #   - prerequisite: a node spliced in before another (mutator, Part 6) —
    #                   it still moves the user forward (learn the prereq,
    #                   then continue to the node that needed it)
    # "deeper" edges are deliberately NOT part of the walk: they're opt-in
    # side detours, reached only by explicit navigation.

    _PATH_EDGE_KINDS = ("sequence", "prerequisite")

    def next_in_path(self, node_id: str) -> str | None:
        # Next node along the main walk, or None at the end. Prefer a sequence
        # edge; fall back to a prerequisite edge (a prereq points at the node
        # it unblocks, which is exactly where the user should go next).
        for kind in self._PATH_EDGE_KINDS:
            for edge in self.edges:
                if edge.kind == kind and edge.from_node_id == node_id:
                    return edge.to_node_id
        return None

    def path_head(self) -> str | None:
        # The node with no incoming path edge — where the walk starts.
        if not self.nodes:
            return None
        incoming = {
            e.to_node_id for e in self.edges if e.kind in self._PATH_EDGE_KINDS
        }
        for node_id in self.nodes:
            if node_id not in incoming:
                return node_id
        return next(iter(self.nodes))

    def path_order(self) -> list[str]:
        # Node ids in walk order: from the head along path edges, then any
        # off-path nodes (e.g. "deeper" detours) appended at the end. The
        # seen-set guards against cycles.
        order: list[str] = []
        seen: set[str] = set()
        cur = self.path_head()
        while cur is not None and cur not in seen:
            seen.add(cur)
            order.append(cur)
            cur = self.next_in_path(cur)
        for node_id in self.nodes:
            if node_id not in seen:
                order.append(node_id)
        return order

    def resume_point(self) -> str | None:
        # Where a returning user should continue: the first unvisited node, in
        # walk order, whose prerequisites are all understood. Falls back to the
        # saved current_node_id when everything's been visited (or nothing
        # qualifies). Heuristic, not rigorous — just a sensible re-entry point.
        #
        # `optional` units are skipped for the same reason `/advance` steps over
        # them: they are not part of the journey the learner was promised, so
        # dropping someone back into one on their return would resume a path
        # they did not leave. They stay reachable from the rail.
        for node_id in self.path_order():
            node = self.nodes[node_id]
            if node.visited or self.is_optional(node):
                continue
            prereqs = [
                e.from_node_id
                for e in self.edges
                if e.kind == "prerequisite" and e.to_node_id == node_id
            ]
            if all(
                self.nodes[p].understanding_state == "understood"
                for p in prereqs
                if p in self.nodes
            ):
                return node_id
        return self.current_node_id

    # --- derived metrics ---

    def readiness(self) -> float:
        """Goal readiness — evidence-weighted mastery of what the goal requires.

        DELEGATES to `learning/progress.py`, which owns the definition and the
        second measure beside it (learning-graph.md §5.4). Kept as a method
        because six call sites and the `readiness` wire key already exist; the
        arithmetic moved out because the frontend, the map and any later report
        must not each carry their own version of it.

        The definition CHANGED with the progress model, in two ways that matter:

          - the denominator is the `required` set, not every non-optional unit,
            so the number is a claim about the GOAL rather than about a node
            count;
          - remedial warm-ups are excluded from both sides. Before this, the
            Mutator's warm-up — marked `priority: required` so scope control
            cannot take it away — entered the denominator, and the gauge fell
            from 0.50 to 0.33 the moment the system decided to help.

        The import is function-local to keep `progress` free to depend on this
        module's types without a cycle.
        """
        from backend.learning.progress import goal_readiness

        return goal_readiness(self)

    @staticmethod
    def is_optional(node: LearningNode) -> bool:
        """Depth the learner was not promised — collapsed in the rail, excluded
        from the stop counter and from `readiness()`, and stepped over by
        `/advance`. Reachable deliberately, never walked into."""
        return (node.lesson_brief or {}).get("priority") == "optional"

    # --- serialization (for API responses / UI) ---

    def to_dict(self) -> dict:
        # JSON-friendly view of the graph for HTTP responses. Excludes the
        # cached_lesson bodies (large) — the lesson endpoint returns those
        # separately. Includes the derived progress measures.
        from backend.learning import progress as progress_model

        # Once, not per node — the structural pass walks every edge.
        remedial = progress_model.remedial_ids(self)

        return {
            "session_id": self.session_id,
            "repo_url": self.repo_url,
            "goal": self.goal,
            "current_node_id": self.current_node_id,
            # RETAINED, and equal to `progress.goal_readiness`. Every existing
            # consumer keeps working; the two-measure view lives in `progress`.
            "readiness": self.readiness(),
            "progress": progress_model.summary(self),
            "areas": self.areas,
            "nodes": [
                {
                    "id": n.id,
                    "title": n.title,
                    # The DISPLAY anchor. A unit may be grounded in several
                    # equally real locations (a flow crossing three files); this
                    # is the one the code pane opens by default, and it carries
                    # no claim that it matters most. The full set lives in
                    # lesson_brief["anchors"] (learning-engine.md §4.1.1).
                    "file": n.code_anchor.file,
                    "line_start": n.code_anchor.line_start,
                    "line_end": n.code_anchor.line_end,
                    "anchors": (n.lesson_brief or {}).get("anchors", []),
                    "kind": (n.lesson_brief or {}).get("kind", ""),
                    "priority": (n.lesson_brief or {}).get("priority", ""),
                    "area_id": (n.lesson_brief or {}).get("area_id", ""),
                    # The claim this unit exists to make the learner able to
                    # make — the marking standard the Grader uses. On the wire
                    # so the UI can show what was actually being assessed
                    # instead of only the title.
                    "objective": n.objective(),
                    # What the learner ASSERTED, kept distinct from what they
                    # DEMONSTRATED. `override` writes `understanding_state`
                    # directly, so without this the two are indistinguishable
                    # downstream (learning-graph.md §10 R9).
                    "user_override": n.user_override,
                    # "planned" | "system_remediation" | "learner_request",
                    # resolved through the structural fallback for graphs
                    # written before the key existed.
                    "origin": progress_model.origin_of(n, remedial),
                    "concept_tags": n.concept_tags,
                    "understanding_state": n.understanding_state,
                    "visited": n.visited,
                    "weak_spot": n.weak_spot,
                    "has_lesson": n.cached_lesson is not None,
                    "attempts": n.attempts,
                }
                for n in self.nodes.values()
            ],
            "edges": [
                {"from_id": e.from_node_id, "to_id": e.to_node_id, "kind": e.kind}
                for e in self.edges
            ],
        }
