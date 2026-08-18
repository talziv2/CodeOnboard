"""M5 — remediation becomes gap-scoped.

gap-model.md M5. M4 decided *which* gaps a response owes; M5 is about those gaps
actually reaching the prompts. The failure this guards against is quiet: a
re-teach that runs, succeeds, and corrects only one of the three misconceptions
it was given, leaving two silently abandoned with nothing queued to come back
for them.

Two layers are tested, because the wiring can break in either:
  - the PROMPT layer — does `reteach`/`followup` actually put every target in
    front of the model, exactly once?
  - the FLOW layer — does `/respond` hand the M4 plan's targets down, rather
    than letting something downstream re-derive them from `gap_kind`?

The qualitative half of M5 — whether a three-gap re-teach is a good *lesson* —
is not assertable and is not attempted here. See
`docs/planning/phases/evidence/m5-multi-gap-reteach/`.

Run with: uv run pytest tests/test_gap_remediation.py -v
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import backend.api as api
from backend.agents.mentor.mutator import Diagnosis
from backend.agents.teaching import respond as teaching_respond
from backend.learning import store as learning_store
from backend.learning.adaptation import decide_all
from backend.learning.gaps import Gap
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.pipeline.state import OnboardState

from tests.test_session_api import (
    FAKE_GOAL,
    FAKE_LESSON,
    FAKE_REPO_URL,
    _mutator_inserts_prerequisite,
    _teaching_side_effect,
)


CLAIM_A = "child path_cost and depth are filled in later by the search algorithm"
CLAIM_B = "solution() returns both the states and the actions"
CLAIM_C = "expand() returns nodes already scored by the heuristic"


@pytest.fixture(autouse=True)
def _env_and_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("CODEONBOARD_GAPS", "1")
    monkeypatch.setattr(api, "SESSIONS_DB_PATH", tmp_path / "sessions.db")
    monkeypatch.setattr(api.anthropic, "Anthropic", lambda **kw: MagicMock())


@pytest.fixture
def client():
    return TestClient(api.app)


def _node(**kw) -> LearningNode:
    node = LearningNode(
        title="Understand Node as the universal search tree unit",
        code_anchor=CodeAnchor(file="search.py", line_start=68, line_end=130),
        concept_tags=["component"],
        lesson_brief={"objective": "Explain what a Node holds", **kw},
    )
    node.cached_lesson = {"prompt": "What does expand() build?", "setup": "…"}
    return node


def _state_with(node: LearningNode) -> OnboardState:
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    graph.add_node(node)
    graph.set_current(node.id)
    state = OnboardState(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    state.graph = graph
    return state


def _lesson_client() -> MagicMock:
    payload = json.dumps({
        "why_now": "w", "setup": "s", "prompt": "p", "reveal": "r",
        "takeaway": "t", "ownership": "o", "expected_answer": "e",
    })
    message = MagicMock()
    message.content = [MagicMock(text=payload)]
    client = MagicMock()
    client.messages.create.return_value = message
    return client


def _sent(client: MagicMock) -> str:
    return client.messages.create.call_args.kwargs["messages"][0]["content"]


def _sent_system(client: MagicMock) -> str:
    return client.messages.create.call_args.kwargs["system"]


# ── 1. the single-gap case is behaviourally the old path ─────────────────────


def test_no_gaps_sends_the_pre_m5_prompt_unchanged():
    """Flag-off and every pre-gap session: not "compatible", byte-identical."""
    node = _node()
    state = _state_with(node)
    with_gaps = _lesson_client()
    teaching_respond.reteach(state, node, "ans", "why", "src", client=with_gaps, gaps=())

    node2 = _node()
    state2 = _state_with(node2)
    without = _lesson_client()
    teaching_respond.reteach(state2, node2, "ans", "why", "src", client=without)

    assert _sent(with_gaps) == _sent(without)
    assert "MISCONCEPTION to correct" not in _sent(without)


def test_one_gap_is_named_in_the_singular():
    node = _node()
    state = _state_with(node)
    client = _lesson_client()
    gap = Gap.create("wrong_model", CLAIM_A, objective_part="what a Node holds")
    teaching_respond.reteach(state, node, "ans", "why", "src", client=client, gaps=(gap,))
    sent = _sent(client)
    assert "The MISCONCEPTION to correct:" in sent
    assert CLAIM_A in sent
    assert "what a Node holds" in sent


def test_a_single_gap_reteach_still_replaces_the_cached_lesson():
    """The pre-M5 contract: the corrected lesson becomes the lesson."""
    node = _node()
    state = _state_with(node)
    gap = Gap.create("wrong_model", CLAIM_A)
    out = teaching_respond.reteach(
        state, node, "ans", "why", "src", client=_lesson_client(), gaps=(gap,)
    )
    assert out is not None
    assert node.cached_lesson["setup"] == "s"


# ── 2. every target reaches the prompt, exactly once ─────────────────────────


def test_a_multi_gap_reteach_names_every_target_exactly_once():
    node = _node()
    state = _state_with(node)
    client = _lesson_client()
    gaps = tuple(Gap.create("wrong_model", c) for c in (CLAIM_A, CLAIM_B, CLAIM_C))
    teaching_respond.reteach(state, node, "ans", "why", "src", client=client, gaps=gaps)
    sent = _sent(client)
    for claim in (CLAIM_A, CLAIM_B, CLAIM_C):
        assert sent.count(claim) == 1, claim
    assert "3 MISCONCEPTIONS to correct" in sent


def test_the_reteach_system_prompt_demands_one_lesson_not_a_list():
    """The qualitative risk M5 names, pinned as far as a test can pin it: the
    instruction to integrate must actually be present."""
    node = _node()
    state = _state_with(node)
    client = _lesson_client()
    gaps = (Gap.create("wrong_model", CLAIM_A), Gap.create("wrong_model", CLAIM_B))
    teaching_respond.reteach(state, node, "ans", "why", "src", client=client, gaps=gaps)
    system = _sent_system(client)
    assert "ONE LESSON, NOT SEVERAL STACKED TOGETHER" in system
    flat = " ".join(system.split())
    assert "CANNOT be answered while still holding ANY of them" in flat
    assert "FIND THE ROOT FIRST" in flat
    # The two defects the live probe found: checklist structure, and length
    # growing with the number of corrections.
    assert "Never write \"Misconception 1 / 2 / 3\"" in flat
    assert "LENGTH DOES NOT SCALE WITH THE NUMBER OF MISCONCEPTIONS" in flat


def test_a_followup_also_receives_its_targets():
    node = _node()
    state = _state_with(node)
    client = _lesson_client()
    client.messages.create.return_value.content = [MagicMock(text='{"text": "q?"}')]
    gaps = tuple(Gap.create("right_idea_wrong_altitude", c) for c in (CLAIM_A, CLAIM_B))
    teaching_respond.followup(state, node, "ans", "why", client=client, gaps=gaps)
    sent = _sent(client)
    assert CLAIM_A in sent and CLAIM_B in sent


# ── 3. deferred gaps are not treated as remediated ───────────────────────────


def test_deferred_gaps_never_reach_the_prompt():
    """A gap outside the plan's targets is real and still open, but it is not
    what is being taught now. Listing it would have the lesson correct
    something the policy did not select."""
    node = _node()
    state = _state_with(node)
    client = _lesson_client()
    targeted = Gap.create("wrong_model", CLAIM_A)
    other_kind = Gap.create("right_idea_wrong_altitude", CLAIM_B)
    plan = decide_all("confused", [targeted, other_kind])
    assert plan.action == "reteach"

    teaching_respond.reteach(
        state, node, "ans", "why", "src", client=client, gaps=plan.targets
    )
    sent = _sent(client)
    assert CLAIM_A in sent
    assert CLAIM_B not in sent


def test_gaps_outside_the_active_set_stay_open_after_a_reteach():
    node = _node()
    gaps = [Gap.create("wrong_model", f"claim {i}") for i in range(5)]
    node.gap_state.gaps.extend(gaps)
    state = _state_with(node)
    plan = decide_all("confused", list(node.gaps))
    teaching_respond.reteach(
        state, node, "ans", "why", "src", client=_lesson_client(), gaps=plan.targets
    )
    assert all(g.status == "open" for g in node.gaps)


# ── 4. a prerequisite is tied to exactly one gap ─────────────────────────────


def test_the_plan_gives_a_prerequisite_exactly_one_target():
    gaps = [Gap.create("missing_prerequisite", "A"),
            Gap.create("missing_prerequisite", "B"),
            Gap.create("wrong_model", CLAIM_A)]
    plan = decide_all("confused", gaps)
    assert plan.action == "prerequisite"
    assert len(plan.targets) == 1


def test_the_prereq_prompt_states_the_specific_claim_not_just_the_kind():
    from backend.agents.mentor.mutator import _build_prereq_prompt

    anchor = _node()
    gap = Gap.create("missing_prerequisite", "a frontier is a sorted list",
                     objective_part="what expand() consumes")
    candidates = [{"file": "search.py", "name": "expand", "type": "function",
                   "start_line": 1, "end_line": 5, "content": "def expand(): ..."}]
    prompt = _build_prereq_prompt(
        anchor, candidates, {},
        diagnosis=Diagnosis(answer="a", rationale="r", gap_kind="missing_prerequisite",
                            gap=gap),
    )
    assert "THE MISCONCEPTION THIS WARM-UP MUST UNBLOCK:" in prompt
    assert "a frontier is a sorted list" in prompt
    assert "what expand() consumes" in prompt


def test_the_prereq_prompt_falls_back_to_the_kind_without_a_gap():
    """Pre-M5 shape, for flag-off and for sessions with no gap records."""
    from backend.agents.mentor.mutator import _build_prereq_prompt

    prompt = _build_prereq_prompt(
        _node(), [{"file": "f", "name": "n", "type": "function",
                   "start_line": 1, "end_line": 2, "content": "c"}], {},
        diagnosis=Diagnosis(answer="a", rationale="r", gap_kind="missing_prerequisite"),
    )
    assert "Diagnosed gap: missing_prerequisite" in prompt
    assert "MUST UNBLOCK" not in prompt


def test_retry_picks_its_gap_from_the_plan_not_from_the_scalar():
    """`/retry` has no grade in scope. The gap must come from `decide_all` over
    the node's open gaps — deriving it from the attempt's `gap_kind` would pick
    a category, and several open gaps can share one."""
    node = _node()
    wrong = Gap.create("wrong_model", CLAIM_A)
    foundation = Gap.create("missing_prerequisite", "does not know what a frontier is")
    node.gap_state.gaps.extend([wrong, foundation])
    node.attempts.append({"answer": "a", "rationale": "r", "gap_kind": "wrong_model"})

    diagnosis = Diagnosis.from_node(node)
    # Precedence, not the recorded scalar, chooses.
    assert diagnosis.gap is foundation
    assert diagnosis.gap_kind == "missing_prerequisite"
    assert diagnosis.answer == "a"


def test_from_node_falls_back_to_the_attempt_when_there_are_no_gaps():
    node = _node()
    node.attempts.append({"answer": "a", "rationale": "r", "gap_kind": "wrong_model"})
    diagnosis = Diagnosis.from_node(node)
    assert diagnosis.gap is None
    assert diagnosis.gap_kind == "wrong_model"


def test_from_node_is_none_when_there_is_nothing_to_say():
    assert Diagnosis.from_node(_node()) is None


# ── 5. `remediates` survives a round trip ────────────────────────────────────


def _inserted_warm_up(diagnosis: Diagnosis) -> LearningNode:
    """Run the real `mutate()` prerequisite path and return the node it spliced in.

    Through `mutate` rather than a construction helper, because the point is
    that `remediates` survives the whole generation path — parse, ground, build
    — not that a helper can be called with the right argument.
    """
    from backend.agents.mentor.mutator import mutate

    from tests.test_prerequisite_diagnosis import (  # the established harness
        CANDIDATES, POOL, PREREQ_JSON,
    )
    from backend.repo.skeleton import Skeleton

    state, node_id = _prereq_state()
    message = MagicMock()
    message.content = [MagicMock(text=json.dumps(PREREQ_JSON))]
    llm = MagicMock()
    llm.messages.create.return_value = message

    with patch("backend.agents.mentor.mutator.candidate_pool", return_value=POOL), \
         patch("backend.agents.mentor.mutator.build_skeleton",
               side_effect=lambda repo_path: Skeleton.from_chunks(
                   [{**c, "content": None} for c in CANDIDATES],
                   file_lines={"search.py": 1500})), \
         patch("backend.agents.mentor.mutator._candidates_as_chunks",
               side_effect=lambda repo_path, pool: CANDIDATES if pool else []):
        mutate(state, "prerequisite", client=llm, diagnosis=diagnosis)

    inserted = state.last_mutation.get("new_node_id")
    assert inserted, f"no prerequisite was inserted: {state.last_mutation}"
    return state.graph.nodes[inserted]


def _prereq_state() -> tuple[OnboardState, str]:
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    first = graph.add_node(LearningNode(
        title="Problem contract",
        code_anchor=CodeAnchor(file="search.py", line_start=15, line_end=62),
    ))
    node = graph.add_node(LearningNode(
        title="Understand Node as the universal search tree unit",
        code_anchor=CodeAnchor(file="search.py", line_start=68, line_end=130),
        concept_tags=["component"],
        lesson_brief={"why": "w", "understand": "u"},
    ))
    graph.add_edge(first.id, node.id, kind="sequence")
    graph.set_current(node.id)
    state = OnboardState(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    state.repo_path = "data/repos/aima"
    state.graph = graph
    return state, node.id


def test_remediates_is_recorded_on_the_generated_warm_up():
    gap = Gap.create("missing_prerequisite", "does not know what a frontier is")
    warm_up = _inserted_warm_up(Diagnosis(answer="a", rationale="r", gap=gap))
    assert warm_up.lesson_brief["remediates"] == [gap.id]


def test_a_warm_up_generated_without_a_gap_has_no_remediates_key():
    """Pre-gap warm-ups keep exactly the brief they have always had."""
    warm_up = _inserted_warm_up(Diagnosis(answer="a", rationale="r"))
    assert "remediates" not in warm_up.lesson_brief


def test_remediates_round_trips_through_the_store(tmp_path):
    """`lesson_brief` is persisted as JSON, so the relationship must survive a
    save/load with no extra plumbing — asserted rather than assumed."""
    db = tmp_path / "sessions.db"
    gap = Gap.create("missing_prerequisite", "does not know what a frontier is")
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    warm_up = graph.add_node(LearningNode(
        title="Warm-up: the frontier",
        code_anchor=CodeAnchor(file="search.py", line_start=1, line_end=9),
        lesson_brief={"objective": "o", "priority": "required",
                      "remediates": [gap.id]},
    ))
    graph.set_current(warm_up.id)
    learning_store.save_graph(graph, db)

    reloaded = learning_store.load_graph(graph.session_id, db)
    assert reloaded.nodes[warm_up.id].lesson_brief["remediates"] == [gap.id]


def test_no_remediates_key_when_there_is_no_gap():
    """Pre-gap warm-ups keep exactly the brief they have always had."""
    node = _node()
    assert "remediates" not in (node.lesson_brief or {})


# ── 6. duplicate references do not become duplicate targets ──────────────────


def test_two_references_to_one_gap_produce_one_target():
    """M3 measured the model naming one id twice in a single re-grade. Matching
    creates nothing, so the node cannot hold a duplicate — but the plan is
    defensive about it, because a target list mentioning one misconception
    twice would ask the lesson to correct it twice."""
    gap = Gap.create("wrong_model", CLAIM_A)
    plan = decide_all("confused", [gap, gap])
    assert len(plan.targets) == 1


def test_a_duplicated_gap_reaches_the_prompt_once():
    node = _node()
    state = _state_with(node)
    client = _lesson_client()
    gap = Gap.create("wrong_model", CLAIM_A)
    plan = decide_all("confused", [gap, gap])
    teaching_respond.reteach(
        state, node, "ans", "why", "src", client=client, gaps=plan.targets
    )
    assert _sent(client).count(CLAIM_A) == 1


# ── the flow: /respond hands the plan down ───────────────────────────────────


def _graph_with_gaps(*gaps: Gap) -> LearningGraph:
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    a = graph.add_node(LearningNode(
        title="Understand the adapter layer",
        code_anchor=CodeAnchor(file="requests/adapters.py", line_start=1, line_end=20),
        concept_tags=["architecture"],
        lesson_brief={"objective": "Explain what the adapter owns",
                      "area_id": "a1", "priority": "required"},
    ))
    b = graph.add_node(LearningNode(
        title="Trace the send",
        code_anchor=CodeAnchor(file="requests/sessions.py", line_start=1, line_end=20),
        concept_tags=["flow"],
        lesson_brief={"objective": "Trace it", "area_id": "a1", "priority": "required"},
    ))
    graph.add_edge(a.id, b.id, kind="sequence")
    graph.set_current(a.id)
    a.gap_state.gaps.extend(gaps)
    return graph


def _run_respond(client, graph, classification, gap_kind):
    def _pipeline(repo_url, goal, client=None, progress_id=""):
        state = MagicMock()
        state.graph = graph
        state.errors = []
        return state

    def _grader(state, user_response, client=None):
        state.last_grade = {"classification": classification,
                            "gap_kind": gap_kind, "rationale": "because"}
        return state

    with patch("backend.api.run_pipeline", side_effect=_pipeline), \
         patch("backend.api.run_teaching", side_effect=_teaching_side_effect), \
         patch("backend.api.clone_repo", return_value="data/repos/requests"):
        body = client.post(
            "/session/start", json={"repo_url": FAKE_REPO_URL, "goal": FAKE_GOAL}
        ).json()
        session_id = body["session_id"]
        client.get(f"/session/{session_id}/lesson")
        with patch("backend.api.run_grader", side_effect=_grader), \
             patch("backend.api.mutate_graph",
                   side_effect=_mutator_inserts_prerequisite) as mutate, \
             patch("backend.api._node_source", return_value="source"), \
             patch("backend.api.teaching_respond") as respond:
            respond.reteach.return_value = MagicMock()
            respond.hint.return_value = "h"
            respond.followup.return_value = "f"
            result = client.post(
                f"/session/{session_id}/respond", json={"response": "my answer"}
            ).json()
    return result, mutate, respond


def test_respond_hands_every_reteach_target_to_teaching(client):
    a = Gap.create("wrong_model", CLAIM_A)
    b = Gap.create("wrong_model", CLAIM_B)
    graph = _graph_with_gaps(a, b)
    result, _, respond = _run_respond(client, graph, "confused", "wrong_model")
    assert result["adaptation"]["kind"] == "reteach"
    passed = respond.reteach.call_args.kwargs["gaps"]
    assert [g.id for g in passed] == [a.id, b.id]


def test_respond_hands_the_prerequisite_exactly_one_gap(client):
    foundation = Gap.create("missing_prerequisite", "no idea what an adapter is")
    other = Gap.create("wrong_model", CLAIM_A)
    graph = _graph_with_gaps(foundation, other)
    result, mutate, _ = _run_respond(client, graph, "confused", "missing_prerequisite")
    assert result["adaptation"]["kind"] == "prerequisite"
    diagnosis = mutate.call_args.kwargs["diagnosis"]
    assert diagnosis.gap is not None
    assert diagnosis.gap.id == foundation.id


def test_respond_with_no_gaps_still_uses_the_scalar(client):
    """The flag-off world. `decide_all` must not downgrade this to `none`."""
    graph = _graph_with_gaps()
    result, _, respond = _run_respond(client, graph, "partial", "wrong_model")
    assert result["adaptation"]["kind"] == "reteach"
    assert respond.reteach.call_args.kwargs["gaps"] == ()


def test_respond_keeps_every_pre_existing_response_key(client):
    """M9's compatibility invariant: "existing response keys unchanged; an
    un-updated client keeps working".

    Asserted as a SUPERSET rather than an exact set. M9 adds `gaps` and
    `complete` deliberately, and an exact-set assertion would have to be edited
    every time the surface grows — which turns the guard into a chore and teaches
    people to update it without thinking. What must never happen is a key
    *disappearing*, and that is what this pins.
    """
    graph = _graph_with_gaps(Gap.create("wrong_model", CLAIM_A))
    result, _, _ = _run_respond(client, graph, "confused", "wrong_model")
    assert {
        "classification", "gap_kind", "rationale", "understanding_state",
        "mutation", "adaptation", "current_node_id",
    } <= set(result)
