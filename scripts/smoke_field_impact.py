"""
Side-by-side proof that goal fields shape the graph — not just the wording.

Runs the pipeline TWICE on the same repo + goal_type with two CONTRASTING
field-setting combinations:

    RUN A — overview / diving-into-source / prototype
    RUN B — deep / starting-fresh / production-critical

Same repo, same goal_type (improve_existing_system), same change_target,
same focus_area, same Reviewer / Mentor / retrieval pipeline. The only
things that differ are `depth`, `familiarity`, `background`, and
`risk_tolerance`.

If the calibration rules in the Mentor / Reviewer / Teaching system prompts
are doing real work, the resulting graphs will differ in:
  - node count (depth)
  - presence and density of orientation nodes (familiarity)
  - skipped-foundational nodes (background)
  - risk + test_coverage density (risk_tolerance)
  - SEQUENCE ORDERING for safety-critical risk_tolerance: every
    extension_point preceded in the chain by a risk and a test_coverage
    node. (The initial graph is pure sequence — by architectural decision,
    prerequisite edges are reserved for the Mutator's session-time
    response to user confusion.)

If the runs come out nearly identical, the prompt rules are not landing and
need to be sharpened — that's the point of this demo. It is not a happy-path
showcase; it is a behavioural check.

Repo-agnostic: defaults to psf/requests but accepts --repo for any GitHub URL.

Cost: 2 full pipeline runs (~$0.30-0.50 in API calls); ~90-120s on a warm
cache. Needs ANTHROPIC_API_KEY in .env.

Run with:
    .venv\\Scripts\\python.exe scripts\\smoke_field_impact.py
or:
    .venv\\Scripts\\python.exe scripts\\smoke_field_impact.py --repo https://github.com/fastapi/fastapi
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

from dotenv import load_dotenv
from fastapi.testclient import TestClient

import backend.api as api
from backend.learning import store as learning_store
from backend.learning.graph import LearningGraph


load_dotenv(override=True)

DEFAULT_REPO = "https://github.com/psf/requests"


# A goal generic enough to work on any library / framework. We deliberately
# avoid naming specific classes or extension points — those are the kind of
# repo-specific signals that would skew the comparison. The Mentor and
# Reviewer figure out the right anchors from the module map and retrieval.
def make_base_goal(repo_url: str) -> dict:
    return {
        "primary_goal": (
            "Safely extend an existing extension point in this codebase "
            "with a new implementation of the contract it exposes"
        ),
        "goal_type": "improve_existing_system",
        "focus_area": "the primary extension surface this codebase exposes",
        # experience_level and depth are normally LLM-synthesized; here we
        # set them directly per run since we want to test depth as a lever.
        "experience_level": "intermediate",
        "depth": "moderate",          # overridden per run
        "target_repo": repo_url,
        "familiarity": "",            # overridden per run
        "background": "",             # overridden per run
        "change_target": (
            "add a new subclass of the primary extension contract this "
            "codebase exposes"
        ),
        "risk_tolerance": "",         # overridden per run
    }


# The two contrast runs. Familiarity strings match the Goal Agent's enum
# literals so the Mentor's substring-match calibration rules fire reliably.
# Background uses two profiles that are FAR apart in what they assume the
# user knows — strongest signal that the assumed-knowledge gate fires.
RUNS = [
    {
        "label": "RUN A",
        "subtitle": "overview / diving-into-source / prototype",
        "overrides": {
            "depth": "overview",
            "familiarity": "Used it before, now diving into the source",
            "background": "Python, 10 years, deep CPython internals",
            "risk_tolerance": (
                "prototype, can break — exploring the design space"
            ),
        },
    },
    {
        "label": "RUN B",
        "subtitle": "deep / starting-fresh / production-critical",
        "overrides": {
            "depth": "deep",
            "familiarity": "Starting fresh — never looked at it",
            "background": "Embedded C++, new to Python",
            "risk_tolerance": (
                "production use, must not regress — safety-critical"
            ),
        },
    },
]


SMOKE_DB = Path("data/smoke_field_impact_sessions.db")


# ── Concept-tag taxonomy ──────────────────────────────────────────────────────


NEW_TAGS = (
    "architecture",
    "flow",
    "extension_point",
    "risk",
    "test_coverage",
    "component",
)


def dominant_new_tag(tags: list[str]) -> str | None:
    """Same picker the Teaching Agent's framing branch uses — first match wins."""
    for t in tags:
        if t in NEW_TAGS:
            return t
    return None


