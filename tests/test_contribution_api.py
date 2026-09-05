# The contribution routes, end to end over HTTP against a real SQLite round-trip.
#
# Two things this file is for that no unit test can reach:
#
#   THE GATE ACTUALLY REFUSES. `progress.ready_to_implement` returning False is
#   one thing; `/contribution/plan` answering 409 because of it is the product
#   claim. The demo says blocking required knowledge stops implementation, and
#   this is where that is either true or a caption.
#
#   THE OVERRIDE IS A DECISION AND NOT EVIDENCE. `/contribution/proceed` unblocks
#   the road, and the payload's blockers, counts and readiness are IDENTICAL
#   afterwards. That is the `continue_past` bargain, and it is the one place a
#   learner action could quietly become a claim about their understanding.

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import backend.api as api
from backend.learning import store as learning_store
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from tests.conftest import TEST_USER_ID


REPO_URL = "https://github.com/psf/requests"
GOAL = {
    "primary_goal": "add a getter to the cookie jar",
    "goal_type": "contribute_code",
    "focus_area": "cookies",
    "code_depth": "working",
    "depth": "moderate",
    "contribution_context": (
        "Add RequestsCookieJar.get_all(name) returning every value stored under "
        "that name, and cover its boundary cases with tests."
    ),
}

BOUNDARY = {
    "target": [
        {"file": "src/requests/cookies.py", "symbol": "RequestsCookieJar.get_all",
         "why_here": "the jar owns name lookup"},
    ],
    "must_not_change": [
        {"file": "src/requests/sessions.py", "symbol": "Session.send",
         "why_not": "unrelated"},
    ],
    "existing_tests": [
        {"file": "tests/test_requests.py", "symbol": "TestRequests",
         "what_it_guards": "conflict behaviour"},
    ],
    "edge_cases": [
        {"case": "same name, two domains", "why_it_bites": "get() refuses",
         "file": "src/requests/cookies.py", "symbol": "RequestsCookieJar._find"},
    ],
}


@pytest.fixture(autouse=True)
def _env_and_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(api, "SESSIONS_DB_PATH", tmp_path / "sessions.db")
    monkeypatch.setattr(api.anthropic, "Anthropic", lambda **kw: MagicMock())
    # The boundary lives on the stored dossier. Stubbed at the store rather than
    # written through it, so these tests never need a clone or a commit sha.
    monkeypatch.setattr(api, "clone_repo", lambda url: "/tmp/repo")
    monkeypatch.setattr(api, "get_commit_sha", lambda path: "abc123")
    monkeypatch.setattr(
        api.dossier_store, "load_investigation",
        lambda session_id, commit, db_path=None: {
            "dossier": {"change_boundary": BOUNDARY}
        },
    )


@pytest.fixture
def client():
    return TestClient(api.app)


def _graph(demonstrated: int, required: int = 2) -> LearningGraph:
    graph = LearningGraph(repo_url=REPO_URL, goal=GOAL)
    previous = None
    for i in range(required):
        node = graph.add_node(LearningNode(
            title=f"Concept {i}",
            code_anchor=CodeAnchor(file="src/requests/cookies.py",
                                   line_start=1, line_end=10),
            lesson_brief={"priority": "required", "area_id": "a1",
                          "objective": f"Explain concept {i}"},
        ))
        if i < demonstrated:
            node.understanding_state = "understood"
            node.attempts.append({
                "kind": "assessment", "answer": "a", "classification": "understood",
                "rationale": "r", "at": "2026-01-01T00:00:00Z",
            })
        if previous:
            graph.add_edge(previous, node.id, kind="sequence")
        previous = node.id
    graph.set_current(next(iter(graph.nodes)))
    return graph


def _seed(demonstrated: int) -> str:
    graph = _graph(demonstrated)
    learning_store.create_session(graph, api.SESSIONS_DB_PATH, user_id=TEST_USER_ID)
    return graph.session_id


PATCH_FILES = [
    {"path": "src/requests/cookies.py",
     "contents": "class RequestsCookieJar:\n    def get_all(self, name):\n        return []\n"},
    {"path": "tests/test_requests.py",
     "contents": "class TestRequests:\n    def test_get_all(self):\n        assert True\n"},
]


