# Repository identity, validation and checkout.
#
# THREE CONCERNS, DELIBERATELY IN ONE PLACE, because they have to agree:
#
#   normalize_repo_url   the canonical string for one repository
#   validate_repo_url    whether a URL is one we will ever touch
#   clone_repo           where that repository lives on disk
#
# They disagreed before, and that was the bug. `clone_repo` keyed the checkout
# directory on the URL's LAST PATH SEGMENT — the owner was thrown away — while
# `survey_store` keyed its cache on `owner/repo`. So two repositories with the
# same name and different owners shared one directory on disk:
#
#     github.com/psf/requests          →  data/repos/requests
#     github.com/kennethreitz/requests →  data/repos/requests   ← the same one
#
# The second learner silently studied the first one's code, and the survey cache
# — correctly keyed — wrote an account of a repository that was not there. With
# one user and one owner per name this never fired. With many users it is a
# cross-tenant data leak that needs no attacker.
#
# The fix is that the path now carries the same identity the cache does:
#
#     data/repos/<owner>/<name>
#
# Lower-cased, because GitHub treats owners and names case-insensitively while
# preserving their case — `WorldFlowAI/everything-claude-code` and
# `worldflowai/everything-claude-code` are one repository, and this machine's dev
# checkout directory had cloned both. On a case-insensitive filesystem (Windows,
# macOS) two casings of one name are also the same directory, so normalising is
# what keeps disk and cache key in step rather than merely tidy.
#
# VALIDATION IS NOT TIDINESS EITHER. `check_repo_reachable` hands a user-supplied
# string to `git ls-remote`, and `clone_repo` hands one to `git clone`. Without a
# scheme and host allow-list that is a server-side request forgery primitive: a
# URL like `http://169.254.169.254/latest/meta-data/` is a request the server
# makes on the caller's behalf, to a host the caller could not reach. It is
# checked here, at the one place both paths pass through, rather than at the two
# endpoints that happen to call them today.

from __future__ import annotations

import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit

import git


REPOS_DIR = Path("data/repos")

# Hosts we will clone from. One entry today; a list because adding GitLab is a
# row rather than a rewrite, and because a `== "github.com"` buried in a
# condition is not a place anyone would look for the policy.
ALLOWED_HOSTS: frozenset[str] = frozenset({"github.com"})

# `owner/name`, and nothing else. No nested groups (GitLab's shape), no trailing
# path, no `.` or `..` segments — the last of those is what would let a crafted
# URL climb out of REPOS_DIR when the pieces are joined into a path.
_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# Reasons are the user-facing sentences the API already returns from
# `check_repo_reachable`, so a rejected URL reads the same however it failed.
_BAD_SCHEME = "Only https:// GitHub URLs are supported."
_BAD_HOST = "CodeOnboard only opens repositories hosted on GitHub."
_BAD_SHAPE = "That doesn't look like a repository URL. Expected https://github.com/owner/name."
_HAS_CREDENTIALS = "Remove the credentials from the URL before pasting it."


def validate_repo_url(repo_url: str) -> str | None:
    """None when the URL is one we will touch, otherwise why we won't.

    Checked before anything hands the string to git. The order matters only for
    which message a doubly-wrong URL gets; every branch is a refusal.
    """
    if not repo_url or not repo_url.strip():
        return _BAD_SHAPE

    try:
        parts = urlsplit(repo_url.strip())
    except ValueError:
        return _BAD_SHAPE

    if parts.scheme.lower() != "https":
        # http:// is excluded along with everything else: it is the scheme an
        # SSRF probe reaches for, and GitHub redirects it to https anyway.
        return _BAD_SCHEME

    # `urlsplit` puts `user:pass@host` in netloc and exposes the pieces
    # separately. A URL carrying credentials is either a mistake worth telling
    # someone about or an attempt to make the server authenticate somewhere.
    if parts.username or parts.password:
        return _HAS_CREDENTIALS

    # `hostname` is lower-cased and strips any port; a port is rejected below
    # rather than ignored, since `github.com:8080` is not GitHub.
    if parts.hostname not in ALLOWED_HOSTS:
        return _BAD_HOST
    if parts.port is not None:
        return _BAD_HOST

    # A query or fragment is never meaningful on a clone URL, and both are places
    # to hide a payload. Refused rather than stripped: stripping would silently
    # accept a URL the person did not mean to paste.
    if parts.query or parts.fragment:
        return _BAD_SHAPE

    segments = [s for s in parts.path.split("/") if s]
    if len(segments) != 2:
        return _BAD_SHAPE

    owner, name = segments[0], segments[1].removesuffix(".git")
    if not name:
        return _BAD_SHAPE
    if not _SEGMENT.match(owner) or not _SEGMENT.match(name):
        return _BAD_SHAPE

    return None


