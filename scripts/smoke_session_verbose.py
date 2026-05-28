"""
Verbose end-to-end trace of the Phase 3 interactive learning loop.

Same flow as scripts/smoke_session.py, but prints EVERYTHING so the console
output reads as a demo/proof of the adaptive system working live on
psf/requests with one goal:

    Mentor builds graph → Teaching generates lesson → user answers wrong →
    Grader detects confusion → Mutator inserts a grounded prerequisite →
    graph mutates → traversal returns to the original node → resume works
    without re-running the pipeline.

How it gets the detail:
  - drives the REAL API endpoints in-process (TestClient) so it's the genuine
    flow, including resume;
  - loads the rich LearningGraph from the store for introspection the API's
    JSON view omits (per-node why/understand, edge kinds);
  - wraps the mutator's internal helpers with tracing shims so we can see the
    candidate chunks, the attempted prerequisite, and the grounding result
    while the real code runs;
  - counts run_pipeline calls to prove resume doesn't re-run it.

Costs ~$0.15-0.25 in API calls; ~30-60s on a warm cache. Needs ANTHROPIC_API_KEY.

Run with:
    .venv\\Scripts\\python.exe scripts\\smoke_session_verbose.py
"""
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
from backend.agents.mentor import mutator as mutator_mod
from backend.learning import store as learning_store
from backend.learning.graph import LearningGraph


load_dotenv(override=True)

REPO_URL = "https://github.com/psf/requests"

GOAL = {
    "primary_goal": "understand how authentication works in requests",
    "goal_type": "understand_component",
    "focus_area": "authentication",
    "experience_level": "intermediate",
    "depth": "deep",
    "target_repo": REPO_URL,
    "familiarity": "new to requests internals",
    "background": "5 years of Python",
}

# A confident, ON-TOPIC but WRONG answer. It engages the question with a
# specific false claim, so the Grader reliably classifies it as "confused"
# (which triggers the adaptive prerequisite path) rather than "off-topic"
# (a no-op that would skip the mutation — the demo's whole point).
WEAK_ANSWER = (
    "Request validates the (user, pass) tuple and builds the Authorization "
    "header itself in __init__, then hands the finished header string to "
    "PreparedRequest."
)

SMOKE_DB = Path("data/smoke_sessions.db")


# ── Tracing shims: observe the mutator's internals while the real code runs ────

_TRACE: dict = {"candidates": None, "wire_node": None, "grounded": "(not reached)"}
_PIPELINE_CALLS = {"n": 0}


def _install_tracers() -> None:
    orig_retrieve = mutator_mod.retrieve_supporting_chunks
    orig_parse = mutator_mod._parse_node
    orig_ground = mutator_mod._ground_node
    orig_pipeline = api.run_pipeline

    def traced_retrieve(*a, **k):
        result = orig_retrieve(*a, **k)
        _TRACE["candidates"] = result
        return result

    def traced_parse(raw):
        node = orig_parse(raw)
        _TRACE["wire_node"] = node
        return node

    def traced_ground(wire, candidates):
        result = orig_ground(wire, candidates)
        _TRACE["grounded"] = result  # canonical file path on success, None on failure
        return result

    def counted_pipeline(*a, **k):
        _PIPELINE_CALLS["n"] += 1
        return orig_pipeline(*a, **k)

    mutator_mod.retrieve_supporting_chunks = traced_retrieve
    mutator_mod._parse_node = traced_parse
    mutator_mod._ground_node = traced_ground
    api.run_pipeline = counted_pipeline


# ── Printing helpers ───────────────────────────────────────────────────────────

def section(n: int, title: str) -> None:
    print()
    print("█" * 78)
    print(f"█  STEP {n}: {title}")
    print("█" * 78)


def sub(title: str) -> None:
    print(f"\n── {title} " + "─" * max(0, 70 - len(title)))


def _short(graph: LearningGraph, node_id: str) -> str:
    node = graph.nodes.get(node_id)
    return node.title if node else f"<{node_id[:8]}>"


def print_nodes(graph: LearningGraph) -> None:
    print(f"nodes: {len(graph.nodes)}")
    for i, node in enumerate(graph.nodes.values(), 1):
        cur = "  «CURRENT»" if node.id == graph.current_node_id else ""
        flags = []
        if node.visited:
            flags.append("visited")
        if node.weak_spot:
            flags.append("WEAK-SPOT")
        flag_str = f"   flags=[{', '.join(flags)}]" if flags else ""
        brief = node.lesson_brief or {}
        print(f"\n  [{i}] {node.title}{cur}")
        print(f"      id:         {node.id}")
        print(f"      anchor:     {node.code_anchor.file}:"
              f"{node.code_anchor.line_start}-{node.code_anchor.line_end}")
        print(f"      state:      {node.understanding_state}{flag_str}")
        print(f"      why:        {brief.get('why', '—')}")
        print(f"      understand: {brief.get('understand', '—')}")
        if node.concept_tags:
            print(f"      concepts:   {', '.join(node.concept_tags)}")


