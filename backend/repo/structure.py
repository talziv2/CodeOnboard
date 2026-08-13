# Skeleton-backed structural neighbours — the Mutator's second candidate source.
#
# WHY THIS EXISTS. The Dossier is goal-specific and deliberately selective, and
# the native-Dossier Mentor is good at using it: measured across eight sessions,
# it turned nearly every verified anchor into a learning node. So by the time a
# developer gets confused, the dossier's neighbourhood of the confused node is
# usually *already the graph*, and excluding what has been taught leaves nothing
# to offer. Three sessions had 0-2 dossier anchors that were not already nodes.
#
# That emptiness is a property of the dossier's scope, not a reason to reach for
# semantic retrieval. Layer A already knows the whole repository structurally —
# base classes, methods, callees, callers, imports — and every edge it reports is
# exact or explicitly approximate, and anchorable. This module turns those edges
# into candidates.
#
# WHAT IT IS NOT. It does not decide what to teach. D8 stands: structural
# dependency is not pedagogical prerequisite, and the ordering here is "how a
# teacher would reach for them", not a ranking of importance. The Mutator's model
# step makes the choice, and is free to choose none.
#
# The Dossier stays first. This widens the pool when goal-specific evidence has
# been exhausted; it never replaces it.

from __future__ import annotations

import re

from backend.repo import anchors
from backend.repo.dossier_context import PrereqCandidate
from backend.repo.skeleton import Skeleton, Symbol

# Names that carry no teaching value as a prerequisite, however often they appear.
_NOISE = frozenset({
    "self", "cls", "super", "type", "object", "str", "int", "bool", "dict",
    "list", "set", "tuple", "len", "print", "range", "property", "staticmethod",
    "classmethod", "Exception", "ValueError", "TypeError", "KeyError",
})

_IDENTIFIER = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")

# Per-source caps. The pool is a shortlist for a reasoning step, not a report.
MAX_PER_SOURCE = 4
MAX_CANDIDATES = 8


def _callees(skeleton: Skeleton, symbol: Symbol) -> list[Symbol]:
    """Indexed symbols whose names appear inside this symbol's body.

    Name-based, and honest about it: Python has no call graph without type
    inference, and `neighbors` already reports its `references` relation as
    approximate for the same reason. It is safe here because a candidate is only
    ever *offered* — it must still resolve through the Stage-0 oracle, and the
    Mutator's model step sees the code before choosing.

    Same-file definitions come first: a helper beside the confused function is a
    likelier foundation than a same-named symbol from an unrelated module.
    """
    source = skeleton.read_lines(symbol.file, symbol.line_start, symbol.line_end)
    if not source:
        return []
    # A name from another module can only be reached if this file imported it.
    # Without that filter, `.items()` and `.keys()` match unrelated classes'
    # methods across the repository and crowd out the real callees — observed on
    # `merge_setting`, whose four cross-file "callees" were all attribute noise.
    imported = {
        name
        for entry in skeleton.imports_in(symbol.file)
        for name in entry.names
    }
    imported |= {
        (entry.module or "").rsplit(".", 1)[-1]
        for entry in skeleton.imports_in(symbol.file)
    }
    found: list[Symbol] = []
    seen: set[tuple[str, int, int]] = set()
    for name in dict.fromkeys(_IDENTIFIER.findall(source)):
        if name in _NOISE or name == symbol.name:
            continue
        matches = skeleton.find_symbol(name)
        if not matches or len(matches) > 3:
            continue      # a name defined all over the repo identifies nothing
        for match in matches:
            key = (match.file, match.line_start, match.line_end)
            if key in seen or match.role != "source":
                continue
            if match.file != symbol.file and name not in imported:
                continue  # not in this file's vocabulary: a same-name coincidence
            if match.line_start >= symbol.line_start and match.line_end <= symbol.line_end:
                continue  # defined inside the confused symbol: not a foundation
            seen.add(key)
            found.append(match)
    found.sort(key=lambda s: (s.file != symbol.file, s.file, s.line_start))
    return found


def _callers(skeleton: Skeleton, symbol: Symbol) -> list[Symbol]:
    """Symbols that mention this one — a concrete use of an abstraction.

    The mirror of `_callees`, and the answer for a base class or interface whose
    own dependencies are nothing: the way into `AuthBase` is something that
    subclasses it.
    """
    pattern = re.compile(rf"\b{re.escape(symbol.name)}\b")
    found: list[Symbol] = []
    for candidate in skeleton.symbols:
        if candidate.role != "source" or candidate.file == symbol.file:
            continue
        source = skeleton.read_lines(
            candidate.file, candidate.line_start, candidate.line_end
        )
        if source and pattern.search(source):
            found.append(candidate)
        if len(found) >= MAX_PER_SOURCE * 3:
            break
    return found


