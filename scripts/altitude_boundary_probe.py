"""Is `right_idea_wrong_altitude` ever used for a claim that is false at EVERY level?

    uv run python scripts/altitude_boundary_probe.py --dry-run
    CODEONBOARD_GAPS=1 uv run python scripts/altitude_boundary_probe.py

THE PRINCIPLE UNDER TEST
    A claim that is false regardless of abstraction level should never be
    `right_idea_wrong_altitude`. Both definitions already say so — the base
    prompt requires "the substance is right", and the addendum requires the
    claim be "true of the implementation but false as a statement about
    responsibility, or the reverse". The question is whether the prompt makes
    that clear enough in practice.

WHY A PROBE RATHER THAN THE CORPUS
    28 altitude gaps have been recorded across the phase's evidence. Judged by
    hand, 27 are legitimate: the FastAPI family is a granularity error whose
    coarse claim is true ("get() leads to add_api_route()" — the elision of
    api_route() is the error), and the `prepare_content_length` family is true
    of the implementation and wrong in scope. Exactly one — AIMA's "solution()
    returns states as well as actions" — is false at every level.
    1 of 28 is a borderline judgement, not a measurement. The corpus is also
    dominated by a handful of repeated scenarios, so it cannot answer the
    general question.

THE DESIGN
    Two authored sets with known ground truth, each embedded as a one-claim
    answer against a real node with a real objective:

      FALSE_EVERYWHERE  no reading at any altitude makes it true → wrong_model
      TRUE_WRONG_LEVEL  a correct implementation fact offered as the answer to
                        a responsibility question → right_idea_wrong_altitude

    A clean separation means the prompt is sufficiently clear and nothing should
    change. Systematic leakage of FALSE_EVERYWHERE into the altitude kind would
    be the general defect worth the smallest principled correction.

    Ground truth is authored here, before any output was seen. The probe reports
    the confusion matrix; it changes no prompt.
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
from backend.learning.flags import gaps_enabled  # noqa: E402
from backend.learning.graph import LearningGraph  # noqa: E402
from backend.pipeline.state import OnboardState  # noqa: E402

DB = Path("data/sessions.db")

# (session prefix, node prefix) — real stored nodes with real objectives.
AUTH = ("a3234f413b", "b50c4cad")        # requests: auth parameter forms
AIMA = ("431af31514", "435e4fc4")        # aima: what a Node holds / solution()

CASES = [
    # ── FALSE AT EVERY LEVEL → expect wrong_model ────────────────────────────
    {
        "id": "F1-aima-solution", "node": AIMA, "expect": "wrong_model",
        "why": "solution() returns actions only; 'states too' is false at any level",
        "answer": "A Node holds the parent pointer, the action, the path cost and the "
                  "depth. When you call solution() on a goal node it walks the parent "
                  "chain and returns both the states and the actions it collected.",
    },
    {
        "id": "F2-aima-parent", "node": AIMA, "expect": "wrong_model",
        "why": "the parent pointer is set by the constructor, not the frontier",
        "answer": "A Node holds the action and the accumulated cost. The parent pointer "
                  "is attached by the frontier when the node is queued, which is how the "
                  "chain gets built up for solution() to walk later.",
    },
    {
        "id": "F3-auth-replaces", "node": AUTH, "expect": "wrong_model",
        "why": "prepare_auth mutates and syncs; it does not swap in a new object",
        "answer": "Passing auth makes prepare_auth() construct a brand-new PreparedRequest "
                  "and return that in place of the original one, so the object you started "
                  "with is discarded.",
    },
    {
        "id": "F4-auth-body", "node": AUTH, "expect": "wrong_model",
        "why": "a tuple becomes HTTPBasicAuth and an Authorization header, never body fields",
        "answer": "When you pass auth=('user','pass'), requests writes the username and "
                  "password into the request body as two separate form fields before "
                  "sending it.",
    },
    {
        "id": "F5-auth-socket", "node": AUTH, "expect": "wrong_model",
        "why": "nothing is sent during preparation; the handler cannot read a challenge",
        "answer": "The auth handler opens the connection first so it can read the server's "
                  "challenge, and only then decides which credentials to attach to the "
                  "request.",
    },
    # ── TRUE OF THE IMPLEMENTATION, WRONG LEVEL → expect altitude ────────────
    {
        "id": "T1-auth-basicauth", "node": AUTH, "expect": "right_idea_wrong_altitude",
        "why": "true of HTTPBasicAuth specifically; offered as the general contract",
        "answer": "What the auth parameter does is set "
                  "r.headers['Authorization'] = _basic_auth_str(self.username, self.password) "
                  "on the request object.",
    },
    {
        "id": "T2-auth-contentlength", "node": AUTH, "expect": "right_idea_wrong_altitude",
        "why": "prepare_auth really does end there; it is not what the auth parameter means",
        "answer": "The auth parameter's effect is that prepare_auth() finishes by calling "
                  "self.__dict__.update(r.__dict__) and then prepare_content_length(self.body).",
    },
    {
        "id": "T3-aima-depthline", "node": AIMA, "expect": "right_idea_wrong_altitude",
        "why": "the line is real; it is not what a Node holds beyond a bare state",
        "answer": "What a Node holds beyond the state is the line "
                  "self.depth = parent.depth + 1 that runs inside __init__ when a parent "
                  "is passed in.",
    },
    {
        "id": "T4-aima-listcomp", "node": AIMA, "expect": "right_idea_wrong_altitude",
        "why": "an accurate quote of the body, offered instead of what solution() gives you",
        "answer": "solution() is the list comprehension "
                  "[node.action for node in self.path()[1:]], which is what it produces "
                  "when you call it on a goal node.",
    },
]


def load(prefixes):
    import sqlite3
    sess, node_prefix = prefixes
    for (sid,) in sqlite3.connect(DB).execute("select session_id from sessions"):
        if not sid.startswith(sess):
            continue
        graph = learning_store.load_graph(sid, DB)
        if graph is None:
            continue
        for node_id, node in graph.nodes.items():
            if node_id.startswith(node_prefix):
                return graph, node
    return None, None


def grade(case, client) -> dict:
    graph, node = load(case["node"])
    if node is None:
        return {"id": case["id"], "error": "node_not_found"}
    isolated = LearningGraph(repo_url=graph.repo_url, goal=graph.goal)
    fresh = copy.deepcopy(node)
    fresh.attempts = []
    fresh.gap_state.gaps = []
    fresh.understanding_state = "not_started"
    isolated.add_node(fresh)
    isolated.set_current(fresh.id)
    state = OnboardState(repo_url=graph.repo_url, goal=graph.goal, client=client)
    state.graph = isolated
    run_grader(state, case["answer"], client=client)
    kinds = [g.kind for g in fresh.gaps]
    return {
        "id": case["id"], "expect": case["expect"], "why": case["why"],
        "classification": (state.last_grade or {}).get("classification"),
        "scalar_gap_kind": (state.last_grade or {}).get("gap_kind"),
        "gap_kinds": kinds,
        "gaps": [{"kind": g.kind, "claim": g.claim} for g in fresh.gaps],
        # The verdict is about the kind assigned to the claim under test. With
        # one false claim per answer, the leading gap is that claim.
        "got": kinds[0] if kinds else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out", default="docs/planning/phases/evidence/altitude-boundary")
    args = parser.parse_args()

    if args.dry_run:
        for c in CASES:
            graph, node = load(c["node"])
            print(f"{c['id']:<24} expect={c['expect']:<26} node={'ok' if node else 'MISSING'}")
        print(f"\ncases: {len(CASES)} (1 grading call each)")
        return 0
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY missing", file=sys.stderr)
        return 2
    if not gaps_enabled():
        print("CODEONBOARD_GAPS=1 required", file=sys.stderr)
        return 2

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=180.0)
    rows = [grade(c, client) for c in CASES]

    line = "─" * 78
    print(f"\n{line}\nALTITUDE BOUNDARY\n{line}")
    for r in rows:
        mark = "ok  " if r.get("got") == r.get("expect") else "MISS"
        print(f"  {mark} {r['id']:<24} expect={r.get('expect'):<26} got={r.get('got')}")
        for g in r.get("gaps", []):
            print(f"         [{g['kind']}] {g['claim'][:88]}")

    false_set = [r for r in rows if r.get("expect") == "wrong_model"]
    true_set = [r for r in rows if r.get("expect") == "right_idea_wrong_altitude"]
    leaked = [r for r in false_set if r.get("got") == "right_idea_wrong_altitude"]
    print(f"\n{line}\nVERDICT\n{line}")
    print(f"  false-at-every-level correctly `wrong_model`   "
          f"{sum(1 for r in false_set if r.get('got') == 'wrong_model')}/{len(false_set)}")
    print(f"  ...LEAKED into `right_idea_wrong_altitude`     {len(leaked)}/{len(false_set)}")
    print(f"  true-but-wrong-level correctly altitude        "
          f"{sum(1 for r in true_set if r.get('got') == 'right_idea_wrong_altitude')}/{len(true_set)}")
    print("\n  Leakage is the defect. A true-but-wrong-level case landing on")
    print("  `wrong_model` is a harsher call, not a false one — it costs the")
    print("  learner a correction they arguably needed anyway.")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "altitude-boundary.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"\nwritten: {out / 'altitude-boundary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
