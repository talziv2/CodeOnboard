# Open-source readiness plan

**Status:** planning only. Nothing in this document has been implemented.
**Goal:** `fresh clone → configure API key → fresh DB → local run`, self-hosted,
with the person running it supplying their own Anthropic key.

**Scope discipline.** This is a student final project and a working prototype.
Nothing here is deployment, infrastructure, CI, Postgres, HTTPS or security
hardening. Where an audit item touches one of those areas it is named and
explicitly left out. The one code change proposed (§C-1) is a functional bug on
the first-run path, not hardening.

Everything below was verified against the repository as it stands on branch
`improve-welcome-window` at commit `3dc579e` (2026-08-30), not inferred. Where a
claim came from running something, the probe is described in the appendix.

> **Revision note.** Commit `3dc579e` — *"a forgotten password is a link away, in
> development"* — landed while this plan was being written, and it committed the
> password-reset feature as one coherent unit: `backend/auth/reset.py`,
> `frontend/app/forgot-password/page.tsx`, `frontend/app/reset-password/page.tsx`
> and `tests/test_password_reset.py`, together with the tracked files that
> reference them. **That resolves what was the hardest runtime blocker in the
> first draft** (tracked code importing an untracked module). Verified against a
> real clone: `import backend.api` succeeds. The audit in §C-2 has been re-run
> against the new HEAD and is now down to two test files and two development-only
> scripts. §B-2 records the resolved finding rather than deleting it, because the
> *class* of defect is what the audit exists to catch.

**Priority model.** Every recommendation carries one of three levels, and the
distinction is load-bearing:

| | Level | Definition |
|---|---|---|
| **A** | **Runtime blocker** | Prevents or breaks `fresh clone → configure key → fresh DB → start backend/frontend → use the application`. |
| **B** | **Required for public release** | Does not stop execution, but should not be published as-is: misleading documentation, missing licence, publishable-but-wrong configuration. |
| **C** | **Nice to have** | Improves developer experience. Deliberately kept small. |

---

## A. Current-state audit

How the application starts today, and what it assumes about the developer machine.

### A.1 Backend startup — **already ready**

`uv run uvicorn backend.api:app --reload`, from the repository root.

`backend/api.py` calls `load_dotenv()` at import (line ~104), **without**
`override=True` — the real environment wins over `.env`, which is the correct
precedence and is documented at length in the file. Then the FastAPI lifespan
handler (`_lifespan`) runs, in this order:

1. `auth_config.enforce()` — refuses to start on an unusable environment.
2. `run_startup_checks(SESSIONS_DB_PATH)` — housekeeping plus the ownership assertion.

Both are safe against a database that does not exist yet. Every function in
`backend/auth/startup.py` either guards with `if not Path(db_path).exists()` or
swallows exactly `no such table` / `no such column`
(`count_unowned_sessions`, `sweep_orphaned_investigations`,
`fail_stale_generating_sessions`, `_purge_expired_auth_sessions`).

**Probe run:** a `TestClient` against `backend.api.app` with `SESSIONS_DB_PATH`
pointed at a temp directory started cleanly with no database file present, and
started cleanly again on a second boot against a partially-populated one. No
change needed.

### A.2 Frontend startup — **already ready**

`cd frontend && npm install && npm run dev` → `http://localhost:3000`.

`frontend/lib/api.ts` line 10: `const BASE = "/api"`. The browser never contacts
`:8000` directly. `frontend/next.config.ts` rewrites `/api/:path*` to
`${API_ORIGIN}/:path*`, with `API_ORIGIN` defaulting to `http://localhost:8000`
and read by the Next **server** at request time. There is no
`NEXT_PUBLIC_API_URL` baked into the browser bundle any more.

This means **local-first is already the default and there is no "web version" to
separate out.** Requirement 3 is satisfied by the existing architecture; the only
work is documenting it.

### A.3 Configuration / environment loading — **already ready**

Every environment variable the system reads, and its default:

| Variable | Read at | Default | Required for a fresh local run |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | `auth/config.py:69`, and each agent's client construction | none | **yes** |
| `CODEONBOARD_COOKIE_SECURE` | `auth/config.py:38`, `auth/routes.py:71` | `1` (secure) | recommended `0` |
| `CODEONBOARD_ENV` | `auth/config.py:34` | `development` | no |
| `CODEONBOARD_ALLOWED_ORIGINS` | `api.py:149` | `http://localhost:3000,http://127.0.0.1:3000` | no |
| `CODEONBOARD_SECRET_KEY` | `auth/google_routes.py:52` | per-process random | no |
| `CODEONBOARD_TRUST_PROXY` | `auth/routes.py:107` | unset | no |
| `GOOGLE_CLIENT_ID` / `_SECRET` | `auth/google.py:81` | unset → button hidden, `/auth/google/start` → 503 | no |
| `CODEONBOARD_CURRICULUM` | `agents/mentor/agent.py:49` | `0` | no |
| `CODEONBOARD_GAPS` | `learning/flags.py:26` | `0` | no |
| `API_ORIGIN` | `frontend/next.config.ts` (Next server) | `http://localhost:8000` | no |
| `NEXT_DIST_DIR` | `frontend/next.config.ts` | `.next` | no |
| `GITHUB_TOKEN` | **nowhere** | — | **no — see B-4** |

Google sign-in being absent-rather-than-broken when unconfigured is exactly the
right behaviour for a fresh clone and needs no change.

### A.4 Anthropic client initialization — **already ready**

Thirteen call sites, all identical in shape:
`anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])`. A missing key
would be a `KeyError` at those sites — but it never gets that far, because
`auth_config.check()` (`backend/auth/config.py:69`) checks it **unconditionally,
in every environment**, and `enforce()` raises `InsecureConfiguration` from the
lifespan handler with the message:

> `ANTHROPIC_API_KEY is not set — every lesson, grade and plan needs it.`

Uvicorn then reports `Application startup failed` and exits. **Requirement 2
("fail clearly if a required key is missing") is already met.** The only change
needed is documenting the message in `RUN.md` so the reader recognises it.

### A.5 Database path and initialization — **already ready**

`backend/learning/store.py:98`: `DEFAULT_DB_PATH = Path("data/sessions.db")`.
Relative to the process working directory, i.e. the repository root. There is one
SQLite file; `backend/repo/survey_store.py:21` and
`backend/repo/dossier_store.py:26` point at the same path.

Creation is fully automatic and lazy:

- `store._connect` (lines 245–246) does
  `db_path.parent.mkdir(parents=True, exist_ok=True)` before `sqlite3.connect`,
  so both `data/` and the file appear on first use.
- `store.init_db` issues seven `CREATE TABLE/INDEX IF NOT EXISTS` plus
  `_add_missing_columns`, which reads `PRAGMA table_info` and adds only what is
  absent. Called by `save_graph`, `create_session`, `create_pending_session`.
- `auth/schema.init_auth_schema` is the same idea for the six account tables, and
  is called by every write path in `identity.py`, `tokens.py`, `drafts.py`,
  `reset.py`.

`data/` also survives a clone because `data/experiments/*.json` is tracked, so the
directory exists even before anything runs.