def parse_repo_url(repo_url: str) -> tuple[str, str]:
    """(owner, name) — lower-cased, `.git` and a trailing slash removed.

    LOWER-CASED IS A CHANGE, and it is the one that makes the identity single.
    `survey_store` keys on `f"{owner}/{repo}"`, so two casings of one repository
    previously produced two cache entries and paid for two surveys of the same
    code. It also produced two checkout directories on a case-sensitive
    filesystem and one racing directory on a case-insensitive one.

    Raises ValueError on a URL `validate_repo_url` would reject, so a caller that
    skipped validation fails loudly here instead of deriving a path from
    nonsense.
    """
    reason = validate_repo_url(repo_url)
    if reason is not None:
        raise ValueError(f"unsupported repository URL: {reason}")

    segments = [s for s in urlsplit(repo_url.strip()).path.split("/") if s]
    return segments[0].lower(), segments[1].removesuffix(".git").lower()


def normalize_repo_url(repo_url: str) -> str:
    """The canonical URL for one repository — the string identity is keyed on.

    `https://github.com/PSF/Requests.git`, `https://github.com/psf/requests/` and
    `https://github.com/psf/requests` are one repository and normalise to one
    string. The live database holds five spellings of three repositories, which
    is what this exists to collapse.
    """
    owner, name = parse_repo_url(repo_url)
    return f"https://github.com/{owner}/{name}"


def repo_slug(repo_url: str) -> str:
    """`owner/name` — the survey cache's key, derived from the same place."""
    owner, name = parse_repo_url(repo_url)
    return f"{owner}/{name}"


def repo_dir(repo_url: str) -> Path:
    """Where this repository's checkout lives. Pure — touches no disk.

    Separate from `clone_repo` so the layout migration and the tests can ask
    where a repository *belongs* without cloning it.
    """
    owner, name = parse_repo_url(repo_url)
    return REPOS_DIR / owner / name


def clone_repo(repo_url: str) -> str:
    """The path to a checkout of `repo_url`, cloning it if it is not there.

    Never updates an existing checkout: a clone is pinned, which is what lets
    the survey cache key on `(repo, commit)` and the dossier trust the commit it
    recorded.
    """
    repo_path = repo_dir(repo_url)   # validates as a side effect
    if repo_path.exists():
        return str(repo_path)

    repo_path.parent.mkdir(parents=True, exist_ok=True)
    # Clone to a temporary sibling and rename, so an interrupted clone cannot
    # leave a half-populated directory that the `exists()` check above would
    # later treat as a finished checkout. Two learners starting the same
    # repository at once is a normal event once there are two learners.
    staging = repo_path.with_name(f".{repo_path.name}.partial")
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    try:
        git.Repo.clone_from(repo_url, str(staging), depth=1)
        try:
            staging.rename(repo_path)
        except OSError:
            # Lost the race: someone else finished first. Their checkout is as
            # good as ours — same repository, same depth — so keep theirs.
            if not repo_path.exists():
                raise
            shutil.rmtree(staging, ignore_errors=True)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    return str(repo_path)


def check_repo_reachable(repo_url: str, timeout: int = 15) -> str | None:
    """Return None when the repo can be cloned, otherwise why it can't.

    Uses the same transport as clone_repo, so a pass here is a real predictor
    rather than a guess. Callers use this to fail before the goal interview
    instead of after the pipeline has already started.

    Validation runs FIRST and without touching the network — a rejected URL must
    not become an outbound request, which is the whole point of the allow-list.
    """
    reason = validate_repo_url(repo_url)
    if reason is not None:
        return reason

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


def get_commit_sha(repo_path: str) -> str:
    return git.Repo(repo_path).head.commit.hexsha


def resolve_within(repo_path: str, relative: str) -> Path | None:
    """`relative` resolved inside `repo_path`, or None if it escapes.

    THE CHECK THIS REPLACES WAS A STRING PREFIX:

        os.path.abspath(full).startswith(os.path.abspath(repo_path))

    which passes for a sibling whose name merely begins with the same
    characters — `data/repos/requests-private` starts with `data/repos/requests`
    — so `../requests-private/secrets.py` was reachable from a session anchored
    on `requests`. Harmless while every checkout was a public repo in a flat
    directory; not harmless once checkouts are per-owner and sessions belong to
    different people.

    `resolve()` on both sides also follows symlinks before comparing, so a link
    inside the checkout pointing at `/etc` fails the same test rather than being
    followed. Returns a path, not a bool, so the caller cannot check one string
    and then open another.
    """
    root = Path(repo_path).resolve()
    try:
        candidate = (root / relative).resolve()
    except (OSError, ValueError, RuntimeError):
        # RuntimeError: a symlink loop. OSError: a path the OS rejects outright.
        return None
    if candidate != root and root not in candidate.parents:
        return None
    return candidate
