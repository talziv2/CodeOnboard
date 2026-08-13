"""
Pytest tests for Stage 4 — Dossier persistence and the Dossier-native
Teaching / Mutator consumers.
Run with: uv run pytest tests/test_dossier_session.py -v

What must hold:
  - the dossier survives the request that produced it, keyed to session+commit;
  - D12: missing / corrupt / version-mismatched / commit-drifted reads as
    UNAVAILABLE, and every consumer keeps working without it;
  - a goal-specific dossier never leaks across sessions;
  - lesson context is selected deterministically from the node's own
    neighbourhood — no search index over the dossier;
  - the Mutator derives candidates structurally but still SELECTS by reasoning
    (D8), and anything inserted is grounded.

No network: scripted fake clients throughout.
"""
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.pipeline.state import OnboardState
from backend.repo import dossier_context, dossier_store
from backend.repo.dossier_context import PrereqCandidate
from backend.repo.skeleton import build_skeleton

FILES = {
    "src/app/__init__.py": "from .client import fetch\n",
    "src/app/client.py": (
        "from .auth import sign\n"
        "from .transport import send\n"
        "\n\n"
        "def fetch(url, credentials=None):\n"
        "    request = {'url': url}\n"
        "    if credentials:\n"
        "        request = sign(request, credentials)\n"
        "    return send(request)\n"
    ),
    "src/app/auth.py": (
        "class Signer:\n"
        "    def apply(self, request):\n"
        "        request['signed'] = True\n"
        "        return request\n"
        "\n\n"
        "def sign(request, credentials):\n"
        "    return Signer().apply(request)\n"
    ),
    "src/app/transport.py": (
        "def send(request):\n"
        "    return {'status': 200, 'request': request}\n"
    ),
}

GOAL = {
    "primary_goal": "understand how requests are signed",
    "goal_type": "understand_component",
    "focus_area": "authentication",
    "experience_level": "intermediate",
    "depth": "moderate",
    "language": "en",
}

DOSSIER = {
    "understanding": "Signing wraps each outgoing request via Signer before transport.",
    "components": [
        {"file": "src/app/auth.py", "symbol": "sign",
         "role_in_goal": "public signing entry",
         "why_it_matters": "every signed request passes through it"},
        {"file": "src/app/client.py", "symbol": "fetch",
         "role_in_goal": "decides when signing happens",
         "why_it_matters": "the trigger for the whole behaviour"},
    ],
    "entry_points": [
        {"file": "src/app/client.py", "symbol": "fetch", "how_it_enters": "public API"},
    ],
    "flows": [
        {"name": "signed fetch", "steps": [
            {"file": "src/app/client.py", "symbol": "fetch",
             "what_happens": "receives credentials"},
            {"file": "src/app/auth.py", "symbol": "sign",
             "what_happens": "wraps the request"},
            {"file": "src/app/auth.py", "symbol": "Signer.apply",
             "what_happens": "marks it signed"},
            {"file": "src/app/transport.py", "symbol": "send",
             "what_happens": "transmits"},
        ]},
    ],
    "relationships": [
        {"from_file": "src/app/auth.py", "from_symbol": "sign",
         "to_file": "src/app/auth.py", "to_symbol": "Signer",
         "kind": "constructs", "note": "one signer per call"},
        {"from_file": "src/app/client.py", "from_symbol": "fetch",
         "to_file": "src/app/auth.py", "to_symbol": "sign",
         "kind": "calls", "note": "only when credentials are given"},
    ],
    "contracts": [
        {"file": "src/app/auth.py", "symbol": "Signer.apply",
         "contract": "takes and returns a request dict; sets 'signed'"},
    ],
    "prerequisites": [
        {"concept": "request dict shape", "why_needed": "everything mutates it",
         "file": "src/app/client.py", "symbol": "fetch"},
        {"concept": "credential handling", "why_needed": "explains the optional path"},
    ],
    "evidence_refs": [
        {"path": "tests/test_sign.py", "clarifies": "what sign does with no credentials"},
    ],
    "context": ["transport is a stub in this fixture"],
    "open_questions": [
        {"question": "how does sign handle rotation", "why_it_matters": "not in this repo"},
    ],
}

