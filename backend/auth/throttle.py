"""Brute-force throttling for the two endpoints that take a password.

Multi-user M2.

## In-process and bounded, on purpose

This is a module-level dict, which is the shape multi-user.md §2 criticises
elsewhere — so it is worth saying why it is the right one here and wrong there.

The goal-dialogue dict held THE ONLY COPY of a learner's in-flight interview:
losing it to an eviction or a restart lost their work, and a shared 64-entry cap
meant one busy user could evict another's. This holds only "how many times has
this key failed recently", which is:

  - reconstructible — a restart forgives outstanding failures, and forgiving is
    the safe direction for a lockout;
  - not per-user state anyone can lose;
  - bounded by eviction of EXPIRED entries first, so a flood cannot push out a
    live counter.

A shared store would be needed the moment there are two processes. There is one.

## Two keys, not one

Per-IP alone lets an attacker with a botnet spread attempts across addresses and
never trip it. Per-account alone lets one address walk a list of accounts, one
attempt each, forever. Both are checked, and the account counter is what actually
protects a specific person's password.

Locking on the ACCOUNT is also a denial-of-service against that account, which is
why the lockout is short and exponential rather than long and flat: it costs an
attacker exponentially while costing the real owner a wait they will usually not
notice.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

# Failures before the first lockout. Generous enough for a person mistyping a
# password they know, short enough to make guessing pointless.
FREE_ATTEMPTS = 5

# Lockout doubles per failure past the free ones, capped. 2s, 4s, 8s … 15min.
BASE_PENALTY_SECONDS = 2.0
MAX_PENALTY_SECONDS = 900.0

# A key with no failure for this long is forgotten entirely.
WINDOW_SECONDS = 3600.0

# Backstop against unbounded growth. Expired entries are evicted first, so a
# flood of new keys cannot displace a live counter (see `_evict`).
MAX_KEYS = 4096


@dataclass
class _Record:
    failures: int = 0
    last_failure: float = 0.0
    locked_until: float = 0.0


class Throttle:
    """Failure counters keyed by an opaque string. Thread-safe.

    A class rather than module functions so tests can use an isolated instance
    and so a second one (per-IP vs per-account) costs nothing.
    """

    def __init__(self) -> None:
        self._records: dict[str, _Record] = {}
        self._lock = threading.Lock()

    def retry_after(self, key: str, *, now: float | None = None) -> float:
        """Seconds the caller must wait, or 0.0 when it may proceed."""
        moment = time.monotonic() if now is None else now
        with self._lock:
            record = self._records.get(key)
            if record is None:
                return 0.0
            if moment - record.last_failure > WINDOW_SECONDS:
                del self._records[key]
                return 0.0
            return max(0.0, record.locked_until - moment)

    def record_failure(self, key: str, *, now: float | None = None) -> float:
        """Count a failed attempt. Returns the new lockout in seconds."""
        moment = time.monotonic() if now is None else now
        with self._lock:
            self._evict(moment)
            record = self._records.get(key)
            if record is None or moment - record.last_failure > WINDOW_SECONDS:
                record = _Record()
                self._records[key] = record
            record.failures += 1
            record.last_failure = moment
            over = record.failures - FREE_ATTEMPTS
            if over > 0:
                penalty = min(
                    BASE_PENALTY_SECONDS * (2 ** (over - 1)), MAX_PENALTY_SECONDS
                )
                record.locked_until = moment + penalty
                return penalty
            record.locked_until = 0.0
            return 0.0

    def record_success(self, key: str) -> None:
        """Forget this key. A correct password clears the slate.

        Deliberate: an attacker who guesses correctly has already won, so
        keeping the counter would only punish the real owner who mistyped four
        times and then got it right.
        """
        with self._lock:
            self._records.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._records.clear()

    def _evict(self, moment: float) -> None:
        """Make room, expired entries first. Caller holds the lock."""
        if len(self._records) < MAX_KEYS:
            return
        stale = [
            key for key, record in self._records.items()
            if moment - record.last_failure > WINDOW_SECONDS
        ]
        for key in stale:
            del self._records[key]
        if len(self._records) < MAX_KEYS:
            return

        # Still full. A LOCKED-OUT KEY IS NEVER EVICTED FIRST.
        #
        # THE ATTACK THIS CLOSES, and it is why "least recently failed" alone was
        # not enough: an attacker who has tripped the lockout on an account can
        # generate thousands of junk keys to force eviction, and if the victim's
        # counter is eligible to be dropped, the flood buys its own amnesty. That
        # is not hypothetical — the first version of this evicted purely by
        # timestamp, and a test that floods with a SINGLE timestamp evicted the
        # locked key roughly at random, because equal timestamps sort
        # arbitrarily.
        #
        # So eviction takes unlocked keys first, oldest-failure first among them.
        # Those are the ones closest to being forgiven anyway, and dropping one
        # costs nothing an attacker can use.
        unlocked = [
            (key, record) for key, record in self._records.items()
            if record.locked_until <= moment
        ]
        needed = len(self._records) - MAX_KEYS + 1
        for key, _ in sorted(unlocked, key=lambda item: item[1].last_failure)[:needed]:
            del self._records[key]
        if len(self._records) < MAX_KEYS:
            return
        # Every key is locked out: a genuine large-scale attack rather than a
        # flood around one victim. Nothing can be preserved for free at this
        # point, so fall back to oldest-failure-first and let the table breathe.
        for key, _ in sorted(
            self._records.items(), key=lambda item: item[1].last_failure
        )[:needed]:
            del self._records[key]


# The two live counters. Reset between tests via `reset_all`.
by_ip = Throttle()
by_account = Throttle()


def reset_all() -> None:
    by_ip.reset()
    by_account.reset()
