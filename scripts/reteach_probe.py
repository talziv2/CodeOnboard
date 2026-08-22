"""M5 — is a multi-gap re-teach still a good LESSON?

    uv run python scripts/reteach_probe.py --dry-run
    CODEONBOARD_GAPS=1 uv run python scripts/reteach_probe.py

gap-model.md M5 names the risk this measures and says no test asserts it:
"re-teach quality with 3 gaps at once — a prompt property no test asserts
(LR3-class risk)". A re-teach can name all three misconceptions, pass every
structural check, and still be a worse lesson than the one-gap version — three
corrections stapled together, in the order they were listed, with no thread.

So: the SAME real node, the SAME learner answer, re-taught three times with 1,
2 and 3 target gaps. Holding the node and the answer fixed is the point — the
only variable is how many misconceptions the lesson is asked to carry, so the
three outputs are directly comparable and any degradation is attributable.

The gaps are the real ones the Grader opened on this node during the M3 probe,
not invented for this script.

Judgement is by reading. This script measures what can be counted (is each
claim addressed, how long is the result) and prints the lessons in full for the
rest, which is the same standard §3.2's duplicate count is held to.
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

from backend.agents.teaching import respond as teaching_respond  # noqa: E402
from backend.agents.teaching.agent import _read_node_source  # noqa: E402
from backend.learning import store as learning_store  # noqa: E402
from backend.learning.flags import gaps_enabled  # noqa: E402
from backend.learning.gaps import Gap  # noqa: E402
from backend.learning.graph import LearningGraph  # noqa: E402
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

# `requests/architecture` — the AuthBase contract. Chosen because the M3 probe
# opened THREE independent `wrong_model` gaps on it from one answer, which is
# the case M5's risk is about, and they are genuinely separable: correcting any
# one leaves the other two standing.
SESSION = "a3234f413b024fbfb4242917fa34c173"
NODE_PREFIX = "7ecc5fe3"

ANSWER = (
    "The handler owns the whole authentication decision: it inspects the URL and "
    "the environment, decides whether credentials are needed at all, opens the "
    "connection so it can read the server's challenge, and then returns a fresh "
    "Request object that replaces the original one."
)
RATIONALE = (
    "The developer describes the auth handler as owning connection management and "
    "request construction, when it owns neither."
)

# Verbatim from the M3 probe's grade-1 output on this node.
CLAIMS = [
    ("The auth handler inspects the URL and environment, decides whether "
     "credentials are needed, and opens the connection.",
     "what the handler owns"),
    ("The auth handler returns a fresh Request object that replaces the original one.",
     "what the handler returns"),
    ("The auth handler opens the connection so it can read the server's challenge.",
     "where connection management lives"),
]


def load_node():
    graph = learning_store.load_graph(SESSION, DB)
    if graph is None:
        return None, None
    for node_id, node in graph.nodes.items():
        if node_id.startswith(NODE_PREFIX):
            return graph, node
    return graph, None


def run_case(graph, node, source, gaps, client) -> dict:
    """One re-teach with `gaps` targets, against an untouched copy of the node."""
    isolated = LearningGraph(repo_url=graph.repo_url, goal=graph.goal)
    fresh = copy.deepcopy(node)
    isolated.add_node(fresh)
    isolated.set_current(fresh.id)
    state = OnboardState(repo_url=graph.repo_url, goal=graph.goal, client=client)
    state.graph = isolated

    lesson = teaching_respond.reteach(
        state, fresh, ANSWER, RATIONALE, source, client=client, gaps=gaps,
    )
    if lesson is None:
        return {"error": state.errors[-1] if state.errors else "unknown"}
    return lesson.model_dump()


def coverage(lesson: dict, gaps) -> list[dict]:
    """A cheap, honest signal: does the lesson text touch each claim's subject?

    Deliberately keyword-based and deliberately NOT presented as the answer.
    Whether a claim is genuinely CORRECTED is a judgement made by reading; this
    only catches the blatant case of a claim never mentioned at all.
    """
    body = " ".join(str(lesson.get(k, "")) for k in
                    ("setup", "prompt", "reveal", "takeaway")).lower()
    out = []
    for gap in gaps:
        # The distinguishing nouns of each claim, chosen by hand.
        probes = {
            "opens the connection": ["connection", "transport", "adapter", "socket"],
            "fresh Request object": ["return", "same", "mutat", "in place", "new "],
            "inspects the URL": ["url", "environment", "decide", "whether"],
        }
        key = next((k for k in probes if k.lower() in gap.claim.lower()), None)
        hits = [w for w in probes.get(key, []) if w in body] if key else []
        out.append({"claim": gap.claim[:70], "probe": key, "hits": hits})
    return out


def show(label: str, lesson: dict, gaps) -> None:
    line = "─" * 78
    print(f"\n{line}\n{label}\n{line}")
    if "error" in lesson:
        print(f"  FAILED: {lesson['error']}")
        return
    for gap in gaps:
        print(f"  target: {gap.claim}")
    words = sum(len(str(lesson.get(k, "")).split()) for k in
                ("setup", "prompt", "reveal", "takeaway"))
    print(f"  length: {words} words")
    for key in ("setup", "prompt", "reveal", "takeaway"):
        print(f"\n[{key.upper()}]\n{lesson.get(key, '')}")
    print("\n  coverage probe:")
    for row in coverage(lesson, gaps):
        mark = "hit " if row["hits"] else "MISS"
        print(f"    {mark} {row['claim']}  -> {row['hits']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out", default="docs/planning/phases/evidence/m5-multi-gap-reteach")
    args = parser.parse_args()

    if args.dry_run:
        print(f"session {SESSION} node {NODE_PREFIX}")
        print(f"cases  : 1, 2 and 3 target gaps (3 re-teach calls)")
        for i, (claim, part) in enumerate(CLAIMS, 1):
            print(f"  gap {i}: {claim}")
        return 0

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY missing", file=sys.stderr)
        return 2
    if not gaps_enabled():
        print("CODEONBOARD_GAPS=1 required", file=sys.stderr)
        return 2

    graph, node = load_node()
    if node is None:
        print(f"node {NODE_PREFIX} not found in session {SESSION}", file=sys.stderr)
        return 2

    source = _read_node_source(clone_repo(graph.repo_url), node)
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=180.0)

    all_gaps = [Gap.create("wrong_model", c, objective_part=p) for c, p in CLAIMS]
    rows = []
    for n in (1, 2, 3):
        gaps = tuple(all_gaps[:n])
        lesson = run_case(graph, node, source, gaps, client)
        show(f"{n} TARGET GAP{'S' if n > 1 else ''}", lesson, gaps)
        rows.append({
            "targets": n,
            "gaps": [{"claim": g.claim, "objective_part": g.objective_part}
                     for g in gaps],
            "lesson": lesson,
            "coverage": coverage(lesson, gaps) if "error" not in lesson else [],
        })

    print(f"\n{'=' * 78}\nLENGTH ACROSS CASES\n{'=' * 78}")
    for row in rows:
        lesson = row["lesson"]
        if "error" in lesson:
            continue
        words = {k: len(str(lesson.get(k, "")).split())
                 for k in ("setup", "prompt", "reveal", "takeaway")}
        print(f"  {row['targets']} gap(s): total {sum(words.values()):>4}   {words}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "reteach-cases.json").write_text(
        json.dumps({"node": NODE_PREFIX, "answer": ANSWER, "cases": rows}, indent=2),
        encoding="utf-8")
    print(f"\nwritten: {out / 'reteach-cases.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
