# Repository exploration tools (Stage 1).
#
# The deterministic surface Claude will eventually explore through. Six
# primitives, chosen so that a realistic investigation is *composable* rather
# than served by a bespoke tool per question:
#
#   list_files      what is here
#   read_file       show me this, bounded
#   search_code     where does this text appear
#   symbols         what is defined, and exactly where
#   neighbors       what is this connected to
#   propose_anchor  is this citation real          (delegates to Stage 0)
#
# Three rules this module holds itself to:
#
#   1. FACTS, NOT JUDGEMENT. Every result is derivable from the checkout and the
#      Skeleton. No tool asks a model anything, ranks by "importance", or
#      summarises. Layer A stays model-free.
#   2. BOUNDED OUTPUT. Every tool caps its result and reports `truncated`.
#      Replacing vector-retrieval context flooding with tool-output context
#      flooding would not be a migration.
#   3. ONE BOUNDARY CHECK. All filesystem access goes through
#      skeleton.safe_repo_path(); no tool reimplements path validation.
#
# Result shape is uniform so a caller can branch without per-tool knowledge:
#   success -> {"ok": True,  ...payload...}
#   failure -> {"ok": False, "error": "<code>", "detail": "<human readable>"}
#
# Stage 1 wires nothing into the pipeline. See
# docs/planning/phases/repo-understanding.md §12.

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from backend.repo.parser import classify_role
from backend.repo import anchors
from backend.repo.skeleton import (
    Skeleton,
    build_skeleton,
    normalize_path,
    safe_repo_path,
)


# ── Output budgets ────────────────────────────────────────────────────────────
#
# Deliberately small. An explorer that needs more can ask again with a narrower
# question, which is cheaper than one prompt carrying everything.

MAX_READ_LINES = 400        # hard cap on a single read
OUTLINE_THRESHOLD = 400     # bigger files return an outline unless a range is given
MAX_FILE_RESULTS = 200
MAX_SEARCH_RESULTS = 50
MAX_MATCH_CHARS = 200       # per matched line
MAX_SYMBOL_RESULTS = 200
MAX_NEIGHBOR_RESULTS = 50
MAX_SEARCH_FILE_BYTES = 2_000_000   # skip pathological files during search

SKIP_DIRS = {".git", "__pycache__", ".mypy_cache", ".pytest_cache", ".venv", "node_modules"}


def _err(code: str, detail: str) -> dict:
    return {"ok": False, "error": code, "detail": detail}


def _skeleton(repo_path: str, skeleton: Skeleton | None) -> Skeleton:
    return skeleton if skeleton is not None else build_skeleton(repo_path)


def _walk(repo_path: str):
    """Every file in the checkout, repo-relative, minus noise directories.

    The Skeleton only indexes Python, but exploration needs to see that a
    README, a pyproject, or an .rst doc exists.
    """
    root = Path(repo_path)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = normalize_path(str(path.relative_to(root)))
        if any(part in SKIP_DIRS for part in relative.split("/")):
            continue
        yield relative


# ── list_files ────────────────────────────────────────────────────────────────


def list_files(
    repo_path: str,
    glob: str = "**/*.py",
    role: str | None = None,
    limit: int = MAX_FILE_RESULTS,
    skeleton: Skeleton | None = None,
) -> dict:
    """Files matching a glob, with Layer-A metadata attached where indexed.

    GUARANTEES: every path returned exists in the checkout; `role` is the
    deterministic path-based classification; `loc` and `symbol_count` are exact
    for indexed (Python) files.

    DOES NOT: rank, judge relevance, or recurse into skipped directories.
    `loc`/`symbol_count` are None for files the Skeleton does not index.
    """
    sk = _skeleton(repo_path, skeleton)
    limit = max(1, min(int(limit), MAX_FILE_RESULTS))

    matches: list[str] = []
    for relative in _walk(repo_path):
        if not (fnmatch.fnmatch(relative, glob) or fnmatch.fnmatch(relative, f"**/{glob}")):
            continue
        entry_role = (
            sk.files[relative].role if relative in sk.files
            else classify_role(Path(relative))
        )
        if role and entry_role != role:
            continue
        matches.append(relative)

    matches.sort()
    total = len(matches)
    files = []
    for relative in matches[:limit]:
        entry = sk.files.get(relative)
        files.append({
            "path": relative,
            "role": entry.role if entry else classify_role(Path(relative)),
            "loc": entry.line_count if entry else None,
            "symbol_count": entry.symbol_count if entry else None,
        })
    return {"ok": True, "files": files, "total": total, "truncated": total > limit}


