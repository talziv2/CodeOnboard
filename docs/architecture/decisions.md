# Architectural decisions and invariants

> The non-obvious rules a future change could break without anything failing
> loudly. Each one is stated with the failure it prevents, because that is the
> part that makes it checkable.
>
> Parent: [overview.md](overview.md) · Index: [docs/README.md](../README.md)

This is not an exhaustive ADR log. Trivial decisions are omitted; what is here is
the set where the wrong change compiles, passes an eyeball review, and quietly
makes the product lie.

---

## D1 — Repository understanding is separated from teaching

**Rule.** Exactly one exploration loop runs per session, at plan time. Teaching,
the Mentor, the Reviewer and the Mutator read what it produced; none explores on
its own.

**Prevents.** Every agent growing its own retrieval, each with its own idea of
what the repository is, at its own cost. If the Dossier cannot support a good
curriculum, the fix belongs in the investigation's exit criteria — not in a second
loop one layer up.

**Where.** `backend/repo/investigation.py`, reached only from the
`goal_investigation` node.

---

## D2 — Grounding is against the repository, not against the evidence shown

**Rule.** A model names a `file` and a `symbol`; **our code derives the line
range**, through `anchors.resolve` against the deterministic Skeleton.

**Prevents.** Hallucinated line ranges — structurally, not probabilistically. It
also separates two questions three earlier implementations had conflated: *does
this exist?* and *was this shown to the agent?*

**Do not** reintroduce a validator that checks a citation against a retrieval
slice and calls it grounding.

---

## D3 — No source, no lesson

**Rule.** Grounding is verified at plan time but source is **read at lesson
time**, and the two can disagree. If *some* of a unit's anchors fail to load,
Teaching degrades and teaches from the rest. If **all** of them fail, Teaching
**fails the lesson** — it must never render one.

**Prevents.** The worst failure the system can produce. With no source the model
has only the objective, and it will write a fluent, confident, entirely ungrounded
lesson from it. Nothing in the output looks wrong, which is exactly why this is
refused at the point of reading rather than caught afterwards.

---

## D4 — `objective` is the contract between three agents

**Rule.** The Planner writes the objective, Teaching is instructed to build
exactly it, and the Grader marks against **it** rather than against the
`expected_answer` Teaching invented. Read it through `LearningNode.objective()`,
never straight off `lesson_brief`.

**Prevents.** Each agent aiming at its own target, so that the system verifies the
learner has reproduced the teacher rather than reached what the planner intended.

`expected_answer` is a **calibration reference**, not the marking standard.

`objective()`'s fallback to the older `understand` key is what keeps graphs
planned before the contract working, and Teaching and the Grader **must share it** —
if they disagreed about the target on old graphs, the drift the contract exists to
end would simply move there.

---

## D5 — The planner over-generates and code cuts

**Rule.** The model is given **no target number** and told to enumerate
everything worth learning. `curriculum.select()` then cuts by required-set
closure, dependency closure, area coverage and a guard band. Every sizing rule is
a pure function.

**Prevents.** Curriculum size being a sentence in a prompt keyed on a field nobody
asked the user for, with no code anywhere checking it. Asking a model to enumerate
is asking it to do something it is good at; asking it to self-limit is not.

**Overflow is demoted to `optional` on the same spine, never discarded.**

---

## D6 — `optional` means excluded from the walk, not removed

**Rule.** `/advance` steps over an optional unit, `resume_point()` skips it, the
stop counter and readiness exclude it, and the rail collapses it — but it stays in
the graph, in `path_order()`, and teaches and grades normally when reached from
the rail.

A unit with **no** `priority` at all is **not** optional and stays on the walk —
which is what makes both progress measures defined on every pre-B3 graph.

**Prevents.** "Make it shorter" and prune-ahead only relabelling a journey rather
than shortening it, and a sixteen-unit graph that says "stop 3 of 15" while still
walking the learner through all sixteen.

---

## D7 — Two progress measures, and neither is `completed / total`

**Rule.** Goal readiness is evidence-weighted mastery of the **required set**.
Journey progress is how much of the promised walk has been dealt with. Evidence
coverage is reported beside them and never folded in. Remedial warm-ups are
excluded from all three.

**The invariant:**

> Goal readiness may fall **only** when evidence about the learner changes. It
> must **never** fall because the system changed the plan.

**Prevents.** What actually happened: inserting a remedial prerequisite dropped
the gauge from 0.50 to 0.33, so the system's decision to help looked like the
learner losing ground.

`tests/test_progress.py` pins every mutation against this rule.

---

## D8 — A learner decision is never evidence of understanding

**Rule.** `understanding_state` is the **evidence** channel; `user_override` is
the **disposition** channel. `Move on anyway` and `mark_understood` write only
disposition. Settlement for an assertion comes from `SETTLING_OVERRIDES`, not from
a state write.

`mark_weak` is the deliberate asymmetry: agreeing with a shortfall can only lower
the claim being made about the learner, so it still writes state.

