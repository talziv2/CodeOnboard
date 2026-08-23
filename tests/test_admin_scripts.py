"""`set_password.py` and `adopt_legacy_sessions.py` (multi-user M2).

Run with: uv run pytest tests/test_admin_scripts.py -v

Two console tools that do things no endpoint may. What is worth testing is not
that they work — they are forty lines each — but that their REFUSALS hold, since
each one exists to prevent a specific irreversible mistake:

  `set_password`   is the only way back into an account (D-5 ships no reset), so
                   it must never be reachable over HTTP and must never move an
                   identity between users.
  `adopt_legacy`   is a bulk ownership rewrite — the exact operation the whole
                   ownership model exists to prevent — so every precondition is
                   a guard, and none is optional.
"""
import importlib
import sqlite3
import sys
from pathlib import Path

import pytest

from tests.conftest import TEST_USER_ID

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import adopt_legacy_sessions as adopt_script  # noqa: E402
import set_password as set_password_script  # noqa: E402

from backend.auth import identity, tokens  # noqa: E402
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode  # noqa: E402
from backend.learning.store import save_graph  # noqa: E402

migration = importlib.import_module("backend.migrations.001_multi_user")

EMAIL = "shira@example.com"
PASSWORD = "a-long-enough-passphrase"


@pytest.fixture
def db(tmp_path) -> Path:
    return tmp_path / "sessions.db"


def _graph(repo_url="https://github.com/psf/requests") -> LearningGraph:
    graph = LearningGraph(repo_url=repo_url, goal={"focus_area": "sessions"})
    node = graph.add_node(LearningNode(
        title="Understand Session",
        code_anchor=CodeAnchor(file="requests/sessions.py", line_start=1, line_end=80),
    ))
    graph.set_current(node.id)
    return graph


def _legacy_corpus(db: Path, count: int = 3) -> list[LearningGraph]:
    graphs = [_graph() for _ in range(count)]
    for graph in graphs:
        save_graph(graph, db, user_id=TEST_USER_ID)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE sessions SET user_id = NULL")
    migration.migrate(db, apply=True)
    return graphs


def _real_account(db: Path, email: str = EMAIL) -> str:
    """An account someone can actually sign in to."""
    return set_password_script.set_password(
        email, PASSWORD, create=True, db_path=db
    )["user_id"]


# ── set_password.py ───────────────────────────────────────────────────────────

def test_it_creates_an_account_that_can_then_sign_in(db):
    report = set_password_script.set_password(EMAIL, PASSWORD, create=True, db_path=db)

    assert report["created_user"] is True
    record = identity.find_identity(identity.PASSWORD, EMAIL, db)
    assert record is not None
    from backend.auth import passwords

    assert passwords.verify(record["secret_hash"], PASSWORD)


def test_it_refuses_to_create_unless_asked(db):
    with pytest.raises(SystemExit):
        set_password_script.set_password(EMAIL, PASSWORD, db_path=db)


def test_it_updates_an_existing_password(db):
    _real_account(db)

    report = set_password_script.set_password(
        EMAIL, "a-different-passphrase", db_path=db
    )

    assert report["created_identity"] is False
    from backend.auth import passwords

    record = identity.find_identity(identity.PASSWORD, EMAIL, db)
    assert passwords.verify(record["secret_hash"], "a-different-passphrase")
    assert passwords.verify(record["secret_hash"], PASSWORD) is False


def test_changing_a_password_ends_every_existing_session(db):
    """Somebody changes a password when they think it has been learned.

    Leaving live tokens in place would preserve exactly the access they are
    trying to revoke.
    """
    user_id = _real_account(db)
    tokens.issue(user_id, db_path=db)
    tokens.issue(user_id, db_path=db)

    report = set_password_script.set_password(EMAIL, "a-different-passphrase", db_path=db)

    assert report["sessions_revoked"] == 2
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0] == 0


def test_it_refuses_a_weak_password(db):
    from backend.auth import passwords

    with pytest.raises(passwords.WeakPasswordError):
        set_password_script.set_password("x@example.com", "short", create=True, db_path=db)


