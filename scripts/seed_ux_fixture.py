"""Seed a throwaway database with a session rich enough to walk the UI.

    uv run python scripts/seed_ux_fixture.py --db data/ux-fixture.db

## Why this exists

`scripts/smoke_multiuser.py` proves the account layer over real HTTP but starts
every session through `/session/start`, which runs the whole pipeline: a clone,
an exploration and a Sonnet call, two to four minutes and real money per run.
That is the right shape for what it tests and the wrong shape for looking at a
screen.

Everything a UI pass needs is downstream of the planner and none of it needs the
planner to have run. So this writes the graph directly — nodes, anchors, cached
lessons, attempts, gaps — and the app then behaves exactly as it would on a real
session, because from `/lesson` onwards it is reading the same rows.

**A cached lesson on every node is what keeps it free.** `/lesson` renders
through Teaching when `cached_lesson` is empty; pre-populated, the endpoint
serves the row and no model is called.

REFUSES `data/sessions.db`, like `smoke_multiuser.py` and for the same reason:
it creates accounts and sessions, and pointing it at real data would be a
fixture that overwrites the thing it is meant to sit beside.

The stops are shaped for the states this pass touches:

The anchors are REAL paths in `psf/requests` as it is actually laid out
(`src/requests/...`), because `/respond` reads the source before grading and
refuses a lesson it cannot ground — a fixture pointing at a path that does not
exist would 409 at the one moment the pass is trying to look at feedback.

    1  answered correctly            demonstrated, and revisitable (#6)
    2  answered, one gap open        the ledger, and its two verbs (#3, #4)
    3  reached, never answered       walked past (#8) once advanced through
    4  untouched                     the unwalked baseline
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.auth import identity, passwords  # noqa: E402
from backend.learning import store as learning_store  # noqa: E402
from backend.learning.gaps import Gap  # noqa: E402
from backend.learning.graph import (  # noqa: E402
    CodeAnchor, LearningGraph, LearningNode,
)

EMAIL = "ux-fixture@example.test"
PASSWORD = "a-long-enough-passphrase"
REPO = "https://github.com/psf/requests"
def _ago(minutes: int) -> str:
    """A timestamp `minutes` before now, in the format the backend writes.

    RELATIVE, not a literal. The first draft hard-coded two ISO stamps and they
    landed AHEAD of the server's UTC clock, which made every seeded attempt read
    as "not yet happened" — `arrival.ts` compares attempt times against the
    arrival, so the whole fixture looked unanswered. A fixture whose meaning
    depends on the day it is run is not a fixture.
    """
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat(
        timespec="seconds"
    )


GOAL = {
    "primary_goal": "understand the request lifecycle",
    "goal_type": "understand_component",
    "focus_area": "the Session object",
    "code_depth": "working",
    "depth": "moderate",
    "familiarity": "some",
}


def _lesson(title: str) -> dict:
    """A complete cached lesson, so `/lesson` never reaches for a model."""
    return {
        "setup": f"**{title}.** Read the anchor below before you answer. The "
                 f"object is constructed once and reused for every request that "
                 f"follows, which is where its behaviour comes from.",
        "walkthrough": f"{title} — the walkthrough.",
        "why_now": "This is the object every later stop hangs off.",
        "prompt": f"What does {title.lower()} own that a bare call does not?",
        "prompt_kind": "explain",
        "reveal": "**The explanation.** It owns the connection pool, the cookie "
                  "jar and the default configuration — so sending through it "
                  "changes behaviour in three ways a bare call cannot.",
        "takeaway": "One object, three kinds of state carried between calls.",
        "ownership": "You should now be able to say why reuse matters here.",
    }


def _node(title: str, *, file: str, start: int, end: int) -> LearningNode:
    node = LearningNode(
        title=title,
        code_anchor=CodeAnchor(file=file, line_start=start, line_end=end),
        lesson_brief={
            "objective": f"Explain what {title} owns and why it matters.",
            "priority": "required",
            "kind": "component",
            "area_id": "core",
            "anchors": [{"file": file, "symbol": title.split()[-1],
                         "line_start": start, "line_end": end}],
        },
    )
    node.cached_lesson = _lesson(title)
    return node


def build(db_path: Path) -> tuple[str, str]:
    """Create the account and the session. Returns (user_id, session_id)."""
    user_id = identity.create_user(EMAIL, "UX fixture", db_path=db_path)
    identity.add_identity(
        user_id, identity.PASSWORD, EMAIL,
        secret_hash=passwords.hash_password(PASSWORD), db_path=db_path,
    )

    graph = LearningGraph(repo_url=REPO, goal=GOAL)
    stops = [
        _node("The Session object", file="src/requests/sessions.py", start=1, end=80),
        _node("Adapter mounting", file="src/requests/adapters.py", start=1, end=60),
        _node("Request preparation", file="src/requests/models.py", start=1, end=90),
        _node("Response streaming", file="src/requests/models.py", start=600, end=700),
    ]
    for node in stops:
        graph.add_node(node)
    for a, b in zip(stops, stops[1:]):
        graph.add_edge(a.id, b.id, kind="sequence")

    # ── stop 1: demonstrated, and behind the learner ──────────────────────────
    first = stops[0]
    first.attempts.append({
        "answer": "It owns the connection pool, the cookies and the defaults.",
        "classification": "understood",
        "rationale": "Yes — all three, and you said why reuse matters.",
        "gap_kind": "none",
        "kind": "assessment",
        "graded": True,
        "question": first.cached_lesson["prompt"],
        "question_source": "lesson",
        "at": _ago(120),
    })
    first.understanding_state = "understood"
    first.visited = True

    # ── stop 2: answered, and carrying an open blocking gap ───────────────────
    second = stops[1]
    second.attempts.append({
        "answer": "Adapters are just a dict, nothing else happens.",
        "classification": "partial",
        "rationale": "The dict is there, but the LONGEST-PREFIX match is the part "
                     "that decides which adapter handles a URL.",
        "gap_kind": "wrong_model",
        "kind": "assessment",
        "graded": True,
        "question": second.cached_lesson["prompt"],
        "question_source": "lesson",
        "at": _ago(110),
    })
    second.understanding_state = "partial"
    second.gap_state.gaps.append(
        Gap.create(
            "wrong_model",
            "mounting an adapter is only a dict insert, with no prefix matching",
            objective_part="how a URL is routed to an adapter",
        )
    )
    settled = Gap.create("right_idea_wrong_altitude", "adapters are per-request")
    settled.waive()
    second.gap_state.gaps.append(settled)

    # Stop 3 is where the learner is standing: reached, nothing answered. Walking
    # on from here is what produces the `passed_by` pin (#8).
    graph.set_current(stops[2].id)

    learning_store.create_session(graph, db_path, user_id=user_id)
    learning_store.set_session_status(graph.session_id, "active", db_path)
    return user_id, graph.session_id


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/ux-fixture.db")
    args = ap.parse_args()

    db_path = Path(args.db).resolve()
    if db_path.name == "sessions.db":
        print("refusing to seed the real database", file=sys.stderr)
        return 2
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    learning_store.init_db(db_path)
    user_id, session_id = build(db_path)
    print(f"db         {db_path}")
    print(f"user       {EMAIL}")
    print(f"user_id    {user_id}")
    print(f"session    {session_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
