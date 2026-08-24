"""Sign in with Google. Authorization-code flow with PKCE, via Authlib.

Multi-user M6, decisions D-4 and D-7.

## What is delegated, and why

Authlib validates the ID token: its SIGNATURE against Google's published keys,
its `iss`, its `aud`, its `exp`, and the `nonce` we sent. Every one of those is a
way the flow fails silently if hand-rolled — an unverified `id_token` is just a
base64 JSON blob anybody can write, and "decode the JWT and trust the email" is
the single commonest OAuth mistake.

We never accept a token from the client. The browser carries a one-time CODE;
the exchange happens server-to-server.

## The identity key is `sub`, never the email

Google emails can change; `sub` cannot. Keying on the email would mean a person
who changes their Google address becomes a different user and loses their
sessions — or, worse, inherits somebody else's.

## Linking (D-4 + D-7), and the attack it closes

Google login for an address that already has a PASSWORD account does not simply
link. It cannot, because D-5 ships no email verification of our own, and that
makes the obvious rule an account takeover:

    1. attacker registers a password account as victim@gmail.com — nothing
       verifies they own it, because we verify nothing;
    2. the victim later clicks "Continue with Google" as victim@gmail.com;
    3. Google says `email_verified: true`, quite correctly;
    4. a naive rule links the victim's Google identity into the ATTACKER's
       account, and the victim's sessions land somewhere the attacker has a
       password for.

Google behaves perfectly throughout. The flaw is entirely ours: we let an
unverified email into `users.email` in the first place.

So the link requires proof of BOTH: Google proves the email, and a one-time
password confirmation proves the account. On success every other session for
that user is revoked, so an attacker already holding a token is ejected at the
moment the real owner proves ownership.
"""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Google's OIDC discovery document. Authlib reads the endpoints and the signing
# keys from it, so nothing here hardcodes a URL that Google may rotate.
DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"

# The short-lived cookie carrying `state` and `nonce` across the redirect. It is
# not the session cookie and must never be confused with it: it authenticates
# the CALLBACK, not the person.
FLOW_COOKIE = "co_oauth_flow"
FLOW_TTL_SECONDS = 600


class GoogleNotConfigured(RuntimeError):
    """No client id or secret. The route says so rather than half-working."""


@dataclass(frozen=True)
class GoogleProfile:
    """What the ID token told us, after Authlib validated it."""

    subject: str
    email: str | None
    email_verified: bool
    name: str | None


def is_configured() -> bool:
    return bool(os.environ.get("GOOGLE_CLIENT_ID")
                and os.environ.get("GOOGLE_CLIENT_SECRET"))


def _require_config() -> tuple[str, str]:
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise GoogleNotConfigured(
            "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set to use Google sign-in."
        )
    return client_id, client_secret


def build_client():
    """An Authlib OAuth client for Google. Built per use, not cached.

    The credentials are read from the environment each time, so a deployment
    that rotates them does not need a restart — and a test that sets them does
    not have to fight a module-level singleton created at import.
    """
    from authlib.integrations.starlette_client import OAuth

    client_id, client_secret = _require_config()
    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url=DISCOVERY_URL,
        client_kwargs={
            "scope": "openid email profile",
            # PKCE. Protects the code against interception between Google and
            # the callback — the code alone becomes useless without the verifier.
            "code_challenge_method": "S256",
        },
    )
    return oauth.create_client("google")


def new_flow_state() -> dict:
    """The one-time values that tie a callback to the request that started it.

    `state` defeats CSRF on the callback: without it, an attacker can complete
    the flow in a victim's browser with the attacker's own code, silently
    signing the victim into the ATTACKER'S account.

    `nonce` is bound into the ID token by Google and checked on the way back, so
    a token minted for a different request cannot be replayed into this one.
    """
    return {
        "state": secrets.token_urlsafe(24),
        "nonce": secrets.token_urlsafe(24),
        "verifier": secrets.token_urlsafe(48),
    }


