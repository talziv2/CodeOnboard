"""
Pytest tests for the calibration harness's resume contract.
Run with: uv run pytest tests/test_calibration_harness.py -v

No API calls: `run_cell` is stubbed. What must hold is the property that cost
real money to discover — a partial rerun must never destroy completed evidence,
and a resumed run must not re-pay for cells already recorded.

The harness lives in scripts/ rather than in a package, so it is loaded by path.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent


def load_harness():
    spec = importlib.util.spec_from_file_location(
        "calibrate_bands", ROOT / "scripts" / "calibrate_bands.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


harness = load_harness()


def cell(name: str, repeats: int = 3, ok: bool = True) -> dict:
    return {
        "cell": name,
        "code_depth": name.split("-")[1],
        "ok": ok,
        "band": [5, 14],
        "investigate_seconds": 100.0,
        "runs": [
            {"repeat": i + 1, "ok": True, "seconds": 10.0, "proposed": 12,
             "grounding_drops": 0, "core_before_band": 9, "journey": 11,
             "optional": 1, "band_bound": None, "demoted_by_band": 0,
             "areas": 4, "kinds": {"flow": 2}, "covers_goal": True,
             "confidence": "high"}
            for i in range(repeats)
        ],
        "spread": {},
    }


@pytest.fixture(autouse=True)
def _contain_the_flag(monkeypatch):
    """`main()` sets CODEONBOARD_CURRICULUM with a raw assignment.

    Without this the flag leaks out of these tests and into every later one in
    the same process — which is how running the harness tests turned fourteen
    unrelated planner tests red. monkeypatch restores whatever was there before,
    whoever changed it in between.
    """
    monkeypatch.setenv("CODEONBOARD_CURRICULUM", "0")


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    """A calibration file holding four completed cells."""
    out = tmp_path / "evidence"
    out.mkdir()
    done = [cell(n) for n in (
        "requests-map", "requests-working", "requests-implementation", "fastapi-map",
    )]
    (out / "band-calibration.json").write_text(json.dumps(done, indent=2), encoding="utf-8")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    return out


def run_main(argv: list[str]) -> int:
    old = sys.argv
    sys.argv = ["calibrate_bands.py", *argv]
    try:
        return harness.main()
    finally:
        sys.argv = old


# ── the guard ─────────────────────────────────────────────────────────────────

def test_a_partial_rerun_without_resume_refuses_rather_than_overwrites(
    evidence, monkeypatch, capsys
):
    # The defect that would have destroyed three paid-for cells.
    called = []
    monkeypatch.setattr(harness, "run_cell", lambda *a, **k: called.append(a) or cell("x"))

    code = run_main(["--only", "fastapi-working", "--out", str(evidence)])

    assert code == 3
    assert called == []          # nothing ran
    kept = json.loads((evidence / "band-calibration.json").read_text(encoding="utf-8"))
    assert len(kept) == 4        # nothing lost


def test_the_guard_names_what_it_is_protecting(evidence, capsys):
    run_main(["--only", "fastapi-working", "--out", str(evidence)])
    err = capsys.readouterr().err
    assert "requests-map" in err and "--resume" in err


def test_a_fresh_matrix_in_an_empty_directory_is_allowed(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(harness, "run_cell",
                        lambda name, *a, **k: cell(name))
    code = run_main(["--only", "requests-map", "--out", str(tmp_path / "new")])
    assert code == 0


# ── resume ────────────────────────────────────────────────────────────────────

def test_resume_runs_only_what_is_missing(evidence, monkeypatch):
    ran: list[str] = []

    def fake(name, repo_url, depth, repeats, client, previous=None):
        ran.append(name)
        return cell(name)

    monkeypatch.setattr(harness, "run_cell", fake)
    run_main(["--resume", "--out", str(evidence)])

    assert ran == ["fastapi-working", "fastapi-implementation"]


def test_resume_writes_the_whole_matrix_not_a_fragment(evidence, monkeypatch):
    monkeypatch.setattr(harness, "run_cell",
                        lambda name, *a, **k: cell(name))
    run_main(["--resume", "--out", str(evidence)])

    written = json.loads((evidence / "band-calibration.json").read_text(encoding="utf-8"))
    assert [c["cell"] for c in written] == [
        "requests-map", "requests-working", "requests-implementation",
        "fastapi-map", "fastapi-working", "fastapi-implementation",
    ]


def test_completed_cells_survive_a_resume_byte_for_byte(evidence, monkeypatch):
    before = {
        c["cell"]: c
        for c in json.loads((evidence / "band-calibration.json").read_text(encoding="utf-8"))
    }
    monkeypatch.setattr(harness, "run_cell", lambda name, *a, **k: cell(name))
    run_main(["--resume", "--out", str(evidence)])

    after = {
        c["cell"]: c
        for c in json.loads((evidence / "band-calibration.json").read_text(encoding="utf-8"))
    }
    for name, original in before.items():
        assert after[name] == original


def test_a_cell_with_too_few_good_repeats_is_not_treated_as_done(evidence, monkeypatch):
    path = evidence / "band-calibration.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data[0]["runs"] = data[0]["runs"][:1]      # only one good repeat
    path.write_text(json.dumps(data), encoding="utf-8")

    ran: list[str] = []
    monkeypatch.setattr(harness, "run_cell",
                        lambda name, *a, **k: ran.append(name) or cell(name))
    run_main(["--resume", "--out", str(evidence)])

    assert "requests-map" in ran


def test_a_died_cell_is_retried_on_resume(evidence, monkeypatch):
    path = evidence / "band-calibration.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data[3] = {"cell": "fastapi-map", "ok": False, "died": "no dossier"}
    path.write_text(json.dumps(data), encoding="utf-8")

    ran: list[str] = []
    monkeypatch.setattr(harness, "run_cell",
                        lambda name, *a, **k: ran.append(name) or cell(name))
    run_main(["--resume", "--out", str(evidence)])

    assert "fastapi-map" in ran


def test_a_crashing_cell_does_not_lose_the_others(evidence, monkeypatch):
    def fake(name, *a, **k):
        if name == "fastapi-working":
            raise RuntimeError("boom")
        return cell(name)

    monkeypatch.setattr(harness, "run_cell", fake)
    run_main(["--resume", "--out", str(evidence)])

    written = json.loads((evidence / "band-calibration.json").read_text(encoding="utf-8"))
    assert len(written) == 6
    assert next(c for c in written if c["cell"] == "fastapi-working")["ok"] is False
    assert next(c for c in written if c["cell"] == "requests-map")["ok"] is True


# ── failed observations are kept, and named ───────────────────────────────────

def test_a_timeout_is_recorded_as_a_timeout():
    assert harness._classify(["curriculum: proposal call failed: ReadTimeout"], 5) == "timeout"


def test_a_long_failure_with_no_marker_is_recorded_as_suspected():
    # The SDK's exception text varies by transport, so duration corroborates.
    assert harness._classify(["something opaque"], 200.0) == "timeout_suspected"


def test_a_truncated_proposal_is_not_called_a_timeout():
    # Different fact about the run: the call landed, the answer was unusable.
    got = harness._classify(["curriculum: proposal truncated at the token limit"], 5)
    assert got == "truncated_proposal"


def test_an_unclassified_failure_is_still_kept():
    assert harness._classify(["mystery"], 5) == "other"


def test_the_call_timeout_is_well_under_the_sdk_worst_case():
    # The SDK default is 600s read x 3 attempts. The point of the ceiling is that
    # one stalled call cannot hold a cell for tens of minutes.
    assert harness.CALL_TIMEOUT_SECONDS <= 300
    assert harness.SDK_MAX_RETRIES == 0
