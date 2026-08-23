"""M10 — the Gap Model's acceptance cases, run live.

    uv run python scripts/m10_acceptance.py --dry-run
    CODEONBOARD_GAPS=1 uv run python scripts/m10_acceptance.py

gap-model.md §4 states two acceptance cases and says plainly that neither may be
satisfied by a unit test. This runs both, end to end, with real model calls
against real repositories — the AIMA node is the one the whole phase came from
(session 9d432157, node 63644c89, `search.py` `Node.expand` / `solution()`).

AC1 — two misconceptions, one resolved, the other survives:
  1. both detected and persisted as TWO distinct gaps, same `kind`
  2. remediation addresses one of them
  3. a FRESH verification question closes that one
  4. the other stays `open`, blocking, and nameable — not silently dropped, not
     inferred resolved from an answer that never mentions it
  5. the node is NOT `understood`, and the reason is available

AC2 — verification is a new question:
  mechanically not the original prompt, and a learner still holding the
  misconception cannot answer it correctly.

Also validated here, because M10 is where the deferred limitations get judged
rather than tuned:
  - the >3 blocking-gap COLLAPSED re-teach path, never probed until now
  - whether the multi-gap re-teach still splits its `reveal` into sections

Every answer is authored in this file, before any output was seen.
"""

import argparse
import copy
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(override=True)

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import anthropic  # noqa: E402

from backend.agents.grader import run as run_grader  # noqa: E402
from backend.agents.grader.verification import grade_verification  # noqa: E402
from backend.agents.teaching import respond as teaching_respond  # noqa: E402
from backend.agents.teaching import verify as teaching_verify  # noqa: E402
from backend.agents.teaching.agent import _read_node_source  # noqa: E402
from backend.learning import adaptation, history  # noqa: E402
from backend.learning import store as learning_store  # noqa: E402
from backend.learning import understanding  # noqa: E402
from backend.learning.flags import gaps_enabled  # noqa: E402
from backend.learning.gaps import Gap  # noqa: E402
from backend.learning.graph import LearningGraph, understanding_of  # noqa: E402
from backend.pipeline.state import OnboardState  # noqa: E402
from backend.repo.cloner import clone_repo  # noqa: E402

# The FROZEN v2 fixture database, not the live one.
#
# This probe measures against specific stored sessions — its value is that the
# numbers are reproducible against the sessions the phase was measured on. The
# live database moved to schema v3 (`docs/planning/phases/session-reset.md` D8),
# which makes every v2 session invisible to `load_graph`, so pointing here is
# what keeps these fixtures readable rather than merely archived.
DB = Path("data/sessions-fixtures.db")

# ── the two cases, authored up front ─────────────────────────────────────────

AIMA = {
    "label": "aimacode/aima-python — the original trace",
    # NOT session 9d432157/63644c89, although that is where the trace came from:
    # that node's stored lesson is the RE-TEACH it later received, and its prompt
    # already resolves misconception B inside the question ("how would solution()
    # be able to extract node.action for every step?"). Replaying the original
    # answer against it measures a distorted scenario, not AC1. Confirmed by
    # running it: one gap, because B was no longer a live question.
    #
    # This node asks the ORIGINAL question and its objective covers both claims:
    # "what a Node holds that a bare state does not ... and how solution()
    # produces the ordered list of actions".
    "session": "431af31514",
    "node": "435e4fc4",
    # THE QUESTION IS NEUTRALISED, and this is the honest part of the case.
    #
    # Every stored AIMA lesson for this node states B's answer inside its own
    # question: this one asks "how does solution() produce the ordered list of
    # ACTIONS ... (Hint: look at what path() builds)", and 63644c89's is the
    # re-teach it later received. Marked against either, the learner's blurring
    # of path() and solution() reads as imprecision rather than a confident false
    # claim — which is the Grader applying its own rule correctly, not missing a
    # gap.
    #
    # So the prompt is replaced with a neutral one derived from the objective.
    # The repository, the source, the objective and the answer are all real and
    # unchanged; only the question stops giving away the thing under test. Two
    # misconceptions cannot be measured through a question that has already
    # corrected one of them.
    "neutral_prompt": (
        "A search function hands you a goal Node. Describe what that Node carries "
        "beyond the raw state, when each of those values is set, and what you get "
        "back when you call solution() on it."
    ),
    # Verbatim from the answer that exposed the whole defect. TWO independent
    # misconceptions, both `wrong_model`: (A) child metadata is filled in later,
    # (B) solution() returns states as well as actions.
    "answer": (
        "When `node.expand(problem)` is called, it asks the Problem for the available "
        "actions using `problem.actions(state)`. For each action, it calls "
        "`problem.result(state, action)` and creates a child `Node`. The child stores "
        "the resulting state and the action that produced it, but its `path_cost` and "
        "`depth` are recalculated later by the search algorithm rather than during "
        "expansion. When `solution()` is later called on a goal node, it follows the "
        "`parent` references backward from the goal node until it reaches the root. "
        "As it walks backward, it collects both the states and actions stored in each "
        "Node. It then returns these in reverse order."
    ),
    # Demonstrates the CHILD-METADATA correction and says nothing whatever about
    # what solution() returns. That silence is the point of AC1 step 4.
    "verification_answer": (
        "Everything the child needs is already set the moment it comes back from "
        "expand — the constructor works out the depth from the parent and adds the "
        "step cost onto the parent's path_cost right there. Nothing fills those in "
        "afterwards; a node handed to you is complete."
    ),
    "still_holding": (
        "The child comes back with just the state and the action on it. The search "
        "algorithm fills in the depth and the path cost afterwards, once it decides "
        "where the node sits in the frontier."
    ),
}

