# The contribution stage — Plan → Locate → Implement → Validate → Review.
#
# ── WHY THIS IS NOT IN THE LEARNING GRAPH ─────────────────────────────────────
#
# The obvious implementation is five more `LearningNode`s. It is wrong three
# times over, in descending order of severity:
#
#   1. It corrupts every progress measure. Five stages in the walk move
#      `journey_progress`, `stops_total` and `is_complete()`; any marked
#      `required` would enter `goal_readiness`'s denominator — the exact defect
#      `progress.py`'s header records, where the gauge fell from 0.50 to 0.33 the
#      moment the system decided to help. D7 forbids it.
#   2. A node's contract is that the Planner writes an objective, Teaching builds
#      exactly it, and the Grader marks exactly it (D4). "Write your patch" has
#      no claim to mark, so it would be a node with a hollow contract.
#   3. Writing a patch is a LEARNER ACTION. Letting one move
#      `understanding_state` is precisely what D8 forbids.
#
# So the stages are session state: same session, same page, a different phase of
# it.
#
# ── WHAT THIS MODULE MAY AND MAY NOT DO ───────────────────────────────────────
#
# Pure. No IO, no model calls, no subprocess, and — the load-bearing one —
# **nothing here ever writes to the repository checkout.** `data/repos/<owner>/
# <name>` is ONE directory shared by every user and every session of that
# repository (see `repo/cloner.py`), so applying a learner's patch there would
# corrupt other people's sessions. The patch lives in `contribution_json` and is
# never applied to anything.
#
# `ast.parse` is the one structural read of learner text this module performs. It
# builds a syntax tree; it does not import, execute or evaluate. That distinction
# is the whole reason the deterministic checks can exist at all.
#
# ── THREE CLAIMS, KEPT APART ──────────────────────────────────────────────────
#
#   SCOPE        which files were touched          — decided here, deterministically
#   CORRECTNESS  whether it does what was asked    — a model's opinion, elsewhere
#   TESTS        whether the repository passes     — NOBODY. Not run.
#
# `ScopeCheck.passed` means the first and only the first. The `change_boundary`
# it compares against was itself derived by an investigation, so a path
# comparison must never be allowed to imply correctness — see the property's own
# docstring, and `frontend/lib/strings.ts` for the wording that carries it.

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Literal


Stage = Literal["plan", "locate", "implement", "validate", "review", "done"]

STAGE_ORDER: tuple[Stage, ...] = (
    "plan", "locate", "implement", "validate", "review", "done",
)

# Bounds on learner-authored text. `ast.parse` is safe but not unbounded: deeply
# nested input can exhaust the C stack, and `RecursionError` from a 500 handler
# is a worse answer than a refusal. Refusing early is cheaper than catching, and
# more honest than truncating a patch and checking the remains.
MAX_PATCH_FILES = 10
MAX_PATCH_BYTES = 64 * 1024

# Path fragments that mean "this is a test file" when the boundary does not say.
# A fallback, not the rule: the boundary's `existing_tests` is the authority, and
# this only catches a learner who added a test file the investigation had not
# named — which is a good thing to do and should not read as "no test written".
_TEST_HINTS = ("test_", "_test.", "/tests/", "tests/")


@dataclass
class PatchFile:
    """One file the learner proposes to write. NEVER applied to disk."""

    path: str
    contents: str
    intent: Literal["modify", "add"] = "modify"

    def to_dict(self) -> dict:
        return {"path": self.path, "contents": self.contents, "intent": self.intent}

    @staticmethod
    def from_dict(raw: dict) -> "PatchFile":
        intent = str(raw.get("intent") or "modify")
        return PatchFile(
            path=str(raw.get("path") or ""),
            contents=str(raw.get("contents") or ""),
            intent="add" if intent == "add" else "modify",
        )


