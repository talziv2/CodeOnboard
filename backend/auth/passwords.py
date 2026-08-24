"""Password hashing. Argon2id, via argon2-cffi, at library defaults.

Multi-user M2. This is the one part of authentication that must never be
hand-rolled, so the module is deliberately thin: it wraps `argon2-cffi` and adds
the two behaviours a login path needs from it — rehash-on-verify, and a dummy
verify that keeps a miss from being distinguishable by timing.

## Why the defaults are not tuned

`argon2-cffi`'s defaults track the OWASP recommendation and move with the
library. Pinning our own numbers here would freeze them at whatever was
reasonable on the day this was written, and the hash format is self-describing —
every stored hash carries the parameters it was made with — so raising them later
is a config change plus `needs_rehash`, not a migration.

## What is NOT here

No password-strength scoring, no composition rules. Length is the only
requirement that survives contact with evidence, and a small common-password
check catches the rest of what a rule would. Complexity rules mostly produce
`Password1!`.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# One hasher for the process. It carries the parameters new hashes are made with;
# verification reads them from the hash itself, so raising these never
# invalidates an existing password.
_hasher = PasswordHasher()

# Long enough to matter, short enough not to push people into a manager they do
# not have. NIST's guidance is length over composition, and 10 is where a
# passphrase becomes natural.
MIN_PASSWORD_LENGTH = 10

# A dummy hash of a value nobody will ever submit, verified on the miss path so
# that "no such account" costs the same as "wrong password". Computed once at
# import: doing it per-request would be a wasted hash on every miss, and doing it
# lazily would make the FIRST miss slower than the rest — which is itself a
# signal.
_DUMMY_HASH = _hasher.hash("a password that is never anyone's")

# The shortlist, not a dictionary. A 100k-entry wordlist is a dependency and a
# file to ship; these are the ones that actually turn up, and the check costs
# nothing. Lower-cased, compared lower-cased.
_COMMON_PASSWORDS = frozenset({
    "password", "password1", "password123", "passw0rd", "letmein123",
    "12345678", "123456789", "1234567890", "qwertyuiop", "qwerty123",
    "iloveyou1", "adminadmin", "administrator", "welcome123", "changeme",
    "codeonboard", "letmein1234", "monkey1234", "trustno1234", "abc12345",
})


class WeakPasswordError(ValueError):
    """The password was rejected before it was ever hashed."""


def validate(password: str) -> None:
    """Raise `WeakPasswordError` if this password may not be used.

    Called at registration and at password change, never at login: an existing
    password that would no longer be accepted must still let its owner in, or
    raising the minimum length locks people out of their own accounts.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(
            f"Use at least {MIN_PASSWORD_LENGTH} characters."
        )
    if password.strip().lower() in _COMMON_PASSWORDS:
        raise WeakPasswordError("That password is too common. Pick another.")


def hash_password(password: str) -> str:
    """Argon2id hash, encoded with its own parameters."""
    return _hasher.hash(password)


def verify(stored_hash: str | None, password: str) -> bool:
    """Is this the right password? Constant-ish time whether or not it is.

    `stored_hash` is None for a federated identity — a Google row has no secret
    of ours — and that is a miss rather than an error: it means "this identity
    does not authenticate by password". The dummy verify still runs, so
    "identity has no password" is not distinguishable from "wrong password"
    either.
    """
    if not stored_hash:
        # Still pay for a verification, so "this identity has no password of
        # ours" costs the same as "wrong password". `verify_dummy` swallows the
        # mismatch it is guaranteed to raise — calling `_hasher.verify` directly
        # here let that exception escape, which turned a federated identity into
        # a 500 instead of a refusal.
        verify_dummy()
        return False
    try:
        return _hasher.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def verify_dummy() -> None:
    """Burn one verification's worth of time on a miss.

    THE ATTACK THIS CLOSES: without it, "no account with that email" returns in
    microseconds while "wrong password" takes the ~50ms Argon2 is tuned to cost.
    That difference is measurable over a handful of requests, and it turns the
    login form into an account-enumeration oracle regardless of how carefully the
    two responses are worded.

    Deliberately not a `verify()` call the caller might forget: the login path
    has exactly two branches and both must cost the same, so this is the name of
    the thing the miss branch owes.
    """
    try:
        _hasher.verify(_DUMMY_HASH, "wrong")
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        pass


def needs_rehash(stored_hash: str) -> bool:
    """Was this hash made with weaker parameters than we now use?

    Checked on a SUCCESSFUL login, which is the only moment the plaintext is in
    hand and therefore the only moment a stronger hash can be made. Raising the
    parameters then upgrades accounts as people return, with no migration and no
    forced reset.
    """
    try:
        return _hasher.check_needs_rehash(stored_hash)
    except (InvalidHashError, ValueError):
        # Unreadable hash. Not "needs rehash" — there is nothing to rehash, and
        # saying True here would invite a caller to overwrite it with something
        # derived from an unverified password.
        return False