# ── read_file ─────────────────────────────────────────────────────────────────


def read_file(
    repo_path: str,
    path: str,
    start: int | None = None,
    end: int | None = None,
    skeleton: Skeleton | None = None,
) -> dict:
    """Line-numbered source for a bounded range.

    Line numbers are part of the contract, not decoration: they are how a caller
    reasons about an anchor without ever having to invent one.

    GUARANTEES: content is the real file; `start`/`end` are 1-indexed inclusive;
    at most MAX_READ_LINES lines are ever returned.

    DOES NOT: dump a large file. Without a range, a file longer than
    OUTLINE_THRESHOLD returns its symbol outline plus a hint instead of content,
    so the caller narrows the question rather than flooding its own context.
    """
    target = safe_repo_path(repo_path, path)
    if target is None:
        return _err("invalid_path", f"{path!r} is outside the repository")
    if not target.is_file():
        # Recover a stripped package prefix ("sessions.py" for
        # "src/requests/sessions.py") the same way the anchor resolver does.
        # `symbols` and `propose_anchor` already accept an abbreviated path, so
        # rejecting it here would make the tool layer inconsistent about the
        # same input — and reintroduce exactly the false rejection Stage 0
        # removed. Ambiguity still declines to guess.
        canonical = _skeleton(repo_path, skeleton).canonical_file(path)
        target = safe_repo_path(repo_path, canonical) if canonical else None
        if target is None or not target.is_file():
            return _err("not_found", f"{path!r} does not exist in the repository")

    try:
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return _err("unreadable", str(exc))

    total = len(lines)
    relative = normalize_path(str(target.relative_to(Path(repo_path).resolve())))

    if start is None and end is None:
        if total > OUTLINE_THRESHOLD:
            sk = _skeleton(repo_path, skeleton)
            outline = [
                {"name": s.qualified_name, "kind": s.kind,
                 "line_start": s.line_start, "line_end": s.line_end}
                for s in sorted(sk.symbols_in(relative), key=lambda s: s.line_start)
            ]
            return {
                "ok": True, "path": relative, "total_lines": total,
                "outline": outline, "content": None, "truncated": True,
                "hint": (
                    f"{relative} has {total} lines — too long to return whole. "
                    f"Re-read with start/end (max {MAX_READ_LINES} lines), "
                    f"using the outline above to pick a range."
                ),
            }
        start, end = 1, total

    start = 1 if start is None else max(1, int(start))
    end = total if end is None else int(end)
    if end < start:
        return _err("invalid_range", f"end ({end}) precedes start ({start})")
    if start > total:
        return _err("invalid_range", f"start ({start}) is past end of file ({total} lines)")
    end = min(end, total)
    if end - start + 1 > MAX_READ_LINES:
        return _err(
            "range_too_large",
            f"requested {end - start + 1} lines; the cap is {MAX_READ_LINES}. "
            f"Narrow the range or read in successive slices.",
        )

    width = len(str(end))
    body = "\n".join(
        f"{n:>{width}}| {lines[n - 1]}" for n in range(start, end + 1)
    )
    return {
        "ok": True, "path": relative, "start": start, "end": end,
        "total_lines": total, "content": body,
        "truncated": (start > 1 or end < total),
    }


# ── search_code ───────────────────────────────────────────────────────────────


def search_code(
    repo_path: str,
    pattern: str,
    glob: str | None = None,
    max_results: int = MAX_SEARCH_RESULTS,
    ignore_case: bool = False,
) -> dict:
    """Deterministic regex search over the checkout.

    GUARANTEES: pure text matching, same input same output; every hit carries a
    real path and 1-indexed line number; each matched line is truncated to
    MAX_MATCH_CHARS.

    DOES NOT: understand scope, resolve names, or rank by relevance. A match is
    a textual fact, not evidence that the symbol is the one you meant.
    """
    if not pattern:
        return _err("invalid_pattern", "pattern is empty")
    try:
        compiled = re.compile(pattern, re.IGNORECASE if ignore_case else 0)
    except re.error as exc:
        return _err("invalid_pattern", f"{pattern!r} is not a valid regex: {exc}")

    max_results = max(1, min(int(max_results), MAX_SEARCH_RESULTS))
    root = Path(repo_path)
    matches: list[dict] = []
    total = 0
    files_with_matches: set[str] = set()

    for relative in _walk(repo_path):
        if glob and not (
            fnmatch.fnmatch(relative, glob) or fnmatch.fnmatch(relative, f"**/{glob}")
        ):
            continue
        file_path = root / relative
        try:
            if file_path.stat().st_size > MAX_SEARCH_FILE_BYTES:
                continue
            text = file_path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError):
            continue  # binary or unreadable — not a search target
        if "\x00" in text:
            # A NUL byte decodes as valid UTF-8, so the decode above does not
            # catch every binary file. Matching inside one yields a "hit" whose
            # text is garbage — noise the explorer pays tokens for.
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if not compiled.search(line):
                continue
            total += 1
            files_with_matches.add(relative)
            if len(matches) < max_results:
                stripped = line.strip()
                matches.append({
                    "path": relative,
                    "line": number,
                    "text": stripped[:MAX_MATCH_CHARS],
                })

    return {
        "ok": True, "matches": matches, "total": total,
        "files_with_matches": len(files_with_matches),
        "truncated": total > len(matches),
    }


