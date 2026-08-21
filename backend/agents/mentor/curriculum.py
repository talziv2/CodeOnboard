# The objective-first planner — propose, then cut.
#
# The old planner asked one model for "6–10 nodes" and used whatever came back
# (learning-engine.md L1). Curriculum size was a sentence in a prompt, keyed on a
# field nobody had asked the user for, and no code anywhere checked it.
#
# This module splits that into two jobs with different owners:
#
#   PROPOSE   the model, once. It reads the Dossier and enumerates everything
#             worth learning for this goal, each with a kind, a priority, its
#             dependencies and its evidence. It deliberately OVER-generates.
#   CUT       our code, deterministically. Required-set closure, dependency
#             closure, area coverage, then a guard band. No model involved, so
#             every sizing rule here is unit-testable without an API key.
#
# Asking a model to enumerate is asking it to do something it is good at; asking
# it to self-limit is not (LD7). So the enumeration stays with the model and the
# limit moves into code, which is the structural replacement for a node count in
# a prompt.
#
# What this module does NOT do: explore. It reads the Dossier the
# `goal_investigation` stage already produced. If the Dossier cannot support a
# good curriculum, the fix is that stage's exit criteria — not a second
# exploration loop here (LD10).

import json
import os
from typing import Literal

import anthropic
from pydantic import BaseModel

from backend.agents.mentor.dossier import (
    _dossier_evidence_ranges,
    render_dossier,
)
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.pipeline.state import OnboardState
from backend.repo import anchors
from backend.repo.skeleton import build_skeleton


MODEL = "claude-sonnet-4-6"
# Larger than the old planner's 4096: over-generation is the point, and a
# truncated JSON payload costs the whole curriculum.
MAX_TOKENS = 8192

Priority = Literal["required", "recommended", "optional"]

# A unit's `kind` is one primary tag from the vocabulary four agents already
# share, rather than a parallel taxonomy (LD9) — the prompt below lists it.
# `synthesis` is the one addition: a unit that connects several previously-taught
# units and introduces no new code, which is where a mental model consolidates
# and which had no way to be expressed at all before. An unrecognised kind is not
# rejected here; it becomes a free-form tag, which the frontend already renders.

# Typical journey size by code_depth, as a guard band rather than a target.
#
# The band exists to catch pathological output, not to be hit. A narrow goal on a
# small repo legitimately lands below its range.
#
# `map`'s ceiling is CALIBRATED (2026-08-15, 18 runs — see learning-engine.md
# §6.3). It was 14, and at 14 it stopped being a guard: on `fastapi` it fired in
# two runs of three and pinned the journey at exactly 14 in all three, flattening
# the variance while the underlying demand still moved (core 11-13). Measured
# demand across the six `map` runs was 11-15; 18 is max + 2sd (and mean + 3sd),
# so it now fires only on output statistically unlike anything observed, while
# staying 4 clear of `working` so the three bands remain ordered and distinct.
#
# `working` and `implementation` remain UNCALIBRATED judgement (LD14). The same
# matrix showed both behaving as guards should — neither fired, with slack of +5
# and +4 over the largest journey seen — so the evidence gives nothing to correct
# and they were deliberately left alone.
_SCOPE_BANDS: dict[str, tuple[int, int]] = {
    "map": (5, 18),
    "working": (8, 22),
    "implementation": (10, 28),
}
_DEFAULT_BAND = _SCOPE_BANDS["working"]


# ── wire format ────────────────────────────────────────────────────────────────


class AnchorWire(BaseModel):
    """One piece of evidence. The model names it; our code resolves the range."""

    file: str
    symbol: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    # Filled by grounding.
    resolved_start: int | None = None
    resolved_end: int | None = None
    resolved_symbol: str | None = None


class ObjectiveWire(BaseModel):
    id: str
    title: str
    objective: str
    kind: str
    priority: Priority
    area_id: str
    # Ids of objectives that must be understood first. This is what makes
    # prerequisites real: today they exist only as post-failure remediation, so
    # `resume_point()`'s prerequisite check is nearly vacuous on a fresh graph.
    depends_on: list[str] = []
    # One or more. A flow is grounded in an ordered sequence across files; a
    # boundary on both sides of the seam. Every entry is verified — the invariant
    # is grounding, not cardinality (LD13).
    anchors: list[AnchorWire]
    why: str
    concept_tags: list[str] = []
    # `understand` is deliberately absent. It meant "what the user should take
    # away", which is what `objective` now is, said twice — and the second
    # saying was costing a sentence per objective in a response that was
    # overflowing its token budget on implementation-depth runs. The field
    # survives on pre-B3 graphs, where it is what `objective()` falls back to.


