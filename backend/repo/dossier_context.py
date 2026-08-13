# Node-scoped context selection from the Investigation Dossier (Stage 4).
#
# The dossier holds the whole goal's understanding; one lesson needs a slice of
# it. This module computes that slice DETERMINISTICALLY, by walking the
# structure we already have:
#
#     current node (file + symbol + range)
#         -> the dossier component that describes it
#         -> the flow steps it participates in, and its immediate neighbours
#         -> relationships touching it
#         -> contracts on it
#         -> prerequisites pointing at it
#         -> supporting evidence
#
# Explicitly NOT a search index over the dossier. No embeddings, no scoring, no
# `top_k` reinvented one layer up: matching is anchor identity (resolved through
# the Stage-0 oracle so "Session.send" and a raw range agree), with a symbol/file
# fallback for entries the resolver cannot place. If a lesson genuinely needs
# something the dossier does not connect to the node, that is an explicit
# extension to design — not a reason to reach back into Chroma.
#
# Shared by Teaching (context for the current lesson) and the Mutator
# (prerequisite candidates around a confused node) so both see the same slice
# computed the same way.

from __future__ import annotations

from dataclasses import dataclass, field

from backend.repo import anchors
from backend.repo.investigation import _entries
from backend.repo.skeleton import Skeleton, normalize_path

# How many entries of each kind reach a single lesson. These bound the RENDERING
# of a slice that is already node-scoped by structure — they are not a retrieval
# cutoff choosing what is relevant. A node with three relationships shows three.
MAX_RELATIONSHIPS = 6
MAX_FLOW_NEIGHBOURS = 2      # steps either side of the node within a flow
MAX_PREREQUISITES = 4
MAX_CONTRACTS = 3
MAX_EVIDENCE = 3


def _key(skeleton: Skeleton, file, symbol) -> tuple | None:
    """Resolved anchor identity for a (file, symbol) pair, or None."""
    if not file or not symbol:
        return None
    resolution = anchors.resolve(skeleton, str(file), symbol=str(symbol))
    return resolution.anchor.as_tuple() if resolution.ok else None


def _loose(file, symbol) -> tuple[str, str]:
    """Fallback identity when the resolver cannot place an entry."""
    return (normalize_path(str(file or "")), str(symbol or ""))


@dataclass
class NodeContext:
    """The dossier's understanding of one learning node's place in the system."""

    component: dict | None = None            # role_in_goal + why_it_matters
    flow_position: list[dict] = field(default_factory=list)   # ordered neighbourhood
    relationships: list[dict] = field(default_factory=list)
    contracts: list[dict] = field(default_factory=list)
    prerequisites: list[dict] = field(default_factory=list)
    evidence_refs: list[dict] = field(default_factory=list)
    understanding: str = ""                  # the goal-level framing
    open_questions: list[dict] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not any((
            self.component, self.flow_position, self.relationships,
            self.contracts, self.prerequisites, self.understanding,
        ))

    def as_prompt_section(self) -> str:
        """The slice as prompt text. Empty string when there is nothing to add."""
        if self.is_empty:
            return ""
        parts: list[str] = ["System context for this piece of code, from the "
                            "investigation of the developer's goal:"]
        if self.understanding:
            parts.append(f"  What the goal is really about: {self.understanding}")
        if self.component:
            parts.append(
                f"  This code's role in the goal: {self.component.get('role_in_goal')}\n"
                f"  Why it matters here: {self.component.get('why_it_matters')}"
            )
        if self.flow_position:
            parts.append("  Where it sits in the verified execution flow:")
            for step in self.flow_position:
                marker = ">>" if step.get("is_current") else "  "
                parts.append(
                    f"    {marker} {step.get('file')}:{step.get('symbol')}"
                    f" — {step.get('what_happens')}"
                )
        if self.relationships:
            parts.append("  Confirmed relationships:")
            for r in self.relationships:
                parts.append(
                    f"    {r.get('from_symbol')} --{r.get('kind')}--> "
                    f"{r.get('to_symbol')}  ({r.get('note')})"
                )
        if self.contracts:
            parts.append("  Contracts this code is written against:")
            for c in self.contracts:
                parts.append(f"    {c.get('symbol')}: {c.get('contract')}")
        if self.prerequisites:
            parts.append("  Concepts the developer needs for this:")
            for p in self.prerequisites:
                parts.append(f"    {p.get('concept')}: {p.get('why_needed')}")
        if self.evidence_refs:
            parts.append("  Tests/docs that clarify this behaviour:")
            for e in self.evidence_refs:
                parts.append(f"    {e.get('path')} — {e.get('clarifies')}")
        if self.open_questions:
            parts.append(
                "  Recorded uncertainty — NOT established fact, do not teach as true:"
            )
            for q in self.open_questions:
                parts.append(f"    {q.get('question')}")
        return "\n".join(parts)