@dataclass
class ScopeCheck:
    """What our code can decide about a proposed patch, without running anything.

    Every field is a list of file paths or symbol names, so the surface can name
    what it found instead of showing a tick. A check that reports only a boolean
    cannot tell the learner what to fix.
    """

    in_boundary: list[str] = field(default_factory=list)
    outside_boundary: list[str] = field(default_factory=list)
    # Touched something the investigation said not to. Its own list because the
    # response is different: not "you went wide", but "you went somewhere the
    # change was explicitly not supposed to go".
    forbidden: list[str] = field(default_factory=list)
    unparseable: list[str] = field(default_factory=list)
    symbols_defined: list[str] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    misnamed_tests: list[str] = field(default_factory=list)
    # ── the constraints we did NOT check ──────────────────────────────────────
    #
    # `"file:symbol"` for every symbol-level `must_not_change` entry that touches
    # a file this patch changes. NOT a finding, and never a failure: it is the
    # list of things this check was asked about and cannot answer.
    #
    # It exists because silence reads as a pass. A boundary that says "do not
    # change `cookies.py:get`" beside a green "Scope check passed" invites the
    # reading that `get` was checked and found intact. Nothing here parsed the
    # original file or compared it at symbol granularity, so the honest surface
    # is a row that says the check was not performed — which is what the UI
    # renders from this, and only when the list is non-empty.
    unchecked_symbols: list[str] = field(default_factory=list)
    # True only when the boundary named a symbol to compare against. The Validate
    # surface renders the symbol row ONLY when this is true, rather than showing
    # an empty row for a task that never named one.
    symbol_expected: str = ""

    @property
    def passed(self) -> bool:
        """**PATH SCOPE ONLY.** Not correctness, not safety, not a test result,
        and not the protected symbols — see `unchecked_symbols`.

        The one claim this supports is: *no files outside the planned
        contribution boundary were modified.* The boundary itself was derived
        during the investigation of the task, so it is a plan the learner stayed
        inside — never evidence that the change is right.

        `unparseable` is deliberately NOT a failure here. A syntax error is a
        fact worth reporting and it is not a scope violation; folding it in would
        make one word mean two things, which is how "scope check passed" starts
        being read as "the change is fine".
        """
        return not (self.outside_boundary or self.forbidden)

    @property
    def symbol_found(self) -> bool:
        """Did the patch define the symbol the boundary named? False when none was."""
        if not self.symbol_expected:
            return False
        return self.symbol_expected in self.symbols_defined

    def to_dict(self) -> dict:
        return {
            "in_boundary": list(self.in_boundary),
            "outside_boundary": list(self.outside_boundary),
            "forbidden": list(self.forbidden),
            "unparseable": list(self.unparseable),
            "symbols_defined": list(self.symbols_defined),
            "test_files": list(self.test_files),
            "misnamed_tests": list(self.misnamed_tests),
            "unchecked_symbols": list(self.unchecked_symbols),
            "symbol_expected": self.symbol_expected,
            "symbol_found": self.symbol_found,
            "passed": self.passed,
        }

    @staticmethod
    def from_dict(raw: dict) -> "ScopeCheck":
        # `passed` and `symbol_found` are derived and deliberately not read back:
        # a stored boolean that disagreed with the lists beside it would be a
        # second authority on the same question.
        return ScopeCheck(
            in_boundary=[str(x) for x in raw.get("in_boundary") or []],
            outside_boundary=[str(x) for x in raw.get("outside_boundary") or []],
            forbidden=[str(x) for x in raw.get("forbidden") or []],
            unparseable=[str(x) for x in raw.get("unparseable") or []],
            symbols_defined=[str(x) for x in raw.get("symbols_defined") or []],
            test_files=[str(x) for x in raw.get("test_files") or []],
            misnamed_tests=[str(x) for x in raw.get("misnamed_tests") or []],
            unchecked_symbols=[str(x) for x in raw.get("unchecked_symbols") or []],
            symbol_expected=str(raw.get("symbol_expected") or ""),
        )