**No manual database step is required on a fresh clone, and none should be
added.** Do not redesign the persistence layer.

### A.6 Migrations — **already ready, and correctly a no-op on a fresh clone**

`backend/migrations/001_multi_user.py` exists for one purpose: giving an owner to
sessions written before accounts existed. On a fresh install it short-circuits —
`if not Path(db_path).exists(): report["error"] = "database does not exist"` — and
on an empty-but-created database it assigns zero rows. A new user never runs it.
`RUN.md` should not mention it at all.

### A.7 Account / user initialization — **already ready**

No bootstrap, no seed user, no admin account, no allow-list.
`POST /auth/register` (`auth/routes.py:179`) is open, creates the `users` row and
the `auth_identities` row in one flow, issues a cookie, and cleans up the user row
if the identity insert collides. The "legacy user" in `identity.py` is only ever
created by the migration.

### A.8 First-run application state — **one blocker, see B-1**

`frontend/app/page.tsx` redirects `anonymous → /login`, `authenticated →
/sessions`. `/signup` exists and is reachable. `frontend/app/sessions/page.tsx`
has a real empty state ("INVITES rather than apologises") and renders the
`Start a new session` button **above** the list, so it is present even when the
list fails to load.

The one thing that is wrong on a fresh install is `GET /sessions` itself. Detail
in §B-1.

### A.9 Scripts and package commands — **small change needed**

- `run-dev.bat` — tracked, Windows-only, and it **forces two development flags**:
  `CODEONBOARD_CURRICULUM=1` and `CODEONBOARD_GAPS=1`. Neither is the shipped
  default. Its comment block is also stale (it says gaps are not shown to the
  learner; `CLAUDE.md` says they now are).
- `.claude/launch.json` — tracked, 18 configurations, most of them
  machine-specific: ports 3001/3007/3100/3105/3107/8001/8100/8105/8107, a `cwd`
  of `.ui-audit-fe` (a directory that is **not in the repository**), and
  `scripts.ux_fixture_app:app` with `CODEONBOARD_UX_DB=data/ux-fixture.db` (a
  module that is currently **untracked**). Several of these configurations cannot
  work on a fresh clone.
- `frontend/tsconfig.json` — tracked and modified. Its `include` array names
  `.next-3105/types/**/*.ts` and `.next-3107/types/**/*.ts`, alternate build
  directories from the multi-port development setup. Neither exists on a fresh
  clone. TypeScript ignores an `include` glob that matches nothing, so this is
  **not** a blocker — it is machine-specific leftover in a published file.
- `scripts/` — 26 tracked measurement/probe/smoke scripts. Seven of them read
  `data/sessions-fixtures.db` or `data/sessions.db` (`grader_eval.py`,
  `m10_acceptance.py`, `reteach_probe.py`, `altitude_boundary_probe.py`,
  `gap_identity_probe.py`, `gate_stage4.py`, `smoke_stage4.py`). Those databases
  are gitignored and will not exist. This is **acceptable** — they are research
  instruments, not part of running the app — but `RUN.md` must not point at them.

### A.10 Ignored and tracked runtime files — **small change needed**

`.gitignore` correctly covers `.env`, `.venv/`, `data/repos/`, `data/*.db` and its
three SQLite sidecars, `__pycache__/`, `.pytest_cache/`, `.idea/`,
`_tmp_compare/`, `frontend/.next/`, both `node_modules/`, `data/quarantine/`.

The gap: four local artifacts are ignored **only** by `.git/info/exclude`, which is
per-clone and never published —

```
.ui-audit-fe/
data/sessions.db.uibaseline-backup
data/sessions.db.post-f2
frontend/public/probe.txt
```

`data/sessions.db.post-f2` and `data/sessions.db.uibaseline-backup` do not match
`data/*.db`, because the suffix comes after the extension. They are not at risk on
a fresh clone (they will not exist), but the pattern that catches them belongs in
the published `.gitignore`.

`frontend/next-env.d.ts` and `frontend/tsconfig.tsbuildinfo` are ignored and
**correctly so** — Next regenerates the first on every `dev`/`build`, and the
second is a compiler cache. No action.

### A.11 README / setup documentation — **wrong, but not a runtime blocker**

`README.md`'s Setup section is broadly right in shape (`uv sync`,
`cp .env.example .env`, `uvicorn`, `npm install`, `npm run dev`, two terminals,
the two ports) but its Tech Stack section is materially wrong. It advertises:

- **Python 3.14** — `.python-version` says `3.11`, `pyproject.toml` says `>=3.11`.
- **nomic-embed-text-v1.5 via sentence-transformers**
- **ChromaDB (vector store)**
- an architecture bullet reading "Vector Store (RAG)"

`pyproject.toml` states in a comment that Stage 5 removed the entire
embedding/vector stack, and `CLAUDE.md` states "There is no retrieval, no
embedding model and no vector store." A new developer following the README will
try to install a stack that no longer exists.

`frontend/README.md` is still the untouched `create-next-app` boilerplate.

### A.12 Secrets in history — **already ready, verified clean**

- `git log --all -- .env` → empty. `.env` has **never** been tracked.
- `git log --all -- "*.db" "data/*.db"` → empty. No database has ever been tracked.
- `git grep -nIE "sk-ant-…|ghp_…|github_pat_…|AKIA…|BEGIN … PRIVATE KEY"` over the
  tracked tree → no matches.
- The same patterns over `git log --all -p` (full history diff) → no matches.

**No history rewrite is required.** The tracked tree is 10.7 MB, `.git` is 25 MB;
the largest single file is `docs/poster/codeonboard-poster.png` at 1.2 MB. Nothing
needs stripping for size either.

### A.13 Absolute / machine-specific paths — **already ready**

A search for `C:\`, `C:/`, `/Users/`, `/home/` and the developer's name across
`backend/`, `frontend/`, `scripts/`, `tests/` and `.claude/` returned only test
fixture data (`"Shira"` as a display name in `tests/test_auth.py`,
`frontend/lib/sessionSummary.test.ts`, `tests/test_migration.py`, and a personal
repository URL in `tests/test_repo_identity.py:104`). None of these affect running
the application. Every data path in application code (`data/sessions.db`,
`data/repos`) is repository-root-relative.

### A.14 Tracked-vs-untracked consistency — **now ready; keep the check**

Tracked code must never reference a file that is not tracked. Until commit
`3dc579e` it did — `backend/auth/routes.py:44` imported `backend.auth.reset`,
which was untracked, so a clone could not import `backend.api` at all.

**Verified resolved.** A `--no-hardlinks` clone of `improve-welcome-window` into a
temp directory imports cleanly:

```
=== data/ in the clone ===   experiments
=== .env present? ===        No such file
=== db/env tracked? ===      (empty)
=== import backend.api ===   IMPORT OK
```

Two source files remain untracked, and the audit in §C-2 classifies them. Neither
is referenced by tracked code, so neither is a blocker.

---

## B. Gaps

Only the things actually preventing `fresh clone → own API key → fresh DB → local
run`, or making the published repository misleading. Each carries its priority
level.

### B-1. `GET /sessions` returns 500 on a brand-new installation — **level A**

**Evidence (reproduced, not inferred).** A probe pointed
`backend.api.SESSIONS_DB_PATH` at a temp path and drove the real app:

```
fresh db path: …\co-fresh-…\data\sessions.db   exists before: False
health:    200 {'status': 'ok'}
me (anon): 401
register:  201 {'user_id': '26dfa70…', 'email': 'probe@example.com'}
sessions:  sqlite3.OperationalError: no such table: sessions
```

Tables present after registration:
`auth_identities, auth_sessions, password_resets, repositories, session_drafts, users`
— i.e. the account layer only.

**Mechanism.** `store.list_sessions_for_user` (`backend/learning/store.py:1024`)
guards with:

```python
if not Path(db_path).exists():
    return []
