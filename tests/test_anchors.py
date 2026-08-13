"""
Pytest tests for repository-backed anchor resolution (Stage 0).
Run with: uv run pytest tests/test_anchors.py -v

The central distinction under test is the one Stage 0 exists to create:

    resolve()          -> does this anchor REALLY EXIST in the repository?
    within_evidence()  -> was this code actually SHOWN to the agent?

Stage 0 improves the first while leaving the second exactly as strict.
"""
import pytest

from backend.repo import anchors
from backend.repo.skeleton import Skeleton


CHUNK_DICTS = [
    {"file": "src/requests/sessions.py", "start_line": 100, "end_line": 300,
     "type": "class", "name": "Session", "role": "source"},
    {"file": "src/requests/sessions.py", "start_line": 150, "end_line": 200,
     "type": "function", "name": "send", "role": "source"},
    {"file": "src/requests/auth.py", "start_line": 72, "end_line": 100,
     "type": "class", "name": "HTTPBasicAuth", "role": "source"},
    {"file": "src/requests/models.py", "start_line": 10, "end_line": 40,
     "type": "class", "name": "PreparedRequest", "role": "source"},
]


@pytest.fixture
def skeleton() -> Skeleton:
    # Explicit line counts so out-of-bounds rejection is testable.
    return Skeleton.from_chunks(
        CHUNK_DICTS,
        file_lines={
            "src/requests/sessions.py": 800,
            "src/requests/auth.py": 320,
            "src/requests/models.py": 1000,
        },
    )


# ── symbol -> exact range ─────────────────────────────────────────────────────


def test_symbol_resolves_to_exact_range(skeleton):
    res = anchors.resolve(skeleton, "src/requests/sessions.py", symbol="Session.send")
    assert res.ok
    assert (res.anchor.line_start, res.anchor.line_end) == (150, 200)
    assert res.anchor.symbol == "Session.send"
    assert res.anchor.kind == "symbol"


def test_qualified_method_symbol_beats_the_enclosing_class(skeleton):
    method = anchors.resolve(skeleton, "src/requests/sessions.py", symbol="Session.send")
    klass = anchors.resolve(skeleton, "src/requests/sessions.py", symbol="Session")
    assert (method.anchor.line_start, method.anchor.line_end) == (150, 200)
    assert (klass.anchor.line_start, klass.anchor.line_end) == (100, 300)


def test_symbol_overrides_supplied_line_numbers(skeleton):
    # The symbol IS the identity — this is what makes a hallucinated range
    # impossible when the caller emits a symbol.
    res = anchors.resolve(
        skeleton, "src/requests/sessions.py",
        symbol="Session.send", line_start=1, line_end=9999,
    )
    assert res.ok
    assert (res.anchor.line_start, res.anchor.line_end) == (150, 200)


def test_missing_symbol_is_rejected(skeleton):
    res = anchors.resolve(skeleton, "src/requests/sessions.py", symbol="Session.teleport")
    assert not res.ok
    assert res.reason == anchors.UNKNOWN_SYMBOL


def test_symbol_in_wrong_file_is_rejected(skeleton):
    res = anchors.resolve(skeleton, "src/requests/auth.py", symbol="Session.send")
    assert not res.ok
    assert res.reason == anchors.UNKNOWN_SYMBOL


# ── raw range validation ──────────────────────────────────────────────────────


def test_raw_range_resolves_and_records_enclosing_symbol(skeleton):
    res = anchors.resolve(
        skeleton, "src/requests/sessions.py", line_start=160, line_end=170
    )
    assert res.ok
    assert res.anchor.kind == "range"
    # Narrowest containing symbol becomes provenance.
    assert res.anchor.symbol == "Session.send"


def test_raw_range_matching_a_symbol_exactly_is_kind_symbol(skeleton):
    res = anchors.resolve(
        skeleton, "src/requests/sessions.py", line_start=150, line_end=200
    )
    assert res.ok
    assert res.anchor.kind == "symbol"
    assert res.anchor.symbol == "Session.send"