class AreaWire(BaseModel):
    id: str
    title: str
    why: str
    order: int


class CurriculumOutput(BaseModel):
    areas: list[AreaWire]
    objectives: list[ObjectiveWire]
    # §6.5 criterion 3, asked as one field rather than a second LLM call.
    covers_goal: bool
    coverage_note: str = ""
    confidence: Literal["high", "medium", "low"]


# ── selection: the deterministic cut ───────────────────────────────────────────


def dependency_closure(
    chosen: set[str], by_id: dict[str, ObjectiveWire]
) -> set[str]:
    """`chosen` plus everything it transitively depends on.

    A required objective whose foundation was labelled `optional` is a required
    objective that cannot be taught, so the closure is not optional either.
    Unknown ids are ignored rather than raising: a model referencing an objective
    it did not emit should cost one edge, not the curriculum.
    """
    closed = set(chosen)
    frontier = list(chosen)
    while frontier:
        current = by_id.get(frontier.pop())
        if current is None:
            continue
        for dep in current.depends_on:
            if dep in by_id and dep not in closed:
                closed.add(dep)
                frontier.append(dep)
    return closed


def core_set(
    objectives: list[ObjectiveWire], areas: list[AreaWire]
) -> set[str]:
    """What the curriculum needs BEFORE any band is considered.

    The required set, its dependency closure, and one promoted unit per declared
    area that the closure left unstaffed. This is the number §6.3's calibration
    procedure asks for: the band is only a guard around it, so a band that binds
    on a normal run is a band set below what curricula genuinely need — and the
    right response is to widen the band, not to prune real requirements.

    Extracted from `select` so it can be measured and tested on its own.
    """
    by_id = {o.id: o for o in objectives}
    core = dependency_closure(
        {o.id for o in objectives if o.priority == "required"}, by_id
    )

    # An area the planner declared but never staffed is either a planning slip
    # or a subsystem quietly dropped; either way the learner should meet it once.
    for area in areas:
        if any(by_id[i].area_id == area.id for i in core):
            continue
        candidates = [o for o in objectives if o.area_id == area.id]
        if not candidates:
            continue
        best = min(candidates, key=lambda o: _PRIORITY_ORDER[o.priority])
        core = dependency_closure(core | {best.id}, by_id)
    return core


def select(
    objectives: list[ObjectiveWire],
    areas: list[AreaWire],
    code_depth: str,
) -> list[ObjectiveWire]:
    """Decide the curriculum, and its priorities, without an LLM.

    Returns every objective — nothing is discarded — with `priority` rewritten
    where the rules demand it. Three mechanisms, in order of authority:

      1. The required set is the FLOOR. Every `required` objective, plus its
         dependency closure, stays required. This is what stops a superficial
         journey: a goal that genuinely needs eleven concepts gets eleven,
         whatever any target number says.
      2. Area coverage is a BREADTH obligation. Every declared area contributes
         at least one non-optional unit, mirroring the investigation's own
         coverage contract one level up and preventing tunnel vision on a single
         subsystem.
      3. The band is a GUARD. Anything beyond it is demoted to `optional` —
         never dropped (§6.3). Optional units sit on the same spine, collapsed
         in the UI, so depth stays one click away and the journey stays finite.

    Deliberately not a weighted 0.0–1.0 score with a threshold: the inputs are
    model judgements, and three ordered buckets carry the same information
    without the false precision (LD8).
    """
    # (1) and (2) — the floor, and the breadth obligation on top of it.
    core = core_set(objectives, areas)

    # (3) The band, applied to whatever is NOT already core. The core is counted
    # first, before any room is handed out: the floor outranks the guard, so a
    # goal needing twelve required concepts gets twelve even under a band of
    # eight — it does not get eight required plus whatever was listed earliest.
    # Model order is the tiebreak for the remaining room, being the only ranking
    # signal available and the model's own sense of what matters most.
    _, band_max = _SCOPE_BANDS.get(code_depth, _DEFAULT_BAND)
    room = band_max - len(core)
    result: list[ObjectiveWire] = []
    for objective in objectives:
        selected = objective.model_copy()
        if objective.id in core:
            selected.priority = "required"
        elif objective.priority != "optional" and room > 0:
            room -= 1
        else:
            selected.priority = "optional"
        result.append(selected)
    return result


