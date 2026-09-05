"""Prepare the writable working copy that `Continue in Claude Code` opens.

    uv run python tools/prepare_workspace.py --session <id> --db data/demo.db

Creates `workspace/<owner>/<name>` at the SAME commit the session's anchors were
resolved against, and writes the `.mcp.json` that points a coding agent at that
session. One command, so a second machine reproduces the demo by cloning
CodeOnboard and running this — there is no absolute path written down anywhere to
go stale.

## Two checkouts, and why they must stay two

    data/repos/<owner>/<name>   ONE shared checkout, pinned, READ-ONLY.
                                `anchors.resolve` resolves every anchor in every
                                session against it (D2).
    workspace/<owner>/<name>    the learner's own copy, WRITABLE, edited by a
                                coding agent.

A coding agent editing the first would move the ground under every lesson in
every session. This script REFUSES to write anywhere under `data/`, and that
refusal is tested.

## The commit is the point

The handoff's every `file:symbol` is true at one revision. The working copy is
checked out at exactly that revision, so the `verify` step the agent is told to
run — `git rev-parse HEAD` against `repository.commit` — passes. A workspace on a
different commit is worse than none: the context would be confidently wrong.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.repo.cloner import get_commit_sha, parse_repo_url, repo_dir  # noqa: E402

WORKSPACE_DIR = "workspace"


def _session_row(db: Path, session_id: str) -> tuple[str, str]:
    """(repo_url, user_id) for one session, read straight from the database.

    A local setup tool, like `tools/demo_checkpoints.py`: it runs as the machine's
    own user against that user's own database, so there is no ownership boundary
    to cross here — and it never writes a row.
    """
    connection = sqlite3.connect(db)
    try:
        row = connection.execute(
            "SELECT repo_url, user_id FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    finally:
        connection.close()
    if not row:
        raise SystemExit(f"session {session_id} not found in {db}")
    return row[0], row[1]


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def prepare(session_id: str, db: Path) -> Path:
    repo_url, user_id = _session_row(db, session_id)
    owner, name = parse_repo_url(repo_url)

    # The revision the investigation was written against — read from the SHARED
    # checkout, which is the thing anchors resolve against. Not HEAD of the
    # remote: that moves.
    grounding = repo_dir(repo_url)
    if not grounding.is_absolute():
        grounding = ROOT / grounding
    if not grounding.exists():
        raise SystemExit(
            f"no grounding checkout at {grounding} — run a session for "
            f"{owner}/{name} first, or the workspace has no revision to match"
        )
    commit = get_commit_sha(str(grounding))

    target = ROOT / WORKSPACE_DIR / owner / name
    # The refusal that keeps the two checkouts apart.
    if (ROOT / "data") in target.parents:
        raise SystemExit(f"refusing to prepare a writable clone under data/: {target}")

    if (target / ".git").exists():
        current = get_commit_sha(str(target))
        if current != commit:
            print(f"  moving {target.name} from {current[:12]} to {commit[:12]}")
            _git("fetch", "--depth", "1", "origin", commit, cwd=target)
            _git("checkout", "--force", "FETCH_HEAD", cwd=target)
    else:
        target.mkdir(parents=True, exist_ok=True)
        print(f"  cloning {owner}/{name} at {commit[:12]}")
        _git("init", "--quiet", cwd=target)
        _git("remote", "add", "origin", repo_url, cwd=target)
        _git("fetch", "--quiet", "--depth", "1", "origin", commit, cwd=target)
        _git("checkout", "--quiet", "FETCH_HEAD", cwd=target)

    # The config that points a coding agent at THIS session. Written here rather
    # than copied by hand so it can never carry a stale session id.
    config = {
        "mcpServers": {
            "codeonboard": {
                "type": "stdio",
                "command": "uv",
                "args": ["run", "--directory", ROOT.as_posix(),
                         "python", "-m", "backend.mcp_server"],
                "env": {
                    "CODEONBOARD_SESSION": session_id,
                    "CODEONBOARD_USER": user_id,
                    "CODEONBOARD_DB": db.as_posix(),
                    "PYTHONIOENCODING": "utf-8",
                },
            }
        }
    }
    (target / ".mcp.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )

    print(f"  workspace  {target}")
    print(f"  commit     {get_commit_sha(str(target))}")
    print(f"  grounding  {commit}  ({'match' if get_commit_sha(str(target)) == commit else 'MISMATCH'})")
    print(f"  session    {session_id}")
    print()
    print("One step left, and only once per machine:")
    print(f"  cd {target} && claude")
    print("  accept the trust prompt, then approve the `codeonboard` server.")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True)
    parser.add_argument("--db", default="data/sessions.db")
    args = parser.parse_args()

    db = Path(args.db)
    if not db.is_absolute():
        db = ROOT / db
    if not db.exists():
        raise SystemExit(f"{db} does not exist")
    prepare(args.session, db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
