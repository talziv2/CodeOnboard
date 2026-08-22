"""The checkout-layout migration's decisions (multi-user M0).

Run with: uv run pytest tests/test_repo_layout_migration.py -v

`scripts/migrate_repo_layout.py` moves `data/repos/<name>` to
`data/repos/<owner>/<name>`. It is a one-shot developer utility, so what is
worth testing is not its plumbing but the two judgements it makes on real data —
which directory wins a destination collision, and whether a second run does
anything. Both were wrong-able, and one of them decides whether a checkout is
deleted.

The git layer is stubbed: these are tests of the planning rules, not of
GitPython.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import migrate_repo_layout as migration  # noqa: E402


@pytest.fixture
def repos(tmp_path, monkeypatch):
    """A fake `data/repos` whose checkouts report whatever origin we name."""
    root = tmp_path / "repos"
    root.mkdir()
    monkeypatch.setattr(migration, "REPOS_DIR", root)

    origins: dict[str, str] = {}

    def make(name: str, origin: str) -> Path:
        path = root / name
        (path / ".git").mkdir(parents=True)
        origins[name] = origin
        return path

    monkeypatch.setattr(migration, "_origin_url", lambda p: origins.get(p.name))
    monkeypatch.setattr(migration, "_commit", lambda p: "deadbeef")
    return make


def test_a_checkout_is_planned_under_its_owner(repos):
    repos("requests", "https://github.com/psf/requests")

    moves, duplicates = migration.build_plans()

    assert len(moves) == 1
    assert moves[0].destination.parts[-2:] == ("psf", "requests")
    assert duplicates == []


def test_two_owners_of_one_name_are_two_destinations(repos):
    """The collision that made this migration necessary is not itself a conflict.

    Both directories cannot exist at the flat layout — that is the bug — but
    once the owner is in the path they are simply two moves.
    """
    repos("requests", "https://github.com/psf/requests")
    repos("requests-fork", "https://github.com/kennethreitz/requests")

    moves, _ = migration.build_plans()

    destinations = {m.destination.parts[-2:] for m in moves}
    assert destinations == {("psf", "requests"), ("kennethreitz", "requests")}


def test_the_canonical_spelling_wins_a_collision(repos):
    """`aima-python` and `aima-python.git` are one repository, two directories.

    Only one can occupy the destination. The suffix-free name wins because it is
    the spelling the sessions were started from — and, critically, the loser is
    reported as a DUPLICATE rather than moved or deleted.
    """
    repos("aima-python", "https://github.com/aimacode/aima-python")
    repos("aima-python.git", "https://github.com/aimacode/aima-python.git")

    moves, duplicates = migration.build_plans()

    assert [m.source.name for m in moves] == ["aima-python"]
    assert [d.source.name for d in duplicates] == ["aima-python.git"]


def test_a_collision_of_casings_is_still_a_collision(repos):
    """The live dev machine had exactly this: `WorldFlowAI` and `worldflowai`.

    GitHub treats them as one repository, so normalising to lower case is what
    stops the survey being paid for twice and two clones racing for one
    directory on a case-insensitive filesystem.
    """
    repos("everything-claude-code", "https://github.com/worldflowai/everything-claude-code")
    repos("everything-claude-code.git", "https://github.com/WorldFlowAI/everything-claude-code.git")

    moves, duplicates = migration.build_plans()

    assert len(moves) == 1
    assert moves[0].destination.parts[-2:] == ("worldflowai", "everything-claude-code")
    assert len(duplicates) == 1


def test_an_already_migrated_layout_plans_nothing(repos, tmp_path):
    """Idempotence, which is what makes re-running after a failure safe.

    A migrated checkout is at `<owner>/<name>`, so it has no `.git` at the top
    level any more and is not a candidate at all.
    """
    root = tmp_path / "repos"
    (root / "psf" / "requests" / ".git").mkdir(parents=True)

    moves, duplicates = migration.build_plans()

    assert moves == []
    assert duplicates == []


def test_a_checkout_with_no_origin_is_left_alone(repos):
    repos("mystery", "https://github.com/x/y")
    migration._origin_url = lambda p: None      # type: ignore[assignment]

    moves, duplicates = migration.build_plans()

    assert moves == []
    assert [d.note for d in duplicates] == ["no origin remote - left alone"]
    # Never a deletion candidate: it has no destination to be redundant against.
    assert duplicates[0].destination is None


def test_an_unsupported_origin_is_left_alone(repos):
    repos("weird", "git@gitlab.example.com:team/project.git")

    moves, duplicates = migration.build_plans()

    assert moves == []
    assert duplicates[0].destination is None
