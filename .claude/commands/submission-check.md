---
description: Pre-submission check — the repository is complete, honest and runnable from a fresh clone. Reports; changes nothing.
---

# Submission check

CodeOnboard is a final-year project handed over as a repository someone else will
clone, read and run. This checks that it is **complete, honest and runnable**.

**Report only. Do not fix anything, do not commit, do not push.** Produce a list of
findings with file references, each marked `blocking` / `worth fixing` / `note`,
and ask before changing anything.

---

## 1. Both suites, from the repository root

```bash
uv run pytest tests/
```

```bash
cd frontend && npm test && npm run build
```

Expect 1801 passed / 1 skipped / **1 failed** (the known
`test_every_stored_gap_free_node_derives_its_stored_state` gate — see
`docs/testing.md` §5) and 50 frontend files passing plus a clean build. Anything
else is `blocking`. Report the real numbers, not "green".

## 2. Nothing private or generated is staged

```bash
git status --porcelain
```

```bash
git ls-files --error-unmatch .env 2>/dev/null && echo "BLOCKING: .env is tracked"
```

`.env`, `data/*.db`, `data/repos/`, `.venv/`, `node_modules/`, `.next/` and
`.ui-audit-fe/` must all be ignored. Scan the diff for an API key, a token or a
password that is not obviously a placeholder — `blocking` if found, and say the key
must be rotated rather than just removed.

## 3. A stranger's fresh clone would work

- `.env.example` exists, carries every variable the app reads, and ships
  `CODEONBOARD_COOKIE_SECURE=0` for a localhost run.
- No setup step depends on something only on this machine — an absolute path, a
  seeded database, a cloned fixture repository.
- `README.md`'s install and run commands are the ones that actually work. Check
  them against `pyproject.toml`, `frontend/package.json`, `run-dev.bat` and
  `.claude/launch.json` rather than trusting the prose.

## 4. Documentation still describes the system that exists

Sample rather than re-read everything, and check the things that rot:

- Every command, path, port and environment variable named in `README.md`,
  `CLAUDE.md`, `docs/testing.md` and `docs/configuration.md` resolves.
- Counts that are stated as facts (test totals, route counts, file counts) match
  what the suites just printed. A drifted count is `note`, not `blocking` — but say
  the real number.
- Internal links resolve:

```bash
grep -rhoE "\]\(([^)#]+\.md)" README.md CLAUDE.md docs backend frontend tests scripts --include=*.md | sed 's/](//' | sort -u
```

- `docs/planning/` and `project-archive/` are still framed as design records and
  superseded history, not as current behaviour.

## 5. Claimed behaviour is behaviour that exists

Spot-check the claims a reader would most reasonably test:

- The invariants in `docs/architecture/decisions.md` still hold in code — in
  particular D16 (`save_graph` writes no plan table), D20 (`load_graph` requires a
  `user_id`) and D9 (`understanding_of()` is the single owner). The structural
  tests in `tests/` cover these; confirm they ran rather than re-deriving them.
- `README.md`'s "deliberately not built" list is still accurate.
- Anything described as measured has its evidence committed under
  `docs/planning/phases/evidence/`.

## 6. Repository hygiene

- No stray scratch files, `_tmp_*` directories, or debug prints in `backend/` or
  `frontend/`.
- `git log` reads as a coherent history: `type: sentence` subjects, no
  "wip"/"fix2"/"asdf".
- The working tree is clean or its remaining changes are intentional and named.

---

Finish with a short verdict: **ready to submit**, or the shortest list of blocking
items and what each one needs. Do not act on that list without being asked.