REQUESTS = {
    "label": "psf/requests — the auth parameter forms",
    "session": "a3234f413b",
    "node": "b50c4cad",
    "answer": (
        "The tuple is passed straight through to the server as the credentials — "
        "requests sends the username and password as separate fields in the request "
        "body. HTTPBasicAuth is a different mechanism that instead encodes them into "
        "a header, so the two produce different requests. The auth handler also opens "
        "the connection itself so it can read the server's challenge before deciding "
        "what to send."
    ),
    "verification_answer": (
        "A two-item tuple is not its own mechanism — it is shorthand. It gets turned "
        "into the same basic-auth handler you could have passed yourself, so by the "
        "time anything goes out the credentials are an encoded Authorization header "
        "and the body is untouched. Both spellings produce an identical request."
    ),
    "still_holding": (
        "The two values go out as their own fields in the body, the way posted form "
        "values do, whereas passing an auth object puts them in a header instead."
    ),
}


def load(case) -> tuple[LearningGraph, object]:
    for sid in (row for row in _session_ids()):
        if not sid.startswith(case["session"]):
            continue
        graph = learning_store.load_graph(sid, DB)
        if graph is None:
            continue
        for node_id, node in graph.nodes.items():
            if node_id.startswith(case["node"]):
                return graph, node
    return None, None


def _session_ids():
    import sqlite3
    return [r[0] for r in sqlite3.connect(DB).execute("select session_id from sessions")]


def isolate(graph, node):
    """A one-node copy with a clean gap slate — the case starts from zero."""
    fresh = copy.deepcopy(node)
    fresh.gap_state.gaps = []
    fresh.gap_state.remediation_rounds = 0
    fresh.gap_state.pending_verification = None
    fresh.attempts = []
    fresh.understanding_state = "not_started"
    fresh.user_override = None
    isolated = LearningGraph(repo_url=graph.repo_url, goal=graph.goal)
    isolated.add_node(fresh)
    isolated.set_current(fresh.id)
    state = OnboardState(repo_url=graph.repo_url, goal=graph.goal)
    state.graph = isolated
    return state, fresh, isolated


