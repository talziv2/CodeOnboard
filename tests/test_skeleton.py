"""
Pytest tests for the deterministic repository skeleton (Stage 0, Layer A).
Run with: uv run pytest tests/test_skeleton.py -v
"""
from pathlib import Path

import pytest

from backend.repo.skeleton import (
    Skeleton,
    build_skeleton,
    normalize_path,
)


# Chunker-shaped fixtures. Deliberately written with Windows separators in one
# place so the normalisation contract is exercised rather than assumed.
FAKE_CHUNKS = [
    {"file": "src\\requests\\sessions.py", "start_line": 100, "end_line": 300,
     "type": "class", "name": "Session", "role": "source", "content": "class Session: ..."},
    {"file": "src\\requests\\sessions.py", "start_line": 150, "end_line": 200,
     "type": "function", "name": "send", "role": "source", "content": "def send(): ..."},
    {"file": "src\\requests\\sessions.py", "start_line": 210, "end_line": 240,
     "type": "function", "name": "request", "role": "source", "content": "def request(): ..."},
    {"file": "src/requests/api.py", "start_line": 10, "end_line": 30,
     "type": "function", "name": "get", "role": "source", "content": "def get(): ..."},
    {"file": "src/requests/api.py", "start_line": 1, "end_line": 1,
     "type": "import", "name": "import x", "role": "source", "content": "import x"},
    {"file": "tests/test_api.py", "start_line": 5, "end_line": 12,
     "type": "function", "name": "test_get", "role": "test", "content": "def test_get(): ..."},
]


@pytest.fixture
def skeleton() -> Skeleton:
    return Skeleton.from_chunks(FAKE_CHUNKS)


# ── path normalisation ────────────────────────────────────────────────────────


def test_normalize_path_folds_separators():
    assert normalize_path("src\\requests\\api.py") == "src/requests/api.py"
    assert normalize_path("src/requests/api.py") == "src/requests/api.py"


def test_skeleton_stores_only_normalized_paths(skeleton):
    assert all("\\" not in p for p in skeleton.files)
    assert "src/requests/sessions.py" in skeleton.files


# ── symbol index ──────────────────────────────────────────────────────────────


def test_methods_get_qualified_names(skeleton):
    send = skeleton.find_symbol("Session.send", file="src/requests/sessions.py")
    assert len(send) == 1
    assert send[0].parent == "Session"
    assert (send[0].line_start, send[0].line_end) == (150, 200)


def test_module_level_function_has_no_parent(skeleton):
    get = skeleton.find_symbol("get", file="src/requests/api.py")
    assert len(get) == 1
    assert get[0].parent is None
    assert get[0].qualified_name == "get"


def test_imports_are_not_symbols(skeleton):
    assert skeleton.find_symbol("import x") == []
    # ...but the file is still indexed.
    assert "src/requests/api.py" in skeleton.files


def test_roles_are_carried_through(skeleton):
    assert skeleton.files["tests/test_api.py"].role == "test"
    assert skeleton.files["src/requests/api.py"].role == "source"


def test_bare_name_lookup_finds_qualified_symbol(skeleton):
    # "send" alone should still resolve inside the file that defines it.
    found = skeleton.find_symbol("send", file="src/requests/sessions.py")
    assert len(found) == 1
    assert found[0].qualified_name == "Session.send"


# ── file resolution ───────────────────────────────────────────────────────────


def test_canonical_file_exact_match(skeleton):
    assert skeleton.canonical_file("src/requests/api.py") == "src/requests/api.py"


def test_canonical_file_recovers_stripped_package_prefix(skeleton):
    # The classic LLM failure: it wrote "requests/api.py" for "src/requests/api.py".
    assert skeleton.canonical_file("requests/api.py") == "src/requests/api.py"


def test_canonical_file_rejects_unknown(skeleton):
    assert skeleton.canonical_file("does/not/exist.py") is None


def test_canonical_file_rejects_ambiguous_suffix():
    ambiguous = Skeleton.from_chunks([
        {"file": "a/utils.py", "start_line": 1, "end_line": 5,
         "type": "function", "name": "f", "role": "source"},
        {"file": "b/utils.py", "start_line": 1, "end_line": 5,
         "type": "function", "name": "g", "role": "source"},
    ])
    # Two files end with "utils.py" — a guess would be worse than a rejection.
    assert ambiguous.canonical_file("utils.py") is None


