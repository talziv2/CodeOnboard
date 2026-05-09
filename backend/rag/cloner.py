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