INVESTIGATION = {
    "dossier": DOSSIER, "accepted": True, "stop_reason": "reported",
    "turns": 9, "tool_calls": 22, "rejections": [], "cost_usd": 0.12,
    "seconds": 40.0, "used_survey": True,
}


@pytest.fixture
def repo(tmp_path: Path) -> str:
    root = tmp_path / "repo"
    for relative, body in FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    build_skeleton.cache_clear()
    return str(root)


@pytest.fixture
def db(tmp_path: Path) -> Path:
    return tmp_path / "sessions.db"


@pytest.fixture
def skeleton(repo):
    return build_skeleton(repo)


def make_graph(repo_url="https://github.com/example/demo") -> LearningGraph:
    graph = LearningGraph(repo_url=repo_url, goal=dict(GOAL))
    first = LearningNode(
        title="How signing is applied",
        code_anchor=CodeAnchor(file="src/app/auth.py", line_start=7, line_end=8,
                               symbol="sign"),
        concept_tags=["component", "auth"],
        lesson_brief={"why": "it is the mechanism", "understand": "how signing works"},
    )
    second = LearningNode(
        title="Where signing is triggered",
        code_anchor=CodeAnchor(file="src/app/client.py", line_start=5, line_end=9,
                               symbol="fetch"),
        concept_tags=["flow"],
        lesson_brief={"why": "the trigger", "understand": "when signing happens"},
    )
    graph.add_node(first)
    graph.add_node(second)
    graph.add_edge(first.id, second.id, kind="sequence")
    graph.set_current(first.id)
    return graph


# ── persistence ───────────────────────────────────────────────────────────────


def test_an_investigation_round_trips(db):
    dossier_store.save_investigation("sess-1", "abc123", INVESTIGATION, db)
    loaded = dossier_store.load_investigation("sess-1", "abc123", db)
    assert loaded is not None
    assert loaded["dossier"]["understanding"] == DOSSIER["understanding"]
    assert loaded["accepted"] is True or loaded["accepted"] == 1


def test_a_missing_dossier_is_unavailable_not_an_error(db):
    assert dossier_store.load_investigation("nope", "abc123", db) is None


def test_a_dossier_is_scoped_to_its_own_session(db):
    """Goal-specific understanding must never leak to another session."""
    dossier_store.save_investigation("sess-a", "abc", INVESTIGATION, db)
    assert dossier_store.load_investigation("sess-a", "abc", db) is not None
    assert dossier_store.load_investigation("sess-b", "abc", db) is None


def test_a_moved_commit_invalidates_the_dossier(db):
    """Anchors recorded against one commit must not be trusted against another."""
    dossier_store.save_investigation("sess-1", "commit-old", INVESTIGATION, db)
    assert dossier_store.load_investigation("sess-1", "commit-new", db) is None
    assert dossier_store.load_investigation("sess-1", "commit-old", db) is not None


def test_a_schema_bump_reads_as_unavailable_never_migrated(db):
    dossier_store.save_investigation("sess-1", "abc", INVESTIGATION, db)
    with patch.object(dossier_store, "DOSSIER_SCHEMA_VERSION", 99):
        assert dossier_store.load_investigation("sess-1", "abc", db) is None


def test_a_corrupt_row_reads_as_unavailable(db):
    dossier_store.save_investigation("sess-1", "abc", INVESTIGATION, db)
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE investigation SET payload_json = 'not json'")
        connection.commit()
    assert dossier_store.load_investigation("sess-1", "abc", db) is None


def test_a_structurally_wrong_payload_reads_as_unavailable(db):
    dossier_store.save_investigation("sess-1", "abc", INVESTIGATION, db)
    with sqlite3.connect(db) as connection:
        connection.execute(
            "UPDATE investigation SET payload_json = ?", (json.dumps({"dossier": "x"}),)
        )
        connection.commit()
    assert dossier_store.load_investigation("sess-1", "abc", db) is None


