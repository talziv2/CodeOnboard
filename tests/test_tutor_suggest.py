"""The tier-3 boundary: a model may PROPOSE, and the graph decides.

Run with: uv run pytest tests/test_tutor_suggest.py -v

`suggest.validate` is the only thing standing between a model's opinion and a
control on a learner's screen. Two properties are asserted throughout:

  - a proposal the endpoint it names would refuse never reaches the learner. An
    offer that errors when pressed is worse than no offer;
  - an invalid proposal costs the PROPOSAL and never the answer. That is the rule
    `briefing/agent.py` applies to a note whose file will not resolve.

Pure: no API key, no database.
"""
import pytest

from backend.agents.tutor import suggest
from backend.learning import retry as retry_model, scope as scope_model
from backend.learning.gaps import REASSESSMENT_CAP, VERIFICATION_ATTEMPT_CAP, Gap
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.learning.tutor import SUGGESTION_KINDS


def _node(title="A", taught=True) -> LearningNode:
    node = LearningNode(
        title=title,
        code_anchor=CodeAnchor("a.py", 1, 20),
        lesson_brief={"objective": f"Explain {title}", "priority": "required"},
    )
    if taught:
        node.cached_lesson = {"prompt": "the question", "reveal": "the answer"}
    return node


def _graph(*nodes) -> LearningGraph:
    graph = LearningGraph(repo_url="r", goal={})
    for node in nodes:
        graph.add_node(node)
    for a, b in zip(nodes, nodes[1:]):
        graph.add_edge(a.id, b.id)
    graph.set_current(nodes[0].id)
    return graph


def _answered(node: LearningNode, classification="partial") -> LearningNode:
    node.attempts.append({"answer": "a", "classification": classification,
                          "rationale": "r", "kind": "assessment", "graded": True})
    node.understanding_state = classification
    return node


# ── the vocabulary is closed ──────────────────────────────────────────────────


def test_the_vocabulary_maps_only_onto_endpoints_that_already_exist():
    """No `open_gap`, no `insert_prerequisite`, no `mark_understood`.

    Those are decisions the learning engine makes from graded evidence. A
    conversation is not that, so they are not spellable.
    """
    assert SUGGESTION_KINDS == {"verify", "reassess", "jump", "deepen"}
    assert "shorter" not in SUGGESTION_KINDS, (
        "demoting a journey on the strength of a conversation is the system "
        "deciding the learner has had enough"
    )


@pytest.mark.parametrize("raw", [
    None, {}, {"kind": ""}, {"kind": "open_gap"}, {"kind": "shorter"},
    {"kind": "mark_understood"}, {"kind": "insert_prerequisite"},
    {"node_id": "x"},
])
def test_anything_outside_the_vocabulary_is_dropped(raw):
    graph = _graph(_node())
    assert suggest.validate(graph, graph.nodes[graph.current_node_id], raw) is None


def test_a_suggestion_with_no_node_is_dropped():
    graph = _graph(_node())
    assert suggest.validate(graph, None, {"kind": "reassess"}) is None


# ── verify ────────────────────────────────────────────────────────────────────


def test_verify_resolves_to_the_gap_the_engine_would_actually_aim_at():
    node = _answered(_node())
    gap = Gap.create(kind="wrong_model", claim="c", objective_part="o")
    node.gap_state.gaps.append(gap)
    graph = _graph(node)

    offered = suggest.validate(graph, node, {"kind": "verify", "gap_id": gap.id})
    assert offered.kind == "verify"
    assert offered.gap_id == gap.id
    assert offered.gap_id == retry_model.offer(node).gap_id
    assert offered.label_key == "checkGap"


def test_verify_with_no_gap_named_still_resolves_to_the_engines_choice():
    node = _answered(_node())
    gap = Gap.create(kind="wrong_model", claim="c", objective_part="o")
    node.gap_state.gaps.append(gap)
    graph = _graph(node)
    assert suggest.validate(graph, node, {"kind": "verify"}).gap_id == gap.id


def test_verify_naming_a_different_gap_is_dropped():
    """The model does not get to overrule precedence."""
    node = _answered(_node())
    leading = Gap.create(kind="missing_prerequisite", claim="c1", objective_part="o")
    other = Gap.create(kind="right_idea_wrong_altitude", claim="c2", objective_part="o")
    node.gap_state.gaps.extend([leading, other])
    graph = _graph(node)
    assert suggest.validate(graph, node, {"kind": "verify", "gap_id": other.id}) is None


def test_verify_on_a_node_with_no_open_gap_is_dropped():
    node = _answered(_node())
    graph = _graph(node)
    assert suggest.validate(graph, node, {"kind": "verify", "gap_id": "x"}) is None


def test_verify_on_an_exhausted_gap_is_dropped():
    """The per-gap cap is `adaptation`'s business; this must not disagree with it."""
    node = _answered(_node())
    gap = Gap.create(kind="wrong_model", claim="c", objective_part="o")
    for _ in range(VERIFICATION_ATTEMPT_CAP):
        gap.record_failed_verification()
    node.gap_state.gaps.append(gap)
    graph = _graph(node)
    assert suggest.validate(graph, node, {"kind": "verify", "gap_id": gap.id}) is None


def test_verify_on_a_gap_from_another_node_is_dropped():
    a, b = _answered(_node("A")), _answered(_node("B"))
    foreign = Gap.create(kind="wrong_model", claim="c", objective_part="o")
    b.gap_state.gaps.append(foreign)
    graph = _graph(a, b)
    assert suggest.validate(graph, a, {"kind": "verify", "gap_id": foreign.id}) is None


