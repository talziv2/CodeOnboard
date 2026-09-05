# Contribution handoff — should CodeOnboard own the second half?

> **Status: design proposal. Nothing here is built.** It questions work that
> exists on `feat/contribution-journey` and recorded in
> [`contribution-journey.md`](contribution-journey.md). Read that first; this
> document argues with it.
>
> The question: CodeOnboard currently owns
> `learning → ready → Plan → Locate → Implement → Validate → Review → PR-ready`.
> Should it stop at readiness and hand off to a coding agent instead?

---

## 1. Where the responsibility boundary became questionable

### 1.1 What the system actually claims to be

The stated X-factor, recorded before the contribution journey existed:

> CodeOnboard does **not** compete with AI that writes code — it complements it
> by developing the human capability to **understand, critique, and direct**
> AI-generated code inside a real codebase. […] The learning graph reframes as a
> **trust map** — where the user can confidently point AI at the codebase, and
> where they still need to learn before trusting AI output.

"Where the user can confidently point AI at the codebase" **is a handoff.** The
thesis already contains it. The in-app implementation flow is not an expression
of that thesis; it is a substitute for it.

Two more from the repository's own planning corpus, both predating the
contribution journey and both stronger than the memory note:

> Users reach **contribution-ready understanding** faster with CodeOnBoard.
> — `docs/planning/vision/evaluation.md`, Expected Outcome, whose named baseline
> is *"AI-assisted development using tools such as GitHub Copilot or Cursor"*

> CodeOnboard complements AI code generation rather than competing with it …
> training the human ability to understand, critique, and direct AI-generated
> changes. […] reframes the learning graph as a **trust map** — where the user
> can confidently direct AI at the codebase.
> — `docs/planning/phases/roadmap.md:127`, `:178`

The stated evaluation outcome is **readiness**. Not a shipped patch. And the
named baseline is the class of tool this document proposes handing off to.

### 1.2 What was actually ruled out, and whether we drifted

*Correction to a claim it would be easy to make here:* the four crisp non-goals
often repeated about this feature — "not a generic repository coding agent", "not
autonomous feature implementation", "not a Cursor-like editor", "not automatic PR
creation" — **are not in the document**. They are how the feature was *briefed*.
What the record actually contains is:

- **§9, "Keeping the coding stage from becoming a coding agent"** — five limits:
  the system never writes code the learner did not write · nothing is written to
  disk, ever · the stage is unreachable before the learning is done · the change
  boundary comes from the investigation, not the coder · the Tutor stays inside
  its boundary.
- **§12 "Explicitly deferred"** and **A3 "Rejected for v1"** (import-graph
  checking, style checks, diff application, coverage).

**All five §9 limits hold, and are enforced by tests** — including prompt-level
assertions (`"Do NOT write the code"`) and a copy-level ban on the words
*correct / valid / verified / tests pass* in `frontend/lib/strings.ts`. Nothing
deferred was quietly built. **There has been no drift toward a coding agent.**

The drift that did happen runs the other way: the deterministic claim got
*weaker* than approved. B1.1 and B1.2 loosened the scope check twice, and B4.3
had to add a *"Protected-symbol check — Not performed"* row because silence read
as a pass.

So the case against the current design is not misconduct. It is that the built
flow respects every limit *literally* and still lands next to the thing it was
told not to be:

| Stage | What it is | Distance from the non-goal |
|---|---|---|
| Implement | a textarea per file, no diff, no working copy | a Cursor-like editor, minus the editor |
| Review | one Haiku call over pasted text | a code review, without the code |
| PR-ready | generated title/body/testing notes | a PR, minus the ability to open one |

None of them crosses the line. All of them are the *weaker half* of something
another tool does properly.

### 1.3 The tell: the deferred table

The same document's **"Explicitly deferred"** list is the strongest evidence
against the current boundary, because it was written honestly and before this
question was asked:

| Deferred | Stated reason |
|---|---|
| **Executing tests** | "Needs a sandbox that does not exist." |
| **Real PR creation** | "No GitHub write infrastructure, and the configured GitHub MCP server does not currently connect." |
| **A diff editor / applying patches to a working copy** | "Would require per-session checkouts — a real change to the storage model." |

Three capabilities, all deferred as structurally infeasible *for CodeOnboard*.
All three are ordinary, already-solved capabilities of a coding agent running on
the developer's own machine.

That is not a gap to close later. It is the boundary telling us where it is.

### 1.4 The structural reason, stated once

`data/repos/<owner>/<name>` is **one shared checkout per repository**, across
every user and every session, pinned by `clone_repo` which never updates an
existing clone (`repo/cloner.py:171`). It is the grounding oracle's substrate:
`anchors.resolve` resolves `file+symbol → line range` against it, and D2/D3 make
every lesson depend on that.

A writable per-learner working tree is therefore not a feature CodeOnboard is
missing. It is a thing CodeOnboard **must not have** in the place it keeps the
repository, and adding a second, per-session, writable checkout is a change to
the storage model with no learning benefit.

**So: CodeOnboard cannot execute, cannot edit, and cannot open a PR — not for
want of effort, but because of a decision that is right for the reasons it was
made.** Everything downstream of "write the change" is being simulated.

---

## 2. Recommended product boundary

### 2.1 The test to apply

Not "what did we build", and not "what could we build". Two questions, in order:

1. **Does this require a persistent model of what *this learner* understands
   about *this repository*?** If yes, only CodeOnboard can do it. Nothing else
   in the ecosystem has that object.
2. **Does this require a writable working tree, execution, or repository write
   access?** If yes, CodeOnboard structurally cannot do it (§1.4).

Anything that is *neither* is genuinely negotiable, and should go wherever it is
done better.

### 2.2 The verdict, responsibility by responsibility

| Responsibility | Owner | Why |
|---|---|---|
| Repository investigation | **CodeOnboard** | D1: one exploration loop. It is goal-aware, and the learning plan is cut from its output. An agent's ad-hoc reading is not a durable artefact. |
| Identifying the change boundary | **CodeOnboard** | It is a *product of* the investigation and the reason two goals on one repository produce different journeys. This is the demo's central claim. |
| Identifying relevant existing tests | **CodeOnboard** | Same provenance; cited as anchors, resolvable against the pinned commit. |
| Discovering edge cases / contracts | **CodeOnboard** | The single most defensible output the system has (see §5.4). |
| Required-knowledge selection | **CodeOnboard** | Nobody else does this at all. |
| Learning | **CodeOnboard** | — |
| Grading | **CodeOnboard** | — |
| Misconception / gap tracking | **CodeOnboard** | — |
| Readiness | **CodeOnboard** | Derived, D7-governed. The gate is the product. |
| Implementation planning | **Shared — CodeOnboard first, agent after** | A plan written *before* opening the editor is a pedagogical commitment device. A plan that adapts as code changes needs to see the code. Both are real; they are different artefacts. |
| Locating code | **Split** | CodeOnboard *names* the location (boundary, anchors). The agent *navigates* to it. Naming is knowledge; navigating is tooling. |
| Editing code | **Learner**, assisted by the agent | Requires a working tree. |
| Running tests | **Agent** | Requires execution. |
| Validating the change | **Split, and the split is principled** | *Did the change stay inside the boundary?* is CodeOnboard's claim, because CodeOnboard owns the boundary. *Does it work?* is the agent's, because only it can run anything. |
| Code review | **Agent** | Requires the real diff in the real repository. A Haiku call over pasted text is strictly worse. |
| Preparing / opening a PR | **Agent** | Requires `git` and `gh`. |