_PRIORITY_ORDER = {"required": 0, "recommended": 1, "optional": 2}


def journey_size(selected: list[ObjectiveWire]) -> int:
    """Units the learner actually walks — optional ones are collapsed."""
    return sum(1 for o in selected if o.priority != "optional")


def band_report(selected: list[ObjectiveWire], code_depth: str) -> str | None:
    """A note when the journey fell outside its band, or None.

    The FLOOR is advisory and only ever logged (LQ6): a small repository may
    honestly have fewer than five teachable objectives, and padding one to reach
    a number would be inventing curriculum. The ceiling is enforced in `select`,
    so a report about it means the required set alone overflowed the band —
    which is the floor correctly outranking the guard, worth recording and not
    worth pruning.
    """
    low, high = _SCOPE_BANDS.get(code_depth, _DEFAULT_BAND)
    size = journey_size(selected)
    if size < low:
        return (
            f"curriculum: {size} units is below the {code_depth} band ({low}-{high}); "
            "kept as planned — the floor is advisory"
        )
    if size > high:
        return f"curriculum: {size} units exceeds the {code_depth} band ({low}-{high})"
    return None


# ── ordering ───────────────────────────────────────────────────────────────────


def order(
    objectives: list[ObjectiveWire], areas: list[AreaWire] | None = None
) -> list[ObjectiveWire]:
    """Topological over `depends_on`, area order then the model's order as tiebreak.

    The result is still mostly a chain — but a chain that came from a dependency
    structure rather than from a model emitting nodes in some order (§6.4).
    Within a tier the model decides, because sequencing two independent concepts
    pedagogically is judgement, not computation.

    THE AREA OUTRANKS THE MODEL'S SEQUENCING, and that is the whole reason this
    takes `areas` at all. Areas are the chapters the learner is shown — the rail
    groups by them, the overview introduces them one at a time — while the walk
    is what "stop 3 of 12" counts. Ordering the chain on model order alone let
    the two disagree: the planner would emit an area-2 objective second, so the
    rail drew it fourth (first stop of the second chapter) while its own header
    called it stop 2. Sorting ready objectives by area first makes each chapter a
    contiguous run of the walk, which is what makes those two numbers the same
    number. Dependencies still win over both — a cross-area `depends_on` is a
    real constraint, and being taught in the wrong chapter is a smaller cost than
    being taught before the thing it needs.

    A dependency cycle cannot be ordered. Rather than fail the curriculum, the
    remaining objectives are appended in model order: a bad edge should cost the
    ordering guarantee, not the journey.
    """
    position = {o.id: i for i, o in enumerate(objectives)}
    by_id = {o.id: o for o in objectives}
    # An objective naming no declared area sorts after every declared one — the
    # same place the rail puts it, in the trailing ungrouped bucket.
    area_rank = {a.id: a.order for a in (areas or [])}
    unplaced = max(area_rank.values(), default=0) + 1
    rank = {
        o.id: (area_rank.get(o.area_id, unplaced), position[o.id]) for o in objectives
    }
    pending = {
        o.id: {d for d in o.depends_on if d in by_id and d != o.id}
        for o in objectives
    }

    ordered: list[ObjectiveWire] = []
    while pending:
        ready = [oid for oid, deps in pending.items() if not deps]
        if not ready:
            ordered.extend(
                by_id[oid] for oid in sorted(pending, key=lambda i: rank[i])
            )
            break
        # ONE AT A TIME, not a tier at a time. Emitting a whole dependency tier
        # sorted by area still interleaves: with a0 → a1 in area 1 and a free b1
        # in area 2, the first tier is {a0, b1} and the second is {a1}, so area 1
        # ends up split around b1. Taking the lowest-ranked ready objective and
        # re-reading readiness keeps a chapter running for as long as its own
        # dependencies allow.
        oid = min(ready, key=lambda i: rank[i])
        ordered.append(by_id[oid])
        del pending[oid]
        for deps in pending.values():
            deps.discard(oid)
    return ordered


# ── the proposal prompt ────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are designing a curriculum through an unfamiliar Python codebase for one
developer with one stated goal.

