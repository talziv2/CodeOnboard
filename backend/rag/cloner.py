from pathlib import Path

import git


REPOS_DIR = Path("data/repos")


def clone_repo(repo_url: str) -> str:
    repo_name = repo_url.rstrip("/").split("/")[-1]
    repo_path = REPOS_DIR / repo_name

    if repo_path.exists():
        return str(repo_path)

    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    git.Repo.clone_from(repo_url, str(repo_path), depth=1)

    return str(repo_path)


def check_repo_reachable(repo_url: str, timeout: int = 15) -> str | None:
    """Return None when the repo can be cloned, otherwise why it can't.

    Uses the same transport as clone_repo, so a pass here is a real predictor
    rather than a guess. Callers use this to fail before the goal interview
    instead of after the pipeline has already started.
    """
    client = git.cmd.Git()
    # GIT_TERMINAL_PROMPT/GIT_ASKPASS stop a private repo from blocking on a
    # credential prompt; the low-speed pair is the timeout, since GitPython's
    # kill_after_timeout is not supported on Windows.
    env = {
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "",
        "GCM_INTERACTIVE": "never",
        "GIT_HTTP_LOW_SPEED_LIMIT": "1000",
        "GIT_HTTP_LOW_SPEED_TIME": str(timeout),
    }
    try:
        with client.custom_environment(**env):
            client.ls_remote(repo_url, heads=True)
        return None
    except git.GitCommandError as exc:
        stderr = f"{exc.stderr or ''} {exc.stdout or ''}".lower()
        if "not found" in stderr:
            return "That repository doesn't exist, or it's private."
        if "could not resolve host" in stderr or "unable to access" in stderr:
            return "Couldn't reach the host. Check your connection and try again."
        if (
            "authentication" in stderr
            or "permission denied" in stderr
            or "terminal prompts disabled" in stderr
        ):
            return "That repository needs credentials CodeOnboard doesn't have."
        return "That repository couldn't be opened. Check the URL."


def parse_repo_url(repo_url: str) -> tuple[str, str]:
    cleaned = repo_url.rstrip("/").removesuffix(".git")
    parts = cleaned.split("/")
    return parts[-2], parts[-1]


def get_commit_sha(repo_path: str) -> str:
    return git.Repo(repo_path).head.commit.hexsha
