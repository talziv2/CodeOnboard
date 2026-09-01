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
from backend.learning.tutor import TutorState


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
    # What the Tutor has done on this stop: how many hints were written for the
    # question in front of the learner, whether they asked to see the answer, and
    # how many turns this stop has drawn (tutor.md §4.2).
    #
    # NOT EVIDENCE, and the placement says so: it sits beside `gap_state` because
    # both are per-node persisted facts, but nothing here can reach
    # `understanding_state`. Two consumers read it — `retry.py`, to decide what to
    # OFFER, and the attempt record, as metadata about the conditions an answer
    # was given under. Neither is a claim about understanding.
    tutor_state: TutorState = field(default_factory=TutorState)

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
#   continue         they read the verdict and chose to move on anyway
#   waive_remaining  they chose to stop remediating this node
#   skip             they never engaged with it, deliberately
#   mark_understood  they asserted they already know it
#
# `mark_weak` is absent on purpose: "I don't get this" is the opposite of having
# dealt with it.
#
# `mark_understood` WAS absent, on the reasoning that M8 routed it elsewhere. That
# was only ever true of a gap-bearing node: on a gap-free one `override` wrote
# `understanding_state = "understood"` directly, and settlement came from that
# write rather than from the intent. M0 stops the write — an assertion is not a
# demonstration, and the single invariant this milestone exists to enforce is that
# **a learner decision is never evidence of understanding**. Settlement therefore
# has to come from the intent, which is what this line now says. Without it,
# removing the write would silently make every asserted node block completion.
SETTLING_OVERRIDES: frozenset[str] = frozenset(
    {"continue", "waive_remaining", "skip", "mark_understood"}
)


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
    # The welcome briefing — what this repository is, written for THIS learner's
    # profile (backend/agents/briefing). Session-scoped rather than derived on
    # every read because it costs a model call: the first GET of the welcome page
    # writes it, later ones read it back. None means "not written yet", which is
    # every graph until its welcome page is opened.
    briefing: dict | None = None
    # Ordered curriculum areas: [{id, title, why, order}]. One level of grouping
    # so a sixteen-stop journey is legible as a shape rather than a list
    # (learning-engine.md LD3). Deliberately metadata, not an entity: an area
    # has no state, no lifecycle and no traversal of its own — units point at
    # one by `lesson_brief["area_id"]`. Empty for every graph the objective-first
    # planner did not build.
    areas: list[dict] = field(default_factory=list)
    # JOURNEY-SCOPED history: every change to the shape of the journey —
    # prune-ahead, scope adjustments, remediation insertions — plus the jumps that
    # moved the learner through it out of order. Session-scoped rather than
    # node-scoped for the same reason `areas` is: it belongs to the journey, not
    # to any one unit. Append-only, oldest first.
    journey_events: list[dict] = field(default_factory=list)
    # HOW THE LEARNER GOT TO `current_node_id`, when that is worth saying.
    #
    # Distinct from `journey_events` on purpose, and the distinction is
    # permanent-vs-current: the event list is the append-only record ("they
    # jumped, at 14:02"), and this is the one live fact a screen can act on
    # ("they are here, and they did not walk here"). Deriving the second from the
    # first is not safe — `/advance` records nothing, so a stale `jumped` event
    # would still match a node the learner later walked back into behind a
    # warm-up, and the notice would fire on a stop they reached legitimately.
    #
    # `None` means "no notice to show", and it deliberately conflates two things
    # that need no separating: arrived by walking, and written before this
    # existed. Both are the absence of a positive claim, which is what a notice
    # requires. Cleared by `/advance` — walking on is rejoining the route.
    arrival: dict | None = None
    # Does this session have its ORIGINAL PLAN on disk? Set by the store, which is
    # the only layer that can know, and reported on the wire as `has_plan`.
    #
    # It answers one product question: can this session be started over? `Start
    # over` restores from the plan snapshot, so a session without one cannot be
    # restarted at all — and a menu must not offer an action that cannot work.
    #
    # Deliberately keyed on THE PLAN EXISTING rather than on `schema_version`. The
    # plan tables are the actual precondition; a version comparison is a proxy for
    # it that goes stale the next time versions move. Sessions written before the
    # plan tables existed load with False (session-reset.md D8), and nothing ever
    # synthesises a plan for them: a plan invented from a half-walked session is
    # not the plan that learner was given.
    #
    # NOT learner state, and not persisted — it is a fact about what the database
    # holds, so `save_graph` never writes it and every reader gets it fresh.
    has_plan: bool = False
    # THE TUTOR TRANSCRIPT — every exchange in this session, oldest first, each
    # anchored to the stop it was asked from (tutor.md §4).
    #
    # Session-scoped for the same reason `areas` and `journey_events` are: it
    # belongs to the journey rather than to any one unit, and there is no node
    # payload it could ride in — nodes are rebuilt from `plan_nodes` on a reset,
    # which has no column for it and must not grow one.
    #
    # Deliberately ABSENT from `to_dict`. A transcript that grew with every
    # question would make each session poll heavier for a surface that may never
    # be opened; `GET /session/{id}/tutor` serves it, like lessons.
    #
    # LEARNER-PRODUCED, so `Start over` clears it — see `reset.py`, and
    # `reset.learner_state`, which is the enumeration this has to appear in.
    tutor: list[dict] = field(default_factory=list)

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
        question: str = "",
        question_source: str = "",
    ) -> dict:
        """One graded answer, and THE QUESTION IT ANSWERED (M1).

        The question was not recorded before, and its absence was load-bearing in
        a way that only shows up later. Three things make an attempt's question
        unrecoverable after the fact:

          - a re-teach REPLACES `cached_lesson`, so the prompt the learner
            actually answered survives only inside `response.superseded_lesson`,
            and only for the one attempt that caused the rewrite;
          - `grade_verification` clears `pending_verification` whatever the
            outcome, so a verification question existed nowhere once answered;
          - `/reassess` (M5) will put a THIRD question against the same node.

        So "which question produced this verdict?" was unanswerable for every
        stored attempt — which makes every claim about whether two questions
        assess the same knowledge unfalsifiable, and that claim is the whole
        subject of the objective-model decision this pass has to make.

        `question_source` names WHICH mechanism asked, because the four are
        graded differently and mean different things about the learner:
        `history.QUESTION_SOURCES`.

        Both default to empty, which reads as UNKNOWN — every attempt written
        before M1 — and never as "there was no question".
        """
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
        # Omitted rather than nulled when unknown, like every other optional key
        # in this record: an absent key means "not recorded", and a present empty
        # one would mean "asked nothing".
        if question:
            attempt["question"] = question
        if question_source:
            attempt["question_source"] = question_source
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

    def record_arrival(
        self, node_id: str, *, kind: str, from_node_id: str | None = None
    ) -> dict:
        """Record HOW the learner reached `node_id`, for the notice on that stop.

        Stores the raw fact and nothing derived: which stop was left, which was
        landed on, when. Direction, position and how many stops were passed are
        all computed from the ROUTE by the caller that draws the notice — the
        frontend's `buildRoute`, which is what numbers the rail. Computing them
        here would put a second implementation of "stop N of M" on the wire, and
        the two would eventually disagree in exactly the place a learner is
        comparing them.
        """
        self.arrival = {
            "node_id": node_id,
            "kind": kind,
            "from_node_id": from_node_id,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        return self.arrival

    def clear_arrival(self) -> None:
        """Forget how the learner got here — they are on the route now."""
        self.arrival = None

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
        """Record that the learner chose to move on without reaching the objective.

        Returns whether anything was recorded.

        THE CONDITION IS "UNMET OBJECTIVE, AND THEY TRIED", not "open blocking
        gaps". The gap test was correct when gaps were the only representation of
        unfinished work; they are not, and the gap where they are not is the
        common case rather than the edge:

          - an `off-topic` answer opens NO gaps at all, by explicit policy
            (`Gap.create` refuses `no_attempt`, and `_record_gaps` returns early)
          - a `confused` or `partial` answer whose Grader named no FALSE
            STATEMENT opens none either — an omission is not a gap

        In every one of those cases the learner answered, fell short, pressed
        "Move on anyway", and this recorded nothing. The node then had no
        settling override, so `is_settled` stayed False and `is_complete()` was
        permanently unreachable for the whole session — silently, with the stop
        rendering as though it had never been opened.

        **The attempt clause is what keeps the record meaningful.** Stamping every
        advance would settle stops nobody decided about, which is what the gap
        test was really protecting; presence is not a decision, so a refresh, a
        scroll-past and a plain walk-through still record nothing. An ANSWER plus
        a button press is a decision, and that is exactly what this now requires.

        Assessments only. A verification answer is evidence about one gap rather
        than an attempt at the objective, and it cannot occur without a prior
        assessment anyway — reading it through `history.assessments` keeps this
        function agreeing with `understanding.classify` about what "they tried"
        means instead of quietly using a second definition.

        STRICTLY WIDER BY CONSTRUCTION. The old gap test is kept as a second
        trigger rather than replaced, so nothing that fired before can stop
        firing. In production it is redundant — a gap is minted only by grading,
        which records an assessment in the same request — but "redundant" is an
        argument about reachability, and keeping the clause makes the guarantee a
        property of the code instead. It costs one condition and it is the reason
        every stranding test above continues to mean what it meant.

        Never touches understanding: `user_override` is the disposition channel
        and `understanding_state` is the evidence channel (understanding.py's two
        dimensions). Moving on records a DECISION, and a decision is not evidence.
        """
        node = self.nodes[node_id]
        if understanding_of(node) == "understood":
            return False
        if not history.assessments(node.attempts) and not has_open_blocking_gaps(node):
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
        """A user-driven graph edit: "mark understood" / "mark weak" / "skip".

        **`mark_understood` NEVER writes `understanding_state`.** That is the M0
        invariant, and it is the whole of what changed here: an assertion is not a
        demonstration, so it is recorded in the DISPOSITION channel
        (`user_override`, read as `understanding.ASSERTED`) and nowhere else.

        §18.16.2 half-closed this door already, and the half it left open was the
        consequential one. `mark_understood` was routed to `waive_remaining` on a
        gap-bearing node — but on a GAP-FREE node it still wrote `understood`
        straight into the evidence channel. On an *unassessed* node that was
        harmless, because `classify` returns `insufficient` with no evidence
        whatever the stored state says. On an *assessed* one it was not. Measured
        on a node whose only answer was graded `confused`:

            before:  classify=unresolved  demonstrated=False  goal_readiness=0.0
            after :  classify=strength    demonstrated=True   goal_readiness=1.0

        A failed node became a STRENGTH — not even `recovered` — and moved the
        product's centrepiece measure to 100%, on a button press. Goal readiness
        is defined as evidence-weighted mastery; this was the one door through
        which a decision entered it as evidence.

        `mark_weak` still writes `failed`, and that is not the same thing wearing
        a different hat. It is the learner AGREEING with a shortfall — it can only
        ever lower the claim being made about them, never raise it — which is why
        `disposition_of` leaves it `active` rather than treating it as settled.

        Settlement for `mark_understood` now comes from `SETTLING_OVERRIDES`
        rather than from the state write, so completion and resume behave exactly
        as they did.
        """
        node = self.nodes[node_id]
        # On a gap-bearing node the honest name for the intent is "stop asking me"
        # — so it is recorded as `waive_remaining`, which also settles the gaps
        # themselves rather than leaving them open behind an assertion.
        if action == "mark_understood" and node.gaps:
            self.waive_remaining(node_id)
            return
        node.user_override = action
        if action == "mark_weak":
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
        from backend.learning import understanding as understanding_model

        # Once, not per node — the structural pass walks every edge.
        remedial = progress_model.remedial_ids(self)

        return {
            "session_id": self.session_id,
            "repo_url": self.repo_url,
            "goal": self.goal,
            "current_node_id": self.current_node_id,
            # Whether `Start over` is available at all. Named for the fact rather
            # than for the button, like `has_lesson` on a node — the UI decides
            # what to do about it, and one name beats a model field and a wire
            # field that mean the same thing.
            "has_plan": self.has_plan,
            # RETAINED, and equal to `progress.goal_readiness`. Every existing
            # consumer keeps working; the two-measure view lives in `progress`.
            "readiness": self.readiness(),
            "progress": progress_model.summary(self),
            # The Understanding Profile (M3a.1). Derived, never stored: two
            # dimensions per node — what the evidence demonstrates, and what the
            # learner decided about remediation.
            "understanding": understanding_model.profile(self),
            "areas": self.areas,
            # Journey-scoped history. On the wire so M3 can explain a journey
            # that changed shape, and so the session log can show the jumps that
            # moved the learner through it.
            "journey_events": self.journey_events,
            # The live arrival fact, for the notice on a jumped-to lesson. Null
            # whenever there is nothing to say.
            "arrival": self.arrival,
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
                    # The two dimensions, per node, so every surface renders the
                    # same classification instead of each deriving its own from
                    # `weak_spot` — which is sticky, and therefore captions a
                    # recovered unit as a current weakness forever (M3a.1).
                    "understanding": understanding_model.classify(n),
                    "disposition": understanding_model.disposition_of(n),
                    # DID THEY TRY? A third fact, and it is not derivable from
                    # the other two: `insufficient` covers both "never opened"
                    # and "answered, and the answer told us nothing", and those
                    # are the two stops a learner most needs to tell apart.
                    #
                    # Server-owned rather than counted from `attempts` in the
                    # client, because "which attempts count" is a rule this
                    # codebase already owns — assessments only, since a
                    # verification answer is evidence about a gap rather than an
                    # attempt at the objective. A second definition in the rail
                    # is exactly how `weak_spot` came to caption recovered units
                    # as weaknesses.
                    "attempted": bool(history.assessments(n.attempts)),
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
                    # EVERY gap, settled ones included, each with its `status`.
                    # What the learner does not know here by name — and what
                    # they have since put right.
                    #
                    # This sent open gaps only, and it is the payload the lesson
                    # falls back to between answers. So a gap the learner CLOSED
                    # was visible for exactly one render of the feedback card and
                    # then gone: the single act they can perform on a gap deleted
                    # its own evidence. Consumers that mean "outstanding work" —
                    # the rail's count, its hover — filter on `status`, which is
                    # a thing they can now do and previously could not.
                    #
                    # `opened_at` / `closed_at` also unblock the session log's
                    # gap rows, which were written against this shape and had
                    # nothing to read.
                    "gaps": [
                        {"id": g.id, "kind": g.kind, "claim": g.claim,
                         "objective_part": g.objective_part,
                         "status": g.status, "blocking": g.is_blocking,
                         "verification_attempts": g.verification_attempts,
                         "exhausted": g.is_exhausted,
                         "opened_at": g.opened_at, "closed_at": g.closed_at}
                        for g in n.gaps
                    ],
                }
                for n in self.nodes.values()
            ],
            "edges": [
                {"from_id": e.from_node_id, "to_id": e.to_node_id, "kind": e.kind}
                for e in self.edges
            ],
        }
