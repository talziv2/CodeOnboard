"""The multi-user M1 migration: schema, backfill, idempotence, invariants.

Run with: uv run pytest tests/test_migration.py -v

The load-bearing property is **I8** — existing sessions remain loadable. A
migration that silently made ninety sessions invisible would look like a clean
run and read, from the app, as an empty account. So the tests here mostly assert
that things which existed before still exist and still load afterwards, rather
than that new things appeared.

Real SQLite against a temp file. No network, no LLM, no API key.
"""
import importlib
import json
import sqlite3
from pathlib import Path

import pytest

from backend.auth import identity, startup
from backend.auth.schema import init_auth_schema
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.learning.store import (
    SCHEMA_VERSION,
    delete_session,
    init_db,
    list_sessions_for_user,
    load_graph,
    save_graph,
)
from backend.repo import dossier_store

migration = importlib.import_module("backend.migrations.001_multi_user")


REPO_SPELLINGS = [
    "https://github.com/aimacode/aima-python",
    "https://github.com/aimacode/aima-python.git",
    "https://github.com/psf/requests",
    "https://github.com/psf/requests/",
    "https://github.com/fastapi/fastapi",
]


@pytest.fixture
def db(tmp_path) -> Path:
    return tmp_path / "sessions.db"


def _graph(repo_url: str, focus: str = "authentication") -> LearningGraph:
    graph = LearningGraph(
        repo_url=repo_url,
        goal={
            "primary_goal": "understand how authentication works",
            "goal_type": "understand_component",
            "focus_area": focus,
        },
    )
    node = graph.add_node(LearningNode(
        title="Understand HTTPBasicAuth",
        code_anchor=CodeAnchor(file="requests/auth.py", line_start=72, line_end=100),
    ))
    graph.set_current(node.id)
    return graph


def _legacy_db(db: Path, spellings=REPO_SPELLINGS) -> list[LearningGraph]:
    """A database in the PRE-MIGRATION shape: sessions with no owner.

    Built by saving graphs and then blanking the account columns, rather than by
    hand-writing rows — so the fixture cannot drift away from what the store
    actually produces.
    """
    graphs = [_graph(url, focus=f"area {i}") for i, url in enumerate(spellings)]
    for graph in graphs:
        save_graph(graph, db)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE sessions SET user_id = NULL, repo_id = NULL, title = NULL, "
            "status = NULL, last_active_at = NULL"
        )
    return graphs


# ── I8: nothing existing is lost ──────────────────────────────────────────────

def test_schema_version_does_not_move(db):
    _legacy_db(db)
    migration.migrate(db, apply=True)

    with sqlite3.connect(db) as conn:
        versions = {r[0] for r in conn.execute("SELECT schema_version FROM sessions")}
    assert versions == {SCHEMA_VERSION}, (
        "a bump makes load_graph treat every pre-existing session as MISSING"
    )


def test_every_session_still_loads_after_the_migration(db):
    graphs = _legacy_db(db)
    migration.migrate(db, apply=True)

    for graph in graphs:
        reloaded = load_graph(graph.session_id, db)
        assert reloaded is not None
        assert reloaded.repo_url == graph.repo_url
        assert reloaded.goal == graph.goal
        assert set(reloaded.nodes) == set(graph.nodes)


def test_repo_url_is_left_exactly_as_it_was(db):
    """The engine reads `graph.repo_url`; `clone_repo` reads it too.

    Normalising it in place would be a change to what the learning engine sees,
    which M1 is explicitly not allowed to make (I9). The canonical form lives on
    the `repositories` row instead.
    """
    graphs = _legacy_db(db)
    before = {g.session_id: g.repo_url for g in graphs}

    migration.migrate(db, apply=True)

    with sqlite3.connect(db) as conn:
        after = dict(conn.execute("SELECT session_id, repo_url FROM sessions"))
    assert after == before


# ── ownership ─────────────────────────────────────────────────────────────────

