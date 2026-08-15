"""
Pytest tests for the explorer pipeline path (production integration through the
Mentor boundary) and the survey store.
Run with: uv run pytest tests/test_explorer_pipeline.py -v

What must hold: the explorer graph runs repo_survey -> documentation ->
goal_investigation -> (reviewer?) -> mentor with no prioritization node; a
missing skeleton or missing dossier ends the run explicitly (D15) instead of
producing an ungrounded graph; the RAG graph is untouched; the survey store
treats a schema mismatch as missing; and run_pipeline reaches the Mentor
selects between the two compiled graphs.

No network, no clones: every node is patched at backend.pipeline.runner.run_*.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.pipeline.graph import (
    build_graph,
    route_after_investigation,
    route_after_repo_survey,
)
from backend.pipeline.runner import run_pipeline
from backend.pipeline.state import OnboardState
from backend.repo import survey_store

FAKE_REPO_URL = "https://github.com/example/demo"
FAKE_GOAL = {
    "primary_goal": "understand authentication",
    "goal_type": "understand_component",
    "focus_area": "authentication",
    "code_depth": "working",
    "depth": "deep",
    "language": "en",
}

DOSSIER = {"understanding": "x", "components": [], "entry_points": [], "flows": [],
           "relationships": [], "contracts": [], "prerequisites": [],
           "evidence_refs": [], "context": [], "open_questions": []}


def _survey_ok(state, client=None):
    state.repo_path = "data/repos/demo"
    state.survey = {"architecture": "a demo", "subsystems": []}
    state.module_map = {"demo": {"purpose": "x", "key_files": [], "exports": [],
                                 "dependencies": []}}
    return state


def _survey_clone_failed(state, client=None):
    state.errors.append("cloner failed: repository unreachable")
    return state


def _investigation_ok(state, client=None):
    state.investigation = {"dossier": dict(DOSSIER), "accepted": True,
                           "stop_reason": "reported", "turns": 5,
                           "tool_calls": 12, "rejections": [],
                           "cost_usd": 0.1, "seconds": 30.0, "used_survey": True}
    return state


def _investigation_failed(state, client=None):
    state.errors.append("goal_investigation: no dossier produced (api_error)")
    return state


def _mentor_ok(state, client=None):
    state.learning_path = [{"step": 1, "title": "x", "file": "demo/auth.py",
                            "line_range": [1, 10], "why": "x", "understand": "x",
                            "concepts": []}]
    state.confidence = "high"
    return state


# ── graph shape ───────────────────────────────────────────────────────────────


def test_the_explorer_graph_has_the_d11_shape():
    nodes = set(build_graph().get_graph().nodes.keys())
    assert "repo_survey" in nodes
    assert "goal_investigation" in nodes
    assert "documentation" in nodes
    assert "reviewer" in nodes
    assert "mentor" in nodes
    assert "prioritization" not in nodes    # absorbed into Layer C (H5)
    assert "code_structure" not in nodes


def test_there_is_no_second_graph_shape():
    """Stage 5: one production architecture, so `build_graph` takes no flag."""
    import inspect

    assert not inspect.signature(build_graph).parameters
    nodes = set(build_graph().get_graph().nodes.keys())
    assert "code_structure" not in nodes
    assert "prioritization" not in nodes


# ── routing (D15: fail explicitly, never fabricate) ───────────────────────────


def test_route_ends_when_the_skeleton_or_clone_failed():
    state = OnboardState(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    assert route_after_repo_survey(state) == "__end__"


def test_route_continues_without_a_survey():
    # The survey is Layer B context, not a requirement — a skeleton-derived
    # module_map is enough to continue.
    state = OnboardState(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL,
                         repo_path="x", module_map={"m": {}}, survey=None)
    assert route_after_repo_survey(state) == "documentation"


def test_route_ends_when_no_dossier_was_produced():
    state = OnboardState(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    assert route_after_investigation(state) == "__end__"


def test_route_sends_reviewer_goal_types_through_the_reviewer():
    state = OnboardState(
        repo_url=FAKE_REPO_URL,
        goal={**FAKE_GOAL, "goal_type": "improve_existing_system"},
        investigation={"dossier": DOSSIER},
    )
    assert route_after_investigation(state) == "reviewer"


def test_route_sends_other_goal_types_straight_to_the_mentor():
    state = OnboardState(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL,
                         investigation={"dossier": DOSSIER})
    assert route_after_investigation(state) == "mentor"


# ── end-to-end through the compiled graph (patched nodes) ─────────────────────


@patch("backend.pipeline.runner.run_mentor", side_effect=_mentor_ok)
@patch("backend.pipeline.runner.run_goal_investigation", side_effect=_investigation_ok)
@patch("backend.pipeline.runner.run_documentation")
@patch("backend.pipeline.runner.run_repo_survey", side_effect=_survey_ok)
def test_the_explorer_pipeline_reaches_the_mentor(m_survey, m_doc, m_inv, m_mentor):
    state = run_pipeline(FAKE_REPO_URL, FAKE_GOAL, client=MagicMock())
    m_survey.assert_called_once()
    m_doc.assert_called_once()
    m_inv.assert_called_once()
    m_mentor.assert_called_once()
    assert state.investigation is not None
    assert state.survey is not None
    assert state.learning_path is not None
    assert state.confidence == "high"


@patch("backend.pipeline.runner.run_mentor")
@patch("backend.pipeline.runner.run_goal_investigation")
@patch("backend.pipeline.runner.run_documentation")
@patch("backend.pipeline.runner.run_repo_survey", side_effect=_survey_clone_failed)
def test_a_failed_clone_ends_the_run_before_any_llm_stage(
    m_survey, m_doc, m_inv, m_mentor
):
    state = run_pipeline(FAKE_REPO_URL, FAKE_GOAL, client=MagicMock())
    m_doc.assert_not_called()
    m_inv.assert_not_called()
    m_mentor.assert_not_called()
    assert any("cloner failed" in e for e in state.errors)
    assert state.graph is None


@patch("backend.pipeline.runner.run_mentor")
@patch("backend.pipeline.runner.run_goal_investigation", side_effect=_investigation_failed)
@patch("backend.pipeline.runner.run_documentation")
@patch("backend.pipeline.runner.run_repo_survey", side_effect=_survey_ok)
def test_a_failed_investigation_ends_the_run_instead_of_fabricating(
    m_survey, m_doc, m_inv, m_mentor
):
    state = run_pipeline(FAKE_REPO_URL, FAKE_GOAL, client=MagicMock())
    m_mentor.assert_not_called()
    assert state.graph is None
    assert any("no dossier" in e for e in state.errors)


@patch("backend.pipeline.runner.run_reviewer")
@patch("backend.pipeline.runner.run_mentor", side_effect=_mentor_ok)
@patch("backend.pipeline.runner.run_goal_investigation", side_effect=_investigation_ok)
@patch("backend.pipeline.runner.run_documentation")
@patch("backend.pipeline.runner.run_repo_survey", side_effect=_survey_ok)
def test_reviewer_goal_types_run_the_reviewer_after_the_investigation(
    m_survey, m_doc, m_inv, m_mentor, m_reviewer
):
    goal = {**FAKE_GOAL, "goal_type": "improve_existing_system"}
    run_pipeline(FAKE_REPO_URL, goal, client=MagicMock())
    m_reviewer.assert_called_once()
    m_mentor.assert_called_once()


def test_nothing_imports_the_deleted_retrieval_layer():
    """Stage 5, asserted rather than assumed: `backend.rag` no longer exists."""
    import importlib

    for module in ("backend.rag", "backend.rag.retrieval", "backend.rag.store",
                   "backend.rag.embedder", "backend.agents.code_structure",
                   "backend.agents.prioritization", "backend.pipeline.profiles"):
        try:
            importlib.import_module(module)
        except ModuleNotFoundError:
            continue
        raise AssertionError(f"{module} still exists")


# ── the survey store ──────────────────────────────────────────────────────────


def test_a_saved_survey_round_trips(tmp_path):
    db = tmp_path / "sessions.db"
    payload = {"architecture": "x", "subsystems": [{"name": "a"}]}
    survey_store.save_survey("owner/repo", "abc123", payload,
                             accepted=True, db_path=db)
    assert survey_store.load_survey("owner/repo", "abc123", db_path=db) == payload


def test_a_missing_survey_is_none(tmp_path):
    db = tmp_path / "sessions.db"
    assert survey_store.load_survey("owner/repo", "abc123", db_path=db) is None


def test_a_schema_version_mismatch_reads_as_missing(tmp_path):
    db = tmp_path / "sessions.db"
    survey_store.save_survey("owner/repo", "abc123", {"architecture": "x"},
                             accepted=True, db_path=db)
    with patch.object(survey_store, "SURVEY_SCHEMA_VERSION", 999):
        assert survey_store.load_survey("owner/repo", "abc123", db_path=db) is None


def test_surveys_are_keyed_per_commit(tmp_path):
    db = tmp_path / "sessions.db"
    survey_store.save_survey("owner/repo", "commit-a", {"architecture": "a"},
                             accepted=True, db_path=db)
    survey_store.save_survey("owner/repo", "commit-b", {"architecture": "b"},
                             accepted=True, db_path=db)
    assert survey_store.load_survey("owner/repo", "commit-a", db_path=db)["architecture"] == "a"
    assert survey_store.load_survey("owner/repo", "commit-b", db_path=db)["architecture"] == "b"


def test_get_or_create_reuses_the_stored_survey(tmp_path):
    db = tmp_path / "sessions.db"
    survey_store.save_survey("owner/repo", "abc", {"architecture": "stored"},
                             accepted=True, db_path=db)
    payload, meta = survey_store.get_or_create_survey(
        client=MagicMock(), repo_path="unused", owner_repo="owner/repo",
        commit_sha="abc", db_path=db,
    )
    assert payload["architecture"] == "stored"
    assert meta["source"] == "cache"
    assert meta["cost_usd"] == 0.0


def test_get_or_create_produces_and_persists_when_absent(tmp_path):
    db = tmp_path / "sessions.db"
    fake_run = MagicMock()
    fake_run.survey = {"architecture": "fresh"}
    fake_run.accepted = True
    fake_run.exploration.stop_reason = "reported"
    fake_run.exploration.seconds = 12.0
    fake_run.exploration.usage.cost_usd.return_value = 0.15
    with patch("backend.repo.survey.run_survey", return_value=fake_run):
        payload, meta = survey_store.get_or_create_survey(
            client=MagicMock(), repo_path="p", owner_repo="o/r",
            commit_sha="sha", db_path=db,
        )
    assert payload["architecture"] == "fresh"
    assert meta["source"] == "fresh"
    # ...and the next call reads the stored copy without producing again.
    payload2, meta2 = survey_store.get_or_create_survey(
        client=MagicMock(), repo_path="p", owner_repo="o/r",
        commit_sha="sha", db_path=db,
    )
    assert payload2 == payload and meta2["source"] == "cache"


def test_a_failed_fresh_survey_is_not_persisted(tmp_path):
    db = tmp_path / "sessions.db"
    fake_run = MagicMock()
    fake_run.survey = None
    fake_run.accepted = False
    fake_run.exploration.stop_reason = "api_error"
    fake_run.exploration.seconds = 1.0
    fake_run.exploration.usage.cost_usd.return_value = 0.0
    with patch("backend.repo.survey.run_survey", return_value=fake_run):
        payload, meta = survey_store.get_or_create_survey(
            client=MagicMock(), repo_path="p", owner_repo="o/r",
            commit_sha="sha", db_path=db,
        )
    assert payload is None
    assert survey_store.load_survey("o/r", "sha", db_path=db) is None


def test_a_corrupt_row_reads_as_missing_not_a_crash(tmp_path):
    db = tmp_path / "sessions.db"
    survey_store.save_survey("o/r", "sha", {"x": 1}, accepted=True, db_path=db)
    import sqlite3

    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE repo_survey SET payload_json = 'not json'")
        connection.commit()
    assert survey_store.load_survey("o/r", "sha", db_path=db) is None


# ── explorer node behaviour (unpatched, offline) ──────────────────────────────


def test_module_map_from_survey_uses_the_full_subsystem_account():
    from backend.pipeline.explorer_nodes import _module_map_from_survey

    survey = {"subsystems": [
        {"name": "security", "responsibility": "auth schemes",
         "key_file": "pkg/security/base.py", "key_symbol": "SecurityBase"},
        {"name": "routing.py", "responsibility": "routes",
         "key_file": "pkg/routing.py"},
        "malformed entry",
    ]}
    modules = _module_map_from_survey(survey)
    assert modules["security"]["purpose"] == "auth schemes"
    assert modules["security"]["exports"] == ["SecurityBase"]
    assert "routing.py" in modules
    assert len(modules) == 2


def test_run_goal_investigation_requires_goal_and_repo(tmp_path):
    from backend.pipeline.explorer_nodes import run_goal_investigation

    state = OnboardState(repo_url=FAKE_REPO_URL, goal=None, repo_path="x")
    run_goal_investigation(state, client=MagicMock())
    assert any("goal missing" in e for e in state.errors)

    state = OnboardState(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL, repo_path="")
    run_goal_investigation(state, client=MagicMock())
    assert any("repo_path missing" in e for e in state.errors)
    assert state.investigation is None