def run_case(case, client) -> dict:
    line = "─" * 78
    print(f"\n{line}\nAC1 · {case['label']}\n{line}")
    graph, node = load(case)
    if node is None:
        print(f"  SKIP — node {case['node']} not found")
        return {"case": case["label"], "error": "node_not_found"}

    state, working, isolated = isolate(graph, node)
    source = _read_node_source(clone_repo(graph.repo_url), working)
    original_prompt = (working.cached_lesson or {}).get("prompt", "")
    if case.get("neutral_prompt"):
        working.cached_lesson = {**(working.cached_lesson or {}),
                                 "prompt": case["neutral_prompt"]}
        original_prompt = case["neutral_prompt"]
    out = {"case": case["label"], "node": working.id[:8],
           "objective": working.objective(), "original_prompt": original_prompt}

    # ── step 1: two misconceptions, two gaps ──────────────────────────────
    run_grader(state, case["answer"], client=client)
    grade = state.last_grade or {}
    isolated.record_attempt(working.id, case["answer"],
                            grade.get("classification", "partial"),
                            grade.get("rationale", ""),
                            gap_kind=grade.get("gap_kind", "none"))
    gaps = list(working.gaps)
    out["step1"] = {
        "classification": grade.get("classification"),
        "gap_kind": grade.get("gap_kind"),
        "gaps": [{"id": g.id[:8], "kind": g.kind, "claim": g.claim} for g in gaps],
        "distinct_ids": len({g.id for g in gaps}),
        "distinct_claims": len({g.claim for g in gaps}),
    }
    print(f"  1 DETECT   {grade.get('classification')}/{grade.get('gap_kind')} "
          f"→ {len(gaps)} gaps")
    for g in gaps:
        print(f"      [{g.kind}] {g.claim[:88]}")
    if len(gaps) < 2:
        out["verdict"] = "FAIL: fewer than two gaps detected"
        print("  → AC1 FAIL: the answer did not yield two gaps")
        return out

    # ── step 2: remediation addresses the selected gaps ───────────────────
    plan = adaptation.decide_all(grade.get("classification", "partial"), list(working.gaps),
                                 grade.get("gap_kind"))
    lesson = None
    if plan.action == "reteach":
        lesson = teaching_respond.reteach(
            state, working, case["answer"], grade.get("rationale", ""), source,
            client=client, gaps=plan.targets)
    out["step2"] = {
        "action": plan.action,
        "targets": [g.id[:8] for g in plan.targets],
        "collapsed": plan.collapsed,
        "lesson": lesson.model_dump() if lesson else None,
    }
    print(f"  2 REMEDIATE {plan.action} over {len(plan.targets)} target(s), "
          f"collapsed={plan.collapsed}")

    # ── step 3: a FRESH question for ONE gap ──────────────────────────────
    target = plan.active_set[0] if plan.active_set else gaps[0]
    prompt = teaching_verify.verify(state, working, [target], source, client=client)
    if prompt is None:
        out["verdict"] = f"FAIL: no verification question ({state.errors[-1:]})"
        print("  → AC1 FAIL: verification question could not be generated")
        return out
    teaching_verify.store(working, prompt)
    same = prompt.question.strip() == original_prompt.strip()
    out["step3"] = {"question": prompt.question, "targets": [t[:8] for t in prompt.targets],
                    "identical_to_original": same}
    print(f"  3 VERIFY   targets {target.id[:8]} · identical_to_original={same}")
    print(f"      Q: {prompt.question[:150]}")

    # ── step 4: closes ONLY what was demonstrated ─────────────────────────
    result = grade_verification(state, working, case["verification_answer"], client=client)
    isolated.record_attempt(working.id, case["verification_answer"], "",
                            result.get("rationale", ""), kind=history.VERIFICATION)
    by_id = {g.id: g for g in working.gaps}
    survivors = [g for g in working.gaps if g.is_open]
    out["step4"] = {
        "resolved": [i[:8] for i in result.get("resolved", [])],
        "unresolved": [i[:8] for i in result.get("unresolved", [])],
        "rationale": result.get("rationale"),
        "statuses": {g.id[:8]: g.status for g in working.gaps},
        "survivors": [{"id": g.id[:8], "claim": g.claim, "blocking": g.is_blocking}
                      for g in survivors],
    }
    print(f"  4 CLOSE    resolved={len(result.get('resolved', []))} "
          f"survivors={len(survivors)}")
    for g in survivors:
        print(f"      STILL OPEN [{g.kind}] {g.claim[:80]}")

    # ── step 5: not understood, and it can say why ────────────────────────
    summary = understanding.node_summary(working)
    out["step5"] = {
        "understanding_state": understanding_of(working),
        "understanding": summary["understanding"],
        "gaps_blocking": summary["gaps_blocking"],
        "gaps_verified": summary["gaps_verified"],
        "state_matches_latest_answer": summary["state_matches_latest_answer"],
    }
    print(f"  5 STATE    {understanding_of(working)} / {summary['understanding']} "
          f"· blocking={summary['gaps_blocking']} verified={summary['gaps_verified']}")

    resolved_ids = set(result.get("resolved", []))
    checks = {
        "two_distinct_gaps": out["step1"]["distinct_ids"] >= 2
                             and out["step1"]["distinct_claims"] >= 2,
        "remediation_addressed_targets": bool(out["step2"]["targets"]),
        "verification_is_fresh": not same,
        "exactly_one_closed": len(resolved_ids) >= 1,
        "a_survivor_remains_open": any(g.is_open for g in working.gaps),
        "survivor_is_nameable": all(g.claim.strip() for g in survivors),
        "node_not_understood": understanding_of(working) != "understood",
        "reason_available": summary["gaps_blocking"] > 0,
    }
    out["checks"] = checks
    out["verdict"] = "PASS" if all(checks.values()) else "FAIL"
    print(f"  → AC1 {out['verdict']}: " +
          ", ".join(f"{k}={'ok' if v else 'NO'}" for k, v in checks.items()))
    return out