def test_every_session_gets_the_legacy_owner(db):
    _legacy_db(db)
    report = migration.migrate(db, apply=True)

    assert report["sessions_assigned"] == len(REPO_SPELLINGS)
    assert startup.count_unowned_sessions(db) == 0

    legacy = identity.get_legacy_user_id(db)
    with sqlite3.connect(db) as conn:
        owners = {r[0] for r in conn.execute("SELECT user_id FROM sessions")}
    assert owners == {legacy}


def test_the_legacy_user_cannot_be_logged_in_as(db):
    """A parking space, not an account.

    Inactive and with NO auth identity, so there is no (provider, subject) pair
    that resolves to it — which is what stops "every pre-existing session" from
    being reachable by anyone who works out the address.
    """
    _legacy_db(db)
    migration.migrate(db, apply=True)

    legacy = identity.get_legacy_user_id(db)
    with sqlite3.connect(db) as conn:
        active = conn.execute(
            "SELECT is_active FROM users WHERE user_id = ?", (legacy,)
        ).fetchone()[0]
        identities = conn.execute(
            "SELECT COUNT(*) FROM auth_identities WHERE user_id = ?", (legacy,)
        ).fetchone()[0]
    assert active == 0
    assert identities == 0


# ── repositories ──────────────────────────────────────────────────────────────

def test_five_url_spellings_collapse_to_three_repositories(db):
    """The exact shape of the live database (multi-user.md §1.7)."""
    _legacy_db(db)
    migration.migrate(db, apply=True)

    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT owner, name FROM repositories").fetchall()
    assert sorted(rows) == [
        ("aimacode", "aima-python"),
        ("fastapi", "fastapi"),
        ("psf", "requests"),
    ]


def test_sessions_on_different_spellings_share_one_repository_row(db):
    _legacy_db(db)
    migration.migrate(db, apply=True)

    with sqlite3.connect(db) as conn:
        by_url = dict(conn.execute("SELECT repo_url, repo_id FROM sessions"))
    assert by_url["https://github.com/psf/requests"] == by_url["https://github.com/psf/requests/"]
    assert (
        by_url["https://github.com/aimacode/aima-python"]
        == by_url["https://github.com/aimacode/aima-python.git"]
    )


def test_a_url_the_cloner_would_refuse_does_not_lose_its_session(db):
    """A session written before URL validation existed still has to work.

    It gets no repository row — there is no repository to point at — but the
    graph, its lessons and the learner's answers are untouched, and the run
    reports the URL rather than failing on it.
    """
    graph = _graph("https://gitlab.example.com/team/project")
    save_graph(graph, db)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE sessions SET user_id = NULL, repo_id = NULL")

    report = migration.migrate(db, apply=True)

    assert report["unmappable_repo_urls"] == ["https://gitlab.example.com/team/project"]
    assert load_graph(graph.session_id, db) is not None
    assert startup.count_unowned_sessions(db) == 0


# ── display metadata ──────────────────────────────────────────────────────────

def test_titles_come_from_the_goal_the_session_already_carries(db):
    _legacy_db(db, ["https://github.com/psf/requests"])
    migration.migrate(db, apply=True)

    with sqlite3.connect(db) as conn:
        title, status = conn.execute(
            "SELECT title, status FROM sessions"
        ).fetchone()
    assert title == "Area 0"          # focus_area, capitalised
    assert status == "active"


def test_a_finished_walk_is_not_marked_completed_by_the_migration(db):
    """Completion is derived from the graph, never a second stored truth."""
    _legacy_db(db, ["https://github.com/psf/requests"])
    migration.migrate(db, apply=True)

    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT status FROM sessions").fetchone()[0] == "active"


# ── idempotence ───────────────────────────────────────────────────────────────

def test_a_second_run_changes_nothing(db):
    _legacy_db(db)
    migration.migrate(db, apply=True)

    with sqlite3.connect(db) as conn:
        before = conn.execute(
            "SELECT session_id, user_id, repo_id, title, status FROM sessions "
            "ORDER BY session_id"
        ).fetchall()
        repos_before = conn.execute("SELECT COUNT(*) FROM repositories").fetchone()[0]
        users_before = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    second = migration.migrate(db, apply=True)

    with sqlite3.connect(db) as conn:
        after = conn.execute(
            "SELECT session_id, user_id, repo_id, title, status FROM sessions "
            "ORDER BY session_id"
        ).fetchall()
        assert conn.execute("SELECT COUNT(*) FROM repositories").fetchone()[0] == repos_before
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == users_before

    assert after == before
    assert second["sessions_assigned"] == 0
    assert second["sessions_already_owned"] == len(REPO_SPELLINGS)


