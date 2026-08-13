# Repository skeleton — the deterministic symbol/file index (Layer A).
#
# What exists in the repository, with exact line ranges. No LLM, no embeddings,
# no similarity. This is the grounding oracle: an anchor is real if and only if
# it can be located here (see backend/repo/anchors.py).
#
# Built by REUSING backend/rag/chunker.py's tree-sitter walk rather than adding a
# second parser. The chunker already produces (file, start_line, end_line, type,
# name, role) for every function and class; the skeleton derives qualified names
# by containment on top of that and drops the chunk bodies.
#
# Public API:
#   build_skeleton(repo_path) -> Skeleton      cached per repo_path
#   Skeleton.from_chunks(chunks, ...)          construct directly (used by tests)
#
# Path convention: every path in a Skeleton is repo-relative and uses forward
# slashes, on every platform. The chunker emits OS separators (Windows produces
# "src\requests\api.py"), so normalisation happens once, here, and everything
# downstream can compare paths without thinking about it.

from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from backend.repo.parser import parse_repo


# Provisional subsystem-granularity constant — see repo-understanding.md OQ7.
# A directory bucket larger than this splits into one subsystem per file, so a
# big subpackage cannot hide inside a single entry.
SUBSYSTEM_MAX_FILES = 12


def normalize_path(path: str) -> str:
    """Repo-relative path with forward slashes. Idempotent.

    Only a literal leading "./" is stripped — str.lstrip("./") would eat the dot
    of a legitimate dotted directory and turn ".github/x.py" into "github/x.py",
    which would then fail to resolve against the real file.
    """
    normalized = str(path).replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def safe_repo_path(repo_path: str, relative: str) -> Path | None:
    """Absolute path for a repo-relative path, or None if it escapes the repo.

    The single repository-boundary check for the whole tool layer — no tool
    reimplements this. Rejects absolute inputs, Windows drive letters, and any
    traversal that lands outside the checkout, including via symlinks (which
    ``resolve()`` follows before the containment test).
    """
    normalized = normalize_path(relative)
    if not normalized or normalized.startswith("/"):
        return None
    if len(normalized) > 1 and normalized[1] == ":":  # "C:/..." on Windows
        return None
    root = Path(repo_path).resolve()
    target = (root / normalized).resolve()
    if target != root and not target.is_relative_to(root):
        return None
    return target


@dataclass(frozen=True)
class Symbol:
    name: str                 # "send"
    qualified_name: str       # "Session.send" — unique within a file in practice
    kind: str                 # "function" | "class"
    file: str                 # normalized, repo-relative
    line_start: int           # 1-indexed, inclusive
    line_end: int             # 1-indexed, inclusive
    parent: str | None        # enclosing class name, or None
    role: str                 # source | test | doc | example | tooling

    @property
    def line_count(self) -> int:
        return self.line_end - self.line_start + 1


@dataclass(frozen=True)
class FileEntry:
    path: str
    role: str
    line_count: int
    symbol_count: int


@dataclass(frozen=True)
class ImportEntry:
    """One import statement, parsed exactly (via `ast`) rather than by regex."""

    file: str                  # normalized path of the importing file
    line_start: int
    line_end: int
    module: str | None         # "requests.auth", or "auth" for a relative import
    level: int                 # 0 = absolute, 1+ = number of leading dots
    names: tuple[str, ...]     # imported names ("*" for a star import)
    statement: str


@dataclass(frozen=True)
class Export:
    """One way a symbol is reachable by code outside the repository.

    A package's ``__init__.py`` re-exporting a name is the one form of "public
    API" Python states structurally rather than by convention, which makes it
    the only form Layer A is allowed to report. Everything else — what the docs
    call public, what the changelog promises — is judgement, and belongs to
    Layer C.
    """

    symbol: str            # the name as users write it
    defined_in: str        # the file that actually defines it
    exported_from: str     # the __init__.py that re-exports it
    import_path: str       # "fastapi.Depends" — what a user types
    line: int              # the re-export statement's line


