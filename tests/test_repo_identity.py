"""Repository identity, URL validation and checkout containment (multi-user M0).

Run with: uv run pytest tests/test_repo_identity.py -v

These cover the three hazards M0 exists to close, all of which are invisible with
one user and one repository owner:

  P6  two repositories with the same NAME and different OWNERS shared one
      checkout directory, because the path was keyed on the URL basename while
      the survey cache was keyed on `owner/repo`;
  P8  `/repo/check` handed an arbitrary user-supplied URL to `git ls-remote`,
      making the server fetch anything the caller named;
  P9  containment was a string prefix, so a sibling directory whose name began
      the same way was reachable by traversal.

No network and no cloning: everything here is either pure or operates on a
temporary directory.
"""
from pathlib import Path

import pytest

from backend.repo.cloner import (
    REPOS_DIR,
    normalize_repo_url,
    parse_repo_url,
    repo_dir,
    repo_slug,
    resolve_within,
    validate_repo_url,
)


# --- P6: identity is owner + name, on disk and in the cache key ---------------

def test_same_name_different_owners_get_different_directories():
    """THE BUG THIS MILESTONE EXISTS FOR.

    Both of these are real repositories called `requests`. Keyed on the basename
    they were one directory, so whoever cloned second silently studied the first
    one's code while the survey cache — correctly keyed on `owner/repo` — wrote
    an account of a repository that was not on disk.
    """
    psf = repo_dir("https://github.com/psf/requests")
    other = repo_dir("https://github.com/kennethreitz/requests")

    assert psf != other
    assert psf == REPOS_DIR / "psf" / "requests"
    assert other == REPOS_DIR / "kennethreitz" / "requests"


def test_the_checkout_path_and_the_survey_key_agree():
    # The two disagreeing is what made the collision silent rather than loud.
    url = "https://github.com/psf/requests"

    owner, name = parse_repo_url(url)

    assert repo_slug(url) == f"{owner}/{name}"
    assert repo_dir(url) == REPOS_DIR / owner / name


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/psf/requests",
        "https://github.com/psf/requests/",
        "https://github.com/psf/requests.git",
        "https://github.com/PSF/Requests",
        "https://github.com/psf/Requests.git/",
    ],
)
def test_every_spelling_of_one_repository_normalises_to_one_identity(url):
    """The live database holds five spellings of three repositories.

    Case matters here and not only punctuation: this machine's checkout
    directory contained `WorldFlowAI/everything-claude-code` and
    `worldflowai/everything-claude-code` as two separate clones of one
    repository. GitHub treats them as the same; so must we, or the survey is
    paid for twice and a case-insensitive filesystem races two clones into one
    directory.
    """
    assert normalize_repo_url(url) == "https://github.com/psf/requests"
    assert parse_repo_url(url) == ("psf", "requests")
    assert repo_dir(url) == REPOS_DIR / "psf" / "requests"


def test_different_repositories_do_not_normalise_together():
    # Guard against a normalisation so eager it merges things it shouldn't.
    assert normalize_repo_url("https://github.com/psf/requests") != normalize_repo_url(
        "https://github.com/psf/requests-html"
    )


# --- P8: the URL allow-list ---------------------------------------------------

@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/psf/requests",
        "https://github.com/psf/requests.git",
        "https://github.com/psf/requests/",
        "https://github.com/aimacode/aima-python",
        "https://github.com/some/other-repo",
        "https://github.com/ShiraZakov/Dynamic4DPathOptimizationForSubmarines",
    ],
)
def test_real_repository_urls_are_accepted(url):
    # Every shape the existing tests, scripts and live database actually use.
    assert validate_repo_url(url) is None