**Prevents.** Measured, on a node whose only answer was graded `confused`:
pressing *mark understood* turned it into a **strength** — not even `recovered` —
and moved goal readiness from 0% to 100%. That was the one door through which a
decision entered the product's centrepiece measure as evidence.

**Also.** The condition for recording "I moved on" is *an unmet objective plus at
least one assessment*. Presence is not a decision, so a refresh or a scroll-past
records nothing.

---

## D9 — A node cannot be `understood` while a blocking gap is unverified

**Rule.** `graph.understanding_of()` is the **single owner** of this question, and
`verified` is the only gap status that permits `understood` — not merely "not
open". A `waived` gap is a decision rather than evidence, so it keeps the node off
`understood` exactly as an open one does.

**Prevents.** An answer graded `understood` while two detected misconceptions sat
open on the same node, with the graph reporting mastery.

An AST test enforces that nothing re-derives this outside that function.

---

## D10 — Only a fresh verification answer produces `verified`

**Rule.** `Gap.mark_verified` is called from exactly one place. Re-answering the
lesson's own question can match or open gaps, never close one.

**Prevents.** A memory check passing as understanding: the reveal has already
given the reasoning away by then.

**And the general form of it:** *a retry question never ships its own answer.* The
unit's own prompt is answerable exactly **once**, before its reveal has ever been
shown. Every later assessment comes from `/verify` or `/reassess`. A re-teach does
not escape this — it regenerates the whole lesson, so its better new prompt
arrives with a new `reveal` that answers it.

---

## D11 — Silence never closes a gap

**Rule.** The verification grader returns a verdict **per gap**, keyed by an id we
supplied. Anything it does not vouch for stays open **by default**, not by
inference.

**Prevents.** An answer that is correct about A and says nothing about B closing
both. It is also why a verification question is aimed at **one** gap: a blanket
question invites exactly the partial answer that would otherwise look like
completion.

---

## D12 — Caps bound the system, not the learner

**Rule.** Reaching `VERIFICATION_ATTEMPT_CAP`, `REMEDIATION_ROUND_CAP` or
`REASSESSMENT_CAP` writes **nothing** to a gap. It removes the gap from the
*active set* — the system stops offering — and the gap stays `open` and stays
blocking. A learner who names it themselves still gets a question.

**Prevents.** The system marking its own homework because it ran out of ideas.
Asking is a different act from being nagged.

---

## D13 — Gap identity is ours

**Rule.** `Gap.create` mints the id; a model is only ever shown ids and asked to
reference them. Nothing accepts a model-supplied id, and text-similarity merging is
refused.

**Prevents.** One misconception becoming two gaps across a re-grade — or two
becoming one — which would make every count downstream unfalsifiable.

`Gap.from_dict` is deliberately **permissive** where `create` is strict:
validation belongs at the point a gap is opened, and at load time the only correct
behaviour is to return what is stored.

---

## D14 — Grading and the response policy are separate

**Rule.** The Grader says *how far* an answer fell short and *why*
(`classification` + `gap_kind` + named claims). `adaptation.decide_all` — a pure
table — says what happens about it. What the response *says* is generated.

**A named `gap_kind` outranks the coarse classification.** Found in live
validation: a learner wrote "I can't follow this because I don't know what a
function signature is", the Grader read it exactly right and reported
`missing_prerequisite`, and the policy threw the signal away because the same
answer was also classified `off-topic`.

What the off-topic guard actually protects is the **unclassified** case: an answer
that addresses nothing and names no gap earns nothing and must not reshape a path.

---

## D15 — One structural mutation per graded answer

**Rule.** A `prerequisite` targets exactly one gap. A `reteach` or `followup`
targets *every* active gap of its own kind — a lesson can name several
misconceptions and must, or the ones it omits are silently abandoned. Gaps of
different kinds are never merged.

**Prevents.** A fan-out of warm-ups. And when more than three blocking gaps are
open, that is itself one signal — the unit did not land — so the response collapses
to a single full re-teach.

---

## D16 — `save_graph` never writes a plan table

**Rule.** The only writers of `plan_nodes` / `plan_edges` are `create_session`
(once, in the same transaction as the session) and `record_plan_lesson` (which is
physically unable to overwrite).

**Prevents.** `Start over` restoring a plan that has been quietly contaminated by
the walk. And the consequence is what makes the module short: **anything not in
the plan is gone by construction**, so a state field added to `LearningNode`
tomorrow is handled today, without a line changing. There is no list of fields to
clear — a list is exactly what rots.

The plan tables' **column list is the plan/state partition**, readable in
`.schema` rather than living in a test file.

---

## D17 — Nothing is ever synthesised for a session that has no plan

**Rule.** A version-2 session loads and resumes with its state exactly as it is,
and `Start over` is simply unavailable. `POST /reset` answers **409**, not 404, and
attempts no reconstruction.

**Prevents.** A plan invented from a half-walked graph — which is not the plan, it
is wherever the learner had got to, relabelled. Absent is honest; fabricated is
not.

---

## D18 — `SCHEMA_VERSION` and `SUPPORTED_SCHEMA_VERSIONS` are two questions