class TestThePayload:
    def test_a_contribution_session_reports_its_task_and_boundary(self, client):
        session_id = _seed(demonstrated=2)
        body = client.get(f"/session/{session_id}/contribution").json()
        assert body["available"] is True
        assert "get_all" in body["task"]
        assert body["boundary"]["target"][0]["file"] == "src/requests/cookies.py"
        assert body["ready"]["ready"] is True
        assert body["validation_command"] == "pytest tests/test_requests.py -q"

    def test_a_non_contribution_session_answers_rather_than_404s(self, client):
        """A 404 would make the frontend branch on goal type before it is allowed
        to ask a question, which is a learning decision in the client."""
        graph = _graph(demonstrated=1)
        graph.goal = {**GOAL, "goal_type": "understand_architecture",
                      "contribution_context": None}
        learning_store.create_session(graph, api.SESSIONS_DB_PATH, user_id=TEST_USER_ID)
        body = client.get(f"/session/{graph.session_id}/contribution").json()
        assert body["available"] is False
        assert body["state"] is None

    def test_another_users_session_is_404_not_403(self, client):
        session_id = _seed(demonstrated=2)
        with patch.object(api.learning_store, "load_graph", return_value=None):
            response = client.get(f"/session/{session_id}/contribution")
        assert response.status_code == 404


class TestTheGateRefuses:
    def test_planning_is_refused_while_a_required_concept_is_undemonstrated(self, client):
        session_id = _seed(demonstrated=1)
        response = client.post(f"/session/{session_id}/contribution/plan")
        assert response.status_code == 409
        assert response.json()["detail"] == "not_ready_to_implement"

    def test_saving_a_patch_is_refused_too(self, client):
        """The gate is on the STAGE, not on one endpoint — otherwise a client
        that skipped `/plan` would be inside it anyway."""
        session_id = _seed(demonstrated=0)
        response = client.post(
            f"/session/{session_id}/contribution/patch", json={"files": PATCH_FILES},
        )
        assert response.status_code == 409

    def test_planning_succeeds_once_everything_is_demonstrated(self, client):
        session_id = _seed(demonstrated=2)
        with patch.object(api.contribution_agent, "build_plan",
                          return_value={"steps": [{"title": "Add the method", "detail": "d"}]}):
            response = client.post(f"/session/{session_id}/contribution/plan")
        assert response.status_code == 200
        assert response.json()["state"]["plan"]["steps"][0]["title"] == "Add the method"

    def test_the_plan_is_written_from_what_was_demonstrated(self, client):
        """Not from the whole curriculum. The plan is written in the vocabulary
        the learner has actually earned — that is what makes the stage read as
        the end of the journey rather than the start of a different product."""
        session_id = _seed(demonstrated=2)
        with patch.object(api.contribution_agent, "build_plan",
                          return_value={"steps": []}) as build:
            client.post(f"/session/{session_id}/contribution/plan")
        demonstrated = build.call_args.kwargs["demonstrated"]
        assert demonstrated == ["Explain concept 0", "Explain concept 1"]
        assert "get_all" in build.call_args.kwargs["task"]


class TestTheOverrideIsNotEvidence:
    def test_proceeding_unblocks_the_stage(self, client):
        session_id = _seed(demonstrated=1)
        assert client.post(f"/session/{session_id}/contribution/plan").status_code == 409
        client.post(f"/session/{session_id}/contribution/proceed")
        with patch.object(api.contribution_agent, "build_plan",
                          return_value={"steps": [{"title": "t", "detail": "d"}]}):
            assert client.post(f"/session/{session_id}/contribution/plan").status_code == 200

    def test_proceeding_changes_nothing_about_what_was_demonstrated(self, client):
        """THE ONE TEST THIS CLASS EXISTS FOR. The blockers, the counts and the
        readiness verdict are identical afterwards — the decision unlocks a road
        and never becomes a claim about the learner."""
        session_id = _seed(demonstrated=1)
        before = client.get(f"/session/{session_id}/contribution").json()["ready"]
        after = client.post(
            f"/session/{session_id}/contribution/proceed"
        ).json()["ready"]
        assert after == before
        assert after["ready"] is False
        assert after["demonstrated"] == 1

    def test_proceeding_does_not_touch_the_learning_graph(self, client):
        """Byte-identical, the way `test_tutor_boundary` asserts it for a turn."""
        session_id = _seed(demonstrated=1)
        before = learning_store.load_graph(
            session_id, TEST_USER_ID, api.SESSIONS_DB_PATH
        ).to_dict()
        client.post(f"/session/{session_id}/contribution/proceed")
        after = learning_store.load_graph(
            session_id, TEST_USER_ID, api.SESSIONS_DB_PATH
        ).to_dict()
        # `journey_events` is the one intended difference: the decision is
        # recorded, which is what makes it auditable rather than invisible.
        assert after.pop("journey_events") != before.pop("journey_events")
        assert after == before

    def test_the_decision_is_recorded_as_a_journey_event(self, client):
        session_id = _seed(demonstrated=1)
        client.post(f"/session/{session_id}/contribution/proceed")
        graph = learning_store.load_graph(session_id, TEST_USER_ID, api.SESSIONS_DB_PATH)
        kinds = [e.get("kind") for e in graph.journey_events]
        assert "contribution_proceeded_unready" in kinds

    def test_proceeding_twice_records_once(self, client):
        session_id = _seed(demonstrated=1)
        client.post(f"/session/{session_id}/contribution/proceed")
        client.post(f"/session/{session_id}/contribution/proceed")
        graph = learning_store.load_graph(session_id, TEST_USER_ID, api.SESSIONS_DB_PATH)
        events = [e for e in graph.journey_events
                  if e.get("kind") == "contribution_proceeded_unready"]
        assert len(events) == 1