@dataclass
class ContributionState:
    """The contribution stage's own state. Learner-produced, session-scoped.

    Deliberately holds NO copy of the task and NO copy of the change boundary.
    The task is `graph.goal["contribution_context"]` and the boundary is the
    dossier's; copying either here would make two rows authoritative for one
    fact, which is the failure `state-ownership.md` exists to prevent.

    Holds no understanding, readiness or gap field either. Readiness is derived
    from the graph (`progress.ready_to_implement`), and nothing in this dataclass
    may be read by the learning engine.
    """

    stage: Stage = "plan"
    plan: dict | None = None
    patch: list[PatchFile] = field(default_factory=list)
    scope_check: ScopeCheck | None = None
    review: dict | None = None
    pr: dict | None = None
    # The learner chose to start implementing before every required concept was
    # demonstrated. RECORDED, NEVER EVIDENCE — the `continue_past` shape: an
    # explicit decision that unblocks the road without ever becoming a claim
    # about what they understand.
    proceeded_unready: bool = False
    # RECOMMENDED, never executed. Derived from the boundary's existing tests.
    validation_command: str = ""

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "plan": self.plan,
            "patch": [f.to_dict() for f in self.patch],
            "scope_check": self.scope_check.to_dict() if self.scope_check else None,
            "review": self.review,
            "pr": self.pr,
            "proceeded_unready": self.proceeded_unready,
            "validation_command": self.validation_command,
        }

    @staticmethod
    def from_dict(raw: dict | None) -> "ContributionState | None":
        if not isinstance(raw, dict):
            return None
        stage = str(raw.get("stage") or "plan")
        scope_raw = raw.get("scope_check")
        return ContributionState(
            stage=stage if stage in STAGE_ORDER else "plan",  # type: ignore[arg-type]
            plan=raw.get("plan") if isinstance(raw.get("plan"), dict) else None,
            patch=[
                PatchFile.from_dict(f)
                for f in raw.get("patch") or []
                if isinstance(f, dict)
            ],
            scope_check=(
                ScopeCheck.from_dict(scope_raw)
                if isinstance(scope_raw, dict) else None
            ),
            review=raw.get("review") if isinstance(raw.get("review"), dict) else None,
            pr=raw.get("pr") if isinstance(raw.get("pr"), dict) else None,
            proceeded_unready=bool(raw.get("proceeded_unready")),
            validation_command=str(raw.get("validation_command") or ""),
        )


# ── reading the boundary ──────────────────────────────────────────────────────


def _norm(path: str) -> str:
    return str(path or "").replace("\\", "/").strip().lstrip("./")


def boundary_paths(boundary: dict, section: str) -> set[str]:
    """The file paths one change-boundary section names."""
    entries = boundary.get(section)
    if not isinstance(entries, list):
        return set()
    return {
        _norm(str(e.get("file")))
        for e in entries
        if isinstance(e, dict) and e.get("file")
    }