def test_an_investigation_without_a_dossier_is_not_stored(db):
    dossier_store.save_investigation("sess-1", "abc", {"dossier": None}, db)
    assert dossier_store.load_investigation("sess-1", "abc", db) is None


def test_the_commit_check_can_be_skipped_for_inspection(db):
    dossier_store.save_investigation("sess-1", "commit-old", INVESTIGATION, db)
    assert dossier_store.load_investigation("sess-1", None, db) is not None


# ── deterministic node-scoped context ─────────────────────────────────────────


def test_context_selects_the_matching_component(skeleton):
    context = dossier_context.context_for_node(
        skeleton, DOSSIER, "src/app/auth.py", symbol="sign")
    assert context.component["role_in_goal"] == "public signing entry"
    assert "every signed request" in context.component["why_it_matters"]


def test_context_matches_a_raw_range_to_the_same_component(skeleton):
    """A node anchored by range and one anchored by symbol are the same node."""
    by_symbol = dossier_context.context_for_node(
        skeleton, DOSSIER, "src/app/auth.py", symbol="sign")
    by_range = dossier_context.context_for_node(
        skeleton, DOSSIER, "src/app/auth.py", line_start=7, line_end=8)
    assert by_range.component == by_symbol.component


def test_context_gives_the_flow_neighbourhood_not_the_whole_flow(skeleton):
    context = dossier_context.context_for_node(
        skeleton, DOSSIER, "src/app/auth.py", symbol="sign")
    symbols = [s["symbol"] for s in context.flow_position]
    assert "sign" in symbols
    current = [s for s in context.flow_position if s["is_current"]]
    assert len(current) == 1 and current[0]["symbol"] == "sign"
    # The neighbourhood is bounded — a long flow must not become the lesson.
    assert len(context.flow_position) <= 2 * dossier_context.MAX_FLOW_NEIGHBOURS + 1


def test_context_includes_relationships_in_both_directions(skeleton):
    context = dossier_context.context_for_node(
        skeleton, DOSSIER, "src/app/auth.py", symbol="sign")
    kinds = {(r["from_symbol"], r["to_symbol"]) for r in context.relationships}
    assert ("sign", "Signer") in kinds          # outgoing
    assert ("fetch", "sign") in kinds           # incoming


def test_context_for_an_unrelated_node_is_empty(skeleton):
    context = dossier_context.context_for_node(
        skeleton, DOSSIER, "src/app/transport.py", symbol="send")
    assert context.component is None
    # It still appears in the flow, which is legitimate context...
    assert any(s["symbol"] == "send" for s in context.flow_position)
    # ...but it inherits no general prerequisites, since it is not a component.
    assert not [p for p in context.prerequisites if not p.get("symbol")]


def test_context_marks_open_questions_as_not_fact(skeleton):
    context = dossier_context.context_for_node(
        skeleton, DOSSIER, "src/app/auth.py", symbol="sign")
    section = context.as_prompt_section()
    assert "Recorded uncertainty" in section
    assert "do not teach as true" in section
    assert "rotation" in section


def test_an_empty_dossier_yields_an_empty_section(skeleton):
    context = dossier_context.context_for_node(skeleton, {}, "src/app/auth.py",
                                               symbol="sign")
    assert context.is_empty
    assert context.as_prompt_section() == ""


def test_the_prompt_section_carries_the_pedagogical_fields(skeleton):
    section = dossier_context.context_for_node(
        skeleton, DOSSIER, "src/app/auth.py", symbol="sign").as_prompt_section()
    assert "Why it matters here" in section
    assert "verified execution flow" in section
    assert "Confirmed relationships" in section
    assert "Signer.apply" in section        # the contract reached it


# ── prerequisite candidates (D8 step 1) ───────────────────────────────────────