def test_non_symbol_range_is_allowed_with_no_symbol(skeleton):
    # A module-level region that no function or class covers — legal anchor,
    # simply without symbol provenance.
    res = anchors.resolve(
        skeleton, "src/requests/sessions.py", line_start=1, line_end=20
    )
    assert res.ok
    assert res.anchor.symbol is None
    assert res.anchor.kind == "range"


def test_range_beyond_end_of_file_is_rejected(skeleton):
    res = anchors.resolve(
        skeleton, "src/requests/auth.py", line_start=300, line_end=999
    )
    assert not res.ok
    assert res.reason == anchors.RANGE_OUT_OF_BOUNDS


def test_inverted_and_zero_ranges_are_rejected(skeleton):
    inverted = anchors.resolve(
        skeleton, "src/requests/auth.py", line_start=100, line_end=72
    )
    zero = anchors.resolve(
        skeleton, "src/requests/auth.py", line_start=0, line_end=10
    )
    assert inverted.reason == anchors.INVALID_RANGE
    assert zero.reason == anchors.INVALID_RANGE


def test_missing_range_and_symbol_is_rejected(skeleton):
    res = anchors.resolve(skeleton, "src/requests/auth.py")
    assert not res.ok
    assert res.reason == anchors.MISSING_RANGE


def test_unknown_file_is_rejected(skeleton):
    res = anchors.resolve(skeleton, "fake/file.py", line_start=1, line_end=9)
    assert not res.ok
    assert res.reason == anchors.UNKNOWN_FILE


def test_stripped_package_prefix_is_canonicalized(skeleton):
    # The false rejection Stage 0 exists to eliminate: a correct anchor written
    # with the package prefix dropped.
    res = anchors.resolve(skeleton, "requests/auth.py", line_start=72, line_end=100)
    assert res.ok
    assert res.anchor.file == "src/requests/auth.py"


def test_oversize_cap_is_opt_in(skeleton):
    span = dict(line_start=100, line_end=300)  # 201 lines
    assert anchors.resolve(skeleton, "src/requests/sessions.py", **span).ok
    capped = anchors.resolve(
        skeleton, "src/requests/sessions.py", max_lines=50, **span
    )
    assert not capped.ok
    assert capped.reason == anchors.RANGE_TOO_LARGE


# ── the Stage-0 evidence boundary ─────────────────────────────────────────────


def _evidence(*names: str) -> list[dict]:
    return [c for c in CHUNK_DICTS if c["name"] in names]


def test_anchor_inside_shown_evidence_passes(skeleton):
    res = anchors.resolve_within_evidence(
        skeleton, _evidence("send"), "src/requests/sessions.py",
        line_start=150, line_end=200,
    )
    assert res.ok


def test_sub_range_of_a_shown_chunk_passes(skeleton):
    # Narrowing within a chunk shown in full introduces no new content.
    res = anchors.resolve_within_evidence(
        skeleton, _evidence("send"), "src/requests/sessions.py",
        line_start=160, line_end=170,
    )
    assert res.ok


def test_real_symbol_outside_the_evidence_is_still_rejected(skeleton):
    """THE core Stage-0 invariant.

    models.py:10-40 is a genuine location — resolve() proves it. But it was not
    among the chunks the agent received, so it must not become curriculum.
    """
    direct = anchors.resolve(
        skeleton, "src/requests/models.py", line_start=10, line_end=40
    )
    assert direct.ok, "the anchor is real"

    gated = anchors.resolve_within_evidence(
        skeleton, _evidence("send"), "src/requests/models.py",
        line_start=10, line_end=40,
    )
    assert not gated.ok
    assert gated.reason == anchors.OUT_OF_EVIDENCE


def test_evidence_check_normalizes_chunk_paths(skeleton):
    windows_chunk = [{
        "file": "src\\requests\\auth.py", "start_line": 72, "end_line": 100,
        "type": "class", "name": "HTTPBasicAuth", "role": "source",
    }]
    res = anchors.resolve_within_evidence(
        skeleton, windows_chunk, "requests/auth.py", line_start=72, line_end=100
    )
    assert res.ok
    assert res.anchor.file == "src/requests/auth.py"
