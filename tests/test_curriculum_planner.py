"""
Pytest tests for the objective-first planner end to end (curriculum.run).
Run with: uv run pytest tests/test_curriculum_planner.py -v

The deterministic half lives in test_curriculum.py. What must hold here: every
anchor on every unit is verified — not just the displayed one — and the display
columns always equal one member of `anchors`; a multi-anchor `flow` unit is
expressible at all (impossible before B3); planned prerequisite edges exist on a
fresh graph; areas reach the graph and survive SQLite; and `mentor.run` routes
here, which it now does unconditionally — `CODEONBOARD_CURRICULUM` and the
pre-B3 planner it selected are both gone.

No network: scripted fake client, real temporary checkout.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.conftest import TEST_USER_ID

from backend.agents.mentor import agent as mentor_agent
from backend.agents.mentor import curriculum
from backend.learning import store as learning_store
from backend.pipeline.state import OnboardState
from backend.repo.skeleton import build_skeleton

# Shared with the rendering tests: one dossier and one temporary checkout, so a
# planner test and a rendering test cannot silently disagree about the evidence.
from tests.test_dossier_rendering import DOSSIER, FILES, GOAL


@pytest.fixture
def repo(tmp_path: Path) -> str:
    for relative, body in FILES.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    build_skeleton.cache_clear()
    return str(tmp_path)


class FakeClient:
    """Scripted replies. `texts` may be one string or a list, one per call.

    `stop_reasons` mirrors it — "max_tokens" is what the API reports when the
    model ran out of room, which is how the planner tells a truncated response
    from a malformed one.
    """

    def __init__(self, texts, stop_reasons=None):
        self.texts = [texts] if isinstance(texts, str) else list(texts)
        self.stop_reasons = list(stop_reasons or ["end_turn"] * len(self.texts))
        self.requests = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        i = min(len(self.requests) - 1, len(self.texts) - 1)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self.texts[i])],
            stop_reason=self.stop_reasons[min(i, len(self.stop_reasons) - 1)],
        )


def anchor(file: str, symbol: str) -> dict:
    return {"file": file, "symbol": symbol}


def objective(
    id: str,
    anchors: list[dict],
    *,
    kind: str = "component",
    priority: str = "required",
    area: str = "a1",
    depends_on: list[str] | None = None,
) -> dict:
    return {
        "id": id,
        "title": f"Learn {id}",
        "objective": f"Explain what {id} owns and what it does not",
        "kind": kind,
        "priority": priority,
        "area_id": area,
        "depends_on": depends_on or [],
        "anchors": anchors,
        "why": "matters for the goal",
        "concept_tags": ["auth"],
    }


AREAS = [
    {"id": "a1", "title": "Signing", "why": "the goal turns on it", "order": 1},
    {"id": "a2", "title": "Transport", "why": "where signed requests go", "order": 2},
]

FLOW_ANCHORS = [
    anchor("src/app/client.py", "fetch"),
    anchor("src/app/auth.py", "sign"),
    anchor("src/app/transport.py", "send"),
]


def response(objectives: list[dict], areas=None, covers_goal=True, confidence="high") -> str:
    return json.dumps({
        "areas": areas if areas is not None else AREAS,
        "objectives": objectives,
        "covers_goal": covers_goal,
        "coverage_note": "",
        "confidence": confidence,
    })


def make_state(repo: str, accepted: bool = True) -> OnboardState:
    return OnboardState(
        repo_url="https://github.com/example/demo",
        goal=dict(GOAL),
        repo_path=repo,
        investigation={
            "dossier": DOSSIER, "accepted": accepted, "stop_reason": "reported",
            "turns": 8, "tool_calls": 20, "rejections": [], "cost_usd": 0.1,
            "seconds": 30.0, "used_survey": True,
        },
    )


DEFAULT = [
    objective("n1", [anchor("src/app/client.py", "fetch")], kind="architecture"),
    objective("n2", FLOW_ANCHORS, kind="flow", depends_on=["n1"]),
    objective("n3", [anchor("src/app/auth.py", "Signer.apply")], area="a2",
              depends_on=["n2"]),
]


def plan(repo: str, objectives=None, **kwargs) -> OnboardState:
    state = make_state(repo)
    client = FakeClient(response(objectives if objectives is not None else DEFAULT, **kwargs))
    return curriculum.run(state, client)


# ── grounding: every anchor, not just the displayed one ───────────────────────

def test_a_unit_can_be_grounded_in_several_files_at_once(repo):
    # Impossible before B3: a flow crossing three files had to pick one of them
    # and hope the lesson explained the rest (L4, L5).
    state = plan(repo)
    flow = next(n for n in state.graph.nodes.values() if n.title == "Learn n2")
    stored = flow.lesson_brief["anchors"]
    assert [a["file"] for a in stored] == [
        "src/app/client.py", "src/app/auth.py", "src/app/transport.py"
    ]


def test_every_anchor_on_every_unit_is_resolved_by_our_code(repo):
    # The model names file + symbol and never states a range; a hallucinated
    # range is structurally impossible because it has nowhere to be written.
    state = plan(repo)
    for node in state.graph.nodes.values():
        for a in node.lesson_brief["anchors"]:
            assert a["line_start"] and a["line_end"]
            assert a["line_start"] <= a["line_end"]


def test_the_display_columns_always_equal_one_member_of_anchors(repo):
    # The named denormalization's one invariant (§10).
    state = plan(repo)
    for node in state.graph.nodes.values():
        stored = node.lesson_brief["anchors"]
        assert {
            "file": node.code_anchor.file,
            "line_start": node.code_anchor.line_start,
            "line_end": node.code_anchor.line_end,
        } in [
            {"file": a["file"], "line_start": a["line_start"], "line_end": a["line_end"]}
            for a in stored
        ]


def test_the_first_anchor_is_the_one_the_code_pane_opens(repo):
    state = plan(repo)
    flow = next(n for n in state.graph.nodes.values() if n.title == "Learn n2")
    assert flow.code_anchor.file == "src/app/client.py"  # the flow's entry point


def test_an_unresolvable_anchor_is_dropped_without_sinking_the_unit(repo):
    # A four-step flow whose third step went stale is still a real flow.
    partly_stale = [
        objective("n1", [
            anchor("src/app/client.py", "fetch"),
            anchor("src/app/client.py", "no_such_symbol"),
            anchor("src/app/auth.py", "sign"),
        ], kind="flow"),
    ]
    state = plan(repo, partly_stale)
    node = next(iter(state.graph.nodes.values()))
    assert len(node.lesson_brief["anchors"]) == 2
    assert any("no_such_symbol" in e for e in state.errors)


def test_a_unit_whose_anchors_all_fail_is_dropped(repo):
    objectives = [
        objective("good", [anchor("src/app/auth.py", "sign")]),
        objective("bad", [anchor("src/app/auth.py", "invented")]),
    ]
    state = plan(repo, objectives)
    assert [n.title for n in state.graph.nodes.values()] == ["Learn good"]


def test_an_anchor_outside_the_dossiers_evidence_is_rejected(repo):
    # The evidence gate is the dossier, not the repository. `cache` below is
    # real, resolvable code — and the investigation never looked at it, so it is
    # still ungrounded for teaching purposes.
    unwatched = Path(repo) / "src/app/cache.py"
    unwatched.write_text("def cache(request):\n    return request\n", encoding="utf-8")
    build_skeleton.cache_clear()

    objectives = [
        objective("good", [anchor("src/app/auth.py", "sign")]),
        objective("outside", [anchor("src/app/cache.py", "cache")]),
    ]
    state = plan(repo, objectives)

    assert [n.title for n in state.graph.nodes.values()] == ["Learn good"]
    assert any("verified evidence" in e for e in state.errors)


def test_a_dependency_on_a_dropped_unit_does_not_survive(repo):
    # Otherwise resume_point() holds the learner behind a prerequisite that is
    # not in the graph.
    objectives = [
        objective("gone", [anchor("src/app/auth.py", "invented")]),
        objective("kept", [anchor("src/app/auth.py", "sign")], depends_on=["gone"]),
    ]
    state = plan(repo, objectives)
    assert not [e for e in state.graph.edges if e.kind == "prerequisite"]


# ── the graph the planner builds ──────────────────────────────────────────────

def test_prerequisite_edges_exist_on_a_freshly_planned_graph(repo):
    # Before B3 these appeared only as post-failure remediation, which left
    # resume_point()'s prerequisite check nearly vacuous on a new graph (§6.4).
    state = plan(repo)
    assert len([e for e in state.graph.edges if e.kind == "prerequisite"]) == 2


def test_the_learner_still_walks_one_ordered_chain(repo):
    state = plan(repo)
    order = state.graph.path_order()
    assert len(order) == len(state.graph.nodes)
    assert [state.graph.nodes[i].title for i in order] == [
        "Learn n1", "Learn n2", "Learn n3"
    ]


def test_dependencies_are_taught_before_the_units_that_need_them(repo):
    # The model emitted these in the wrong order on purpose.
    objectives = [
        objective("last", [anchor("src/app/transport.py", "send")], depends_on=["first"]),
        objective("first", [anchor("src/app/client.py", "fetch")]),
    ]
    state = plan(repo, objectives)
    order = [state.graph.nodes[i].title for i in state.graph.path_order()]
    assert order == ["Learn first", "Learn last"]


def test_the_kind_leads_the_concept_tags(repo):
    # Four agents and the frontend colour map already read concept_tags[0].
    state = plan(repo)
    flow = next(n for n in state.graph.nodes.values() if n.title == "Learn n2")
    assert flow.concept_tags[0] == "flow"


def test_kind_priority_and_area_reach_the_wire(repo):
    state = plan(repo)
    node = next(n for n in state.graph.to_dict()["nodes"] if n["title"] == "Learn n2")
    assert node["kind"] == "flow"
    assert node["priority"] == "required"
    assert node["area_id"] == "a1"
    assert len(node["anchors"]) == 3


def test_areas_reach_the_graph_in_order(repo):
    state = plan(repo, areas=list(reversed(AREAS)))
    assert [a["id"] for a in state.graph.areas] == ["a1", "a2"]
    assert state.graph.to_dict()["areas"][0]["title"] == "Signing"


def test_areas_survive_a_round_trip_through_sqlite(tmp_path, repo):
    state = plan(repo)
    db = tmp_path / "s.db"
    learning_store.save_graph(state.graph, db, user_id=TEST_USER_ID)
    loaded = learning_store.load_graph(state.graph.session_id, TEST_USER_ID, db)
    assert [a["id"] for a in loaded.areas] == ["a1", "a2"]
    node = next(n for n in loaded.nodes.values() if n.title == "Learn n2")
    assert len(node.lesson_brief["anchors"]) == 3


def test_a_graph_with_no_areas_still_saves_and_loads(tmp_path, repo):
    # Every session planned before B3 has none.
    state = plan(repo, areas=[])
    db = tmp_path / "s.db"
    learning_store.save_graph(state.graph, db, user_id=TEST_USER_ID)
    assert learning_store.load_graph(state.graph.session_id, TEST_USER_ID, db).areas == []


# ── sizing, without a node count anywhere ─────────────────────────────────────

def test_no_node_count_appears_in_the_planner_prompt(repo):
    # The direct, verifiable end of L1.
    prompt = curriculum._SYSTEM_PROMPT
    for banned in ("4-5", "5-7", "7-10", "4–5", "5–7", "7–10"):
        assert banned not in prompt
    assert "you are not choosing a length" in prompt


def test_the_planner_is_told_to_over_generate(repo):
    assert "ENUMERATE, DO NOT SELF-LIMIT" in curriculum._SYSTEM_PROMPT


def test_background_may_cheapen_a_unit_but_never_drop_it(repo):
    # LD15, resolving LQ1.
    assert "CHEAPER TO TEACH" in curriculum._SYSTEM_PROMPT
    assert "Never drop an objective because they claim to know it" in (
        curriculum._SYSTEM_PROMPT
    )


# ── failure modes ─────────────────────────────────────────────────────────────

def test_no_dossier_means_no_graph(repo):
    state = make_state(repo)
    state.investigation = {}
    curriculum.run(state, FakeClient(response(DEFAULT)))
    assert state.graph is None
    assert any("no investigation dossier" in e for e in state.errors)


def test_a_malformed_response_never_raises(repo):
    state = make_state(repo)
    curriculum.run(state, FakeClient("not json at all"))
    assert state.graph is None
    assert any("proposal call failed" in e for e in state.errors)


def test_a_salvaged_dossier_caps_confidence(repo):
    state = make_state(repo, accepted=False)
    curriculum.run(state, FakeClient(response(DEFAULT)))
    assert state.confidence == "medium"


def test_a_planner_admitting_incomplete_coverage_caps_confidence(repo):
    state = plan(repo, covers_goal=False)
    assert state.confidence == "medium"
    assert any("incomplete coverage" in e for e in state.errors)


# ── routing ───────────────────────────────────────────────────────────────────

def test_mentor_run_routes_here(repo):
    """There is one planner, and `mentor.run` reaches it with no flag set.

    This used to be a pair — one test for each side of `CODEONBOARD_CURRICULUM`,
    plus a third asserting the flag defaulted off. The flag is gone and so is the
    planner it defaulted to, so what is left to pin is that the delegation still
    happens: a graph with `areas` on it can only have come from this planner.
    """
    state = make_state(repo)
    mentor_agent.run(state, FakeClient(response(DEFAULT)))
    assert state.graph.areas != []


# ── truncation recovery ───────────────────────────────────────────────────────

def _truncated(objectives) -> str:
    """A payload cut off mid-string, exactly as a max_tokens stop produces."""
    return response(objectives)[:-120]


def test_a_truncated_proposal_is_retried_once_and_recovers(repo):
    state = make_state(repo)
    client = FakeClient(
        [_truncated(DEFAULT), response(DEFAULT)],
        stop_reasons=["max_tokens", "end_turn"],
    )
    curriculum.run(state, client)

    assert len(client.requests) == 2
    assert state.graph is not None and len(state.graph.nodes) == 3
    assert any("truncated at the token limit" in e for e in state.errors)


def test_the_retry_asks_for_the_same_curriculum_written_tighter(repo):
    # NOT for fewer objectives. "Propose less" is a size instruction, and
    # putting one back in this prompt would undo B3's whole point (L1).
    state = make_state(repo)
    client = FakeClient(
        [_truncated(DEFAULT), response(DEFAULT)],
        stop_reasons=["max_tokens", "end_turn"],
    )
    curriculum.run(state, client)

    retry = client.requests[1]["messages"][0]["content"]
    assert "Do NOT reduce the number of objectives" in retry
    assert "the same objectives" in retry


def test_a_malformed_but_complete_response_is_not_retried(repo):
    # A model that returned valid-length nonsense will mostly return more of it;
    # the retry is for the one failure we can name.
    state = make_state(repo)
    client = FakeClient(["{ not json at all", "{ still not json"],
                        stop_reasons=["end_turn", "end_turn"])
    curriculum.run(state, client)

    assert len(client.requests) == 1
    assert state.graph is None


def test_a_second_truncation_gives_up_without_a_third_call(repo):
    state = make_state(repo)
    client = FakeClient(
        [_truncated(DEFAULT), _truncated(DEFAULT)],
        stop_reasons=["max_tokens", "max_tokens"],
    )
    curriculum.run(state, client)

    assert len(client.requests) == 2
    assert state.graph is None
    assert any("proposal call failed" in e for e in state.errors)


def test_a_clean_first_response_never_costs_a_second_call(repo):
    state = make_state(repo)
    client = FakeClient(response(DEFAULT))
    curriculum.run(state, client)
    assert len(client.requests) == 1


# ── verbosity: understand is gone, objective carries it ───────────────────────

def test_the_planner_no_longer_asks_for_understand(repo):
    # It meant "what the user should take away", which is what `objective` is.
    assert "understand:" not in curriculum._SYSTEM_PROMPT
    assert "AT MOST 15 WORDS" in curriculum._SYSTEM_PROMPT


def test_a_b3_brief_carries_no_understand_key(repo):
    state = plan(repo)
    node = next(iter(state.graph.nodes.values()))
    assert "understand" not in node.lesson_brief
    # …and the objective is still what Teaching and the Grader read.
    assert node.objective().startswith("Explain what")


# ── use_library reaches the planner (LQ5) ─────────────────────────────────────

def test_the_planner_is_told_to_start_from_the_caller_facing_surface():
    prompt = curriculum._SYSTEM_PROMPT
    assert "use_library" in prompt
    assert "START FROM THE CALLER-FACING SURFACE" in prompt
    # The three-way distinction: what they call, what happens behind it, and
    # what is merely supporting evidence.
    assert "SUPPORTING EVIDENCE" in prompt
    assert "CONTRACTS and CONSTRAINTS" in prompt


def test_the_planner_is_warned_off_an_internals_tour_for_use_library():
    assert (
        "teaches this repository's internals in a sensible order has"
        in curriculum._SYSTEM_PROMPT
    )


def test_a_use_library_plan_sees_the_public_api_distinction(repo):
    """The whole chain: a use_library goal renders a dossier whose entry points
    carry their perspective, and that text is what the planner is given."""
    state = make_state(repo)
    state.goal = dict(state.goal, goal_type="use_library",
                      primary_goal="use this in my own project")
    state.investigation = dict(state.investigation)
    dossier = json.loads(json.dumps(state.investigation["dossier"]))
    dossier["entry_points"] = [
        {"file": "src/app/client.py", "symbol": "fetch",
         "perspective": "public_api", "how_it_enters": "what callers import"},
    ]
    state.investigation["dossier"] = dossier

    client = FakeClient(response(DEFAULT))
    curriculum.run(state, client)

    sent = client.requests[0]["messages"][0]["content"]
    assert "[public_api]" in sent
    assert '"goal_type": "use_library"' in sent