```

That guard was written for "no file at all". But registration creates the file —
`init_auth_schema` → `_connect` → `sqlite3.connect` — **without** creating the
learning store's `sessions` table. The file now exists, the guard passes, and the
`SELECT … FROM sessions` hits a table that is not there. The route raises, FastAPI
returns 500, and `frontend/app/sessions/page.tsx` renders a red error line.

**Blast radius, stated honestly.** It is not permanent and it is not a hard block:
the `Start a new session` button renders above the error, and the first
`POST /session/start` calls `create_pending_session` → `init_db`, after which the
dashboard works forever. But it is the **first screen a new user sees after
signing up**, and it is the exact acceptance path this whole task is about.
`store.delete_session` (line 1235) has the same guard shape and the same latent
failure.

### B-2. Tracked code references untracked files — **was level A, RESOLVED by `3dc579e`**

Recorded rather than deleted, because the *class* of defect is what §C-2's audit
exists to catch, and it will recur on the next feature branch.

**What it was.** `backend/auth/routes.py:44` read
`from backend.auth import config, identity, passwords, reset, throttle, tokens`
while `backend/auth/reset.py` was untracked → a clone failed at import → the
backend did not start at all. Two frontend routes were in the same position one
level down: `frontend/components/auth/AuthForm.tsx:141` links
`href="/forgot-password"` and `frontend/lib/auth.tsx:53–54` lists
`/forgot-password` and `/reset-password` as public routes, while neither page file
was tracked — a 404 on an advertised control rather than a build failure.

**How it was resolved.** Commit `3dc579e` shipped the feature whole: the module,
both pages, the test file, and the ten tracked files that reference them, in one
commit. That is the right shape, and it is the shape the audit is asking for.

**What remains.** Nothing at level A. §C-2 re-runs the check against the new HEAD.
**The implementation must still never resolve this class of finding with
`git add -A`** — the remaining untracked files include two that should stay
untracked.

### B-3. README describes a stack that was deleted — **level B**

Python 3.14, ChromaDB, sentence-transformers, nomic embeddings, "Vector Store
(RAG)". See A.11. Nothing about it stops the app running — the commands in the
Setup section are correct — but it is the first thing anyone opening the GitHub
page reads, and it sends them to install a stack the project removed.

### B-4. `GITHUB_TOKEN` is documented but never read — **level B**

`.env.example` line 2 and the README both list it. A search across `backend/` and
`scripts/` for `GITHUB_TOKEN` returns **zero** reads. `backend/repo/cloner.py`
clones public repositories anonymously and deliberately *disables* credential
prompts (`GIT_TERMINAL_PROMPT=0`, `GIT_ASKPASS=""`). Telling a new user to obtain
a token they do not need is a setup step that does not need to exist.

### B-5. No `LICENSE` file — **level B**

`ls LICENSE*` → nothing. Without one, "open source" is not legally what the
repository is, and GitHub will show no licence badge.

### B-6. Prerequisites are undocumented — **level B**

The project needs, and nowhere says it needs: `git` on `PATH` (GitPython shells
out to it — `cloner.py` uses `git.cmd.Git().ls_remote` and `git clone`), Node
(`frontend/package.json` has **no `engines` field**; Next 15.3 requires ≥18.18),
`uv`, and Python ≥3.11 (`.python-version` pins 3.11). A reader currently has to
infer all four. Absorbed by `RUN.md` (§C-4).

### B-7. `.gitignore` misses locally-excluded artifacts — **level B**

Four patterns live only in `.git/info/exclude`, which is not published. See A.10.
Nothing breaks on a fresh clone (the files will not exist); the risk is that a
future local artifact of the same shape gets committed by accident.

### B-8. Tracked dev tooling assumes this machine — **level B**

`.claude/launch.json` references `.ui-audit-fe/` (not in the repo) and
`scripts.ux_fixture_app` (untracked); `frontend/tsconfig.json` includes
`.next-3105`/`.next-3107` type globs; `run-dev.bat` is Windows-only and forces two
non-default flags. None prevents the documented setup path from working —
`RUN.md` will not point at any of them — so this is publication quality, not
function.

---

## C. Recommendations, classified

Eight changes, unchanged in substance from the first draft except that C-2 is now
an audit rather than a bulk commit. Each is re-evaluated below against the three
priority levels.

### C.0 Summary table

| | Change | Level | Still recommended | Effort |
|---|---|---|---|---|
| **C-1** | Initialize both schemas at startup | **A** | yes — the only level-A item left | ~5 lines + 1 test file |
| **C-2** | Tracked-files audit (explicit, per file) | **B** (level-A rows resolved by `3dc579e`) | yes | audit done below; `git add` of 2 named paths |
| **C-3** | Correct `README.md` | **B** | yes | 20 min |
| **C-4** | Write `RUN.md` | **B** | yes | 45 min |
| **C-5** | Clean up `.env.example` | **B** | yes | 10 min |
| **C-6** | Add `LICENSE` | **B** | yes | 2 min + one decision |
| **C-7** | `.gitignore` + machine-specific tracked config | **B** | yes | 20 min |
| **C-8** | `engines` in `frontend/package.json` | **C** | optional | 1 min |

**Combinable.** C-2's remaining `git add`, C-5, C-6 and C-7 are small edits to a
handful of configuration files with no interdependencies; do them as **one
commit**. C-3 and C-4 are a single documentation pass, since C-3's main edit is
"delete the setup section and point at `RUN.md`" — also **one commit**. With C-1
standing alone, that is **three implementation commits** for the whole plan.

---

### C-1 — Initialize both schemas once, at startup — **level A**

**Files:** `backend/api.py` (`_lifespan`) — or, equivalently,
`backend/auth/startup.py` (`run_startup_checks`).

**What changes.** Before the housekeeping sweeps, call
`learning_store.init_db(SESSIONS_DB_PATH)` and
`auth_schema.init_auth_schema(SESSIONS_DB_PATH)`. Both are idempotent
(`CREATE … IF NOT EXISTS` throughout, and `_add_missing_columns` reads
`PRAGMA table_info` first), so this is a no-op on an existing database and costs
one connection per process.

**Why this rather than adding `init_db` to `list_sessions_for_user`.** The
per-reader fix repairs one symptom; there are two known guards with this shape
(`list_sessions_for_user`, `delete_session`) and nothing prevents a third. Doing
it once at startup makes "the database has its tables" true before the process
serves anything, which is the same discipline `run_startup_checks` already applies
to its other invariants. It is also strictly less code.

**Ordering note.** `init_db` must run **before** `init_auth_schema`, because
`init_auth_schema` creates two indexes on `sessions` columns (`user_id`,
`repo_id`) that `init_db`'s `_ADDITIVE_COLUMNS` adds. `init_auth_schema` already
tolerates their absence, so the order is a nicety rather than a requirement — but
it removes the tolerated-exception path from the normal boot.

**If we do not do it.** Every new user sees a red error on the dashboard
immediately after signing up. It clears itself once they start a session, so the
product is not permanently broken — but the acceptance test in §F fails at step
11, and the first impression is of a broken app.

**Afterwards.** A brand-new installation answers `GET /sessions` with
`{"sessions": []}` and renders the empty state. No 500, no red line.

**Verification.**
- New test, `tests/test_first_run.py`: point `api.SESSIONS_DB_PATH` at `tmp_path`,
  drive `TestClient` through register → `GET /sessions`, assert `200` and an empty
  list. **This test fails on `main` today** — it is the regression guard.
- Second case in the same file: boot the app twice against the same temp path and
  assert the second boot succeeds (proves idempotence).
- `pytest tests/` must stay green — in particular `tests/test_startup_checks.py`
  and `tests/test_migration.py`, which exercise partially-initialized databases.

**Effort:** small. Roughly five lines of application code plus one new test file.

---

### C-2 — Explicit tracked-files audit — **level B (its level-A rows are already done)**

**This replaces "commit the working tree completely". The implementation must
never run `git add -A`, `git add .`, or any equivalent.** Each file below is a
separate decision, and the two `scripts/` entries are recommended *against*
tracking.

**The rule that produced this list.** *No tracked file may reference a file that
is not tracked.* Applied in both directions: either the referenced file becomes
tracked, or the reference is removed.

**Method.** The candidate set is exhaustive, not sampled. It was produced by
diffing every on-disk source file against `git ls-files`:

```
comm -23 <(find backend -name "*.py" -not -path "*__pycache__*" | sort) \
         <(git ls-files backend | grep '\.py$' | sort)