# ── symbols ───────────────────────────────────────────────────────────────────


def symbols(
    repo_path: str,
    path: str | None = None,
    name: str | None = None,
    kind: str | None = None,
    limit: int = MAX_SYMBOL_RESULTS,
    skeleton: Skeleton | None = None,
) -> dict:
    """Definitions from the deterministic Skeleton, with exact line ranges.

    The cheap way to see what a file contains without reading it, and the exact
    way to locate a definition.

    GUARANTEES: every range comes from the tree-sitter parse; `qualified_name`
    disambiguates methods ("Session.send"); results are Python-only, because
    that is what Layer A indexes today.

    DOES NOT: rank by importance, resolve which same-named symbol you meant
    (all matches are returned), or find dynamic/generated definitions.
    """
    sk = _skeleton(repo_path, skeleton)
    limit = max(1, min(int(limit), MAX_SYMBOL_RESULTS))

    if path is not None:
        canonical = sk.canonical_file(path)
        if canonical is None:
            return _err("not_found", f"{path!r} is not an indexed file")
        found = sk.symbols_in(canonical)
        if name:
            found = [s for s in found if name in (s.name, s.qualified_name)]
    elif name is not None:
        found = sk.find_symbol(name)
    else:
        found = list(sk.symbols)

    if kind:
        found = [s for s in found if s.kind == kind]

    found.sort(key=lambda s: (s.file, s.line_start))
    total = len(found)
    return {
        "ok": True,
        "symbols": [
            {
                "name": s.name, "qualified_name": s.qualified_name, "kind": s.kind,
                "file": s.file, "line_start": s.line_start, "line_end": s.line_end,
                "parent": s.parent, "role": s.role,
            }
            for s in found[:limit]
        ],
        "total": total,
        "truncated": total > limit,
    }


# ── neighbors ─────────────────────────────────────────────────────────────────

RELATIONS = ("defines", "defined_in", "extends", "imports", "imported_by",
             "exported_by", "references")