def test_it_refuses_when_the_identity_belongs_to_someone_else(db):
    """Silently moving an identity between users is an account takeover.

    The state: `users.email` says the address belongs to one account, while the
    password identity for that same address belongs to another. However it
    arose, repairing it by reassignment would hand one person's credential to
    somebody else's account.
    """
    owner = _real_account(db)                       # holds EMAIL and its identity
    impostor = identity.create_user("impostor@example.com", db_path=db)

    # Swap which USER the address belongs to, leaving the IDENTITY where it is.
    # Done in two steps because `users.email` is unique — the owner has to let go
    # of the address before the impostor can take it.
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE users SET email = ? WHERE user_id = ?",
            ("displaced@example.com", owner),
        )
        conn.execute(
            "UPDATE users SET email = ? WHERE user_id = ?", (EMAIL, impostor)
        )

    with pytest.raises(SystemExit, match="different user"):
        set_password_script.set_password(EMAIL, PASSWORD, db_path=db)

    # And the real owner's password is untouched.
    from backend.auth import passwords

    record = identity.find_identity(identity.PASSWORD, EMAIL, db)
    assert record["user_id"] == owner
    assert passwords.verify(record["secret_hash"], PASSWORD)


def test_no_route_exposes_the_password_setter(db):
    """THE BOUNDARY THAT MUST NOT ERODE.

    D-5 ships no email verification, so a reset ENDPOINT would have nothing to
    authenticate the request with — which is exactly why reset was deferred.
    This tool's safety comes entirely from needing shell access to the machine.

    Asserted structurally rather than trusted, so a future "small helper
    endpoint" fails the suite instead of quietly becoming a password-reset API
    that anyone on the network can call.
    """
    import backend.api as api

    for route in api.app.routes:
        endpoint = getattr(route, "endpoint", None)
        module = getattr(endpoint, "__module__", "") or ""
        assert "set_password" not in module, (
            f"{getattr(route, 'path', route)} reaches the console password setter"
        )

    source = (Path(__file__).resolve().parents[1] / "backend").rglob("*.py")
    for path in source:
        text = path.read_text(encoding="utf-8", errors="replace")
        assert "set_password_script" not in text
        assert "scripts.set_password" not in text
        assert "from set_password" not in text


# ── adopt_legacy_sessions.py ──────────────────────────────────────────────────

def test_it_plans_the_move_without_touching_anything(db):
    _legacy_corpus(db, 3)
    _real_account(db)
    legacy = identity.get_legacy_user_id(db)

    report = adopt_script.plan(EMAIL, db)

    assert report["count"] == 3
    with sqlite3.connect(db) as conn:
        still_legacy = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE user_id = ?", (legacy,)
        ).fetchone()[0]
    assert still_legacy == 3


def test_it_moves_every_legacy_session(db):
    _legacy_corpus(db, 3)
    target = _real_account(db)

    report = adopt_script.adopt(EMAIL, db)

    assert report["moved"] == 3
    with sqlite3.connect(db) as conn:
        owners = {r[0] for r in conn.execute("SELECT user_id FROM sessions")}
    assert owners == {target}


def test_a_second_run_moves_nothing(db):
    _legacy_corpus(db, 3)
    _real_account(db)
    adopt_script.adopt(EMAIL, db)

    again = adopt_script.adopt(EMAIL, db)

    assert again["moved"] == 0
    assert again["count"] == 0


def test_it_refuses_a_target_that_cannot_sign_in(db):
    """THE GUARD THAT MATTERS MOST.

    The legacy user is precisely an account with no identity. Adopting into
    another one would move the whole corpus somewhere equally unreachable and
    report success.
    """
    _legacy_corpus(db, 2)
    identity.create_user("ghost@example.com", db_path=db)   # no identity

    with pytest.raises(adopt_script.AdoptionRefused, match="no way to sign in"):
        adopt_script.plan("ghost@example.com", db)


def test_it_refuses_an_unknown_target(db):
    _legacy_corpus(db, 2)

    with pytest.raises(adopt_script.AdoptionRefused, match="No account"):
        adopt_script.plan("nobody@example.com", db)


