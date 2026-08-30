# `data/` — local state

Everything in this directory is **generated at runtime and gitignored**. This
README is the only tracked file here; the directory itself is created by the app
on first use if it does not exist.

> Data model: [docs/architecture/persistence.md](../docs/architecture/persistence.md)

---

## What appears here

| Path | What it is | Safe to delete? |
|---|---|---|
| `sessions.db` | **Everything the app knows**: accounts, sessions, learning graphs, plan snapshots, dossiers, survey caches | Yes — it resets the installation to brand new. Nothing else is lost, and nothing is recoverable |
| `sessions.db-wal`, `sessions.db-shm` | SQLite's write-ahead-log sidecars. The store runs in WAL mode | Only with the servers stopped, and only alongside the database itself |
| `repos/<owner>/<name>/` | Shallow (`--depth 1`) checkouts of the repositories being taught | Yes — they are re-cloned on demand. Costs a clone, nothing else |
| `sessions-fixtures.db`, `ux-fixture.db` | Throwaway databases used by the measurement and UI-fixture scripts | Yes, if you did not create them on purpose |
| `experiments/` | Output from the archived migration harnesses | Yes |

**There is no database setup step.** `run_startup_checks` creates the schema
before the process serves anything, and every statement is idempotent. To reset:
stop both servers, delete `sessions.db`, start again.

---

## One directory per repository *owner*

Checkouts are keyed `data/repos/<owner>/<name>`, lower-cased, from the same
identity function the `repositories` table and the survey cache use.

This used to be keyed on the URL's last path segment alone, and the owner was
thrown away — so `psf/requests` and `kennethreitz/requests` shared one directory
while the correctly-keyed survey cache described a repository that was not there.
With one user it never fired; with many it is a cross-tenant leak that needs no
attacker. `scripts/migrate_repo_layout.py` moves an old layout across.

---

## Backups

There is no backup mechanism, and `sessions.db` holds every learner's work.
`.gitignore` deliberately covers `data/sessions.db.*` as well, so a hand-made copy
kept beside it — `sessions.db.2026-08-30-backup` — stays out of git rather than
being committed by a wildcard.
