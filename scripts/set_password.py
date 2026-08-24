"""Set a password from the console. The only recovery path this system has.

Multi-user M2. D-5 ships no password reset and no email verification, so a
forgotten password would otherwise mean a permanently unreachable account —
including all of that learner's sessions. This is the way back in.

## Console only, and why that is load-bearing rather than lazy

There is no endpoint and there will not be one. A reset endpoint has to
authenticate the *request* somehow, and with no verified email address there is
nothing to authenticate it with — which is precisely why D-5 deferred reset in
the first place. Running this requires shell access to the machine holding the
database, which is a real credential and one an attacker on the network does not
have.

A test asserts no route references this module, so the boundary cannot erode by
someone helpfully wiring it up.

## What it does not print

Never the password, never the hash, never a token. The operator typed the
password; echoing it back only puts it in a scrollback buffer and a terminal
log.

Usage:

    uv run python scripts/set_password.py --email you@example.com
    uv run python scripts/set_password.py --email you@example.com --create
"""

from __future__ import annotations

import argparse
import getpass
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.auth import identity, passwords, tokens  # noqa: E402
from backend.learning.store import DEFAULT_DB_PATH  # noqa: E402


def set_password(
    email: str,
    password: str,
    *,
    create: bool = False,
    db_path: Path = DEFAULT_DB_PATH,
    revoke_sessions: bool = True,
) -> dict:
    """Set or create a password identity. Returns a report; raises on refusal."""
    normalised = identity.validate_email(email)
    passwords.validate(password)

    user = identity.find_user_by_email(normalised, db_path=db_path)
    existing = identity.find_identity(identity.PASSWORD, normalised, db_path)

    if user is None:
        if not create:
            raise SystemExit(
                f"No account for {normalised}. Pass --create to make one."
            )
        user_id = identity.create_user(normalised, db_path=db_path)
        created_user = True
    else:
        user_id = user["user_id"]
        created_user = False

    secret = passwords.hash_password(password)
    if existing is None:
        identity.add_identity(
            user_id, identity.PASSWORD, normalised, secret_hash=secret,
            db_path=db_path,
        )
        created_identity = True
    else:
        if existing["user_id"] != user_id:
            # The identity belongs to a different account than the email does.
            # Refused rather than repaired: silently moving an identity between
            # users is an account takeover with a friendly name.
            raise SystemExit(
                "Refusing: that password identity belongs to a different user."
            )
        identity.set_password_hash(user_id, normalised, secret, db_path)
        created_identity = False

    # EVERY EXISTING SESSION IS ENDED. Changing a password is what someone does
    # when they think it has been learned by somebody else, so leaving live
    # tokens in place would preserve exactly the access they are trying to
    # revoke. The operator signs in again afterwards.
    ended = tokens.revoke_all(user_id, db_path) if revoke_sessions else 0

    return {
        "user_id": user_id,
        "email": normalised,
        "created_user": created_user,
        "created_identity": created_identity,
        "sessions_revoked": ended,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--create", action="store_true",
                        help="create the account if it does not exist")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    args = parser.parse_args()

    # Never from a flag: a password on the command line lands in shell history
    # and in the process list, where every other user on the machine can read it.
    password = getpass.getpass("New password: ")
    if password != getpass.getpass("Repeat: "):
        print("Passwords did not match.")
        return 1

    try:
        report = set_password(
            args.email, password, create=args.create, db_path=Path(args.db)
        )
    except passwords.WeakPasswordError as exc:
        print(f"Refused: {exc}")
        return 1
    except identity.InvalidEmailError as exc:
        print(f"Refused: {exc}")
        return 1
    except sqlite3.IntegrityError as exc:
        print(f"Refused: {exc}")
        return 1

    what = "Created" if report["created_identity"] else "Updated"
    print(f"{what} the password for {report['email']} (user {report['user_id']}).")
    if report["created_user"]:
        print("A new account was created for that address.")
    if report["sessions_revoked"]:
        print(f"Ended {report['sessions_revoked']} existing session(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