**The line falls between "naming what is true and what is known" and "changing
the repository".** CodeOnboard owns the first entirely. It owns exactly one
thing on the far side — the boundary-conformance claim — and it owns that
because it owns the boundary, not because it owns the diff.

---

## 3. A / B / C compared

### A — everything stays inside CodeOnboard *(today)*

**Advantages.** One system, no external dependency, fully controlled demo. It
exists and is tested. Nothing new to build before submission.

**Disadvantages.** Validate cannot run tests; Review is weaker than any coding
agent; PR-ready cannot open a PR; Implement is a textarea. Every one of these is
a *simulation* of something the audience knows is done better elsewhere, and the
project's own documentation already says why they cannot be improved.

**Complexity.** Zero additional. **Risk.** The examiner asks "why is a learning
system writing PR descriptions?" and there is no good answer. **Demo value.**
The first eight minutes are strong; the last four invite the comparison the
project's thesis exists to avoid.

### B — CodeOnboard stops at readiness; full handoff

**Advantages.** The boundary is exactly the thesis. The three deferred
capabilities become real: tests actually execute, a PR can actually be opened.
CodeOnboard's outputs get *used* by something that could not have produced them.

**Disadvantages.** The learner leaves the product. Nothing after readiness is
observable to CodeOnboard unless a return channel is built. The final screen
becomes a handoff, which is less of a finale than "PR-ready".

**Complexity.** Moderate: one artifact endpoint, one generated instruction file,
one launch path. **Risk.** "Your project is a wrapper." **Demo value.** High,
if the artifact is shown before the agent — see §11.

### C — hybrid: CodeOnboard keeps Plan and Locate, hands off editing onward

**Advantages.** Everything in B, plus the two pre-implementation surfaces that
are genuinely learning surfaces rather than tooling: *Locate* is the last lesson
("here is where it goes, and here is what you must not break"), and *Plan* makes
the learner commit to an approach before an agent can suggest one. Both are
things a coding agent will not do for you, because a coding agent's incentive is
to start.

**Disadvantages.** Two systems own "planning", which needs care to avoid
becoming two authorities for one fact (DI-1). Slightly more surface to explain.

**Complexity.** Same as B — the two retained stages already exist and stop being
a flow, becoming the last two screens before the handoff. **Risk.** Lower than
B: CodeOnboard stays useful and complete even if no agent is ever opened. **Demo
value.** Highest — the handoff is a *conclusion* of a journey rather than an
exit from it.

---

## 4. Recommendation — **C**, with a specific shape

**Adopt C.** CodeOnboard owns everything through *Locate*, produces a grounded,
machine-readable **handoff artifact**, and hands editing, testing, review and PR
to the coding agent.

Three reasons, in order of weight:

1. **It is the only option where nothing is simulated.** Every claim CodeOnboard
   makes is one it can actually support; every capability it lacks is provided by
   something that genuinely has it.
2. **It restores the stated thesis.** "Where you can confidently point AI at the
   codebase" stops being a slogan and becomes a file.
3. **It is cheap.** The artifact is pure assembly of data that already exists
   (§10). No new model call, no new storage model, nothing to measure.

**What I am *not* recommending:** deleting the existing flow now. Keep it until
the handoff is demonstrably better on your own machine, then remove the three
stages §9 marks REMOVE. It is a working fallback and a fallback has value the
week before a submission.

### 4.1 The condition that makes this legal — DI-6

There is one principle a naive handoff genuinely violates, and it changes the
design rather than merely qualifying it:

> **DI-6 ①** — A model's output is a **proposal**. Something owned by our code
> stands between it and authoritative state.

Today this holds by construction: the plan is prose, the review is a labelled
opinion, and the only thing that becomes state is learner-typed text that has
passed through `check_scope`. Under a **pure** handoff, the coding agent's edit
becomes the artifact with **nothing of ours in between** — and DI-6 is a ①, so
violating it requires an argument about what the product is, not a trade-off.

**Therefore the return channel is not optional.** It is the thing that keeps the
architecture compliant with the project's own first-class principles. Concretely:

1. **We export a boundary; we never import a verdict.** The changed-file list
   comes back and *our* `check_scope` produces the scope claim. If we accepted the
   agent's word for "this stayed in scope", **DI-1** would be violated too — two
   authorities for one fact.
2. **What comes back is evidence about a patch, never about a learner** (§8).
3. If the return channel is not built, the honest position is not "handoff
   without it" — it is **option A**. A handoff with no boundary check downstream
   gives up the one deterministic claim this project can make.

This raises §10's step 5 from *optional* to *required for the architecture to be
worth adopting*, and it is the single most important correction to the first
draft of this proposal.

### 4.2 One argument I am deliberately not making

**D26** — *"Cost is a metric, not a design constraint."* The handoff would remove
three cheap Haiku calls (Plan 8.8 s, Review 3.3–4.9 s, PR 5.9 s) and keep the
expensive half ($0.20–0.27 per investigation run). Cost is not a reason to do
this, and if it comes up in the defence, say so.

---

## 5. Is MCP the right mechanism? — **No, not for the handoff**

### 5.1 The disqualifying fact

**An MCP server cannot contribute instructions.** It exposes tools whose
*results* the model reads; there is no supported way for a server to say "behave
this way in this session". (Verified against current Claude Code documentation;
resources and prompts are protocol-supported but thinly surfaced — tools are the
primitive that actually works.)

The single most important thing about this handoff is not data. It is the rule
*"the learner is the implementer; scaffold, do not take over"* (§7). That is an
instruction. MCP structurally cannot carry it. `CLAUDE.md` and skills can, and
that is what they are for.

An architecture whose most important element cannot travel over the chosen
transport is the wrong architecture.

### 5.2 The shape of the payload argues the same way

The handoff is **computed once, pinned to one commit and one readiness snapshot,
and immutable thereafter**. A tool call is the right shape for data that is
dynamic, parameterised, or too large to inline. This is a constant. Fetching a
constant through a tool call costs a round trip, a tool definition in every
session's context, and a failure mode, and buys nothing.

### 5.3 What MCP would actually cost here

- A server to write, run and keep running (there is no MCP dependency in this
  repository today — no `.mcp.json`, nothing in `pyproject.toml`).
- `.mcp.json` in the learner's repo plus a trust dialog. **There is no one-click
  install.** No deep link installs a server.
- Authentication, and it is not optional: sessions are owned (D20, 404-never-403)
  and D21 says nothing about a learner is inferred from an email. A remote MCP
  server exposing session data needs OAuth or a scoped token — real work.