# ── reassess ──────────────────────────────────────────────────────────────────


def test_reassess_is_offered_when_there_is_budget():
    node = _answered(_node())
    graph = _graph(node)
    offered = suggest.validate(graph, node, {"kind": "reassess"})
    assert offered.kind == "reassess"
    assert offered.node_id == node.id
    assert offered.label_key == "askAgain"


def test_reassess_is_dropped_when_the_budget_is_spent():
    node = _answered(_node())
    node.gap_state.reassessments = REASSESSMENT_CAP
    graph = _graph(node)
    assert suggest.validate(graph, node, {"kind": "reassess"}) is None


@pytest.mark.parametrize("field", ["pending_verification", "pending_reassessment"])
def test_reassess_is_dropped_while_a_question_is_already_on_screen(field):
    """Offering a second question abandons a budget already spent."""
    node = _answered(_node())
    setattr(node.gap_state, field, {"question": "already asked"})
    graph = _graph(node)
    assert suggest.validate(graph, node, {"kind": "reassess"}) is None


def test_reassess_is_dropped_on_a_stop_that_was_never_taught():
    node = _node(taught=False)
    graph = _graph(node)
    assert suggest.validate(graph, node, {"kind": "reassess"}) is None


def test_reassess_is_dropped_with_no_objective():
    node = _answered(_node())
    node.lesson_brief = {}
    graph = _graph(node)
    assert suggest.validate(graph, node, {"kind": "reassess"}) is None


# ── jump ──────────────────────────────────────────────────────────────────────


def test_jump_to_a_stop_on_the_route_is_offered():
    a, b = _node("A"), _node("B")
    graph = _graph(a, b)
    offered = suggest.validate(graph, a, {"kind": "jump", "node_id": b.id})
    assert offered.kind == "jump"
    assert offered.node_id == b.id


@pytest.mark.parametrize("target", ["", "not-a-node", None])
def test_jump_to_an_unknown_stop_is_dropped(target):
    a, b = _node("A"), _node("B")
    graph = _graph(a, b)
    assert suggest.validate(graph, a, {"kind": "jump", "node_id": target}) is None


def test_jump_to_the_stop_they_are_already_on_is_dropped():
    a = _node("A")
    graph = _graph(a, _node("B"))
    assert suggest.validate(graph, a, {"kind": "jump", "node_id": a.id}) is None


def test_jump_to_an_off_path_node_is_allowed_because_jumping_is_unconditional():
    """Mirrors `/jump`, which enforces no dependencies and locks no stop.

    Refusing an offer the endpoint would honour is the same defect as offering one
    it would refuse — and `path_order()` appends off-path nodes anyway, so there
    is no route filter to apply even if we wanted one.
    """
    a, b = _node("A"), _node("B")
    graph = _graph(a, b)
    orphan = graph.add_node(_node("orphan"))
    assert suggest.validate(graph, a, {"kind": "jump", "node_id": orphan.id}) is not None


# ── deepen ────────────────────────────────────────────────────────────────────


def test_deepen_is_offered_only_when_there_is_optional_material():
    a, b = _node("A"), _node("B")
    graph = _graph(a, b)
    assert suggest.validate(graph, a, {"kind": "deepen"}) is None

    b.lesson_brief = {**b.lesson_brief, "priority": "optional"}
    assert scope_model.can_deepen(graph) is True
    offered = suggest.validate(graph, a, {"kind": "deepen"})
    assert offered.kind == "deepen"
    assert offered.label_key == "goDeeper"


def test_the_deepen_offer_agrees_with_what_deepen_would_do():
    """One definition of "material in reserve", so the offer cannot disagree with
    the endpoint it offers."""
    a, b = _node("A"), _node("B")
    graph = _graph(a, b)
    b.lesson_brief = {**b.lesson_brief, "priority": "optional"}

    assert suggest.validate(graph, a, {"kind": "deepen"}) is not None
    promoted = scope_model.deepen(graph)
    assert promoted == [b.id]
    # Nothing left in reserve, so the offer withdraws.
    assert suggest.validate(graph, a, {"kind": "deepen"}) is None


# ── it never raises, and never mutates ────────────────────────────────────────


@pytest.mark.parametrize("raw", [
    {"kind": "jump", "node_id": {"not": "a string"}},
    {"kind": "verify", "gap_id": ["list"]},
    {"kind": "jump", "node_id": 12345},
])
def test_a_malformed_proposal_costs_the_proposal_never_an_exception(raw):
    node = _answered(_node())
    graph = _graph(node)
    assert suggest.validate(graph, node, raw) is None


def test_validating_never_mutates_the_graph():
    import json

    a, b = _answered(_node("A")), _node("B")
    b.lesson_brief = {**b.lesson_brief, "priority": "optional"}
    graph = _graph(a, b)
    before = json.dumps(graph.to_dict(), sort_keys=True)

    for raw in ({"kind": "reassess"}, {"kind": "jump", "node_id": b.id},
                {"kind": "deepen"}, {"kind": "verify"}):
        suggest.validate(graph, a, raw)

    assert json.dumps(graph.to_dict(), sort_keys=True) == before


def test_the_wire_shape_is_stable():
    node = _answered(_node())
    graph = _graph(node)
    offered = suggest.validate(graph, node, {"kind": "reassess"})
    assert set(offered.to_dict()) == {"kind", "label_key", "node_id", "gap_id"}
