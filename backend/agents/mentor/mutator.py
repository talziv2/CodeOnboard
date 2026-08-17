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

from backend.learning import history, progress
from backend.learning.adaptation import decide_all
from backend.learning.gaps import Gap
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.pipeline.state import OnboardState
from backend.repo import anchors, dossier_context, dossier_store, structure
from backend.repo.skeleton import Skeleton, build_skeleton, normalize_path


MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024

# How many candidate chunks to offer Sonnet when generating a prerequisite.
CANDIDATE_COUNT = 5


@dataclass(frozen=True)
class Diagnosis:
    """What the learner actually got wrong, for the branch that reshapes the graph.

    `hint`, `followup` and `reteach` have always received the learner's answer and
    the Grader's rationale; `prerequisite` — the only adaptation that changes the
    graph — received neither (learning-engine.md §18.2). It selected a warm-up for
    the NODE, from structural candidates, without knowing what the developer
    believed. When that happened to look well-targeted it was proximity, not
    diagnosis: the same warm-up would have been generated for any wrong answer on
    that node.

    Optional everywhere. A caller with no grade in hand — an older session, a
    direct `mutate()` call in a test — passes nothing and gets the previous
    behaviour exactly.
    """

    answer: str = ""
    rationale: str = ""
    gap_kind: str = ""
    # The ONE gap this warm-up exists to unblock (M5, §18.6). Selected by the
    # M4 plan, never inferred here from `gap_kind` — the scalar names a category
    # and a warm-up has to be built for a specific false belief.
    #
    # Singular by policy: §18.5 allows one structural mutation per graded answer,
    # so there is exactly one gap to carry. Its id is recorded on the inserted
    # node as `lesson_brief["remediates"]`, which is how M6 later knows what this
    # warm-up was supposed to fix.
    gap: Gap | None = None

    def __bool__(self) -> bool:
        return bool(self.answer.strip() or self.rationale.strip() or self.gap is not None)

    @classmethod
    def from_attempt(cls, attempt: dict | None) -> "Diagnosis | None":
        """Build one from a recorded attempt, or None if there is nothing to say.

        `/retry` reaches the Mutator with no grade in scope — the learner clicked
        "build me a warm-up" some time after answering. The diagnosis is on the
        node, in `attempts`, which until now nothing read.
        """
        if not attempt:
            return None
        diagnosis = cls(
            answer=str(attempt.get("answer") or ""),
            rationale=str(attempt.get("rationale") or ""),
            gap_kind=str(attempt.get("gap_kind") or ""),
        )
        return diagnosis or None

    @classmethod
    def from_node(cls, node: LearningNode) -> "Diagnosis | None":
        """The diagnosis for a warm-up requested after the fact, off the node.

        `/retry` has no grade in scope, and an attempt record carries the scalar
        `gap_kind` but no gap ids — so the specific `Gap` cannot come from there.
        It comes from the same place `/respond` gets it: the M4 plan, run over
        the node's own open gaps. Inferring one from `gap_kind` instead would be
        exactly the downstream re-derivation M5 exists to remove — the scalar
        names a category, and several open gaps can share it.

        Falls back to the attempt alone when the node has no gaps, which is
        every flag-off session and every session written before the gap model.
        """
        # The latest ASSESSMENT. `attempts[-1]` would hand the Mutator a
        # verification answer whenever one was graded most recently — a reply
        # to a different question — and the warm-up would be chosen for it.
        # That is precisely the diagnosis-blindness §18.2 exists to end.
        assessed = history.assessments(node.attempts)
        attempt = assessed[-1] if assessed else None
        base = cls.from_attempt(attempt)
        if not node.gaps:
            return base

        # `partial` rather than the recorded classification: this is a learner
        # ASKING for a warm-up, so the question is only which gap it should
        # unblock, not whether the answer earned one. Passing the recorded
        # verdict could return `none` and leave the warm-up unaimed.
        plan = decide_all("partial", list(node.gaps))
        gap = plan.targets[0] if plan.action == "prerequisite" and plan.targets else None
        if gap is None:
            # No foundational gap leads. The learner still asked for a warm-up
            # and still gets one; it is simply aimed by the answer rather than
            # by a specific false belief, which is the pre-M5 behaviour.
            return base
        return cls(
            answer=base.answer if base else "",
            rationale=base.rationale if base else "",
            gap_kind=gap.kind,
            gap=gap,
        )


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
    diagnosis: Diagnosis | None = None,
    origin: str = progress.SYSTEM_REMEDIATION,
) -> OnboardState:
    """`origin` records WHO asked for the warm-up (learning-engine.md §18.11).

    It defaults to `system_remediation` because that is what a policy-driven
    insertion is; `/retry` passes `learner_request`. Progress excludes both from
    its measures either way — the distinction exists because §18.11 protects a
    learner-requested warm-up from demotion, and because "you asked to step
    back" and "the system sent you back" are different things to show someone.
    """
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
        return _mutate_prerequisite(state, current, client, diagnosis, origin)

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
    """Has a REMEDIAL warm-up already been spliced in before this node?

    Counting every `prerequisite` edge was correct until B3, when the planner
    began emitting one per `depends_on` — dozens per journey. On such a graph
    almost every unit has an incoming prerequisite edge before the learner
    answers anything, so this guard was permanently satisfied and remediation
    could never fire except on the few units nothing depends on. Measured: a
    real `psf/requests` journey declined every insertion with
    `prerequisite_exists`, on nodes that had never been remediated.

    The distinction is the one `learning/graph.py` documents: `insert_before`
    reroutes the incoming sequence edge onto the spliced node, so a REMEDIAL
    node has no outgoing `sequence` edge, while a planned dependency sits on the
    chain and keeps one.
    """
    has_sequence_out = {
        e.from_node_id for e in graph.edges if e.kind == "sequence"
    }
    return any(
        e.kind == "prerequisite"
        and e.to_node_id == node_id
        and e.from_node_id not in has_sequence_out
        for e in graph.edges
    )


