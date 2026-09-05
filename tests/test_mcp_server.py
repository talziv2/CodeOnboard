"""The MCP bridge — the two tools, and the boundary they must not cross.

Run with: uv run pytest tests/test_mcp_server.py -v

These call the tool functions directly with the environment pointed at a database
built in `tmp_path`. The wire protocol belongs to the official SDK and is not
retested here; what is tested is everything this repository is responsible for:

  IDENTITY   the session comes from the environment, never from the model, and a
             session that is not this user's is indistinguishable from one that
             does not exist (D20 — 404, never 403).
  READ-ONLY  nothing here writes a row, and nothing returns a verdict that could
             become learner evidence (D8).
  HONESTY    `check_scope` compares paths and says so. A result that lists four
             findings and stays silent about syntax, symbols and tests would be
             read as a full check that passed.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.auth import identity, schema as auth_schema
from backend.learning import store as learning_store
from backend.learning.contribution import ContributionState
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.repo import dossier_store

import backend.mcp_server as srv

OWNER_EMAIL = "mcp-owner@example.test"
OTHER_EMAIL = "someone-else@example.test"
COMMIT = "e8d2c015aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

BOUNDARY = {
    "target": [
        {"file": "src/requests/cookies.py", "symbol": "RequestsCookieJar.get_all",
         "why_here": "the jar owns name lookup"},
    ],
    "must_not_change": [
        {"file": "src/requests/cookies.py", "symbol": "RequestsCookieJar.get",
         "why_not": "existing callers rely on the single-value contract"},
    ],
    "existing_tests": [
        {"file": "tests/test_requests.py", "symbol": "TestRequests",
         "what_it_guards": "cookie conflict behaviour"},
    ],
    "edge_cases": [
        {"case": "a cookie whose value is None",
         "why_it_bites": "_find_no_duplicates treats it as absent"},
        {"case": "same name, two domains", "why_it_bites": "get() raises"},
    ],
}
DOSSIER = {
    "change_boundary": BOUNDARY,
    "contracts": [{"file": "src/requests/cookies.py", "symbol": "get",
                   "contract": "returns exactly one value or raises"}],
}


@pytest.fixture
def session(tmp_path, monkeypatch):
    """A ready contribution session in a throwaway database, with the server's
    environment pointed at it. Returns (session_id, user_id, other_user_id)."""
    db = tmp_path / "mcp.db"
    learning_store.init_db(db)
    auth_schema.init_auth_schema(db)
    user_id = identity.create_user(OWNER_EMAIL, "Owner", db_path=db)
    other_id = identity.create_user(OTHER_EMAIL, "Other", db_path=db)

    graph = LearningGraph(
        repo_url="https://github.com/psf/requests",
        goal={"goal_type": "contribute_code", "primary_goal": "add a getter",
              "contribution_context": "Add get_all(name) to RequestsCookieJar."},
    )
    for i in range(2):
        node = graph.add_node(LearningNode(
            title=f"Stop {i}",
            code_anchor=CodeAnchor(file="src/requests/cookies.py",
                                   line_start=1, line_end=9, symbol="Jar"),
            lesson_brief={"priority": "required", "area_id": "a1",
                          "objective": f"Explain thing {i}"},
        ))
        node.understanding_state = "understood"
        node.attempts.append({
            "kind": "assessment", "answer": "a", "classification": "understood",
            "rationale": "r", "at": "2026-09-05T10:00:00Z",
        })
    learning_store.create_session(graph, db, user_id=user_id)
    dossier_store.save_investigation(
        graph.session_id, COMMIT,
        {"dossier": DOSSIER, "accepted": True}, db,
    )

    monkeypatch.setenv("CODEONBOARD_DB", str(db))
    monkeypatch.setenv("CODEONBOARD_SESSION", graph.session_id)
    monkeypatch.setenv("CODEONBOARD_USER", user_id)
    # The commit is normally read from the shared checkout. Nothing in this test
    # has one, and the server must never clone to get it.
    monkeypatch.setattr(srv, "_commit", lambda graph: COMMIT)
    return graph.session_id, user_id, other_id


class TestIdentity:
    def test_the_session_comes_from_the_environment_not_the_model(self, session):
        """Neither tool takes a session_id — there is nothing for a model to
        mistype, guess, or be talked into changing."""
        import inspect
        for tool in (srv.get_contribution_context, srv.check_scope):
            assert "session_id" not in inspect.signature(tool).parameters

    def test_a_session_belonging_to_someone_else_is_not_found(
        self, session, monkeypatch
    ):
        """D20: not yours and not there are indistinguishable. The refusal must
        not leak that the session exists."""
        _, _, other_id = session
        monkeypatch.setenv("CODEONBOARD_USER", other_id)
        with pytest.raises(ValueError, match="session not found"):
            srv.get_contribution_context()

    def test_a_server_started_without_a_session_says_so(self, session, monkeypatch):
        monkeypatch.delenv("CODEONBOARD_SESSION")
        with pytest.raises(ValueError, match="CODEONBOARD_SESSION"):
            srv.check_scope(["a.py"])

    def test_an_unknown_session_is_not_found(self, session, monkeypatch):
        monkeypatch.setenv("CODEONBOARD_SESSION", "0" * 32)
        with pytest.raises(ValueError, match="session not found"):
            srv.get_contribution_context()


class TestContext:
    def test_it_returns_the_live_session_context(self, session):
        ctx = srv.get_contribution_context()
        assert ctx["task"] == "Add get_all(name) to RequestsCookieJar."
        assert ctx["repository"]["commit"] == COMMIT
        assert ctx["change_boundary"]["target"][0]["symbol"] \
            == "RequestsCookieJar.get_all"
        assert ctx["learner"]["ready"] is True
        assert ctx["learner"]["demonstrated"] == 2
        assert len(ctx["learner"]["demonstrated_concepts"]) == 2

    def test_it_refuses_a_session_that_is_not_ready(self, session, monkeypatch):
        """The gate is the product. It holds at the bridge too."""
        session_id, user_id, _ = session
        db = Path(os.environ["CODEONBOARD_DB"])
        graph = learning_store.load_graph(session_id, user_id, db)
        for node in graph.nodes.values():
            node.understanding_state = "not_started"
            node.attempts.clear()
        learning_store.save_graph(graph, db, user_id=user_id)
        with pytest.raises(ValueError, match="not yet demonstrated"):
            srv.get_contribution_context()

    def test_it_refuses_when_the_investigation_recorded_no_boundary(
        self, session, monkeypatch
    ):
        """DI-8. A confident schema wrapped around an empty boundary is worse
        than an error."""
        monkeypatch.setattr(srv, "_dossier", lambda graph, commit: {})
        with pytest.raises(ValueError, match="no change boundary"):
            srv.get_contribution_context()

    def test_a_missing_survey_costs_one_field_not_the_handoff(
        self, session, monkeypatch
    ):
        ctx = srv.get_contribution_context()
        assert ctx["learner"]["not_taught"] == []
        assert ctx["change_boundary"]["target"]        # the useful part survives


class TestCheckScope:
    def test_an_in_scope_change_passes(self, session):
        out = srv.check_scope(
            ["src/requests/cookies.py", "tests/test_requests.py"]
        )
        assert out["passed"] is True
        assert out["outside_boundary"] == []

    def test_an_out_of_scope_change_fails_and_names_the_file(self, session):
        out = srv.check_scope(["src/requests/cookies.py", "setup.py"])
        assert out["passed"] is False
        assert out["outside_boundary"] == ["setup.py"]

    def test_it_says_what_it_did_not_check(self, session):
        """The claim is a path comparison. Silence about the rest reads as a
        pass — the same defect B4.3 fixed on the Validate surface."""
        out = srv.check_scope(["src/requests/cookies.py"])
        assert "syntax" in out["not_checked"]
        assert "repository tests" in out["not_checked"]
        assert out["checked"].startswith("file paths")

    def test_a_protected_symbol_is_reported_and_never_evaluated(self, session):
        out = srv.check_scope(["src/requests/cookies.py"])
        assert out["unchecked_symbols"] == [
            "src/requests/cookies.py:RequestsCookieJar.get"
        ]
        assert out["passed"] is True

    def test_an_empty_list_is_not_an_error(self, session):
        out = srv.check_scope([])
        assert out["passed"] is True
        assert out["in_boundary"] == []


class TestBoundary:
    """What this server must never do."""

    def test_it_never_writes(self, session):
        """A coding agent's success is not evidence about a learner (D8), and the
        rule is kept structurally: nothing here can write a row."""
        session_id, user_id, _ = session
        db = Path(os.environ["CODEONBOARD_DB"])
        before = db.read_bytes()
        srv.get_contribution_context()
        srv.check_scope(["src/requests/cookies.py", "setup.py"])
        assert db.read_bytes() == before

    def test_readiness_is_unchanged_by_anything_the_agent_reports(self, session):
        session_id, user_id, _ = session
        db = Path(os.environ["CODEONBOARD_DB"])
        graph = learning_store.load_graph(session_id, user_id, db)
        before = graph.progress_summary() if hasattr(graph, "progress_summary") else None
        srv.check_scope(["setup.py"])          # an out-of-scope change
        after = learning_store.load_graph(session_id, user_id, db)
        assert [n.understanding_state for n in after.nodes.values()] \
            == [n.understanding_state for n in graph.nodes.values()]

    def test_the_module_imports_nothing_that_could_grade_or_mutate(self):
        """The Tutor's structural rule, applied to the bridge: an AST walk, so a
        future edit that reaches for the learning engine fails the build rather
        than a review."""
        import ast
        source = Path(srv.__file__).read_text(encoding="utf-8")
        forbidden = {
            "run_grader", "mutate_graph", "record_attempt", "save_graph",
            "adaptation", "retry", "clone_repo",
        }
        names: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ImportFrom):
                names.update(a.name for a in node.names)
                names.add((node.module or "").rsplit(".", 1)[-1])
            elif isinstance(node, ast.Import):
                names.update(a.name.rsplit(".", 1)[-1] for a in node.names)
        assert not (names & forbidden), f"the bridge must not import {names & forbidden}"

    def test_there_are_exactly_two_tools(self):
        """One real runtime capability plus its context. A third tool needs an
        argument, not an opportunity."""
        import ast
        source = Path(srv.__file__).read_text(encoding="utf-8")
        assert source.count("@server.tool(") == 2
        decorated = {
            node.name
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.FunctionDef) and node.decorator_list
        }
        assert decorated == {"get_contribution_context", "check_scope"}