You are given an INVESTIGATION DOSSIER: the verified, goal-specific
understanding of the repository that a prior investigation established by
reading the actual code. Every code reference in it has been checked against
the repository. It tells you what is TRUE; your job is what this developer
should LEARN.

ENUMERATE, DO NOT SELF-LIMIT. List everything worth learning here for this
goal, and rank it honestly by priority. Our code decides how much of your list
becomes the journey — you are not choosing a length, and there is no target
number. A list that is too short cannot be recovered from; a list that is too
long costs nothing, because the surplus becomes optional depth the developer
can open when they want it.

WHAT TO AIM AT

Success is the developer answering OWNERSHIP questions about a system they have
barely read: what does this part own, where does data enter, what breaks if I
change X, where would a new feature belong. Coverage of the repository is not
the goal, and teaching it file-by-file is an explicit non-goal.

Default to system altitude — architecture, responsibilities, boundaries,
runtime flows, state ownership, contracts and invariants, extension points,
risk areas. Implementation detail is taught when it is load-bearing, or when
the developer asked for it via `code_depth`, and never as the definition of
"understanding code".

Every unit must earn its place. The default answer to "should we teach this?"
is NO. A unit earns inclusion by being relevant to the goal, structurally
important, and non-obvious. A unit teaching something a competent developer
would infer in thirty seconds from a filename is negative value: it spends
attention and inflates the developer's sense of progress.

In an AI-assisted workflow the valuable human understanding is the SUPERVISION
layer. For each candidate ask: must the developer hold this themselves, do they
mainly need to be able to check it, or can it be delegated to an assistant while
they keep enough system understanding to supervise the result? Prefer objectives
that build judgement over objectives that build recall.

Produce a JSON object with exactly these keys:
  areas:         list of curriculum areas (see below)
  objectives:    list of learning objectives (see below)
  covers_goal:   true if a developer who reached every `required` objective
                 could answer the goal's ownership questions; false otherwise
  coverage_note: one sentence — if covers_goal is false, what is missing and why
  confidence:    one of "high", "medium", "low"

An AREA is one level of grouping, so the developer can see the SHAPE of what
they are learning. In the common case an area is a subsystem from the dossier
that the curriculum decided to teach. Keys:
  id:     short local identifier (e.g. "a1"), unique in this response
  title:  short human title (e.g. "Routing and dispatch")
  why:    one sentence — why this area matters for THIS developer's goal
  order:  integer, the order areas should be met in

An OBJECTIVE is one learning unit. Keys:
  id:           short local identifier (e.g. "n1"), unique in this response
  title:        short imperative title
  objective:    the single claim this developer should be able to MAKE, in
                their own words, once they have learned this unit
  kind:         one of architecture | flow | component | extension_point |
                risk | test_coverage | synthesis
  priority:     one of required | recommended | optional
  area_id:      the id of the area this belongs to
  depends_on:   ids of objectives that must be understood FIRST (may be empty)
  anchors:      one or more pieces of evidence — see ANCHORS below
  why:          why this unit matters for the goal — AT MOST 15 WORDS, and it
                must add something `objective` does not already say. Do not
                restate the objective here.
  concept_tags: list of short tags (<= 4), free-form domain terms welcome

Write every field except `objective` tersely. Titles are short imperatives, not
sentences. `why` is a fragment, not a paragraph. The objective is where your
words belong; everything else is a label.

THE OBJECTIVE IS THE MOST IMPORTANT FIELD YOU WRITE. It is not a topic and not
a summary of the code — it is the sentence the developer should be able to say
afterwards, and it is what their answer will be marked against. Write it as a
claim, specific enough that a wrong answer is visibly wrong:

  BAD   "Understand the Session object"            (a topic, not a claim)
  BAD   "Learn how routing works"                  (nothing to be right about)
  GOOD  "Explain what Session owns that a bare request does not — connection
         reuse, cookie persistence and default configuration — and why sending
         through a Session changes behaviour"
  GOOD  "Explain why the adapter layer exists between Session and urllib3, and
         what Session is therefore able not to know about transport"

An objective a developer could satisfy by repeating the lesson's wording back
is a bad objective. Aim at the claim, not the vocabulary.

PRIORITY
  required     the goal is not met without this. Be honest and be sparing:
               everything you mark required WILL be in the journey, together
               with everything it depends on.
  recommended  materially improves the mental model; included if there is room.
  optional     genuine depth, or a tangent worth having available.

