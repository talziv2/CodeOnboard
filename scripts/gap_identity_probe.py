"""M3 — does explicit-id matching actually keep one misconception one gap?

    uv run python scripts/gap_identity_probe.py --dry-run
    uv run python scripts/gap_identity_probe.py

gap-model.md §3.2 refuses text-similarity merging: a heuristic that quietly
fuses two distinct misconceptions is worse than a duplicate. The price is that
the model can over-report `new` and duplicate a gap, and the design says that
failure "must be MEASURED during M3, not assumed away". This is that
measurement.

Three grades of one real node, in order, against the same accumulating gap list:

  1. OPEN     the `wrong_model` answer from the Grader evaluation set. It is
              already known to produce 2-3 independent false claims. Gaps open.
  2. VERBATIM the SAME answer again. Every gap it reports must match an id we
              just supplied, so ANY `new` here is a certain duplicate — no hand
              judgement is needed and none is used. This is the identity floor:
              if it fails, the strategy is broken outright.
  3. PARAPHRASE a restatement of the same false claims in entirely different
              words, authored below. This is the real test, because matching
              can no longer be done on surface text. `new` reports here are
              printed in full for the hand judgement §3.2 asks for.

The rejected count is reported too: our code discards any `refers_to` outside
the supplied set, and a non-zero rate there would mean the model is inventing
ids rather than referencing them.
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
from backend.learning import store as learning_store  # noqa: E402
from backend.learning.graph import LearningGraph  # noqa: E402
from backend.pipeline.state import OnboardState  # noqa: E402

from grader_eval_cases import ANSWERS, OBJECTIVES  # noqa: E402

# The FROZEN v2 fixture database, not the live one.
#
# This probe measures against specific stored sessions — its value is that the
# numbers are reproducible against the sessions the phase was measured on. The
# live database moved to schema v3 (`docs/planning/phases/session-reset.md` D8),
# which makes every v2 session invisible to `load_graph`, so pointing here is
# what keeps these fixtures readable rather than merely archived.
DB = Path("data/sessions-fixtures.db")

# The same false claims as `ANSWERS[prefix]["wrong_model"]`, restated so that
# almost no content words survive. Authored before any probe output was seen,
# for the same reason the Grader evaluation's labels were: a paraphrase written
# after watching what matches would be a paraphrase tuned to pass.
#
# Each one must assert exactly the original's false claims — no more, no fewer.
# Adding a new falsehood would make a legitimate `new` look like a duplicate.
PARAPHRASE = {
    # requests/component — auth parameter forms
    "b50c4cad": (
        "When you hand requests a plain (user, pass) pair, those two values travel "
        "in the body of the request as ordinary form fields. Going through "
        "HTTPBasicAuth is a different route entirely — that one builds an "
        "Authorization header instead. So the request that goes out over the wire "
        "differs depending on which of the two you pick."
    ),
    # requests/risk — response.text encoding
    "bbae87b9": (
        "This is really a speed question. The library leans on charset_normalizer "
        "to keep .text quick, so if you take it out the body ends up being decoded "
        "twice over — once for the guess and once properly. You would still get the "
        "right characters out of it; it would just crawl on large payloads."
    ),
    # requests/architecture — AuthBase contract
    "7ecc5fe3": (
        "Everything about authenticating is the handler's job. It looks at the "
        "target URL and the surrounding environment to work out whether any "
        "credentials are called for at all, establishes the connection itself so it "
        "can see what the server challenges with, and then hands back a brand-new "
        "Request that takes the place of the one it was given."
    ),
    # fastapi/architecture — app/router two layers
    "ed5b84d5": (
        "Think of them as two separate route tables that are mirrored. The "
        "application records the route locally first, which is the fast path, and "
        "afterwards duplicates it into the router so that include_router has "
        "something to pull in later. When a request arrives the app checks its own "
        "table, and only consults the router's if it comes up empty."
    ),
    # fastapi/flow — decorator-to-registration chain
    "44e85351": (
        "The call lands straight on add_api_route. get() is nothing more than a "
        "shorthand that plugs in methods=['GET'] before doing so. api_route is "
        "there purely for the case where you want to register several verbs at "
        "once, so a plain @app.get never goes near it."
    ),
    # fastapi/synthesis — declaration vs runtime
    "1699bba2": (
        "The checking happens at boot. Once every module has been imported FastAPI "
        "makes a dedicated pass over app.routes and type-checks each endpoint, and "
        "that same pass is where the dependency tree gets assembled. The decorator "
        "itself is not doing any of that work."
    ),
}


def load_node(session_id: str, prefix: str):
    graph = learning_store.load_graph(session_id, DB)
    if graph is None:
        return None, None
    for node_id, node in graph.nodes.items():
        if node_id.startswith(prefix):
            return graph, node
    return graph, None


def isolate(graph: LearningGraph, node):
    """A one-node copy that ACCUMULATES gaps across grades.

    Unlike `grader_eval.py`, which isolates each case so grades cannot influence
    one another, this probe depends on exactly that influence: grade 2 is only
    meaningful because grade 1 left gaps behind.
    """
    isolated = LearningGraph(repo_url=graph.repo_url, goal=graph.goal)
    fresh = copy.deepcopy(node)
    fresh.attempts = []
    fresh.understanding_state = "not_started"
    fresh.gap_state.gaps = []
    fresh.gap_state.remediation_rounds = 0
    isolated.add_node(fresh)
    isolated.set_current(fresh.id)
    return isolated, fresh


def grade(isolated: LearningGraph, node, answer: str, client) -> dict:
    state = OnboardState(repo_url=isolated.repo_url, goal=isolated.goal, client=client)
    state.graph = isolated
    run_grader(state, answer, client=client)
    grade_result = state.last_grade or {}
    # The real session records an attempt after every grade; `origin_attempt`
    # indexes into it, so the probe has to as well or the audit link is wrong.
    node.attempts.append({
        "answer": answer,
        "classification": grade_result.get("classification"),
        "gap_kind": grade_result.get("gap_kind"),
    })
    return grade_result


def snapshot(node) -> list[dict]:
    return [{"id": g.id, "kind": g.kind, "claim": g.claim, "status": g.status,
             "origin_attempt": g.origin_attempt} for g in node.gaps]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out", default="docs/planning/phases/evidence/m3-gap-identity")
    args = parser.parse_args()

    if args.dry_run:
        print(f"nodes      : {len(OBJECTIVES)}")
        print(f"paraphrases: {len(PARAPHRASE)}")
        for _, prefix, repo, kind, label in OBJECTIVES:
            has = "ok" if prefix in PARAPHRASE else "MISSING"
            print(f"  {repo:<9} {kind:<14} {label:<32} paraphrase={has}")
        print("\ngrades per node: 3 (open, verbatim re-grade, paraphrase re-grade)")
        print(f"total grades   : {len(OBJECTIVES) * 3}")
        return 0

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY missing", file=sys.stderr)
        return 2
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=180.0)
    rows: list[dict] = []

    for session_id, prefix, repo, kind, label in OBJECTIVES:
        graph, node = load_node(session_id, prefix)
        if node is None:
            print(f"SKIP {prefix}: node not found", file=sys.stderr)
            continue
        isolated, working = isolate(graph, node)
        print(f"\n{repo}/{kind}: {label}", flush=True)

        original = ANSWERS[prefix]["wrong_model"]
        g1 = grade(isolated, working, original, client)
        opened = snapshot(working)
        print(f"  1 OPEN       {g1.get('classification')}/{g1.get('gap_kind')}  "
              f"{len(opened)} gaps opened")
        for g in opened:
            print(f"       [{g['kind']}] {g['claim'][:96]}")

        before_verbatim = {g["id"] for g in opened}
        g2 = grade(isolated, working, original, client)
        after_verbatim = snapshot(working)
        r2 = g2.get("gap_report", {})
        dup_verbatim = [g for g in after_verbatim if g["id"] not in before_verbatim]
        print(f"  2 VERBATIM   matched={r2.get('matched')} new={r2.get('new')} "
              f"rejected={r2.get('rejected')}  -> {len(dup_verbatim)} certain duplicates")
        for g in dup_verbatim:
            print(f"       DUP [{g['kind']}] {g['claim'][:96]}")

        before_para = {g["id"] for g in after_verbatim}
        g3 = grade(isolated, working, PARAPHRASE[prefix], client)
        after_para = snapshot(working)
        r3 = g3.get("gap_report", {})
        new_para = [g for g in after_para if g["id"] not in before_para]
        print(f"  3 PARAPHRASE matched={r3.get('matched')} new={r3.get('new')} "
              f"rejected={r3.get('rejected')}  -> {len(new_para)} new gaps to judge")
        for g in new_para:
            print(f"       NEW [{g['kind']}] {g['claim'][:96]}")

        rows.append({
            "repo": repo, "kind": kind, "objective": label, "node": prefix,
            "opened": opened,
            "verbatim": {"grade": g2, "report": r2, "duplicates": dup_verbatim},
            "paraphrase": {"grade": g3, "report": r3, "new_gaps": new_para,
                           "answer": PARAPHRASE[prefix]},
            "final_gaps": after_para,
        })

    # ── report ────────────────────────────────────────────────────────────────
    line = "=" * 78
    print(f"\n{line}\nIDENTITY ACROSS RE-GRADES\n{line}")
    tot_open = sum(len(r["opened"]) for r in rows)
    v = {k: sum(r["verbatim"]["report"].get(k, 0) for r in rows)
         for k in ("matched", "new", "rejected")}
    p = {k: sum(r["paraphrase"]["report"].get(k, 0) for r in rows)
         for k in ("matched", "new", "rejected")}
    dup_v = sum(len(r["verbatim"]["duplicates"]) for r in rows)
    new_p = sum(len(r["paraphrase"]["new_gaps"]) for r in rows)
    print(f"  nodes                       {len(rows)}")
    print(f"  gaps opened by grade 1      {tot_open}")
    print(f"  VERBATIM   matched {v['matched']:<3} new {v['new']:<3} rejected {v['rejected']}")
    print(f"  PARAPHRASE matched {p['matched']:<3} new {p['new']:<3} rejected {p['rejected']}")
    print()
    print(f"  CERTAIN duplicates (verbatim re-grade)  {dup_v}")
    print(f"    -> any value above 0 means the model reported `new` for a gap it")
    print(f"       had just been shown, in identical words. The identity floor.")
    print(f"  NEW gaps after paraphrase               {new_p}")
    print(f"    -> HAND-JUDGE each: is it a semantic duplicate of an open gap, or")
    print(f"       a genuinely different false claim? §3.2 requires this by hand.")
    print(f"  Invented ids rejected by our code       {v['rejected'] + p['rejected']}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "gap-identity.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"\nwritten: {out / 'gap-identity.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
