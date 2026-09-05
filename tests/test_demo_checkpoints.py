"""Unit tests for the presentation checkpoint utility.

Run with: uv run pytest tests/test_demo_checkpoints.py -v

A wrong instrument produces wrong evidence, and this one produces the sessions a
presentation is given from — a checkpoint that silently loses the contribution
stage, or that collides node ids with the session it was copied from, would be
discovered on stage. So the copy is tested the way the store is: build a database
per test in `tmp_path`, copy, and read the result back through the REAL loader.

The load-bearing property is the last class: a duplicated session must be
independent of its source. `nodes` is keyed on `node_id` alone, so a naive copy
either collides or silently overwrites the original's rows.
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

from backend.auth import identity, schema as auth_schema
from backend.learning import store as learning_store
from backend.learning.contribution import ContributionState, PatchFile
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode

_SPEC = importlib.util.spec_from_file_location(
    "demo_checkpoints",
    Path(__file__).resolve().parents[1] / "tools" / "demo_checkpoints.py",
)
demo = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(demo)


OWNER_EMAIL = "demo-owner@example.test"


def _graph(repo="https://github.com/psf/requests") -> LearningGraph:
    graph = LearningGraph(repo_url=repo, goal={
        "goal_type": "contribute_code",
        "primary_goal": "add a getter",
        "contribution_context": "Add get_all to RequestsCookieJar",
    })
    previous = None
    for i in range(3):
        node = graph.add_node(LearningNode(
            title=f"Stop {i}",
            code_anchor=CodeAnchor(file="src/requests/cookies.py",
                                   line_start=1, line_end=9),
            lesson_brief={"priority": "required", "area_id": "a1",
                          "objective": f"claim {i}"},
        ))
        if previous:
            graph.add_edge(previous, node.id, kind="sequence")
        previous = node.id
    graph.set_current(next(iter(graph.nodes)))
    graph.areas = [{"id": "a1", "title": "Area", "why": "w", "order": 1}]
    return graph


@pytest.fixture
def source_db(tmp_path) -> tuple[Path, str, str]:
    """A database holding one real-shaped session, mid-contribution."""
    path = tmp_path / "source.db"
    learning_store.init_db(path)
    auth_schema.init_auth_schema(path)
    user_id = identity.create_user(OWNER_EMAIL, "Demo", db_path=path)

    graph = _graph()
    learning_store.create_session(graph, path, user_id=user_id)

    # State the product would have written: a walked stop, a journey event, and
    # a contribution stage carrying a patch.
    graph = learning_store.load_graph(graph.session_id, user_id, path)
    first = next(iter(graph.nodes))
    graph.nodes[first].visited = True
    graph.nodes[first].understanding_state = "understood"
    graph.nodes[first].attempts.append({
        "kind": "assessment", "answer": "a", "classification": "understood",
        "rationale": "r", "at": "2026-09-05T10:00:00Z",
    })
    graph.record_journey_event("jump", node_id=first)
    graph.contribution = ContributionState(
        stage="validate",
        plan={"steps": [{"title": "t", "detail": "d"}]},
        patch=[PatchFile(path="src/requests/cookies.py", contents="x = 1\n")],
        validation_command="pytest -q",
    )
    learning_store.save_graph(graph, path, user_id=user_id)
    return path, graph.session_id, user_id


class TestDiscovery:
    def test_session_tables_are_found_not_listed(self, source_db):
        path, _, _ = source_db
        connection = demo._connect(path)
        try:
            found = set(demo.session_tables(connection))
        finally:
            connection.close()
        # A table added later is carried without this file changing — which is
        # the reason discovery beats a hard-coded list.
        assert {"sessions", "nodes", "edges", "plan_nodes", "plan_edges"} <= found
        assert "users" not in found


class TestImport:
    def test_a_session_arrives_and_loads_through_the_real_loader(
        self, source_db, tmp_path
    ):
        path, session_id, user_id = source_db
        target = tmp_path / "demo.db"
        demo.do_import(_Args(source=str(path), session=[session_id],
                             db=str(target)))

        graph = learning_store.load_graph(session_id, user_id, target)
        assert graph is not None
        assert len(graph.nodes) == 3
        assert graph.contribution is not None
        assert graph.contribution.stage == "validate"
        assert graph.contribution.patch[0].path == "src/requests/cookies.py"

    def test_the_owning_account_comes_with_it(self, source_db, tmp_path):
        """Without the account row, `load_graph` filters the session away and the
        demo opens on an empty dashboard."""
        path, session_id, user_id = source_db
        target = tmp_path / "demo.db"
        demo.do_import(_Args(source=str(path), session=[session_id],
                             db=str(target)))
        assert identity.find_user_by_email(OWNER_EMAIL, db_path=target) is not None

    def test_the_plan_comes_with_it_so_start_over_still_works(
        self, source_db, tmp_path
    ):
        path, session_id, user_id = source_db
        target = tmp_path / "demo.db"
        demo.do_import(_Args(source=str(path), session=[session_id],
                             db=str(target)))
        graph = learning_store.load_graph(session_id, user_id, target)
        assert graph.has_plan is True

    def test_importing_twice_is_idempotent(self, source_db, tmp_path):
        """A re-import is a RESTORE — it replaces, it does not accumulate.

        `sessions` alone is not enough to assert that, and asserting it alone is
        how this shipped broken: `_copy_session` mints a fresh `node_id` per copy,
        so the second import inserted a whole second set of nodes under ids that
        collided with nothing, while `INSERT OR REPLACE` quietly replaced the one
        row whose primary key had not changed. On the presentation database that
        showed up as every stop appearing twice in the route.

        So every session-scoped table is counted, not just the one.
        """
        path, session_id, user_id = source_db
        target = tmp_path / "demo.db"

        demo.do_import(_Args(source=str(path), session=[session_id],
                             db=str(target)))
        connection = demo._connect(target)
        try:
            tables = demo.session_tables(connection)
            once = {t: connection.execute(
                f"SELECT COUNT(*) FROM {t} WHERE session_id = ?", (session_id,)
            ).fetchone()[0] for t in tables}
        finally:
            connection.close()

        demo.do_import(_Args(source=str(path), session=[session_id],
                             db=str(target)))
        connection = sqlite3.connect(target)
        try:
            twice = {t: connection.execute(
                f"SELECT COUNT(*) FROM {t} WHERE session_id = ?", (session_id,)
            ).fetchone()[0] for t in tables}
        finally:
            connection.close()

        assert once == twice
        assert once["sessions"] == 1
        assert once["nodes"] == 3

    def test_a_restore_replaces_a_session_that_was_walked_on(
        self, source_db, tmp_path
    ):
        """The case the runbook actually tells the presenter to run.

        A checkpoint gets dirtied by a stray click, and the fix is to import it
        again from the pristine copy. What comes back must be the pristine
        session, not the dirty one with a second copy layered over it.
        """
        path, session_id, user_id = source_db
        target = tmp_path / "demo.db"
        demo.do_import(_Args(source=str(path), session=[session_id],
                             db=str(target)))

        # Dirty it the way a click would: advance the stage.
        graph = learning_store.load_graph(session_id, user_id, target)
        graph.contribution.stage = "done"
        learning_store.save_graph(graph, target, user_id=user_id)

        demo.do_import(_Args(source=str(path), session=[session_id],
                             db=str(target)))

        graph = learning_store.load_graph(session_id, user_id, target)
        assert graph.contribution.stage == "validate"
        assert len(graph.nodes) == 3
        assert len({n.title for n in graph.nodes.values()}) == 3

    def test_it_refuses_the_real_database(self, source_db, tmp_path):
        path, session_id, _ = source_db
        real = tmp_path / "sessions.db"
        with pytest.raises(SystemExit, match="refusing"):
            demo.do_import(_Args(source=str(path), session=[session_id],
                                 db=str(real)))


class TestSnapshot:
    def _imported(self, source_db, tmp_path) -> tuple[Path, str, str]:
        path, session_id, user_id = source_db
        target = tmp_path / "demo.db"
        demo.do_import(_Args(source=str(path), session=[session_id],
                             db=str(target)))
        return target, session_id, user_id

    def test_a_checkpoint_is_a_second_independent_session(
        self, source_db, tmp_path, capsys
    ):
        target, session_id, user_id = self._imported(source_db, tmp_path)
        demo.do_snapshot(_Args(db=str(target), session=session_id,
                               name="01 · fresh"))
        new_id = _snapshot_id(capsys)

        assert new_id != session_id
        original = learning_store.load_graph(session_id, user_id, target)
        copy = learning_store.load_graph(new_id, user_id, target)
        assert original is not None and copy is not None
        assert len(copy.nodes) == len(original.nodes)

    def test_node_ids_are_remapped_so_the_two_cannot_collide(
        self, source_db, tmp_path, capsys
    ):
        """THE PROPERTY THIS CLASS EXISTS FOR.

        `nodes` is keyed on `node_id` ALONE, so reusing ids would either violate
        the primary key or silently reassign the original's rows to the copy —
        which would be discovered on stage, when the pristine session had
        quietly become the dirtied one.
        """
        target, session_id, user_id = self._imported(source_db, tmp_path)
        demo.do_snapshot(_Args(db=str(target), session=session_id, name="copy"))
        new_id = _snapshot_id(capsys)

        original = learning_store.load_graph(session_id, user_id, target)
        copy = learning_store.load_graph(new_id, user_id, target)
        assert set(original.nodes) & set(copy.nodes) == set()

    def test_the_remap_reaches_inside_json_payloads(
        self, source_db, tmp_path, capsys
    ):
        """`current_node_id` is a column; `journey_events` is JSON. A remap that
        only fixed columns would leave the copy pointing at the original's
        nodes."""
        target, session_id, user_id = self._imported(source_db, tmp_path)
        demo.do_snapshot(_Args(db=str(target), session=session_id, name="copy"))
        new_id = _snapshot_id(capsys)

        copy = learning_store.load_graph(new_id, user_id, target)
        assert copy.current_node_id in copy.nodes
        for event in copy.journey_events:
            if "node_id" in event:
                assert event["node_id"] in copy.nodes

    def test_learner_state_survives_the_copy(self, source_db, tmp_path, capsys):
        target, session_id, user_id = self._imported(source_db, tmp_path)
        demo.do_snapshot(_Args(db=str(target), session=session_id, name="copy"))
        copy = learning_store.load_graph(_snapshot_id(capsys), user_id, target)

        answered = [n for n in copy.nodes.values() if n.attempts]
        assert len(answered) == 1
        assert answered[0].understanding_state == "understood"
        assert copy.contribution.stage == "validate"
        assert copy.contribution.plan["steps"][0]["title"] == "t"

    def test_the_dossier_follows_the_copy(self, source_db, tmp_path, capsys):
        """`Locate` and the scope check read the boundary off the dossier, which
        is keyed by session_id — a checkpoint without it has an empty Locate.

        Written through `dossier_store`, the real writer, which also creates the
        table: it is made lazily on first use, so a database that has never held
        an investigation does not have it.
        """
        from backend.repo import dossier_store

        path, session_id, user_id = source_db
        dossier_store.save_investigation(
            session_id, "abc123",
            {"dossier": {"understanding": "u",
                         "change_boundary": {"target": [{"file": "a.py",
                                                         "symbol": "Jar"}]}},
             "accepted": True, "stop_reason": "contract_met"},
            path,
        )
        target = tmp_path / "demo.db"
        demo.do_import(_Args(source=str(path), session=[session_id],
                             db=str(target)))
        demo.do_snapshot(_Args(db=str(target), session=session_id, name="copy"))
        new_id = _snapshot_id(capsys)

        carried = dossier_store.load_investigation(new_id, "abc123", db_path=target)
        assert carried is not None
        assert carried["dossier"]["change_boundary"]["target"][0]["symbol"] == "Jar"

    def test_the_checkpoint_is_named(self, source_db, tmp_path, capsys):
        target, session_id, user_id = self._imported(source_db, tmp_path)
        demo.do_snapshot(_Args(db=str(target), session=session_id,
                               name="03 · ready to implement"))
        new_id = _snapshot_id(capsys)
        summary = learning_store.get_session_summary(new_id, user_id, target)
        assert summary["title"] == "03 · ready to implement"

    def test_dirtying_a_checkpoint_leaves_the_source_pristine(
        self, source_db, tmp_path, capsys
    ):
        """The whole reason checkpoints are copies rather than restore points."""
        target, session_id, user_id = self._imported(source_db, tmp_path)
        demo.do_snapshot(_Args(db=str(target), session=session_id, name="copy"))
        new_id = _snapshot_id(capsys)

        copy = learning_store.load_graph(new_id, user_id, target)
        for node in copy.nodes.values():
            node.visited = True
            node.user_override = "skip"
        copy.contribution = None
        learning_store.save_graph(copy, target, user_id=user_id)

        original = learning_store.load_graph(session_id, user_id, target)
        assert original.contribution is not None
        assert sum(1 for n in original.nodes.values() if n.visited) == 1

    def test_it_refuses_the_real_database(self, source_db, tmp_path):
        _, session_id, _ = source_db
        with pytest.raises(SystemExit, match="refusing"):
            demo.do_snapshot(_Args(db=str(tmp_path / "sessions.db"),
                                   session=session_id, name="x"))

    def test_an_unknown_session_is_refused_rather_than_silently_empty(
        self, source_db, tmp_path
    ):
        target, _, _ = self._imported(source_db, tmp_path)
        with pytest.raises(SystemExit, match="not found"):
            demo.do_snapshot(_Args(db=str(target), session="0" * 32, name="x"))


class _Args:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _snapshot_id(capsys) -> str:
    for line in capsys.readouterr().out.splitlines():
        if line.strip().startswith("session_id"):
            return line.split()[-1]
    raise AssertionError("snapshot printed no session_id")
