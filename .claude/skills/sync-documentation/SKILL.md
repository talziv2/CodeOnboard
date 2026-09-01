---
name: sync-documentation
description: Update CodeOnboard's documentation so it still describes the system that exists — after a behaviour change, when closing a milestone, or when a document and the code disagree. Knows which document owns which fact, and the difference between an architecture document and a design record.
---

# Keeping the documentation true

Roughly one commit in six here is a documentation commit, and the corpus is the
project's main artifact after the code. It has one rule above all others:

> **Where a document and the code disagree, the code is right** — and the
> disagreement gets fixed, not left standing.

The second rule is that facts have **owners**. A long explanation lives in exactly
one place and everything else links to it. Copying it into a second document is
how the four stale statements in the old `CLAUDE.md` came to exist.

---

## 1. Find the document that owns the fact

| The change is about | Owner |
|---|---|
| What the system is, setup, running, troubleshooting | `README.md` |
| An invariant a change could break quietly | `docs/architecture/decisions.md` |
| Components, boundaries, dependency direction | `docs/architecture/overview.md` |
| An agent's job, model, inputs, outputs; orchestration | `docs/architecture/agents.md` |
| Layers A/B/C, the tools, grounding | `docs/architecture/repository-understanding.md` |
| The graph, gaps, understanding, progress, adaptation | `docs/architecture/learning-engine.md` |
| Creation, planning, resume, `Start over` vs `Rebuild`, completion | `docs/architecture/session-lifecycle.md` |
| Endpoints, the auth boundary, error conventions | `docs/architecture/backend-api.md` |
| Routing, the view-model layer, surfaces, copy | `docs/architecture/frontend.md` |
| Tables, plan vs state, schema versions, migrations | `docs/architecture/persistence.md` |
| Identities, cookies, passwords, Google, ownership | `docs/architecture/auth.md` |
| An environment variable | `docs/configuration.md` |
| What to run, and the expected failures | `docs/testing.md` |
| A recurring Python idiom | `docs/reference/patterns.md` |
| How this package works, for someone reading its code | the package's own `README.md` |
| Rules an agent must follow while editing | `CLAUDE.md` and the scoped ones |

If the fact has no owner, it usually belongs in the package README beside the
code, not in a new top-level document.

## 2. Know which tier you are editing

- **`docs/architecture/`** — the system as it is. Update it whenever behaviour
  changes.
- **`docs/planning/`** — **design records**, written at a point in time, carrying
  the argument and the rejected alternatives. Several describe work deliberately
  not built. **Do not retcon them.** When something ships differently from the
  plan, record what shipped and *where it diverged* — the divergence is the
  valuable part. Mark milestones shipped rather than rewriting them as though they
  were always right.
- **`docs/planning/phases/evidence/`** — measured output. Append; never edit a
  result. See `measure-and-record`.
- **`project-archive/`** — an architecture that no longer exists. Never update it
  to match current behaviour; that would destroy the comparison it exists to hold.

## 3. Write it the way this corpus is written

- **Explain why a responsibility sits where it does**, rather than listing the
  files in a directory.
- **State a rule with the failure it prevents.** That is what makes it checkable,
  and it is why `decisions.md` reads the way it does.
- **Do not repeat a long explanation in two places.** Link to the owner.
- **Deeper documents link back** to their parent and to `docs/README.md`.
- Say what something does **not** do, and what was deliberately not built.

## 4. Verify before you write it down

Every command, path, port, environment variable, symbol and count must be checked
against the repository — that is an explicit convention in `docs/README.md`, and
the failure it prevents is real: the previous `CLAUDE.md` listed four of seven
`goal_type` values, named the wrong number of Sonnet call sites, and stated a cost
target the measurements contradict.

```bash
grep -rhoE "\]\(([^)#]+\.md)" README.md CLAUDE.md docs --include=*.md | sed 's/](//' | sort -u
```

Counts (test totals, file counts) drift fastest. Either check them or do not state
them.

## 5. Then check the always-on layer

A behaviour change may also invalidate `CLAUDE.md`, `backend/CLAUDE.md`,
`backend/agents/CLAUDE.md`, `frontend/CLAUDE.md`, `tests/CLAUDE.md` or a skill in
`.claude/skills/`. Those are instructions Claude follows without being asked, so a
stale one is worse than a stale document.

## Completion criteria

- Exactly one document changed per fact, and links point at it.
- Architecture documents describe current behaviour; planning documents record
  what shipped and where it diverged.
- Every command, path and symbol in the diff was verified.
- No count was stated that was not checked.
- The `.claude/` instruction layer still matches.

## Common failure modes

- Explaining the same thing in the README and an architecture document, so they
  drift apart.
- Editing a planning document to look as though the plan was followed.
- Updating `project-archive/`.
- Documenting a command that was never run.
- Fixing the document and leaving `CLAUDE.md` saying the old thing.