class TestPatchAndValidation:
    def _ready_session(self, client) -> str:
        session_id = _seed(demonstrated=2)
        with patch.object(api.contribution_agent, "build_plan",
                          return_value={"steps": [{"title": "t", "detail": "d"}]}):
            client.post(f"/session/{session_id}/contribution/plan")
        return session_id

    def test_a_patch_is_stored_and_survives_a_reload(self, client):
        session_id = self._ready_session(client)
        client.post(f"/session/{session_id}/contribution/patch",
                    json={"files": PATCH_FILES})
        body = client.get(f"/session/{session_id}/contribution").json()
        assert [f["path"] for f in body["state"]["patch"]] == [
            "src/requests/cookies.py", "tests/test_requests.py",
        ]
        assert body["state"]["stage"] == "implement"

    def test_an_oversized_patch_is_refused(self, client):
        session_id = self._ready_session(client)
        files = [{"path": f"f{i}.py", "contents": "x = 1\n"} for i in range(20)]
        response = client.post(f"/session/{session_id}/contribution/patch",
                               json={"files": files})
        assert response.status_code == 400
        assert response.json()["detail"] == "patch_too_large"

    def test_validation_reports_scope_without_running_anything(self, client):
        session_id = self._ready_session(client)
        client.post(f"/session/{session_id}/contribution/patch",
                    json={"files": PATCH_FILES})
        body = client.post(f"/session/{session_id}/contribution/validate").json()
        check = body["state"]["scope_check"]
        assert check["passed"] is True
        assert check["symbol_expected"] == "get_all"
        assert check["symbol_found"] is True
        assert check["test_files"] == ["tests/test_requests.py"]

    def test_a_file_outside_the_boundary_fails_the_scope_check(self, client):
        session_id = self._ready_session(client)
        client.post(f"/session/{session_id}/contribution/patch", json={"files": [
            *PATCH_FILES,
            {"path": "src/requests/adapters.py", "contents": "x = 1\n"},
        ]})
        body = client.post(f"/session/{session_id}/contribution/validate").json()
        assert body["state"]["scope_check"]["passed"] is False
        assert body["state"]["scope_check"]["outside_boundary"] == [
            "src/requests/adapters.py",
        ]

    def test_editing_the_patch_clears_findings_about_the_previous_one(self, client):
        """Left in place they would be read as findings about what is on screen
        now, which is the one way a scope check could report something untrue."""
        session_id = self._ready_session(client)
        client.post(f"/session/{session_id}/contribution/patch",
                    json={"files": PATCH_FILES})
        client.post(f"/session/{session_id}/contribution/validate")
        body = client.post(f"/session/{session_id}/contribution/patch",
                           json={"files": PATCH_FILES[:1]}).json()
        assert body["state"]["scope_check"] is None
        assert body["state"]["review"] is None

    def test_validating_without_a_patch_is_refused(self, client):
        session_id = self._ready_session(client)
        response = client.post(f"/session/{session_id}/contribution/validate")
        assert response.status_code == 409


