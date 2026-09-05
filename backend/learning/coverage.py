# What the journey deliberately left out — computed, never generated.
#
# The contribution scope card claims "topics intentionally skipped", and that
# claim is only worth making if it is TRUE OF THIS PLAN. A model asked "what did
# you skip?" produces a plausible list; this produces the actual one, by
# subtracting what the curriculum anchored on from what the Layer-B survey said
# the repository contains.
#
# Two properties the product depends on, both of which come from being code:
#
#   EVIDENCE-BOUND   Only subsystems the SURVEY ITSELF named can appear. Nothing
#                    here invents a repository area to make the card look fuller,
#                    which is the failure mode a generated list has and this one
#                    structurally cannot.
#   HONEST WHEN BLIND  No survey means no list — the caller shows nothing rather
#                    than something. The survey is cached per (repo, commit) and
#                    can legitimately be missing, and "we skipped nothing" and
#                    "we cannot say what we skipped" are different claims.
#
# Pure: no IO, no model calls, no mutation. Same contract as `progress.py` and
# `scope.py`, and for the same reason — the whole thing is testable without an
# API key.

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle
    from backend.learning.graph import LearningGraph


# How many to show. A long list of things you did not learn reads as padding,
# and stops being the point it was making after about three.
MAX_SKIPPED = 3


def _normalize(path: str) -> str:
    """Comparable form of a repository-relative path."""
    return str(path or "").replace("\\", "/").strip().lstrip("./").lower()


def curriculum_files(graph: "LearningGraph") -> set[str]:
    """Every file the curriculum anchored on, in comparable form.

    Reads `lesson_brief["anchors"]` — the semantic truth about where a unit lives
    — and falls back to the node's display anchor for graphs written before that
    key existed. Both, not either: a multi-anchor unit's second and third files
    are just as much "covered" as its first, and counting only the display anchor
    would report a flow's later files as skipped.
    """
    files: set[str] = set()
    for node in graph.nodes.values():
        for anchor in (node.lesson_brief or {}).get("anchors") or []:
            if isinstance(anchor, dict) and anchor.get("file"):
                files.add(_normalize(str(anchor["file"])))
        if node.code_anchor and node.code_anchor.file:
            files.add(_normalize(node.code_anchor.file))
    return {f for f in files if f}


def _subsystem_files(entry: dict) -> list[str]:
    """The files a survey subsystem claims, across the shapes surveys use.

    `key_file` — SINGULAR — is what the survey actually writes, and omitting it
    was the bug that made this whole list silently empty on a real survey: every
    subsystem looked file-less, so none of them could be reported as untouched
    and the card had nothing to show. The plural forms are kept because nothing
    guarantees one survey's shape is every survey's.
    """
    out: list[str] = []
    for key in ("key_files", "files", "paths"):
        value = entry.get(key)
        if isinstance(value, list):
            out.extend(_normalize(str(v)) for v in value if v)
    for key in ("key_file", "file", "path"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            out.append(_normalize(value))
    return [f for f in out if f]


def _central_files(survey: dict) -> set[str]:
    """The files the SURVEY ITSELF treats as central to this repository.

    Used only for ORDER, never for inclusion — so this cannot add a subsystem to
    the list or remove one from it, only decide which three of seventeen are
    worth the space.

    Both signals come from the survey's own document rather than from any
    judgement of ours: a file carrying a `core_abstraction`, and a subsystem the
    survey bothered to give a `key_symbol`. Without this the list is emitted in
    survey order, which on `psf/requests` means the learner is told they skipped
    `setup.py` and `compat.py` while `models.py` and `sessions.py` — the parts
    they would actually wonder about — go unmentioned.
    """
    central = {
        _normalize(str(entry.get("file")))
        for entry in survey.get("core_abstractions") or []
        if isinstance(entry, dict) and entry.get("file")
    }
    for entry in survey.get("subsystems") or []:
        if isinstance(entry, dict) and str(entry.get("key_symbol") or "").strip():
            central.update(_subsystem_files(entry))
    return {f for f in central if f}


def _touches(subsystem_files: list[str], covered: set[str]) -> bool:
    """Does the curriculum reach any of this subsystem's files?

    Prefix matching in BOTH directions, because a survey may name a directory
    (`src/requests/adapters`) where the curriculum anchors a file
    (`src/requests/adapters.py`), or name a file where the survey listed its
    package. Exact-match-only reported directory-shaped subsystems as skipped
    while the learner was being taught out of them.
    """
    for covered_file in covered:
        for claimed in subsystem_files:
            if covered_file == claimed:
                return True
            if covered_file.startswith(claimed.rstrip("/") + "/"):
                return True
            if claimed.startswith(covered_file.rsplit(".", 1)[0] + "/"):
                return True
            # `src/requests/adapters` (survey) vs `src/requests/adapters.py`.
            if covered_file.rsplit(".", 1)[0] == claimed.rstrip("/"):
                return True
    return False


def skipped_areas(
    survey: dict | None, graph: "LearningGraph", limit: int = MAX_SKIPPED
) -> list[dict]:
    """Survey subsystems this curriculum does not touch, with the survey's own words.

    Returns `[{"name", "reason"}]`, in the survey's order, capped at `limit`.
    Empty whenever there is no survey, no subsystem list, or no subsystem whose
    files the curriculum leaves alone — and the caller renders nothing at all in
    that case rather than an empty heading.

    A subsystem the survey named WITHOUT any files is skipped over rather than
    reported: with nothing to compare, "the curriculum does not touch it" is not
    a fact we have.
    """
    if not isinstance(survey, dict):
        return []
    subsystems = survey.get("subsystems")
    if not isinstance(subsystems, list):
        return []

    covered = curriculum_files(graph)
    central = _central_files(survey)
    candidates: list[tuple[int, int, dict]] = []
    for position, entry in enumerate(subsystems):
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        files = _subsystem_files(entry)
        if not files or _touches(files, covered):
            continue
        rank = 0 if any(f in central for f in files) else 1
        candidates.append((rank, position, {
            "name": name,
            # The survey's own responsibility line, not a new sentence about it.
            # This list is a claim about coverage; inventing prose here would
            # make it a claim about the subsystem as well.
            "reason": str(entry.get("responsibility") or "").strip(),
        }))

    # Central first, then the survey's own order. `sorted` is stable, so equal
    # ranks keep the order the survey wrote them in.
    candidates.sort(key=lambda c: (c[0], c[1]))
    return [entry for _, _, entry in candidates[:limit]]
