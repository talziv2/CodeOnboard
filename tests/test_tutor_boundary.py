"""**A conversation turn is not evidence about the learner.**

Run with: uv run pytest tests/test_tutor_boundary.py -v

This is the tier-1 law of tutor.md §5.1, and it is asserted two independent ways
because a law with one guard is a law until somebody is in a hurry:

  STRUCTURALLY   no module under `backend/agents/tutor/` may import the Grader,
                 the Mutator, `adaptation` or `record_attempt`. An AST walk, in
                 the shape `test_gap_model.py::test_the_persistence_path_never_
                 reads_the_flag` established — a rule the compiler can enforce is
                 worth more than a rule in a docstring.

  BEHAVIOURALLY  a full round trip through `POST /tutor/ask` leaves `to_dict()`
                 byte-identical except for the Tutor's own keys. That catches
                 what the import check cannot: a route that reached around the
                 boundary by mutating a node directly.

The behavioural half is the one that would fail if somebody decided, reasonably
and wrongly, that a learner who has asked four questions is "struggling" and wrote
it down.
"""
import ast
import json
import pathlib
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import backend.api as api
from backend.learning import store as learning_store
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from tests.conftest import TEST_USER_ID, start_session
from tests.test_session_api import FAKE_GOAL, FAKE_REPO_URL, _teaching_side_effect


TUTOR_PACKAGE = pathlib.Path(api.__file__).parent / "agents" / "tutor"

# Everything that can change what the system believes about a learner. Named
# rather than pattern-matched, so adding one is a deliberate act.
FORBIDDEN_NAMES = {
    "run_grader",          # produces a classification and opens gaps
    "mutate_graph",        # the only thing that reshapes the journey
    "mutate",              # the Mutator's own name for it
    "record_attempt",      # writes evidence
    "record_response",
    "decide",              # adaptation's policy table
    "decide_all",
    "prune_ahead",
    "reset_to_plan",
    "save_graph",          # persistence is the ENDPOINT's job, not an agent's
}

FORBIDDEN_MODULES = {
    "backend.agents.grader",
    "backend.agents.mentor.mutator",
    "backend.learning.adaptation",
    "backend.learning.store",
}


def _tutor_modules():
    files = sorted(TUTOR_PACKAGE.glob("*.py"))
    assert files, "the tutor package has no modules — this test is not running"
    return files


# ── structural ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", _tutor_modules(), ids=lambda p: p.name)
def test_no_tutor_module_can_reach_the_learning_engines_writers(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))

    imported_modules = set()
    imported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_modules.add(node.module or "")
            imported_names.update(alias.asname or alias.name for alias in node.names)
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)

    offending_modules = {
        module for module in imported_modules
        if any(module == f or module.startswith(f + ".") for f in FORBIDDEN_MODULES)
    }
    assert not offending_modules, (
        f"{path.name} imports {sorted(offending_modules)} — the Tutor observes the "
        f"learning engine, it never drives it"
    )

    offending_names = imported_names & FORBIDDEN_NAMES
    assert not offending_names, (
        f"{path.name} imports {sorted(offending_names)} — a conversation turn is "
        f"not evidence, so nothing here may write one"
    )