class TestReviewAndPr:
    def _with_patch(self, client) -> str:
        session_id = _seed(demonstrated=2)
        with patch.object(api.contribution_agent, "build_plan",
                          return_value={"steps": []}):
            client.post(f"/session/{session_id}/contribution/plan")
        client.post(f"/session/{session_id}/contribution/patch",
                    json={"files": PATCH_FILES})
        return session_id

    def test_review_is_an_opinion_carried_as_one(self, client):
        session_id = self._with_patch(client)
        with patch.object(api.contribution_agent, "review_patch", return_value={
            "meets_task": True, "observations": ["adds get_all"], "concerns": [],
        }):
            body = client.post(f"/session/{session_id}/contribution/review").json()
        assert body["state"]["review"]["meets_task"] is True
        assert body["state"]["stage"] == "review"

    def test_the_pr_summary_ends_the_stage(self, client):
        session_id = self._with_patch(client)
        with patch.object(api.contribution_agent, "build_pr", return_value={
            "title": "Add RequestsCookieJar.get_all",
            "body": "…", "testing_notes": "Not run.",
        }):
            body = client.post(f"/session/{session_id}/contribution/pr").json()
        assert body["state"]["stage"] == "done"
        assert body["state"]["pr"]["title"].startswith("Add ")


class TestPersistence:
    def test_the_whole_stage_survives_a_round_trip(self, client):
        session_id = _seed(demonstrated=2)
        with patch.object(api.contribution_agent, "build_plan",
                          return_value={"steps": [{"title": "t", "detail": "d"}]}):
            client.post(f"/session/{session_id}/contribution/plan")
        client.post(f"/session/{session_id}/contribution/patch",
                    json={"files": PATCH_FILES})
        client.post(f"/session/{session_id}/contribution/validate")

        graph = learning_store.load_graph(session_id, TEST_USER_ID, api.SESSIONS_DB_PATH)
        assert graph.contribution is not None
        assert graph.contribution.stage == "validate"
        assert len(graph.contribution.patch) == 2
        assert graph.contribution.scope_check.passed is True

    def test_a_session_without_one_loads_with_none(self, client):
        """Every session stored before the column existed, and every session that
        never entered the stage. No SCHEMA_VERSION bump, so none of them became
        invisible."""
        session_id = _seed(demonstrated=1)
        graph = learning_store.load_graph(session_id, TEST_USER_ID, api.SESSIONS_DB_PATH)
        assert graph.contribution is None

    def test_the_contribution_is_never_written_to_a_plan_table(self):
        """D16. The plan tables' column list IS the plan/state partition, and a
        patch is learner-produced from end to end."""
        import backend.learning.store as store
        assert "contribution" not in store._CREATE_PLAN_NODES
        assert "contribution" not in store._CREATE_PLAN_EDGES

    def test_start_over_discards_it(self, client):
        session_id = _seed(demonstrated=2)
        with patch.object(api.contribution_agent, "build_plan",
                          return_value={"steps": [{"title": "t", "detail": "d"}]}):
            client.post(f"/session/{session_id}/contribution/plan")
        client.post(f"/session/{session_id}/contribution/patch",
                    json={"files": PATCH_FILES})

        response = client.post(f"/session/{session_id}/reset")
        assert response.status_code == 200
        graph = learning_store.load_graph(session_id, TEST_USER_ID, api.SESSIONS_DB_PATH)
        assert graph.contribution is None
        # The TASK survives: it is `goal["contribution_context"]`, which is
        # plan-side. Starting over re-runs the same contribution against a fresh
        # route rather than losing what the learner came to do.
        assert "get_all" in graph.goal["contribution_context"]

    def test_the_reset_summary_counts_what_it_discarded(self, client):
        session_id = _seed(demonstrated=2)
        with patch.object(api.contribution_agent, "build_plan",
                          return_value={"steps": []}):
            client.post(f"/session/{session_id}/contribution/plan")
        client.post(f"/session/{session_id}/contribution/patch",
                    json={"files": PATCH_FILES})
        body = client.post(f"/session/{session_id}/reset").json()
        assert body["discarded"]["contribution_patch_files"] == 2


