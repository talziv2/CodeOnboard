from unittest.mock import MagicMock, patch

import git
import pytest

from backend.repo.cloner import check_repo_reachable, parse_repo_url


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
