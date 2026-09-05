"""The grounded contribution handoff — what leaves CodeOnboard for a coding agent.

CodeOnboard owns the repository investigation, the required knowledge, the
teaching, the grading and the readiness gate. It does not own editing, executing
or opening a pull request: `data/repos/<owner>/<name>` is ONE shared, pinned
checkout that the grounding oracle reads (`repo/anchors.py`), so a writable
per-learner working tree is a thing this system must not have where it keeps the
repository. Everything downstream of "write the change" therefore happens
somewhere else, and this module is what that somewhere else is told.

## Two namespaces, never mixed

`change_boundary` / `contracts` are facts about the CODE. `learner` is a fact
about the PERSON. They are separate objects in the payload because a consumer
that reads "demonstrated 11 concepts" as "the code does 11 things" — or the
reverse — would be making exactly the claim D8 exists to prevent. The `means`
sentence is part of the contract, not decoration: without it, `demonstrated: 11`
reads as a certification, and it is a record of eleven exchanges.

## File and symbol; never a line number

Every anchor here is `file` + `symbol`. `anchors.resolve` is the oracle
precisely because a model never names a range (D2), and a line range is the
fastest thing in this system to go stale — the handoff is read against a working
tree we cannot see. A symbol survives an edit above it; a range does not.

## The revision is load-bearing

Every `file:symbol` below is true at ONE commit. Handed to an agent standing on a
different checkout, the whole payload is confidently wrong, which is worse than
empty — so `repository.commit` is mandatory and `repository.verify` tells the
reader to check it before trusting anything else.

Pure: no IO, no model calls, no database. The caller loads the dossier, the
survey and the commit and passes them in, which is what makes this testable
without a repository on disk.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from backend.learning import contribution as contribution_model
from backend.learning import coverage, progress
from backend.repo import investigation as investigation_module

if TYPE_CHECKING:  # pragma: no cover
    from backend.learning.graph import LearningGraph

# Caps. The handoff is context for one change, not an export of the session —
# a payload that has to be summarised before use is not a handoff.
MAX_CONTRACTS = 8
MAX_CONCEPTS = 40

#: What `demonstrated` does and does not assert. Travels WITH the number,
#: because the number is meaningless and dangerous on its own.
MEANS = (
    "Demonstrated means the learner answered a question against this objective "
    "and the Grader classified it `strength` or `recovered`. It is a record of "
    "one exchange, not a certification, and it says nothing about their ability "
    "to write this code."
)

VERIFY = "Run `git rev-parse HEAD`; it must equal `commit` or nothing below is reliable."


def unusable_reason(graph: "LearningGraph", dossier: dict | None) -> str | None:
    """Why this session cannot produce a handoff, or `None` if it can.

    DI-8: refuse rather than fabricate. A payload with a confident schema and an
    empty boundary is worse than an error, because the schema is what makes a
    reader trust it. Every caller checks this before building.
    """
    if not _task(graph):
        return "not_a_contribution_session"
    if not progress.ready_to_implement(graph)["ready"] and not _proceeded(graph):
        return "not_ready_to_implement"
    if not investigation_module.boundary(dossier or {}):
        return "no_change_boundary"
    return None


def build_context(
    graph: "LearningGraph",
    dossier: dict | None,
    survey: dict | None,
    commit: str,
) -> dict:
    """The whole handoff, compact and structured.

    Callers: `GET /session/{id}/contribution/handoff` and the MCP server's
    `get_contribution_context`. ONE function so the screen the learner reads and
    the payload the agent receives cannot disagree (DI-1).
    """
    boundary = investigation_module.boundary(dossier or {})
    ready = progress.ready_to_implement(graph)

    return {
        # Not a courtesy field. See the module header.
        "repository": {
            "url": graph.repo_url,
            "commit": commit,
            "verify": VERIFY,
        },
        "task": _task(graph),

        # ── facts about the code ──────────────────────────────────────────────
        # `_entries` reads the DOSSIER, not the extracted boundary:
        # `investigation.boundary_entries` does its own extraction, and one
        # authority for "where is the boundary" is the point.
        "change_boundary": {
            "target": _entries(dossier, "target", ("file", "symbol", "why_here")),
            "must_not_change": _entries(
                dossier, "must_not_change", ("file", "symbol", "why_not"),
            ),
            "existing_tests": _entries(
                dossier, "existing_tests", ("file", "symbol", "what_it_guards"),
            ),
            "edge_cases": _entries(
                dossier, "edge_cases", ("case", "why_it_bites", "file", "symbol"),
            ),
            "conventions": _entries(
                dossier, "conventions", ("convention", "evidence_file"),
            ),
        },
        "contracts": _contracts(dossier or {}),
        # RECOMMENDED, never executed here. Empty when the investigation named no
        # tests, in which case the reader is told nothing rather than a guess.
        "recommended_validation": contribution_model.validation_command(boundary),

        # ── facts about the person ────────────────────────────────────────────
        "learner": {
            "ready": ready["ready"],
            "required": ready["required"],
            "demonstrated": ready["demonstrated"],
            "demonstrated_concepts": _concepts(graph),
            # What the journey deliberately did NOT cover. As much a part of the
            # trust map as what it did: it says where this learner has no
            # grounding at all.
            "not_taught": coverage.skipped_areas(survey, graph),
            "started_unready": _proceeded(graph),
            "means": MEANS,
        },
    }


# ── helpers ───────────────────────────────────────────────────────────────────


def _task(graph: "LearningGraph") -> str:
    """ONE authority: the goal. Same source the contribution surfaces read."""
    return str((graph.goal or {}).get("contribution_context") or "").strip()


def _proceeded(graph: "LearningGraph") -> bool:
    state = getattr(graph, "contribution", None)
    return bool(state and state.proceeded_unready)


def _entries(payload: dict | None, key: str, fields: tuple[str, ...]) -> list[dict]:
    """One boundary section, reduced to the fields the schema declares.

    Whitelisted rather than copied: the dossier is model-authored, and a section
    that grew a field would otherwise export it unreviewed. Blank values are
    dropped so an optional anchor is absent rather than empty — `edge_cases` may
    legitimately carry no `file`/`symbol`.
    """
    out = []
    for entry in investigation_module.boundary_entries(payload or {}, key):
        row = {f: str(entry.get(f) or "").strip() for f in fields}
        row = {k: v for k, v in row.items() if v}
        if row:
            out.append(row)
    return out


def _contracts(dossier: dict) -> list[dict]:
    """Invariants the investigation recorded — what the change must not break.

    From the dossier's own `contracts`, not from the boundary: `must_not_change`
    says *where* not to go, a contract says *what stays true*. Both are useful to
    someone editing, and they are different claims.
    """
    raw = dossier.get("contracts")
    if not isinstance(raw, list):
        return []
    out = []
    for entry in raw[:MAX_CONTRACTS]:
        if not isinstance(entry, dict):
            continue
        row = {
            f: str(entry.get(f) or "").strip()
            for f in ("file", "symbol", "contract")
        }
        if row["contract"]:
            out.append({k: v for k, v in row.items() if v})
    return out


def _concepts(graph: "LearningGraph") -> list[str]:
    """The objectives this learner has SHOWN they can make — not the curriculum.

    `core_nodes` + `is_demonstrated` are the same predicates `ready_to_implement`
    counts with, so the list and the number can never tell different stories.
    """
    return [
        n.objective()
        for n in progress.core_nodes(graph)
        if progress.is_demonstrated(n) and n.objective()
    ][:MAX_CONCEPTS]
