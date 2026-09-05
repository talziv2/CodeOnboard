"""The CodeOnboard MCP server — a small live bridge, not a subsystem.

    uv run python -m backend.mcp_server        (stdio; Claude Code spawns it)

## What this is for

CodeOnboard owns the investigation, the required knowledge, the teaching, the
grading and the readiness gate. It does not own editing, executing or opening a
pull request — `data/repos/<owner>/<name>` is ONE shared, pinned checkout that
the grounding oracle reads, so a writable per-learner tree is a thing this system
must not have where it keeps the repository.

So the learner's coding agent owns the working tree, and this server answers the
two questions that agent cannot answer for itself:

    get_contribution_context()      what CodeOnboard learned for THIS task, and
                                    what THIS learner demonstrated
    check_scope(changed_files)      are the files you are changing inside the
                                    boundary CodeOnboard taught?

`check_scope` is the reason this is MCP rather than a file. Context could travel
as a document; "is what I am doing right now still in scope" is a live question
about a working tree that changes under the agent's hands, and only a call can
answer it. **One real runtime capability. There is no third tool** — and in
particular no `report_outcome`, because nothing here writes.

## THIS SERVER IS READ-ONLY, AND THAT IS LOAD-BEARING

It opens the database read-only, never clones, never writes a row, and returns no
verdict that becomes state. A coding agent's success is not evidence about a
learner (D8, and the same rule that makes a Tutor conversation not evidence), so
there is nothing here that could move `understanding_state`, close a gap, or
change readiness. `check_scope` is the boundary a model's output crosses before
CodeOnboard makes any claim about it (DI-6): the agent reports paths, *our*
deterministic code decides scope.

## Identity comes from the environment, not from the model

`CODEONBOARD_SESSION` and `CODEONBOARD_USER` are read from the process
environment exactly as `api.py` reads them from a cookie, and handed to
`store.load_graph`, whose `user_id` argument **is** the security model. Neither
tool takes a `session_id`, so there is no id for a model to mistype or guess, and
a mismatch makes `load_graph` return `None` — answered here as *"session not
found"*: 404, never 403 (D20).
"""
from __future__ import annotations

import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from backend.learning import contribution as contribution_model
from backend.learning import handoff
from backend.learning import store as learning_store
from backend.repo import dossier_store, investigation as investigation_module
from backend.repo import survey_store
from backend.repo.cloner import get_commit_sha, parse_repo_url, repo_dir

#: The repository root, so the server works whatever directory it is spawned in.
#: `cloner.REPOS_DIR` and the default database path are both relative.
ROOT = Path(__file__).resolve().parents[1]

server = MCPServer(
    name="codeonboard",
    version="1.0.0",
    instructions=(
        "CodeOnboard prepared this contribution: it investigated the repository "
        "for this specific task, taught the developer what the change depends "
        "on, and verified they can make those claims. THE DEVELOPER IS THE "
        "IMPLEMENTER. Call get_contribution_context first and verify the commit. "
        "Use the edge cases as questions to ask them, not as a specification to "
        "satisfy. Call check_scope before you finish."
    ),
)


# ── environment ───────────────────────────────────────────────────────────────


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _db_path() -> Path:
    return _resolve(os.environ.get("CODEONBOARD_DB", "data/sessions.db"))


def _session():
    """The graph this server was started for, or a refusal.

    `load_graph` takes the owner as a required argument and answers `None` for a
    session that is not theirs — identical to one that does not exist. That is
    the ownership boundary, used rather than reimplemented.
    """
    session_id = os.environ.get("CODEONBOARD_SESSION", "").strip()
    user_id = os.environ.get("CODEONBOARD_USER", "").strip()
    if not session_id or not user_id:
        raise ValueError(
            "This server was started without a session. Set CODEONBOARD_SESSION "
            "and CODEONBOARD_USER in the server's env in .mcp.json."
        )
    graph = learning_store.load_graph(session_id, user_id, _db_path())
    if graph is None:
        raise ValueError("session not found")
    return graph


def _commit(graph) -> str:
    """The revision the investigation was written against. NEVER clones.

    Read-only by construction: `repo_dir` is pure and `get_commit_sha` reads
    `HEAD`. If the checkout is absent there is no revision to pin the payload to,
    and refusing beats emitting anchors with nothing to resolve them against.
    """
    path = repo_dir(graph.repo_url)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        raise ValueError(
            f"no local checkout of {graph.repo_url} — CodeOnboard cannot pin the "
            "revision this context is true at"
        )
    return get_commit_sha(str(path))


def _dossier(graph, commit: str) -> dict | None:
    stored = dossier_store.load_investigation(
        graph.session_id, commit, db_path=_db_path()
    )
    return (stored or {}).get("dossier") or None


# ── the two tools ─────────────────────────────────────────────────────────────


@server.tool(
    description=(
        "The grounded contribution context CodeOnboard prepared for this "
        "session: the task, the pinned repository revision, the change boundary "
        "(target files and symbols, what must not change, the tests that already "
        "guard this behaviour, discovered edge cases and repository "
        "conventions), the contracts the change must preserve, and what the "
        "developer has demonstrated they understand. Call this first, and verify "
        "the commit before trusting any file or symbol in it."
    )
)
def get_contribution_context() -> dict:
    graph = _session()
    commit = _commit(graph)
    dossier = _dossier(graph, commit)

    # DI-8: refuse rather than fabricate. A confident schema wrapped around an
    # empty boundary is worse than an error, because the schema is what makes a
    # reader trust it.
    reason = handoff.unusable_reason(graph, dossier)
    if reason:
        raise ValueError(_REFUSALS.get(reason, reason))

    survey = None
    try:
        owner, repo = parse_repo_url(graph.repo_url)
        survey = survey_store.load_survey(f"{owner}/{repo}", commit,
                                          db_path=_db_path())
    except Exception:                                             # noqa: BLE001
        # The survey only feeds `not_taught`. Its absence loses one field; it is
        # not a reason to withhold the boundary the agent actually needs.
        survey = None

    return handoff.build_context(graph, dossier, survey, commit)


@server.tool(
    description=(
        "Check whether the files currently changed are inside the contribution "
        "boundary CodeOnboard planned for this session. Pass the output of "
        "`git diff --name-only` (repository-relative paths). This compares FILE "
        "PATHS ONLY: it does not read the files, run anything, or judge whether "
        "the change is correct — see `not_checked` in the result."
    )
)
def check_scope(changed_files: list[str]) -> dict:
    graph = _session()
    dossier = _dossier(graph, _commit(graph))
    boundary = investigation_module.boundary(dossier or {})
    if not boundary:
        raise ValueError(_REFUSALS["no_change_boundary"])
    return contribution_model.check_paths(list(changed_files or []), boundary)


#: Refusals, worded for the agent that reads them. A slug would be a fixed key
#: for a frontend; this reader is a model, and it needs to know what to do next.
_REFUSALS = {
    "not_a_contribution_session":
        "This CodeOnboard session is not a code contribution, so there is no "
        "change boundary to work inside.",
    "not_ready_to_implement":
        "This learner has not yet demonstrated the concepts this change depends "
        "on. CodeOnboard has not opened the handoff.",
    "no_change_boundary":
        "The investigation for this session recorded no change boundary, so "
        "CodeOnboard cannot say what is in or out of scope for this task.",
}


if __name__ == "__main__":
    server.run(transport="stdio")