# ── Graph measurements ────────────────────────────────────────────────────────


def _chain_order(graph: LearningGraph) -> list:
    """Walk the initial sequence chain and return nodes in order.

    The Mentor's initial graph is, by architectural decision, a pure
    sequence chain. We follow sequence edges from the head (no incoming
    sequence edge) until exhausted. Any node not reachable through the
    chain is appended at the end (defensive — should not happen).
    """
    next_id: dict[str, str] = {
        e.from_node_id: e.to_node_id for e in graph.edges if e.kind == "sequence"
    }
    incoming = {e.to_node_id for e in graph.edges if e.kind == "sequence"}
    heads = [nid for nid in graph.nodes if nid not in incoming]
    if not heads:
        return list(graph.nodes.values())
    head = heads[0]

    order: list = []
    seen: set[str] = set()
    cur: str | None = head
    while cur is not None and cur not in seen:
        seen.add(cur)
        order.append(graph.nodes[cur])
        cur = next_id.get(cur)
    for nid, node in graph.nodes.items():
        if nid not in seen:
            order.append(node)
    return order


def measure(graph: LearningGraph) -> dict:
    """Return a dict of the metrics the side-by-side cares about."""
    tag_buckets: dict[str, int] = {t: 0 for t in NEW_TAGS}
    tag_buckets["other"] = 0

    # Concept-tag distribution by dominant tag.
    nodes_by_id = graph.nodes
    for node in nodes_by_id.values():
        bucket = dominant_new_tag(node.concept_tags) or "other"
        tag_buckets[bucket] += 1

    seq_edges = [e for e in graph.edges if e.kind == "sequence"]
    non_sequence_edges = [e for e in graph.edges if e.kind != "sequence"]

    # Safety-critical signal expressed as ORDERING (not edge kinds): for each
    # extension_point node in the chain, was at least one risk node and at
    # least one test_coverage node teaching the same area visited earlier in
    # the path? This is the constraint the improve_existing_system builder
    # expresses for safety-critical risk_tolerance.
    chain = _chain_order(graph)
    extensions_guarded_by_risk = 0
    extensions_guarded_by_test = 0
    extensions_total = 0
    seen_risk_before = False
    seen_test_before = False
    for node in chain:
        tags = set(node.concept_tags)
        if "risk" in tags:
            seen_risk_before = True
        if "test_coverage" in tags:
            seen_test_before = True
        if "extension_point" in tags:
            extensions_total += 1
            if seen_risk_before:
                extensions_guarded_by_risk += 1
            if seen_test_before:
                extensions_guarded_by_test += 1

    # Entry point: the head of the sequence chain.
    entry_node = chain[0] if chain else None

    return {
        "node_count": len(nodes_by_id),
        "sequence_edges": len(seq_edges),
        "non_sequence_edges_in_initial_graph": len(non_sequence_edges),
        "extensions_total": extensions_total,
        "extensions_guarded_by_risk": extensions_guarded_by_risk,
        "extensions_guarded_by_test": extensions_guarded_by_test,
        "tag_buckets": tag_buckets,
        "entry_node_title": entry_node.title if entry_node else "(none)",
        "entry_node_tags": list(entry_node.concept_tags) if entry_node else [],
        "entry_node_dominant_tag": dominant_new_tag(entry_node.concept_tags) if entry_node else None,
    }


# ── Pipeline driving ─────────────────────────────────────────────────────────


def run_once(client: TestClient, goal: dict) -> tuple[dict | None, str]:
    """Force a fresh /session/start so we get a new Mentor call, then load
    the resulting graph and return its measurements. Returns (measurements,
    note). The note carries any errors or fallback messages."""
    resp = client.post(
        "/session/start",
        json={"repo_url": goal["target_repo"], "goal": goal, "force_new": True},
    )
    if resp.status_code != 200:
        return None, f"start failed: HTTP {resp.status_code} — {resp.json()}"

    body = resp.json()
    session_id = body["session_id"]
    graph = learning_store.load_graph(session_id, SMOKE_DB)
    if graph is None:
        return None, f"could not load session {session_id} from {SMOKE_DB}"

    measurements = measure(graph)
    note = ""
    if body.get("errors"):
        note = f"start returned errors: {body['errors']}"
    return measurements, note


# ── Comparison printing ───────────────────────────────────────────────────────


def _row(label: str, a: object, b: object, indent: int = 0) -> str:
    prefix = " " * indent
    return f"{prefix}{label:<35} | {str(a):<22} | {str(b):<22}"