- Tool definitions consuming context in every session, whether used or not.
- One more thing that can fail on stage. *This repository has already been bitten
  once:* "the configured GitHub MCP server does not currently connect"
  (`contribution-journey.md:492`).

### 5.4 The honest answer to "is MCP solving a real problem, or making the demo look sophisticated?"

**For the handoff: it is decoration.** A JSON file in the repository is simpler,
more reliable, agent-agnostic, requires no server, no auth, and no setup, and it
is *visible* — you can put it on a slide. MCP would be chosen here for how it
sounds in a report, and an examiner who knows MCP will ask what it bought.

**There is one narrow real case**, and it is worth stating so the rejection is
fair: if you wanted the agent to *query* CodeOnboard **mid-session** — "the
learner is about to touch `sessions.py`, is that inside the boundary?", "has this
learner demonstrated the cookie-jar contract?" — that is dynamic, parameterised,
repeated access to a live system. That is genuinely MCP-shaped, and a file cannot
do it. But nobody has asked for that feature, it is not needed for the story, and
it is strictly more work.

### 5.5 If you build MCP anyway: which direction?

**CodeOnboard as MCP *server*, never client.** CodeOnboard holds state somebody
else wants to read; that is a server. Making it a client would mean CodeOnboard
driving a coding agent — which is autonomous feature implementation, an explicit
non-goal, and would put a model's editing success upstream of a learning system.

Minimal server surface, if it happens:

| Tool | Returns |
|---|---|
| `get_contribution_context(session_id)` | `repository_knowledge` (§6) |
| `get_learner_readiness(session_id)` | `learner_state` (§6) |
| `check_scope(session_id, changed_files)` | the ScopeCheck verdict — **the one genuinely dynamic call**, and the only one a file cannot replace |
| `report_outcome(session_id, …)` | development metadata (§8) |

Note that only the third earns its keep. Which is the argument in miniature.

### 5.6 What to use instead

| Need | Mechanism | Reliability |
|---|---|---|
| Carry the data | `.codeonboard/handoff.json` written into the learner's clone | total — it is a file |
| Carry the behaviour | `.claude/skills/codeonboard-contribution/SKILL.md` (+ a short `CLAUDE.md` pointer) | high — loads automatically once the directory is trusted |
| Start the session | deep link `claude-cli://open?cwd=<path>&q=/codeonboard-contribution` | good; prompt is pre-filled, learner presses Enter. **Capped ~5000 chars**, so the data must be in the file, not the link |
| Report back | HTTP hook on `Stop` / `SessionEnd` → `POST /session/{id}/contribution/outcome` | **deterministic** — fires regardless of what the model decides |

The last row matters: **asking the model to call a "report outcome" tool is not
reliable.** A hook is not a request to the model; it is a lifecycle event.

---

## 6. Proposed handoff schema

Two top-level namespaces, and the separation is load-bearing: **no consumer may
read "the learner demonstrated X" as "the code does X", or the reverse.** That is
the same discipline as D8 (a learner decision is never evidence) applied at an
export boundary.

```jsonc
{
  "schema": "codeonboard/contribution-handoff@1",
  "generated_at": "2026-09-05T10:00:00Z",
  "session": { "id": "…", "url": "http://localhost:3000/session/…" },

  // ── the change is only meaningful at ONE revision ──────────────────────────
  "repository": {
    "url": "https://github.com/psf/requests",
    "commit": "e8d2c015…",
    "verify": "git rev-parse HEAD    # must match `commit`"
  },

  "task": {
    "statement": "Add get_all(name, …) to RequestsCookieJar and cover its edge cases.",
    "goal_type": "contribute_code"
  },

  // ══ FACTS ABOUT THE CODE. No learner appears in this object. ═══════════════
  "repository_knowledge": {
    "change_boundary": {
      "target":          [{ "file": "…", "symbol": "…", "why_here": "…" }],
      "must_not_change": [{ "file": "…", "symbol": "…", "why_not": "…" }],
      "existing_tests":  [{ "file": "…", "symbol": "…", "what_it_guards": "…" }],
      "edge_cases":      [{ "case": "…", "why_it_bites": "…", "file": "…", "symbol": "…" }],
      "conventions":     [{ "convention": "…", "evidence_file": "…" }]
    },
    "contracts": [{ "file": "…", "symbol": "…", "contract": "…" }],
    "flows":     [{ "name": "…", "steps": [{ "file": "…", "symbol": "…", "what_happens": "…" }] }],
    "recommended_validation": "pytest tests/test_requests.py -q",
    "provenance": {
      "produced_by": "goal_investigation",
      "accepted": true,
      "grounding_accuracy": 0.93,
      "note": "Derived by reading the repository at `commit`. Anchors are file+symbol; resolve them yourself."
    }
  },

  // ══ FACTS ABOUT THE PERSON. No claim about the code appears here. ══════════
  "learner_state": {
    "readiness": { "ready": true, "required": 11, "demonstrated": 11 },
    "demonstrated": [{ "objective": "…", "understanding": "strength|recovered" }],
    "unresolved":   [{ "objective": "…", "gap_kind": "…", "claim": "…", "blocking": false }],
    "not_taught":   [{ "name": "adapters", "reason": "…" }],
    "means": "Demonstrated = they answered a question against this objective and the Grader classified it `strength` or `recovered`. It is a record of one exchange, not a certification, and it says nothing about their ability to write this code."
  },

  // ══ HOW THE AGENT SHOULD BEHAVE. Data here; ENFORCED in the skill (§5.1). ══
  "handoff_policy": {
    "implementer": "learner",
    "assistant_default": "scaffold",
    "may_take_over": "only when explicitly asked, and say so when you do"
  }
}
```

### Design notes, each with the failure it prevents

- **`commit` is mandatory and must be verified first.** Every `file:symbol` in
  this document is true *at one revision*. Handed to an agent standing on a
  different checkout, the whole artifact is confidently wrong. The agent's first
  instruction is to compare and refuse on mismatch — DI-8, refuse rather than
  fabricate.
- **File + symbol, never line numbers.** `anchors.resolve` is the oracle
  precisely because a model never names a range (D2). Line numbers are the fastest
  thing in this system to go stale; a symbol survives edits. Shipping ranges would
  export a lie with a short shelf life.
- **`means` is a sentence, not decoration.** Without it, `demonstrated: 11` will
  be read by the next system as competence. It is a record of eleven exchanges.
- **`not_taught` is included deliberately.** What the journey *skipped* is as
  much a part of the trust map as what it covered, and it tells the agent where
  the learner has no grounding at all.
- **`unresolved` carries `blocking: false` only.** A blocking gap means the gate
  is shut and there is no handoff to make.
- **No lesson text, no attempts, no transcripts.** The agent needs the shape of
  what is known, not the learner's answers. Exporting attempts would be a privacy
  decision nobody has taken.

---

## 7. Post-handoff interaction — how the learning survives

This is the section that decides whether the whole idea is good or corrosive.
A handoff that ends *"…now implement this"* destroys the journey that preceded
it. The instruction file must therefore do real work.