def context_for_node(
    skeleton: Skeleton,
    dossier: dict,
    file: str,
    symbol: str | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
) -> NodeContext:
    """The dossier slice describing one node. Never raises; empty when unmatched."""
    if not dossier:
        return NodeContext()

    resolution = anchors.resolve(
        skeleton, file, symbol=symbol, line_start=line_start, line_end=line_end
    )
    node_key = resolution.anchor.as_tuple() if resolution.ok else None
    node_symbol = (resolution.anchor.symbol if resolution.ok else symbol) or ""
    node_file = normalize_path(
        resolution.anchor.file if resolution.ok else (file or "")
    )
    node_loose = (node_file, node_symbol)

    def matches(entry_file, entry_symbol) -> bool:
        key = _key(skeleton, entry_file, entry_symbol)
        if node_key is not None and key is not None:
            return key == node_key
        return _loose(entry_file, entry_symbol) == node_loose

    context = NodeContext(understanding=str(dossier.get("understanding") or "").strip())

    for entry in _entries(dossier, "components")[0]:
        if matches(entry.get("file"), entry.get("symbol")):
            context.component = entry
            break

    # Flow neighbourhood: the node's own step plus what happens immediately
    # before and after it. That is what makes a lesson able to say "this runs
    # after X and hands off to Y" without dumping the whole trace.
    for flow in _entries(dossier, "flows")[0]:
        steps = [s for s in (flow.get("steps") or []) if isinstance(s, dict)]
        for index, step in enumerate(steps):
            if not matches(step.get("file"), step.get("symbol")):
                continue
            low = max(0, index - MAX_FLOW_NEIGHBOURS)
            high = min(len(steps), index + MAX_FLOW_NEIGHBOURS + 1)
            for position in range(low, high):
                neighbour = dict(steps[position])
                neighbour["is_current"] = position == index
                neighbour["flow"] = flow.get("name")
                context.flow_position.append(neighbour)
            break
        if context.flow_position:
            break

    for entry in _entries(dossier, "relationships")[0]:
        if (
            matches(entry.get("from_file"), entry.get("from_symbol"))
            or matches(entry.get("to_file"), entry.get("to_symbol"))
        ):
            context.relationships.append(entry)
        if len(context.relationships) >= MAX_RELATIONSHIPS:
            break

    related_symbols = {node_symbol} | {
        str(r.get("to_symbol") or "") for r in context.relationships
    } | {str(r.get("from_symbol") or "") for r in context.relationships}

    for entry in _entries(dossier, "contracts")[0]:
        if matches(entry.get("file"), entry.get("symbol")) or (
            str(entry.get("symbol") or "") in related_symbols
        ):
            context.contracts.append(entry)
        if len(context.contracts) >= MAX_CONTRACTS:
            break

    for entry in _entries(dossier, "prerequisites")[0]:
        anchored = entry.get("file") and entry.get("symbol")
        if anchored and matches(entry.get("file"), entry.get("symbol")):
            context.prerequisites.append(entry)
        elif not anchored and context.component is not None:
            # An unanchored concept applies to the goal as a whole; include it
            # only when this node is actually part of the goal's component set,
            # so unrelated nodes do not inherit every general concept.
            context.prerequisites.append(entry)
        if len(context.prerequisites) >= MAX_PREREQUISITES:
            break

    node_basename = node_file.rsplit("/", 1)[-1]
    for entry in _entries(dossier, "evidence_refs")[0]:
        path = normalize_path(str(entry.get("path") or ""))
        clarifies = str(entry.get("clarifies") or "")
        if (
            node_symbol and node_symbol.split(".")[-1] in clarifies
        ) or node_basename and node_basename.removesuffix(".py") in path:
            context.evidence_refs.append(entry)
        if len(context.evidence_refs) >= MAX_EVIDENCE:
            break

    if context.component is not None:
        for entry in _entries(dossier, "open_questions")[0]:
            question = str(entry.get("question") or "")
            if node_symbol and node_symbol.split(".")[-1] in question:
                context.open_questions.append(entry)

    return context


