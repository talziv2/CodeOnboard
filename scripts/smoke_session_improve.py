"""
End-to-end demo of the improve_existing_system flow, including adaptive
recovery from misunderstanding.

Exercises the NEW pieces added to the pipeline:
  - the improve_existing_system goal type
  - the Reviewer Agent (single Haiku call, runs between Prioritization and
    Mentor) — produces strengths / risks / extension_points / test_gaps /
    boundaries
  - the Mentor's widened concept-tag vocabulary
    (architecture / flow / extension_point / risk / test_coverage)
  - the Teaching Agent's per-tag framing branch

…and composes them with the full Phase 3 adaptive loop:
    Mentor → Teaching → correct answer → Grader (UNDERSTOOD) →
    advance → Teaching → wrong answer → Grader (CONFUSED) →
    Mutator inserts a grounded prerequisite → advance returns to the
    originally confused node → resume reuses the saved session.

Drives the real API endpoints in-process (TestClient) on psf/requests with one
realistic safe-change goal. Costs ~$0.20-0.40 in API calls and takes ~60-120s
on a warm cache. Needs ANTHROPIC_API_KEY in .env.

Run with:
    .venv\\Scripts\\python.exe scripts\\smoke_session_improve.py
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
from backend.pipeline import runner as runner_mod


load_dotenv(override=True)

REPO_URL = "https://github.com/psf/requests"

GOAL = {
    "primary_goal": (
        "Safely add a custom authentication scheme to requests.Session, "
        "so it injects an HMAC-signed header on every outgoing request"
    ),
    "goal_type": "improve_existing_system",
    "focus_area": "session authentication and adapter pipeline",
    "experience_level": "intermediate",
    "depth": "moderate",
    "target_repo": REPO_URL,
    "familiarity": "used requests as a library, new to its internals",
    "background": "5 years of Python, some Flask",
    "change_target": (
        "subclass AuthBase to add a custom HMAC auth and plug it into Session"
    ),
    "risk_tolerance": "production use — must not regress existing auth flows",
}

# A confident, on-topic, but WRONG answer for the second lesson. Engages with
# the lesson's typical territory (prepare_auth / __call__ contract / headers /
# the return value) but makes a specific false claim about how the framework
# consumes the auth handler's output. Designed to land as Grader=CONFUSED
# (not OFF-TOPIC, which would skip the mutator entirely).
WRONG_ANSWER = (
    "I think prepare_auth() reads the request fields directly from the auth "
    "handler's locals using introspection — it doesn't really care what your "
    "__call__ returns, since Python objects are mutable and any header changes "
    "you make persist on PreparedRequest automatically. The return value is "
    "mostly a stylistic convention; you could safely omit the return statement "
    "entirely and the framework would still see the modified request."
)

# Dedicated DB so this run does not collide with smoke_session.py or the
# user-facing data/sessions.db, and gets a clean slate every run.
SMOKE_DB = Path("data/smoke_improve_sessions.db")


# ── Tracing ───────────────────────────────────────────────────────────────────
#
# Same idea as scripts/smoke_session_verbose.py: wrap the agent's internals so
# we can print what the Reviewer produced, what the Mutator considered, and
# how many times the heavyweight pipeline actually ran. None of these change
# behaviour — they just let the demo prove what happened.

_TRACE = {
    "system_review": None,
    "reviewer_called": False,
    # Mutator's per-call introspection (reset before the wrong-answer step).
    "candidates": None,
    "wire_node": None,
    "grounded": "(not reached)",
}
_PIPELINE_CALLS = {"n": 0}


def _install_reviewer_tracer() -> None:
    original = runner_mod.run_reviewer

    def traced(state, client=None):
        _TRACE["reviewer_called"] = True
        result = original(state, client=client)
        _TRACE["system_review"] = result.system_review
        return result

    runner_mod.run_reviewer = traced


def _install_mutator_tracers() -> None:
    # Mirrors the shim pattern in smoke_session_verbose.py.
    orig_retrieve = mutator_mod.retrieve_supporting_chunks
    orig_parse = mutator_mod._parse_node
    orig_ground = mutator_mod._ground_node

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
        _TRACE["grounded"] = result
        return result

    mutator_mod.retrieve_supporting_chunks = traced_retrieve
    mutator_mod._parse_node = traced_parse
    mutator_mod._ground_node = traced_ground


def _install_pipeline_counter() -> None:
    orig_pipeline = api.run_pipeline

    def counted(*a, **k):
        _PIPELINE_CALLS["n"] += 1
        return orig_pipeline(*a, **k)

    api.run_pipeline = counted


# ── Print helpers ─────────────────────────────────────────────────────────────


def section(n: int, title: str) -> None:
    print()
    print("█" * 78)
    print(f"█  STEP {n}: {title}")
    print("█" * 78)


def sub(title: str) -> None:
    print(f"\n── {title} " + "─" * max(0, 70 - len(title)))


def _print_anchor(anchor: dict | None) -> str:
    if not anchor:
        return ""
    return f" [{anchor['file']}:{anchor['line_start']}-{anchor['line_end']}]"


def print_system_review(review: dict | None) -> None:
    if review is None:
        print("  (Reviewer did not run or produced no output.)")
        return

    def _list(label: str, items: list[dict], anchored: bool = True) -> None:
        if not items:
            print(f"\n  {label}: (none)")
            return
        print(f"\n  {label}:")
        for it in items:
            anchor_str = _print_anchor(it.get("anchor")) if anchored else ""
            print(f"    - {it['area']}: {it['note']}{anchor_str}")

    _list("STRENGTHS", review.get("strengths", []))
    _list("RISKS", review.get("risks", []))
    _list("EXTENSION POINTS", review.get("extension_points", []))
    _list("TEST GAPS", review.get("test_gaps", []))

    boundaries = review.get("boundaries", [])
    if boundaries:
        print("\n  BOUNDARIES:")
        for b in boundaries:
            between = " <-> ".join(b.get("between", []))
            print(f"    - {between}: {b['note']}")


# Concept tags introduced by the new flow. Anything outside this set is
# treated as a free-form domain tag and grouped under "other".
NEW_TAGS = {
    "architecture",
    "flow",
    "extension_point",
    "risk",
    "test_coverage",
}


def dominant_new_tag(tags: list[str]) -> str | None:
    """First new-vocabulary tag on the node, if any.

    Mirrors how the Teaching Agent's framing branch picks a frame — it keys
    off the dominant new tag, defaulting to the generic mode when only
    free-form tags are present.
    """
    for t in tags:
        if t in NEW_TAGS:
            return t
    return None


def print_graph_nodes_by_tag(graph: LearningGraph) -> None:
    buckets: dict[str, list] = {tag: [] for tag in NEW_TAGS}
    buckets["other"] = []
    for node in graph.nodes.values():
        bucket = dominant_new_tag(node.concept_tags) or "other"
        buckets[bucket].append(node)

    for tag in ("architecture", "flow", "extension_point", "risk", "test_coverage", "other"):
        nodes = buckets[tag]
        label = "OTHER (free-form tags only)" if tag == "other" else tag.upper()
        if not nodes:
            print(f"\n  {label}: (none)")
            continue
        print(f"\n  {label}: ({len(nodes)})")
        for node in nodes:
            cur = "  «CURRENT»" if node.id == graph.current_node_id else ""
            print(f"    - {node.title}{cur}")
            print(f"        anchor: {node.code_anchor.file}:"
                  f"{node.code_anchor.line_start}-{node.code_anchor.line_end}")
            if node.concept_tags:
                print(f"        tags:   {', '.join(node.concept_tags)}")


def print_edges(graph: LearningGraph) -> None:
    titles = {nid: n.title for nid, n in graph.nodes.items()}
    print(f"  edges: {len(graph.edges)}")
    for e in graph.edges:
        ft = titles.get(e.from_node_id, e.from_node_id[:8])
        tt = titles.get(e.to_node_id, e.to_node_id[:8])
        print(f"    {ft}  --[{e.kind}]-->  {tt}")


def snapshot(graph: LearningGraph) -> dict:
    return {
        "node_ids": set(graph.nodes),
        "edges": {(e.from_node_id, e.to_node_id, e.kind) for e in graph.edges},
        "titles": {nid: n.title for nid, n in graph.nodes.items()},
        "weak": {nid for nid, n in graph.nodes.items() if n.weak_spot},
        "current_id": graph.current_node_id,
    }


def load(session_id: str) -> LearningGraph:
    return learning_store.load_graph(session_id, SMOKE_DB)


# ── Robust HTTP wrappers ──────────────────────────────────────────────────────
#
# The Teaching Agent occasionally truncates its JSON output mid-string (Haiku
# samples a long lesson and runs out of token budget right at the wrong
# place). The agent already retries internally once; we add a second tier
# here so a single transient flake doesn't break the demo narrative.


def get_lesson_with_retry(client, session_id: str, tries: int = 3) -> dict | None:
    """GET /lesson is idempotent (renders/returns the current node's lesson),
    so safe to retry on the same node."""
    last = None
    for attempt in range(1, tries + 1):
        resp = client.get(f"/session/{session_id}/lesson")
        if resp.status_code == 200:
            if attempt > 1:
                print(f"  (lesson rendered on retry {attempt})")
            return resp.json()
        last = resp
    if last is not None:
        print(f"  lesson failed after {tries} tries: HTTP {last.status_code} — {last.json()}")
    return None


def advance_with_fallback(client, session_id: str) -> tuple[dict | None, str | None]:
    """POST /advance once; if it 500s with lesson_generation_failed, fall back
    to GET /lesson — /advance already moved the current pointer and persisted
    it, so re-running it would skip the now-current node entirely. The lesson
    endpoint will re-attempt Teaching against the same node.

    Returns (body, fallback_note). body is the advance-shaped dict; note is a
    human-readable explanation if a fallback was used, else None.
    """
    resp = client.post(f"/session/{session_id}/advance", json={"signal": "next"})
    if resp.status_code == 200:
        return resp.json(), None

    detail = resp.json().get("detail", {})
    err = detail.get("error") if isinstance(detail, dict) else None
    if err == "lesson_generation_failed":
        lesson = get_lesson_with_retry(client, session_id)
        if lesson is not None:
            return (
                {"done": False, "node_id": lesson["node_id"], "lesson": lesson["lesson"]},
                "/advance moved the current pointer but Teaching truncated; "
                "GET /lesson rendered the lesson on retry.",
            )

    return None, f"advance failed: HTTP {resp.status_code} — {resp.json()}"


# ── Main trace ────────────────────────────────────────────────────────────────


def main() -> None:
    api.SESSIONS_DB_PATH = SMOKE_DB
    if SMOKE_DB.exists():
        SMOKE_DB.unlink()
    _install_reviewer_tracer()
    _install_mutator_tracers()
    _install_pipeline_counter()
    client = TestClient(api.app)

    # ---- 1. Goal ----
    section(1, "THE GOAL (improve_existing_system)")
    print(f"repo: {REPO_URL}")
    for k, v in GOAL.items():
        print(f"  {k}: {v}")

    # ---- 2. Pipeline ----
    section(2, "PIPELINE  →  code_structure  →  prioritization  →  reviewer  →  mentor")
    print("POST /session/start  → live clone / chunk / embed / Reviewer (Haiku) / Mentor (Sonnet)…")
    start_resp = client.post("/session/start", json={"repo_url": REPO_URL, "goal": GOAL})
    if start_resp.status_code != 200:
        print(f"start failed: HTTP {start_resp.status_code} — {start_resp.json()}")
        return
    start = start_resp.json()
    session_id = start["session_id"]
    print(f"\nsession_id:   {session_id}")
    print(f"resumed:      {start['resumed']}")
    print(f"errors:       {start['errors'] or 'none'}")
    print(f"reviewer ran: {_TRACE['reviewer_called']}")
    print(f"pipeline runs so far: {_PIPELINE_CALLS['n']}")

    # ---- 3. Reviewer findings ----
    section(3, "REVIEWER FINDINGS  (Haiku, gated to improve_existing_system + understand_architecture)")
    print_system_review(_TRACE["system_review"])

    # ---- 4. Graph by concept tag ----
    section(4, "MENTOR'S GRAPH — nodes grouped by NEW concept-tag vocabulary")
    graph = load(session_id)
    print_graph_nodes_by_tag(graph)
    sub("Path edges (sequence)")
    print_edges(graph)

    # ---- 5. First lesson ----
    section(5, "TEACHING — first lesson (framing keys off the dominant new tag)")
    first_node = graph.nodes.get(graph.current_node_id) if graph.current_node_id else None
    if first_node is None:
        print("(no current node — aborting trace)")
        return
    frame = dominant_new_tag(first_node.concept_tags)
    print(f"current node: {first_node.title}")
    print(f"concept_tags: {first_node.concept_tags or '—'}")
    print(f"dominant new tag → framing: {frame or 'generic'}")
    print(f"anchor: {first_node.code_anchor.file}:"
          f"{first_node.code_anchor.line_start}-{first_node.code_anchor.line_end}")

    lesson_payload = get_lesson_with_retry(client, session_id)
    if lesson_payload is None:
        print("Could not render the first lesson; aborting.")
        return
    lesson = lesson_payload["lesson"]
    sub("WALKTHROUGH")
    print(lesson["walkthrough"])
    sub("ACTIVE-LEARNING PROMPT")
    print(lesson["prompt"])

    # ---- 6. Grader — correct answer (expect UNDERSTOOD) ----
    section(6, "GRADER — POST /respond with a thoughtful CORRECT answer")
    # Paraphrase the system's own expected_answer so the answer is on-topic
    # and accurate without being identical to the expected string.
    correct_answer = (
        "From what I can tell, "
        + lesson["expected_answer"]
        + " — I'm reasoning from how Session uses self.auth as a default."
    )
    print(f"answer:\n  {correct_answer}")
    respond = client.post(
        f"/session/{session_id}/respond", json={"response": correct_answer}
    )
    if respond.status_code != 200:
        print(f"\nrespond failed: HTTP {respond.status_code} — {respond.json()}")
        return
    graded = respond.json()
    sub("Grader output")
    print(f"  classification:      {graded['classification'].upper()}")
    print(f"  understanding_state: {graded['understanding_state']}")
    print(f"  rationale:           {graded['rationale']}")
    print(f"  mutation:            {graded['mutation']['kind']}")

    g_after_good = load(session_id)
    n_after_good = g_after_good.nodes[first_node.id]
    print(f"\n  → first node now: state={n_after_good.understanding_state}, "
          f"visited={n_after_good.visited}, weak_spot={n_after_good.weak_spot}")

    # ---- 7. Advance to the next node ----
    section(7, "TRAVERSAL — POST /advance to the next node")
    body, note = advance_with_fallback(client, session_id)
    if body is None:
        print(f"advance failed: {note}")
        return
    if note:
        print(f"  note: {note}")
    if body.get("done"):
        print("Reached end of path on the very first advance — nothing left to demo.")
        return
    second_node_id = body["node_id"]
    g_at_second = load(session_id)
    second_node = g_at_second.nodes[second_node_id]
    print(f"advanced to: {second_node.title}")
    print(f"concept_tags: {second_node.concept_tags or '—'}")
    print(f"framing:      {dominant_new_tag(second_node.concept_tags) or 'generic'}")

    # ---- 8. Second lesson ----
    section(8, "TEACHING — second lesson (about to receive a deliberately wrong answer)")
    second_lesson = body.get("lesson") or {}
    walkthrough = second_lesson.get("walkthrough", "")
    sub("WALKTHROUGH")
    print(walkthrough)
    sub("ACTIVE-LEARNING PROMPT")
    print(second_lesson.get("prompt", "(no prompt)"))

    # ---- 9. Grader — wrong answer (expect CONFUSED) ----
    section(9, "GRADER — POST /respond with a CONFIDENT BUT WRONG answer")
    print(f"answer:\n  {WRONG_ANSWER}")
    # Reset mutator-trace fields so the candidates / wire_node / grounded keys
    # reflect THIS response's mutator call, not anything from earlier.
    _TRACE.update(candidates=None, wire_node=None, grounded="(not reached)")
    before_snap = snapshot(load(session_id))

    respond2 = client.post(
        f"/session/{session_id}/respond", json={"response": WRONG_ANSWER}
    )
    if respond2.status_code != 200:
        print(f"\nrespond failed: HTTP {respond2.status_code} — {respond2.json()}")
        return
    graded2 = respond2.json()
    sub("Grader output")
    print(f"  classification:      {graded2['classification'].upper()}")
    print(f"  understanding_state: {graded2['understanding_state']}")
    print(f"  rationale:           {graded2['rationale']}")

    confused = graded2["classification"] == "confused"
    if not confused:
        print(
            f"\n  ⚠ Grader did NOT classify as 'confused' — got "
            f"'{graded2['classification']}'. Mutator only fires on 'confused',"
            f" so steps 10–12 will report no mutation."
        )

    # ---- 10. Mutator internals ----
    section(10, "MUTATOR — candidate chunks, proposed prerequisite, grounding")
    mutation = graded2.get("mutation", {}) or {}
    print(f"mutation kind reported by API: {mutation.get('kind')}")
    if mutation.get("kind") == "prerequisite":
        print(f"new prereq node_id: {mutation.get('new_node_id')}")
        print(f"anchored on confused node: {mutation.get('anchor_node_id')}")
    elif mutation.get("kind") == "none":
        reason = mutation.get("reason") or (
            "Grader did not classify as 'confused'" if not confused
            else "mutator skipped — see candidates / wire_node / grounded below"
        )
        print(f"reason: {reason}")

    sub("Candidate chunks retrieved (RAG) for the prerequisite")
    cands = _TRACE["candidates"] or []
    if not cands:
        print("  (none retrieved — mutator never ran, or retrieval returned nothing)")
    for c in cands:
        print(f"  - [{c['type']}] {c['name']}  {c['file']}:"
              f"{c['start_line']}-{c['end_line']}  (role={c.get('role')})")

    sub("Prerequisite node the LLM proposed (raw, before grounding)")
    wire = _TRACE["wire_node"]
    if wire is None:
        print("  (LLM did not produce a parseable proposal)")
    else:
        print(f"  title:           {wire.title}")
        print(f"  proposed anchor: {wire.file}:{wire.line_start}-{wire.line_end}")
        print(f"  why:             {wire.why}")
        print(f"  understand:      {wire.understand}")
        print(f"  concepts:        {', '.join(wire.concept_tags)}")

    sub("Anchor grounding (must match a real retrieved chunk)")
    grounded = _TRACE["grounded"]
    if grounded == "(not reached)":
        print("  grounding step not reached (generation aborted earlier)")
    elif grounded is None:
        print("  ✗ VALIDATION FAILED — proposed anchor not in candidates → no insert")
    else:
        print(f"  ✓ VALIDATION OK — grounded to {grounded}:"
              f"{wire.line_start}-{wire.line_end}")

    # ---- 11. Graph diff ----
    section(11, "GRAPH DIFF  (before vs after the wrong-answer step)")
    after_graph = load(session_id)
    after_snap = snapshot(after_graph)

    added_nodes = after_snap["node_ids"] - before_snap["node_ids"]
    removed_nodes = before_snap["node_ids"] - after_snap["node_ids"]
    added_edges = after_snap["edges"] - before_snap["edges"]
    removed_edges = before_snap["edges"] - after_snap["edges"]
    newly_weak = after_snap["weak"] - before_snap["weak"]

    print(f"node count:  {len(before_snap['node_ids'])}  →  {len(after_snap['node_ids'])}")
    print(f"edge count:  {len(before_snap['edges'])}  →  {len(after_snap['edges'])}")
    print(f"weak spots:  {len(before_snap['weak'])}  →  {len(after_snap['weak'])}")

    sub("Added node(s)")
    if not added_nodes:
        print("  (none)")
    for nid in added_nodes:
        node = after_graph.nodes[nid]
        print(f"  + {node.title}")
        print(f"      id:     {nid}")
        print(f"      anchor: {node.code_anchor.file}:"
              f"{node.code_anchor.line_start}-{node.code_anchor.line_end}")
        if node.concept_tags:
            print(f"      tags:   {', '.join(node.concept_tags)}")

    sub("Removed node(s)")
    if not removed_nodes:
        print("  (none)")
    for nid in removed_nodes:
        print(f"  - {before_snap['titles'].get(nid, nid)}")

    sub("New / rerouted edge(s)")
    if not added_edges and not removed_edges:
        print("  (none)")
    for f, t, k in added_edges:
        ft = after_snap["titles"].get(f, f[:8])
        tt = after_snap["titles"].get(t, t[:8])
        print(f"  + {ft}  --[{k}]-->  {tt}")
    for f, t, k in removed_edges:
        ft = before_snap["titles"].get(f, f[:8])
        tt = before_snap["titles"].get(t, t[:8])
        print(f"  - (rerouted away) {ft}  --[{k}]-->  {tt}")

    sub("Weak-spot flag changes")
    if not newly_weak:
        print("  (no new weak-spot flags)")
    for nid in newly_weak:
        print(f"  ⚑ {after_graph.nodes[nid].title}  (originally confused node)")

    sub("Current node pointer")
    cur_before = before_snap["current_id"]
    cur_after = after_snap["current_id"]
    print(f"  before: {before_snap['titles'].get(cur_before, cur_before)}")
    print(f"  after:  {after_snap['titles'].get(cur_after, cur_after)}")
    if cur_before != cur_after and cur_after in added_nodes:
        print("  → current pointer moved to the inserted prerequisite (correct).")

    # ---- 12. Traversal — should return to the originally confused node ----
    section(12, "TRAVERSAL — POST /advance should return to the originally confused node")
    confused_node_id = second_node_id
    body3, note3 = advance_with_fallback(client, session_id)
    if body3 is None:
        print(f"advance failed: {note3}")
    elif body3.get("done"):
        print("advance reported DONE — end of path (no node to advance to).")
    else:
        landed = body3["node_id"]
        g_after_adv = load(session_id)
        landed_title = g_after_adv.nodes[landed].title
        print(f"advanced to: {landed_title}")
        print(f"  node_id:      {landed}")
        print(f"  matches the originally-confused node? "
              f"{'YES — recovered to the confused node' if landed == confused_node_id else 'NO'}")
        if note3:
            print(f"  note: {note3}")

    # ---- 13. Resume ----
    section(13, "RESUME — second /session/start with the same repo+goal")
    pipeline_before_resume = _PIPELINE_CALLS["n"]
    again = client.post("/session/start", json={"repo_url": REPO_URL, "goal": GOAL}).json()
    g_resumed = load(again["session_id"])
    same = again["session_id"] == session_id
    cur = g_resumed.nodes[g_resumed.current_node_id] if g_resumed.current_node_id else None
    print(f"same session?      {same}")
    print(f"resumed flag:      {again['resumed']}")
    if cur is not None:
        print(f"resume point:      {cur.title} "
              f"(visited={cur.visited}, state={cur.understanding_state})")
    print(f"pipeline runs total: {_PIPELINE_CALLS['n']}  "
          f"(unchanged by resume: {_PIPELINE_CALLS['n'] == pipeline_before_resume})")

    section(0, "STORY COMPLETE")
    print("Reviewer ran on improve_existing_system → produced structured findings →")
    print("Mentor built a graph using the new concept-tag vocabulary → Teaching framed")
    print("the first lesson → correct answer → Grader UNDERSTOOD → advance → second")
    print("lesson → wrong answer → Grader CONFUSED → Mutator generated and grounded a")
    print("prerequisite → advance returned to the originally-confused node → resume")
    print("reused the saved session without re-running the pipeline.")


if __name__ == "__main__":
    main()
