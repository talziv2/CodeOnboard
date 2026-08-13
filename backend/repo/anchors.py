# Anchor resolution — the single grounding oracle for every agent.
#
# Replaces three near-identical implementations that each validated against a
# *retrieval result*:
#   backend/agents/mentor/agent.py     _ground_anchors
#   backend/agents/reviewer/agent.py   _drop_ungrounded_anchors
#   backend/agents/mentor/mutator.py   _ground_node
#
# The oracle is now the repository (via the Skeleton), not the chunk slice. That
# separates two questions the old code conflated:
#
#   resolve(...)          Does this file / symbol / range REALLY EXIST?
#   within_evidence(...)  Was this code actually SHOWN to the agent?
#
# Stage 0 improves the first and leaves the second exactly as strict as it was.
# See docs/planning/phases/repo-understanding.md §12 Stage 0.

from __future__ import annotations

from dataclasses import dataclass

from backend.repo.skeleton import Skeleton, normalize_path


# A teachable unit, per the grounding strategy (repo-understanding.md §9 G3).
# Wired as an OPT-IN parameter, not a default: switching it on at Stage 0 would
# reject oversized anchors that pass today, which is a behaviour change beyond
# "verify anchors are real". Stage 3 turns it on with the granularity rules.
MAX_ANCHOR_LINES = 400


@dataclass(frozen=True)
class ResolvedAnchor:
    file: str                 # canonical, repo-relative, forward slashes
    line_start: int
    line_end: int
    symbol: str | None        # qualified name when the range maps to one symbol
    kind: str                 # "symbol" | "range"

    def as_tuple(self) -> tuple[str, int, int]:
        return (self.file, self.line_start, self.line_end)


@dataclass(frozen=True)
class Resolution:
    anchor: ResolvedAnchor | None
    reason: str | None = None   # rejection code, None on success

    @property
    def ok(self) -> bool:
        return self.anchor is not None


# Rejection codes. Strings rather than an enum — they end up in state.errors and
# in test assertions, where readability matters more than type safety.
UNKNOWN_FILE = "unknown_file"
UNKNOWN_SYMBOL = "unknown_symbol"
AMBIGUOUS_SYMBOL = "ambiguous_symbol"
MISSING_RANGE = "missing_range"
INVALID_RANGE = "invalid_range"
RANGE_OUT_OF_BOUNDS = "range_out_of_bounds"
EMPTY_RANGE = "empty_range"
RANGE_TOO_LARGE = "range_too_large"
# Stage-0 only — the anchor is real but was not shown to the agent. See below.
OUT_OF_EVIDENCE = "out_of_evidence"


def resolve(
    skeleton: Skeleton,
    file: str,
    symbol: str | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
    max_lines: int | None = None,
) -> Resolution:
    """Verify an anchor against the repository and return its canonical form.

    Two modes:

      symbol given  — the symbol IS the identity. Its indexed range is returned,
                      overriding any line numbers supplied alongside it. This is
                      the mode that makes hallucinated line numbers impossible,
                      because the caller never has to produce one.

      range only    — verified by structure and, when a real checkout is
                      available, by reading it. Any symbol the range lands on is
                      recorded as provenance.

    ``max_lines`` is opt-in; see MAX_ANCHOR_LINES.
    """
    path = skeleton.canonical_file(file)
    if path is None:
        return Resolution(None, UNKNOWN_FILE)

    if symbol:
        matches = skeleton.find_symbol(symbol, file=path)
        if not matches:
            return Resolution(None, UNKNOWN_SYMBOL)
        if len(matches) > 1:
            return Resolution(None, AMBIGUOUS_SYMBOL)
        found = matches[0]
        return Resolution(
            ResolvedAnchor(
                file=found.file,
                line_start=found.line_start,
                line_end=found.line_end,
                symbol=found.qualified_name,
                kind="symbol",
            )
        )

    if line_start is None or line_end is None:
        return Resolution(None, MISSING_RANGE)

    start, end = int(line_start), int(line_end)
    if start < 1 or end < start:
        return Resolution(None, INVALID_RANGE)

    bound = skeleton.file_line_count(path)
    if bound and end > bound:
        return Resolution(None, RANGE_OUT_OF_BOUNDS)

    if max_lines is not None and (end - start + 1) > max_lines:
        return Resolution(None, RANGE_TOO_LARGE)

    # Content check only when a real checkout backs the skeleton.
    source = skeleton.read_lines(path, start, end)
    if source is not None and not source.strip():
        return Resolution(None, EMPTY_RANGE)

    matched = skeleton.exact_symbol(path, start, end)
    enclosing = matched or skeleton.enclosing_symbol(path, start, end)
    return Resolution(
        ResolvedAnchor(
            file=path,
            line_start=start,
            line_end=end,
            symbol=enclosing.qualified_name if enclosing else None,
            kind="symbol" if matched else "range",
        )
    )


# ── Stage-0 migration boundary ────────────────────────────────────────────────
#
# REMOVED AT STAGE 3, when the evidence provider itself changes.
#
# Resolution proves an anchor is real. It does NOT prove the agent was shown the
# code. While the evidence set is still a retrieval slice, an agent must not cite
# something it never received — it would have no content to reason from, and the
# lesson would be confident and ungrounded. Keeping this check separate is what
# lets Stage 0 improve validation without expanding curriculum scope.


def within_evidence(anchor: ResolvedAnchor, chunks: list[dict]) -> bool:
    """True when the resolved anchor lies inside code the agent actually received.

    Containment, not equality: a chunk shown in full covers any sub-range of
    itself, so narrowing an anchor within a chunk introduces no new content.
    """
    for chunk in chunks:
        if normalize_path(chunk["file"]) != anchor.file:
            continue
        if (
            int(chunk["start_line"]) <= anchor.line_start
            and anchor.line_end <= int(chunk["end_line"])
        ):
            return True
    return False


def resolve_within_evidence(
    skeleton: Skeleton,
    chunks: list[dict],
    file: str,
    symbol: str | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
) -> Resolution:
    """resolve(), then the Stage-0 evidence-scope gate.

    The shared path for Mentor / Reviewer / Mutator, so all three enforce the
    boundary identically and all three stop enforcing it in one edit at Stage 3.
    """
    resolution = resolve(
        skeleton, file, symbol=symbol, line_start=line_start, line_end=line_end
    )
    if not resolution.ok:
        return resolution
    if not within_evidence(resolution.anchor, chunks):
        return Resolution(None, OUT_OF_EVIDENCE)
    return resolution