def _mutate_prerequisite(
    state: OnboardState,
    current: str,
    client: anthropic.Anthropic,
    diagnosis: Diagnosis | None = None,
    origin: str = progress.SYSTEM_REMEDIATION,
) -> OnboardState:
    graph = state.graph

    # Guard: at most one prerequisite per node. Repeated confusion shouldn't
    # stack endless prereqs (and shouldn't burn a Sonnet call each time).
    if _has_prerequisite(graph, current):
        state.last_mutation = {"kind": "none", "reason": "prerequisite_exists"}
        return state

    anchor = graph.nodes[current]
    if diagnosis is None:
        # `/retry` arrives with no grade in scope: the learner asked for a warm-up
        # after the fact. The diagnosis is already on the node.
        diagnosis = Diagnosis.from_node(anchor)
    new_node = _generate_prerequisite_node(state, anchor, client, diagnosis, origin)
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
    state: OnboardState,
    anchor: LearningNode,
    client: anthropic.Anthropic,
    diagnosis: Diagnosis | None = None,
    origin: str = progress.SYSTEM_REMEDIATION,
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
        anchor, candidates, state.goal or {}, structural=structural,
        diagnosis=diagnosis,
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
            # A warm-up the learner demonstrably needed is not optional and is
            # not up for demotion — "make it shorter" must never take away the
            # remediation that unblocked them. Stated rather than left absent:
            # an empty priority happens to behave correctly everywhere today,
            # and correctness by accident is one refactor from being wrong.
            "priority": "required",
            # A DETOUR, not a stop on the promised journey. This is what keeps
            # the progress gauge from falling when the system decides to help:
            # `progress` excludes remedial units from both sides of goal
            # readiness, and `priority: required` above would otherwise put this
            # node straight into the denominator (learning-graph.md §5.2 D1).
            progress.ORIGIN_KEY: origin,
            # WHICH false belief this warm-up was built to unblock (M5, §18.6).
            # M6 reads it to know what passing this node is evidence about —
            # without it, a warm-up is a node that appeared near a failure, and
            # nothing downstream can tell which gap it was supposed to close.
            #
            # A LIST with one entry, not a scalar: §18.5 caps the structural
            # mutation at one gap per answer, so one is all there can be today,
            # but the field describes a relationship that is naturally many and
            # a later widening should not have to change its shape. Omitted
            # entirely when there is no gap, so pre-gap warm-ups and flag-off
            # sessions keep the brief they have always had.
            **({"remediates": [diagnosis.gap.id]}
               if diagnosis is not None and diagnosis.gap is not None else {}),
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
- If the user content includes WHAT THE DEVELOPER ACTUALLY WROTE and why it fell
  short, that diagnosis decides BETWEEN candidates that clear the foundational
  bar — it does not lower the bar. Among candidates that are genuinely more
  foundational, choose the one that unblocks THAT specific misconception. A
  candidate that speaks directly to what they got wrong but is a peer of the
  node, not a foundation for it, is still the wrong answer: return
  {"decision": "none"} rather than teaching a sibling concept. Never repeat the
  misconception back as a lesson topic — teach the foundation that makes it
  impossible to hold.
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
    diagnosis: Diagnosis | None = None,
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
    # What they actually got wrong, when we know it. Placed BEFORE the node
    # description because it is the sharper signal: the node says which lesson
    # failed, this says why.
    diagnosed = ""
    if diagnosis:
        parts = []
        if diagnosis.answer.strip():
            parts.append("What the developer actually wrote:\n" + diagnosis.answer.strip())
        if diagnosis.rationale.strip():
            parts.append("Why it fell short:\n" + diagnosis.rationale.strip())
        # The specific false belief this warm-up exists to unblock, when the
        # policy named one. Placed last so it is the final thing read before the
        # candidates, and stated as a claim rather than a category: "they believe
        # X" is something a warm-up can be chosen against, where `wrong_model`
        # only says a warm-up is warranted.
        if diagnosis.gap is not None:
            gap_lines = [
                "THE MISCONCEPTION THIS WARM-UP MUST UNBLOCK:\n"
                f"  {diagnosis.gap.claim}"
            ]
            if diagnosis.gap.objective_part.strip():
                gap_lines.append(
                    f"  (it violates: {diagnosis.gap.objective_part.strip()})"
                )
            gap_lines.append(
                "Choose the candidate that builds the foundation this belief is "
                "missing — not merely one near the node they failed."
            )
            parts.append("\n".join(gap_lines))
        elif diagnosis.gap_kind and diagnosis.gap_kind != "none":
            parts.append(f"Diagnosed gap: {diagnosis.gap_kind}")
        diagnosed = "\n\n".join(parts) + "\n\n" if parts else ""
    return (
        f"Developer profile:\n"
        f"  familiarity with THIS codebase: {goal.get('familiarity', 'unknown')}\n"
        f"  background: {goal.get('background', 'unknown')}\n\n"
        f"{diagnosed}"
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