### 7.1 The rules, as they would be written into the skill

1. **The learner is the implementer.** Default mode is *scaffold*: locate,
   explain, ask, review. Do not write the change unasked.
2. **Taking over is allowed and must be declared.** If asked directly, do it —
   and say plainly that you did, so the learner's own record of what they wrote
   stays honest.
3. **Do not hand back what they were just taught.** For anything under
   `learner_state.unresolved`, ask before telling. This mirrors a discipline the
   codebase already has: the Tutor may hint, and revealing spends the prompt
   through `retry.py` — it is not free and it is not silent.
4. **Use `edge_cases` as questions, not as a specification.** Not *"I have
   handled the `None`-valued cookie case"* but *"your patch calls `get()` — what
   happens when the cookie's value is `None`?"* This is the X-factor operating in
   the editor: critique, aimed at the learner, grounded in the investigation.
5. **Respect `must_not_change`.** Before finishing, diff against it and report.
6. **Keep the three claims apart** — *scope* (a path fact), *correctness* (an
   opinion), *tests* (executed or not). This is the honesty discipline the
   existing PR-ready output already enforces; it survives as a rule rather than as
   generated prose.

### 7.2 Why this is an improvement rather than a compromise

The original framing was *human critiques AI-generated code*. The handoff
naturally produces the inverse: **AI critiques the human, grounded in what the
human was just taught, using edge cases the human has already demonstrated they
understand.** The learner writes; the agent interrogates.

Both are defensible and they are not the same product claim. Which one you lead
with is a decision for you (§12, Q1) — but note that the inverse is *easier to
demonstrate live*, because the learner typing a change and being asked "what
about the `None` case?" is a 60-second beat with a visible payoff.

### 7.3 The failure mode to name out loud

If the learner simply says "just write it", they get an agent writing it, and the
journey bought nothing. **This is not preventable and should not be claimed as
prevented.** What CodeOnboard can honestly claim is narrower and still true: the
learner who does that now knows what the change touches, what it must not break,
and which edge cases exist — so they can *evaluate* what the agent produced. That
is the thesis, and it survives the lazy path.

---

## 8. State ownership and the return channel

### 8.1 The principle, by direct analogy

The codebase already draws this line three times:

- *"A conversation is never evidence"* — the Tutor boundary.
- *"Reading is guidance and never evidence"* — `materialSeen`.
- **D8** — a learner decision is never evidence of understanding.

By exactly the same reasoning: **a coding agent's success is never evidence of
learner understanding.** If Claude writes a passing patch, that is a fact about
Claude. If the learner writes one, it is a fact about a patch — a correct change
can be produced by pattern-matching and a wrong one by someone who understands
the code perfectly.

### 8.2 Consequently

Anything returned is **development metadata, never learner evidence.** It may be
stored, displayed and used to mark the session complete. It must never move
`understanding_state`, close a gap, or change `goal_readiness` — **D7: readiness
falls only when evidence changes, never because something else happened.**

This is a *fifth* transition kind alongside the four in
[`state-ownership.md`](../../../.claude/reference/state-ownership.md) §5 — graph,
learner-evidence, learner-disposition, UI. It belongs in none of them, which is
the clearest possible sign it needs its own name.

Proposed shape, stored on `contribution_json.outcome`:

```jsonc
{
  "files_changed": ["src/requests/cookies.py", "tests/test_requests.py"],
  "tests": { "command": "pytest … -q", "result": "passed|failed|not_run" },
  "pr_url": "https://github.com/…/pull/123",   // or null
  "reported_by": "claude-code-hook|learner",   // DI-4: provenance recorded, not inferred
  "at": "2026-09-05T11:00:00Z"
}
```

Two constraints from the existing principles:

- **DI-6** — model output crosses a boundary before it becomes state. A hook
  payload is untrusted input: validate it, cap it, and never let it name a node.
- **DI-4** — `reported_by` is recorded, not inferred. "Claude said the tests
  passed" and "the learner said the tests passed" are different facts.

### 8.3 What must come back, and what must not

Under §4.1 the return channel carries **the changed-file list** so that *our*
`check_scope` produces the scope verdict. It must never carry the verdict itself.

| Comes back | Becomes | Why |
|---|---|---|
| changed file paths | input to `check_scope` → our scope claim | DI-1: we stay the authority for a fact about our boundary |
| test command + result | development metadata | we did not run it; `reported_by` records who says so |
| PR url | development metadata | — |
| *"the change is correct"* | **nothing** | not a fact anyone in this loop can establish |
| *"the learner understands X"* | **nothing** | §8.1 |

Optionally the diff itself, if you want the `ast.parse` and symbol halves of
`check_scope` to keep working. That is a size and privacy decision, not a
principle — the path half needs only paths.

### 8.4 The one legitimate way the loop can reopen learning

If reported tests fail on an edge case the learner was taught, CodeOnboard may
**offer a question** about it. Offering is not evidence; the *answer* would be,
and it would arrive through the ordinary Grader path like every other answer.

This closes the loop without blurring anything: the return channel can *reopen*
learning, but it can never *conclude* anything about the learner.

---

## 9. What happens to each existing component

| Component | Verdict | Reasoning |
|---|---|---|
| **Change boundary** (`investigation.change_boundary`) | **KEEP — it becomes the handoff contract** | The most valuable thing built. It is already exactly the right shape: five sections, per-entry reasons, anchored `file`+`symbol`. Ships verbatim as `repository_knowledge.change_boundary`. |
| **Readiness** (`progress.ready_to_implement`) | **KEEP — unchanged** | Pure, derived, D7-governed, computed for every session. It becomes the *gate on producing a handoff at all*. |
| **`skipped_areas`** (`coverage.py`) | **KEEP — promoted** | Currently a line on the welcome page. In the artifact it is `not_taught` and carries more weight: it tells the agent where the learner has no grounding. |
| **Locate** | **KEEP — reframed as the final learning surface** | Not implementation. It renders the boundary, which is ours, and it is the last thing the learner reads before leaving. Rename its role, not its code. |
| **Plan** | **KEEP, purpose changed** | Stops being step 1 of an in-app flow; becomes an optional pre-commitment ("say how you will do it before an agent can suggest one") and an optional field in the artifact. Cheap, reliable (~9 s), and a coding agent will not make you commit first. |
| **ScopeCheck** | **KEEP, input changed** | The claim — *no files outside the planned boundary* — is CodeOnboard's because the *boundary* is CodeOnboard's. Change its input from a pasted patch to a reported changed-file list. Its path half needs only paths. Its `ast.parse` / symbol half needs contents and can either move agent-side or stay if the diff is reported. **Its docstring discipline is the most reusable thing in the feature** and should become a rule in the skill. |
| **Validate** (the surface) | **KEEP, narrowed** | Keeps the boundary-conformance row and the honest "Repository tests — not executed by CodeOnboard" row, which now reads *better*, because the tests genuinely were executed — elsewhere, and reported. |
| **Implement** (the in-app patch editor) | **REMOVE** | The weakest piece and the one the deferred table already concedes: no working copy, no diff. Under B/C it has no reason to exist. |
| **Review** (`review_patch`, Haiku over pasted text) | **REMOVE / MOVE** | A coding agent with the real repository reviews strictly better. Nothing is lost that anyone would defend. |
| **PR-ready** (`build_pr`) | **REMOVE the generator; KEEP the discipline** | We cannot open a PR; the agent can. But the *wording rules* — three claims kept apart, "these tests HAVE NOT BEEN RUN" — are a genuine contribution and survive as instructions in the skill. |
| **`contribution.py`'s `Stage` machine** | **SHRINK** | Six stages become two surfaces plus a handoff. `ContributionState` keeps `plan`, `scope_check` and gains `outcome`; `patch` and `pr` go. |
| **`agents/contribution/agent.py`** | **SHRINK to one call** | `build_plan` survives; `review_patch` and `build_pr` go. Note the header — *"NOTHING HERE EVER WRITES CODE"* — stops being a rule that needs stating, because the module that could have is gone. |