@dataclass
class Skeleton:
    """Deterministic inventory of one repository checkout."""

    files: dict[str, FileEntry]
    symbols: list[Symbol]
    # Top-level import statements, used by the `neighbors` tool to follow real
    # dependency edges rather than guessing from names.
    imports: list[ImportEntry] = field(default_factory=list)
    # Set when the skeleton was built from a real checkout. Enables content
    # checks (an anchored range must not be pure whitespace). A synthetic
    # skeleton leaves it None and those checks are skipped.
    repo_path: str | None = None

    _by_file: dict[str, list[Symbol]] = field(default_factory=dict, repr=False)
    _by_qualified: dict[tuple[str, str], Symbol] = field(default_factory=dict, repr=False)
    _by_name: dict[str, list[Symbol]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        for sym in self.symbols:
            self._by_file.setdefault(sym.file, []).append(sym)
            # First writer wins on a collision (e.g. a conditionally redefined
            # function). Ambiguity is resolved by line range, not by name.
            self._by_qualified.setdefault((sym.file, sym.qualified_name), sym)
            self._by_name.setdefault(sym.name, []).append(sym)

    # ── construction ─────────────────────────────────────────────────────────

    @classmethod
    def from_chunks(
        cls,
        chunks: list[dict],
        file_lines: dict[str, int] | None = None,
        repo_path: str | None = None,
    ) -> "Skeleton":
        """Build from chunker-shaped dicts.

        ``file_lines`` maps a normalized path to its real line count. When a file
        is absent from it, the highest ``end_line`` seen for that file is used as
        the bound — good enough for synthetic skeletons in tests, while
        ``build_skeleton`` always supplies real counts.
        """
        file_lines = {normalize_path(k): v for k, v in (file_lines or {}).items()}

        # Class chunks first, so a function can find its enclosing class.
        classes_by_file: dict[str, list[dict]] = {}
        for c in chunks:
            if c.get("type") == "class":
                classes_by_file.setdefault(normalize_path(c["file"]), []).append(c)

        symbols: list[Symbol] = []
        imports: list[ImportEntry] = []
        max_line: dict[str, int] = {}
        roles: dict[str, str] = {}
        for c in chunks:
            kind = c.get("type")
            path = normalize_path(c["file"])
            start, end = int(c["start_line"]), int(c["end_line"])
            max_line[path] = max(max_line.get(path, 0), end)
            roles.setdefault(path, c.get("role", "source"))
            if kind == "import":
                # Imports are chunked but are not symbols; they become
                # dependency edges instead.
                imports.extend(
                    _parse_import(path, start, end, c.get("content") or "")
                )
                continue
            if kind not in ("function", "class"):
                continue
            parent = _enclosing_class_name(classes_by_file.get(path, []), c)
            name = c["name"]
            symbols.append(
                Symbol(
                    name=name,
                    qualified_name=f"{parent}.{name}" if parent else name,
                    kind=kind,
                    file=path,
                    line_start=start,
                    line_end=end,
                    parent=parent,
                    role=c.get("role", "source"),
                )
            )

        per_file_counts: dict[str, int] = {}
        for sym in symbols:
            per_file_counts[sym.file] = per_file_counts.get(sym.file, 0) + 1

        files = {
            path: FileEntry(
                path=path,
                role=roles.get(path, "source"),
                line_count=file_lines.get(path, max_line.get(path, 0)),
                symbol_count=per_file_counts.get(path, 0),
            )
            for path in sorted(set(max_line) | set(file_lines))
        }
        return cls(
            files=files, symbols=symbols, imports=imports, repo_path=repo_path
        )

    # ── lookups ──────────────────────────────────────────────────────────────

    def canonical_file(self, path: str) -> str | None:
        """Resolve a possibly-abbreviated path to a real indexed file.

        Exact match wins. Otherwise a unique path-suffix match is accepted — the
        common case being a model that dropped the package prefix and wrote
        "sessions.py" for "src/requests/sessions.py". Ambiguity is a rejection,
        never a guess.
        """
        candidate = normalize_path(path)
        if candidate in self.files:
            return candidate
        suffix_matches = [
            known
            for known in self.files
            if known.endswith("/" + candidate) or candidate.endswith("/" + known)
        ]
        if len(suffix_matches) == 1:
            return suffix_matches[0]
        return None

    def symbols_in(self, file: str) -> list[Symbol]:
        return list(self._by_file.get(normalize_path(file), []))

    def find_symbol(self, name: str, file: str | None = None) -> list[Symbol]:
        """Symbols matching ``name`` — qualified ("Session.send") or bare ("send").

        Scoped to ``file`` when given. Returns every match so the caller decides
        what to do about ambiguity.
        """
        if file is not None:
            path = self.canonical_file(file)
            if path is None:
                return []
            exact = self._by_qualified.get((path, name))
            if exact is not None:
                return [exact]
            return [s for s in self._by_file.get(path, []) if s.name == name]

        by_qualified = [s for s in self.symbols if s.qualified_name == name]
        return by_qualified or list(self._by_name.get(name, []))

    def exact_symbol(self, file: str, start: int, end: int) -> Symbol | None:
        """The symbol occupying exactly this range, preferring the narrowest."""
        matches = [
            s
            for s in self.symbols_in(file)
            if s.line_start == start and s.line_end == end
        ]
        if not matches:
            return None
        # A class and its only method can share a range in degenerate cases;
        # the function is the more teachable unit.
        matches.sort(key=lambda s: (s.kind != "function",))
        return matches[0]

    def enclosing_symbol(self, file: str, start: int, end: int) -> Symbol | None:
        """Narrowest symbol whose span contains [start, end]."""
        containing = [
            s
            for s in self.symbols_in(file)
            if s.line_start <= start and end <= s.line_end
        ]
        if not containing:
            return None
        return min(containing, key=lambda s: s.line_count)

    def imports_in(self, file: str) -> list[ImportEntry]:
        path = self.canonical_file(file)
        return [i for i in self.imports if i.file == path] if path else []

    def resolve_import(self, entry: ImportEntry) -> str | None:
        """The repo file an import refers to, or None when it leaves the repo.

        An unresolved import is not an error — it usually means a third-party
        or stdlib module, which is a true fact about the dependency edge.
        """
        parts: list[str] = []
        if entry.level:
            # Relative: walk up from the importing file's directory. level=1 is
            # the current package, level=2 its parent, and so on.
            base = os.path.dirname(entry.file).split("/") if "/" in entry.file else []
            up = entry.level - 1
            base = base[:-up] if up and up <= len(base) else base
            parts = [p for p in base if p]
        if entry.module:
            parts.extend(entry.module.split("."))
        if not parts:
            return None

        stem = "/".join(parts)
        for candidate in (f"{stem}.py", f"{stem}/__init__.py"):
            if candidate in self.files:
                return candidate
        if entry.level:
            # A relative import is already anchored to a directory; refusing to
            # suffix-match keeps it from silently binding to a same-named module
            # elsewhere in the repo.
            return None
        if len(parts) < 2:
            # A single-segment absolute import ("import types", "import json")
            # is almost always stdlib. Suffix-matching it would bind `types` to
            # any `*/types.py` in the repo — a confident wrong answer, which is
            # worse for grounding than an honest "leaves the repo".
            return None
        # A src/-layout repo needs this: "requests.auth" lives at
        # "src/requests/auth.py". Dotted paths are specific enough that a unique
        # suffix match is trustworthy; ambiguity still declines to guess.
        for candidate in (f"{stem}.py", f"{stem}/__init__.py"):
            matches = [f for f in self.files if f.endswith("/" + candidate)]
            if len(matches) == 1:
                return matches[0]
        return None

    def _package_path(self, init_file: str) -> str:
        """Dotted import path of the package an ``__init__.py`` defines.

        The package root is the highest ancestor directory that still has an
        ``__init__.py``, which is what Python itself uses — not the source root.
        A src/-layout repo therefore reports "requests", not "src.requests",
        because `src/` has no `__init__.py` and is not part of the import path.
        """
        parts = [p for p in os.path.dirname(init_file).replace("\\", "/").split("/") if p]
        for index in range(len(parts)):
            if f"{'/'.join(parts[:index + 1])}/__init__.py" in self.files:
                return ".".join(parts[index:])
        return ".".join(parts)

    def exports_of(self, name: str, file: str | None = None) -> list[Export]:
        """How code outside the repository reaches ``name``, per the import graph.

        Answers the question the `fastapi-di` gap turned on: a user writes
        `from fastapi import Depends`, and that name is not the class the
        internals pass around but a factory re-exported beside it. Structural,
        not conventional — the re-export statement either exists or it does not.

        ``file`` scopes the answer to one definition, which is what distinguishes
        the public twin from the internal one when both share a name.
        """
        wanted = self.canonical_file(file) if file else None
        definitions = [
            s for s in self.find_symbol(name)
            if wanted is None or s.file == wanted
        ]
        if not definitions:
            return []
        defining_files = {s.file for s in definitions}
        bare = definitions[0].name

        exports: list[Export] = []
        for entry in self.imports:
            if not entry.file.endswith("__init__.py"):
                continue
            if bare not in entry.names and "*" not in entry.names:
                continue
            target = self.resolve_import(entry)
            if target is None or target not in defining_files:
                continue
            package = self._package_path(entry.file)
            exports.append(Export(
                symbol=bare,
                defined_in=target,
                exported_from=entry.file,
                import_path=f"{package}.{bare}" if package else bare,
                line=entry.line_start,
            ))
        # A symbol defined directly in an __init__.py is public by position.
        for symbol in definitions:
            if symbol.file.endswith("__init__.py"):
                package = self._package_path(symbol.file)
                exports.append(Export(
                    symbol=symbol.name, defined_in=symbol.file,
                    exported_from=symbol.file,
                    import_path=f"{package}.{symbol.name}" if package else symbol.name,
                    line=symbol.line_start,
                ))
        exports.sort(key=lambda e: (e.import_path, e.exported_from))
        return exports

    def file_line_count(self, file: str) -> int:
        path = self.canonical_file(file)
        return self.files[path].line_count if path else 0

    def read_lines(self, file: str, start: int, end: int) -> str | None:
        """Source text for [start, end], or None when there is no real checkout."""
        if self.repo_path is None:
            return None
        path = self.canonical_file(file)
        if path is None:
            return None
        try:
            text = Path(self.repo_path).joinpath(path).read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            return None
        return "\n".join(text.splitlines()[start - 1:end])

    # ── derived inventory (repo-understanding.md OQ7, provisional v1) ─────────

    def source_root(self) -> str:
        """Longest common directory prefix of all source files.

        "src/requests" for requests, "fastapi" for fastapi, "" for a repo whose
        modules sit at the top level.
        """
        dirs = [
            os.path.dirname(p)
            for p, e in self.files.items()
            if e.role == "source"
        ]
        if not dirs:
            return ""
        common = os.path.commonpath(dirs).replace("\\", "/") if len(dirs) > 1 else dirs[0]
        return "" if common == "." else common

    def subsystems(self) -> dict[str, list[str]]:
        """Required-subsystem inventory: name -> the source files it contains.

        Provisional v1 rule (OQ7). Structure is the only signal; this is
        deterministic by construction and must never become a classification
        problem for a model.

          - subdirectories below the source root are one subsystem each
          - modules sitting directly at the source root are one subsystem each,
            so a flat package does not collapse into a single vacuous unit
          - a directory bucket over SUBSYSTEM_MAX_FILES splits per file
        """
        root = self.source_root()
        prefix = root + "/" if root else ""

        buckets: dict[str, list[str]] = {}
        for path, entry in self.files.items():
            if entry.role != "source":
                continue
            relative = path[len(prefix):] if prefix and path.startswith(prefix) else path
            directory = os.path.dirname(relative).replace("\\", "/")
            # No directory => a module at the source root => its own subsystem.
            key = directory if directory else relative
            buckets.setdefault(key, []).append(path)

        result: dict[str, list[str]] = {}
        for key, paths in buckets.items():
            if len(paths) > SUBSYSTEM_MAX_FILES:
                for p in paths:
                    result[p[len(prefix):] if prefix and p.startswith(prefix) else p] = [p]
            else:
                result[key] = sorted(paths)
        return dict(sorted(result.items()))


def _parse_import(
    path: str, start: int, end: int, statement: str
) -> list[ImportEntry]:
    """Parse one import statement with `ast` — exact, not regex-approximated.

    A statement that will not parse (a fragment, a syntax the grammar accepted
    but Python does not) is skipped rather than guessed at.
    """
    text = statement.strip()
    if not text:
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    entries: list[ImportEntry] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                entries.append(ImportEntry(
                    file=path, line_start=start, line_end=end,
                    module=alias.name, level=0,
                    names=(alias.asname or alias.name,), statement=text,
                ))
        elif isinstance(node, ast.ImportFrom):
            entries.append(ImportEntry(
                file=path, line_start=start, line_end=end,
                module=node.module, level=node.level or 0,
                names=tuple(a.name for a in node.names), statement=text,
            ))
    return entries


def _enclosing_class_name(class_chunks: list[dict], chunk: dict) -> str | None:
    """Narrowest class strictly containing ``chunk``, by line range."""
    if chunk.get("type") != "function":
        return None
    start, end = int(chunk["start_line"]), int(chunk["end_line"])
    containing = [
        c
        for c in class_chunks
        if int(c["start_line"]) <= start and end <= int(c["end_line"])
    ]
    if not containing:
        return None
    narrowest = min(containing, key=lambda c: int(c["end_line"]) - int(c["start_line"]))
    return narrowest["name"]


def _count_lines(repo_path: str, relative: str) -> int:
    try:
        text = Path(repo_path).joinpath(relative).read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError:
        return 0
    return len(text.splitlines())


@lru_cache(maxsize=8)
def build_skeleton(repo_path: str) -> Skeleton:
    """Index a checkout. Cached — a clone is pinned and never updated in place.

    Call ``build_skeleton.cache_clear()`` if a checkout does change underneath.
    """
    chunks = parse_repo(repo_path)
    paths = {normalize_path(c["file"]) for c in chunks}
    file_lines = {p: _count_lines(repo_path, p) for p in paths}
    return Skeleton.from_chunks(chunks, file_lines=file_lines, repo_path=repo_path)