def protected_symbols(boundary: dict) -> dict[str, list[str]]:
    """Symbol-level `must_not_change` entries, keyed by the file they live in.

    The constraints this checker is asked about and cannot evaluate. Separated
    from `whole_files_forbidden` because the two need opposite treatment: one is
    a rule a path comparison can enforce, the other is a rule it must decline to
    claim it enforced.
    """
    entries = boundary.get("must_not_change")
    if not isinstance(entries, list):
        return {}
    out: dict[str, list[str]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        file = _norm(str(entry.get("file") or ""))
        symbol = str(entry.get("symbol") or "").strip()
        if file and symbol:
            out.setdefault(file, []).append(symbol)
    return out


def whole_files_forbidden(boundary: dict) -> set[str]:
    """Files `must_not_change` puts off limits ENTIRELY — no symbol named.

    THE DISTINCTION THIS FUNCTION EXISTS FOR, found by running the thing:

    A real boundary named `cookies.py:RequestsCookieJar` as the target and
    `cookies.py:RequestsCookieJar.get` as untouchable — one file, two symbols.
    It also named `tests/test_requests.py:TestRequests.test_cookie_duplicate_
    names_different_domains` untouchable, in the very file the learner has to add
    a test to. Comparing paths marked both files of a correct patch forbidden.

    So: an entry that names a SYMBOL is a symbol-level constraint, and a
    path comparison cannot evaluate it. Reporting it as a path violation is
    claiming to have checked something we did not — the exact overclaiming this
    stage's wording is built to avoid. Only an entry with NO symbol means "stay
    out of this file", and only that can fail a path check.

    What is lost is real and is deliberately left unclaimed: nothing here can
    tell the learner they edited `get()`. That is what the Review step reads for,
    and it is labelled an opinion because it is one.
    """
    entries = boundary.get("must_not_change")
    if not isinstance(entries, list):
        return set()
    return {
        _norm(str(e.get("file")))
        for e in entries
        if isinstance(e, dict) and e.get("file")
        and not str(e.get("symbol") or "").strip()
    }


def target_symbol(boundary: dict) -> str:
    """The bare symbol name the boundary's first target names, or "".

    Bare, because the boundary carries a qualified name (`RequestsCookieJar.get_all`)
    while `ast` sees only the leaf (`get_all`) — comparing the two forms directly
    would report every method as missing.

    Empty when the boundary names no target, which is what makes the Validate
    surface able to omit the symbol row rather than render a meaningless one.
    """
    entries = boundary.get("target")
    if not isinstance(entries, list):
        return ""
    for entry in entries:
        if isinstance(entry, dict) and str(entry.get("symbol") or "").strip():
            return str(entry["symbol"]).strip().rsplit(".", 1)[-1]
    return ""


def validation_command(boundary: dict, fallback: str = "") -> str:
    """The smallest relevant test command, as a RECOMMENDATION. Never executed.

    Built from the test files the investigation actually found, so it points at
    the tests that already guard this behaviour rather than at the whole suite.
    Returns "" when the boundary names none — the surface then says so instead of
    inventing a command that may not work.
    """
    files = sorted(boundary_paths(boundary, "existing_tests"))
    if not files:
        return fallback
    return "pytest " + " ".join(files[:3]) + " -q"


# ── the deterministic checks ──────────────────────────────────────────────────


def _defined_symbols(tree: ast.AST) -> list[str]:
    """Every function/class name defined anywhere in the tree, nesting included."""
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
    return names


def _top_level_test_names(tree: ast.AST) -> list[str]:
    """Function names in a test file, including methods of a test class.

    Both levels, because this repository's own demo target writes both shapes —
    `TestRequests.test_cookie_parameters` and a module-level `test_json_encodes`
    live in the same file.
    """
    names: list[str] = []
    for node in getattr(tree, "body", []):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.append(node.name)
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.append(child.name)
    return names


def looks_like_test(path: str, boundary_tests: set[str]) -> bool:
    boundary_hit = _norm(path) in boundary_tests
    name = _norm(path).lower()
    return boundary_hit or any(hint in name for hint in _TEST_HINTS)


def _scope_sets(boundary: dict) -> tuple[set[str], set[str]]:
    """(allowed, forbidden) paths for one boundary. The set comparison, once.

    Extracted so `check_scope` and `check_paths` cannot drift: two definitions of
    "inside the boundary" would be two answers to the question the whole stage
    exists to answer. The rules are unchanged — see `check_scope`.
    """
    forbidden = whole_files_forbidden(boundary)
    allowed = (
        boundary_paths(boundary, "target")
        | boundary_paths(boundary, "existing_tests")
        | (boundary_paths(boundary, "must_not_change") - forbidden)
    )
    forbidden -= (
        boundary_paths(boundary, "target")
        | boundary_paths(boundary, "existing_tests")
    )
    return allowed, forbidden


#: What a path-only check did NOT look at. Shipped WITH the result, never
#: omitted: `check_paths` cannot see file contents, so every claim `check_scope`
#: makes from `ast.parse` is unmade here — and a result that lists four findings
#: and stays silent about the rest reads as a full check that passed.
PATHS_NOT_CHECKED = (
    "syntax", "symbol definitions", "protected symbols", "test contents",
    "repository tests",
)


def check_paths(paths: list[str], boundary: dict) -> dict:
    """Scope, from file paths alone. **No contents, so no symbol or syntax claim.**

    For a caller that can see which files changed but not what is in them — the
    MCP bridge, where the working tree belongs to the learner and their coding
    agent and only `git diff --name-only` crosses the boundary.

    NOT `check_scope` with empty contents, and the difference is not cosmetic.
    `check_scope` sets `symbol_expected` unconditionally, so empty contents make
    `symbol_found` false and report a symbol that is present as missing; and an
    empty `unparseable` list renders as "every file parses", which is a claim
    nobody made. Both are the same failure — **silence read as a pass** — so this
    returns its own narrower shape that names what it did not do.

    The one claim: *no file outside the planned boundary was changed.* The
    boundary was derived during the investigation of this task, so it is a plan
    the learner stayed inside — never evidence that the change is right.
    """
    allowed, forbidden_paths = _scope_sets(boundary)
    protected = protected_symbols(boundary)

    inside: list[str] = []
    outside: list[str] = []
    forbidden: list[str] = []
    unchecked: list[str] = []

    for raw in paths:
        path = _norm(raw)
        if not path:
            continue
        if path in forbidden_paths:
            forbidden.append(path)
        elif not allowed or path in allowed:
            # No boundary to compare against → everything counts as inside, so
            # `passed` says nothing it cannot support.
            inside.append(path)
        else:
            outside.append(path)
        for symbol in protected.get(path, []):
            unchecked.append(f"{path}:{symbol}")

    return {
        "passed": not (outside or forbidden),
        "in_boundary": inside,
        "outside_boundary": outside,
        "forbidden": forbidden,
        "unchecked_symbols": unchecked,
        "checked": "file paths against the change boundary for this session",
        "not_checked": list(PATHS_NOT_CHECKED),
    }


def check_scope(patch: list[PatchFile], boundary: dict) -> ScopeCheck:
    """Compare a proposed patch against the planned boundary. No execution.

    The only judgement made here is a set comparison plus `ast.parse`. Every
    finding is a list of names the surface can print, and `passed` answers one
    question: did anything land outside the plan.

    A boundary with NO targets and NO forbidden paths cannot decide scope, so
    nothing is reported outside it — an empty plan must not accuse the learner of
    leaving a boundary that was never drawn.
    """
    # WHAT "OUTSIDE THE PLANNED BOUNDARY" MEANS: a file the boundary never
    # mentions at all.
    #
    # Not "a file that is not a target". A file the investigation named — even
    # only to say "do not break the test in it" — is a file it considered part of
    # this change's neighbourhood, and a learner who adds a test to it has not
    # gone anywhere the plan did not go. On a real run the boundary listed the
    # test file solely under `must_not_change`, and the narrower definition
    # reported a correct patch as out of scope.
    #
    # The exception is a whole-file exclusion, which is the one thing
    # `must_not_change` can say that a path check can act on.
    allowed, forbidden_paths = _scope_sets(boundary)
    check = ScopeCheck(symbol_expected=target_symbol(boundary))
    boundary_tests = boundary_paths(boundary, "existing_tests")
    protected = protected_symbols(boundary)

    for entry in patch:
        path = _norm(entry.path)
        if not path:
            continue
        if path in forbidden_paths:
            check.forbidden.append(path)
        elif not allowed or path in allowed:
            # No boundary to compare against → everything counts as inside, and
            # `passed` therefore says nothing it cannot support.
            check.in_boundary.append(path)
        else:
            check.outside_boundary.append(path)

        # What the boundary protects INSIDE a file this patch touches. Recorded
        # only for touched files: a symbol in a file the learner never opened is
        # not a constraint anyone needs telling about.
        for symbol in protected.get(path, []):
            check.unchecked_symbols.append(f"{path}:{symbol}")

        is_test = looks_like_test(path, boundary_tests)
        if is_test:
            check.test_files.append(path)

        if not path.endswith(".py"):
            continue
        try:
            tree = ast.parse(entry.contents)
        except (SyntaxError, ValueError, RecursionError, MemoryError):
            # Every one of these is "we could not read it", and none of them is
            # a reason to fail the request. A patch that does not parse is a
            # finding to show the learner, not a 500.
            check.unparseable.append(path)
            continue
        check.symbols_defined.extend(_defined_symbols(tree))
        if is_test:
            check.misnamed_tests.extend(
                name for name in _top_level_test_names(tree)
                if not name.startswith("test_")
            )
    return check


def patch_faults(patch: list[PatchFile]) -> list[str]:
    """Why this patch cannot be accepted at all, as messages for the caller.

    Bounds only — the checks proper are in `check_scope`. Enforced before
    anything parses it, because the bounds exist to keep `ast.parse` inside the
    envelope it is safe in.
    """
    faults: list[str] = []
    if len(patch) > MAX_PATCH_FILES:
        faults.append(f"at most {MAX_PATCH_FILES} files")
    for entry in patch:
        if not _norm(entry.path):
            faults.append("every file needs a path")
            break
    for entry in patch:
        if len(entry.contents.encode("utf-8")) > MAX_PATCH_BYTES:
            faults.append(f"{entry.path or '?'} exceeds {MAX_PATCH_BYTES // 1024} KB")
    return faults


def advance(stage: Stage) -> Stage:
    """The next stage. `done` is terminal."""
    index = STAGE_ORDER.index(stage)
    return STAGE_ORDER[min(index + 1, len(STAGE_ORDER) - 1)]