def neighbors(
    repo_path: str,
    symbol: str,
    file: str | None = None,
    relations: list[str] | None = None,
    limit: int = MAX_NEIGHBOR_RESULTS,
    skeleton: Skeleton | None = None,
) -> dict:
    """Deterministic relationships around a symbol and its defining file.

    Relations, and exactly how far each is trusted:

      defines      class -> its methods                     EXACT (parse tree)
      defined_in   method -> its class                      EXACT
      extends      class -> its base classes                EXACT for the normal
                                                            `class X(A, B):` form
      imports      defining file -> modules it imports      EXACT statements;
                                                            in-repo targets resolved,
                                                            external ones reported unresolved
      imported_by  files importing the defining file        EXACT
      exported_by  package __init__ files re-exporting it,  EXACT
                   with the dotted path a user would type
      references   files mentioning the symbol's NAME       NAME-BASED, approximate

    `references` is the one approximation, and it is called out on every result
    via `"exact": false`. It is a word-boundary text scan, so a same-named
    symbol from an unrelated module will appear. It approximates callers well
    enough to follow a flow; it is not a call graph, and Python cannot give one
    without type inference. Verify a reference by reading it.

    DOES NOT: decide which relationships matter. That judgement belongs to the
    explorer, not to Layer A.
    """
    sk = _skeleton(repo_path, skeleton)
    limit = max(1, min(int(limit), MAX_NEIGHBOR_RESULTS))
    wanted = tuple(relations) if relations else RELATIONS
    unknown = [r for r in wanted if r not in RELATIONS]
    if unknown:
        return _err("unknown_relation", f"{unknown} not in {list(RELATIONS)}")

    candidates = sk.find_symbol(symbol, file=file) if file else sk.find_symbol(symbol)
    if not candidates:
        return _err("unknown_symbol", f"{symbol!r} is not an indexed symbol")
    if len(candidates) > 1 and file is None:
        # A repeated name is a FACT ABOUT THE CODE, not a caller mistake, and it
        # is often the most interesting fact available: the public factory and
        # the class it constructs share a name (`field`/`Field`, a re-exported
        # `X` beside the `X` it wraps), so the two definitions are precisely the
        # indirection someone learning the code needs to see. Returning an error
        # answered nothing and pushed the caller to pick one blind — measured on
        # a real investigation, it picked the implementation and never learned
        # that the name users actually import is the other one. So: hand back
        # both definitions and let the caller choose which to follow.
        return {
            "ok": True,
            "symbol": symbol,
            "ambiguous": True,
            "candidates": [
                {
                    "qualified_name": c.qualified_name, "kind": c.kind,
                    "file": c.file, "line_start": c.line_start,
                    "line_end": c.line_end, "parent": c.parent,
                }
                for c in sorted(candidates, key=lambda c: (c.file, c.line_start))
                [:MAX_NEIGHBOR_RESULTS]
            ],
            "neighbors": [],
            "total": 0,
            "truncated": len(candidates) > MAX_NEIGHBOR_RESULTS,
        }
    target = candidates[0]

    out: list[dict] = []

    def _add(relation: str, **payload) -> None:
        out.append({"relation": relation, "exact": relation != "references", **payload})

    if "defines" in wanted and target.kind == "class":
        for s in sk.symbols_in(target.file):
            if s.parent == target.name:
                _add("defines", symbol=s.qualified_name, file=s.file,
                     line_start=s.line_start, line_end=s.line_end)

    if "defined_in" in wanted and target.parent:
        for s in sk.find_symbol(target.parent, file=target.file):
            _add("defined_in", symbol=s.qualified_name, file=s.file,
                 line_start=s.line_start, line_end=s.line_end)

    if "extends" in wanted and target.kind == "class":
        for base in _base_classes(sk, target):
            resolved = sk.find_symbol(base)
            if len(resolved) == 1:
                b = resolved[0]
                _add("extends", symbol=b.qualified_name, file=b.file,
                     line_start=b.line_start, line_end=b.line_end)
            else:
                _add("extends", symbol=base, file=None,
                     line_start=None, line_end=None)

    if "imports" in wanted:
        # One dependency edge per module, not one per import statement.
        # `from x import a` and `from x import b` are two statements and the same
        # edge; a file importing five names from urllib3.exceptions would
        # otherwise spend five result slots saying so.
        seen_modules: set[str | None] = set()
        for entry in sk.imports_in(target.file):
            resolved = sk.resolve_import(entry)
            if entry.module in seen_modules:
                continue
            seen_modules.add(entry.module)
            _add("imports", symbol=None, module=entry.module, file=resolved,
                 line_start=entry.line_start, line_end=entry.line_end,
                 in_repo=resolved is not None)

    if "imported_by" in wanted:
        for entry in sk.imports:
            if entry.file == target.file:
                continue
            if sk.resolve_import(entry) == target.file:
                _add("imported_by", symbol=None, file=entry.file,
                     line_start=entry.line_start, line_end=entry.line_end)

    if "exported_by" in wanted:
        # The one structurally-stated form of "public API" in Python: a package
        # __init__ re-exporting the name. This is how a caller reaches the symbol,
        # which is a different question from which file defines it — and the two
        # answers differ exactly where a public factory sits beside the internal
        # type it builds.
        for export in sk.exports_of(target.name, file=target.file):
            _add("exported_by", symbol=export.symbol, file=export.exported_from,
                 line_start=export.line, line_end=export.line,
                 import_path=export.import_path)

    if "references" in wanted:
        hits = search_code(
            repo_path, rf"\b{re.escape(target.name)}\b", glob="*.py",
            max_results=MAX_SEARCH_RESULTS,
        )
        for match in hits.get("matches", []):
            inside_definition = (
                match["path"] == target.file
                and target.line_start <= match["line"] <= target.line_end
            )
            if inside_definition:
                continue
            _add("references", symbol=None, file=match["path"],
                 line_start=match["line"], line_end=match["line"],
                 text=match["text"])

    total = len(out)
    return {
        "ok": True,
        "symbol": target.qualified_name,
        "file": target.file,
        "anchor": {
            "file": target.file,
            "line_start": target.line_start,
            "line_end": target.line_end,
        },
        "neighbors": _fair_share(out, limit),
        "total": total,
        "truncated": total > limit,
    }