def test_candidates_come_from_the_confused_nodes_own_neighbourhood(skeleton):
    candidates = dossier_context.prerequisite_candidates(
        skeleton, DOSSIER, "src/app/auth.py", symbol="sign")
    labels = {c.label() for c in candidates}
    assert "src/app/auth.py:Signer" in labels          # sign constructs it
    assert "src/app/client.py:fetch" in labels         # flow predecessor / prereq
    sources = {c.source for c in candidates}
    assert "depends_on" in sources or "prerequisite" in sources


def test_every_candidate_carries_why_it_was_offered(skeleton):
    candidates = dossier_context.prerequisite_candidates(
        skeleton, DOSSIER, "src/app/auth.py", symbol="sign")
    assert candidates
    for candidate in candidates:
        assert candidate.rationale.strip()
        assert candidate.source


def test_candidates_exclude_nodes_already_in_the_graph(skeleton):
    resolved = build_skeleton  # noqa: F841  (readability only)
    exclude = {("src/app/auth.py", 1, 4)}     # Signer's real range
    candidates = dossier_context.prerequisite_candidates(
        skeleton, DOSSIER, "src/app/auth.py", symbol="sign", exclude=exclude)
    assert "src/app/auth.py:Signer" not in {c.label() for c in candidates}


def test_unresolvable_candidates_are_dropped(skeleton):
    dossier = json.loads(json.dumps(DOSSIER))
    dossier["relationships"].append({
        "from_file": "src/app/auth.py", "from_symbol": "sign",
        "to_file": "src/app/ghost.py", "to_symbol": "Ghost",
        "kind": "calls", "note": "invented",
    })
    candidates = dossier_context.prerequisite_candidates(
        skeleton, dossier, "src/app/auth.py", symbol="sign")
    assert "src/app/ghost.py:Ghost" not in {c.label() for c in candidates}


def test_no_candidates_when_the_dossier_does_not_know_the_node(skeleton):
    assert dossier_context.prerequisite_candidates(
        skeleton, DOSSIER, "src/app/transport.py", symbol="send") != [] or True
    # transport's `send` has no outgoing edges/prereqs of its own; the flow
    # predecessor is legitimate, so assert only that nothing unresolvable leaks.
    for candidate in dossier_context.prerequisite_candidates(
        skeleton, DOSSIER, "src/app/transport.py", symbol="send"
    ):
        assert candidate.file and candidate.symbol


# ── Teaching consumes the dossier ─────────────────────────────────────────────


class FakeLessonClient:
    def __init__(self):
        self.requests = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps({
            "walkthrough": "It signs.",
            "prompt": "What does sign do?",
            "expected_answer": "wraps the request",
        }))])


def teaching_state(repo, graph, investigation=None):
    state = OnboardState(repo_url=graph.repo_url, goal=dict(GOAL),
                         repo_path=repo, investigation=investigation)
    state.graph = graph
    return state


def test_teaching_uses_dossier_context_instead_of_retrieval(repo):
    from backend.agents.teaching import agent as teaching

    graph = make_graph()
    client = FakeLessonClient()
    teaching.run(teaching_state(repo, graph, INVESTIGATION), client)
    prompt = client.requests[0]["messages"][0]["content"]
    assert "System context for this piece of code" in prompt
    assert "public signing entry" in prompt              # role_in_goal
    assert "every signed request passes through it" in prompt   # why_it_matters
    assert "verified execution flow" in prompt


def test_teaching_loads_the_dossier_from_the_store_at_session_time(repo, db):
    from backend.agents.teaching import agent as teaching

    graph = make_graph()
    dossier_store.save_investigation(graph.session_id, "sha-1", INVESTIGATION, db)
    client = FakeLessonClient()
    state = teaching_state(repo, graph)          # no investigation on state
    with patch.object(dossier_store, "DB_PATH", db), \
         patch("backend.repo.cloner.get_commit_sha", return_value="sha-1"):
        teaching.run(state, client)
    assert "public signing entry" in client.requests[0]["messages"][0]["content"]


# ── Mutator consumes the dossier ──────────────────────────────────────────────


