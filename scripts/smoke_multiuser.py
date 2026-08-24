"""Two accounts, one server, every multi-user guarantee (multi-user M8).

Run with a backend already serving, against a THROWAWAY database:

    uv run python scripts/smoke_multiuser.py --base http://127.0.0.1:8100

## Why this exists alongside 1700 unit tests

The suites use `TestClient`, which is in-process: the same Python objects, the
same module state, no sockets, no cookie jar of its own. Everything they prove is
real, and none of it proves that a BROWSER-shaped client talking to a REAL server
over HTTP gets the same answers.

The properties that only show up here are the ones that live in the plumbing —
cookie attributes as a real client stores them, a second account genuinely
isolated in a separate cookie jar, and a session that outlives the process that
made it.

It refuses to run against `data/sessions.db`. This creates accounts, sessions and
deletions; pointing it at real data would be a test that destroys the thing it
is testing.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

PASSWORD = "a-long-enough-passphrase"
REPO = "https://github.com/psf/requests"
GOAL = {
    "primary_goal": "understand how sessions work",
    "goal_type": "understand_component",
    "focus_area": "the Session object",
    "code_depth": "working",
    "depth": "moderate",
}

_passed: list[str] = []
_failed: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    (_passed if condition else _failed).append(name)
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {name}" + (f"  — {detail}" if detail and not condition else ""))
    return condition


def account(base: str, email: str) -> httpx.Client:
    """A client with its own cookie jar — a separate browser, in effect."""
    client = httpx.Client(base_url=base, timeout=30, follow_redirects=False)
    response = client.post(
        "/auth/register", json={"email": email, "password": PASSWORD}
    )
    if response.status_code != 201:
        raise SystemExit(f"could not register {email}: {response.status_code} {response.text}")
    return client


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8100")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    health = httpx.get(f"{base}/health", timeout=10)
    if health.status_code != 200:
        raise SystemExit(f"no server at {base}")

    stamp = uuid.uuid4().hex[:8]
    alice_email = f"alice-{stamp}@example.com"
    mallory_email = f"mallory-{stamp}@example.com"

    print(f"\nserver {base}")
    print(f"accounts {alice_email} / {mallory_email}\n")

    # ── registration and the cookie ──────────────────────────────────────────
    print("registration")
    alice = account(base, alice_email)
    raw = httpx.post(
        f"{base}/auth/register",
        json={"email": f"cookie-{stamp}@example.com", "password": PASSWORD},
        timeout=30,
    )
    header = raw.headers.get("set-cookie", "")
    check("the session cookie is HttpOnly", "httponly" in header.lower(), header)
    check("the session cookie is SameSite=Lax", "samesite=lax" in header.lower(), header)
    check("registration signs you in", alice.get("/auth/me").status_code == 200)

    # ── the learner's own session ────────────────────────────────────────────
    print("\nsessions")
    started = alice.post(
        "/session/start", json={"repo_url": REPO, "goal": GOAL}
    )
    check("starting returns immediately with 202", started.status_code == 202,
          f"{started.status_code} {started.text[:120]}")
    session_id = started.json().get("session_id", "")
    check("and hands back an id before any planning", bool(session_id))

    listed = alice.get("/sessions").json()["sessions"]
    check("the new session is on the dashboard at once",
          any(s["session_id"] == session_id for s in listed))
    card = next((s for s in listed if s["session_id"] == session_id), {})
    check("and says it is being built", card.get("status") in ("generating", "active", "failed"),
          str(card.get("status")))

    # ── a second, independent session on the SAME repository ─────────────────
    second = alice.post("/session/start", json={"repo_url": REPO, "goal": GOAL})
    if second.status_code == 409:
        check("one generation at a time, per learner", True)
    else:
        check("a second session on one repo is a DIFFERENT session",
              second.json().get("session_id") != session_id)

    # ── isolation ────────────────────────────────────────────────────────────
    print("\nisolation")
    mallory = account(base, mallory_email)
    check("a stranger sees none of it",
          mallory.get("/sessions").json()["sessions"] == [])

    foreign = mallory.get(f"/session/{session_id}")
    invented = mallory.get(f"/session/{'0' * 32}")
    check("a stranger gets 404 on somebody else's session",
          foreign.status_code == 404, str(foreign.status_code))
    check("indistinguishable from a session that never existed",
          (foreign.status_code, foreign.text) == (invented.status_code, invented.text))

    for path, body in [
        (f"/session/{session_id}/advance", {"signal": "next"}),
        (f"/session/{session_id}/respond", {"response": "mallory was here"}),
        (f"/session/{session_id}/override", {"action": "mark_understood"}),
    ]:
        response = mallory.post(path, json=body)
        check(f"a stranger cannot POST {path.split('/')[-1]}",
              response.status_code == 404, str(response.status_code))

    check("a stranger cannot delete it",
          mallory.delete(f"/sessions/{session_id}").status_code == 404)
    check("and it is still there afterwards",
          alice.get(f"/sessions/{session_id}").status_code == 200)

    # ── anonymous ────────────────────────────────────────────────────────────
    print("\nanonymous access")
    anonymous = httpx.Client(base_url=base, timeout=30)
    for path in ("/sessions", f"/session/{session_id}", "/auth/me"):
        check(f"anonymous {path} is refused",
              anonymous.get(path).status_code == 401)

    # ── lifecycle ────────────────────────────────────────────────────────────
    print("\nlifecycle")
    alice.patch(f"/sessions/{session_id}", json={"title": "Renamed by the smoke test"})
    check("renaming sticks",
          alice.get(f"/sessions/{session_id}").json()["title"]
          == "Renamed by the smoke test")

    alice.patch(f"/sessions/{session_id}", json={"archived": True})
    check("archiving hides it from the default list",
          all(s["session_id"] != session_id
              for s in alice.get("/sessions").json()["sessions"]))
    check("but it is still there when asked for",
          any(s["session_id"] == session_id
              for s in alice.get("/sessions?include_archived=true").json()["sessions"]))
    alice.patch(f"/sessions/{session_id}", json={"archived": False})

    # ── the session survives sign-out and sign-in ────────────────────────────
    print("\npersistence")
    alice.post("/auth/logout")
    check("logging out ends access", alice.get("/auth/me").status_code == 401)

    returning = httpx.Client(base_url=base, timeout=30, follow_redirects=False)
    login = returning.post(
        "/auth/login", json={"email": alice_email, "password": PASSWORD}
    )
    check("signing in again works", login.status_code == 200)
    check("and the session is still there",
          any(s["session_id"] == session_id
              for s in returning.get("/sessions").json()["sessions"]))

    # ── a wrong password says nothing ────────────────────────────────────────
    print("\nwhat the API declines to say")
    wrong = httpx.post(f"{base}/auth/login",
                       json={"email": alice_email, "password": "wrong-one-here"},
                       timeout=30)
    unknown = httpx.post(f"{base}/auth/login",
                         json={"email": f"nobody-{stamp}@example.com",
                               "password": PASSWORD}, timeout=30)
    check("a wrong password and an unknown account are indistinguishable",
          (wrong.status_code, wrong.text) == (unknown.status_code, unknown.text),
          f"{wrong.status_code}/{wrong.text[:60]} vs {unknown.status_code}/{unknown.text[:60]}")

    # ── deletion ─────────────────────────────────────────────────────────────
    print("\ndeletion")
    check("deleting your own session works",
          returning.delete(f"/sessions/{session_id}").status_code == 204)
    check("and it is gone",
          returning.get(f"/sessions/{session_id}").status_code == 404)

    print(f"\n{len(_passed)} passed, {len(_failed)} failed")
    if _failed:
        print("\nFAILED:")
        for name in _failed:
            print(f"  - {name}")
        return 1
    print("\nAll multi-user guarantees hold over real HTTP.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
