"""Live A/B on the real failure shape: does the diagnosis change the warm-up?

Loads the actual session that exposed the defect (`9d432157`, node `63644c89`,
AIMA `search.py`), takes the actual recorded answer and Grader rationale, and
runs the REAL `_generate_prerequisite_node` twice against the REAL repository
and the REAL candidate pool:

    A  without a diagnosis  — the pre-fix behaviour
    B  with the diagnosis   — the post-fix behaviour

`_generate_prerequisite_node` is called directly rather than through `mutate`
because that node already carries a warm-up from the original live run, so the
one-per-node guard would decline before reaching selection. Everything below
that guard is the real path: real candidate pool, real Sonnet call, real
grounding against the repository.

    uv run python scripts/validate_prereq_diagnosis.py
"""

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

from backend.agents.mentor import mutator  # noqa: E402
from backend.learning import store as learning_store  # noqa: E402
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

# (session, node prefix, what this case exercises)
TARGETS = [
    ("9d4321577f2e441ea515f0e4d0595ea7", "63644c89",
     "wrong_model — the two-misconception answer that exposed the defect"),
    ("d1e5fc95e9f740f8a06f024e492248b7", "567b6d88",
     "missing_prerequisite — the shape that actually grows the graph"),
    ("a3234f413b024fbfb4242917fa34c173", "50eccc35",
     "missing_prerequisite on requests — does the new rule over-decline?"),
    ("d1e5fc95e9f740f8a06f024e492248b7", "a1f6dd40",
     "wrong_model, repo-level (Depends/use_cache) — can B still insert?"),
    ("6844db104abc464ebb3516597cbc57a8", "a3df61ad",
     "wrong_model, repo-level (actions vs result) — can B still insert?"),
]


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY missing", file=sys.stderr)
        return 2

    for session, node_prefix, label in TARGETS:
        print("\n" + "#" * 78)
        print(f"# {label}")
        print("#" * 78)
        try:
            run_case(session, node_prefix)
        except Exception as e:
            print(f"  case failed: {type(e).__name__}: {e}")
    return 0


def run_case(session: str, node_prefix: str) -> None:
    graph = learning_store.load_graph(session, DB)
    if graph is None:
        print("  session not found")
        return
    if node_prefix:
        node = next(n for i, n in graph.nodes.items() if i.startswith(node_prefix))
    else:
        # the node whose latest attempt names a missing foundation
        node = next(
            n for n in graph.nodes.values()
            if any(a.get("gap_kind") == "wrong_model" for a in n.attempts)
        )
    _ab(graph, node)


def _ab(graph, node) -> None:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=180.0)
    failed = [a for a in node.attempts if a.get("classification") != "understood"]
    attempt = (failed or node.attempts)[-1]

    diagnosis = mutator.Diagnosis.from_attempt(attempt)
    assert diagnosis is not None, "the recorded attempt carries no diagnosis"

    print(f"node       : {node.title}")
    print(f"anchor     : {node.code_anchor.file}:"
          f"{node.code_anchor.line_start}-{node.code_anchor.line_end}")
    print(f"grade      : {attempt['classification']} / {attempt['gap_kind']}")
    print(f"answer     : {len(attempt['answer'].split())} words")
    print(f"rationale  : {attempt['rationale'][:110]}...\n")

    # The graph already contains the warm-up produced by the original run; leave
    # it in place so both arms see the same "already taught" exclusion set.
    state = OnboardState(repo_url=graph.repo_url, goal=graph.goal, client=client)
    state.graph = graph
    state.repo_path = clone_repo(graph.repo_url)

    pool = mutator.candidate_pool(state, node)
    print(f"candidate pool ({len(pool)}):")
    for c in pool:
        print(f"  {c.file}:{c.symbol}  [{c.source}] {c.rationale[:70]}")
    print()

    for label, diag in (("A  no diagnosis (pre-fix)", None),
                        ("B  with diagnosis (post-fix)", diagnosis)):
        print("=" * 78)
        print(label)
        print("=" * 78)
        result = mutator._generate_prerequisite_node(state, node, client, diag)
        if isinstance(result, mutator._Declined):
            print(f"  DECLINED: {result.reason}")
        elif result is None:
            print(f"  generation failed; errors={state.errors[-2:]}")
        else:
            a = result.code_anchor
            print(f"  title    : {result.title}")
            print(f"  anchor   : {a.file}:{a.line_start}-{a.line_end}  ({a.symbol})")
            print(f"  objective: {(result.lesson_brief or {}).get('objective')}")
            print(f"  why      : {(result.lesson_brief or {}).get('why')}")
        print()


if __name__ == "__main__":
    raise SystemExit(main())