```
…and the same for `frontend/{app,components,lib,test}`, `tests/` and `scripts/`.
`git status --porcelain --untracked-files=all` independently returns the same
paths. Both methods agree, which is what makes this exhaustive rather than
sampled. **Re-run this diff before implementing** — the set changed once already
during this planning task.

#### The audit, as of `3dc579e`

| File | Referenced by (tracked) | Classification | Action | Level |
|---|---|---|---|---|
| `frontend/components/lesson/CompletionScreen.test.tsx` | nothing — tests the tracked `CompletionScreen.tsx` | **required verification** | **track** | **B** |
| `frontend/components/lesson/LessonBrief.test.tsx` | nothing — tests the tracked `LessonBrief.tsx` | **required verification** | **track** | **B** |
| `scripts/ux_fixture_app.py` | `.claude/launch.json:270` (`backend-3107`) only | **development-only** | **leave untracked**, and delete the two `-3107` launch configurations that reference it (C-7) | B |
| `scripts/seed_ux_fixture.py` | `scripts/ux_fixture_app.py` only | **development-only** | **leave untracked** | B |
| `docs/open-source-readiness-plan.md` | this document | **required documentation** | **track** (consistent with the rest of `docs/`) | B |

#### Already resolved by `3dc579e` — recorded for the record

| File | Was | Now |
|---|---|---|
| `backend/auth/reset.py` | required runtime/source; `routes.py:44` imported it | **tracked** |
| `frontend/app/forgot-password/page.tsx` | required runtime/source; `AuthForm.tsx:141`, `lib/auth.tsx:53` | **tracked** |
| `frontend/app/reset-password/page.tsx` | required runtime/source; `lib/auth.tsx:54` | **tracked** |
| `tests/test_password_reset.py` | required verification; only coverage of `auth/reset.py` | **tracked** |

#### Reasoning on the judgment calls

**Why the two `scripts/` files stay untracked.** They are a *fake* backend
(`ux_fixture_app.py` serves a seeded fixture database instead of the real
pipeline) built to review UI states without spending API credit. Their input,
`data/ux-fixture.db`, is gitignored and will not exist on any clone, so tracking
them would publish two scripts that cannot run. The seven *other* tracked scripts
that read gitignored fixture databases are measurement instruments whose results
are in `docs/planning/phases/evidence/` — they document how a published number was
obtained. These two document nothing. That is the distinction, and it is why this
is a judgment call rather than a rule.

Because they stay untracked, the `backend-3107` and `frontend-3107` entries in
`.claude/launch.json` must go — otherwise the repository ships configuration
pointing at files it does not contain, which is the same defect in the other
direction.

**Why the two component test files are level B, not A.** They do not affect
whether the app runs. But `npm test` from a fresh clone is part of the acceptance
gate (§F), and a repository that advertises a test suite should ship the tests
that exist for the components it ships.

**Uncertain — requires the author's review before action.** None. Every file
resolved cleanly. If any of the remaining *modified* tracked files contains work
you do not intend to publish, that is a separate review, and this plan does not
assume the current working tree is final.

**What `3dc579e` demonstrates.** The right resolution to this class of finding is
what that commit did — ship the feature whole, module and pages and tests
together, in one reviewed commit. Not `git add -A` afterwards.

#### What is deliberately NOT in scope of this audit

Ignored files stay ignored. `git status --ignored` lists `.env`, twelve
`__pycache__/` directories, `.venv/`, `node_modules/` ×2, `.next/`, `.next-3105/`,
`.next-3107/`, `frontend/next-env.d.ts` (Next regenerates it),
`frontend/tsconfig.tsbuildinfo` (compiler cache), `data/*.db` ×9, `data/repos/`,
`data/quarantine/`, `.ui-audit-fe/`, `_tmp_compare/`, `.idea/`, `.pytest_cache/`,
`frontend/public/probe.txt`. **None of these should become tracked.** They are
listed here so the decision is on the record rather than implicit.

**If we do not do it.** Two component tests never run in CI or on anyone else's
machine, and `.claude/launch.json` keeps pointing at two modules the repository
does not contain. Nothing breaks. Had `3dc579e` not landed, this row would read
"the published repository does not import" — which is why the check stays in the
plan even though it currently finds little.

**Verification.** From a fresh clone of the published branch:
`uv run python -c "import backend.api"`, then `uv run pytest tests/`, then
`cd frontend && npm run build` and `npm test`. Then re-run the diff command above
against the clone: it should return nothing but the two `scripts/ux_fixture*`
files, deliberately.

**Effort:** trivial now. The audit is done (this table); implementation is a
`git add` of two named paths, plus the launch.json edit that rides along with C-7.

---

### C-3 — Correct `README.md` — **level B**

**Files:** `README.md`.

**What changes.**
- Tech Stack: Python **3.11+** (not 3.14); delete the sentence-transformers,
  nomic-embed and ChromaDB lines; delete the "Vector Store (RAG)" architecture
  bullet. Replace with what is actually there: tree-sitter (AST), a deterministic
  skeleton index, and a budgeted tool-driven exploration loop.
- Setup: replace the inline instructions with a pointer to `RUN.md`, keeping the
  README as the "what is this project" document. Two documents, two jobs.
- Add a Prerequisites line (git, Python 3.11+, uv, Node 18.18+) — this is B-6.
- Add a Licence section once C-6 lands.

**Why level B, not A.** The *commands* in the current Setup section are correct;
someone who ignores the Tech Stack section can still get the app running. What is
wrong is the description of the project, and that is a publication problem.

**If we do not do it.** A reader tries to install ChromaDB and sentence-
transformers, does not find them in `pyproject.toml`, and concludes the repository
is stale or broken before running anything. For an academic submission, it also
misdescribes the architecture being assessed.

**Verification.** Read it against `pyproject.toml` and `CLAUDE.md`; no dependency
named in the README that is absent from `pyproject.toml`.

**Effort:** small — one editing pass, ~20 minutes. **Combine with C-4.**

---

### C-4 — Write `RUN.md` — **level B**

**Files:** new `RUN.md` at the repository root.

Contents specified in full in §E.

**Why level B, not A.** The application runs today with the commands already in
the README; `RUN.md` makes that path reliable and complete rather than possible.
It is the requested deliverable of this task and the single highest-value item for
"another developer can use this", but strictly it documents a working system
rather than fixing a broken one.

**If we do not do it.** The prerequisites (git, Node version, uv) stay
undiscoverable, and the two settings that actually bite on a first run —
`ANTHROPIC_API_KEY` and `CODEONBOARD_COOKIE_SECURE=0` — are buried in a 60-line
commented `.env.example`. A new developer gets there eventually, by trial.

**Verification.** Follow it literally in a fresh clone (the §F acceptance test).
Any step that needs a correction is a bug in `RUN.md`.

**Effort:** small–medium — ~45 minutes of writing, then one acceptance pass.
**Combine with C-3.**

---

### C-5 — Clean up `.env.example` — **level B**

**Files:** `.env.example`.

**What changes.**
1. Delete `GITHUB_TOKEN=` — nothing reads it. (If it is kept for a future
   rate-limit feature, it must be labelled "not currently used".)
2. Put a short **required** block at the top: `ANTHROPIC_API_KEY=` with one line
   saying where to get one and that the backend refuses to start without it.
3. Keep `CODEONBOARD_COOKIE_SECURE=0` where it is, and add one sentence saying
   this is what a local http run needs — it is already explained, but the
   explanation is six lines long and the actionable part should lead.
4. Leave the Google, production and `API_ORIGIN` blocks exactly as they are. They
   are already correct and already commented out.

**If we do not do it.** The first required-looking variable in the setup file is
one the project never reads, so a new user goes and creates a GitHub token for
nothing. Everything still works.

**Verification.** `grep -rn GITHUB_TOKEN` returns nothing outside history and
docs. `cp .env.example .env`, add a key, boot the backend, register, reach the
dashboard.

**Effort:** trivial — ~10 minutes. **Combine with C-6 and C-7.**

---

### C-6 — Add a `LICENSE` file — **level B**

**Files:** new `LICENSE`.

**What changes.** MIT is the conventional choice for a student project meant to be
cloned and read. **This is the author's decision, not mine to make** — the plan
records that it must be made before publishing.

**If we do not do it.** Legally the repository is all-rights-reserved: nobody may
copy, modify or redistribute it, which contradicts publishing it as open source.
GitHub shows no licence badge, and other developers are advised not to use it.

**Verification.** GitHub shows the licence on the repository page.

**Effort:** trivial — one file. **Combine with C-5 and C-7.**

---

### C-7 — `.gitignore` and machine-specific tracked configuration — **level B**

**Files:** `.gitignore`, `.claude/launch.json`, `frontend/tsconfig.json`,
`run-dev.bat`.

**What changes.**
- `.gitignore`: add `data/sessions.db.*`, `.ui-audit-fe/`,
  `frontend/public/probe.txt`, `/.next-*/`. These currently live in
  `.git/info/exclude`, which is not published.
- `.claude/launch.json`: reduce to the configurations that work on a fresh clone —
  `backend` and `frontend`. Everything referencing `.ui-audit-fe`,
  `scripts.ux_fixture_app` (which C-2 leaves untracked), or a port other than
  8000/3000 goes.
- `frontend/tsconfig.json`: drop the `.next-3105/types/**/*.ts` and
  `.next-3107/types/**/*.ts` `include` entries. Harmless but machine-specific.
- `run-dev.bat`: drop the two forced development flags
  (`CODEONBOARD_CURRICULUM=1`, `CODEONBOARD_GAPS=1`) so it launches the shipped
  defaults, and refresh the stale comment claiming gaps are not shown to the
  learner. See §E on why no *new* launcher is proposed.

**If we do not do it.** The repository ships configuration pointing at directories
and modules it does not contain, and a tracked convenience script silently changes
product behaviour for anyone who uses it — the one genuinely misleading item in
this group. Nothing breaks.

**Verification.** `git status --porcelain` in a fresh clone after a full local run
shows no untracked runtime artifacts. `npm run build` still succeeds after the
tsconfig edit.

**Effort:** small — ~20 minutes. **Combine with C-5 and C-6.**

---

### C-8 — `engines` in `frontend/package.json` — **level C**

**Files:** `frontend/package.json`. Add `"engines": { "node": ">=18.18" }`.

**Why level C.** `RUN.md` documents the requirement; this makes npm enforce it,
turning a confusing build error into a clear one. Genuinely optional.

**If we do not do it.** Someone on Node 16 gets an obscure Next build failure
instead of a version warning. Rare, and `RUN.md` already covers it.

**Effort:** trivial — one line. Do it only if C-3/C-4 are already open.

---

## D. Public-repository hygiene

**Nothing is deleted as part of this planning task.** This is the checklist for
the cleanup step, which is a separate authorization.

### Verified clean — no action

| Item | Finding |
|---|---|
| `.env` in history | never tracked (`git log --all -- .env` empty) |
| databases in history | never tracked (`git log --all -- "*.db"` empty) |
| secret-shaped strings, tracked tree | none (`git grep` for `sk-ant-`, `ghp_`, `github_pat_`, `AKIA`, PEM headers) |
| secret-shaped strings, full history | none (same patterns over `git log --all -p`) |
| absolute / Windows paths in code | none |
| repository size | 10.7 MB tracked, 25 MB `.git` — no rewrite needed |

**No history rewrite (`filter-repo`, BFG) is required.** Do not do one.

### Must not be committed — confirm still ignored before publishing

- `.env` — ignored (`.gitignore:1`). Contains a live Anthropic key. **Never commit.**
- `data/sessions.db` (17 MB) — real learning sessions, real accounts, real
  argon2 password hashes. Ignored by `data/*.db`.
- `data/sessions-fixtures.db`, `data/ux-fixture.db`,
  `data/sessions.pre-multiuser-*.db`, `data/sessions.pre-usertest.db`,
  `data/sessions.learner-test.db`, `data/smoke_*.db` — ignored by `data/*.db`.
- `data/sessions.db.post-f2`, `data/sessions.db.uibaseline-backup` — **ignored
  only by `.git/info/exclude`**. Add `data/sessions.db.*` to `.gitignore` (C-7).
- `data/repos/` — five cloned upstream repositories, including a personal one
  (`shirazakov/`). Ignored.
- `data/quarantine/`, `_tmp_compare/`, `.ui-audit-fe/`, `.venv/`,
  `.pytest_cache/`, `.idea/`, `node_modules/` (root and frontend),
  `frontend/.next/`, `frontend/.next-3105/`, `frontend/.next-3107/`,
  `frontend/next-env.d.ts`, `frontend/tsconfig.tsbuildinfo`,
  `frontend/public/probe.txt`, all `__pycache__/` — ignored, except the last two
  categories partly relying on `.git/info/exclude`.

### Research material — keep, subject to an explicit criterion

`data/experiments/*.json` (25 files, 1.5 MB) and
`docs/planning/phases/evidence/**` (74 files) stay, **provided all five of the
following hold**. This is the criterion, stated so it can be re-checked rather
than assumed:

1. **No secrets.** Checked: `git grep` for API-key, token and private-key patterns
   over the tracked tree returns nothing. The `api_key` string matches inside the
   experiment JSON are `fastapi/security/api_key.py` — a path *inside the
   repository being analysed*, not a credential.
2. **No personal data.** The content is model output about public repositories
   (`psf/requests`, `fastapi/fastapi`, `aimacode/*`). Learner answers from real
   sessions live in `data/sessions.db`, which is gitignored and stays so.
3. **No machine-specific artifacts.** No absolute paths, no local hostnames, no
   developer environment details. Verified by the §A.13 search.
4. **Reasonable in size.** 1.5 MB + the evidence tree, against a 10.7 MB tracked
   total. The largest single tracked file is the 1.2 MB poster PNG, which is a
   submission artifact.
5. **Academically load-bearing.** Each file is the recorded result behind a
   number claimed in a phase document — grader-agreement gates, cost
   measurements, acceptance runs. Anything that is *not* — a stray probe output,
   a superseded run kept "just in case" — fails this criterion and should be
   dropped during the separate cleanup pass.

Point 5 is the one that needs a human pass. Items 1–4 are verified.

### Decide before publishing — presentation, not risk

- `frontend/README.md` — untouched `create-next-app` boilerplate. Replace with
  three lines, or delete and let the root `README.md` and `RUN.md` carry it.
- `frontend/CLAUDE.md`, `frontend/AGENTS.md`, root `CLAUDE.md` (25 KB) — AI-agent
  instruction files. Publishing them is fine and increasingly common; it is a
  choice about how the repository presents itself, not a hygiene problem.
- `scripts/` (26 tracked files) — research instruments. Several read gitignored
  fixture databases and will not run on a clone. Keeping them is honest for a
  research project; `RUN.md` must simply not reference them.
- `tests/test_gap_understanding.py:303` — a compatibility gate that skips with
  `reason="no local sessions.db"`. On a fresh clone it skips cleanly. **Correct
  behaviour, leave it**; the docstring already explains why it skips rather than
  silently passing.
- `tests/test_repo_identity.py:104` — a personal repository URL used as a test
  fixture. Harmless; noted so it is a decision rather than an oversight.

---

## E. `RUN.md` plan

A single root-level file. Purely operational — no architecture, no roadmap, no
design rationale. Those live in `README.md`, `CLAUDE.md` and `docs/`. Target
length: one screen of prose plus commands, roughly 100 lines.

### Section-by-section

**1. What you get**
Two sentences. A local web app: a Python API on `:8000`, a Next.js UI on `:3000`,
one SQLite file, and Claude reached with your own API key. Nothing is hosted;
nothing phones home except the Anthropic API and `git clone` of the public
repository you ask it to teach you.

**2. Prerequisites**

| | Version | Check |
|---|---|---|
| Python | 3.11+ | `python --version` |
| uv | any recent | `uv --version` — install from https://docs.astral.sh/uv/ |
| Node.js | 18.18+ | `node --version` |
| git | any | `git --version` — the backend shells out to it to clone repositories |

Plus: an Anthropic API key from https://console.anthropic.com/, and enough credit
to plan a session (see §9 on cost).

**3. Setup — four commands**

```bash
git clone <repo-url> && cd CodeOnboard
uv sync
cp .env.example .env       # then open it and paste your key
cd frontend && npm install && cd ..
```

**4. Environment**

Only one variable is required:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Plus one that `.env.example` already sets and that you should leave alone for a
local run:

```
CODEONBOARD_COOKIE_SECURE=0
```

with one sentence: the default is `1` (https-only cookies), which is right for a
deployment and wrong for `http://localhost`. Everything else in `.env.example` is
commented out and optional — say so explicitly, so the reader does not go hunting.

**5. Database**

Three sentences, and they should be reassuring:

> There is no database step. On first use the app creates `data/sessions.db`
> itself, with an empty schema. Nothing is seeded, no migration is needed, and
> deleting that file resets the installation to brand new.

**6. Running it — two terminals**

```bash
# terminal 1 — backend
uv run uvicorn backend.api:app --reload
```

```bash
# terminal 2 — frontend
cd frontend && npm run dev
```

Then open **http://localhost:3000**.

Note that the frontend proxies `/api/*` to the backend, so `:3000` is the only URL
you need; `:8000` is there for `curl` and `/docs`.

**7. Verifying it works**

1. `curl http://localhost:8000/health` → `{"status":"ok"}`
2. Open http://localhost:3000 — you should land on **Sign in**.
3. Create an account (any email; nothing is emailed, nothing is verified).
4. You land on the dashboard, which says you have no sessions yet. **An empty
   dashboard with no error is the success signal.**
5. `Start a new session`, paste `https://github.com/psf/requests`, answer the
   interview. This is the point at which the app first calls Claude and first
   clones a repository — planning takes a few minutes and runs in the background,
   so the card shows `generating` and you may close the tab.

**8. Common first-run problems**

| Symptom | Cause | Fix |
|---|---|---|
| Backend exits with `Refusing to start: ANTHROPIC_API_KEY is not set` | no `.env`, or the key line is empty | `cp .env.example .env`, paste the key |
| `sh: next: command not found` | `npm install` not run | `cd frontend && npm install` |
| The UI loads but every call fails | backend not running, or started on a port other than 8000 | start it, or set `API_ORIGIN` |
| Signed in, then immediately signed out again | `CODEONBOARD_COOKIE_SECURE` left at `1` over http | set it to `0` in `.env` |
| `Port 3000 is in use` | something else has it | `npm run dev -- --port 3100`, and set `API_ORIGIN` accordingly |
| Repository URL rejected | only public `github.com` repositories are accepted (`cloner.ALLOWED_HOSTS`) | use a public GitHub URL |
| "Sign in with Google" missing | `GOOGLE_CLIENT_ID`/`SECRET` unset | expected — the button hides itself; email sign-in is the normal path |

**9. Cost** — one short paragraph, because a user supplying their own key deserves
to know before they click. The project targets under $0.10 per planning run
(`CLAUDE.md`); lessons and grading are Haiku, the planner is one Sonnet call.

**10. Starting over** — stop both servers, delete `data/sessions.db`, restart.

### Should there be a one-command launcher?

**Confirmed recommendation: no new launcher.** `RUN.md` plus the project's
existing standard commands is sufficient, and further inspection did not turn up
anything that changes this.

The case against: the setup is already two commands in two terminals, and a
cross-platform launcher that supervises two processes, forwards signals, and
reports which one died is meaningfully more code than the problem justifies. A
shell script that only works on macOS/Linux while the author develops on Windows
is worse than nothing — it will rot untested.

The narrower thing that *is* worth doing is C-7's cleanup of the existing
`run-dev.bat`: drop the two forced development flags so it launches the shipped
defaults, refresh the stale comment, and have `RUN.md` mention it as an optional
Windows convenience — with the two manual commands as the canonical documented
path. That costs nothing new, and it stops a tracked script from silently changing
the product's behaviour.

---

## F. Acceptance test

Manual, in a **completely new directory**, on a machine that has never run this
project — or with `data/` renamed aside if that is not available.

### Setup

```bash
cd /some/empty/place
git clone <repo-url> codeonboard-acceptance
cd codeonboard-acceptance
```

**Gate 0 — the clone is clean and complete.** Before anything else:

```bash
ls data/                                   # expect: experiments/ only. No .db file of any kind.
ls .env                                    # expect: No such file
git ls-files | grep -E "\.db$|^\.env$"     # expect: no output
uv run python -c "import backend.api"      # expect: no output
```

*Proves: no development database and no credential ships with the repository, and
no tracked file references an untracked one.*

**Already verified against `3dc579e`**, by cloning the branch into a temp
directory: `data/` held only `experiments/`, `.env` was absent, `git ls-files`
matched no `.db` or `.env`, and `import backend.api` printed `IMPORT OK`. Gate 0
passes today. Re-run it anyway on the published branch — it is cheap, and it is
the check that would have caught the `reset.py` blocker.

### Steps

| # | Action | Expected | Proves |
|---|---|---|---|
| 1 | `uv sync` | resolves and installs; no ChromaDB, no torch, no sentence-transformers | dependencies match the documented stack |
| 2 | `cd frontend && npm install && cd ..` | completes | frontend deps are declared |
| 3 | `uv run uvicorn backend.api:app` **with no `.env`** | exits with `Refusing to start: ANTHROPIC_API_KEY is not set — every lesson, grade and plan needs it.` | **the key is required and the failure is legible** |
| 4 | `cp .env.example .env`, paste a real key | — | configuration is one file, one value |
| 5 | `uv run uvicorn backend.api:app --reload` | starts; `Uvicorn running on http://127.0.0.1:8000` | **the user's own key is read** |
| 6 | `ls data/` | `sessions.db` now exists | **a fresh DB is created automatically** |
| 7 | `curl localhost:8000/health` | `{"status":"ok"}` | the backend serves |
| 8 | terminal 2: `cd frontend && npm run dev` | `ready on http://localhost:3000` | **the frontend starts** |
| 9 | open http://localhost:3000 | redirected to the **Sign in** page | **the UI loads; no prior session assumed** |
| 10 | click `Forgot password?` on the sign-in form | the reset page renders (not a 404) | the frontend pages are tracked (`3dc579e`) |
| 11 | `Create an account`, register a new email | lands on the dashboard | **a new user can begin** |
| 12 | read the dashboard carefully | greeting, `Start a new session`, and the empty-state card. **No red error line.** | **C-1 landed** |
| 13 | toggle `Show archived` | still empty, still no error | the empty path is empty in both modes |
| 14 | `Start a new session`, `https://github.com/psf/requests`, complete the interview | card appears as `generating`, then becomes a real session | **the full loop works on a fresh install** |
| 15 | `sqlite3 data/sessions.db "select email from users"` | **exactly the one address registered in step 11** | **no development data is present** |
| 16 | `sqlite3 data/sessions.db "select count(*) from sessions"` | `1` | ditto |
| 17 | `git status --porcelain` | no output — `data/sessions.db*` and `data/repos/` are both ignored | **no runtime artifact would be committed** |

### Regression gate (automated, run before the manual pass)

```bash
uv run pytest tests/
cd frontend && npm test
```

Both green, from the fresh clone, with no `data/sessions.db` present.
`tests/test_gap_understanding.py::test_every_stored_gap_free_node_derives_its_stored_state`
is **expected to skip** with `no local sessions.db` — that is correct behaviour,
not a failure.

### Cleanup

Delete the acceptance directory. Note that step 14 spends real API credit (under
$0.10) and clones a repository into `data/repos/`.

---

## G. Scope check

### A — Runtime blockers (must fix, or the app does not work from a fresh clone)

1. **C-1** — initialize both schemas at startup. Reproduced against a real clone
   of `3dc579e`: register → `201`, then `GET /sessions` →
   `OperationalError: no such table: sessions`.

**One item.** The second level-A item in the first draft — tracking
`backend/auth/reset.py` and the two password pages — was resolved by commit
`3dc579e` and verified by clone.

### B — Required for public GitHub release

2. **C-2 (what remains)** — track
   `frontend/components/lesson/CompletionScreen.test.tsx` and
   `frontend/components/lesson/LessonBrief.test.tsx`; leave the two
   `scripts/ux_fixture*` files untracked and remove the launch configurations that
   reference them; track this plan document.
3. **C-3** — correct `README.md`'s stack section (absorbs B-6, prerequisites).
4. **C-4** — write `RUN.md`.
5. **C-5** — `.env.example`: drop the unread `GITHUB_TOKEN`, lead with the one
   required variable.
6. **C-6** — add a `LICENSE`.
7. **C-7** — `.gitignore` patterns from `.git/info/exclude`; trim
   `.claude/launch.json`, `frontend/tsconfig.json`, and `run-dev.bat`'s forced
   flags.
8. **Human pass** over `data/experiments/` and `docs/planning/phases/evidence/`
   against criterion 5 in §D (points 1–4 already verified).

**Six implementation items plus one review pass** — collapsing to **two commits**,
since C-3+C-4 are one documentation pass and C-2+C-5+C-6+C-7 are one configuration
pass.

### C — Nice to have

10. **C-8** — `"engines": { "node": ">=18.18" }` in `frontend/package.json`.

**One item.** Deliberately the whole category.

### Explicitly not required for this release

- **Any history rewrite.** Verified clean: no `.env`, no database, no
  secret-shaped string has ever been committed.
- **Any persistence-layer redesign.** Lazy `IF NOT EXISTS` creation already works;
  C-1 only moves *when* it happens, not *how*.
- **Making the database path absolute or configurable.** `Path("data/sessions.db")`
  relative to the repository root is correct for a `cd`-into-the-repo workflow,
  which is what `RUN.md` documents.
- **A cross-platform one-command launcher.** Confirmed in §E.
- **`Dockerfile` / `docker-compose`.** Would add a toolchain prerequisite to
  remove two, and hides the local-first model the project is demonstrating.
- **Removing `.claude/`, `CLAUDE.md`, `AGENTS.md` or `scripts/`.** Presentation
  choices, not blockers.
- **Deleting `data/experiments/` or the evidence directories** wholesale. They pass
  the §D criterion; only individual files that fail point 5 should go.
- **CI, deployment, Postgres, HTTPS, monitoring, secrets management, OAuth
  redesign, email verification, rate-limit tuning, broader security hardening.**
  Out of scope, and **none is needed for a fresh clone to work.** The production
  guard rails that already exist (`auth/config.enforce()`, the undeclared-route
  middleware, the ownership chokepoint) behave correctly in development and need
  no change.
- **Fixing `tests/test_gap_understanding.py`'s live-database skip.** It skips
  loudly and for a documented reason. Correct as it stands.

---

## H. Proposed implementation sequence

Three phases, **three commits**. Nothing here is implemented yet.

### Phase 0 — Re-run the audit (5 minutes, no changes)

The untracked set changed once during planning. Before touching anything:

```bash
git status --porcelain --untracked-files=all | grep '^??'
```

Expect exactly: the two `frontend/components/lesson/*.test.tsx` files, the two
`scripts/ux_fixture*` files, and this plan document. **Anything else is a new
finding and must be classified against §C-2's five categories before it is
committed or ignored.**

### Phase 1 — Fix the actual fresh-clone runtime blocker

**Commit 1 — "fix: a fresh installation has its tables before it serves anyone"**
- `backend/api.py` (`_lifespan`): call `learning_store.init_db(SESSIONS_DB_PATH)`
  then `auth_schema.init_auth_schema(SESSIONS_DB_PATH)` before the housekeeping
  sweeps.
- New `tests/test_first_run.py`: register → `GET /sessions` → `200 []` against a
  `tmp_path` database; plus a double-boot idempotence case.
- Run `uv run pytest tests/`.

*The first draft's Commit 2 — tracking `backend/auth/reset.py` and the two
password pages — is no longer needed. Commit `3dc579e` did it, and a clone of the
branch imports cleanly.*

*Gate: after Phase 1, a clone of this branch imports, starts, and shows a clean
empty dashboard to a newly registered user.*

### Phase 2 — Make the repository safe and clear for public GitHub

**Commit 2 — "docs: a setup path that matches the project that exists"**
- New `RUN.md`, per §E.
- `README.md`: correct the Tech Stack (Python 3.11+; delete ChromaDB,
  sentence-transformers, nomic-embed, "Vector Store (RAG)"); replace the Setup
  section with a pointer to `RUN.md`; add Prerequisites; add a Licence section.
- Optionally replace `frontend/README.md`'s create-next-app boilerplate.
- `git add docs/open-source-readiness-plan.md` (this file).

**Commit 3 — "chore: configuration that a stranger's machine can use"**
- `.env.example`: delete `GITHUB_TOKEN`; lead with the required
  `ANTHROPIC_API_KEY` block; one actionable line on `CODEONBOARD_COOKIE_SECURE=0`.
- New `LICENSE` (author picks; MIT recommended).
- `.gitignore`: add `data/sessions.db.*`, `.ui-audit-fe/`,
  `frontend/public/probe.txt`, `/.next-*/`.
- `.claude/launch.json`: keep only `backend` and `frontend`; delete the
  `-3001`/`-3007`/`-3100`/`-3105`/`-3107`/`uiaudit` entries.
- `frontend/tsconfig.json`: drop the `.next-3105` and `.next-3107` include globs.
- `run-dev.bat`: drop the two forced flags; refresh the stale gap comment.
- `git add` exactly these two test files, and nothing else:
  `frontend/components/lesson/CompletionScreen.test.tsx`,
  `frontend/components/lesson/LessonBrief.test.tsx`.
  (`tests/test_password_reset.py` is already tracked as of `3dc579e`.)
  **No `git add -A`.**
- Optional (level C): `"engines": { "node": ">=18.18" }` in
  `frontend/package.json`.
- Leave `scripts/seed_ux_fixture.py` and `scripts/ux_fixture_app.py` untracked.

**Separate review pass (not a commit)** — walk `data/experiments/` and
`docs/planning/phases/evidence/` against criterion 5 in §D and drop anything that
backs no published claim. This is the author's call, not a mechanical step.

*Gate: `git status --porcelain` is clean apart from ignored runtime artifacts, and
nothing tracked references anything untracked.*

### Phase 3 — Run the fresh-clone acceptance test

- Clone into a new directory. Run **Gate 0** and all 17 steps of §F.
- Run the automated regression gate (`pytest tests/`, `npm test`) *before* the
  manual pass.
- Any step needing an undocumented correction is a bug in `RUN.md` — fix `RUN.md`,
  do not fix it in your head.
- Delete the acceptance directory afterwards. Step 14 spends real API credit.

---

## Appendix: probes run for this audit

Read-only, in a temp directory. `data/sessions.db` was never opened for writing,
and nothing in the repository was modified.

1. **Fresh-install first run.** Imported `backend.api`, repointed
   `SESSIONS_DB_PATH` at a temp path, drove `TestClient` through `/health` →
   `/auth/me` → `/auth/register` → `/sessions`. Produced the
   `no such table: sessions` failure in §B-1, and the table listing showing the
   account layer alone.
2. **Restart on a partially-initialized database.** Booted the app a second time
   against the database left by probe 1. Startup succeeded — confirming
   `run_startup_checks` is already tolerant, and narrowing the defect to the read
   path.
3. **History secret scan.** `git log --all` for `.env` and `*.db`; `git grep` and
   `git log --all -p` for `sk-ant-`, `ghp_`, `github_pat_`, `AKIA`, and PEM
   private-key headers. All clean.
4. **Ignore-source attribution.** `git check-ignore -v` on every local artifact in
   `data/` and the repository root, which surfaced the four patterns living only
   in `.git/info/exclude`.
5. **Tracked-vs-on-disk source diff.** `comm -23` between `find` and
   `git ls-files` over `backend/`, `frontend/{app,components,lib,test}`, `tests/`
   and `scripts/`, cross-checked against
   `git status --porcelain --untracked-files=all`. Both methods return the same
   nine paths, which is what makes the §C-2 audit exhaustive rather than sampled.
6. **Reference search for each untracked file.** `grep` across the tracked tree
   for each candidate's import path, route path and module name — this is what
   established that `reset.py` was imported by `routes.py:44`, that the two
   password pages are named by `AuthForm.tsx:141` and `lib/auth.tsx:53–54`, and
   that the two `ux_fixture` scripts are referenced only by
   `.claude/launch.json:270`.
7. **Clone-and-import, against `3dc579e`.** `git clone --no-hardlinks` of the
   branch into a temp directory, then `ls data/`, `ls .env`,
   `git ls-files | grep -E "\.db$|^\.env$"`, and
   `import backend.api`. Result: `experiments` only, no `.env`, no matches,
   `IMPORT OK`. This is Gate 0 of §F, run early.
8. **The §B-1 bug, re-confirmed on that clone.** Same `TestClient` drive against
   the cloned tree: `register: 201`, then
   `sessions RAISED: OperationalError no such table: sessions`. Commit `3dc579e`
   did not touch `backend/learning/store.py`, and the defect is unchanged.
