# Live progress for one in-flight pipeline run.
#
# /session/start blocks for two to four minutes. Nothing about that is going to
# change — the run genuinely does clone, index, survey, investigate and plan —
# so the client should at least be able to see which of those it is doing, and
# what the exploration is currently reading.
#
# How the client sees it: it invents a `progress_id`, sends it with
# /session/start, and polls GET /session/progress/{id} on a *separate* request
# while the POST is still in flight. FastAPI runs sync endpoints in a
# threadpool, so the poll is served while the pipeline thread works.
#
# Two deliberate properties:
#
#   1. Reporting can never fail a run. Every public function here is
#      best-effort: an unknown id, a missing stage, a raising callback — all
#      swallowed. Progress is a view of the work, never a participant in it.
#   2. This module emits KEYS, not prose. Stage keys and tool names are fixed
#      vocabulary; the wording the user reads lives in frontend/lib/strings.ts
#      (see CLAUDE.md, "UI copy"). A percentage is deliberately not computed
#      here either — the client decides how to draw what it is told.
#
# In-memory and process-local by design: a run that outlives the request that
# produced it has nothing left to report, so there is nothing worth persisting.

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

# The stages a run passes through, in pipeline order. This is the vocabulary and
# the order — not the wording, and not a promise that every run reports all of
# them (a cached survey passes through `survey` in milliseconds).
STAGES: tuple[str, ...] = (
    "clone",
    "structure",
    "survey",
    "documentation",
    "investigation",
    "plan",
)

# Nothing else deletes a finished run, so without a cap a long-lived server
# accumulates every run it ever served. Oldest-first eviction; a run being
# polled is by definition among the newest.
MAX_RUNS = 64


@dataclass
class _Run:
    started: float
    stage: str | None = None
    done: list[str] = field(default_factory=list)
    # The last tool call the exploration made: {"tool": name, "target": str}.
    # Cleared on every stage change so a finished stage never leaves its last
    # read hanging under the next one.
    activity: dict | None = None
    turn: int = 0
    calls: int = 0
    finished: bool = False


_runs: dict[str, _Run] = {}
_lock = threading.Lock()


def begin(run_id: str | None) -> None:
    """Register a run so polls have something to find before stage one lands."""
    if not run_id:
        return
    with _lock:
        while len(_runs) >= MAX_RUNS:
            _runs.pop(next(iter(_runs)), None)
        _runs[run_id] = _Run(started=time.monotonic())


def stage(run_id: str | None, key: str) -> None:
    """Enter `key`, marking whatever was current as done.

    Stages are reported by whoever can actually see the transition: the graph
    nodes for the coarse ones, `explorer_nodes` for the substages inside
    repo_survey, which from the graph's side is a single node.
    """
    if not run_id or key not in STAGES:
        return
    with _lock:
        run = _runs.get(run_id)
        if run is None:
            return
        if run.stage and run.stage not in run.done:
            run.done.append(run.stage)
        run.stage = key
        run.activity = None
        run.turn = 0


def activity(run_id: str | None, tool: str, target: str, turn: int = 0) -> None:
    """Report one exploration tool call: what it was and what it looked at."""
    if not run_id:
        return
    with _lock:
        run = _runs.get(run_id)
        if run is None:
            return
        run.activity = {"tool": tool, "target": target}
        run.turn = max(run.turn, turn)
        run.calls += 1


def finish(run_id: str | None) -> None:
    """Mark the run complete however it ended — success, failure or resume.

    Kept deliberately outcome-free: the POST's own response says whether the
    run worked, and a client polling a finished run only needs to stop.
    """
    if not run_id:
        return
    with _lock:
        run = _runs.get(run_id)
        if run is None:
            return
        if run.stage and run.stage not in run.done:
            run.done.append(run.stage)
        run.stage = None
        run.activity = None
        run.finished = True


def snapshot(run_id: str | None) -> dict | None:
    """What the client polls. None when the id was never registered."""
    if not run_id:
        return None
    with _lock:
        run = _runs.get(run_id)
        if run is None:
            return None
        return {
            "stages": list(STAGES),
            "stage": run.stage,
            "done": list(run.done),
            "activity": dict(run.activity) if run.activity else None,
            "turn": run.turn,
            "calls": run.calls,
            "seconds": round(time.monotonic() - run.started, 1),
            "finished": run.finished,
        }


# The argument that names what a tool call looked at, per tool. Checked in this
# order because `symbols` and `propose_anchor` take more than one and the first
# is the more specific: "Session.send" says more than "sessions.py".
_TARGET_KEYS: tuple[str, ...] = (
    "name", "symbol", "pattern", "path", "file", "glob",
)


def tool_reporter(run_id: str | None):
    """An ``on_call`` for :func:`backend.repo.explore.explore`.

    Returns None when there is nothing to report to, which is also what
    `explore` expects for "no callback" — so the caller can pass the result
    through unconditionally.

    Swallows everything: `on_call` is invoked from inside the exploration loop,
    so a raising reporter would end a run the user has already paid for.
    """
    if not run_id:
        return None

    def report(call) -> None:
        try:
            arguments = call.arguments or {}
            target = next(
                (str(arguments[k]) for k in _TARGET_KEYS if arguments.get(k)),
                "",
            )
            activity(run_id, tool=call.name, target=target, turn=call.turn)
        except Exception:
            pass

    return report