**Nothing about the investigation, the curriculum, the learning engine, the
grader or the gap model is touched.** That is the point: the boundary falls
below all of it.

---

## 10. Minimal implementation plan

Ordered so that each step is independently useful and the demo works after step 3.

**Step 1 — the artifact endpoint.** `GET /session/{id}/contribution/handoff`.
Pure assembly, no model call, deterministic, unit-testable. Every input already
exists: `_contribution_payload` (task + boundary), `progress.ready_to_implement`,
`coverage.skipped_areas`, the stored dossier via `dossier_store.load_investigation`,
`get_commit_sha(repo_dir(url))`. Gate it on `ready.ready or proceeded_unready` —
the same gate `/plan` already enforces. *Half a day, and the schema in §6 is the
whole design.*

**Step 2 — the instruction bundle.** Generate alongside the JSON:
`.claude/skills/codeonboard-contribution/SKILL.md` carrying §7.1's rules and
pointing at `.codeonboard/handoff.json`, plus a short `CLAUDE.md` stanza. Offer
both as a download (a two-file zip) from the Ready screen. *A day, mostly wording
— and the wording is the product.*

**Step 3 — the surface.** Replace Implement/Review/PR on the Ready screen with
*"Take this to your editor"*: show the artifact **on screen** (it is legible, and
it is the proof), then Download, then a copyable one-line instruction. Keep
Locate. *A day.*

**Step 4 — the launch path (optional).** A deep link
`claude-cli://open?cwd=<path>&q=/codeonboard-contribution`. Needs the learner's
local path, which CodeOnboard does not know and cannot discover — so *ask for it*
in one field, or skip this and let them open their own terminal. **Do not fake
this.** *Half a day.*

**Step 5 — the return channel. NOT optional (§4.1).**
`POST /session/{id}/contribution/outcome` + a generated `Stop` hook in
`.claude/settings.json`. It carries the changed-file list into *our* `check_scope`,
plus test command/result and PR url as development metadata. Validate hard
(DI-6), record `reported_by` (DI-4), never let it name a node. *A day.*

**Step 6 — the structural guard.** `tests/test_contribution_boundary.py` today
forbids `os, pathlib, subprocess, shutil, importlib, runpy, multiprocessing,
socket, git, tempfile` — filesystem and execution only. **Nothing stops a future
contribution module importing `run_grader` or `record_attempt`.** That is already
a hole; under a handoff, where an external tool's report enters the system, it
becomes the load-bearing rule. Copy the Tutor's structural test
(`tests/test_tutor_boundary.py:42-58`, an AST walk) and point it at the
contribution and outcome modules. *An hour, and it is the cheapest insurance in
this document.*

**Step 7 — MCP.** Only if §5.4's narrow case becomes a goal. Not before
submission.

**Total for a working, demonstrable handoff: three to four days**, no new model
calls, no new measurements, no change to the learning engine, and the existing
flow can stay in place until the last moment.

> **If you have less than that**, the answer is **A**, with §9's REMOVE list
> *deferred rather than done*. A half-built handoff is worse than either
> architecture: it deletes a tested surface (25 API tests, the structural
> boundary suite, 940 frontend tests) and replaces it with something unmeasured.

---

## 11. The strongest demo under each option

### Under A (today)

Beats 1–4 unchanged and strong: two goals on one repository, the required-set
contrast, one live graded stop, readiness. Then Plan, Locate, a pasted patch,
a 0.34 s scope check, a generated PR body. The last four minutes ask the audience
to accept a simulation of things they know are done better elsewhere.

### Under C (recommended)

Beats 1–4 **identical** — everything that is measured and defensible is upstream
of the change, and none of it moves. Then:

**Beat 5 — the artifact.** Readiness screen → *"Take this to your editor"*. Show
the JSON on screen. This is the moment the whole project resolves:

> "Everything on this screen was derived from the repository for *this* task, and
> from what this developer actually demonstrated. It's about 4 KB. This is what
> CodeOnboard produces."

Point at the two namespaces. *"Repository knowledge on the left. Learner
knowledge on the right. Deliberately never mixed."*

**Beat 6 — the handoff.** Open Claude Code in a real clone of `psf/requests`.
The skill is loaded. Ask it to help. It says where the change goes, and asks
about the `None`-valued cookie — the exact edge case from Beat 3 — *because
CodeOnboard found it and told it to ask*. The learner writes the change.

**Beat 7 — the thing A could never do.** `pytest tests/test_requests.py -q`.
Real tests. Real result.

**Beat 8 — the claim, tightened.**

> "CodeOnboard doesn't compete with coding agents. It answers a question they
> can't: *what does this developer need to understand before they should be
> allowed to point one at this code?* Then it hands over what it learned — and
> the agent is better because of it."

### Which is stronger

C, clearly — **and the reason is not that Claude Code is impressive.** It is that
under C every claim CodeOnboard makes on stage is a claim it can support, and the
one thing the audience was silently comparing you against becomes a component you
grounded rather than a competitor you imitated.

### The dependency objection, and the answer

> *"So your project is a wrapper around Claude Code."*

The artifact is plain JSON with no Claude-specific field; the skill file is one
adapter of several possible. CodeOnboard runs, teaches, grades and reaches
readiness with no agent installed — and **you should demonstrate that** by
showing the artifact before opening anything. The dependency is one direction
only: the agent is better with our file; we are complete without it.

**Mitigation for the day:** a second live tool is a second thing that can fail.
Pre-open the clone, pre-load the skill, have the finished diff on a branch you can
`git checkout` if the live edit stalls, and be ready to skip Beat 7 — Beats 5–6
carry the argument on their own.

### The demo risk I under-weighted first time round

**Checkpointing does not survive the boundary.** `tools/demo_checkpoints.py`
works because every artifact of a session is rows in SQLite — session-scoped
tables *discovered* from the schema. An external agent's work is not rows in our
database. It cannot be checkpointed, cannot be restored in one second, and needs
a terminal on stage.