def test_a_rerun_does_not_take_adopted_sessions_back_from_their_owner(db):
    """THE REASON EVERY UPDATE IS `WHERE … IS NULL`.

    M2 adopts the legacy user's sessions into a real account. If this migration
    were ever run again afterwards — and "run it again" must always be a safe
    response — an unconditional UPDATE would hand every one of them back to a
    user nobody can log in as.
    """
    _legacy_db(db)
    migration.migrate(db, apply=True)
    real_user = identity.create_user("shira@example.com", "Shira", db_path=db)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE sessions SET user_id = ?", (real_user,))

    migration.migrate(db, apply=True)

    with sqlite3.connect(db) as conn:
        owners = {r[0] for r in conn.execute("SELECT user_id FROM sessions")}
    assert owners == {real_user}


def test_dry_run_changes_nothing(db):
    """Reports what it would do, and leaves the sessions exactly as they were.

    NOT asserted here: that the account TABLES are absent afterwards. They are
    not, and that is correct — `save_graph` creates them, because the M1 shim
    stamps an owner on every new session so that I1 holds for rows written after
    the migration as well as before it. The fixture blanks `user_id` to
    reconstruct the pre-migration shape, so what a dry run must leave untouched
    is the ASSIGNMENT, which is what this checks.
    """
    _legacy_db(db)
    with sqlite3.connect(db) as conn:
        before = conn.execute(
            "SELECT session_id, user_id, repo_id, title, status FROM sessions "
            "ORDER BY session_id"
        ).fetchall()

    report = migration.migrate(db, apply=False)

    assert report["applied"] is False
    assert report["sessions_assigned"] == len(REPO_SPELLINGS)
    assert startup.count_unowned_sessions(db) == len(REPO_SPELLINGS)
    with sqlite3.connect(db) as conn:
        after = conn.execute(
            "SELECT session_id, user_id, repo_id, title, status FROM sessions "
            "ORDER BY session_id"
        ).fetchall()
    assert after == before


# ── startup invariants ────────────────────────────────────────────────────────

def test_startup_refuses_to_run_with_an_unowned_session(db):
    _legacy_db(db)

    with pytest.raises(startup.UnownedSessionsError) as caught:
        startup.assert_every_session_is_owned(db)
    # The message has to say what to do about it.
    assert "001_multi_user" in str(caught.value)


def test_startup_passes_after_the_migration(db):
    _legacy_db(db)
    migration.migrate(db, apply=True)

    startup.assert_every_session_is_owned(db)          # does not raise


def test_startup_is_silent_on_a_database_that_does_not_exist_yet(tmp_path):
    # A fresh install has no sessions, so none can be unowned.
    startup.run_startup_checks(tmp_path / "nothing.db")


def test_startup_is_silent_on_a_database_with_no_account_columns(db):
    """An older file `init_db` has not touched yet answers zero, not an error."""
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE sessions (session_id TEXT PRIMARY KEY, "
            "schema_version INTEGER NOT NULL)"
        )
    assert startup.count_unowned_sessions(db) == 0


# ── orphaned Dossiers ─────────────────────────────────────────────────────────

def test_deleting_a_session_removes_its_dossier(db):
    graph = _graph("https://github.com/psf/requests")
    save_graph(graph, db)
    dossier_store.save_investigation(
        graph.session_id, "abc123", {"dossier": {"claims": []}}, db
    )
    assert dossier_store.load_investigation(graph.session_id, "abc123", db) is not None

    delete_session(graph.session_id, db)

    assert dossier_store.load_investigation(graph.session_id, "abc123", db) is None