KIND, and what each is for
  architecture     what a part OWNS and what it deliberately does not own
  flow             a runtime path, entry to exit, usually across several files
  component        one abstraction and its contract — the place where
                   implementation detail is legitimately the objective
  extension_point  a seam the system is meant to be extended at, and its contract
  risk             an invariant, and what breaks when it is violated
  test_coverage    what is and is not guarded
  synthesis        connects several EARLIER units and introduces no new code.
                   Use `depends_on` to name them. This is where a mental model
                   consolidates — a journey with several areas should have at
                   least one, usually at an area boundary.

ANCHORS — every unit is grounded in real code
  Each anchor is an object: {"file": "...", "symbol": "..."} — the qualified
  symbol exactly as it appears in the dossier (e.g. "Session.send"). PREFER a
  symbol: the exact line range is resolved for you, so you never state one.
  Set "symbol" to null ONLY when the anchor genuinely is not a symbol, and then
  give "line_start" and "line_end" from the dossier instead.

  Give ONE anchor when the unit lives in one place. Give SEVERAL, IN ORDER,
  when it genuinely does not:
    - a `flow` is anchored on its ordered steps, entry point first
    - an `architecture` unit spanning a seam is anchored on both sides, the
      owning side first
    - a `synthesis` unit is anchored on the code of the units it connects
  Order matters: the first anchor is what the code pane opens by default, so
  it must be the entry point or the owning side.

  Anchor only on code that appears in the dossier — it is the code the
  investigation actually verified. Anchors are cheap and unlimited; a unit
  claiming to be about a cross-file flow while pointing at one file is not.

CALIBRATION
  By `goal_type`, when it is `use_library` — the developer intends to USE this
  code in their own project, not to study it:
    - START FROM THE CALLER-FACING SURFACE. The first units are about what they
      import and call: the entry points marked `public_api`, and the shape of a
      correct call. An internal definition is not where this journey begins,
      even when it is the more interesting code.
    - Then what happens BEHIND that call, where it changes how they use it —
      enough runtime flow to explain the behaviour they will observe, not a tour
      of the implementation for its own sake.
    - Cover CONTRACTS and CONSTRAINTS (what they must honour, what they may
      rely on), the CONFIGURATION and EXTENSION points they are meant to reach
      for, and the RISKS of common misuse.
    - Internal components are SUPPORTING EVIDENCE for those objectives, not the
      starting point and not the spine of the journey.
    A journey that teaches this repository's internals in a sensible order has
    answered the wrong question here.

  By `code_depth` (the developer chose this):
    map            → mostly `architecture` and `flow`. Anchor on classes and
                     entry points as concept representatives. `component` units
                     only where a detail is genuinely load-bearing.
    working        → the above, plus the `component`, `risk` and
                     `extension_point` units needed to change things safely.
    implementation → include `component` units for specific implementations;
                     anchor methods over classes; algorithms and data
                     structures are legitimate objectives here.
  By `familiarity`: newer to the codebase → one or two orientation units first;
    experienced → start where the goal actually bites, zero orientation.
  By `background`: a concept the developer's background already covers should
    make a unit CHEAPER TO TEACH — a shorter lesson, less re-explanation — not
    absent. Never drop an objective because they claim to know it; that is
    validated by how they answer, not by what they reported.

RULES
- Every objective needs at least one anchor, and every anchor must come from
  the dossier. A unit you cannot ground is a unit you must not propose.
- Never reuse the same single anchor as the ONLY anchor of two different units.
  Units may legitimately share an anchor among several.
- `depends_on` must reference ids in this response, and must not form a cycle.
- Open questions in the dossier are recorded uncertainty. Never build a unit
  whose teaching depends on something the investigation could not establish;
  where it matters, name it as open inside a related unit's `understand`.
- Self-rate confidence:
    high   — the dossier clearly covers the goal and the curriculum is concrete
    medium — partial coverage; some objectives required interpolation
    low    — the dossier barely reaches the goal