def profile_from_token(token: dict) -> GoogleProfile:
    """The validated claims, as something with names.

    Authlib has already checked the signature, issuer, audience, expiry and
    nonce by the time this is called — this only reshapes what it produced.

    `email_verified` is read exactly as Google sent it and is never assumed.
    Absent means false, because a claim we did not receive is not one we can act
    on, and D-4 turns entirely on this value.
    """
    claims = token.get("userinfo") or {}
    subject = str(claims.get("sub") or "").strip()
    if not subject:
        raise ValueError("Google returned no subject claim")
    raw_verified = claims.get("email_verified")
    return GoogleProfile(
        subject=subject,
        email=(claims.get("email") or "").strip().lower() or None,
        email_verified=raw_verified is True or str(raw_verified).lower() == "true",
        name=(claims.get("name") or "").strip() or None,
    )


def resolve(
    profile: GoogleProfile, db_path: Path
) -> tuple[str | None, str | None]:
    """Decide what this Google identity means. Returns (user_id, needs_password_for).

    Three outcomes, and the third is the interesting one:

      (user_id, None)   an existing Google identity — sign them in;
      (user_id, None)   no identity and no colliding email — a new account;
      (None, user_id)   no identity, but the VERIFIED email already belongs to a
                        password account. Nothing is linked. The caller must ask
                        for that account's password first (D-7).

    Raises ValueError when Google did not verify the email and one would have to
    be trusted — D-4's condition, and the point at which a naive implementation
    hands over somebody else's account.
    """
    from backend.auth import identity

    existing = identity.find_identity(identity.GOOGLE, profile.subject, db_path)
    if existing is not None:
        return existing["user_id"], None

    if profile.email is None:
        raise ValueError("Google returned no email address")
    if not profile.email_verified:
        # Google itself says it has not verified this address. Creating or
        # linking on it would be trusting a claim its own issuer will not stand
        # behind.
        raise ValueError("Google has not verified that email address")

    collision = identity.find_user_by_email(profile.email, db_path=db_path)
    if collision is None:
        return None, None                       # brand new — the caller creates

    return None, collision["user_id"]           # D-7: prove the account too


def create_account(profile: GoogleProfile, db_path: Path) -> str:
    """A new user whose only identity is Google. No password, and that is fine.

    `secret_hash` stays NULL — there is no secret of ours to keep for a
    federated identity, and `passwords.verify` treats NULL as a miss rather than
    an error, so nothing can be tricked into signing in without one.
    """
    from backend.auth import identity

    user_id = identity.create_user(profile.email, profile.name, db_path=db_path)
    identity.add_identity(
        user_id, identity.GOOGLE, profile.subject,
        secret_hash=None, email_verified=True, db_path=db_path,
    )
    logger.info("google: created user=%s", user_id)
    return user_id


def link_to(user_id: str, profile: GoogleProfile, db_path: Path) -> int:
    """Attach this Google identity to an existing account. Returns sessions revoked.

    **Called only after the account's password has been confirmed** (D-7). The
    revocation is the second half of that decision and is not optional: whoever
    was holding a token for this account before the real owner proved ownership
    should stop holding one.
    """
    from backend.auth import identity, tokens

    identity.add_identity(
        user_id, identity.GOOGLE, profile.subject,
        secret_hash=None, email_verified=True, db_path=db_path,
    )
    revoked = tokens.revoke_all(user_id, db_path)
    logger.info("google: linked to user=%s, revoked %d session(s)", user_id, revoked)
    return revoked


def unlink(user_id: str, db_path: Path) -> bool:
    """Remove the Google identity, unless it is the last way in.

    Refusing the last one is not paternalism: with D-5 shipping no password
    reset, an account with no identities is an account nobody can ever open
    again, and its sessions are gone with it.
    """
    from backend.auth import identity
    from backend.learning.store import _connect

    ways_in = identity.identities_for(user_id, db_path)
    if len([i for i in ways_in if i["provider"] == identity.GOOGLE]) == 0:
        return False
    if len(ways_in) <= 1:
        return False
    with _connect(db_path) as conn:
        conn.execute(
            "DELETE FROM auth_identities WHERE user_id = ? AND provider = ?",
            (user_id, identity.GOOGLE),
        )
    return True
