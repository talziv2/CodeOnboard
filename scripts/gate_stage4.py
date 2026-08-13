"""Stage-4 reliability gate — can the explorer path stand on its own, without RAG?

    uv run python scripts/gate_stage4.py --dry-run
    uv run python scripts/gate_stage4.py                    # the full 10 attempts
    uv run python scripts/gate_stage4.py --only requests-auth --repeats 2

This is not the Stage-3 quality experiment repeated. That measured whether the
new architecture produces a *better* learning path. This measures whether it
produces one *at all, reliably*, and — when it does not — exactly where in the
chain the run died:

    Survey -> Investigation -> Dossier validation -> Mentor
           -> LearningGraph validation/persistence -> session start

Three things it does that no earlier script did:

  RAG CANNOT BE REACHED. Stage 5 deleted `backend.rag` outright, so the gate
  asserts its absence at startup rather than monkeypatching it away. The
  retrieval counters remain in the report and remain zero — by construction now,
  rather than by measurement.

  FAILURES ARE CLASSIFIED BY STAGE. A run that ends without a graph is not "a
  failure"; it is a failure at a named stage with a named cause. The classifier
  is deterministic and reads the same state a human would.

  INFORMATION LOSS IS TRACED PER FILE. For each hand-labelled important file the
  gate records where it stopped travelling: present in the repository, named by
  the Survey, surfaced by a tool call, actually read, cited in the Dossier,
  anchored in the LearningGraph. "The path missed X" and "the investigation never
  saw X" are different findings, and only the trace separates them.

Labels (`important_files`) are scoring data. They never enter a prompt, and the
production exploration brief is not modified for this run.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(override=True)

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from backend.learning import store as learning_store  # noqa: E402
from backend.pipeline import explorer_nodes  # noqa: E402
from backend.pipeline.runner import run_pipeline  # noqa: E402
from backend.repo.cloner import get_commit_sha  # noqa: E402
from backend.repo import anchors, dossier_store, investigation as investigation_module  # noqa: E402
from backend.repo.skeleton import build_skeleton, normalize_path  # noqa: E402

OUT_DIR = Path("data/experiments")
DB_PATH = Path("data/sessions.db")

# ── failure stages, in pipeline order ─────────────────────────────────────────

SURVEY = "survey"
INVESTIGATION = "investigation"
# Not a pipeline stage. An API outage says nothing about the architecture, and
# scoring it as an explorer failure would understate reliability exactly as
# badly as a silent RAG rescue would overstate it. Recorded, excluded from the
# rate, and — because the first such failure burned five further attempts for
# zero information — used to stop the batch.
INFRASTRUCTURE = "infrastructure"
DOSSIER_VALIDATION = "dossier_validation"
MENTOR = "mentor"
GRAPH_PERSISTENCE = "graph_persistence"
SESSION_START = "session_start"
OK = "ok"

STAGES = (SURVEY, INVESTIGATION, DOSSIER_VALIDATION, MENTOR,
          GRAPH_PERSISTENCE, SESSION_START)


# ── goal fixtures ─────────────────────────────────────────────────────────────
#
# Same wording as the Stage-3 fixtures where they overlap, so the numbers stay
# comparable with that report. Three goal types and both repositories: the gate
# must not be answered by the easy component case alone.

GOALS = {
    "requests-auth": {
        "repo_url": "https://github.com/psf/requests",
        "repo_path": "data/repos/requests",
        "goal": {
            "primary_goal": "understand how authentication is applied to outgoing requests",
            "goal_type": "understand_component",
            "focus_area": "authentication",
            "experience_level": "intermediate",
            "depth": "deep",
            "time_available": "2 hours",
            "target_repo": "https://github.com/psf/requests",
            "language": "en",
        },
        "important_files": [
            "src/requests/auth.py", "src/requests/sessions.py",
            "src/requests/models.py", "src/requests/api.py",
        ],
    },
    "requests-flow": {
        "repo_url": "https://github.com/psf/requests",
        "repo_path": "data/repos/requests",
        "goal": {
            "primary_goal": "understand what happens end to end when requests.get(url) is called",
            "goal_type": "understand_system",
            "focus_area": "the request lifecycle",
            "experience_level": "intermediate",
            "depth": "deep",
            "time_available": "2 hours",
            "target_repo": "https://github.com/psf/requests",
            "language": "en",
        },
        "important_files": [
            "src/requests/api.py", "src/requests/sessions.py",
            "src/requests/models.py", "src/requests/adapters.py",
        ],
    },
    "fastapi-di": {
        "repo_url": "https://github.com/fastapi/fastapi",
        "repo_path": "data/repos/fastapi",
        "goal": {
            "primary_goal": "understand how dependency injection works",
            "goal_type": "understand_component",
            "focus_area": "dependency injection",
            "experience_level": "intermediate",
            "depth": "deep",
            "time_available": "3 hours",
            "target_repo": "https://github.com/fastapi/fastapi",
            "language": "en",
        },
        "important_files": [
            "fastapi/dependencies/utils.py", "fastapi/dependencies/models.py",
            "fastapi/params.py", "fastapi/param_functions.py", "fastapi/routing.py",
        ],
    },
    "fastapi-request": {
        "repo_url": "https://github.com/fastapi/fastapi",
        "repo_path": "data/repos/fastapi",
        "goal": {
            "primary_goal": "understand what happens end to end when an HTTP request reaches an endpoint",
            "goal_type": "understand_system",
            "focus_area": "the request lifecycle",
            "experience_level": "intermediate",
            "depth": "deep",
            "time_available": "3 hours",
            "target_repo": "https://github.com/fastapi/fastapi",
            "language": "en",
        },
        "important_files": [
            "fastapi/routing.py", "fastapi/applications.py",
            "fastapi/dependencies/utils.py", "fastapi/encoders.py",
        ],
    },
    "fastapi-security": {
        "repo_url": "https://github.com/fastapi/fastapi",
        "repo_path": "data/repos/fastapi",
        "goal": {
            "primary_goal": "understand the security system well enough to add a custom authentication scheme",
            "goal_type": "contribute_code",
            "focus_area": "security schemes",
            "experience_level": "advanced",
            "depth": "deep",
            "time_available": "3 hours",
            "target_repo": "https://github.com/fastapi/fastapi",
            "language": "en",
        },
        "important_files": [
            "fastapi/security/base.py", "fastapi/security/oauth2.py",
            "fastapi/security/http.py", "fastapi/dependencies/utils.py",
            "fastapi/openapi/models.py",
        ],
    },
}

# The attempt schedule. `requests-auth` and `fastapi-di` are repeated because
# the open questions about them are about run-to-run behaviour; the rest are
# there so the gate is not answered by two goals.
SCHEDULE = (
    ["requests-auth"] * 3
    + ["requests-flow"] * 2
    + ["fastapi-di"] * 3
    + ["fastapi-request"]
    + ["fastapi-security"]
)


def _short(text, width):
    text = " ".join(str(text or "").split())
    return text if len(text) <= width else text[: width - 1] + "…"


# ── RAG severance ─────────────────────────────────────────────────────────────


class RagSpy:
    """Records calls to a retrieval function that no longer exists.

    Stage 5 deleted `backend.rag`, so severance is now a property of the code
    rather than something a harness has to enforce. The spy is kept — with
    nothing to patch it onto — so the gate still *reports* a retrieval count,
    and so the report's "0 calls" line keeps meaning the same thing it did when
    retrieval was still installed.
    """

    def __init__(self, name: str):
        self.name = name
        self.calls: list[str] = []


def sever_rag() -> dict[str, RagSpy]:
    """Assert there is no retrieval left to sever, and return empty counters."""
    import importlib

    for module in ("backend.rag", "backend.rag.retrieval"):
        try:
            importlib.import_module(module)
        except ModuleNotFoundError:
            continue
        raise RuntimeError(
            f"{module} still exists — the gate assumes Stage 5 removed it"
        )
    return {
        "retrieve_chunks": RagSpy("retrieve_chunks"),
        "retrieve_supporting_chunks": RagSpy("retrieve_supporting_chunks"),
    }


# ── capturing the exploration itself ──────────────────────────────────────────
#
# `state.investigation` carries counts, not the trace, and deliberately so — it
# is persisted. The trace is what answers "did the investigation ever see this
# file", so the gate wraps the entry point to keep the run object in hand.


class InvestigationCapture:
    def __init__(self):
        self.run = None
        self._original = investigation_module.run_investigation

    def __enter__(self):
        def wrapper(**kwargs):
            self.run = None
            run = self._original(**kwargs)
            self.run = run
            return run

        explorer_nodes.investigation_module.run_investigation = wrapper
        return self

    def __exit__(self, *exc):
        explorer_nodes.investigation_module.run_investigation = self._original
        return False


def exploration_telemetry(run) -> dict:
    """Turns, calls, tokens, cost and the file trace, from one exploration."""
    if run is None:
        return {}
    exploration = run.exploration
    usage = exploration.usage
    surfaced: set[str] = set()
    read: set[str] = set()
    for call in exploration.trace:
        for path in call.facts.get("paths") or []:
            surfaced.add(normalize_path(str(path)))
        if call.name == "read_file" and call.ok:
            path = call.arguments.get("path")
            if path:
                read.add(normalize_path(str(path)))
                surfaced.add(normalize_path(str(path)))
        if call.name in ("symbols", "neighbors", "propose_anchor"):
            path = call.arguments.get("path") or call.arguments.get("file")
            if path:
                surfaced.add(normalize_path(str(path)))
        # An ambiguity error names the competing definitions in its detail
        # string; the model sees those file names, so the trace must count them
        # as surfaced or it will understate what the run was shown.
        if call.error == "ambiguous_symbol":
            for token in str(call.summary).replace(",", " ").split():
                if token.endswith(".py"):
                    surfaced.add(normalize_path(token.strip("();")))
    return {
        "stop_reason": exploration.stop_reason,
        "turns": exploration.turns,
        "tool_calls": len([c for c in exploration.trace if c.name != "submit_dossier"]),
        "submissions": len([c for c in exploration.trace if c.name == "submit_dossier"]),
        "rejections": list(exploration.rejections),
        "repair_turns": sum(1 for c in exploration.trace if c.facts.get("repair")),
        "duplicate_calls": sum(1 for c in exploration.trace if c.facts.get("duplicate_of")),
        "seconds": exploration.seconds,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_read_tokens": usage.cache_read_input_tokens,
        "cache_write_tokens": usage.cache_creation_input_tokens,
        "cache_hit_ratio": usage.cache_hit_ratio,
        "cost_usd": usage.cost_usd(),
        "contract_met": exploration.contract_met,
        # The text of an API failure, which the pipeline's own error string
        # flattens to "(api_error)". Without it a run cannot tell a billing
        # outage from a malformed request, and the first gate batch could only
        # be diagnosed by probing the API afterwards.
        "harness_errors": list(exploration.errors),
        # `grounding_accuracy` is 1.0 when a payload cites nothing at all, so a
        # structurally broken first submission reads as perfect grounding. The
        # anchor counts are recorded beside it so the ratio stays interpretable.
        "grounding_first": run.validator.first.grounding_accuracy if run.validator.first else None,
        "anchors_first": run.validator.first.total_anchors if run.validator.first else None,
        "grounding_final": run.check.grounding_accuracy if run.check else None,
        "anchors_final": run.check.total_anchors if run.check else None,
        "unresolved_final": list(run.check.unresolved_anchors) if run.check else [],
        "unmet_final": list(run.check.unmet_criteria) if run.check else [],
        "structural_final": list(run.check.structural) if run.check else [],
        "_surfaced": sorted(surfaced),
        "_read": sorted(read),
    }


# ── invariants ────────────────────────────────────────────────────────────────


def check_invariants(state, dossier: dict | None, skeleton) -> dict:
    """The properties that must hold for a graph to count as usable.

    Deliberately independent of the Mentor's own gate: the Mentor already
    refuses ungrounded nodes, and a check that trusts the thing it is checking
    proves nothing.
    """
    graph = state.graph
    nodes = list(graph.nodes.values())
    unresolved: list[str] = []
    outside_evidence: list[str] = []

    evidence: list[dict] = []
    if dossier:
        for _, file, symbol in investigation_module.cited_anchors(dossier):
            if not (file and symbol):
                continue
            resolution = anchors.resolve(skeleton, file, symbol=symbol)
            if resolution.ok:
                a = resolution.anchor
                evidence.append({"file": a.file, "start_line": a.line_start,
                                 "end_line": a.line_end})

    for node in nodes:
        a = node.code_anchor
        resolution = anchors.resolve(
            skeleton, a.file, line_start=a.line_start, line_end=a.line_end
        )
        if not resolution.ok:
            unresolved.append(f"{node.title}: {a.file}:{a.line_start}-{a.line_end}"
                              f" ({resolution.reason})")
            continue
        if evidence and not anchors.within_evidence(resolution.anchor, evidence):
            outside_evidence.append(f"{node.title}: {a.file}:{a.symbol or ''}")

    return {
        "nodes": len(nodes),
        "anchors_resolve": not unresolved,
        "unresolved_anchors": unresolved,
        "no_fabricated_evidence": not outside_evidence,
        "nodes_outside_dossier_evidence": outside_evidence,
        "single_chain": len([e for e in graph.edges if e.kind == "sequence"]) == max(
            0, len(nodes) - 1
        ),
        "has_current_node": graph.current_node_id is not None,
    }


def file_trace(spec: dict, state, dossier: dict | None, telemetry: dict,
               skeleton) -> dict:
    """Where each labelled important file stopped travelling down the pipeline."""
    survey_text = json.dumps(state.survey or {})
    dossier_text = json.dumps(dossier or {})
    graph_files = {
        normalize_path(n.code_anchor.file) for n in (state.graph.nodes.values()
                                                     if state.graph else [])
    }
    surfaced = set(telemetry.get("_surfaced") or [])
    read = set(telemetry.get("_read") or [])

    trace = {}
    for label in spec["important_files"]:
        path = normalize_path(label)
        canonical = skeleton.canonical_file(path) or path
        trace[canonical] = {
            "in_repository": skeleton.canonical_file(path) is not None,
            "in_survey": path in survey_text or canonical in survey_text,
            "surfaced_by_a_tool": canonical in surfaced or path in surfaced,
            "read": canonical in read or path in read,
            "in_dossier": canonical in dossier_text or path in dossier_text,
            "in_graph": canonical in graph_files,
        }
    return trace


# ── one attempt ───────────────────────────────────────────────────────────────


CONFUSED_ANSWER = (
    "I think it just gets passed straight through and the library figures it "
    "out somewhere? I'm not really sure which part is responsible or when it "
    "actually runs."
)


def run_mutation_probe(graph, spec: dict, client, spies: dict) -> dict:
    """Grade a deliberately confused answer and let the Mutator respond.

    Deliberately generic wording: the point is to trip the `confused`
    classification on any goal, not to test the Grader's discrimination.
    """
    from backend.agents.grader.agent import run as run_grader
    from backend.agents.mentor.mutator import mutate
    from backend.pipeline.state import OnboardState

    before = len(spies["retrieve_supporting_chunks"].calls)
    state = OnboardState(repo_url=spec["repo_url"], goal=dict(spec["goal"]),
                         client=client, repo_path=spec["repo_path"])
    state.graph = graph
    try:
        run_grader(state, CONFUSED_ANSWER, client=client)
        grade = (state.last_grade or {}).get("classification")
        mutate(state, "prerequisite", client=client)
    except Exception as exc:
        return {"outcome": f"raised {type(exc).__name__}: {exc}",
                "reached_retrieval": False}
    mutation = state.last_mutation or {"kind": "none"}
    inserted = None
    if mutation.get("kind") == "prerequisite":
        node = graph.nodes[mutation["new_node_id"]]
        inserted = (f"{node.code_anchor.file}:{node.code_anchor.symbol or ''}"
                    f" — {node.title}")
    return {
        "grade": grade,
        "outcome": mutation.get("kind", "none") if inserted else "no prerequisite",
        "prerequisite": inserted,
        # The fact the RAG decision turns on: did the structural path suffice,
        # or did the Mutator fall through to retrieval?
        "reached_retrieval":
            len(spies["retrieve_supporting_chunks"].calls) > before,
        "errors": list(state.errors),
    }


def run_attempt(index: int, name: str, spec: dict, spies: dict,
                with_mutation: bool = False) -> dict:
    import anthropic

    print(f"\n{'=' * 100}\nattempt {index}: {name} ({spec['goal']['goal_type']})\n{'=' * 100}",
          flush=True)
    client = anthropic.Anthropic()
    started = time.time()
    record: dict = {
        "attempt": index, "goal": name, "goal_type": spec["goal"]["goal_type"],
        "repo": spec["repo_url"].rsplit("/", 1)[-1],
    }
    for spy in spies.values():
        spy.calls.clear()

    with InvestigationCapture() as capture:
        try:
            state = run_pipeline(spec["repo_url"], dict(spec["goal"]),
                                 client=client)
        except Exception as exc:
            record.update({"stage": INVESTIGATION, "ok": False,
                           "cause": f"pipeline raised {type(exc).__name__}: {exc}",
                           "seconds": time.time() - started})
            print(f"  !! pipeline raised: {type(exc).__name__}: {exc}", flush=True)
            return record
    telemetry = exploration_telemetry(capture.run)
    record["investigation"] = {k: v for k, v in telemetry.items()
                               if not k.startswith("_")}
    record["pipeline_seconds"] = time.time() - started
    record["errors"] = list(state.errors)

    dossier = (state.investigation or {}).get("dossier")
    skeleton = build_skeleton(spec["repo_path"])

    print(f"  survey        : {'present' if state.survey else 'ABSENT'}", flush=True)
    if telemetry:
        print(f"  investigation : stop={telemetry['stop_reason']} "
              f"turns={telemetry['turns']} calls={telemetry['tool_calls']} "
              f"submissions={telemetry['submissions']} "
              f"repair={telemetry['repair_turns']} "
              f"contract_met={telemetry['contract_met']} "
              f"${telemetry['cost_usd']:.4f} {telemetry['seconds']:.0f}s", flush=True)
        for rejection in telemetry["rejections"]:
            print(f"    rejected: {_short(rejection, 200)}", flush=True)

    # ── stage classification ────────────────────────────────────────────────
    if state.repo_path is None or state.module_map is None:
        record.update({"stage": SURVEY, "ok": False,
                       "cause": "; ".join(state.errors) or "no repo_path/module_map"})
        return _finish(record, started)
    if state.investigation is None:
        outage = telemetry.get("stop_reason") == "api_error"
        record.update({
            "stage": INFRASTRUCTURE if outage else INVESTIGATION, "ok": False,
            "cause": "; ".join(telemetry.get("harness_errors") or []) if outage
                     else ("; ".join(e for e in state.errors if "investigation" in e)
                           or "no dossier produced"),
        })
        return _finish(record, started)
    if state.graph is None:
        # The Mentor refused. Which refusal it was decides the stage: a dossier
        # with nothing resolvable never satisfied its own contract, and calling
        # that a Mentor failure would point the diagnosis one stage too late.
        errors = " ".join(state.errors)
        no_evidence = "no resolvable evidence" in errors
        record.update({
            "stage": DOSSIER_VALIDATION if no_evidence else MENTOR,
            "ok": False,
            "cause": "; ".join(e for e in state.errors if "mentor" in e) or errors,
        })
        record["file_trace"] = file_trace(spec, state, dossier, telemetry, skeleton)
        return _finish(record, started)

    record["invariants"] = check_invariants(state, dossier, skeleton)
    record["confidence"] = state.confidence
    print(f"  graph         : {record['invariants']['nodes']} nodes, "
          f"confidence={state.confidence}, "
          f"anchors_resolve={record['invariants']['anchors_resolve']}, "
          f"no_fabrication={record['invariants']['no_fabricated_evidence']}", flush=True)

    # ── persistence + session start, exactly as /session/start does it ──────
    try:
        learning_store.save_graph(state.graph, DB_PATH)
        commit_sha = get_commit_sha(state.repo_path)
        dossier_store.save_investigation(
            state.graph.session_id, commit_sha, state.investigation, DB_PATH
        )
        reloaded = learning_store.load_graph(state.graph.session_id, DB_PATH)
        stored_dossier = dossier_store.load_investigation(
            state.graph.session_id, commit_sha, DB_PATH
        )
    except Exception as exc:
        record.update({"stage": GRAPH_PERSISTENCE, "ok": False,
                       "cause": f"{type(exc).__name__}: {exc}"})
        return _finish(record, started)

    record["persistence"] = {
        "graph_reloaded": reloaded is not None,
        "nodes_reloaded": len(reloaded.nodes) if reloaded else 0,
        "symbols_kept": sum(1 for n in reloaded.nodes.values()
                            if n.code_anchor.symbol) if reloaded else 0,
        "dossier_reloaded": stored_dossier is not None,
        "resume_point": bool(reloaded and reloaded.resume_point()),
    }
    if reloaded is None or stored_dossier is None or len(reloaded.nodes) == 0:
        record.update({"stage": GRAPH_PERSISTENCE, "ok": False,
                       "cause": f"reload incomplete: {record['persistence']}"})
        return _finish(record, started)

    # Session start: the real endpoint body, against the real persisted graph.
    from backend import api

    session_started = time.time()
    try:
        lesson = api._render_current_lesson(reloaded, client)
    except Exception as exc:
        record.update({"stage": SESSION_START, "ok": False,
                       "cause": f"{type(exc).__name__}: {exc}"})
        return _finish(record, started)
    # `_render_current_lesson` substitutes a placeholder rather than failing, so
    # a "successful" session start has to be checked for the placeholder or the
    # gate would score a broken lesson as a pass.
    fell_back = lesson.get("prompt") == api._FALLBACK_PROMPT
    record["session"] = {
        "lesson_rendered": bool(lesson) and not fell_back,
        "used_fallback_lesson": fell_back,
        "seconds": time.time() - session_started,
        "walkthrough": _short(lesson.get("walkthrough"), 400),
    }
    print(f"  session start : lesson={'ok' if not fell_back else 'FALLBACK'} "
          f"({record['session']['seconds']:.0f}s)", flush=True)
    if fell_back:
        record.update({"stage": SESSION_START, "ok": False,
                       "cause": "teaching produced no lesson; placeholder served"})
        return _finish(record, started)

    # Optional: one confusion cycle, because the Mutator is the last consumer
    # that still has a retrieval fallback wired in. Whether it ever reaches it
    # is a fact the RAG-removal decision needs, and no other check exercises it.
    if with_mutation:
        record["mutation"] = run_mutation_probe(reloaded, spec, client, spies)
        print(f"  mutation      : {record['mutation']['outcome']}", flush=True)

    record["file_trace"] = file_trace(spec, state, dossier, telemetry, skeleton)
    record["discovery"] = sum(
        1 for t in record["file_trace"].values() if t["in_graph"]
    ) / max(1, len(record["file_trace"]))
    record["graph_files"] = sorted({
        normalize_path(n.code_anchor.file) for n in reloaded.nodes.values()
    })
    record["node_titles"] = [
        f"{n.code_anchor.file}:{n.code_anchor.symbol or ''} — {n.title}"
        for n in reloaded.nodes.values()
    ]
    record["session_id"] = state.graph.session_id
    invariants = record["invariants"]
    record.update({
        "stage": OK,
        "ok": invariants["anchors_resolve"] and invariants["no_fabricated_evidence"],
    })
    if not record["ok"]:
        record["cause"] = "invariant violation"
    print(f"  discovery     : {record['discovery']:.0%} "
          f"(missed: {[f for f, t in record['file_trace'].items() if not t['in_graph']]})",
          flush=True)
    return _finish(record, started)


def _finish(record: dict, started: float) -> dict:
    record["seconds"] = time.time() - started
    if record.get("stage") != OK:
        print(f"  FAILED at {record.get('stage')}: {_short(record.get('cause'), 240)}",
              flush=True)
    return record


# ── reporting ─────────────────────────────────────────────────────────────────


def report(records: list[dict], spies: dict) -> None:
    print(f"\n{'=' * 110}\nRELIABILITY GATE — {len(records)} explorer attempts\n{'=' * 110}")
    print(f"{'#':>2} {'goal':17s} {'stage':20s} {'nodes':>5s} {'disc':>5s} "
          f"{'turns':>5s} {'calls':>5s} {'$':>7s} {'secs':>5s}  cause")
    for r in records:
        inv = r.get("investigation") or {}
        print(f"{r['attempt']:>2} {r['goal']:17s} {r.get('stage', '?'):20s} "
              f"{(r.get('invariants') or {}).get('nodes', 0):>5} "
              f"{r.get('discovery', 0):>5.0%} "
              f"{inv.get('turns', 0):>5} {inv.get('tool_calls', 0):>5} "
              f"{inv.get('cost_usd', 0):>7.4f} {r.get('seconds', 0):>5.0f}  "
              f"{_short(r.get('cause', ''), 60)}")

    succeeded = [r for r in records if r.get("stage") == OK and r.get("ok")]
    outages = [r for r in records if r.get("stage") == INFRASTRUCTURE]
    scored = [r for r in records if r.get("stage") != INFRASTRUCTURE]
    print(f"\nend-to-end success: {len(succeeded)}/{len(scored)} "
          f"({len(succeeded) / max(1, len(scored)):.0%}) "
          f"of attempts the architecture actually got to run")
    if outages:
        print(f"  ({len(outages)} further attempt(s) lost to API outage and "
              f"excluded — see `infrastructure` below)")
    by_stage: dict[str, int] = {}
    for r in records:
        if r.get("stage") != OK or not r.get("ok"):
            by_stage[r.get("stage", "?")] = by_stage.get(r.get("stage", "?"), 0) + 1
    print(f"failures by stage : {by_stage or 'none'}")

    grounded = [r for r in records if (r.get("investigation") or {}).get("grounding_final") is not None]
    if grounded:
        finals = [r["investigation"]["grounding_final"] for r in grounded]
        print(f"dossier grounding : final {min(finals):.0%}–{max(finals):.0%} "
              f"over {len(finals)} submissions")
    accepted = sum(1 for r in records
                   if (r.get("investigation") or {}).get("contract_met") is True)
    print(f"dossier accepted on merits: {accepted}/{len(records)}")
    repairs = sum((r.get("investigation") or {}).get("repair_turns", 0) for r in records)
    print(f"serialisation repair turns fired: {repairs}")

    # Summed from the per-attempt records, not from the spies: the spies are
    # cleared at the top of every attempt, so reading them here would report
    # only the final attempt and understate the total.
    print("\nRAG severance — every call below would have been a silent rescue:")
    for name in spies:
        sites = [
            site for r in records for site in (r.get("rag_calls") or {}).get(name, [])
        ]
        print(f"  {name:28s} {len(sites)} call(s) across {len(records)} attempt(s) "
              f"{sorted(set(sites))[:4] if sites else ''}")

    mutations = [r["mutation"] for r in records if r.get("mutation")]
    if mutations:
        reached = sum(1 for m in mutations if m["reached_retrieval"])
        inserted = sum(1 for m in mutations if m.get("prerequisite"))
        print(f"\nMutator probe: {inserted}/{len(mutations)} inserted a "
              f"prerequisite; {reached}/{len(mutations)} fell through to retrieval")
        for m in mutations:
            print(f"  {m['grade']:>10} -> {m.get('prerequisite') or m['outcome']}")

    print("\nINFORMATION-LOSS TRACE (labelled important files that never reached the graph)")
    stages = ["in_repository", "in_survey", "surfaced_by_a_tool", "read",
              "in_dossier", "in_graph"]
    aggregate: dict[str, dict[str, int]] = {}
    for r in records:
        for path, t in (r.get("file_trace") or {}).items():
            key = f"{r['goal']}  {path}"
            bucket = aggregate.setdefault(key, {s: 0 for s in stages} | {"runs": 0})
            bucket["runs"] += 1
            for s in stages:
                bucket[s] += 1 if t[s] else 0
    print(f"{'goal / file':56s} {'runs':>4s} " + " ".join(f"{s[:9]:>9s}" for s in stages))
    for key, bucket in sorted(aggregate.items()):
        if bucket["in_graph"] == bucket["runs"]:
            continue      # arrived every time; nothing to diagnose
        print(f"{key:56s} {bucket['runs']:>4} "
              + " ".join(f"{bucket[s]:>9}" for s in stages))

    totals_cost = sum((r.get("investigation") or {}).get("cost_usd", 0) for r in records)
    print(f"\ninvestigation cost total ${totals_cost:.2f}; "
          f"wall clock total {sum(r.get('seconds', 0) for r in records) / 60:.0f} min")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", choices=list(GOALS))
    parser.add_argument("--repeats", type=int, default=None,
                        help="With --only: attempts per named goal.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--with-mutation", action="store_true",
                        help="Also run one confusion -> Mutator cycle per attempt.")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    schedule = list(SCHEDULE)
    if args.only:
        schedule = [g for g in args.only for _ in range(args.repeats or 1)]

    if args.dry_run:
        print(f"{len(schedule)} attempts: {schedule}")
        for name in dict.fromkeys(schedule):
            spec = GOALS[name]
            skeleton = build_skeleton(spec["repo_path"])
            print(f"\n{name} ({spec['goal']['goal_type']})")
            for label in spec["important_files"]:
                print(f"   label {label:44s} "
                      f"-> {'ok' if skeleton.canonical_file(label) else 'NOT IN SKELETON'}")
        return 0

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set")
        return 1

    spies = sever_rag()
    out = Path(args.out) if args.out else OUT_DIR / f"gate-{time.strftime('%Y%m%d-%H%M%S')}.json"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    records: list[dict] = []
    outages = 0
    for index, name in enumerate(schedule, start=1):
        try:
            record = run_attempt(index, name, GOALS[name], spies,
                                 with_mutation=args.with_mutation)
        except Exception as exc:   # an attempt failing must not lose the batch
            record = {"attempt": index, "goal": name, "stage": "harness",
                      "ok": False, "cause": f"{type(exc).__name__}: {exc}"}
            print(f"  !! harness error: {type(exc).__name__}: {exc}", flush=True)
        record["rag_calls"] = {n: list(s.calls) for n, s in spies.items() if s.calls}
        records.append(record)
        # Written after every attempt: a batch this long must not lose its
        # results to a failure in attempt 9.
        out.write_text(json.dumps(records, indent=2, default=str), encoding="utf-8")

        outages = outages + 1 if record.get("stage") == INFRASTRUCTURE else 0
        if outages >= 2:
            print(f"\n!! two consecutive API outages — stopping with "
                  f"{len(schedule) - index} attempt(s) unrun. Re-run them with "
                  f"--only once the API is reachable.\n"
                  f"   last: {_short(record.get('cause'), 200)}", flush=True)
            break

    report(records, spies)
    out.write_text(json.dumps(records, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