def test_the_sweep_removes_a_dossier_whose_session_is_gone(db):
    graph = _graph("https://github.com/psf/requests")
    save_graph(graph, db)
    dossier_store.save_investigation(
        graph.session_id, "abc123", {"dossier": {"claims": []}}, db
    )
    # Delete the session behind the store's back, as every delete before this
    # milestone did.
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (graph.session_id,))

    assert startup.sweep_orphaned_investigations(db) == 1
    assert startup.sweep_orphaned_investigations(db) == 0     # idempotent


def test_the_sweep_leaves_a_live_session_alone(db):
    graph = _graph("https://github.com/psf/requests")
    save_graph(graph, db)
    dossier_store.save_investigation(
        graph.session_id, "abc123", {"dossier": {"claims": []}}, db
    )

    assert startup.sweep_orphaned_investigations(db) == 0
    assert dossier_store.load_investigation(graph.session_id, "abc123", db) is not None


# ── owner-scoped listing ──────────────────────────────────────────────────────

def test_listing_is_scoped_to_one_user(db):
    _legacy_db(db)
    migration.migrate(db, apply=True)
    legacy = identity.get_legacy_user_id(db)
    other = identity.create_user("someone@example.com", db_path=db)

    assert len(list_sessions_for_user(legacy, db)) == len(REPO_SPELLINGS)
    assert list_sessions_for_user(other, db) == []


def test_listing_hides_archived_sessions_by_default(db):
    _legacy_db(db, ["https://github.com/psf/requests"])
    migration.migrate(db, apply=True)
    legacy = identity.get_legacy_user_id(db)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE sessions SET archived_at = '2026-08-22T10:00:00'")

    assert list_sessions_for_user(legacy, db) == []
    assert len(list_sessions_for_user(legacy, db, include_archived=True)) == 1


def test_listing_reports_progress_as_unknown_until_it_is_cached(db):
    """NULL means "not computed", and must not read as zero.

    The dashboard fills these in M4 from `progress.summary()`. A caller that
    treated the absent value as 0.0 would show every migrated session as 0%
    ready, which is a claim about the learner rather than about the cache.
    """
    _legacy_db(db, ["https://github.com/psf/requests"])
    migration.migrate(db, apply=True)
    legacy = identity.get_legacy_user_id(db)

    row = list_sessions_for_user(legacy, db)[0]
    assert row["progress"]["goal_readiness"] is None
    assert row["progress"]["stops_total"] is None


# ── new sessions, written after the migration ─────────────────────────────────

def test_a_newly_saved_session_is_owned_without_anyone_passing_an_owner(db):
    """The M1 shim: no way to log in yet, so a save defaults to the legacy user.

    M3 removes the default and makes the omission a TypeError.
    """
    graph = _graph("https://github.com/psf/requests")
    save_graph(graph, db)

    assert startup.count_unowned_sessions(db) == 0
    with sqlite3.connect(db) as conn:
        owner, repo_id = conn.execute(
            "SELECT user_id, repo_id FROM sessions WHERE session_id = ?",
            (graph.session_id,),
        ).fetchone()
    assert owner == identity.get_legacy_user_id(db)
    assert repo_id == identity.ensure_repository(graph.repo_url, db)


def test_saving_an_existing_session_never_reassigns_its_owner(db):
    """A save is the owner working, never a change of owner.

    Writing `excluded.user_id` in the upsert would make every save a chance to
    take someone else's session — the exact hole M3 exists to close, opened by
    the code meant to prepare for it.
    """
    graph = _graph("https://github.com/psf/requests")
    real_user = identity.create_user("shira@example.com", db_path=db)
    save_graph(graph, db, user_id=real_user)

    save_graph(graph, db)                     # no owner named this time

    with sqlite3.connect(db) as conn:
        owner = conn.execute(
            "SELECT user_id FROM sessions WHERE session_id = ?", (graph.session_id,)
        ).fetchone()[0]
    assert owner == real_user


def test_saving_updates_last_active_but_not_created_at(db):
    graph = _graph("https://github.com/psf/requests")
    save_graph(graph, db)
    with sqlite3.connect(db) as conn:
        created, active = conn.execute(
            "SELECT created_at, last_active_at FROM sessions"
        ).fetchone()

    graph.mark_visited(next(iter(graph.nodes)))
    save_graph(graph, db)

    with sqlite3.connect(db) as conn:
        created_after, active_after = conn.execute(
            "SELECT created_at, last_active_at FROM sessions"
        ).fetchone()
    assert created_after == created
    assert active_after >= active


