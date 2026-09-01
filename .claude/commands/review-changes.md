---
description: Review the current changes against CodeOnboard's invariants by dispatching the specialist reviewers that the diff actually touches.
argument-hint: "[optional: a git ref to diff against, default HEAD]"
---

# Review the current changes

Generic code review is not what this repository needs — it needs a check against
the 26 invariants where **the wrong change compiles, passes an eyeball review, and
quietly makes the product lie**. Those invariants split cleanly across four
subsystems, so route the diff rather than reading everything with everything
loaded.

## 1. See what changed

```bash
git diff --stat ${1:-HEAD}
```

```bash
git status --porcelain
```

Include uncommitted work. If the diff is empty against `HEAD`, diff against the
merge base with `master` instead.

## 2. Dispatch the reviewers the diff touches — in parallel, in one message

| Paths in the diff | Reviewer |
|---|---|
| `backend/learning/**`, `backend/agents/mentor/mutator.py`, endpoints that grade / advance / waive / override / reset | **learning-engine-reviewer** |
| `backend/agents/**`, `backend/pipeline/**`, `backend/repo/{explore,investigation,survey,anchors,tools}.py`, any prompt text | **ai-pipeline-reviewer** |
| `frontend/**` | **frontend-flow-reviewer** |
| `backend/learning/store.py`, `backend/learning/reset.py`, `backend/auth/**`, `backend/migrations/**`, any route's auth declaration | **session-data-reviewer** |

Give each one the file list it owns, the diff for those files, and the task the
change was meant to accomplish. Send them in a single message so they run
concurrently.

A file may match two rows — `backend/api.py` routinely matches three. Send it to
each; they check different things and their overlap is small.

If the diff touches only `docs/`, `README.md` or `.claude/`, dispatch nothing:
check it against the `sync-documentation` skill instead, and verify that every
command, path and symbol it names resolves.

## 3. Ask the historian when a finding is a design question

If a reviewer flags something that looks deliberate, or the change contradicts a
rule for a reason that might be good, ask the **architecture-historian** whether
the record already settles it. Several rules here look wrong until you read the
defect that produced them.

## 4. Consolidate

Merge the verdicts into one list, most severe first. For each finding: the
invariant by number, `file.py:line`, **the concrete way the product would lie or
lose data**, and the severity the reviewer gave it.

Then de-duplicate — two reviewers reporting the same seam from opposite sides is
one finding, and say that it was seen from both.

## 5. Verify, do not assume

Run the suites the change needs, via the `verify-change` skill, and report the
real numbers. Remember the one backend test that fails by design on a used
database; do not report it as a regression.

If the change is visual, say so and recommend `verify-in-browser` — no reviewer
can approve a layout change from source.

## 6. Report

- A one-line verdict: clean, or the count of blocking findings.
- The consolidated list.
- What was **not** checked: anything visual that was not opened, any prompt change
  no harness has measured, any suite that was not run.

**Report only. Do not fix anything, and do not commit or push.** Ask before acting
on a finding.
