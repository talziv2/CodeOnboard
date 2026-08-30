# `backend/auth/` — the account layer

Wraps the learning engine; the engine knows nothing about it.

> Parent: [`backend/`](../README.md) ·
> Architecture: [docs/architecture/auth.md](../../docs/architecture/auth.md) ·
> Configuration: [docs/configuration.md](../../docs/configuration.md)

---

## Modules

| File | Owns |
|---|---|
| `schema.py` | `users`, `auth_identities`, `auth_sessions`, `password_resets`, `repositories`, `session_drafts` |
| `identity.py` | Users and identities, the inert legacy owner, and `repositories` rows |
| `passwords.py` | argon2id, rehash-on-login, and the dummy verify on the miss path |
| `tokens.py` | Opaque cookie sessions — only the sha256 is stored |
| `throttle.py` | Per-IP **and** per-account, exponential |
| `deps.py` | `current_user` · `optional_user` · `owned_session` ← **the ownership chokepoint** |
| `routes.py` | `/auth/register` · `/login` · `/logout` · `/logout/all` · `/forgot` · `/reset` · `/me` |
| `google.py` · `google_routes.py` | OIDC via Authlib. Linking needs a password too |
| `reset.py` | Single-use reset tokens. **Nothing sends mail** |
| `drafts.py` | The goal interview, in a table rather than a module-level dict |
| `config.py` | Refuses to start on an insecure production environment |
| `startup.py` | Invariants checked before the process serves anything |

---

## The design decisions worth knowing

**Two tables for identity, not one.** `users` is the canonical internal identity —
the thing a session points at. `auth_identities` is how a human proves they *are*
that user: one row per `(provider, subject)`. The flat alternative
(`users.password_hash`, `users.google_sub`) is smaller today and makes every later
provider a schema change plus a new branch in every login path.

**The auth key is never the email.** `users.email` is contact and display only, and
— with no verification shipping — an unverified claim. Keying on it would mean a
person who changes their Google address becomes a different user, or inherits
somebody else's account.

**Opaque tokens, not JWTs.** One process against one SQLite file, so statelessness
buys nothing — and staying opaque means logout is a `DELETE` rather than a denylist,
there is no signing key to manage, sliding expiry replaces the refresh dance, and
"sign out everywhere" is a query. Only the **sha256** of the cookie is stored, so a
dump of `auth_sessions` is not a set of live credentials.

**Two throttle keys.** Per-IP alone lets a botnet spread attempts and never trip
it; per-account alone lets one address walk a list of accounts forever. The
in-process dict is the right shape here (it holds only "how many recent failures",
it is reconstructible, and a restart forgives — the safe direction for a lockout)
and was the wrong shape for the goal interview, which held the only copy of a
learner's work.

**Repositories are not owned.** A `repositories` row is a canonical identity for a
public artifact. Two users studying `psf/requests` share the row, the checkout and
the survey; they share nothing else. Ownership lives on the session.

**Google linking needs a password.** With no email verification of our own, "link
on matching email" is an account takeover: register a password account as someone
else's address, wait for them to click *Continue with Google*, inherit their
account. So `POST /auth/google/link` requires the account's password as well as
Google's word.

**Unconfigured Google is a first-class state.** The button is hidden and
`/auth/google/start` **redirects** to `/login?error=google_not_configured`. It
answered `503` with a JSON body once — the status was right and the medium was
wrong, because that route is only ever a full browser navigation.

**Configuration failures are refusals, not warnings.** Every value `config.py`
checks has a safe default for development and none in production, and the
difference is not something a log line survives. `check()` returns a *list*, so a
deployment missing three things learns that in one run rather than three restarts.

---

## The ownership chokepoint

```python
store.load_graph(session_id, user_id, db_path)   # user_id is REQUIRED
```

`Depends(owned_session)` is the ergonomic wrapper. Four layers back it up, because
forgetting is the failure mode:

1. the persistence signature,
2. the dependency,
3. `tests/test_route_authz_coverage.py`, which fails the build on a route that
   declares neither,
4. a middleware in `api.py` that refuses anything declaring no auth and not on a
   stated allow-list.

**404, never 403.** A foreign session and a nonexistent one answer identically,
byte for byte; a 403 confirms which ids are real.

---

## Password recovery, honestly

`POST /auth/forgot` returns the reset link **to whoever asked for it** — in
development that is the whole point, since no mail provider ships.
`config.reveals_reset_link()` is `False` in production, where returning it would be
an account-takeover endpoint for anybody able to type an email address. The
endpoint still answers there and reveals nothing.

That is a deliberate degradation, not a fix. `scripts/set_password.py` remains the
only recovery path safe to expose outside a laptop.

---

## Tests

`tests/test_auth.py`, `test_ownership.py`, `test_google_oauth.py`,
`test_password_reset.py`, `test_route_authz_coverage.py`, `test_security.py`,
`test_cors.py`, `test_migration.py`.

`test_auth.py` and `test_ownership.py` carry `pytestmark = pytest.mark.real_auth`
to opt out of the signed-in-by-default fixture, because they exercise
authentication itself.

`scripts/smoke_multiuser.py` covers what `TestClient` cannot — a real server, a
real cookie jar, two isolated accounts, and a session outliving the process. It
refuses to run against `data/sessions.db`.