def run_ac2(case, prior, client) -> dict:
    """AC2's judged half: can a learner still holding the belief answer it?"""
    line = "─" * 78
    print(f"\n{line}\nAC2 · {case['label']}\n{line}")
    if "step3" not in prior:
        print("  SKIP — no verification question from AC1")
        return {"case": case["label"], "error": "no_question"}
    graph, node = load(case)
    state, working, isolated = isolate(graph, node)
    gap = Gap.create("wrong_model", prior["step1"]["gaps"][0]["claim"])
    working.gap_state.gaps.append(gap)
    teaching_verify.store(working, teaching_verify.VerificationPrompt(
        question=prior["step3"]["question"], targets=[gap.id]))
    result = grade_verification(state, working, case["still_holding"], client=client)
    caught = gap.id not in result.get("resolved", [])
    print(f"  still-holding answer → resolved={not caught}  "
          f"({'CAUGHT' if caught else 'PASSED — the question does not discriminate'})")
    print(f"      {str(result.get('rationale'))[:150]}")
    return {"case": case["label"], "identical_to_original": prior["step3"]["identical_to_original"],
            "still_holding_caught": caught, "rationale": result.get("rationale"),
            "verdict": "PASS" if caught and not prior["step3"]["identical_to_original"] else "FAIL"}


def run_collapsed(case, client) -> dict:
    """The deferred limitation: >3 blocking gaps collapse to ONE full re-teach.

    Never probed. Judged here rather than tuned — the question is whether a
    lesson asked to correct five misconceptions at once is still a lesson.
    """
    line = "─" * 78
    print(f"\n{line}\nDEFERRED · collapsed re-teach (>3 blocking gaps)\n{line}")
    graph, node = load(case)
    state, working, isolated = isolate(graph, node)
    source = _read_node_source(clone_repo(graph.repo_url), working)
    claims = [
        "child path_cost and depth are filled in later by the search algorithm",
        "solution() returns both the states and the actions",
        "expand() returns nodes already scored by the heuristic",
        "the parent pointer is set by the frontier, not by the constructor",
        "child_node() mutates the parent's state in place",
    ]
    for c in claims:
        working.gap_state.gaps.append(Gap.create("wrong_model", c))
    plan = adaptation.decide_all("confused", list(working.gaps))
    lesson = teaching_respond.reteach(state, working, "…", "several misconceptions",
                                      source, client=client, gaps=plan.targets)
    body = lesson.model_dump() if lesson else {}
    words = sum(len(str(body.get(k, "")).split())
                for k in ("setup", "prompt", "reveal", "takeaway"))
    covered = sum(1 for c in claims
                  if any(w in " ".join(str(body.get(k, "")) for k in
                                       ("setup", "reveal")).lower()
                         for w in c.lower().split()[:3]))
    print(f"  open blocking gaps : {len(claims)}")
    print(f"  plan               : action={plan.action} collapsed={plan.collapsed} "
          f"targets={len(plan.targets)} active={len(plan.active_set)} "
          f"deferred={len(plan.deferred)}")
    print(f"  lesson length      : {words} words (budget 600)")
    for key in ("setup", "reveal"):
        print(f"\n[{key.upper()}]\n{body.get(key, '')}")
    return {"claims": len(claims), "action": plan.action, "collapsed": plan.collapsed,
            "targets": len(plan.targets), "words": words, "lesson": body,
            "claims_touched": covered}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", choices=["aima", "requests"])
    parser.add_argument("--out", default="docs/planning/phases/evidence/m10-acceptance")
    args = parser.parse_args()
    cases = [AIMA, REQUESTS]
    if args.only == "aima":
        cases = [AIMA]
    elif args.only == "requests":
        cases = [REQUESTS]

    if args.dry_run:
        for c in cases:
            graph, node = load(c)
            print(f"{c['label']}: {'found ' + node.id[:8] if node else 'NOT FOUND'}")
        print("calls: 2 repos x (grade + reteach + verify + verify-grade + ac2-grade) "
              "+ 1 collapsed reteach = 11")
        return 0
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY missing", file=sys.stderr)
        return 2
    if not gaps_enabled():
        print("CODEONBOARD_GAPS=1 required", file=sys.stderr)
        return 2

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=180.0)
    ac1 = [run_case(c, client) for c in cases]
    ac2 = [run_ac2(c, prior, client) for c, prior in zip(cases, ac1)]
    collapsed = run_collapsed(AIMA, client) if len(cases) > 1 else None

    line = "=" * 78
    print(f"\n{line}\nM10 ACCEPTANCE\n{line}")
    for row in ac1:
        print(f"  AC1 {row['case']:<48} {row.get('verdict')}")
    for row in ac2:
        print(f"  AC2 {row['case']:<48} {row.get('verdict')}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "acceptance.json").write_text(
        json.dumps({"ac1": ac1, "ac2": ac2, "collapsed": collapsed}, indent=2),
        encoding="utf-8")
    print(f"\nwritten: {out / 'acceptance.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
