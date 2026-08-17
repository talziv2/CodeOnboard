# M6 / AC2 — verification validated live

**Date:** 2026-08-18 · **Probe:** `scripts/verification_probe.py` ·
**Raw data:** [`verification-cases.json`](verification-cases.json) ·
8 calls, ≈$0.02, `CODEONBOARD_GAPS=1`.

**Verdict: AC2 PASSES.** Both double dissociations pass, and silence did not
close a gap.

| case | dissociation | overlap with original |
|---|---|---|
| `requests/architecture` — AuthBase contract | **PASS** | 0.11 |
| `requests/component` — auth parameter forms | **PASS** | 0.15 |
| silence never closes a gap | **PASS** | — |

## What AC2 demanded

[`gap-model.md` §4](../../gap-model.md#4-acceptance-cases--carried-from-the-original-defect)
requires two things and states plainly that the second cannot be asserted:

> the verification prompt is **not** the original prompt (asserted mechanically),
> and a learner still holding the misconception **cannot answer it correctly**
> (judged live — the one property no assertion can carry).

The second is tested as a **double dissociation**, with both answers authored
before any question was generated:

| answer | required | got |
|---|---|---|
| `holding` — expresses the false belief | `resolved: false` | false, both cases |
| `corrected` — the true model, in different words from the lesson | `resolved: true` | true, both cases |

Both halves matter: a question everything fails is impossible, not good. Both
directions held on both nodes.

## Case 1 — `requests/architecture`, the AuthBase contract

False belief: *"The auth handler opens the connection so it can read the
server's challenge."*

| | |
|---|---|
| **original** | "The auth handler is given a `PreparedRequest` and must return a `PreparedRequest`. Looking at `prepare_auth()`, describe the line between what the auth handler owns and what it must NOT own…" |
| **verification** | "Suppose an auth handler needs to add a custom header, but first wants to check what `Content-Length` the request currently has. Should it read `self.headers` and `self.body` from the PreparedRequest it receives, use them to decide what header to add, then return the modified request? Why or why not?" |

A different situation, not a restatement — content-word overlap **0.11**.

- `holding` → **unresolved.** *"reiterates the original false belief rather than
  correcting it."*
- `corrected` → **resolved.** *"auth handlers operate during request
  preparation, before transmission, and cannot access server responses."*

## Case 2 — `requests/component`, auth parameter forms

False belief: *"Tuples passed as auth are sent directly to the server as
separate fields in the request body."*

| | |
|---|---|
| **original** | "If a developer passes `auth=('alice', 'secret')`… what code path does that tuple take in `prepare_auth()`, and what does the final `auth_handler(self)` call actually invoke?" |
| **verification** | "Suppose a developer modifies `prepare_auth()` to skip the tuple check and just does `auth_handler = auth` directly for all auth values. They then call `requests.get(url, auth=('user', 'pass'))`. What would happen to the request, and why?" |

**The strongest question of the three.** It is a counterfactual change to the
code rather than a question about it, and it cannot be answered without knowing
that a tuple is *promoted* to `HTTPBasicAuth` — which is precisely the belief
under test. Overlap **0.15**.

- `holding` → **unresolved.** *"the false belief about tuple handling remains
  firmly held; the developer has not grasped that tuples are internally promoted
  to HTTPBasicAuth."*
- `corrected` → **resolved.** *"tuples are promotional shorthand for
  HTTPBasicAuth and result in an Authorization header, not request body fields."*

## The rationales fail for the RIGHT reason

This was the pre-registered risk: a `holding` answer could be marked unresolved
because it *did not address the question* rather than because it *asserted
something false*. Silence and error both produce `resolved: false`, so the
verdict alone cannot tell them apart, and a pass earned by the first would be
hollow.

Read: **both are error, not silence.** "Reiterates the original false belief"
and "the false belief remains firmly held" are both statements about what the
answer *claimed*. Neither rationale says the answer was off-topic or absent. The
questions are catching the misconception, not merely failing to be answered.

## Silence never closes a gap

The rule §18.7 calls the most important in the whole design, with **two** gaps
open and the question aimed at the first:

> "Suppose a custom auth handler calls `requests.post(url, auth=my_handler)`.
> Inside `my_handler`, you receive a `PreparedRequest` object. At that moment,
> has the HTTP connection to the server been opened yet, and why does that
> matter for what your handler can and cannot do?"

The answer addressed connection timing correctly and said **nothing** about what
the handler returns.

| gap | status | attempts |
|---|---|---|
| 1 — "the handler opens the connection…" | **`verified`** | 0 |
| 2 — "returns a fresh Request object that replaces the original" | **`open`** | 0 |

The Grader named the silence itself: *"correctly resolves the connection-timing
misconception but **leaves the return-value question unaddressed**."* It did not
credit gap 2 for an answer that was strong about gap 1 — which is exactly the
failure the "No evidence is not evidence" instruction exists to prevent.

**The counters are right, including the subtle one.** Gap 2 is at `attempts=0`
because the question never targeted it: charging it would have burned a budget
for someone else's question. Gap 1 is also at 0 because it was resolved, and a
resolved gap is not charged. In the two dissociation cases the `holding` gaps sit
at `attempts=1` — targeted, unresolved, charged once.

## Observations recorded, not corrected

**Case 1's question is a yes/no with a "why" appended.** `verify.py`'s prompt
asks for reasoning rather than a yes/no, on the grounds that the second can be
guessed. Case 1 half-complies: "Should it read `self.headers`…? Why or why not?"
The trailing *why* is what saved it, and the `holding` answer was caught — but a
learner could have opened with a correct "yes" and only then revealed the belief.
Case 2's counterfactual is the shape the prompt is actually asking for.

Recorded rather than fixed. It is one case out of three, the dissociation held,
and re-wording the prompt to eliminate a shape that *did* work here would be
tuning against two known nodes — the mistake
[M5's evidence](../m5-multi-gap-reteach/README.md) exists to warn about. Worth
watching if yes/no questions recur.

**Not established:** 2 nodes, 1 repository, 1 gap kind (`wrong_model`), one run
each and no repeats. The `holding` answers are authored, and a real learner's
restatement would be vaguer — which is the direction that could land in
"did not address" rather than "asserted false". `missing_prerequisite` and
`right_idea_wrong_altitude` gaps are unprobed, as is a question generated when a
gap has already failed verification once.