def print_side_by_side(label_a: str, label_b: str, m_a: dict, m_b: dict) -> None:
    print()
    print("=" * 88)
    print(f"  COMPARISON  ({label_a}  vs  {label_b})")
    print("=" * 88)
    print()
    header = f"  {'metric':<35} | {label_a:<22} | {label_b:<22}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    print(_row("node count",
              m_a["node_count"], m_b["node_count"], indent=2))
    print(_row("sequence edges",
              m_a["sequence_edges"], m_b["sequence_edges"], indent=2))
    print(_row("non-sequence edges in initial graph",
              m_a["non_sequence_edges_in_initial_graph"],
              m_b["non_sequence_edges_in_initial_graph"], indent=2))
    print()
    print("  Safety-critical ordering (sequence-only — no new edge kinds):")
    print(_row("  extension_point nodes total",
              m_a["extensions_total"], m_b["extensions_total"], indent=2))
    print(_row("  …preceded in chain by a risk",
              m_a["extensions_guarded_by_risk"],
              m_b["extensions_guarded_by_risk"], indent=2))
    print(_row("  …preceded in chain by a test_coverage",
              m_a["extensions_guarded_by_test"],
              m_b["extensions_guarded_by_test"], indent=2))
    print()
    print("  Concept-tag distribution (dominant tag per node):")
    for tag in NEW_TAGS:
        print(_row(f"  {tag}",
                  m_a["tag_buckets"].get(tag, 0),
                  m_b["tag_buckets"].get(tag, 0), indent=2))
    print(_row("  other (free-form only)",
              m_a["tag_buckets"].get("other", 0),
              m_b["tag_buckets"].get("other", 0), indent=2))
    print()
    print("  Entry-point node:")
    print(_row("  dominant tag",
              m_a["entry_node_dominant_tag"] or "—",
              m_b["entry_node_dominant_tag"] or "—", indent=2))
    print()
    print(f"  {label_a} entry: {m_a['entry_node_title']}")
    print(f"  {label_b} entry: {m_b['entry_node_title']}")
    print()