def neighbour_candidates(
    skeleton: Skeleton,
    file: str,
    symbol: str | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
    exclude: set[tuple[str, int, int]] | None = None,
    exclude_symbols: set[tuple[str, str]] | None = None,
    limit: int = MAX_CANDIDATES,
) -> list[PrereqCandidate]:
    """Structural neighbours of the confused code, as prerequisite candidates.

    Sources, in the order a teacher would reach for them:
      1. base classes — you cannot read a subclass without its contract
      2. the enclosing class of a method, or a class's own methods
      3. what the code calls
      4. what calls it, for an abstraction that depends on nothing
      5. what its module imports from elsewhere in the repository
    """
    exclude = set(exclude or ())
    exclude_symbols = set(exclude_symbols or ())
    resolution = anchors.resolve(
        skeleton, file, symbol=symbol, line_start=line_start, line_end=line_end
    )
    if not resolution.ok:
        return []
    anchor = resolution.anchor
    target = skeleton.exact_symbol(anchor.file, anchor.line_start, anchor.line_end)
    if target is None:
        target = skeleton.enclosing_symbol(anchor.file, anchor.line_start, anchor.line_end)
    if target is None:
        return []

    candidates: list[PrereqCandidate] = []
    seen: set[tuple[str, int, int]] = set()
    offered: set[tuple[str, str]] = set()
    per_source: dict[str, int] = {}

    def offer(entry: Symbol, source: str, rationale: str) -> None:
        if len(candidates) >= limit or per_source.get(source, 0) >= MAX_PER_SOURCE:
            return
        key = (entry.file, entry.line_start, entry.line_end)
        identity = (entry.file, entry.qualified_name)
        if key in seen or key in exclude or identity in offered:
            return
        if identity in exclude_symbols:
            return
        if key == (anchor.file, anchor.line_start, anchor.line_end):
            return          # the confused code itself is never its own foundation
        seen.add(key)
        # `@overload` stubs are separate ranges of the same name, and offering
        # the same symbol three times crowds out three real candidates.
        offered.add(identity)
        per_source[source] = per_source.get(source, 0) + 1
        candidates.append(PrereqCandidate(
            file=entry.file, symbol=entry.qualified_name,
            source=source, rationale=rationale,
        ))

    if target.kind == "class":
        from backend.repo.tools import _base_classes

        for base in _base_classes(skeleton, target):
            for resolved in skeleton.find_symbol(base):
                offer(resolved, "base_class",
                      f"{target.name} extends it, so its contract comes first")
        for method in skeleton.symbols_in(target.file):
            if method.parent == target.name:
                offer(method, "defines",
                      f"one behaviour of {target.name}, smaller than the whole class")
    elif target.parent:
        for owner in skeleton.find_symbol(target.parent, file=target.file):
            offer(owner, "enclosing_class",
                  f"the class {target.name} belongs to — its state and contract")

    for callee in _callees(skeleton, target):
        offer(callee, "calls",
              f"{target.qualified_name} uses this; it cannot be followed without it")

    if not candidates:
        for caller in _callers(skeleton, target):
            offer(caller, "used_by",
                  f"uses {target.qualified_name}, so it is a concrete example of it")

    for entry in skeleton.imports_in(target.file):
        resolved_file = skeleton.resolve_import(entry)
        if not resolved_file:
            continue
        for name in entry.names:
            for resolved in skeleton.find_symbol(name, file=resolved_file):
                offer(resolved, "module_dependency",
                      f"{target.file} imports it, so it is part of this code's vocabulary")

    return candidates[:limit]


# ── lesson context (Teaching's fallback when no dossier describes the node) ───

# Deliberately smaller than the candidate pool. This is surrounding context for
# one lesson, not a menu to choose from, and an unfocused list of neighbours
# would dilute a lesson rather than ground it.
MAX_CONTEXT_ENTRIES = 5

_CONTEXT_PHRASING = {
    "base_class": "extends",
    "enclosing_class": "is defined in",
    "defines": "defines",
    "calls": "uses",
    "used_by": "is used by",
    "module_dependency": "its module imports",
}


def neighbour_context(
    skeleton: Skeleton,
    file: str,
    symbol: str | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
    limit: int = MAX_CONTEXT_ENTRIES,
) -> str:
    """Surrounding system context for one lesson, from the structural index.

    Teaching's third rung: the Dossier is the preferred enrichment because it
    knows the user's goal; this knows only the repository, which is still far
    better than nothing and is grounded by construction. It is NOT a search —
    the same deterministic edges as the candidate derivation, phrased as context
    and capped hard.

    Returns "" when the structure says nothing useful, which is a legitimate
    state: the lesson then runs on its anchored source alone.
    """
    neighbours = neighbour_candidates(
        skeleton, file, symbol=symbol,
        line_start=line_start, line_end=line_end, limit=limit,
    )
    if not neighbours:
        return ""
    lines = [
        "System context for this piece of code, from the repository's structure "
        "(no goal-specific investigation was available for it):"
    ]
    for entry in neighbours:
        relation = _CONTEXT_PHRASING.get(entry.source, entry.source)
        lines.append(f"    this code {relation} {entry.symbol} ({entry.file})")
    return "\n".join(lines)