def _fair_share(neighbors: list[dict], limit: int) -> list[dict]:
    """Trim to ``limit`` without letting one relation starve the others.

    A plain prefix cut is the wrong shape here: a file with 60 imports and 3
    references would return 60 imports and no references, and the caller tracing
    a flow — the reason `neighbors` exists — gets nothing it asked for. Taking a
    round from each relation in turn keeps every requested relation visible, and
    `truncated` still says the list is partial.
    """
    if len(neighbors) <= limit:
        return neighbors
    groups: dict[str, list[dict]] = {}
    for entry in neighbors:
        groups.setdefault(entry["relation"], []).append(entry)

    kept: list[dict] = []
    while len(kept) < limit:
        progressed = False
        for relation in RELATIONS:
            bucket = groups.get(relation)
            if not bucket:
                continue
            kept.append(bucket.pop(0))
            progressed = True
            if len(kept) >= limit:
                break
        if not progressed:
            break
    # Restore relation grouping so the rendered output reads coherently.
    order = {relation: i for i, relation in enumerate(RELATIONS)}
    kept.sort(key=lambda entry: order.get(entry["relation"], len(RELATIONS)))
    return kept


_CLASS_BASES = re.compile(r"class\s+\w+\s*\(([^)]*)\)")


def _base_classes(skeleton: Skeleton, symbol) -> list[str]:
    """Base-class names from the class header, read from the real file."""
    header = skeleton.read_lines(
        symbol.file, symbol.line_start, min(symbol.line_start + 2, symbol.line_end)
    )
    if not header:
        return []
    match = _CLASS_BASES.search(header.replace("\n", " "))
    if not match:
        return []
    bases = []
    for raw in match.group(1).split(","):
        base = raw.strip().split("=")[0].strip()   # drop metaclass= kwargs
        if base and base.isidentifier():
            bases.append(base)
        elif "." in base:                          # module.Qualified -> last part
            tail = base.rsplit(".", 1)[-1]
            if tail.isidentifier():
                bases.append(tail)
    return bases


# ── propose_anchor ────────────────────────────────────────────────────────────


def propose_anchor(
    repo_path: str,
    file: str,
    symbol: str | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
    skeleton: Skeleton | None = None,
) -> dict:
    """Verify a citation against the repository, via the Stage 0 resolver.

    Not a search tool — the last step of an investigation, turning "I think this
    is the right code" into a checked anchor. Delegates entirely to
    backend/repo/anchors.py so there is one grounding oracle, not two.

    DOES NOT check whether the caller was ever shown this code. That is the
    separate Stage-0 evidence gate, which lives with the agents.
    """
    sk = _skeleton(repo_path, skeleton)
    resolution = anchors.resolve(
        sk, file, symbol=symbol, line_start=line_start, line_end=line_end
    )
    if not resolution.ok:
        return _err(resolution.reason, f"cannot verify {file!r} against the repository")
    a = resolution.anchor
    return {
        "ok": True, "file": a.file, "line_start": a.line_start,
        "line_end": a.line_end, "symbol": a.symbol, "kind": a.kind,
    }


# ── dispatch ──────────────────────────────────────────────────────────────────

TOOLS = {
    "list_files": list_files,
    "read_file": read_file,
    "search_code": search_code,
    "symbols": symbols,
    "neighbors": neighbors,
    "propose_anchor": propose_anchor,
}


def run_tool(name: str, repo_path: str, /, **kwargs) -> dict:
    """Invoke a tool by name. Unknown names and bad arguments become results,
    not exceptions — an explorer must be able to recover from its own mistakes
    without the loop crashing.

    `name` and `repo_path` are POSITIONAL-ONLY on purpose: `symbols` takes a
    `name` argument of its own, so `run_tool("symbols", repo, name="Session.send")`
    would otherwise bind `name` twice and raise TypeError before the tool ever
    ran. That is one of the two main ways to use the keystone tool, and it killed
    a whole investigation when the model reached for it.
    """
    kwargs.pop("repo_path", None)   # injected, never model-supplied
    tool = TOOLS.get(name)
    if tool is None:
        return _err("unknown_tool", f"{name!r} is not one of {sorted(TOOLS)}")
    try:
        return tool(repo_path, **kwargs)
    except TypeError as exc:
        return _err("bad_arguments", str(exc))
    except Exception as exc:  # a tool failure is a result, never a crash
        return _err("tool_failed", f"{name} raised {type(exc).__name__}: {exc}")
