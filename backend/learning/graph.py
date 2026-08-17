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

from backend.learning import history
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


# Overrides that mean "the learner has dealt with this stop", and therefore
# settle it for JOURNEY COMPLETION (§18.16.3). Each is an explicit act:
#
#   continue         they read the gaps and chose to move on anyway
#   waive_remaining  they chose to stop remediating this node
#   skip             they never engaged with it, deliberately
#
# `mark_weak` is absent on purpose: "I don't get this" is the opposite of having
# dealt with it. `mark_understood` is absent because it is migration debt that M8
# routes elsewhere (see `LearningGraph.override`).
SETTLING_OVERRIDES: frozenset[str] = frozenset({"continue", "waive_remaining", "skip"})


def is_settled(node: LearningNode) -> bool:
    """Has the learner DEALT WITH this stop? The input to `is_complete()`.

    §18.16.3: `understood`, or carrying an explicit learner override. **Plain
    `visited` is deliberately not enough** — intent must be recorded, never
    inferred, so scrolling past a stop does not settle it.

    Not to be confused with `progress.is_settled`, which is the *weaker*
    coverage-shaped question ("visited, answered, or acted on") used by the
    progress measures. That module's docstring already points here for the strict
    one; the two answer different questions and both are needed.
    """
    if understanding_of(node) == "understood":
        return True
    return node.user_override in SETTLING_OVERRIDES


def has_open_blocking_gaps(node: LearningNode) -> bool:
    """Is there unfinished remediation here — work the system would still offer?

    `open` specifically, not "unverified": a `waived` gap is unverified forever
    and is precisely what the learner asked to stop being asked about.
    """
    return any(g.is_blocking and g.is_open for g in node.gaps)


