"""
Pytest tests for the repository tool layer (Stage 1, backend/repo/tools.py).
Run with: uv run pytest tests/test_tools.py -v

The tools are the deterministic surface an explorer reasons through, so the
properties under test are the ones a caller has to be able to trust without
reading the implementation: results are facts from the checkout, output is
bounded and says when it was truncated, paths cannot escape the repository, and
a failure is a result rather than an exception.
"""
import textwrap
from pathlib import Path

import pytest

from backend.repo import tools
from backend.repo.skeleton import build_skeleton


# ── a real, tiny checkout ─────────────────────────────────────────────────────
#
# Written to disk rather than mocked: every tool reads files, and a fake
# skeleton would not exercise the path handling that is most of the risk here.

SESSIONS = '''\
"""Session handling."""
import os

from .auth import HTTPBasicAuth
from .models import Request


class Session(Base):
    """Holds connection state."""

    def __init__(self):
        self.adapters = {}

    def send(self, request):
        """Dispatch a prepared request."""
        adapter = self.get_adapter(request.url)
        return adapter.send(request)

    def get_adapter(self, url):
        return self.adapters[url]


def session():
    return Session()
'''

AUTH = '''\
"""Authentication helpers."""


class HTTPBasicAuth:
    def __init__(self, username, password):
        self.username = username

    def __call__(self, request):
        return request
'''

MODELS = '''\
class Base:
    pass


class Request:
    def prepare(self):
        raise NotImplementedError("prepare")
'''

TEST_FILE = '''\
from src.pkg.sessions import Session


def test_send():
    assert Session() is not None
'''