class TestThePrSummaryReportsWhatWasChecked:
    """Three things, kept apart: checked / recommended / not executed.

    The first version reported only the last two. That is honest and incomplete —
    it understates the change by omitting the checks that DID pass, and leaves a
    reader to assume nothing was verified at all.
    """

    def _with_validated_patch(self, client) -> str:
        session_id = _seed(demonstrated=2)
        with patch.object(api.contribution_agent, "build_plan",
                          return_value={"steps": []}):
            client.post(f"/session/{session_id}/contribution/plan")
        client.post(f"/session/{session_id}/contribution/patch",
                    json={"files": PATCH_FILES})
        client.post(f"/session/{session_id}/contribution/validate")
        return session_id

    def test_the_scope_check_reaches_the_pr_agent(self, client):
        session_id = self._with_validated_patch(client)
        with patch.object(api.contribution_agent, "build_pr", return_value={
            "title": "t", "body": "b", "testing_notes": "n",
        }) as build:
            client.post(f"/session/{session_id}/contribution/pr")
        check = build.call_args.kwargs["scope_check"]
        assert check is not None
        assert check.passed is True
        assert check.test_files == ["tests/test_requests.py"]

    def test_skipping_validate_passes_none_rather_than_a_fiction(self, client):
        """The notes then say no automatic checks were run, instead of implying
        some were."""
        session_id = _seed(demonstrated=2)
        with patch.object(api.contribution_agent, "build_plan",
                          return_value={"steps": []}):
            client.post(f"/session/{session_id}/contribution/plan")
        client.post(f"/session/{session_id}/contribution/patch",
                    json={"files": PATCH_FILES})
        with patch.object(api.contribution_agent, "build_pr", return_value={
            "title": "t", "body": "b", "testing_notes": "n",
        }) as build:
            client.post(f"/session/{session_id}/contribution/pr")
        assert build.call_args.kwargs["scope_check"] is None

    def test_the_rendered_checks_name_what_passed_and_what_was_not_checked(self):
        from backend.agents.contribution.agent import _checks_text
        from backend.learning import contribution as contribution_model

        # A boundary whose protected symbol sits in the file the patch TOUCHES —
        # the module fixture protects `sessions.py`, which this patch never
        # opens, and an unchecked constraint in an unopened file is correctly
        # not reported.
        boundary = {
            **BOUNDARY,
            "must_not_change": [
                {"file": "src/requests/cookies.py",
                 "symbol": "RequestsCookieJar.get", "why_not": "public contract"},
            ],
        }
        check = contribution_model.check_scope(
            [contribution_model.PatchFile(
                path="src/requests/cookies.py",
                contents="class RequestsCookieJar:\n    def get_all(self):\n        return []\n")],
            boundary,
        )
        text = _checks_text(check)
        assert "path scope: PASSED" in text
        assert "syntax: every submitted Python file parses" in text
        assert "NOT checked" in text and "compares file paths" in text

    def test_no_checks_is_stated_rather_than_implied(self):
        from backend.agents.contribution.agent import _checks_text
        assert "no automatic checks were run" in _checks_text(None)