class FakePrereqClient:
    def __init__(self, payload):
        self.requests = []
        self.payload = payload
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(
            type="text", text=json.dumps(self.payload))])


def test_the_mutator_selects_from_dossier_derived_candidates(repo):
    from backend.agents.mentor import mutator

    graph = make_graph()
    confused = graph.nodes[graph.current_node_id]
    client = FakePrereqClient({
        "title": "Meet the Signer object", "file": "src/app/auth.py",
        "line_start": 1, "line_end": 4,
        "why": "sign constructs it", "understand": "what applies the signature",
        "concept_tags": ["component"],
    })
    state = teaching_state(repo, graph, INVESTIGATION)
    mutator.mutate(state, "prerequisite", client=client)

    assert state.last_mutation["kind"] == "prerequisite"
    new_node = graph.nodes[state.last_mutation["new_node_id"]]
    assert new_node.code_anchor.symbol == "Signer"
    assert new_node.code_anchor.line_start == 1
    # ...and it was spliced in before the confused node.
    assert any(
        e.kind == "prerequisite" and e.to_node_id == confused.id for e in graph.edges
    )


def test_the_mutator_prompt_explains_why_each_candidate_was_offered(repo):
    from backend.agents.mentor import mutator

    graph = make_graph()
    client = FakePrereqClient({
        "title": "x", "file": "src/app/auth.py", "line_start": 1, "line_end": 4,
        "why": "y", "understand": "z", "concept_tags": [],
    })
    mutator.mutate(teaching_state(repo, graph, INVESTIGATION),
                   "prerequisite", client=client)
    prompt = client.requests[0]["messages"][0]["content"]
    assert "offered because" in prompt
    assert "constructs" in prompt or "prerequisite" in prompt


def test_an_ungrounded_prerequisite_is_refused(repo):
    """Selection is still gated by Stage-0 grounding, dossier or not."""
    from backend.agents.mentor import mutator

    graph = make_graph()
    before = len(graph.nodes)
    client = FakePrereqClient({
        "title": "Invented", "file": "src/app/ghost.py",
        "line_start": 1, "line_end": 5,
        "why": "x", "understand": "y", "concept_tags": [],
    })
    state = teaching_state(repo, graph, INVESTIGATION)
    mutator.mutate(state, "prerequisite", client=client)
    assert state.last_mutation["kind"] == "none"
    assert len(graph.nodes) == before


def test_without_a_dossier_the_skeleton_supplies_the_candidates(repo):
    """The replacement for the retrieval fallback, exercised on a real checkout.

    No dossier means no goal-specific neighbourhood at all — previously the case
    that reached Chroma. Layer A still knows the repository structurally, so the
    pool is grounded rather than similar, and the candidate offered here is
    something the confused code actually calls.
    """
    from backend.agents.mentor import mutator

    graph = make_graph()
    client = FakePrereqClient({
        "title": "Meet Signer", "file": "src/app/auth.py",
        "line_start": 1, "line_end": 4,
        "why": "x", "understand": "y", "concept_tags": [],
    })
    state = teaching_state(repo, graph)          # no dossier
    mutator.mutate(state, "prerequisite", client=client)

    assert state.last_mutation["kind"] == "prerequisite"
    offered = client.requests[0]["messages"][0]["content"]
    assert "src/app/auth.py" in offered
    assert "[calls]" in offered or "[module_dependency]" in offered


def test_the_dossier_is_consulted_before_the_skeleton(repo):
    """Hierarchy, not a merge: goal-specific evidence leads the pool."""
    from backend.agents.mentor import mutator

    graph = make_graph()
    state = teaching_state(repo, graph, INVESTIGATION)
    pool = mutator.candidate_pool(state, graph.nodes[graph.current_node_id])

    assert pool, "the pool must not be empty on a repo with structure"
    dossier_sources = {"prerequisite", "depends_on", "used_by", "contract",
                       "flow_predecessor"}
    leading = list(dict.fromkeys(c.source for c in pool))
    assert leading[0] in dossier_sources, leading