def test_it_refuses_a_deactivated_target(db):
    _legacy_corpus(db, 2)
    user_id = _real_account(db)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE users SET is_active = 0 WHERE user_id = ?", (user_id,))

    with pytest.raises(adopt_script.AdoptionRefused, match="not an active"):
        adopt_script.plan(EMAIL, db)


def test_it_refuses_to_adopt_into_the_legacy_user_itself(db):
    """Three guards stand between here and a no-op that reports success.

    In its natural state the legacy user trips the FIRST two — inactive, and no
    way to sign in — which is the layering working. To reach the third, both are
    lifted, and the "target IS the source" check still refuses. Each is tested
    where it is the only thing standing.
    """
    _legacy_corpus(db, 2)
    legacy = identity.get_legacy_user_id(db)

    # Untouched: caught by the "not active" guard.
    with pytest.raises(adopt_script.AdoptionRefused, match="not an active"):
        adopt_script.plan(identity.LEGACY_EMAIL, db)

    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE users SET is_active = 1 WHERE user_id = ?", (legacy,))
    # Active but still unreachable: caught by the "no way to sign in" guard.
    with pytest.raises(adopt_script.AdoptionRefused, match="no way to sign in"):
        adopt_script.plan(identity.LEGACY_EMAIL, db)

    identity.add_identity(
        legacy, identity.PASSWORD, identity.LEGACY_EMAIL,
        secret_hash="x", db_path=db,
    )
    # Now only the last guard is left, and it holds.
    with pytest.raises(adopt_script.AdoptionRefused, match="IS the legacy user"):
        adopt_script.plan(identity.LEGACY_EMAIL, db)


def test_it_never_touches_a_session_owned_by_someone_else(db):
    """Scoped by CURRENT owner, not by a list gathered a moment ago.

    A session that changed hands between the plan and the apply is left alone
    rather than taken.
    """
    _legacy_corpus(db, 3)
    target = _real_account(db)
    other = identity.create_user("other@example.com", db_path=db)
    with sqlite3.connect(db) as conn:
        victim = conn.execute("SELECT session_id FROM sessions LIMIT 1").fetchone()[0]
        conn.execute(
            "UPDATE sessions SET user_id = ? WHERE session_id = ?", (other, victim)
        )

    adopt_script.adopt(EMAIL, db)

    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "SELECT user_id FROM sessions WHERE session_id = ?", (victim,)
        ).fetchone()[0] == other
        assert conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE user_id = ?", (target,)
        ).fetchone()[0] == 2


def test_it_refuses_before_the_migration_has_run(db):
    save_graph(_graph(), db, user_id=TEST_USER_ID)
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM users")
        conn.execute("UPDATE sessions SET user_id = NULL")
    _real_account(db)

    with pytest.raises(adopt_script.AdoptionRefused, match="No legacy user"):
        adopt_script.plan(EMAIL, db)


def test_adoption_does_not_change_the_sessions_themselves(db):
    """Ownership moves; nothing else does.

    Not obvious from the UPDATE alone, and worth pinning: the point of adopting
    the corpus is that it stays exactly what it was.
    """
    graphs = _legacy_corpus(db, 2)
    _real_account(db)
    with sqlite3.connect(db) as conn:
        before = conn.execute(
            "SELECT session_id, repo_url, goal_json, current_node_id, "
            "schema_version, title FROM sessions ORDER BY session_id"
        ).fetchall()

    adopt_script.adopt(EMAIL, db)

    with sqlite3.connect(db) as conn:
        after = conn.execute(
            "SELECT session_id, repo_url, goal_json, current_node_id, "
            "schema_version, title FROM sessions ORDER BY session_id"
        ).fetchall()
    assert after == before
    from backend.learning.store import load_graph

    # After adoption they belong to the TARGET account — which is the change —
    # so that is who must be able to read them.
    target = identity.find_user_by_email(EMAIL, db_path=db)["user_id"]
    for graph in graphs:
        assert load_graph(graph.session_id, target, db) is not None