**Rule.** A session is **written** at `SCHEMA_VERSION` and **read** back if its
stored version is in `SUPPORTED_SCHEMA_VERSIONS`. `load_graph` treats a mismatch as
*missing*, never as a thing to migrate.

**Prevents.** What happened at the bump to 3: strict equality made all 90 sessions
in the development database invisible — the opposite of a migration. Anything that
can be added as an **additive nullable column** should be, so the version does not
have to move at all.

**Note for whoever moves it to 4:** `load_plan` keeps a strict `==` check, so a
version-3 session with a real plan will silently stop being resettable. That check
must be revisited.

---

## D19 — The flag gates behaviour, never storage

**Rule.** Nothing in `backend/learning/store.py` reads `CODEONBOARD_GAPS`. Gap
data written under the flag survives a flag-off load, a flag-off re-save, and is
restored exactly when the flag comes back on.

**Prevents.** Silent data loss on a setting change. A test asserts this
structurally, so the contract cannot rot.

---

## D20 — Ownership is decided at the persistence boundary

**Rule.** `store.load_graph(session_id, user_id, …)` takes the owner as a
**required** parameter. Four layers back it up, because forgetting is the failure
mode.

**And: 404, never 403.** A foreign session and a nonexistent one answer
identically, byte for byte.

**And: creation always creates.** `_try_resume` matched on `(repo_url, goal)`
across the whole database and handed back somebody else's session.

**And: the learning engine knows nothing about users.** `learning/`, `agents/` and
`repo/` contain no reference to one; `store.py` is the single exception, because it
*is* the boundary. The planner mints its own session id and `_generate_session`
reconciles it, rather than teaching the planner about the account layer.

---

## D21 — Nothing about a learner is inferred from an email

**Rule.** The auth key is `auth_identities.(provider, subject)`. `users.email` is
contact and display only, and — with no verification shipping — an **unverified
claim**. Google linking requires the account's password as well as Google's word.

**Prevents.** The account takeover that the obvious rule allows: register a
password account as someone else's address (nothing verifies it), wait for them to
click "Continue with Google", inherit their account.

---

## D22 — The frontend renders learning decisions; it does not compute them

**Rule.** The retry offer, the reason there is none, whether the objective is met,
and every progress number arrive from the server.

**Prevents.** What happened when four flags were derived in the panel from four
different slices of the grading reply: the system wrote a scaffold whose prompt
forbids it from containing the answer, then removed the only button that could use
it; an exhausted gap was offered and the refusal arrived as an error; and one flag
was derived two different ways and was wrong on one of them. Every defect was a
seam between them.

**The one stated exception** is `lib/materialSeen.ts` — *"have I looked at Lesson
since it changed"* — which is not a fact about understanding and is not observable
server-side. **Reading is guidance and never evidence:** it cannot close a gap,
move a state, or count toward readiness.

---

## D23 — Learner-written text is never markdown

**Rule.** Model-authored prose goes through `Prose` / `InlineProse`; attempt
answers and check answers stay `whitespace-pre-wrap` exactly as typed.

**Prevents.** Interpreting a learner's asterisk as emphasis, which rewrites what
they said — and the one place their own words appear is the one place fidelity
beats polish.

Two subset rules in `lib/markdown.ts` are load-bearing: **`_` is never emphasis**
(`line_start` and `__init__` are the vocabulary), and **an unclosed delimiter stays
literal** (prose that half-parses is worse than prose that does not). The parser
returns nodes, never HTML, so `dangerouslySetInnerHTML` never enters the picture.

---

## D24 — Fixed keys are parsed; only labels are chosen

**Rule.** JSON keys, `goal_type`, `depth`, `familiarity`, concept tags, edge
kinds, gap kinds and Grader classifications are **fixed vocabulary**. The frontend
switches on those values. Only the displayed label is chosen, via `tagLabel` /
`stateLabel`, and all copy lives in `frontend/lib/strings.ts`.

**Prevents.** A copy edit silently changing a code path.

---

## D25 — Exhaustion is a result, not an exception

**Rule.** Running out of exploration budget yields a partial result with
`budget_exhausted=True` and an honest `stop_reason`. So does an API failure, and so
does a tool crash. `accepted: false` propagates into downstream confidence, and
remaining uncertainty is recorded in `open_questions`.

**Prevents.** A run that dies producing either nothing or a confident-looking
whole. Budgets are safety rails against runaways, not rationing: stopping is about
understanding, not spend.

---

## D26 — Cost is a metric, not a design constraint

**Rule.** Every run reports its own cost (`explore.PRICING`, `repo/metrics.py`),
and no design decision is made to reduce a number that is not yet measured.

**Known gap.** `CLAUDE.md` states a target of under $0.10 per run. Measurement puts
a real session materially above that, and the discrepancy is tracked openly in
[`docs/planning/phases/cost-optimization.md`](../planning/phases/cost-optimization.md)
rather than being quietly restated.

---

## Related planning documents

The phase documents in [`docs/planning/phases/`](../planning/) carry the full
argument behind most of these, including the alternatives that were rejected. They
are **design records**, not descriptions of current behaviour — where one disagrees
with the code, the code is right.