def print_interpretation(m_a: dict, m_b: dict) -> None:
    """Plain-language interpretation of the comparison — directional, not
    exact. This is what tells you whether the calibration rules worked."""
    print("=" * 88)
    print("  INTERPRETATION (directional — LLMs don't produce exact numbers)")
    print("=" * 88)
    notes: list[str] = []

    # Depth — node count.
    if m_b["node_count"] > m_a["node_count"]:
        notes.append(
            f"  ✓ depth=deep produced MORE nodes "
            f"({m_b['node_count']}) than depth=overview ({m_a['node_count']})."
        )
    elif m_b["node_count"] == m_a["node_count"]:
        notes.append(
            f"  ⚠ depth did NOT change node count (both {m_a['node_count']}). "
            f"Calibration may need sharpening."
        )
    else:
        notes.append(
            f"  ✗ depth=overview produced MORE nodes than deep — calibration "
            f"rule is mis-firing."
        )

    # Familiarity — entry-point altitude.
    high_alt_a = m_a["entry_node_dominant_tag"] in ("extension_point", "risk", "component")
    high_alt_b = m_b["entry_node_dominant_tag"] in ("architecture", "flow")
    if high_alt_a and high_alt_b:
        notes.append(
            "  ✓ familiarity rules fired: RUN A (diving in) entered at a "
            "deep node; RUN B (starting fresh) entered at an architecture/"
            "flow node."
        )
    elif m_a["entry_node_dominant_tag"] != m_b["entry_node_dominant_tag"]:
        notes.append(
            f"  ~ entry-point dominant tag differs across runs "
            f"({m_a['entry_node_dominant_tag']} vs "
            f"{m_b['entry_node_dominant_tag']}) — partial familiarity signal."
        )
    else:
        notes.append(
            f"  ⚠ entry-point dominant tag is identical "
            f"({m_a['entry_node_dominant_tag']}) — familiarity may not be firing."
        )

    # Risk tolerance — risk and test_coverage density.
    risk_a = m_a["tag_buckets"].get("risk", 0)
    risk_b = m_b["tag_buckets"].get("risk", 0)
    tc_a = m_a["tag_buckets"].get("test_coverage", 0)
    tc_b = m_b["tag_buckets"].get("test_coverage", 0)
    if risk_b > risk_a:
        notes.append(
            f"  ✓ risk_tolerance=safety-critical produced MORE risk nodes "
            f"({risk_b}) than prototype ({risk_a})."
        )
    else:
        notes.append(
            f"  ⚠ risk node count did not increase under safety-critical "
            f"({risk_a} vs {risk_b}) — calibration may not be firing."
        )
    if tc_b > tc_a:
        notes.append(
            f"  ✓ risk_tolerance=safety-critical produced MORE test_coverage "
            f"nodes ({tc_b}) than prototype ({tc_a})."
        )
    else:
        notes.append(
            f"  ⚠ test_coverage node count did not increase under "
            f"safety-critical ({tc_a} vs {tc_b})."
        )

    # Risk_tolerance — safety-critical ordering. Sequence-only.
    if m_b["extensions_total"] == 0:
        notes.append(
            "  ⚠ RUN B produced no extension_point nodes, so the safety "
            "ordering check is vacuous. risk_tolerance may not be steering "
            "the tag mix as intended."
        )
    else:
        ratio_b_risk = m_b["extensions_guarded_by_risk"] / m_b["extensions_total"]
        ratio_b_test = m_b["extensions_guarded_by_test"] / m_b["extensions_total"]
        if ratio_b_risk == 1.0 and ratio_b_test == 1.0:
            notes.append(
                f"  ✓ safety-critical satisfied the ordering invariant: "
                f"every extension_point ({m_b['extensions_total']}) is "
                f"preceded in the sequence chain by a risk AND a "
                f"test_coverage node."
            )
        elif ratio_b_risk >= 0.5:
            notes.append(
                f"  ~ safety-critical partial: "
                f"{m_b['extensions_guarded_by_risk']} of "
                f"{m_b['extensions_total']} extension_point nodes are "
                f"preceded by a risk; "
                f"{m_b['extensions_guarded_by_test']} of "
                f"{m_b['extensions_total']} preceded by a test_coverage."
            )
        else:
            notes.append(
                f"  ⚠ safety-critical ordering rule did NOT land: "
                f"only {m_b['extensions_guarded_by_risk']} of "
                f"{m_b['extensions_total']} extension_point nodes are "
                f"preceded by a risk. The improve_existing_system builder "
                f"ordering rule needs sharpening."
            )

    # The non-sequence edges count should ALWAYS be 0 in the initial graph
    # — per architectural decision, only the Mutator emits prerequisite edges
    # at session time.
    if (m_a["non_sequence_edges_in_initial_graph"] > 0
            or m_b["non_sequence_edges_in_initial_graph"] > 0):
        notes.append(
            f"  ✗ unexpected non-sequence edge(s) found in initial graph "
            f"(A: {m_a['non_sequence_edges_in_initial_graph']}, "
            f"B: {m_b['non_sequence_edges_in_initial_graph']}). The "
            f"EdgeWire schema should reject this — check for a regression."
        )

    for note in notes:
        print(note)
    print()


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=DEFAULT_REPO,
                        help="GitHub repo URL to onboard against")
    args = parser.parse_args()

    api.SESSIONS_DB_PATH = SMOKE_DB
    if SMOKE_DB.exists():
        SMOKE_DB.unlink()
    client = TestClient(api.app)

    print(f"repo: {args.repo}")
    print(f"goal_type: improve_existing_system")
    print()

    results: list[tuple[str, str, dict | None, str]] = []
    for run in RUNS:
        print("─" * 88)
        print(f"  {run['label']}  ({run['subtitle']})")
        print("─" * 88)
        goal = make_base_goal(args.repo)
        goal.update(run["overrides"])
        for k, v in run["overrides"].items():
            print(f"    {k}: {v}")
        print()
        print("  POST /session/start (force_new=True) → live pipeline…")
        m, note = run_once(client, goal)
        if m is None:
            print(f"  FAILED: {note}")
            results.append((run["label"], run["subtitle"], None, note))
            continue
        if note:
            print(f"  note: {note}")
        print(f"  done: {m['node_count']} nodes, "
              f"{m['sequence_edges']} sequence edges; "
              f"{m['extensions_guarded_by_risk']}/{m['extensions_total']} "
              f"extension_points preceded by a risk in the chain")
        results.append((run["label"], run["subtitle"], m, note))

    if any(r[2] is None for r in results):
        print()
        print("One or more runs failed — cannot compare.")
        return

    m_a = results[0][2]
    m_b = results[1][2]
    print_side_by_side(results[0][0], results[1][0], m_a, m_b)
    print_interpretation(m_a, m_b)


if __name__ == "__main__":
    main()