# ── prerequisite candidates for the Mutator ───────────────────────────────────


@dataclass
class PrereqCandidate:
    """One structurally-derived candidate. Selection is a separate, model step."""

    file: str
    symbol: str
    source: str              # which part of the dossier suggested it
    rationale: str
    concept: str = ""

    def label(self) -> str:
        return f"{self.file}:{self.symbol}"


def prerequisite_candidates(
    skeleton: Skeleton,
    dossier: dict,
    file: str,
    symbol: str | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
    exclude: set[tuple[str, int, int]] | None = None,
) -> list[PrereqCandidate]:
    """Structural candidates for what a confused developer might be missing.

    D8: this produces the CANDIDATE SET only. Which of them is the smallest
    missing foundation is a pedagogical judgement made by the Mutator's model
    step — structural dependency is not pedagogical prerequisite, and deriving
    the answer straight from the edges here would be exactly the mistake D8
    names.

    Sources, in the order a teacher would reach for them:
      1. anchored prerequisites the investigation recorded for this node
      2. what this node depends on (outgoing relationships) — you cannot
         understand a caller without its callee
      3. contracts the node is written against
      4. the step immediately before it in a verified flow
    """
    exclude = exclude or set()
    context = context_for_node(
        skeleton, dossier, file, symbol=symbol,
        line_start=line_start, line_end=line_end,
    )
    candidates: list[PrereqCandidate] = []
    seen: set[tuple] = set()

    def offer(entry_file, entry_symbol, source: str, rationale: str, concept: str = "") -> None:
        if not entry_file or not entry_symbol:
            return
        resolution = anchors.resolve(skeleton, str(entry_file), symbol=str(entry_symbol))
        if not resolution.ok:
            return
        anchor = resolution.anchor
        if anchor.as_tuple() in exclude or anchor.as_tuple() in seen:
            return
        seen.add(anchor.as_tuple())
        candidates.append(PrereqCandidate(
            file=anchor.file, symbol=anchor.symbol or str(entry_symbol),
            source=source, rationale=rationale, concept=concept,
        ))

    for entry in context.prerequisites:
        offer(entry.get("file"), entry.get("symbol"), "prerequisite",
              str(entry.get("why_needed") or ""), str(entry.get("concept") or ""))

    node_symbol = context.component.get("symbol") if context.component else symbol
    for entry in context.relationships:
        if str(entry.get("from_symbol") or "") == str(node_symbol or ""):
            offer(entry.get("to_file"), entry.get("to_symbol"), "depends_on",
                  f"the confused node {entry.get('kind')} this: {entry.get('note')}")
        elif str(entry.get("to_symbol") or "") == str(node_symbol or ""):
            # Incoming edges matter for the opposite reason: an abstraction with
            # no outgoing dependencies (a base class, an interface) is often best
            # approached through one concrete thing that uses it. Without this a
            # node like `AuthBase` yields no candidates at all — observed.
            offer(entry.get("from_file"), entry.get("from_symbol"), "used_by",
                  f"this {entry.get('kind')} the confused node, so it is a "
                  f"concrete example of it: {entry.get('note')}")

    for entry in context.contracts:
        offer(entry.get("file"), entry.get("symbol"), "contract",
              str(entry.get("contract") or ""))

    for index, step in enumerate(context.flow_position):
        if step.get("is_current") and index > 0:
            previous = context.flow_position[index - 1]
            offer(previous.get("file"), previous.get("symbol"), "flow_predecessor",
                  f"runs immediately before it in '{step.get('flow')}': "
                  f"{previous.get('what_happens')}")
            break

    return candidates
