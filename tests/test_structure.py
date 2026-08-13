"""
Pytest tests for the Skeleton-backed candidate source (backend/repo/structure.py).
Run with: uv run pytest tests/test_structure.py -v

This exists because the Dossier's local neighbourhood empties out once the
Mentor has turned it into learning nodes — measured at 7 of 8 real confusion
events. What must hold: the widening is grounded (every candidate resolves),
structural (no similarity anywhere), and it never offers the confused code back.

No network, no model: a real temporary checkout and the deterministic index.
"""
from pathlib import Path

import pytest

from backend.repo import structure
from backend.repo.skeleton import build_skeleton

FILES = {
    "pkg/__init__.py": "from .facade import open_session as open_session\n",
    "pkg/base.py": (
        "class Transport:\n"
        "    def send(self, payload):\n"
        "        raise NotImplementedError\n"
    ),
    "pkg/wire.py": (
        "from .base import Transport\n"
        "from .util import encode\n"
        "\n\n"
        "class HttpTransport(Transport):\n"
        "    def send(self, payload):\n"
        "        return encode(payload)\n"
    ),
    "pkg/util.py": (
        "def encode(payload):\n"
        "    return repr(payload)\n"
        "\n\n"
        "def unused_helper():\n"
        "    return None\n"
    ),
    "pkg/facade.py": (
        "from .wire import HttpTransport\n"
        "\n\n"
        "def open_session():\n"
        "    return HttpTransport()\n"
    ),
}


@pytest.fixture
def repo(tmp_path: Path) -> str:
    for relative, body in FILES.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    build_skeleton.cache_clear()
    return str(tmp_path)


@pytest.fixture
def skeleton(repo):
    return build_skeleton(repo)


def _labels(candidates):
    return {(c.file, c.symbol) for c in candidates}


def _sources(candidates):
    return {c.source for c in candidates}


def test_a_base_class_is_offered_before_anything_else(skeleton):
    candidates = structure.neighbour_candidates(
        skeleton, "pkg/wire.py", symbol="HttpTransport"
    )
    assert candidates[0].source == "base_class"
    assert (candidates[0].file, candidates[0].symbol) == ("pkg/base.py", "Transport")


def test_what_the_code_calls_is_offered(skeleton):
    candidates = structure.neighbour_candidates(
        skeleton, "pkg/wire.py", symbol="HttpTransport.send"
    )
    assert ("pkg/util.py", "encode") in _labels(candidates)
    assert "calls" in _sources(candidates)


def test_a_same_named_symbol_the_file_never_imported_is_not_a_callee(tmp_path):
    """`.items()` matched unrelated classes' methods across the repository.

    A name from another module is only reachable if this file imported it, and
    without that filter the real callees were crowded out by attribute noise.
    """
    (tmp_path / "a.py").write_text(
        "def run(values):\n    return values.encode()\n", encoding="utf-8"
    )
    (tmp_path / "b.py").write_text("def encode(x):\n    return x\n", encoding="utf-8")
    build_skeleton.cache_clear()
    skeleton = build_skeleton(str(tmp_path))

    candidates = structure.neighbour_candidates(skeleton, "a.py", symbol="run")
    assert ("b.py", "encode") not in _labels(candidates)


def test_an_abstraction_that_depends_on_nothing_is_approached_through_a_user(skeleton):
    """`Transport` calls nothing, so the way in is something that extends it."""
    candidates = structure.neighbour_candidates(
        skeleton, "pkg/base.py", symbol="Transport",
        # its own method is excluded, leaving nothing local to offer
        exclude_symbols={("pkg/base.py", "Transport.send")},
    )
    assert ("pkg/wire.py", "HttpTransport") in _labels(candidates)
    assert "used_by" in _sources(candidates)


def test_the_confused_code_is_never_its_own_prerequisite(skeleton):
    candidates = structure.neighbour_candidates(
        skeleton, "pkg/util.py", symbol="encode"
    )
    assert ("pkg/util.py", "encode") not in _labels(candidates)


def test_taught_code_is_excluded_by_range_and_by_symbol(skeleton):
    plain = structure.neighbour_candidates(skeleton, "pkg/wire.py", symbol="HttpTransport")
    assert ("pkg/base.py", "Transport") in _labels(plain)

    by_symbol = structure.neighbour_candidates(
        skeleton, "pkg/wire.py", symbol="HttpTransport",
        exclude_symbols={("pkg/base.py", "Transport")},
    )
    assert ("pkg/base.py", "Transport") not in _labels(by_symbol)

    transport = skeleton.find_symbol("Transport", file="pkg/base.py")[0]
    by_range = structure.neighbour_candidates(
        skeleton, "pkg/wire.py", symbol="HttpTransport",
        exclude={(transport.file, transport.line_start, transport.line_end)},
    )
    assert ("pkg/base.py", "Transport") not in _labels(by_range)


def test_exclusion_does_not_discard_a_different_symbol_in_the_same_file(skeleton):
    """Coarse exclusion would empty the pool for no reason.

    `encode` and `unused_helper` share a file; teaching one must not hide the
    other. Identity is the symbol, not the file it lives in.
    """
    encode = skeleton.find_symbol("encode", file="pkg/util.py")[0]
    candidates = structure.neighbour_candidates(
        skeleton, "pkg/wire.py", symbol="HttpTransport.send",
        exclude={(encode.file, encode.line_start, encode.line_end)},
    )
    assert ("pkg/util.py", "encode") not in _labels(candidates)
    assert all(c.file != "pkg/util.py" or c.symbol != "encode" for c in candidates)


def test_every_candidate_resolves_against_the_repository(skeleton):
    from backend.repo import anchors

    for start in ("HttpTransport", "HttpTransport.send", "Transport", "open_session"):
        for candidate in structure.neighbour_candidates(
            skeleton, skeleton.find_symbol(start)[0].file, symbol=start
        ):
            assert anchors.resolve(
                skeleton, candidate.file, symbol=candidate.symbol
            ).ok, f"{candidate.file}:{candidate.symbol} does not resolve"


def test_an_unresolvable_anchor_yields_no_candidates(skeleton):
    assert structure.neighbour_candidates(skeleton, "pkg/nope.py", symbol="Ghost") == []
