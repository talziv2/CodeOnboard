"""Move the pre-accounts sessions from the legacy user to a real account.

Multi-user M2, D-3. The M1 migration parked every session written before accounts
existed on an inert `legacy@codeonboard.local` user — inactive, with no auth
identity, so nobody can sign in as it. This empties that parking space into a
real account once one exists.

## This is a bulk ownership rewrite, which is the operation ownership exists to prevent

So every guard below is deliberate, and none of them is optional:

  - the target must resolve to EXACTLY ONE user;
  - the target must be a REAL account — active, with at least one way to sign in.
    Adopting into another parking space would move the sessions somewhere still
    unreachable while reporting success;
  - only sessions currently owned BY THE LEGACY USER move. Never "all sessions",
    never "sessions with no owner": if a session already belongs to somebody, it
    is not this script's business;
  - `--yes` is required, after printing what will move and where;
  - it runs in ONE transaction, so a partial adoption cannot happen;
  - it is idempotent — a second run moves zero rows and says so.

Usage:

    uv run python scripts/adopt_legacy_sessions.py --email you@example.com
    uv run python scripts/adopt_legacy_sessions.py --email you@example.com --yes
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.auth import identity  # noqa: E402
from backend.learning.store import DEFAULT_DB_PATH, _connect  # noqa: E402


class AdoptionRefused(RuntimeError):
    """A precondition failed. Nothing was changed."""


def plan(email: str, db_path: Path = DEFAULT_DB_PATH) -> dict:
    """What an adoption would do. Touches nothing.

    Raises `AdoptionRefused` when it could not proceed, so a dry run fails for
    the same reasons an apply would — the point of a dry run being to find that
    out before committing to it.
    """
    normalised = identity.normalize_email(email)
    if not Path(db_path).exists():
        raise AdoptionRefused(f"No database at {db_path}.")

    target = identity.find_user_by_email(normalised, db_path=db_path)
    if target is None:
        raise AdoptionRefused(
            f"No account for {normalised}. Register through the app first."
        )
    if not target.get("is_active", 1):
        raise AdoptionRefused(f"{normalised} is not an active account.")

    ways_in = identity.identities_for(target["user_id"], db_path)
    if not ways_in:
        # THE CHECK THAT MATTERS MOST. The legacy user is precisely an account
        # with no identity; adopting into another one would move 91 sessions
        # somewhere equally unreachable and report success.
        raise AdoptionRefused(
            f"{normalised} has no way to sign in — adopting into it would put "
            "the sessions somewhere still unreachable."
        )

    legacy_id = identity.get_legacy_user_id(db_path)
    if legacy_id is None:
        raise AdoptionRefused(
            "No legacy user. Run backend/migrations/001_multi_user.py first."
        )
    if legacy_id == target["user_id"]:
        raise AdoptionRefused("The target IS the legacy user.")

    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT session_id, repo_url, title, schema_version "
            "FROM sessions WHERE user_id = ? ORDER BY COALESCE(last_active_at, updated_at)",
            (legacy_id,),
        ).fetchall()

    return {
        "db": str(db_path),
        "email": normalised,
        "target_user_id": target["user_id"],
        "target_providers": sorted({i["provider"] for i in ways_in}),
        "legacy_user_id": legacy_id,
        "sessions": [dict(r) for r in rows],
        "count": len(rows),
    }


def adopt(email: str, db_path: Path = DEFAULT_DB_PATH) -> dict:
    """Perform the adoption. One transaction; returns the same report plus a count."""
    report = plan(email, db_path)
    if report["count"] == 0:
        report["moved"] = 0
        return report

    with _connect(db_path) as conn:
        # `WHERE user_id = legacy` and nothing else. Scoped by the CURRENT owner
        # rather than by a list of ids gathered a moment ago, so a session that
        # changed hands between the plan and the apply is left alone rather than
        # taken.
        moved = conn.execute(
            "UPDATE sessions SET user_id = ? WHERE user_id = ?",
            (report["target_user_id"], report["legacy_user_id"]),
        ).rowcount
    report["moved"] = moved
    return report


def _print(report: dict, *, applied: bool) -> None:
    print("ADOPTING" if applied else "DRY RUN - nothing will change")
    print()
    print(f"  database        {report['db']}")
    print(f"  target          {report['email']}  ({report['target_user_id']})")
    print(f"  signs in with   {', '.join(report['target_providers'])}")
    print(f"  from legacy     {report['legacy_user_id']}")
    print(f"  sessions        {report['count']}")
    by_repo: dict[str, int] = {}
    versions: dict[int, int] = {}
    for row in report["sessions"]:
        by_repo[row["repo_url"]] = by_repo.get(row["repo_url"], 0) + 1
        versions[row["schema_version"]] = versions.get(row["schema_version"], 0) + 1
    for repo, n in sorted(by_repo.items(), key=lambda kv: -kv[1]):
        print(f"    {n:>4}  {repo}")
    print(f"  schema versions {dict(sorted(versions.items()))}")
    if applied:
        print(f"\nMoved {report.get('moved', 0)} session(s).")
    else:
        print("\nRe-run with --yes to adopt them.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True,
                        help="the real account to adopt the sessions into")
    parser.add_argument("--yes", action="store_true",
                        help="perform the adoption (default is a dry run)")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    args = parser.parse_args()

    db_path = Path(args.db)
    try:
        report = adopt(args.email, db_path) if args.yes else plan(args.email, db_path)
    except AdoptionRefused as exc:
        print(f"Refused: {exc}")
        return 1

    _print(report, applied=args.yes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