Under A, every beat is recoverable in about a second. Under C, Beats 6–7 are not.
The mitigation above (a prepared branch) is a real answer but a weaker one, and
this is the strongest *practical* argument for A that exists. It should be
weighed against the fact that Beats 1–5 — which carry the entire measured claim —
remain fully checkpointed under both.

### And the risk to the artifact itself

The handoff is only as good as the `change_boundary`, and **the boundary is the
least reliable thing in the system**: generation succeeds roughly 1 in 3 (B21),
and a *usable* boundary appeared in only 1–2 of 3 runs (B19/B21). A handoff built
on an empty or unresolvable boundary is an empty file with a confident schema.

This is not an argument against the architecture — the same weakness already
degrades Locate and Validate today — but the artifact endpoint **must refuse
rather than emit a hollow document** (DI-8), and the demo must run from a
pre-generated session, exactly as it does now.

---

## 12. Open questions — your decisions

1. **Which X-factor do you lead with?** *Human critiques AI* (the original
   framing) or *AI critiques the human, grounded in what they were taught* (what
   the handoff naturally produces, and easier to show live). **← the most
   consequential question here.**
   *New information that partly settles it:* the roadmap's version — *"AI
   proposes a change, the user critiques it, and the Grader distinguishes real
   understanding from passive acceptance"* (`roadmap.md:196`) — **has already been
   discharged**, by the AI-critique lesson form mapped to the `risk` kind and
   shipped 2026-08-15 (`learning-engine.md:1229`, `:1709`). It lives *inside* the
   learning loop, and it is Beat 3 of the current runbook. So the two are not
   competing for the same slot: the original framing is delivered by the lesson,
   and the handoff would add the inverse after readiness. That makes "both" a
   coherent answer rather than a dodge.
2. **Is a second live tool acceptable on the day?** If not, C still works —
   Beat 5 is the argument and Beats 6–7 are the payoff. Say now, because it
   changes how much of §10 step 4–5 is worth building.
3. **How many days do you actually have?** §10 is 2–3 days for steps 1–3. If it
   is less than that, the answer is A with §9's REMOVE list *deferred, not done* —
   do not start this and leave it half-built.
4. ~~**Do you want the return channel at all?**~~ **Answered by §4.1: yes, or
   choose A.** Without it the coding agent's edit becomes the artifact with
   nothing of ours in between, which violates DI-6 ①. The remaining choice is
   narrower: does the *diff* come back (keeping the `ast.parse` and symbol checks
   alive) or only the *file list* (keeping the path check alive)? I lean file list
   for v1 — smaller, no privacy question, and the path claim is the one the demo
   actually makes.
5. **Is "the learner works in their own clone" acceptable?** CodeOnboard never
   sees their filesystem, so the handoff is a file they move. If you want it
   seamless, that needs the local-path field in §10 step 4.
6. **Should the plan ship inside the artifact?** Including it is a pedagogical
   commitment device; excluding it leaves the agent free to plan against the code
   it can actually see. I lean *include, marked as the learner's stated approach
   rather than as instructions.*
7. **Do you want the existing flow removed, or left behind a door?** I recommend
   leaving it until the handoff is better on your own machine — but a half-removed
   feature is worse than either, so decide before touching it.

---

## Appendix — what is proven vs what is asserted

Relevant to which architecture is defensible, because it says where the evidence
actually is.

**Measured** (`contribution-journey.md` §B6/B14/B21, and the Candidate A runs):
the goal-directed contrast — architecture `core_before_band=14`, journey 19,
areas 8, against contribution 7–12 / 7–14 / 4–5, with `demoted_by_band = 0` on
every run, so no cap produced the difference. Investigation reliability ~1 in 3,
tracked and known. Timings throughout.

**Measured once, n = 1** (B9, session `d0a18721…`): a deliberately flawed patch
returned `meets_task: false` with six concerns tied to the task or the boundary.
There is no acceptance harness, no adversarial set and no stated gate — contrast
the Tutor, which has `evidence/tutor/` measuring 1 leak in 30 adversarial prompts
against a gate of 0.

**Asserted, never measured:** that the in-app Plan is useful, that the Haiku
Review is worth reading, that the generated PR body is good, that the Implement
textarea is usable for a real change.

**Every measured claim is upstream of the boundary this document proposes.**
Nothing that has been proven about this system depends on CodeOnboard owning the
implementation flow.

**But read that asymmetry precisely.** It says the second half is the
*thinnest-evidence* part of the system, and therefore the cheapest to cut or
replace. It does **not** say a handoff would be better, because a handoff has no
evidence at all. The choice is between a tested-but-unmeasured surface and an
untested-and-unmeasured one, decided on architecture rather than on data.

---

## Appendix B — what the record says *against* this proposal

Recorded so the defence is not surprised by it.

1. **The handoff is unconsidered, not rejected.** No planning document, archive
   entry or commit ever evaluated delegating implementation to an external agent.
   That cuts both ways: there is no prior refutation, and there is no prior
   support either.
2. **The record's own reasoning about implementation is that it is not
   *learning*, not that it belongs elsewhere.** §6.2 — described in the document
   as *"the single most consequential decision"* — is about keeping the stage
   **out of the learning graph**. It concluded *isolate*, and then kept it inside
   deliberately. D4's contract reasoning (*"'Write your patch' has no claim to
   mark, so it would be a node with a hollow contract"*) supports moving it out,
   but was not used that way.
3. **B24.2 of `contribution-journey.md` rejected drawing implementation as a
   separate product**, with the reason *"implementation is the last phase of a
   learning journey, not a separate product"* — written earlier the same day as
   this document, about the route rail. It was a decision about **layout**, not
   about **ownership**, and §2 here argues the boundary falls in a different place
   than that section assumed. Both can be true — the handoff is still presented as
   the journey's last phase — but the tension is real and should be stated rather
   than glossed.
4. **The strongest single argument for keeping it inside is D2/D3 plus DI-6:**
   the `change_boundary` is grounded through `anchors.resolve`, and the
   deterministic scope claim exists *because* the boundary is ours. Hand the
   implementation to a tool that never sees `anchors.resolve`, and that claim has
   nothing to attach to — **unless the changed files come back**. That is exactly
   why §4.1 makes the return channel a condition rather than a nicety.

**Origin note.** `contribute_code` entered the system on 2026-05-09 in commit
`3324cc8` as a label in `GOAL_TYPE_MAP` routing one follow-up question. Nothing
in its origin promised an implementation flow; the flow arrived later, as item 6
of six in a "build now" list, on the reasoning that the demo should end somewhere
concrete.

---

# Part II — Approved direction: Hybrid (C) with a two-tool MCP server

> Decision taken: **Option C**, plus a deliberately small MCP integration.
> CodeOnboard owns through *Locate*; Claude Code owns editing, testing, review
> and PR. **This part is an implementation plan awaiting approval. Nothing is
> built.**

## 13. The shape, in one paragraph

The skill and the MCP config are **generic and written once**. The only
per-session thing that travels is **the session id, in the MCP server's env**.
There is therefore **no generated data file**, no copy of the boundary on disk,
and no staleness: context is read live from the one authority (DI-1). Two tools,
both of which earn their place — `get_contribution_context` because it is the
*only* delivery path for the context, and `check_scope` because it is the
genuinely dynamic call a file could never serve.

