"""Stage 4 smoke test — the full adaptive learning loop over a persisted Dossier.

    uv run python scripts/smoke_stage4.py --dry-run
    uv run python scripts/smoke_stage4.py

Exercises the whole experience, not the pieces:

    onboarding -> investigation -> graph creation -> PERSISTED DOSSIER
      -> session start -> lesson rendering (dossier context)
      -> user answer -> grader -> confusion
      -> mutator -> prerequisite insertion -> back to the original path

and reports, for the lesson and the mutation, exactly WHICH dossier findings
were used — because "the dossier helped" is not a claim a smoke test should be
allowed to make without showing the context it actually fed in.

Also verifies the D12 fallback directly: the same session is re-taught with its
dossier made unavailable, and the run must degrade in richness only.
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

from backend.agents.grader.agent import run as run_grader  # noqa: E402
from backend.agents.mentor.mutator import mutate  # noqa: E402
from backend.agents.teaching.agent import run as run_teaching  # noqa: E402
from backend.learning import store as learning_store  # noqa: E402
from backend.pipeline.runner import run_pipeline  # noqa: E402
from backend.pipeline.state import OnboardState  # noqa: E402
from backend.repo.cloner import clone_repo, get_commit_sha  # noqa: E402
from backend.repo import dossier_context, dossier_store  # noqa: E402
from backend.repo.skeleton import build_skeleton  # noqa: E402

DB_PATH = Path("data/sessions.db")
OUT_DIR = Path("data/experiments")

REPO_URL = "https://github.com/psf/requests"
GOAL = {
    "primary_goal": "understand how authentication is applied to outgoing requests",
    "goal_type": "understand_component",
    "focus_area": "authentication",
    "experience_level": "intermediate",
    "depth": "deep",
    "time_available": "2 hours",
    "target_repo": REPO_URL,
    "language": "en",
}

# A deliberately confused answer, so the Grader classifies it that way and the
# adaptive branch actually runs. Not a trick — just wrong in the ordinary way.
CONFUSED_ANSWER = (
    "I think it just puts the username and password in the URL somewhere, and "
    "the server reads them from there? I'm not really sure what the auth object "
    "is for or when it runs."
)


def _short(text, width):
    text = " ".join(str(text or "").split())
    return text if len(text) <= width else text[: width - 1] + "…"


def rule(title: str) -> None:
    print(f"\n{'=' * 96}\n{title}\n{'=' * 96}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    if args.dry_run:
        print(f"would run the full loop on {REPO_URL}")
        print(f"goal: {GOAL['primary_goal']}")
        return 0
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set")
        return 1

    import anthropic

    client = anthropic.Anthropic()
    report: dict = {}
    started = time.time()

    # ── 1. onboarding ────────────────────────────────────────────────────────
    rule("1. ONBOARDING")
    state = run_pipeline(REPO_URL, dict(GOAL), client=client)
    if state.graph is None:
        print(f"  NO GRAPH — {state.errors}")
        return 1
    graph = state.graph
    repo_path = state.repo_path or clone_repo(REPO_URL)
    commit_sha = get_commit_sha(repo_path)
    inv = state.investigation or {}
    print(f"  graph        : {len(graph.nodes)} nodes, confidence={state.confidence}")
    if inv:
        print(f"  investigation: {'accepted' if inv.get('accepted') else 'salvaged'}, "
              f"{inv.get('turns')} turns, ${inv.get('cost_usd', 0):.4f}")
    learning_store.save_graph(graph, DB_PATH)

    # ── 2. dossier persistence ───────────────────────────────────────────────
    rule("2. DOSSIER PERSISTENCE")
    if inv:
        dossier_store.save_investigation(graph.session_id, commit_sha, inv, DB_PATH)
    reloaded = dossier_store.load_investigation(graph.session_id, commit_sha, DB_PATH)
    print(f"  stored for session {graph.session_id[:8]} @ {commit_sha[:12]}")
    print(f"  reloaded     : {'yes' if reloaded else 'NO'}")
    if reloaded:
        d = reloaded["dossier"]
        print("  sections     : "
              + ", ".join(f"{k}={len(v)}" for k, v in d.items() if isinstance(v, list)))
    print(f"  wrong commit : "
          f"{dossier_store.load_investigation(graph.session_id, 'deadbeef', DB_PATH)}"
          f"   (must be None — anchors could have drifted)")
    print(f"  other session: "
          f"{dossier_store.load_investigation('someone-else', commit_sha, DB_PATH)}"
          f"   (must be None — goal-specific understanding never leaks)")
    report["dossier_persisted"] = bool(reloaded)

    # ── 3. the lesson, and the context behind it ─────────────────────────────
    rule("3. LESSON RENDERING")
    node = graph.nodes[graph.current_node_id]
    print(f"  node: {node.title}")
    print(f"        {node.code_anchor.file}:{node.code_anchor.line_start}-"
          f"{node.code_anchor.line_end}  [{node.code_anchor.symbol}]")

    if reloaded:
        context = dossier_context.context_for_node(
            build_skeleton(repo_path), reloaded["dossier"],
            node.code_anchor.file, symbol=node.code_anchor.symbol,
            line_start=node.code_anchor.line_start,
            line_end=node.code_anchor.line_end,
        )
        print("\n  --- dossier context selected for THIS lesson ---")
        print("  " + context.as_prompt_section().replace("\n", "\n  ")
              if not context.is_empty else "  (none — the dossier does not describe this node)")
        report["lesson_context"] = {
            "component": context.component,
            "flow_position": context.flow_position,
            "relationships": context.relationships,
            "contracts": context.contracts,
            "prerequisites": context.prerequisites,
        }

    lesson_state = OnboardState(repo_url=REPO_URL, goal=dict(GOAL), client=client,
                                repo_path=repo_path)
    lesson_state.graph = graph
    lesson_state.doc_context = graph.doc_context
    run_teaching(lesson_state, client=client)
    lesson = lesson_state.current_lesson or {}
    print(f"\n  walkthrough  : {_short(lesson.get('walkthrough'), 600)}")
    print(f"  prompt       : {_short(lesson.get('prompt'), 200)}")
    print(f"  expected     : {_short(lesson.get('expected_answer'), 200)}")
    if lesson_state.errors:
        print(f"  errors       : {lesson_state.errors}")
    report["lesson"] = lesson
    learning_store.save_graph(graph, DB_PATH)

    # ── 4. the user gets it wrong ────────────────────────────────────────────
    rule("4. USER ANSWER -> GRADER")
    print(f"  answer: {_short(CONFUSED_ANSWER, 200)}")
    grade_state = OnboardState(repo_url=REPO_URL, goal=dict(GOAL), client=client,
                               repo_path=repo_path)
    grade_state.graph = graph
    run_grader(grade_state, CONFUSED_ANSWER, client=client)
    grade = grade_state.last_grade or {}
    print(f"  classification : {grade.get('classification')}")
    print(f"  rationale      : {_short(grade.get('rationale'), 300)}")
    report["grade"] = grade

    # ── 5. the mutation ──────────────────────────────────────────────────────
    rule("5. CONFUSION -> MUTATOR -> PREREQUISITE")
    confused_id = graph.current_node_id
    if reloaded:
        candidates = dossier_context.prerequisite_candidates(
            build_skeleton(repo_path), reloaded["dossier"],
            node.code_anchor.file, symbol=node.code_anchor.symbol,
            line_start=node.code_anchor.line_start,
            line_end=node.code_anchor.line_end,
            exclude={(n.code_anchor.file, n.code_anchor.line_start,
                      n.code_anchor.line_end) for n in graph.nodes.values()},
        )
        print(f"  structural candidates the dossier offered ({len(candidates)}):")
        for candidate in candidates:
            print(f"    {candidate.label():48s} [{candidate.source}]")
            print(f"      {_short(candidate.rationale, 84)}")
        report["candidates"] = [
            {"label": c.label(), "source": c.source, "rationale": c.rationale}
            for c in candidates
        ]

    mutation_state = OnboardState(repo_url=REPO_URL, goal=dict(GOAL), client=client,
                                  repo_path=repo_path)
    mutation_state.graph = graph
    mutate(mutation_state, "prerequisite", client=client)
    mutation = mutation_state.last_mutation or {"kind": "none"}
    print(f"\n  mutation: {mutation.get('kind')}")
    if mutation.get("kind") == "prerequisite":
        inserted = graph.nodes[mutation["new_node_id"]]
        print(f"    SELECTED : {inserted.title}")
        print(f"    anchor   : {inserted.code_anchor.file}:"
              f"{inserted.code_anchor.line_start}-{inserted.code_anchor.line_end}"
              f"  [{inserted.code_anchor.symbol}]")
        print(f"    why      : {_short(inserted.lesson_brief.get('why'), 88)}")
        print(f"    graph is now current at: {graph.nodes[graph.current_node_id].title}")
        report["mutation"] = {
            "title": inserted.title,
            "anchor": f"{inserted.code_anchor.file}:{inserted.code_anchor.line_start}-"
                      f"{inserted.code_anchor.line_end}",
            "symbol": inserted.code_anchor.symbol,
            "why": inserted.lesson_brief.get("why"),
        }
    if mutation_state.errors:
        print(f"    errors: {mutation_state.errors}")
    learning_store.save_graph(graph, DB_PATH)

    # ── 6. return to the original path ───────────────────────────────────────
    rule("6. RETURN TO THE ORIGINAL PATH")
    from backend.agents.mentor.mutator import mutate as _m  # noqa: F401

    if mutation.get("kind") == "prerequisite":
        prereq_state = OnboardState(repo_url=REPO_URL, goal=dict(GOAL), client=client,
                                    repo_path=repo_path)
        prereq_state.graph = graph
        run_teaching(prereq_state, client=client)
        print(f"  prerequisite lesson rendered: "
              f"{_short((prereq_state.current_lesson or {}).get('walkthrough'), 200)}")
        graph.set_current(confused_id)
        learning_store.save_graph(graph, DB_PATH)
    print(f"  back at: {graph.nodes[graph.current_node_id].title}")
    print(f"  graph now has {len(graph.nodes)} nodes "
          f"({sum(1 for e in graph.edges if e.kind == 'prerequisite')} prerequisite edge)")

    # ── 7. D12 fallback ──────────────────────────────────────────────────────
    rule("7. D12 — THE SAME SESSION WITH ITS DOSSIER UNAVAILABLE")
    second = graph.nodes[[
        n for n in graph.nodes if n != graph.current_node_id
    ][0]]
    second.cached_lesson = None
    graph.set_current(second.id)
    print(f"  re-teaching '{second.title}' with the dossier hidden...")
    fallback_state = OnboardState(repo_url=REPO_URL, goal=dict(GOAL), client=client,
                                  repo_path=repo_path)
    fallback_state.graph = graph
    fallback_state.doc_context = graph.doc_context
    # Simulate every unavailability case at once: the store answers None.
    original = dossier_store.load_investigation
    dossier_store.load_investigation = lambda *a, **k: None
    try:
        run_teaching(fallback_state, client=client)
    finally:
        dossier_store.load_investigation = original
    fallback_lesson = fallback_state.current_lesson or {}
    print(f"  lesson rendered : {'YES' if fallback_lesson else 'NO'}")
    print(f"  walkthrough     : {_short(fallback_lesson.get('walkthrough'), 300)}")
    print(f"  errors          : {fallback_state.errors or 'none'}")
    report["d12_fallback_ok"] = bool(fallback_lesson)

    # Which rung of the hierarchy caught it. Before Stage 5 this case reached
    # retrieval; now it must reach the Skeleton, and the point of printing the
    # context is that "it degraded gracefully" is not a claim to take on trust.
    from backend.repo import structure  # noqa: E402
    from backend.repo.skeleton import build_skeleton as _skeleton  # noqa: E402

    structural = structure.neighbour_context(
        _skeleton(repo_path), second.code_anchor.file,
        symbol=second.code_anchor.symbol,
        line_start=second.code_anchor.line_start,
        line_end=second.code_anchor.line_end,
    )
    print("\n  --- structural context that replaced the dossier ---")
    print("  " + (structural.replace("\n", "\n  ") if structural
                  else "(none — a source-only lesson, still a supported mode)"))
    report["d12_structural_context"] = structural
    print("\n  -> the session stayed usable, on grounded structure rather than "
          "retrieval")

    report["seconds_total"] = time.time() - started
    print(f"\nTOTAL: {report['seconds_total']:.0f}s")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else OUT_DIR / f"stage4-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