@pytest.mark.parametrize(
    "url, because",
    [
        ("http://169.254.169.254/latest/meta-data/", "cloud metadata over http"),
        ("http://localhost:8000/session/x", "the app's own backend"),
        ("https://169.254.169.254/", "cloud metadata over https"),
        ("file:///etc/passwd", "local file scheme"),
        ("ssh://git@github.com/psf/requests", "non-https scheme"),
        ("git://github.com/psf/requests", "non-https scheme"),
        ("https://evil.example.com/psf/requests", "host not on the allow-list"),
        ("https://github.com.evil.example.com/a/b", "suffix-confusion host"),
        ("https://github.com:8080/psf/requests", "unexpected port"),
        ("https://user:token@github.com/psf/requests", "credentials in the URL"),
        ("https://github.com/psf", "not a repository path"),
        ("https://github.com/", "no path at all"),
        ("https://github.com/psf/requests/tree/main", "extra path segments"),
        ("https://github.com/psf/requests?x=1", "query string"),
        ("https://github.com/../../etc/passwd", "traversal in the path"),
        ("", "empty"),
        ("   ", "whitespace"),
    ],
)
def test_urls_that_must_never_reach_git_are_refused(url, because):
    """`/repo/check` makes the SERVER fetch what the CALLER names.

    Unbounded, that is a server-side request forgery primitive: a URL the caller
    cannot reach becomes a request the server makes for them. The refusal has to
    happen before git is handed the string, which is why it lives in the cloner
    rather than in the endpoint.
    """
    assert validate_repo_url(url) is not None, because


def test_a_refused_url_never_produces_a_path():
    # Belt to the allow-list's braces: even if a caller skips validation, no
    # filesystem path can be derived from a URL we would not clone.
    with pytest.raises(ValueError):
        repo_dir("https://evil.example.com/a/b")
    with pytest.raises(ValueError):
        parse_repo_url("file:///etc/passwd")


def test_check_repo_reachable_refuses_without_touching_the_network(monkeypatch):
    from backend.repo import cloner

    def explode(*_args, **_kwargs):  # pragma: no cover - must never run
        raise AssertionError("git was called for a URL that should be refused")

    monkeypatch.setattr(cloner.git.cmd, "Git", explode)

    reason = cloner.check_repo_reachable("http://169.254.169.254/latest/meta-data/")

    assert reason is not None


# --- P9: containment ----------------------------------------------------------

@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """A checkout with a same-prefixed sibling beside it.

    `requests-private` is the shape that defeated the old check: it starts with
    the same characters as `requests`, so a string prefix test said it was
    inside.
    """
    repo = tmp_path / "requests"
    (repo / "requests").mkdir(parents=True)
    (repo / "requests" / "sessions.py").write_text("# real file\n")

    sibling = tmp_path / "requests-private"
    sibling.mkdir()
    (sibling / "secrets.py").write_text("SECRET = 'do not read me'\n")
    return repo


def test_a_file_inside_the_checkout_resolves(checkout):
    resolved = resolve_within(str(checkout), "requests/sessions.py")

    assert resolved is not None
    assert resolved.is_file()


def test_the_same_prefixed_sibling_is_refused(checkout):
    """The exact case the previous `startswith` check let through."""
    assert resolve_within(str(checkout), "../requests-private/secrets.py") is None


@pytest.mark.parametrize(
    "path",
    [
        "../requests-private/secrets.py",
        "../../etc/passwd",
        "requests/../../escape.txt",
        "/etc/passwd",
        "..",
    ],
)
def test_traversal_shapes_are_refused(checkout, path):
    assert resolve_within(str(checkout), path) is None


def test_a_symlink_pointing_outside_is_refused(checkout, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("not part of the repository\n")
    link = checkout / "link.py"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform/account")

    # Resolved before comparing, so the link's TARGET is what is judged. A check
    # on the unresolved path would say `link.py` is inside and then open a file
    # that is not.
    assert resolve_within(str(checkout), "link.py") is None


def test_the_checkout_root_itself_resolves(checkout):
    # `.` is inside; only its being a directory stops the endpoint serving it.
    assert resolve_within(str(checkout), ".") is not None