@pytest.mark.parametrize("path", _tutor_modules(), ids=lambda p: p.name)
def test_no_tutor_module_calls_a_writer_by_name(path):
    """Belt and braces: a late `import` inside a function would dodge the check
    above, but the CALL still has to be spelled."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    called = {
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Name, ast.Attribute))
    }
    offending = called & FORBIDDEN_NAMES
    assert not offending, f"{path.name} calls {sorted(offending)}"


def test_the_tutor_package_writes_nothing_to_a_node():
    """No assignment to any learner-state attribute, anywhere in the package.

    `understanding_state`, `weak_spot`, `attempts`, `gaps` and `user_override` are
    the five fields that constitute a claim about the learner. The Tutor reads
    them; it may not set one.
    """
    forbidden_targets = {
        "understanding_state", "weak_spot", "attempts", "gaps", "gap_state",
        "user_override", "visited", "current_node_id",
    }
    for path in _tutor_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            targets = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                targets = [node.target]
            for target in targets:
                if isinstance(target, ast.Attribute):
                    assert target.attr not in forbidden_targets, (
                        f"{path.name} assigns to `{target.attr}` — that is a claim "
                        f"about the learner, and the Tutor does not get to make one"
                    )


# ── behavioural ───────────────────────────────────────────────────────────────


PROMPT = "What does Session.send return?"


@pytest.fixture(autouse=True)
def _env_and_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("CODEONBOARD_TUTOR", "1")
    monkeypatch.setattr(api, "SESSIONS_DB_PATH", tmp_path / "sessions.db")
    monkeypatch.setattr(api.anthropic, "Anthropic", lambda **kw: MagicMock())


@pytest.fixture
def client():
    return TestClient(api.app)


def _session(client):
    node = LearningNode(
        title="The Session object",
        code_anchor=CodeAnchor("requests/sessions.py", 1, 20, symbol="Session"),
        lesson_brief={"objective": "Explain what Session owns", "priority": "required"},
    )
    node.cached_lesson = {"prompt": PROMPT, "reveal": "A Response.",
                          "expected_answer": "A Response."}
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    graph.add_node(node)
    graph.set_current(node.id)

    def _pipeline(repo_url, goal, client=None, progress_id=""):
        state = MagicMock()
        state.graph = graph
        state.errors = []
        return state

    with patch("backend.api.run_pipeline", side_effect=_pipeline), \
         patch("backend.api.run_teaching", side_effect=_teaching_side_effect):
        return start_session(client, FAKE_REPO_URL, FAKE_GOAL)["session_id"]


def _stored(session_id):
    return learning_store.load_graph(session_id, TEST_USER_ID, api.SESSIONS_DB_PATH)


def _no_repo():
    return patch("backend.api._tutor_repo_inputs",
                 return_value=api.tutor_context.RepoInputs(source="class Session: ..."))


def _reply(*_a, **kw):
    return {"text": "look at the return statement", "citations": [], "scope": "answered",
            "suggestion": None, "grounded": True, "usage": {}}


def test_asking_leaves_the_graph_payload_byte_identical(client):
    """The law, end to end.

    `to_dict()` carries every derived learning measure the product shows —
    readiness, the two progress numbers, the understanding profile, the per-node
    states and journey events. If a conversation could move any of them, this
    comparison fails.
    """
    session_id = _session(client)
    before = json.dumps(_stored(session_id).to_dict(), sort_keys=True)

    with _no_repo(), patch("backend.api.tutor_scaffold.reply", side_effect=_reply):
        for question in ("where do I look?", "what is an adapter?", "and then?"):
            client.post(f"/session/{session_id}/tutor/ask", json={"question": question})

    after = json.dumps(_stored(session_id).to_dict(), sort_keys=True)
    assert before == after, "a conversation changed something the learner is measured by"
    # And the conversation really did happen — otherwise this passes vacuously.
    assert len(_stored(session_id).tutor) == 3


def test_hinting_leaves_the_graph_payload_byte_identical(client):
    session_id = _session(client)
    before = json.dumps(_stored(session_id).to_dict(), sort_keys=True)

    with _no_repo(), patch("backend.api.tutor_scaffold.hint",
                           side_effect=lambda ctx, rung, client=None, errors=None: _reply()):
        for _ in range(3):
            client.post(f"/session/{session_id}/tutor/hint", json={})

    assert json.dumps(_stored(session_id).to_dict(), sort_keys=True) == before
    assert _stored(session_id).nodes[_stored(session_id).current_node_id].tutor_state.hints_used == 3


def test_revealing_changes_only_what_is_on_offer(client):
    """Revealing is the ONE Tutor act with a consequence — and the consequence is
    confined to `retry`, which is an offer rather than a measurement."""
    session_id = _session(client)
    before = _stored(session_id).to_dict()

    client.post(f"/session/{session_id}/tutor/reveal", json={})
    after = _stored(session_id).to_dict()

    assert after["readiness"] == before["readiness"]
    assert after["progress"] == before["progress"]
    assert after["understanding"] == before["understanding"]
    assert after["journey_events"] == before["journey_events"]
    assert after["nodes"] == before["nodes"], (
        "revealing must not touch a node's state — it sets a Tutor counter, and "
        "`retry.py` reads that counter to decide what to OFFER"
    )


def test_the_transcript_is_absent_from_the_session_payload(client):
    """It has its own endpoint, like lessons — a payload that grew with every
    question would make each poll heavier for a surface that may never open."""
    session_id = _session(client)
    with _no_repo(), patch("backend.api.tutor_scaffold.reply", side_effect=_reply):
        client.post(f"/session/{session_id}/tutor/ask", json={"question": "q"})
    payload = client.get(f"/session/{session_id}").json()
    assert "tutor" not in payload
    assert "tutor" not in json.dumps(payload)


def test_a_conversation_never_reaches_another_learners_session(client, monkeypatch):
    """Context isolation. Two sessions, one user, one repository, two goals."""
    first = _session(client)
    second = _session(client)
    with _no_repo(), patch("backend.api.tutor_scaffold.reply", side_effect=_reply):
        client.post(f"/session/{first}/tutor/ask", json={"question": "ONLY IN FIRST"})

    other = client.get(f"/session/{second}/tutor").json()
    assert other["turns"] == []
    assert "ONLY IN FIRST" not in json.dumps(other)
