# Explorer-path pipeline stages: repository preparation and Goal Investigation.
#
# These are the production implementations of the Stage-2/3 architecture:
#
#   run_repo_survey         clone -> skeleton (hard requirement, D15) -> Layer B
#                           survey loaded from the store or produced once and
#                           persisted (§6) -> module_map derived from the
#                           survey's subsystems (the P2 fix: complete, never an
#                           alphabetical prefix)
#   run_goal_investigation  the D11 stage: the ONLY plan-time exploration loop,
#                           writing state.investigation for Reviewer and Mentor
#                           to read.
#
# Same conventions as every agent: injected client, append to state.errors,
# never raise. Kept out of backend/agents because these wrap backend/repo
# machinery rather than owning a model conversation of their own.

from __future__ import annotations

import anthropic

from backend.pipeline.state import OnboardState
from backend.repo.cloner import clone_repo, get_commit_sha, parse_repo_url
from backend.repo import investigation as investigation_module
from backend.repo import survey_store
from backend.repo.skeleton import build_skeleton


def _module_map_from_survey(survey_payload: dict) -> dict:
    """The survey's subsystem account, in the module_map wire shape.

    Downstream consumers (the /onboard response, the Reviewer's prompt) keep
    their shape; the content is now the complete Layer B account instead of an
    80-chunk alphabetical prefix.
    """
    modules: dict[str, dict] = {}
    for entry in survey_payload.get("subsystems") or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        modules[name] = {
            "purpose": str(entry.get("responsibility") or ""),
            "key_files": [str(entry.get("key_file") or "")],
            "exports": (
                [str(entry["key_symbol"])] if entry.get("key_symbol") else []
            ),
            "dependencies": [],
        }
    return modules


def _module_map_from_skeleton(skeleton) -> dict:
    """Survey-less fallback: the deterministic inventory, thinly described."""
    return {
        name: {
            "purpose": f"source files: {', '.join(f.rsplit('/', 1)[-1] for f in files[:4])}",
            "key_files": list(files[:6]),
            "exports": [],
            "dependencies": [],
        }
        for name, files in skeleton.subsystems().items()
    }


def run_repo_survey(
    state: OnboardState,
    client: anthropic.Anthropic | None = None,
) -> OnboardState:
    """Clone, index, and attach the Layer B survey (stored, or produced once)."""
    try:
        state.repo_path = clone_repo(state.repo_url)
    except Exception as e:
        state.errors.append(f"cloner failed: {e}")
        return state

    # D15: no skeleton, no onboarding. A graph whose anchors cannot be
    # verified is worse than no graph.
    try:
        skeleton = build_skeleton(state.repo_path)
    except Exception as e:
        state.errors.append(f"repo_survey: skeleton build failed: {e}")
        return state

    try:
        owner, repo = parse_repo_url(state.repo_url)
        commit_sha = get_commit_sha(state.repo_path)
        payload, meta = survey_store.get_or_create_survey(
            client=client,
            repo_path=state.repo_path,
            owner_repo=f"{owner}/{repo}",
            commit_sha=commit_sha,
        )
        state.survey = payload
        if payload is None:
            state.errors.append(
                f"repo_survey: survey unavailable ({meta.get('stop_reason', 'unknown')}) "
                f"— investigation will run from the skeleton alone"
            )
    except Exception as e:
        # A missing survey degrades the investigation's starting map; it does
        # not block onboarding (the skeleton is the hard requirement, not
        # Layer B).
        state.survey = None
        state.errors.append(f"repo_survey: survey failed: {e}")

    state.module_map = (
        _module_map_from_survey(state.survey)
        if state.survey else _module_map_from_skeleton(skeleton)
    ) or _module_map_from_skeleton(skeleton)
    return state


def run_goal_investigation(
    state: OnboardState,
    client: anthropic.Anthropic | None = None,
) -> OnboardState:
    """The dedicated exploration stage (D11). Writes state.investigation."""
    if state.goal is None:
        state.errors.append("goal_investigation: goal missing")
        return state
    if not state.repo_path:
        state.errors.append("goal_investigation: repo_path missing")
        return state

    try:
        run = investigation_module.run_investigation(
            client=client,
            repo_path=state.repo_path,
            goal=state.goal,
            survey_payload=state.survey,
        )
    except Exception as e:
        state.errors.append(f"goal_investigation failed: {e}")
        return state

    if run.dossier is None:
        # Hard stop for the explorer path: the Mentor must not fabricate a
        # graph from nothing (D15). state.investigation stays None and the
        # pipeline routes to END with the error visible.
        # The stop reason alone says a run died, not why. `api_error` in
        # particular is a category, and the exploration's own error list is the
        # only place the cause exists — without it, diagnosing a dead pipeline
        # means re-running the investigation by hand to read a discarded string.
        cause = f" — {run.exploration.errors[0]}" if run.exploration.errors else ""
        state.errors.append(
            f"goal_investigation: no dossier produced "
            f"({run.exploration.stop_reason}){cause}"
        )
        return state

    state.investigation = {
        "dossier": run.dossier,
        "accepted": run.accepted,
        "stop_reason": run.exploration.stop_reason,
        "turns": run.exploration.turns,
        "tool_calls": len(run.exploration.trace),
        "rejections": list(run.exploration.rejections),
        "cost_usd": run.exploration.usage.cost_usd(),
        "seconds": run.exploration.seconds,
        "used_survey": run.used_survey,
    }
    return state