def understanding_of(node: LearningNode) -> UnderstandingState:
    """The node's understanding state. **The single owner of this question.**

    `understanding_state` on the node is the LATEST RECORDED ASSESSMENT — what
    the Grader last concluded from an answer. This function turns that into what
    the learner has actually demonstrated, by also consulting the gaps
    (learning-engine.md §18.8, gap-model.md M7).

    The consequential rule, and the whole reason M7 exists:

        A node cannot be `understood` while a blocking gap is unverified, even
        when the most recent answer was graded `understood`.

    That is loss point 5. Before this, an answer could be marked `understood`
    while two detected misconceptions sat open on the same node, and the graph
    would report mastery.

    **`verified` is the only status that permits `understood`** — not merely
    "not open". A `waived` gap is one the learner chose to stop working on, which
    is a decision rather than evidence, so it keeps the node off `understood`
    exactly as an open one does (§18.16's final state model; the M7 build row
    states the condition as "every blocking gap is `verified`"). What waiving buys
    is that the system stops asking, which is M8's business, not this function's.

    Non-blocking gaps never affect the outcome: a `right_idea_wrong_altitude` gap
    is real, is worth showing, and is not a claim that the objective was missed.

    **Compatibility is by construction, not by care.** When no blocking gap
    exists — every graph written before the gap model, and every flag-off session
    — the first branch returns the stored value untouched. There is no arithmetic
    that could drift, which is what makes the stored-session gate exact rather
    than approximate.
    """
    blocking = [g for g in node.gaps if g.is_blocking]
    if all(g.status == "verified" for g in blocking):
        return node.understanding_state

    # Something blocking is unverified. The node is not `understood`, whatever
    # the last answer scored — but it is not demoted below what was recorded
    # either:
    #
    #   failed       stays failed. The latest answer showed a real
    #                misunderstanding, and that is a sharper fact than "some gap
    #                is open". `weak_spot` is already sticky, so §18.8's "stays
    #                true while any blocking gap is open" needs nothing here.
    #   not_started  stays not_started. Gaps cannot exist without an attempt in
    #                practice, but if they somehow do, inventing progress would
    #                be worse than reporting none.
    #   otherwise    `partial` — including a stored `understood`, which is the
    #                one demotion this function performs and the point of it.
    if node.understanding_state in ("failed", "not_started"):
        return node.understanding_state
    return "partial"


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
    # PLAN-SCOPED history: every change to the shape of the journey — prune-ahead,
    # scope adjustments, remediation insertions. Session-scoped rather than
    # node-scoped for the same reason `areas` is: it belongs to the journey, not
    # to any one unit. Append-only, oldest first.
    journey_events: list[dict] = field(default_factory=list)

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
        kind: str = history.ASSESSMENT,
        graded: bool = True,
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
            # Assessment or verification (gap-model M6). Written explicitly from
            # here on so the two can never be pooled; every stored attempt
            # predates verification and reads correctly as an assessment.
            "kind": kind,
            # Did grading succeed, or is this the fallback verdict? A failed
            # grade is our error, not the learner's answer, and `history` keeps
            # it out of understanding evidence.
            "graded": graded,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        node = self.nodes[node_id]
        node.attempts.append(attempt)
        # A new answer WITHDRAWS a prior `continue` (M8, §3.6). "I chose to move
        # on" and "I am working on this again" are contradictory, and the later
        # act wins. Left standing, the override would keep this node settled for
        # completion and keep `resume_point` walking past the work the learner has
        # just come back to.
        #
        # Only `continue` is withdrawn. `waive_remaining` and `skip` are decisions
        # about whether to engage at all, and answering does not retract them —
        # a waived gap stays waived until the learner asks to verify it.
        if node.user_override == "continue":
            node.user_override = None
        return attempt

    def record_response(self, node_id: str, response: dict) -> dict | None:
        """Attach what the system did to the answer that caused it (§18.9).

        On the LATEST attempt, because a response is caused by exactly one
        answer and is written in the same request that recorded it. Returns None
        when there is no attempt to attach to, rather than inventing one — a
        response with no answer behind it would be a system action the history
        claims a learner triggered.

        The presence of this key is what distinguishes "the system did nothing"
        from "we have no record" for every attempt written before M2.
        """
        # The latest ASSESSMENT, not the latest attempt. A response is what the
        # system did about an answer to the OBJECTIVE; a verification answer is
        # evidence about one gap and earns no such response. Filing one against a
        # verification would attribute the intervention to the wrong question, and
        # since verification answers are appended like any other attempt, `[-1]`
        # is that wrong question exactly whenever one was graded most recently.
        assessments = history.assessments(self.nodes[node_id].attempts)
        if not assessments:
            return None
        assessments[-1][history.RESPONSE] = response
        return assessments[-1]

    def record_journey_event(self, kind: str, **payload) -> dict:
        """Record a change to the SHAPE of the journey.

        Separate from `attempts` by lifecycle, not by taste: scope changes have
        no attempt to hang from (`/session/{id}/scope` takes no answer), and a
        demotion touches units far from whatever the learner just did. See
        `history` for the full argument.
        """
        event = history.new_journey_event(kind, **payload)
        self.journey_events.append(event)
        return event

    def mark_understanding(self, node_id: str, state: UnderstandingState) -> None:
        """Record the LATEST ASSESSMENT. Not the node's understanding state.

        Since M7 this writes an input, not a conclusion: `understanding_of(node)`
        owns the conclusion, and combines what is recorded here with the node's
        gaps. The name is kept because every caller is still doing the same
        thing — reporting what the Grader concluded from one answer.

        The distinction is load-bearing. Writing `understood` here no longer
        makes a node understood; it records that the answer reached the
        objective, and the node still cannot be `understood` while a blocking
        gap is unverified (§18.8, loss point 5).
        """
        node = self.nodes[node_id]
        node.understanding_state = state
        if state == "failed":
            # Mark as weak spot — prerequisite nodes get cleared later in insert_before
            node.weak_spot = True

    # --- learner intents over gaps (M8) ---

    def continue_past(self, node_id: str) -> bool:
        """Record that the learner chose to move on with gaps still open.

        Returns whether anything was recorded. **Only fires when the node
        actually has open blocking gaps** — otherwise there is nothing to
        continue past, and stamping every ordinary advance with an override
        would make the record meaningless and settle stops nobody decided about.

        This is what makes journey completion reachable (§18.16.3): walking to
        the end settles every stop by construction, because leaving unfinished
        work behind is an explicit button press. A refresh does not advance, so a
        refresh records nothing.
        """
        node = self.nodes[node_id]
        if not has_open_blocking_gaps(node):
            return False
        node.user_override = "continue"
        return True

    def waive_gap(self, node_id: str, gap_id: str) -> bool:
        """The learner chooses to stop working on ONE gap.

        Never evidence: `waived` does not permit `understood`, so the node stays
        `partial` and `readiness()` legitimately stays below 100%. What it buys is
        that the system stops asking.

        If this clears the LAST open blocking gap, the node is also recorded as
        `waive_remaining`. That is not an inference — waiving is itself an
        explicit act — and without it a learner who waived their gaps one at a
        time could never complete the journey, because `/advance` records
        `continue` only where gaps are still *open* and there would be none left
        to trigger it. §18.16.3 requires waived gaps not to prevent completion,
        and this is what makes that true however the learner got there.
        """
        node = self.nodes[node_id]
        target = next((g for g in node.gaps if g.id == gap_id and g.is_open), None)
        if target is None:
            return False
        target.waive()
        if not has_open_blocking_gaps(node):
            node.user_override = "waive_remaining"
        return True

    def waive_remaining(self, node_id: str) -> list[str]:
        """Stop remediating this node. Waives every OPEN blocking gap.

        Returns the ids waived, so the caller can name them — "what you chose not
        to check" is the most useful thing the completion screen can say, and a
        bare count is not it (§18.16.3).

        Non-blocking gaps are left alone: they never held the node back, so
        waiving them would be recording a decision the learner did not make. The
        override is recorded even when nothing was open, because the learner
        still expressed the intent.
        """
        node = self.nodes[node_id]
        waived = [g.id for g in node.gaps if g.is_blocking and g.is_open]
        for gap in node.gaps:
            if gap.is_blocking and gap.is_open:
                gap.waive()
        node.user_override = "waive_remaining"
        return waived

    def is_complete(self) -> bool:
        """Has the learner dealt with the whole promised journey? (§18.16.3)

        **Journey completion, not mastery** — the two are separate measures and
        neither gates the other. This can be `true` while `readiness()` sits below
        100%, and that is the intended final state: *"Journey complete — verified
        understanding 92%, 1 gap waived."* Better than pretending to mastery, and
        better than leaving the product permanently unfinished because one thing
        was deliberately not remediated.

        Counted over `walk_nodes` — planned, non-optional units — so `optional`
        stops and remedial detours do not gate completion. Both are already
        excluded from the stop counter and from `readiness()`; a third opinion
        about which nodes count is exactly what this reuse avoids.
        """
        from backend.learning.progress import walk_nodes

        walk = walk_nodes(self)
        return bool(walk) and all(is_settled(n) for n in walk)

    def override(self, node_id: str, action: str) -> None:
        # User-driven graph edit ("mark understood" / "mark weak" / "skip").
        # We record the override and reflect it in understanding_state so the
        # rest of the system doesn't need a special code path for overrides.
        node = self.nodes[node_id]
        # MIGRATION (§18.16.2): `mark_understood` predates the gap model and sets
        # `understanding_state` directly, which would let a learner claim mastery
        # over unverified gaps by a different door. On a gap-bearing node it is
        # therefore READ AS `waive_remaining` — the honest version of the same
        # intent, since the learner is saying "stop asking me", not "I have
        # demonstrated this".
        #
        # On a node with no gap records it keeps working exactly as it always has:
        # vacuously nothing is bypassed. That is the whole compatibility rule, and
        # it is why every session written before this phase is unaffected.
        if action == "mark_understood" and node.gaps:
            self.waive_remaining(node_id)
            return
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
        # UNFINISHED REMEDIATION FIRST (M8). A node still carrying open blocking
        # gaps is where the learner actually left off, even if they had visited it
        # — otherwise a refresh drops them past the work and the remediation is
        # silently abandoned.
        #
        # **Unless they chose to move past it.** A node they explicitly
        # `continue`d or waived is skipped here, and that exception is the whole
        # anti-stranding guarantee: without it, deciding "I'll come back to this"
        # would send them straight back on every return, forever, with no way out
        # except answering something they had just declined to answer.
        for node_id in self.path_order():
            node = self.nodes[node_id]
            if self.is_optional(node):
                continue
            if node.user_override in SETTLING_OVERRIDES:
                continue
            if has_open_blocking_gaps(node):
                return node_id

        for node_id in self.path_order():
            node = self.nodes[node_id]
            if node.visited or self.is_optional(node):
                continue
            prereqs = [
                e.from_node_id
                for e in self.edges
                if e.kind == "prerequisite" and e.to_node_id == node_id
            ]
            # SETTLED, not `understood`. A prerequisite the learner deliberately
            # continued past or waived can never become `understood` — a waived
            # gap is unverified forever — so requiring mastery here would leave
            # every node behind it permanently unreachable, and resume would fall
            # through to the saved position for the rest of the session. Honouring
            # the decision is what keeps the walk moving.
            if all(
                is_settled(self.nodes[p])
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
            # Plan-scoped history. On the wire so M3 can explain a journey that
            # changed shape; no M2 surface reads it yet.
            "journey_events": self.journey_events,
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
                    # DERIVED, not the stored assessment: this is what the UI
                    # renders, and it must not report mastery over an
                    # unverified blocking gap (§18.8).
                    "understanding_state": understanding_of(n),
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