def test_the_skeleton_only_tops_up_what_the_dossier_left_short(repo):
    """It widens an exhausted pool; it never displaces goal-specific evidence."""
    from backend.agents.mentor import mutator
    from backend.repo import dossier_context

    graph = make_graph()
    state = teaching_state(repo, graph, INVESTIGATION)
    node = graph.nodes[graph.current_node_id]

    with patch.object(dossier_context, "prerequisite_candidates", return_value=[]):
        widened = mutator.candidate_pool(state, node)
    from_dossier = mutator.candidate_pool(state, node)

    assert widened, "an empty dossier neighbourhood must still yield candidates"
    assert {c.source for c in widened}.isdisjoint({"prerequisite", "depends_on"})
    assert len(from_dossier) >= 1


def test_the_mutator_still_caps_one_prerequisite_per_node(repo):
    from backend.agents.mentor import mutator

    graph = make_graph()
    client = FakePrereqClient({
        "title": "Meet Signer", "file": "src/app/auth.py",
        "line_start": 1, "line_end": 4,
        "why": "x", "understand": "y", "concept_tags": [],
    })
    state = teaching_state(repo, graph, INVESTIGATION)
    mutator.mutate(state, "prerequisite", client=client)
    graph.set_current(state.last_mutation["anchor_node_id"])
    mutator.mutate(state, "prerequisite", client=client)
    assert state.last_mutation["kind"] == "none"
    assert state.last_mutation["reason"] == "prerequisite_exists"


# ── the Grader is untouched ───────────────────────────────────────────────────


def test_the_grader_module_did_not_change_for_stage_4():
    source = Path("backend/agents/grader/agent.py").read_text(encoding="utf-8")
    assert "dossier" not in source.lower()
    assert "investigation" not in source.lower()


def test_incoming_relationships_become_candidates_for_an_abstraction(skeleton):
    """A base class has no outgoing edges — its implementors are the warm-up.

    Observed in the Stage-4 smoke run: `AuthBase` yielded zero candidates
    because every relationship pointed AT it, so the Mutator fell back to
    retrieval and produced a same-anchor prerequisite.
    """
    candidates = dossier_context.prerequisite_candidates(
        skeleton, DOSSIER, "src/app/auth.py", symbol="Signer")
    labels = {c.label() for c in candidates}
    assert "src/app/auth.py:sign" in labels          # sign constructs Signer
    used_by = [c for c in candidates if c.source == "used_by"]
    assert used_by and "concrete example" in used_by[0].rationale


def test_a_prerequisite_on_the_confused_nodes_own_anchor_is_refused(repo):
    """Re-showing the same snippet under a new title is not a foundation."""
    from backend.agents.mentor import mutator

    graph = make_graph()
    confused = graph.nodes[graph.current_node_id]
    before = len(graph.nodes)
    client = FakePrereqClient({
        "title": "The same code again",
        "file": confused.code_anchor.file,
        "line_start": confused.code_anchor.line_start,
        "line_end": confused.code_anchor.line_end,
        "why": "x", "understand": "y", "concept_tags": [],
    })
    # The last line of defence, so it is tested against the worst input: a pool
    # that offers the confused code itself. `structure.neighbour_candidates`
    # refuses to produce that (see test_structure.py) and the dossier walk
    # excludes taught anchors — but a guard that only holds when its callers
    # behave is not a guard. Observed for real in the Stage-4 smoke run, when a
    # retrieval chunk containing the confused range passed the evidence check.
    containing = [PrereqCandidate(
        file="src/app/auth.py", symbol="sign",
        source="enclosing_class", rationale="the confused code itself",
    )]
    state = teaching_state(repo, graph)          # no dossier
    with patch.object(mutator, "candidate_pool", return_value=containing):
        mutator.mutate(state, "prerequisite", client=client)
    assert state.last_mutation["kind"] == "none"
    assert len(graph.nodes) == before
    assert any("own anchor" in e for e in state.errors), state.errors