# ── account tables ────────────────────────────────────────────────────────────

def test_the_account_schema_is_idempotent(db):
    init_db(db)
    init_auth_schema(db)
    init_auth_schema(db)

    with sqlite3.connect(db) as conn:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"users", "auth_identities", "auth_sessions",
            "repositories", "session_drafts"} <= tables


def test_one_identity_cannot_belong_to_two_users(db):
    init_db(db)
    init_auth_schema(db)
    a = identity.create_user("a@example.com", db_path=db)
    b = identity.create_user("b@example.com", db_path=db)

    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO auth_identities "
            "(identity_id, user_id, provider, subject, created_at) "
            "VALUES ('i1', ?, 'password', 'shared@example.com', '2026-08-22')",
            (a,),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO auth_identities "
                "(identity_id, user_id, provider, subject, created_at) "
                "VALUES ('i2', ?, 'password', 'shared@example.com', '2026-08-22')",
                (b,),
            )


def test_two_users_cannot_share_an_email(db):
    init_db(db)
    init_auth_schema(db)
    identity.create_user("shira@example.com", db_path=db)

    with pytest.raises(sqlite3.IntegrityError):
        identity.create_user("shira@example.com", db_path=db)


def test_repositories_are_not_owned_by_anyone(db):
    """A public GitHub URL has no owner in this system (§9)."""
    init_db(db)
    init_auth_schema(db)

    with sqlite3.connect(db) as conn:
        columns = {r[1] for r in conn.execute("PRAGMA table_info(repositories)")}
    assert "user_id" not in columns


def test_ensure_repository_is_stable_across_spellings(db):
    ids = {identity.ensure_repository(url, db) for url in (
        "https://github.com/psf/requests",
        "https://github.com/psf/requests/",
        "https://github.com/psf/requests.git",
        "https://github.com/PSF/Requests",
    )}
    assert len(ids) == 1


def test_ensure_repository_refuses_a_url_the_cloner_would_refuse(db):
    with pytest.raises(ValueError):
        identity.ensure_repository("https://evil.example.com/a/b", db)


# ── concurrency (the race M1 introduced, and closed) ──────────────────────────

def test_concurrent_first_saves_do_not_race_on_the_legacy_user(db):
    """`save_graph` resolves the owner on EVERY write, so this is the hot path.

    THE BUG THIS CAUGHT: `ensure_legacy_user` was written as
    "look it up, and create it if absent" — idempotent when called twice in
    sequence, and broken when called twice at once. Both callers see None, both
    INSERT, and the loser dies on `UNIQUE constraint failed: users.email`.

    It surfaced within a handful of runs of being introduced, in
    `test_concurrent_writers_all_succeed` rather than here, which is the usual
    way: the failure appears in whatever happens to be writing concurrently, not
    in the code that is wrong. `INSERT … ON CONFLICT DO NOTHING` then SELECT is
    race-free because each statement is atomic.
    """
    import threading

    errors: list[Exception] = []
    ids: list[str] = []
    barrier = threading.Barrier(8)

    def resolve() -> None:
        try:
            barrier.wait(timeout=10)
            ids.append(identity.ensure_legacy_user(db))
        except Exception as exc:              # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=resolve) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert errors == [], f"concurrent legacy-user resolution failed: {errors!r}"
    assert len(set(ids)) == 1, "the legacy user must resolve to ONE row"


def test_concurrent_first_saves_do_not_race_on_a_repository(db):
    """Same shape, same fix, different unique index (`idx_repo_canonical`)."""
    import threading

    errors: list[Exception] = []
    ids: list[str] = []
    barrier = threading.Barrier(8)

    def resolve() -> None:
        try:
            barrier.wait(timeout=10)
            ids.append(identity.ensure_repository(
                "https://github.com/psf/requests", db))
        except Exception as exc:              # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=resolve) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert errors == [], f"concurrent repository resolution failed: {errors!r}"
    assert len(set(ids)) == 1, "one repository must resolve to ONE row"