```
CodeOnboard  --  Locate  --> "Continue in Claude Code"
                                 |  shows the handoff summary
                                 |  + one-time setup, one command
                                 v
                            Claude Code (learner's own clone)
                                 |  skill: "the learner is the implementer"
                                 |--> get_contribution_context()   <- MCP
                                 |      task . revision . boundary . tests
                                 |      . edge cases . readiness
                                 |--  learner edits, Claude scaffolds
                                 |--  pytest — real tests, real result
                                 `--> check_scope(git diff --name-only) <- MCP
                                        "3 files, all inside the boundary"
```

**DI-6 is satisfied without a persistence round trip.** `check_scope` *is* the
boundary between the agent's output and a CodeOnboard claim: the changed files
come back and *our* deterministic code produces the verdict. Nothing external
becomes stored state, so there is no stored state to protect — and the scope
claim stays ours (DI-1). **`report_outcome` is therefore cut from v1.** It is not
free: it needs a new persisted field, validation and provenance, and it buys
nothing the demo shows.

---

## 14. The nine answers

### 14.1 Exact location

| Path | What | Size |
|---|---|---|
| `backend/mcp_server.py` | the whole server: JSON-RPC loop + 2 tools | ~180 lines |
| `backend/learning/handoff.py` | **pure** `build_context(graph, dossier, survey, commit) -> dict` | ~70 lines |
| `backend/learning/contribution.py` | **+`check_paths(paths, boundary)`** — additive, nothing changed | ~20 lines |
| `backend/api.py` | `GET /session/{id}/contribution/handoff` — same `build_context` | ~25 lines |
| `tools/claude-skill/SKILL.md` | the instruction template, generic, written once | prose |
| `frontend/components/contribution/HandoffStep.tsx` | the transition surface | ~150 lines |

Named `mcp_server.py`, not `mcp/`, so it can never shadow the `mcp` package.

`build_context` exists so the endpoint and the tool cannot disagree — one
function, one authority, tested once (DI-1, DI-7).

### 14.2 Transport and run model

**stdio, local, spawned by Claude Code.** No port, no HTTP, no OAuth, no
lifetime to manage. The process starts when Claude Code starts and dies with it.

**Dependency decision — recommend zero-dependency.** The tool-only surface of MCP
over stdio is newline-delimited JSON-RPC 2.0 with four messages: `initialize`,
`notifications/initialized`, `tools/list`, `tools/call`. That is ~110 lines of
stdlib Python, testable by feeding it dicts, with no network and no resolver
risk. The official SDK is fewer lines but adds twelve transitive packages
(`httpx2`, `pyjwt[crypto]`, `opentelemetry-api`, `sse-starlette`,
`python-multipart`, `pywin32`, ...) to an environment this project deliberately
slimmed — the week before submission, that is the wrong risk to take.

*Fallback:* if the handshake proves fiddly against the real client, install the
SDK into a scratch venv first and confirm it resolves before touching
`pyproject.toml`. ~20 minutes to find out. (`mcp` 2.1.1 requires Python >= 3.10;
this project runs 3.11.15, so it is compatible — the objection is footprint, not
support.)

**Ownership — the model is used, not bypassed.** `load_graph` requires a
`user_id` and that is the security model. The server reads **both**
`CODEONBOARD_SESSION` and `CODEONBOARD_USER` from its env — exactly as the API
reads them from a cookie — and calls `load_graph(session, user, db)` unchanged.
A mismatch returns `None`, so the tool answers *"session not found"*: **404, never
403 (D20), for free.** No token table, no new auth. `CODEONBOARD_DB` selects the
database (`data/demo.db` for the presentation).

### 14.3 Tool schemas

**`get_contribution_context()`** — no arguments; the session is the server's
identity, so there is no id for a model to mistype.

```jsonc
{
  "repository": { "url": "...", "commit": "e8d2c015...",
                  "verify": "git rev-parse HEAD must match commit" },
  "task": "Add get_all(name, ...) to RequestsCookieJar ...",
  "change_boundary": {
    "target":          [{ "file", "symbol", "why_here" }],
    "must_not_change": [{ "file", "symbol", "why_not" }],
    "existing_tests":  [{ "file", "symbol", "what_it_guards" }],
    "edge_cases":      [{ "case", "why_it_bites", "file?", "symbol?" }],
    "conventions":     [{ "convention", "evidence_file" }]
  },
  "contracts": [{ "file", "symbol", "contract" }],
  "recommended_validation": "pytest tests/test_requests.py -q",
  "learner": {
    "ready": true, "required": 11, "demonstrated": 11,
    "demonstrated_concepts": ["...objectives..."],
    "not_taught": [{ "name", "reason" }],
    "means": "...answered a question the Grader classified strength or recovered. Not a certification, and it says nothing about their ability to write this code."
  }
}
```

Repository knowledge and learner state stay in separate objects (§6). **File and
symbol; never line numbers** — ranges go stale, symbols do not, and
`anchors.resolve` is the oracle.

**`check_scope(changed_files: string[])`** — the one dynamic call.

```jsonc
{
  "passed": true,
  "in_boundary":       ["src/requests/cookies.py", "tests/test_requests.py"],
  "outside_boundary":  [],
  "forbidden":         [],
  "unchecked_symbols": ["src/requests/cookies.py:get"],
  "checked":     "file paths against the contribution boundary for this session",
  "not_checked": ["syntax", "symbol definitions", "protected symbols", "tests"]
}
```

**`not_checked` is not decoration — it is required.** `check_scope` today sets
`symbol_expected` unconditionally, so calling it without file contents reports
"symbol not defined" falsely; and an empty `unparseable` list would render
*"Syntax — all files parse"*, a claim nobody made. Hence `check_paths`, which
makes only the path claim and names what it did not do. Same rule as B4.3:
**silence reads as a pass.**

### 14.4 How Claude Code connects

**Primary — a generated `.mcp.json`**, downloaded from the transition screen and
dropped in the learner's clone root:

```jsonc
{ "mcpServers": { "codeonboard": {
    "type": "stdio",
    "command": "uv",
    "args": ["run", "--directory", "C:/personal/CodeOnboard",
             "python", "-m", "backend.mcp_server"],
    "env": { "CODEONBOARD_SESSION": "73a2248c...",
             "CODEONBOARD_USER":    "...",
             "CODEONBOARD_DB":      "data/demo.db" } } } }
