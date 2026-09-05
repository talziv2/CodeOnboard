# `tools/` — local setup, not part of the product

Utilities run by hand on a developer's own machine. Nothing here is imported by
the application, nothing here runs in a request, and **nothing here spends money**
— that is what separates `tools/` from [`scripts/`](../scripts/README.md), where
every harness calls a model on the user's own API key.

Both refuse to write `data/sessions.db`. It holds every account and every session,
it is gitignored, there is no backup, and it is the corpus behind
[`docs/planning/phases/evidence/`](../docs/planning/phases/evidence/).

| Tool | What it does |
|---|---|
| `demo_checkpoints.py` | Duplicates real sessions at useful moments, so a presentation starts from a chosen state instead of generating one live |
| `prepare_workspace.py` | Prepares the writable working copy that `Continue in Claude Code` opens |

---

## `demo_checkpoints.py`

```bash
uv run python tools/demo_checkpoints.py import --from data/rehearsal.db --session <id> --db data/demo.db
uv run python tools/demo_checkpoints.py snapshot --db data/demo.db --session <id> --as "01 · contribution scope"
uv run python tools/demo_checkpoints.py list --db data/demo.db
uv run python tools/demo_checkpoints.py backup --db data/demo.db --out data/demo-pristine.db
```

A checkpoint is a **copy of a real session**, produced by the real pipeline and
persisted through the normal product path. Opening one is opening a session —
same routes, same rendering, same learning engine, and nothing in the product
branches on "is this a demo".

Two properties are load-bearing:

- **Session-scoped tables are discovered from the schema**, not listed, so a table
  added later is carried without this file changing.
- **`nodes` is keyed on `node_id` alone**, so a duplicate cannot reuse them. Ids
  are remapped by textual substitution over every copied value, which catches the
  ones inside JSON payloads that nobody remembers — `journey_events`, `arrival`,
  the tutor transcript.

`import` **replaces**; it does not accumulate. That is not free: because every
copy mints fresh node ids, an import into a database that already has the session
would otherwise insert a second full set of nodes while `INSERT OR REPLACE`
quietly replaced only the `sessions` row. It shipped that way once, and a restored
checkpoint showed every stop twice.

## `prepare_workspace.py`

```bash
uv run python tools/prepare_workspace.py --session <id> --db data/demo.db
```

Creates `workspace/<owner>/<name>` and writes the `.mcp.json` that points a coding
agent at that session.

**Two checkouts, and they must stay two:**

| Path | What it is |
|---|---|
| `data/repos/<owner>/<name>` | ONE shared checkout, pinned, **read-only**. `anchors.resolve` resolves every anchor in every session against it (D2) |
| `workspace/<owner>/<name>` | The learner's own copy, **writable**, edited by a coding agent. Gitignored |

An agent editing the first would move the ground under every lesson in every
session, so this script refuses to write anywhere under `data/` — and that
refusal is tested.

The clone is checked out at **the commit the shared checkout is pinned to**, not
at the remote's `HEAD`, which moves. Every `file:symbol` in a handoff is true at
one revision, so the agent's first instruction is to compare `git rev-parse HEAD`
against `repository.commit`; a workspace on a different commit would be worse than
none, because the context would be confidently wrong.

The path is **derived** from the project root and the session's repository URL, so
nothing machine-specific is written down and another machine reproduces a demo by
cloning CodeOnboard and running this.

One step is left to a human, once per machine: `cd workspace/<owner>/<name> &&
claude`, accept the trust prompt, approve the `codeonboard` server. Only an
interactive session can do it.
