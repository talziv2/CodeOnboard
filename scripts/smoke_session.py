"""
End-to-end smoke test for the Phase 3 interactive learning session.

Drives a REAL session against live LLMs through the actual API endpoints
(in-process TestClient, no server needed) on psf/requests with ONE goal. It
exercises the whole adaptive loop:

    /session/start   → prepare repo, survey, investigate, Mentor builds the graph
    /lesson          → Teaching renders the current node (Haiku)
    /respond         → Grader classifies a (deliberately weak) answer (Haiku);
                       on "confused", the Mentor mutator inserts a prerequisite
                       (Sonnet) before the node
    /advance         → walk forward a couple of lessons
    /session/start   → again, same repo+goal → resumes where we left off

Costs roughly $0.10–0.20 in API calls and takes ~30–60s on a warm cache.
Needs ANTHROPIC_API_KEY in .env.

Run with:
    .venv\\Scripts\\python.exe scripts\\smoke_session.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# LLM-generated walkthroughs (and our own arrows/ellipses) contain non-ASCII;
# the default Windows console codec (cp1252) would crash on them.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

from dotenv import load_dotenv
from fastapi.testclient import TestClient

import backend.api as api


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

# A confident, ON-TOPIC but WRONG answer — engages the question with a specific
# false claim, so it reliably grades as "confused" (triggering the prerequisite
# path) rather than "off-topic" (a no-op that would skip the mutation).
WEAK_ANSWER = (
    "Request validates the (user, pass) tuple and builds the Authorization "
    "header itself in __init__, then hands the finished header string to "
    "PreparedRequest."
)

# Keep the run bounded: at most this many /advance lessons after the first.
MAX_ADVANCES = 2

# Dedicated DB so the smoke run doesn't touch data/sessions.db, and a fresh
# start each run (otherwise the first /session/start would resume a prior run).
SMOKE_DB = Path("data/smoke_sessions.db")


def _hr(title: str) -> None:
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)


def _print_graph(graph: dict) -> None:
    print(f"session_id: {graph['session_id']}")
    print(f"readiness:  {graph['readiness']:.2f}")
    print(f"nodes ({len(graph['nodes'])}):")
    for n in graph["nodes"]:
        marker = "→" if n["id"] == graph["current_node_id"] else " "
        flags = []
        if n["visited"]:
            flags.append("visited")
        if n["weak_spot"]:
            flags.append("weak")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        print(
            f"  {marker} {n['understanding_state']:<10} {n['title']}"
            f"  ({n['file']}:{n['line_start']}-{n['line_end']}){flag_str}"
        )


def _print_lesson(node_id: str, lesson: dict) -> None:
    walk = lesson.get("walkthrough", "")
    if len(walk) > 600:
        walk = walk[:600] + " …[truncated]"
    print(f"node: {node_id}")
    print(f"\nwalkthrough:\n{walk}")
    print(f"\nprompt: {lesson.get('prompt')}")
    print(f"expected: {lesson.get('expected_answer')}")


def main() -> None:
    api.SESSIONS_DB_PATH = SMOKE_DB
    if SMOKE_DB.exists():
        SMOKE_DB.unlink()

    client = TestClient(api.app)

    # 1. Start — the full pipeline runs live (clone → chunk → embed → Sonnet).
    _hr("1. POST /session/start  (Mentor builds the graph)")
    resp = client.post("/session/start", json={"repo_url": REPO_URL, "goal": GOAL})
    if resp.status_code != 200:
        print(f"FAILED ({resp.status_code}): {resp.json()}")
        return
    start = resp.json()
    print(f"resumed: {start['resumed']}   errors: {start['errors'] or 'none'}")
    session_id = start["session_id"]
    _print_graph(start["graph"])

    # 2. First lesson — Teaching Agent renders the current node (Haiku).
    _hr("2. GET /session/{id}/lesson  (Teaching renders the first node)")
    resp = client.get(f"/session/{session_id}/lesson")
    if resp.status_code != 200:
        print(f"FAILED ({resp.status_code}): {resp.json()}")
        return
    lesson = resp.json()
    _print_lesson(lesson["node_id"], lesson["lesson"])

    # 3. Respond with a weak answer — Grader classifies; confused → prerequisite.
    _hr("3. POST /session/{id}/respond  (Grader + maybe a prerequisite)")
    print(f"answering with: {WEAK_ANSWER!r}")
    resp = client.post(f"/session/{session_id}/respond", json={"response": WEAK_ANSWER})
    if resp.status_code != 200:
        print(f"FAILED ({resp.status_code}): {resp.json()}")
        return
    graded = resp.json()
    print(f"\nclassification: {graded['classification']}")
    print(f"rationale:      {graded['rationale']}")
    print(f"mutation:       {graded['mutation']}")

    if graded["mutation"]["kind"] == "prerequisite":
        print("\n>>> A prerequisite was inserted. Current graph:")
        _print_graph(client.get(f"/session/{session_id}").json())
    else:
        print("\n(No mutation — the Grader didn't classify this as 'confused'.)")

    # 4. Walk forward a couple of lessons.
    _hr("4. POST /session/{id}/advance  (walk the path)")
    for i in range(MAX_ADVANCES):
        resp = client.post(f"/session/{session_id}/advance", json={"signal": "next"})
        body = resp.json()
        if body.get("done"):
            print(f"advance {i + 1}: done — end of path.")
            break
        print(f"\nadvance {i + 1} → node {body['node_id']}")
        lesson = body["lesson"]
        prompt = lesson.get("prompt", "")
        print(f"  prompt: {prompt}")

    # 5. Resume — start again, same repo+goal → continue where we left off.
    _hr("5. POST /session/start again  (resume, no pipeline re-run)")
    resp = client.post("/session/start", json={"repo_url": REPO_URL, "goal": GOAL})
    again = resp.json()
    print(f"resumed: {again['resumed']}   session_id matches: "
          f"{again['session_id'] == session_id}")
    graph = again["graph"]
    current = next(
        (n for n in graph["nodes"] if n["id"] == graph["current_node_id"]), None
    )
    if current:
        print(f"resume point: {current['title']} "
              f"({current['understanding_state']}, visited={current['visited']})")

    _hr("done")


if __name__ == "__main__":
    main()
