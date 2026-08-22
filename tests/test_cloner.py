from pathlib import Path
from unittest.mock import MagicMock, patch

import git
import pytest

from backend.repo import cloner
from backend.repo.cloner import check_repo_reachable, clone_repo, parse_repo_url


def _git_error(stderr: str) -> git.GitCommandError:
    return git.GitCommandError("git ls-remote", 128, stderr)


@patch("backend.repo.cloner.git.cmd.Git")
def test_reachable_repo_returns_none(mock_git):
    # Arrange
    client = mock_git.return_value

    # Act
    result = check_repo_reachable("https://github.com/psf/requests")

    # Assert
    assert result is None
    client.ls_remote.assert_called_once()


@patch("backend.repo.cloner.git.cmd.Git")
def test_credential_prompts_are_disabled(mock_git):
    # A private repo must fail fast rather than block on a credential prompt.
    client = mock_git.return_value

    check_repo_reachable("https://github.com/private/repo")

    env = client.custom_environment.call_args.kwargs
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GIT_ASKPASS"] == ""


@patch("backend.repo.cloner.git.cmd.Git")
def test_timeout_is_passed_as_low_speed_window(mock_git):
    client = mock_git.return_value

    check_repo_reachable("https://github.com/psf/requests", timeout=7)

    assert client.custom_environment.call_args.kwargs["GIT_HTTP_LOW_SPEED_TIME"] == "7"


@pytest.mark.parametrize(
    "stderr, expected",
    [
        ("remote: Repository not found.", "doesn't exist"),
        ("fatal: could not resolve host: github.com", "Couldn't reach the host"),
        ("fatal: Authentication failed for 'https://...'", "credentials"),
        ("fatal: terminal prompts disabled", "credentials"),
        ("something else entirely", "couldn't be opened"),
    ],
)
@patch("backend.repo.cloner.git.cmd.Git")
def test_git_failures_map_to_readable_reasons(mock_git, stderr, expected):
    client = mock_git.return_value
    client.custom_environment.return_value = MagicMock()
    client.ls_remote.side_effect = _git_error(stderr)

    result = check_repo_reachable("https://github.com/psf/nope")

    assert result is not None
    assert expected in result


def test_parse_repo_url_handles_git_suffix_and_trailing_slash():
    assert parse_repo_url("https://github.com/psf/requests") == ("psf", "requests")
    assert parse_repo_url("https://github.com/psf/requests.git") == ("psf", "requests")
    assert parse_repo_url("https://github.com/psf/requests/") == ("psf", "requests")


# --- clone_repo: the checkout layout (multi-user M0) --------------------------


@pytest.fixture
def repos_dir(tmp_path, monkeypatch):
    """Point REPOS_DIR at a temp directory so no test touches data/repos."""
    root = tmp_path / "repos"
    monkeypatch.setattr(cloner, "REPOS_DIR", root)
    return root


def _fake_clone(populate: str = "# code\n"):
    """Stand in for `git.Repo.clone_from`, writing a file into the target."""

    def clone_from(url, path, depth=None, **kwargs):
        Path(path).mkdir(parents=True, exist_ok=True)
        (Path(path) / "module.py").write_text(populate)
        return MagicMock()

    return clone_from


def test_clone_places_the_checkout_under_its_owner(repos_dir):
    with patch.object(cloner.git.Repo, "clone_from", side_effect=_fake_clone()):
        path = clone_repo("https://github.com/psf/requests")

    assert Path(path) == repos_dir / "psf" / "requests"
    assert (Path(path) / "module.py").exists()


def test_two_owners_of_one_name_do_not_share_a_checkout(repos_dir):
    # P6: keyed on the basename these were one directory, so the second learner
    # studied the first one's code.
    with patch.object(cloner.git.Repo, "clone_from", side_effect=_fake_clone("A\n")):
        first = clone_repo("https://github.com/psf/requests")
    with patch.object(cloner.git.Repo, "clone_from", side_effect=_fake_clone("B\n")):
        second = clone_repo("https://github.com/kennethreitz/requests")

    assert first != second
    assert (Path(first) / "module.py").read_text() == "A\n"
    assert (Path(second) / "module.py").read_text() == "B\n"


def test_an_existing_checkout_is_reused_not_recloned(repos_dir):
    with patch.object(cloner.git.Repo, "clone_from", side_effect=_fake_clone()) as first:
        clone_repo("https://github.com/psf/requests")
    assert first.call_count == 1

    with patch.object(cloner.git.Repo, "clone_from", side_effect=_fake_clone()) as again:
        clone_repo("https://github.com/psf/requests")
    # A clone is pinned — re-cloning would move the commit and invalidate both
    # the survey cache and every dossier recorded against it.
    assert again.call_count == 0


def test_every_spelling_reuses_the_same_checkout(repos_dir):
    with patch.object(cloner.git.Repo, "clone_from", side_effect=_fake_clone()) as first:
        clone_repo("https://github.com/psf/requests")
    with patch.object(cloner.git.Repo, "clone_from", side_effect=_fake_clone()) as again:
        second = clone_repo("https://github.com/PSF/Requests.git/")

    assert again.call_count == 0
    assert Path(second) == repos_dir / "psf" / "requests"
    assert first.call_count == 1


def test_a_failed_clone_leaves_no_directory_behind(repos_dir):
    # Cloning into a staging directory is what makes this true: without it an
    # interrupted clone leaves a partial checkout that `exists()` would later
    # accept as finished.
    def explode(url, path, depth=None, **kwargs):
        Path(path).mkdir(parents=True, exist_ok=True)
        (Path(path) / "half.py").write_text("incomplete")
        raise git.GitCommandError("git clone", 128, "network died")

    with patch.object(cloner.git.Repo, "clone_from", side_effect=explode):
        with pytest.raises(git.GitCommandError):
            clone_repo("https://github.com/psf/requests")

    assert not (repos_dir / "psf" / "requests").exists()
    assert list(repos_dir.rglob("*.partial")) == []


def test_clone_refuses_a_url_outside_the_allow_list(repos_dir):
    with patch.object(cloner.git.Repo, "clone_from") as never:
        with pytest.raises(ValueError):
            clone_repo("http://169.254.169.254/latest/meta-data/")
    assert never.call_count == 0