class TestHandoff:
    """`GET /contribution/handoff` — what leaves for the learner's coding agent.

    The gate holds here too: an unready session gets no handoff, because the
    whole product claim is that blocking required knowledge stops implementation.
    And the payload is the SAME function the MCP tool calls, so what the learner
    reads on screen and what the agent receives cannot diverge.
    """

    def test_a_ready_session_hands_over_code_and_learner_context(self, client):
        session_id = _seed(demonstrated=2)
        body = client.get(f"/session/{session_id}/contribution/handoff").json()
        ctx = body["context"]
        assert "get_all" in ctx["task"]
        assert ctx["repository"]["commit"] == "abc123"
        assert ctx["change_boundary"]["target"][0]["symbol"] \
            == "RequestsCookieJar.get_all"
        assert ctx["learner"]["ready"] is True
        assert ctx["learner"]["demonstrated"] == 2

    def test_the_gate_refuses_a_handoff_the_learner_has_not_earned(self, client):
        session_id = _seed(demonstrated=1)
        r = client.get(f"/session/{session_id}/contribution/handoff")
        assert r.status_code == 409
        assert r.json()["detail"] == "not_ready_to_implement"

    def test_a_session_with_no_boundary_is_refused_not_hollowed_out(
        self, client, monkeypatch
    ):
        """DI-8. A confident schema wrapped around an empty boundary is worse
        than an error, because the schema is what makes a reader trust it."""
        monkeypatch.setattr(
            api.dossier_store, "load_investigation",
            lambda session_id, commit, db_path=None: {"dossier": {}},
        )
        session_id = _seed(demonstrated=2)
        r = client.get(f"/session/{session_id}/contribution/handoff")
        assert r.status_code == 409
        assert r.json()["detail"] == "no_change_boundary"

    def test_it_carries_the_config_that_points_an_agent_at_this_session(self, client):
        session_id = _seed(demonstrated=2)
        setup = client.get(f"/session/{session_id}/contribution/handoff").json()["setup"]
        server = setup["mcp_json"]["mcpServers"]["codeonboard"]
        assert server["type"] == "stdio"
        assert server["env"]["CODEONBOARD_SESSION"] == session_id
        assert server["env"]["CODEONBOARD_USER"] == TEST_USER_ID
        # `--directory` rather than a `cwd` key: `.mcp.json` does not honour one,
        # and without it the module cannot be found. Measured against the real
        # client, so it is asserted rather than remembered.
        assert "--directory" in server["args"]
        assert server["args"][-2:] == ["-m", "backend.mcp_server"]

    def test_the_launch_link_points_at_the_project_local_working_copy(
        self, client, monkeypatch, tmp_path
    ):
        """An ABSOLUTE path, DERIVED from the project root — not a slug, and not
        configuration.

        `repo=<owner>/<name>` was tried first and is not reliable: Claude Code
        resolves a slug only against clones it has already opened, and when it
        cannot it opens somewhere else rather than failing. Measured on a real
        machine: no clone existed, the link opened HOME, and the MCP server was
        simply absent from the session.
        """
        monkeypatch.setattr(api, "PROJECT_ROOT", tmp_path)
        (tmp_path / "workspace" / "psf" / "requests").mkdir(parents=True)
        session_id = _seed(demonstrated=2)
        setup = client.get(f"/session/{session_id}/contribution/handoff").json()["setup"]

        assert setup["deep_link"].startswith("claude-cli://open?cwd=")
        assert setup["workspace"].endswith("workspace/psf/requests")
        assert "repo=" not in setup["deep_link"]
        # Derived from the session's own repository URL, so a second machine
        # reproduces it by preparing the same relative directory.
        assert (tmp_path / "workspace" / "psf" / "requests").as_posix()             == setup["workspace"]

    def test_no_prepared_working_copy_means_no_link_rather_than_a_guess(
        self, client, monkeypatch, tmp_path
    ):
        """DI-8 at the launch control: refuse rather than fabricate. A button
        that silently opens the wrong directory is worse than no button."""
        monkeypatch.setattr(api, "PROJECT_ROOT", tmp_path)
        session_id = _seed(demonstrated=2)
        setup = client.get(f"/session/{session_id}/contribution/handoff").json()["setup"]
        assert setup["deep_link"] is None
        assert setup["workspace"] is None

    def test_the_working_copy_is_never_the_shared_grounding_checkout(
        self, client, monkeypatch, tmp_path
    ):
        """THE INVARIANT THAT KEEPS TWO CHECKOUTS APART.

        `data/repos/<owner>/<name>` is one shared, pinned checkout that
        `anchors.resolve` reads for every session. A coding agent editing it
        would move the ground under every lesson everywhere, so the writable copy
        must never resolve inside `data/`.
        """
        monkeypatch.setattr(api, "PROJECT_ROOT", tmp_path)
        (tmp_path / "workspace" / "psf" / "requests").mkdir(parents=True)
        workspace = api.claude_workspace("https://github.com/psf/requests")
        assert workspace is not None
        assert (tmp_path / "data") not in workspace.parents
        assert "repos" not in workspace.parts

    def test_it_is_owned_like_every_other_session_route(self, client, monkeypatch):
        """404, never 403 — not yours and not there are indistinguishable."""
        session_id = _seed(demonstrated=2)
        monkeypatch.setattr(api, "current_user", lambda: None)
        r = client.get("/session/deadbeef/contribution/handoff")
        assert r.status_code == 404

    def test_a_non_contribution_session_has_nothing_to_hand_over(self, client):
        graph = _graph(demonstrated=2)
        graph.goal = {**GOAL, "goal_type": "understand_architecture",
                      "contribution_context": ""}
        learning_store.create_session(graph, api.SESSIONS_DB_PATH,
                                      user_id=TEST_USER_ID)
        r = client.get(f"/session/{graph.session_id}/contribution/handoff")
        assert r.status_code == 409
        assert r.json()["detail"] == "not_a_contribution_session"