```

Project scope, so Claude Code asks for approval once per directory.
**Alternative:** a copyable `claude mcp add --scope local ...` one-liner — verify
which is smoother during rehearsal and keep the other as the fallback. Both are
one-time.

### 14.5 What is generated

**Almost nothing, and that is the point.**

| Artifact | Per session? | Where |
|---|---|---|
| `SKILL.md` | **no** — generic, written once | `~/.claude/skills/codeonboard-contribution/` |
| `.mcp.json` | yes, but only the env values differ | learner's clone root |
| handoff data | **never written** | read live via the tool |

The skill's rules (§7.1), stated as guidance and **not claimed as enforcement**:
the learner is the implementer · call `get_contribution_context` first and verify
the commit · use `edge_cases` as questions, not as a spec · do not hand back what
`not_taught` or the unresolved list says they have not covered without asking ·
check the diff with `check_scope` before finishing · keep scope, correctness and
tests as three separate claims.

### 14.6 What CodeOnboard exposes

On **Locate**, the primary action becomes **Continue in Claude Code**, opening a
panel with: the compact handoff summary (rendered from `build_context` — the same
thing the tool returns), the one-time setup (download skill, download
`.mcp.json`), and the command to start. A deep link
`claude-cli://open?cwd=...&q=...` is offered **only if** the learner has told us
their clone path — an optional field, remembered client-side. If they have not,
the panel shows the two commands instead. No fragile automation on the demo path.

### 14.7 What is kept, and what is only unlinked

**Nothing is deleted in this plan.**

| Component | v1 |
|---|---|
| Plan, Locate | **kept**, unchanged |
| ScopeCheck, `ready_to_implement`, `skipped_areas`, `change_boundary` | **kept**, now also feeding the handoff |
| Implement, Validate, Review, PR-ready | **unlinked from the stepper**, routes and components left in place |

The stepper becomes `Plan -> Locate -> Continue in Claude`. The backend routes
stay live, so the old flow is reachable and testable as a fallback until the new
one is verified. **Deletion is a separate, later, single commit** — after the demo
works.

### 14.8 Rehearsal

Setup, once, before the day:

1. `git clone https://github.com/psf/requests` to a **separate working clone**
   and `git checkout e8d2c015` — **the pinned revision.** Anchors are only true
   there. Never `data/repos/psf/requests`: that is the shared, pinned checkout the
   grounding oracle reads, and nothing may write to it.
2. Install the skill; drop `.mcp.json` in the clone; run `claude` once and
   approve the server. Confirm `/mcp` lists `codeonboard` with 2 tools.
3. Walk the whole beat once end to end, then restore checkpoint `03`.

On the day: Beats 1–4 exactly as today (all still checkpointed), then Locate ->
Continue in Claude Code -> context tool -> the learner types the change -> pytest
-> `check_scope`. **Fallback if MCP does not connect:** the panel's summary is on
screen and carries the argument; say what the tool call would have sent, and move
on.

### 14.9 Size and risk

**~2 days.** Backend ~300 lines including the protocol; frontend ~150; skill
prose; tests: `test_handoff_context.py` (pure), `test_check_paths.py` (pure),
`test_mcp_server.py` (protocol + both tools, no network), one frontend test.

| Risk | Severity | Mitigation |
|---|---|---|
| Protocol handshake wrong against the real client | **high** | build it first, test against `claude` on day 1, before any UI |
| Learner's clone on the wrong revision — every anchor silently wrong | **high** | `verify` in the payload; the skill checks it first; refuse rather than fabricate (DI-8) |
| Windows quoting in the `uv run --directory` command | medium | rehearse; `.mcp.json` avoids most shell quoting |
| A terminal is needed on stage | medium | pre-opened, pre-approved, skill pre-installed |
| Boundary is the 1-in-3 part of the system | medium | demo from a pre-generated checkpoint, as now |
| SDK dependency resolution | **avoided** | zero-dependency server |

**Cut list if this grows past two days**, in order: the deep link (14.6) -> the
downloadable `.mcp.json` in favour of a pasted command -> `get_contribution_context`
in favour of a generated file, leaving `check_scope` as the only tool. **The last
cut still satisfies every goal**: one real runtime capability, visible in the demo.

---

## 15. What shipped, and where it diverged from this plan

Recorded rather than tidied away: the divergences are the part worth reading.

### Adopted as planned

The product boundary of §2, the two-namespace payload of §6, the learner-agency
rules of §7, and the state-ownership rule of §8 — *a coding agent's success is
never evidence about a learner* — all shipped unchanged.

### Diverged — MCP was adopted after all, and §5 was wrong about the cost

§5 recommended against MCP and called it "decoration" for the handoff. It shipped,
by decision, with the surface §5.5 sketched minus `report_outcome`. Two of that
section's arguments survive and one did not:

- **Survived.** An MCP server still cannot contribute instructions, so the
  learner-is-the-implementer rule lives in a skill and a server `instructions`
  string, not in a tool.
- **Survived.** `check_scope` is the one genuinely dynamic call, exactly as
  predicted — and it turns out to carry the DI-6 obligation, which is why
  `report_outcome` was not needed: the changed files come back and *our*
  deterministic code produces the scope claim, so nothing external becomes stored
  state and there is no stored state to protect.
- **Wrong.** §5.3 argued the dependency footprint was a reason to hand-roll the
  protocol. Measured against a copy of `pyproject.toml` and `uv.lock` before
  adding anything: `mcp` 2.1.1 adds **16 packages, removes 0, and moves exactly
  one existing pin** (`idna` 3.17 → 3.19). fastapi, starlette, pydantic, anthropic
  and langgraph are untouched. The objection was overstated and the official SDK
  was used.

### Diverged — the launch mechanism failed once in the field

The first implementation used `claude-cli://open?repo=<owner>/<name>`, on the
documented behaviour that Claude Code resolves a slug to a clone it has seen.
**It did not work, and it failed silently**: no clone of `psf/requests` existed in
any of the 48 directories Claude Code knew, so the link opened the HOME directory
and `/mcp` was empty. The proof that had been offered for it was invalid — the
directory where the server was shown `✔ Connected` was a scratch folder that was
not a git repository at all, so a slug could never have found it.

Replaced by `cwd=<absolute path>`, **derived** from the project root and the
session's repository URL as `workspace/<owner>/<name>`, with `null` — and no
button — when no working copy is prepared. The lesson generalises: *a control that
silently opens the wrong place is worse than one that is not there* (DI-8), and a
mechanism is not proven until it is proven against the thing it will actually run
on.

### Diverged — two checkouts, not one

Not anticipated in Part I. The learner's working copy had to be a **second**
checkout: `data/repos/<owner>/<name>` is shared, pinned and read by
`anchors.resolve` for every session, so an agent editing it would move the ground
under the whole product. `workspace/<owner>/<name>` is gitignored, prepared by
`tools/prepare_workspace.py` at the same commit the anchors resolve against, and
the refusal to create it under `data/` is tested.

### Not built

`report_outcome` (§8.3) — cut, and §4.1's DI-6 obligation is met by `check_scope`
instead. The old in-app `Implement / Validate / Review / PR` flow (§9's REMOVE
list) is **unlinked from the stepper but not deleted**, and stays reachable as a
fallback until the handoff has been used on a real presentation.

### One thing still unproven

A **model-driven** MCP tool call has not been observed end to end. The server, the
protocol, both tools against live session data, and Claude Code's connection to it
are all verified; what has not been seen is Claude deciding to call a tool and
reading the result. The one-time trust approval that gates it needs an interactive
session in the prepared workspace.
