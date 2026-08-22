"""Move existing checkouts from `data/repos/<name>` to `data/repos/<owner>/<name>`.

## Why this is a migration and not just "delete the directory and re-clone"

`data/repos/` is gitignored and every checkout in it is reproducible, so the
cheapest thing would be to delete it and let `clone_repo` refill it. That would
be wrong, and expensively so.

A clone is pinned: `clone_repo` never updates a checkout in place, which is
exactly what lets two caches key on the commit it happens to hold.

    repo_survey    keyed (owner/repo, commit_sha, schema)  — 6 rows, one Haiku
                   exploration each
    investigation  keyed (session_id, commit_sha)          — 56 rows, and
                   `load_investigation` returns None when the recorded commit is
                   not the one checked out

Re-cloning fetches whatever HEAD is *today*. For every repository whose default
branch has moved since it was first cloned — which, for `fastapi` cloned in May,
is certain — the new commit matches neither cache. The surveys would be
regenerated at cost, and every one of the 56 dossiers would read as unavailable,
silently degrading those sessions' lessons to the skeleton fallback for the rest
of their lives. Nothing would look broken; the lessons would just get worse.

Moving the directory keeps the commit, so both caches stay valid and the change
is what it should be — a rename.

## The owner comes from the checkout, not from the database

Each directory is asked for its own `origin` remote. That is authoritative: it is
the URL the clone was actually made from, so it cannot disagree with the code on
disk. Deriving the owner from `sessions.repo_url` instead would guess, and would
have nothing to say about the two checkouts here that no session references.

## Duplicates

Normalising owner and name to lower case collapses spellings that were separate
directories before. This dev machine has two such pairs:

    aima-python           and  aima-python.git           → aimacode/aima-python
    everything-claude-code and  everything-claude-code.git
                          (WorldFlowAI vs worldflowai)   → worldflowai/…

Only one can occupy the destination. The one without the `.git` suffix wins —
that is the canonical spelling and the one the sessions were started from — and
the loser is REPORTED, never deleted, unless `--remove-duplicates` is passed.
Deleting a checkout is the one irreversible thing here, so it does not happen by
default and never happens to a directory that was not first proved redundant.

Usage:

    uv run python scripts/migrate_repo_layout.py              # dry run, default
    uv run python scripts/migrate_repo_layout.py --apply
    uv run python scripts/migrate_repo_layout.py --apply --remove-duplicates
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import git  # noqa: E402

from backend.repo.cloner import REPOS_DIR, parse_repo_url  # noqa: E402


class Plan:
    """What one existing directory should become."""

    def __init__(self, source: Path, destination: Path | None, note: str):
        self.source = source
        self.destination = destination
        self.note = note


# EVERY GitPython handle is closed before we try to move anything.
#
# THE BUG THIS FIXES, found by this script failing on its own first apply:
# `git.Repo(path)` opens the pack index and keeps it open until the object is
# collected. On Windows an open handle makes `os.rename` fail with
# `PermissionError: [WinError 32] ... being used by another process`. So the
# script inspected five checkouts, held five sets of pack handles, and then
# could not move the first one — it locked the very directories it was about to
# migrate. `with` closes each handle at the end of the statement, so by the time
# the plans are built nothing is held.


def _origin_url(path: Path) -> str | None:
    try:
        with git.Repo(path) as repo:
            return repo.remote("origin").url
    except Exception:
        return None


def _commit(path: Path) -> str:
    try:
        with git.Repo(path) as repo:
            return repo.head.commit.hexsha[:8]
    except Exception:
        return "unknown"


def _rename(source: Path, destination: Path) -> None:
    """Move `source` to `destination`, including when one contains the other.

    ## The case that needs two steps: owner == name

    `data/repos/fastapi` holds the fastapi checkout, and its destination is
    `data/repos/fastapi/fastapi` — a path INSIDE the thing being moved. A direct
    rename of a directory into itself is refused by every OS, and the flat
    checkout also already contains a real `fastapi/` source package at exactly
    that path, so the destination "exists" for two unrelated reasons.

    This is not an oddity of one repository. `owner == name` is one of the
    commonest shapes on GitHub — django/django, pytest-dev/pytest,
    fastapi/fastapi — so a migration that cannot handle it is a migration that
    fails on ordinary input.

    The fix is a hop through a sibling that is outside both paths. Still rename
    only, still never a copy: if the second step fails, the first is undone, so
    the checkout ends up either fully moved or exactly where it started.
    """
    if destination.is_relative_to(source):
        staging = source.with_name(f".{source.name}.moving")
        os.rename(source, staging)
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.rename(staging, destination)
        except OSError:
            os.rename(staging, source)   # put it back exactly as it was
            raise
        return
    os.rename(source, destination)


def _backend_is_running(port: int = 8000) -> bool:
    """Is something listening on the backend's port?

    Asked because a live `uvicorn --reload` is the other half of the same
    failure: it holds checkouts open through `build_skeleton` and `get_commit_sha`,
    and — worse — a running backend that has already picked up the new
    `clone_repo` will CLONE FRESH into the new layout while this script is
    working. A fresh clone lands on today's HEAD, which is exactly the commit
    change this migration exists to avoid.

    A socket probe rather than a process scan: it answers the question that
    actually matters (can something serve requests right now) and needs no
    permissions.
    """
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.4)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _candidates() -> list[Path]:
    """Top-level directories that are git checkouts.

    Only the top level: a directory that is already `<owner>/<name>` has no
    `.git` of its own at this depth, so a second run finds nothing to do. That
    is what makes this idempotent rather than merely safe to repeat.
    """
    if not REPOS_DIR.exists():
        return []
    return sorted(
        d for d in REPOS_DIR.iterdir()
        if d.is_dir() and (d / ".git").exists()
    )


def build_plans() -> tuple[list[Plan], list[Plan]]:
    """(moves, duplicates) — decided before anything is touched."""
    resolved: list[tuple[Path, Path]] = []
    skipped: list[Plan] = []

    for source in _candidates():
        origin = _origin_url(source)
        if origin is None:
            skipped.append(Plan(source, None, "no origin remote - left alone"))
            continue
        try:
            owner, name = parse_repo_url(origin)
        except ValueError as exc:
            skipped.append(Plan(source, None, f"unsupported origin ({exc})"))
            continue
        resolved.append((source, REPOS_DIR / owner / name))

    # Group by destination so a collision is decided once, with both candidates
    # in hand, rather than by whichever happened to be processed first.
    by_destination: dict[Path, list[Path]] = {}
    for source, destination in resolved:
        by_destination.setdefault(destination, []).append(source)

    moves: list[Plan] = []
    duplicates: list[Plan] = list(skipped)
    for destination, sources in sorted(by_destination.items()):
        if len(sources) == 1:
            winner = sources[0]
        else:
            # Canonical spelling first (no `.git` suffix), then the most
            # recently touched — a deterministic rule, so a dry run and the
            # apply that follows it always choose the same directory.
            winner = sorted(
                sources,
                key=lambda p: (p.name.endswith(".git"), -p.stat().st_mtime),
            )[0]
            for loser in sources:
                if loser is not winner:
                    duplicates.append(
                        Plan(loser, destination,
                             f"duplicate of {winner.name} @ {_commit(loser)}")
                    )
        if winner.resolve() == destination.resolve():
            continue   # already in place
        moves.append(Plan(winner, destination, f"commit {_commit(winner)}"))

    return moves, duplicates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="perform the moves (default is a dry run)")
    parser.add_argument("--remove-duplicates", action="store_true",
                        help="delete redundant checkouts after a successful move")
    parser.add_argument("--force", action="store_true",
                        help="apply even while the backend appears to be running")
    args = parser.parse_args()

    if args.apply and not args.force and _backend_is_running():
        print("The backend appears to be running on :8000.")
        print("It holds open handles on these checkouts (so the move will fail),")
        print("and it will clone fresh into the new layout while this runs (so a")
        print("checkout can silently move to a newer commit, invalidating its")
        print("survey and every dossier recorded against it).")
        print()
        print("Stop it and re-run, or pass --force if you are sure.")
        return 1

    # This runs on a Windows console whose default codepage is cp1252, which
    # cannot encode an arrow or an em dash. Output is ASCII-only for that
    # reason: a migration that crashes while REPORTING what it would do is a
    # migration nobody can dry-run.

    moves, duplicates = build_plans()

    if not moves and not duplicates:
        print("Nothing to do - every checkout is already <owner>/<name>.")
        return 0

    header = "APPLYING" if args.apply else "DRY RUN - nothing will change"
    print(f"{header}\n")

    for plan in moves:
        rel = plan.destination.relative_to(REPOS_DIR)
        print(f"  move  {plan.source.name:45} -> {rel}   ({plan.note})")
    for plan in duplicates:
        print(f"  keep  {plan.source.name:45}   {plan.note}")

    if not args.apply:
        print("\nRe-run with --apply to perform the moves.")
        return 0

    moved = 0
    blocked = 0
    for plan in moves:
        # `mkdir` only when the destination is not inside the source — for the
        # owner == name case, creating the parent would be creating a directory
        # inside the very checkout about to be moved.
        inside = plan.destination.is_relative_to(plan.source)
        if not inside:
            plan.destination.parent.mkdir(parents=True, exist_ok=True)
        # A destination that already exists is a genuine conflict ONLY when it is
        # not inside the source. When it is inside, "exists" means the checkout
        # contains a source package at that path (fastapi/fastapi), which is not
        # a conflict at all — it travels with the move.
        if plan.destination.exists() and not inside:
            print(f"  ! {plan.destination} already exists - skipped")
            continue
        # RENAME ONLY. NEVER copy-then-delete.
        #
        # This was `shutil.move`, which silently falls back to
        # copytree + rmtree(source) when the rename fails. On the first apply the
        # rename failed on a held file handle, the fallback copied the checkout
        # successfully and then got part-way through deleting the ORIGINAL before
        # hitting the same lock — leaving a good destination and a half-erased
        # source, from an operation that was supposed to be a rename.
        #
        # A migration must never destroy the thing it could not move. `os.rename`
        # is atomic on one filesystem and simply fails otherwise, so a blocked
        # move now leaves the source exactly as it found it.
        try:
            _rename(plan.source, plan.destination)
        except OSError as exc:
            blocked += 1
            print(f"  ! {plan.source.name}: {exc.strerror or exc}")
            print("    source left untouched. Stop anything using this checkout "
                  "(the backend on :8000) and re-run.")
            continue
        moved += 1

    removed = 0
    if args.remove_duplicates:
        for plan in duplicates:
            # Only ones proved redundant: a skipped directory has no destination
            # and is never a deletion candidate.
            if plan.destination is None or not plan.destination.exists():
                continue
            shutil.rmtree(plan.source, ignore_errors=True)
            removed += 1

    print(f"\nMoved {moved} checkout(s); removed {removed} duplicate(s).")
    if duplicates and not args.remove_duplicates:
        print("Duplicates were left in place. Re-run with --remove-duplicates "
              "to delete them once you are satisfied with the result.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