# ── range containment ─────────────────────────────────────────────────────────


def test_exact_symbol_match(skeleton):
    sym = skeleton.exact_symbol("src/requests/sessions.py", 150, 200)
    assert sym is not None and sym.qualified_name == "Session.send"


def test_enclosing_symbol_prefers_the_narrowest(skeleton):
    # 160-170 sits inside both Session (100-300) and Session.send (150-200).
    sym = skeleton.enclosing_symbol("src/requests/sessions.py", 160, 170)
    assert sym is not None and sym.qualified_name == "Session.send"


def test_enclosing_symbol_none_outside_any_symbol(skeleton):
    assert skeleton.enclosing_symbol("src/requests/sessions.py", 1, 3) is None


# ── subsystem inventory (OQ7 provisional rule) ────────────────────────────────


def test_source_root_detected():
    sk = Skeleton.from_chunks(FAKE_CHUNKS)
    assert sk.source_root() == "src/requests"


def test_flat_package_does_not_collapse_to_one_subsystem(skeleton):
    # Root-level modules become one subsystem each, so a flat library still
    # yields a contract with real granularity.
    subs = skeleton.subsystems()
    assert "sessions.py" in subs
    assert "api.py" in subs
    assert len(subs) == 2


def test_subsystems_exclude_non_source_roles(skeleton):
    subs = skeleton.subsystems()
    assert not any("test_api.py" in name for name in subs)


# ── real-repo regression guards ───────────────────────────────────────────────
#
# These need the demo clones present. They encode the P2 defect (the 80-chunk
# alphabetical module map silently dropped fastapi/security/) as a permanent
# guard on the deterministic inventory.

REQUESTS = Path("data/repos/requests")
FASTAPI = Path("data/repos/fastapi")

requires_requests = pytest.mark.skipif(
    not REQUESTS.exists(), reason="data/repos/requests not cloned"
)
requires_fastapi = pytest.mark.skipif(
    not FASTAPI.exists(), reason="data/repos/fastapi not cloned"
)


@requires_fastapi
def test_fastapi_security_is_an_independently_visible_subsystem():
    """The OQ7 regression criterion.

    If `security` cannot be seen on its own, the granularity is too coarse and
    the coverage contract (D13) would be unable to notice it disappearing.
    """
    subs = build_skeleton(str(FASTAPI)).subsystems()
    assert "security" in subs, sorted(subs)
    assert len(subs["security"]) >= 5
    # The other subpackages the provisional rule was chosen to expose.
    for name in ("dependencies", "middleware", "openapi"):
        assert name in subs, sorted(subs)


@requires_fastapi
def test_fastapi_inventory_is_intermediate_granularity():
    # Neither 1 (vacuous) nor ~45 (one per source file, too noisy).
    subs = build_skeleton(str(FASTAPI)).subsystems()
    assert 10 <= len(subs) <= 30, len(subs)


@requires_fastapi
def test_fastapi_routing_cannot_hide_in_a_catch_all_bucket():
    subs = build_skeleton(str(FASTAPI)).subsystems()
    flattened = {f for files in subs.values() for f in files}
    assert any(f.endswith("fastapi/routing.py") for f in flattened)


@requires_requests
def test_requests_symbols_resolve_against_the_real_checkout():
    sk = build_skeleton(str(REQUESTS))
    session_send = sk.find_symbol("Session.send")
    assert session_send, "Session.send should exist in psf/requests"
    sym = session_send[0]
    assert sym.file.endswith("requests/sessions.py")
    assert sym.line_start < sym.line_end
    # The recorded range must match the real file.
    source = sk.read_lines(sym.file, sym.line_start, sym.line_end)
    assert source is not None
    assert source.lstrip().startswith("def send")


def test_normalize_path_preserves_dotted_directories():
    # str.lstrip("./") would corrupt this into "github/workflows/x.py", and the
    # anchor would then fail to resolve against a file that really exists.
    assert normalize_path(".github/workflows/x.py") == ".github/workflows/x.py"
    assert normalize_path("./src/a.py") == "src/a.py"
    assert normalize_path(r".\src\a.py") == "src/a.py"
