# Live pipeline progress (backend/pipeline/progress.py).
#
# The properties worth holding are about honesty and safety, not bookkeeping:
# a stage never un-completes, an unknown run is silent rather than fatal, and a
# reporter that raises cannot take a paid-for run down with it.

from dataclasses import dataclass

import pytest

from backend.pipeline import progress

RUN = "run-1"


@pytest.fixture(autouse=True)
def _clean_registry():
    progress._runs.clear()
    yield
    progress._runs.clear()


@dataclass
class FakeCall:
    """The shape `explore` hands to `on_call` — only the fields read here."""

    turn: int
    name: str
    arguments: dict


# ── snapshots ─────────────────────────────────────────────────────────────────

def test_an_unregistered_run_has_no_snapshot():
    assert progress.snapshot("never-started") is None


def test_a_begun_run_reports_the_stage_vocabulary_before_any_stage_lands():
    progress.begin(RUN)

    snap = progress.snapshot(RUN)

    assert snap is not None
    assert snap["stages"] == list(progress.STAGES)
    assert snap["stage"] is None
    assert snap["done"] == []
    assert snap["finished"] is False


def test_entering_a_stage_completes_the_one_before_it():
    progress.begin(RUN)
    progress.stage(RUN, "clone")
    progress.stage(RUN, "structure")

    snap = progress.snapshot(RUN)

    assert snap["stage"] == "structure"
    assert snap["done"] == ["clone"]


def test_finishing_completes_the_stage_still_running():
    # Otherwise the last stage of a successful run reads as never finished.
    progress.begin(RUN)
    progress.stage(RUN, "plan")
    progress.finish(RUN)

    snap = progress.snapshot(RUN)

    assert snap["finished"] is True
    assert snap["stage"] is None
    assert snap["done"] == ["plan"]


def test_a_stage_the_pipeline_does_not_have_is_refused():
    # The client renders from `stages`, so an unknown key would show as a stage
    # with no name at all.
    progress.begin(RUN)
    progress.stage(RUN, "clone")
    progress.stage(RUN, "embedding")

    assert progress.snapshot(RUN)["stage"] == "clone"


# ── activity ──────────────────────────────────────────────────────────────────

def test_activity_reports_the_tool_and_what_it_looked_at():
    progress.begin(RUN)
    progress.stage(RUN, "investigation")
    progress.activity(RUN, tool="read_file", target="requests/sessions.py", turn=3)

    snap = progress.snapshot(RUN)

    assert snap["activity"] == {"tool": "read_file", "target": "requests/sessions.py"}
    assert snap["turn"] == 3
    assert snap["calls"] == 1


def test_a_stage_change_clears_the_previous_stage_activity():
    # A finished stage must not leave its last read hanging under the next one.
    progress.begin(RUN)
    progress.stage(RUN, "survey")
    progress.activity(RUN, tool="read_file", target="requests/api.py")
    progress.stage(RUN, "investigation")

    snap = progress.snapshot(RUN)

    assert snap["activity"] is None
    assert snap["turn"] == 0
    # The lookup count is the run's, not the stage's, so it survives.
    assert snap["calls"] == 1


# ── tool_reporter ─────────────────────────────────────────────────────────────

def test_tool_reporter_is_absent_when_nobody_is_watching():
    # `explore` takes None for "no callback", so an unwatched run passes the
    # result straight through.
    assert progress.tool_reporter("") is None
    assert progress.tool_reporter(None) is None


def test_tool_reporter_names_the_most_specific_argument():
    progress.begin(RUN)
    progress.stage(RUN, "investigation")
    report = progress.tool_reporter(RUN)

    report(FakeCall(turn=2, name="symbols", arguments={
        "path": "requests/sessions.py", "name": "Session.send",
    }))

    # "Session.send" says more than the file it lives in.
    assert progress.snapshot(RUN)["activity"]["target"] == "Session.send"


def test_tool_reporter_survives_a_call_it_cannot_read():
    # on_call runs inside the exploration loop: raising here would end a run the
    # user has already paid for.
    progress.begin(RUN)
    report = progress.tool_reporter(RUN)

    report(FakeCall(turn=1, name="search_code", arguments=None))

    assert progress.snapshot(RUN)["activity"] == {"tool": "search_code", "target": ""}


def test_reporting_to_a_forgotten_run_is_silent():
    # Eviction, a restart, or a client that never sent an id — none of it may
    # surface as an exception inside the pipeline.
    progress.stage("gone", "clone")
    progress.activity("gone", tool="read_file", target="x.py")
    progress.finish("gone")
    progress.finish(None)

    assert progress.snapshot("gone") is None


# ── eviction ──────────────────────────────────────────────────────────────────

def test_the_registry_is_bounded_and_evicts_oldest_first():
    for i in range(progress.MAX_RUNS + 3):
        progress.begin(f"run-{i}")

    assert len(progress._runs) <= progress.MAX_RUNS
    assert progress.snapshot("run-0") is None
    assert progress.snapshot(f"run-{progress.MAX_RUNS + 2}") is not None