@pytest.fixture
def repo(tmp_path: Path) -> str:
    pkg = tmp_path / "src" / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "sessions.py").write_text(SESSIONS, encoding="utf-8")
    (pkg / "auth.py").write_text(AUTH, encoding="utf-8")
    (pkg / "models.py").write_text(MODELS, encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_sessions.py").write_text(TEST_FILE, encoding="utf-8")
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    build_skeleton.cache_clear()
    return str(tmp_path)


@pytest.fixture
def big_repo(tmp_path: Path) -> str:
    """A file long enough to trip the outline threshold."""
    pkg = tmp_path / "pkg"
    pkg.mkdir(parents=True)
    body = ["def head():", "    return 1", ""]
    for i in range(tools.OUTLINE_THRESHOLD // 2):
        body += [f"def fn_{i}():", f"    return {i}", ""]
    (pkg / "big.py").write_text("\n".join(body), encoding="utf-8")
    build_skeleton.cache_clear()
    return str(tmp_path)


# ── list_files ────────────────────────────────────────────────────────────────


def test_list_files_returns_layer_a_metadata(repo):
    result = tools.list_files(repo)
    assert result["ok"]
    by_path = {f["path"]: f for f in result["files"]}
    assert by_path["src/pkg/sessions.py"]["role"] == "source"
    assert by_path["src/pkg/sessions.py"]["loc"] > 0
    assert by_path["src/pkg/sessions.py"]["symbol_count"] >= 4


def test_list_files_filters_by_role(repo):
    result = tools.list_files(repo, role="test")
    assert [f["path"] for f in result["files"]] == ["tests/test_sessions.py"]


def test_list_files_sees_unindexed_files(repo):
    # The skeleton only indexes Python; exploration still needs to know a README
    # exists, with None metadata rather than a fabricated zero.
    result = tools.list_files(repo, glob="*.md")
    assert [f["path"] for f in result["files"]] == ["README.md"]
    assert result["files"][0]["loc"] is None


def test_list_files_reports_truncation(repo):
    result = tools.list_files(repo, limit=1)
    assert len(result["files"]) == 1
    assert result["total"] > 1
    assert result["truncated"] is True


def test_list_files_skips_noise_directories(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("def f(): pass\n", encoding="utf-8")
    cache = tmp_path / "pkg" / "__pycache__"
    cache.mkdir()
    (cache / "a.cpython-311.pyc").write_text("junk", encoding="utf-8")
    build_skeleton.cache_clear()
    result = tools.list_files(str(tmp_path), glob="**/*")
    assert not any("__pycache__" in f["path"] for f in result["files"])


# ── read_file ─────────────────────────────────────────────────────────────────


def test_read_file_numbers_every_line(repo):
    result = tools.read_file(repo, "src/pkg/auth.py")
    assert result["ok"]
    first = result["content"].splitlines()[0]
    assert first.strip().startswith("1|")


def test_read_file_range_is_inclusive(repo):
    result = tools.read_file(repo, "src/pkg/models.py", start=1, end=2)
    assert [line.split("| ", 1)[1] for line in result["content"].splitlines()] == [
        "class Base:", "    pass",
    ]
    assert result["truncated"] is True


def test_read_file_recovers_a_stripped_prefix(repo):
    # The path the resolver has to tolerate: a caller that wrote "pkg/auth.py"
    # for "src/pkg/auth.py".
    result = tools.read_file(repo, "pkg/auth.py")
    assert result["ok"]
    assert result["path"] == "src/pkg/auth.py"


def test_read_file_rejects_a_range_over_the_cap(big_repo):
    result = tools.read_file(big_repo, "pkg/big.py", start=1, end=tools.MAX_READ_LINES + 2)
    assert not result["ok"]
    assert result["error"] == "range_too_large"


def test_read_file_clamps_an_overlong_range_to_the_file(repo):
    # Asking past the end of a short file is not an error: the range is clamped
    # to what exists, so the cap applies to lines actually returned.
    result = tools.read_file(repo, "src/pkg/sessions.py", start=1, end=tools.MAX_READ_LINES)
    assert result["ok"]
    assert result["end"] == result["total_lines"]


def test_read_file_rejects_an_inverted_range(repo):
    result = tools.read_file(repo, "src/pkg/auth.py", start=9, end=2)
    assert result["error"] == "invalid_range"


def test_read_file_rejects_a_start_past_end_of_file(repo):
    result = tools.read_file(repo, "src/pkg/auth.py", start=9000, end=9001)
    assert result["error"] == "invalid_range"


def test_read_file_returns_an_outline_for_a_long_file(big_repo):
    result = tools.read_file(big_repo, "pkg/big.py")
    assert result["ok"]
    assert result["content"] is None
    assert result["truncated"] is True
    assert result["outline"][0]["name"] == "head"
    assert "start/end" in result["hint"]


def test_read_file_still_reads_a_range_of_a_long_file(big_repo):
    result = tools.read_file(big_repo, "pkg/big.py", start=1, end=3)
    assert result["ok"] and result["content"] is not None


def test_read_file_reports_a_missing_file(repo):
    assert tools.read_file(repo, "src/pkg/nope.py")["error"] == "not_found"


# ── path containment ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "escape",
    ["../outside.py", "../../etc/passwd", "/etc/passwd", "C:/Windows/win.ini",
     "src/../../outside.py", ""],
)
def test_read_file_refuses_to_leave_the_repository(repo, escape, tmp_path):
    (tmp_path.parent / "outside.py").write_text("secret = 1\n", encoding="utf-8")
    result = tools.read_file(repo, escape)
    assert not result["ok"]
    assert result["error"] in ("invalid_path", "not_found")


# ── search_code ───────────────────────────────────────────────────────────────


def test_search_code_finds_a_literal(repo):
    result = tools.search_code(repo, r"get_adapter")
    assert result["ok"]
    assert result["total"] >= 2
    assert all(m["line"] > 0 for m in result["matches"])
    assert any(m["path"] == "src/pkg/sessions.py" for m in result["matches"])


def test_search_code_honours_a_glob(repo):
    result = tools.search_code(repo, r"Session", glob="tests/*.py")
    assert {m["path"] for m in result["matches"]} == {"tests/test_sessions.py"}


def test_search_code_is_case_sensitive_by_default(repo):
    assert tools.search_code(repo, r"httpbasicauth")["total"] == 0
    assert tools.search_code(repo, r"httpbasicauth", ignore_case=True)["total"] > 0


def test_search_code_reports_totals_beyond_the_result_cap(repo):
    result = tools.search_code(repo, r"e", max_results=2)
    assert len(result["matches"]) == 2
    assert result["total"] > 2
    assert result["truncated"] is True


def test_search_code_rejects_a_bad_pattern(repo):
    assert tools.search_code(repo, r"(unclosed")["error"] == "invalid_pattern"
    assert tools.search_code(repo, "")["error"] == "invalid_pattern"


def test_search_code_skips_binary_files(repo):
    Path(repo, "blob.bin").write_bytes(b"\x00\x01needle\x00")
    result = tools.search_code(repo, "needle")
    assert result["ok"]
    assert not any(m["path"] == "blob.bin" for m in result["matches"])


def test_search_code_truncates_a_very_long_line(repo):
    Path(repo, "long.py").write_text("x = '" + "a" * 5000 + "'\n", encoding="utf-8")
    result = tools.search_code(repo, "aaaa")
    assert all(len(m["text"]) <= tools.MAX_MATCH_CHARS for m in result["matches"])


# ── symbols ───────────────────────────────────────────────────────────────────


def test_symbols_outlines_a_file(repo):
    result = tools.symbols(repo, path="src/pkg/sessions.py")
    assert result["ok"]
    names = [s["qualified_name"] for s in result["symbols"]]
    assert "Session" in names
    assert "Session.send" in names          # methods are qualified
    assert "session" in names               # module-level function survives


def test_symbols_ranges_come_from_the_parse(repo):
    send = next(
        s for s in tools.symbols(repo, name="Session.send")["symbols"]
        if s["qualified_name"] == "Session.send"
    )
    body = tools.read_file(
        repo, send["file"], start=send["line_start"], end=send["line_end"]
    )["content"]
    assert "def send" in body.splitlines()[0]


def test_symbols_filters_by_kind(repo):
    result = tools.symbols(repo, path="src/pkg/models.py", kind="class")
    assert {s["qualified_name"] for s in result["symbols"]} == {"Base", "Request"}


def test_symbols_rejects_an_unindexed_path(repo):
    assert tools.symbols(repo, path="README.md")["error"] == "not_found"


def test_symbols_ordering_is_stable(repo):
    first = tools.symbols(repo)
    second = tools.symbols(repo)
    assert first["symbols"] == second["symbols"]


# ── neighbors ─────────────────────────────────────────────────────────────────


def test_neighbors_lists_the_methods_a_class_defines(repo):
    result = tools.neighbors(repo, "Session", relations=["defines"])
    assert result["ok"]
    defined = {n["symbol"] for n in result["neighbors"]}
    assert {"Session.send", "Session.get_adapter", "Session.__init__"} <= defined


def test_neighbors_finds_the_enclosing_class(repo):
    result = tools.neighbors(repo, "Session.send", relations=["defined_in"])
    assert [n["symbol"] for n in result["neighbors"]] == ["Session"]


def test_neighbors_resolves_a_base_class(repo):
    result = tools.neighbors(repo, "Session", relations=["extends"])
    bases = {n["symbol"] for n in result["neighbors"]}
    assert "Base" in bases
    resolved = next(n for n in result["neighbors"] if n["symbol"] == "Base")
    assert resolved["file"] == "src/pkg/models.py"


def test_neighbors_separates_in_repo_imports_from_external(repo):
    result = tools.neighbors(repo, "Session", relations=["imports"])
    by_module = {n["module"]: n for n in result["neighbors"]}
    assert by_module["os"]["in_repo"] is False
    assert by_module["auth"]["in_repo"] is True
    assert by_module["auth"]["file"] == "src/pkg/auth.py"


def test_neighbors_finds_importers(repo):
    result = tools.neighbors(repo, "HTTPBasicAuth", relations=["imported_by"])
    assert "src/pkg/sessions.py" in {n["file"] for n in result["neighbors"]}


def test_neighbors_marks_references_as_approximate(repo):
    result = tools.neighbors(repo, "Session", relations=["references"])
    refs = [n for n in result["neighbors"] if n["relation"] == "references"]
    assert refs, "the test file references Session"
    assert all(n["exact"] is False for n in refs)


def test_neighbors_relations_other_than_references_are_exact(repo):
    result = tools.neighbors(repo, "Session", relations=["defines", "imports"])
    assert all(n["exact"] is True for n in result["neighbors"])


def test_neighbors_reports_one_edge_per_imported_module(repo):
    # sessions.py has two `from . import` statements plus `import os`; a module
    # imported by several statements is still one dependency edge.
    Path(repo, "src", "pkg", "sessions.py").write_text(
        "from .auth import HTTPBasicAuth\n"
        "from .auth import something_else\n"
        "from .models import Base\n"
        "class Session(Base):\n"
        "    def send(self):\n"
        "        return 1\n",
        encoding="utf-8",
    )
    build_skeleton.cache_clear()
    result = tools.neighbors(repo, "Session", relations=["imports"])
    modules = [n["module"] for n in result["neighbors"]]
    assert modules.count("auth") == 1, modules


def test_neighbors_does_not_let_one_relation_starve_the_others(tmp_path):
    # A file with many imports and one reference: a plain prefix cut would return
    # imports only, which is useless to a caller tracing a flow.
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    imports = "\n".join(f"import mod_{i}" for i in range(30))
    (pkg / "core.py").write_text(
        f"{imports}\n\n\nclass Core:\n    def run(self):\n        return 1\n",
        encoding="utf-8",
    )
    (pkg / "user.py").write_text("from .core import Core\n\nCore().run()\n", encoding="utf-8")
    build_skeleton.cache_clear()

    result = tools.neighbors(str(tmp_path), "Core", limit=8)
    relations = {n["relation"] for n in result["neighbors"]}
    assert len(result["neighbors"]) == 8
    assert result["truncated"] is True
    assert "imports" in relations
    assert "defines" in relations
    assert "references" in relations, relations


def test_neighbors_fair_share_keeps_relations_grouped(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    imports = "\n".join(f"import mod_{i}" for i in range(10))
    (pkg / "core.py").write_text(
        f"{imports}\n\n\nclass Core:\n"
        + "".join(f"    def m{i}(self):\n        return {i}\n" for i in range(6)),
        encoding="utf-8",
    )
    build_skeleton.cache_clear()
    result = tools.neighbors(str(tmp_path), "Core", limit=6)
    seen = [n["relation"] for n in result["neighbors"]]
    assert seen == sorted(seen, key=lambda r: tools.RELATIONS.index(r))


def test_neighbors_carries_a_resolved_anchor(repo):
    result = tools.neighbors(repo, "Session.send")
    anchor = result["anchor"]
    assert anchor["file"] == "src/pkg/sessions.py"
    assert anchor["line_start"] < anchor["line_end"]


def test_neighbors_returns_both_definitions_of_an_ambiguous_symbol(tmp_path):
    """A repeated name is a fact about the code, not a caller mistake.

    The factory-beside-its-class pattern (`Depends()` next to `class Depends`,
    `field()` next to `Field`) is exactly the indirection a learner needs, so
    the tool hands back both definitions instead of refusing. Measured cost of
    refusing: the caller picked the implementation blind and never learned that
    the name its users import is the other one.
    """
    (tmp_path / "a.py").write_text("def helper(): pass\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("class helper: pass\n", encoding="utf-8")
    build_skeleton.cache_clear()

    result = tools.neighbors(str(tmp_path), "helper")
    assert result["ok"] and result["ambiguous"]
    assert result["neighbors"] == []      # no relations until one is chosen
    assert {(c["file"], c["kind"]) for c in result["candidates"]} == {
        ("a.py", "function"), ("b.py", "class"),
    }
    # ...and choosing one still works exactly as before.
    assert tools.neighbors(str(tmp_path), "helper", file="a.py")["ok"]
    assert "anchor" in tools.neighbors(str(tmp_path), "helper", file="a.py")


def test_exported_by_reports_the_dotted_path_a_caller_types(tmp_path):
    """The one form of "public API" Python states structurally, not by convention.

    A package `__init__` re-exporting a name is checkable; docs and changelogs
    are not. This is the edge that tells a public factory from the internal type
    of the same name sitting beside it.
    """
    pkg = tmp_path / "app"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        "from .factory import make as make\n", encoding="utf-8"
    )
    (pkg / "factory.py").write_text("def make():\n    return Thing()\n", encoding="utf-8")
    (pkg / "core.py").write_text("class make:\n    pass\n", encoding="utf-8")
    build_skeleton.cache_clear()

    public = tools.neighbors(str(tmp_path), "make", file="app/factory.py",
                             relations=["exported_by"])
    assert [n["import_path"] for n in public["neighbors"]] == ["app.make"]

    # The same-named internal definition is NOT what callers reach.
    internal = tools.neighbors(str(tmp_path), "make", file="app/core.py",
                               relations=["exported_by"])
    assert internal["neighbors"] == []


def test_neighbors_reports_an_unknown_symbol(repo):
    assert tools.neighbors(repo, "Teleporter")["error"] == "unknown_symbol"


def test_neighbors_rejects_an_unknown_relation(repo):
    result = tools.neighbors(repo, "Session", relations=["calls"])
    assert result["error"] == "unknown_relation"


# ── propose_anchor ────────────────────────────────────────────────────────────


def test_propose_anchor_resolves_a_symbol_to_a_range(repo):
    result = tools.propose_anchor(repo, "src/pkg/sessions.py", symbol="Session.send")
    assert result["ok"]
    assert result["symbol"] == "Session.send"
    assert result["kind"] == "symbol"
    assert result["line_start"] < result["line_end"]


def test_propose_anchor_verifies_a_raw_range(repo):
    result = tools.propose_anchor(repo, "src/pkg/sessions.py", line_start=1, line_end=3)
    assert result["ok"]


def test_propose_anchor_rejects_the_unreal(repo):
    assert not tools.propose_anchor(repo, "src/pkg/teleport.py", symbol="x")["ok"]
    assert not tools.propose_anchor(repo, "src/pkg/sessions.py", symbol="Session.teleport")["ok"]
    assert not tools.propose_anchor(
        repo, "src/pkg/sessions.py", line_start=9000, line_end=9001
    )["ok"]


def test_propose_anchor_does_not_gate_on_evidence(repo):
    # The Stage-0 evidence gate lives with the agents, not in the tool layer:
    # this verifies a range the caller was never "shown".
    assert tools.propose_anchor(repo, "src/pkg/models.py", symbol="Request.prepare")["ok"]


# ── dispatch ──────────────────────────────────────────────────────────────────


def test_run_tool_dispatches_every_declared_tool(repo):
    assert set(tools.TOOLS) == {
        "list_files", "read_file", "search_code", "symbols", "neighbors",
        "propose_anchor",
    }
    assert tools.run_tool("symbols", repo, path="src/pkg/auth.py")["ok"]


def test_run_tool_turns_an_unknown_name_into_a_result(repo):
    result = tools.run_tool("semantic_search", repo, query="auth")
    assert result["error"] == "unknown_tool"


def test_run_tool_turns_bad_arguments_into_a_result(repo):
    result = tools.run_tool("read_file", repo, filepath="src/pkg/auth.py")
    assert result["error"] == "bad_arguments"


def test_run_tool_turns_a_crash_into_a_result(repo, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("tree-sitter exploded")

    monkeypatch.setitem(tools.TOOLS, "symbols", boom)
    result = tools.run_tool("symbols", repo)
    assert result["error"] == "tool_failed"
    assert "RuntimeError" in result["detail"]


def test_every_result_carries_the_ok_flag(repo):
    calls = [
        ("list_files", {}),
        ("read_file", {"path": "src/pkg/auth.py"}),
        ("search_code", {"pattern": "class"}),
        ("symbols", {"path": "src/pkg/auth.py"}),
        ("neighbors", {"symbol": "HTTPBasicAuth"}),
        ("propose_anchor", {"file": "src/pkg/auth.py", "symbol": "HTTPBasicAuth"}),
    ]
    for name, kwargs in calls:
        result = tools.run_tool(name, repo, **kwargs)
        assert result["ok"] is True, (name, result)


def test_output_caps_are_enforced_not_merely_documented(repo):
    # Every ceiling in the module clamps rather than trusting the caller, so an
    # explorer cannot flood its own context by asking for more.
    assert len(tools.list_files(repo, limit=10_000)["files"]) <= tools.MAX_FILE_RESULTS
    assert len(tools.search_code(repo, "e", max_results=10_000)["matches"]) <= tools.MAX_SEARCH_RESULTS
    assert len(tools.symbols(repo, limit=10_000)["symbols"]) <= tools.MAX_SYMBOL_RESULTS
    assert len(
        tools.neighbors(repo, "Session", limit=10_000)["neighbors"]
    ) <= tools.MAX_NEIGHBOR_RESULTS


# ── real-repo guard ───────────────────────────────────────────────────────────

REQUESTS = Path("data/repos/requests")


@pytest.mark.skipif(not REQUESTS.exists(), reason="data/repos/requests not cloned")
def test_tools_work_on_the_demo_repo():
    repo = str(REQUESTS)
    sk = build_skeleton(repo)
    outline = tools.symbols(repo, name="Session.send", skeleton=sk)
    assert outline["ok"] and outline["total"] >= 1
    target = outline["symbols"][0]
    body = tools.read_file(
        repo, target["file"], start=target["line_start"],
        end=min(target["line_end"], target["line_start"] + 20), skeleton=sk,
    )
    assert "def send" in body["content"]
    hood = tools.neighbors(repo, "Session.send", file=target["file"], skeleton=sk)
    assert hood["ok"] and hood["total"] > 0


def test_run_tool_accepts_a_tool_argument_named_name(repo):
    """`symbols(name=...)` must reach the tool, not collide with the dispatcher.

    Regression: `run_tool(name, repo_path, **kwargs)` bound `name` twice when the
    model called `symbols` by symbol name — the keystone tool's primary lookup
    mode — and the TypeError killed the whole investigation.
    """
    result = tools.run_tool("symbols", repo, name="Session.send")
    assert result["ok"], result
    assert result["symbols"][0]["qualified_name"] == "Session.send"


def test_run_tool_ignores_a_model_supplied_repo_path(repo):
    """The checkout is injected; a model that sends one must not redirect it."""
    result = tools.run_tool("symbols", repo, path="src/pkg/auth.py",
                            repo_path="/etc")
    assert result["ok"]
    assert all(s["file"].startswith("src/pkg/") for s in result["symbols"])