- Return ONLY the JSON object — no markdown fences, no explanation.
"""


# ── grounding ──────────────────────────────────────────────────────────────────


def ground(
    objectives: list[ObjectiveWire], skeleton, evidence: list[dict]
) -> tuple[list[ObjectiveWire], list[str]]:
    """Resolve EVERY anchor on every unit; keep the units that survive.

    Verification is per-anchor and unchanged from the single-anchor design —
    there are simply more calls. A unit is grounded when at least one of its
    anchors resolves against the repository AND falls inside the dossier's
    verified evidence; unresolvable anchors are dropped from the unit rather
    than sinking it, because a four-step flow whose third step went stale is
    still a real three-step flow.

    A unit left with no anchors is dropped entirely. Ungrounded conceptual units
    stay forbidden — that is the invariant this whole system rests on, and
    multi-anchor units do not weaken it (LD13).

    Returns (surviving units, human-readable notes about what was dropped).
    """
    survivors: list[ObjectiveWire] = []
    notes: list[str] = []
    for objective in objectives:
        kept: list[AnchorWire] = []
        for anchor in objective.anchors:
            resolution = anchors.resolve(
                skeleton,
                anchor.file,
                symbol=anchor.symbol or None,
                line_start=anchor.line_start,
                line_end=anchor.line_end,
            )
            named = anchor.symbol or f"{anchor.line_start}-{anchor.line_end}"
            if not resolution.ok:
                notes.append(
                    f"{objective.id}: {anchor.file}:{named} ({resolution.reason})"
                )
                continue
            resolved = resolution.anchor
            if not anchors.within_evidence(resolved, evidence):
                notes.append(
                    f"{objective.id}: {resolved.file}:{named} "
                    "(not part of the dossier's verified evidence)"
                )
                continue
            kept.append(
                AnchorWire(
                    file=resolved.file,
                    symbol=anchor.symbol,
                    resolved_start=resolved.line_start,
                    resolved_end=resolved.line_end,
                    resolved_symbol=resolved.symbol,
                )
            )
        if not kept:
            notes.append(f"{objective.id}: dropped — no anchor survived grounding")
            continue
        grounded = objective.model_copy()
        grounded.anchors = kept
        survivors.append(grounded)
    return survivors, notes


def drop_dangling_dependencies(
    objectives: list[ObjectiveWire],
) -> list[ObjectiveWire]:
    """Strip `depends_on` entries whose objective did not survive grounding.

    Without this, a dropped unit would leave a dependency nothing can satisfy —
    `resume_point()` would then hold the learner behind a prerequisite that is
    not in the graph.
    """
    alive = {o.id for o in objectives}
    cleaned = []
    for objective in objectives:
        pruned = objective.model_copy()
        pruned.depends_on = [d for d in objective.depends_on if d in alive]
        cleaned.append(pruned)
    return cleaned


# ── graph construction ─────────────────────────────────────────────────────────


def _anchor_payload(anchor: AnchorWire) -> dict:
    return {
        "file": anchor.file,
        "symbol": anchor.resolved_symbol or anchor.symbol,
        "line_start": anchor.resolved_start,
        "line_end": anchor.resolved_end,
    }


def build_graph(
    state: OnboardState,
    areas: list[AreaWire],
    ordered: list[ObjectiveWire],
) -> LearningGraph:
    """Ordered, grounded units → a LearningGraph.

    Two edge kinds are written at plan time now: the `sequence` chain the
    learner walks, and `prerequisite` edges mirroring `depends_on`. The second
    is what makes prerequisites real — before this they existed only as
    post-failure remediation, which left `resume_point()`'s prerequisite check
    nearly vacuous on a fresh graph (§6.4).

    Traversal is untouched. `next_in_path` already prefers sequence over
    prerequisite and `path_order` already handles both, which is exactly why the
    graph model survives this phase intact.
    """
    graph = LearningGraph(repo_url=state.repo_url, goal=state.goal)
    graph.doc_context = state.doc_context
    graph.areas = [
        {"id": a.id, "title": a.title, "why": a.why, "order": a.order}
        for a in sorted(areas, key=lambda a: a.order)
    ]

    wire_to_uuid: dict[str, str] = {}
    for objective in ordered:
        display = objective.anchors[0]
        node = LearningNode(
            title=objective.title,
            # The display anchor: a UI affordance, derived, carrying no claim
            # that this location matters most. The prompt puts the entry point
            # or the owning side first, which is what makes "the first anchor"
            # the right rule rather than an arbitrary one (§4.1.1).
            code_anchor=CodeAnchor(
                file=display.file,
                line_start=int(display.resolved_start or 0),
                line_end=int(display.resolved_end or 0),
                symbol=display.resolved_symbol,
            ),
            # `kind` leads the tags so the four agents and the frontend colour
            # map that already read concept_tags[0] see the primary tag first.
            concept_tags=[objective.kind]
            + [t for t in objective.concept_tags if t != objective.kind],
            lesson_brief={
                "objective": objective.objective,
                "why": objective.why,
                "kind": objective.kind,
                "priority": objective.priority,
                "area_id": objective.area_id,
                # The semantic truth about where this unit lives. The columns
                # above hold a derived projection of it; the invariant is that
                # they always equal one member of this list (§10).
                "anchors": [_anchor_payload(a) for a in objective.anchors],
            },
        )
        graph.add_node(node)
        wire_to_uuid[objective.id] = node.id

    for previous, current in zip(ordered, ordered[1:]):
        graph.add_edge(
            wire_to_uuid[previous.id], wire_to_uuid[current.id], kind="sequence"
        )

    for objective in ordered:
        for dependency in objective.depends_on:
            source = wire_to_uuid.get(dependency)
            if source is None or source == wire_to_uuid[objective.id]:
                continue
            graph.add_edge(source, wire_to_uuid[objective.id], kind="prerequisite")

    head = wire_to_uuid.get(ordered[0].id) if ordered else None
    if head is not None:
        graph.set_current(head)
    return graph


def to_learning_path(graph: LearningGraph) -> list[dict]:
    """The flat Phase-1 step list the /onboard response still returns."""
    nodes = list(graph.nodes.values())
    return [
        {
            "step": i + 1,
            "title": node.title,
            "file": node.code_anchor.file,
            "line_range": [node.code_anchor.line_start, node.code_anchor.line_end],
            "objective": node.lesson_brief.get("objective", ""),
            "why": node.lesson_brief.get("why", ""),
            "concepts": list(node.concept_tags),
        }
        for i, node in enumerate(nodes)
    ]


# ── run ────────────────────────────────────────────────────────────────────────


def _parse_output(raw: str) -> CurriculumOutput:
    # Leading fence only — `raw_decode` ends the object for us, and cutting at
    # the closing fence truncates any payload containing one of its own.
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else ""
    start = raw.find("{")
    if start < 0:
        raise ValueError("no JSON object found in response")
    decoded, _ = json.JSONDecoder().raw_decode(raw[start:])
    return CurriculumOutput(**decoded)


def _plan_report(
    output: CurriculumOutput,
    grounded: list[ObjectiveWire],
    core: set[str],
    selected: list[ObjectiveWire],
    code_depth: str,
) -> dict:
    """What the planner proposed, what the cut kept, and whether the band bound.

    `core` is the number that matters for judging the band: it is what the
    curriculum genuinely needs, measured before the guard is applied. A band
    that binds on ordinary runs is set below real demand.
    """
    low, high = _SCOPE_BANDS.get(code_depth, _DEFAULT_BAND)
    journey = journey_size(selected)
    # The ceiling bound iff something the model wanted taught ended up demoted.
    proposed_priority = {o.id: o.priority for o in grounded}
    demoted = [
        o.id for o in selected
        if o.priority == "optional"
        and o.id not in core
        and proposed_priority.get(o.id) != "optional"
    ]
    bound = "ceiling" if demoted else ("floor" if journey < low else None)
    return {
        "code_depth": code_depth,
        "proposed": len(output.objectives),
        "grounded": len(grounded),
        "dropped_by_grounding": len(output.objectives) - len(grounded),
        # The required set + dependency closure + area-coverage promotions,
        # before the band — §6.3's calibration input.
        "core_before_band": len(core),
        "journey": journey,
        "optional": len(selected) - journey,
        "band": [low, high],
        "band_bound": bound,
        "demoted_by_band": len(demoted),
        "areas_declared": len(output.areas),
        "covers_goal": output.covers_goal,
    }


# Appended to the user turn on the one retry after a truncated proposal.
#
# It asks for the SAME curriculum written tighter — never for fewer objectives.
# "Propose less" is a size instruction, and putting one back into this prompt
# would undo the whole point of B3 (L1): the model does not choose the length,
# our code does. A retry that shrinks the curriculum to fit a token budget is
# the old failure wearing a new hat.
_TOO_LONG = """