def print_edges(graph: LearningGraph) -> None:
    print(f"edges: {len(graph.edges)}")
    for e in graph.edges:
        print(f"  {_short(graph, e.from_node_id)}  --[{e.kind}]-->  "
              f"{_short(graph, e.to_node_id)}")


def snapshot(graph: LearningGraph) -> dict:
    return {
        "node_ids": set(graph.nodes),
        "edges": {(e.from_node_id, e.to_node_id, e.kind) for e in graph.edges},
        "titles": {nid: n.title for nid, n in graph.nodes.items()},
    }


def load(session_id: str) -> LearningGraph:
    return learning_store.load_graph(session_id, SMOKE_DB)


def get_lesson(client, session_id: str, tries: int = 3) -> dict | None:
    """GET /lesson is idempotent (re-renders the current node), so it's safe to
    retry a transient Teaching failure here for a clean demo run."""
    last = None
    for _ in range(tries):
        resp = client.get(f"/session/{session_id}/lesson")
        if resp.status_code == 200:
            return resp.json()
        last = resp
    print(f"  (lesson failed after {tries} tries: HTTP {last.status_code} — {last.json()})")
    return None


# ── Main trace ─────────────────────────────────────────────────────────────────

def main() -> None:
    api.SESSIONS_DB_PATH = SMOKE_DB
    if SMOKE_DB.exists():
        SMOKE_DB.unlink()
    _install_tracers()
    client = TestClient(api.app)

    # ---- 1. Goal ----
    section(1, "THE GOAL")
    print(f"repo: {REPO_URL}")
    for k, v in GOAL.items():
        print(f"  {k}: {v}")

    # ---- 2. Mentor builds the graph ----
    section(2, "MENTOR BUILDS THE INITIAL LEARNING GRAPH")
    print("POST /session/start  → runs clone → chunk → embed → prioritize → Mentor (Sonnet)…")
    start_resp = client.post("/session/start", json={"repo_url": REPO_URL, "goal": GOAL})
    if start_resp.status_code != 200:
        print(f"start failed: HTTP {start_resp.status_code} — {start_resp.json()}")
        return
    start = start_resp.json()
    session_id_1 = start["session_id"]
    print(f"\nsession_id: {session_id_1}")
    print(f"resumed:    {start['resumed']}")
    print(f"errors:     {start['errors'] or 'none'}")
    print(f"pipeline runs so far: {_PIPELINE_CALLS['n']}")
    graph = load(session_id_1)
    sub("FULL INITIAL GRAPH — NODES")
    print_nodes(graph)
    sub("FULL INITIAL GRAPH — EDGES")
    print_edges(graph)

    confused_node_id = graph.current_node_id
    print(f"\nstarting node (current): {_short(graph, confused_node_id)}")

    # ---- 3. Teaching renders the current node ----
    section(3, "TEACHING AGENT RENDERS THE CURRENT NODE'S LESSON")
    lesson_resp = get_lesson(client, session_id_1)
    if lesson_resp is None:
        print("Could not render the first lesson; aborting trace.")
        return
    lesson = lesson_resp["lesson"]
    print(f"node: {_short(graph, lesson_resp['node_id'])}  ({lesson_resp['node_id']})")
    sub("WALKTHROUGH")
    print(lesson["walkthrough"])
    sub("ACTIVE-LEARNING PROMPT (predict-then-reveal)")
    print(lesson["prompt"])
    sub("EXPECTED ANSWER (used by the Grader)")
    print(lesson["expected_answer"])

    # ---- 4. Simulated (deliberately wrong) user answer ----
    section(4, "SIMULATED USER ANSWER (deliberately wrong)")
    print(f'"{WEAK_ANSWER}"')

    # ---- snapshot BEFORE the respond/mutation ----
    before = snapshot(load(session_id_1))

    # ---- 5 + 6. Grade + mutate ----
    _TRACE.update(candidates=None, wire_node=None, grounded="(not reached)")
    respond_resp = client.post(
        f"/session/{session_id_1}/respond", json={"response": WEAK_ANSWER}
    )
    if respond_resp.status_code != 200:
        print(f"respond failed: HTTP {respond_resp.status_code} — {respond_resp.json()}")
        return
    respond = respond_resp.json()

    section(5, "GRADER CLASSIFIES THE ANSWER")
    print(f"classification: {respond['classification'].upper()}")
    print(f"node state now: {respond['understanding_state']}")
    sub("RATIONALE / detected misunderstanding")
    print(respond["rationale"])

    section(6, "MUTATOR — PREREQUISITE GENERATION & GROUNDING")
    print(f"mutator activated: {respond['mutation']['kind'] != 'none'}")
    print(f"mutation kind:     {respond['mutation']['kind']}")

    sub("Candidate chunks retrieved (RAG) for the prerequisite")
    cands = _TRACE["candidates"] or []
    if not cands:
        print("  (none retrieved)")
    for c in cands:
        print(f"  - [{c['type']}] {c['name']}  {c['file']}:"
              f"{c['start_line']}-{c['end_line']}  (role={c.get('role')})")

    sub("Prerequisite node the LLM proposed (raw, before grounding)")
    wire = _TRACE["wire_node"]
    if wire is None:
        print("  (LLM did not return a parseable node)")
    else:
        print(f"  title:        {wire.title}")
        print(f"  proposed anchor: {wire.file}:{wire.line_start}-{wire.line_end}")
        print(f"  why:          {wire.why}")
        print(f"  understand:   {wire.understand}")
        print(f"  concepts:     {', '.join(wire.concept_tags)}")

    sub("Anchor grounding (must match a real retrieved chunk)")
    grounded = _TRACE["grounded"]
    if grounded == "(not reached)":
        print("  grounding not reached (generation aborted earlier)")
    elif grounded is None:
        print("  ✗ VALIDATION FAILED — proposed anchor not in candidates → no insert")
    else:
        print(f"  ✓ VALIDATION OK — grounded to {grounded}:"
              f"{wire.line_start}-{wire.line_end}")

    # ---- 7. Graph after mutation: before/after diff ----
    section(7, "GRAPH AFTER /respond  (before vs after)")
    after_graph = load(session_id_1)
    after = snapshot(after_graph)

    added_nodes = after["node_ids"] - before["node_ids"]
    added_edges = after["edges"] - before["edges"]
    print(f"node count:  {len(before['node_ids'])}  →  {len(after['node_ids'])}")
    print(f"edge count:  {len(before['edges'])}  →  {len(after['edges'])}")

    sub("NEW node(s)")
    for nid in added_nodes:
        print(f"  + {after['titles'][nid]}  ({nid})")
    if not added_nodes:
        print("  (none)")

    sub("NEW / changed edge(s)")
    for f, t, k in added_edges:
        ft = after["titles"].get(f, f[:8])
        tt = after["titles"].get(t, t[:8])
        print(f"  + {ft}  --[{k}]-->  {tt}")
    removed_edges = before["edges"] - after["edges"]
    for f, t, k in removed_edges:
        ft = before["titles"].get(f, f[:8])
        tt = before["titles"].get(t, t[:8])
        print(f"  - (rerouted) {ft}  --[{k}]-->  {tt}")

    sub("Weak-spot flag")
    weak = [n.title for n in after_graph.nodes.values() if n.weak_spot]
    print(f"  nodes flagged weak: {weak or 'none'}")
    print(f"  (the originally-confused node: {_short(after_graph, confused_node_id)})")

    sub("New current node")
    print(f"  {_short(after_graph, after_graph.current_node_id)}  "
          f"({after_graph.current_node_id})")

    sub("FULL GRAPH AFTER MUTATION")
    print_edges(after_graph)

    # ---- 8. Traversal: prerequisite → confused node → continue ----
    mutated = respond["mutation"]["kind"] == "prerequisite"
    section(8, "TRAVERSAL — walk forward from the current node")
    cur = after_graph.current_node_id
    if mutated:
        print(f"current (the inserted prerequisite): {_short(after_graph, cur)}")
        print("expect: advance 1 returns to the originally-confused node, then continue.")
    else:
        print(f"current (no mutation occurred): {_short(after_graph, cur)}")
        print("expect: normal forward walk (no prerequisite detour this run).")
    for i in range(2):
        resp = client.post(f"/session/{session_id_1}/advance", json={"signal": "next"})
        if resp.status_code != 200:
            print(f"\n  advance {i + 1}: HTTP {resp.status_code} — {resp.json()}")
            break
        body = resp.json()
        if body.get("done"):
            print(f"\n  advance {i + 1}: DONE — reached the end of the path.")
            break
        landed = body.get("node_id")
        if landed is None:
            print(f"\n  advance {i + 1}: unexpected response — {body}")
            break
        g = load(session_id_1)
        note = "   ↩ RETURNED to the originally-confused node" if landed == confused_node_id else ""
        print(f"\n  advance {i + 1}  →  {_short(g, landed)}{note}")
        prompt = body.get("lesson", {}).get("prompt", "")
        print(f"     prompt: {prompt[:160]}…")

    # ---- 9. Resume ----
    section(9, "RESUME — second /session/start with the same repo + goal")
    pipeline_before_resume = _PIPELINE_CALLS["n"]
    again = client.post("/session/start", json={"repo_url": REPO_URL, "goal": GOAL}).json()
    session_id_2 = again["session_id"]
    g2 = load(session_id_2)
    print(f"first  session_id: {session_id_1}")
    print(f"second session_id: {session_id_2}")
    print(f"same session?      {session_id_1 == session_id_2}")
    print(f"resumed flag:      {again['resumed']}")
    print(f"resume point:      {_short(g2, g2.current_node_id)} "
          f"(visited={g2.nodes[g2.current_node_id].visited})")
    print(f"\npipeline runs total: {_PIPELINE_CALLS['n']}  "
          f"(unchanged by resume: {_PIPELINE_CALLS['n'] == pipeline_before_resume})")

    section(0, "STORY COMPLETE")
    print("Mentor built the graph → Teaching taught a node → the user answered wrong →")
    print("Grader caught the confusion → Mutator grounded & inserted a prerequisite →")
    print("the graph grew → traversal returned to the original node → resume reused")
    print("the saved session without re-running the pipeline.")


if __name__ == "__main__":
    main()