YOUR PREVIOUS RESPONSE WAS CUT OFF before the JSON closed, because it was too
long. Return the SAME curriculum again — the same objectives, the same
priorities, the same anchors, nothing dropped — but written to fit:

  - `why`: at most 10 words, or omit the reasoning and state the connection
  - `title`: a short imperative, under 8 words
  - `objective`: keep it complete. This is the one field worth its length.
  - no trailing commentary of any kind, inside or outside the JSON

Do NOT reduce the number of objectives. The length problem is prose, not
count."""


def _propose(client, user_content: str, suffix: str = ""):
    """One proposal call. Returns (response, raw text)."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content + suffix}],
    )
    return response, response.content[0].text


def _was_truncated(response) -> bool:
    """Did the model run out of room, rather than write something malformed?

    The API says so directly. Matching on the decoder's message ("Unterminated
    string...") would work today and break the day the payload happens to end
    on a different token — and it cannot tell a truncated response from a
    genuinely malformed one, which wants a different fix.
    """
    return getattr(response, "stop_reason", None) == "max_tokens"


_CONFIDENCE_CAP = {"high": "medium", "medium": "medium", "low": "low"}


def run(state: OnboardState, client: anthropic.Anthropic | None = None) -> OnboardState:
    """Plan the curriculum. Same contract as every other agent: never raises."""
    if client is None:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    if state.goal is None:
        state.errors.append("curriculum: goal missing")
        return state
    investigation_state = state.investigation or {}
    dossier = investigation_state.get("dossier")
    if not dossier:
        # D15: no dossier, no graph. Fabricating one is the behaviour the
        # repository-understanding migration existed to remove.
        state.errors.append("curriculum: no investigation dossier to plan from")
        return state

    try:
        skeleton = build_skeleton(state.repo_path)
    except Exception as e:
        state.errors.append(f"curriculum: skeleton build failed: {e}")
        return state

    evidence = _dossier_evidence_ranges(skeleton, dossier)
    if not evidence:
        state.errors.append("curriculum: dossier contains no resolvable evidence")
        return state

    user_content = render_dossier(
        skeleton, dossier, state.goal, system_review=state.system_review
    )

    try:
        response, raw = _propose(client, user_content)
        try:
            output = _parse_output(raw)
        except Exception as parse_error:
            if not _was_truncated(response):
                raise
            # One bounded retry, and only for the failure we can name. A
            # malformed-but-complete payload is a different problem and is not
            # retried here — repeating a call that produced valid-length
            # nonsense mostly buys a second helping of it.
            state.errors.append(
                f"curriculum: proposal truncated at the token limit "
                f"({parse_error}); retried once, asking for the same "
                f"curriculum written tighter"
            )
            _, raw = _propose(client, user_content, _TOO_LONG)
            output = _parse_output(raw)
    except Exception as e:
        state.errors.append(f"curriculum: proposal call failed: {e}")
        return state

    grounded, notes = ground(output.objectives, skeleton, evidence)
    if notes:
        state.errors.append("curriculum: " + "; ".join(notes))
    if not grounded:
        state.errors.append("curriculum: no grounded objectives survived")
        return state

    grounded = drop_dangling_dependencies(grounded)
    code_depth = str(state.goal.get("code_depth") or "working")
    core = core_set(grounded, output.areas)
    selected = select(grounded, output.areas, code_depth)
    state.plan_report = _plan_report(
        output, grounded, core, selected, code_depth
    )
    report = band_report(selected, code_depth)
    if report:
        state.errors.append(report)
    if not output.covers_goal:
        # The planner's own self-check (§6.5). Recorded rather than fatal: a
        # partial curriculum over a thin dossier still beats no curriculum, and
        # the honest signal belongs in confidence.
        state.errors.append(
            f"curriculum: planner reports incomplete coverage — {output.coverage_note}"
        )

    ordered = order(selected, output.areas)
    graph = build_graph(state, output.areas, ordered)
    state.graph = graph
    state.learning_path = to_learning_path(graph)

    confidence = output.confidence
    if not investigation_state.get("accepted", False) or not output.covers_goal:
        # §5.4: a dossier salvaged at budget exhaustion carries a recorded gap,
        # and so does a curriculum whose own planner says it misses the goal.
        # Downstream confidence must not exceed what the evidence supports.
        confidence = _CONFIDENCE_CAP[confidence]
    state.confidence = confidence
    return state
