"""M7 — `understanding_state` becomes derived, and blocking takes effect.

gap-model.md M7. This is the step that gives gaps their teeth: a node cannot be
`understood` while a blocking gap is unverified, even when the most recent answer
was graded `understood`. That is loss point 5, and until now the graph would
report mastery over two detected misconceptions sitting open on the same node.

Three things are defended here:

  1. The derivation table itself (§18.8), including that `verified` is the ONLY
     status that permits `understood` — `waived` does not.
  2. **The compatibility gate**, which is the reason this step is safe to ship:
     for every stored graph with no blocking gap, the derived value equals the
     stored value. Run over every session in `data/sessions.db`.
  3. **The structural rule** that production code reads the derivation rather
     than the raw attribute. A forgotten reader would silently use the stale
     stored value, which is the failure mode M7 introduces and the only one no
     behavioural test can catch.

Run with: uv run pytest tests/test_gap_understanding.py -v
"""
import ast
import sqlite3
from pathlib import Path

import pytest

from backend.learning import adaptation, progress
from backend.learning import store as learning_store
from backend.learning.gaps import Gap
from backend.learning.graph import (
    CodeAnchor,
    LearningGraph,
    LearningNode,
    understanding_of,
)


REPO = "https://github.com/psf/requests"
GOAL = {"primary_goal": "x", "goal_type": "understand_component"}
LIVE_DB = Path("data/sessions.db")

# Every module that may touch `node.understanding_state` directly, and why.
_RAW_ACCESS_ALLOWED = {
    # Defines the derivation and records the assessment it reads.
    "backend/learning/graph.py",
    # Persistence. The stored column IS the latest assessment, so the store must
    # write and read the raw value — deriving on save would make the database
    # depend on gap state and lose the input the derivation needs.
    "backend/learning/store.py",
}


def _node(state: str = "not_started", **kw) -> LearningNode:
    node = LearningNode(
        title="Understand the adapter",
        code_anchor=CodeAnchor(file="requests/adapters.py", line_start=1, line_end=20),
        lesson_brief={"objective": "Explain what the adapter owns", **kw},
    )
    node.understanding_state = state
    return node


def _blocking(status: str = "open") -> Gap:
    gap = Gap.create("wrong_model", "a false claim about the adapter")
    gap.status = status
    return gap


# ── the derivation ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("state", ["not_started", "partial", "failed", "understood"])
def test_with_no_gaps_the_derived_value_is_the_stored_value(state):
    """The compatibility rule, at the unit level: no blocking gap, no change."""
    assert understanding_of(_node(state)) == state


def test_an_open_blocking_gap_prevents_understood():
    """Loss point 5, the regression this whole phase exists to close.

    The latest answer was graded `understood` and the node still is not.
    """
    node = _node("understood")
    node.gap_state.gaps.append(_blocking("open"))
    assert understanding_of(node) == "partial"


def test_a_verified_gap_permits_understood():
    node = _node("understood")
    node.gap_state.gaps.append(_blocking("verified"))
    assert understanding_of(node) == "understood"


def test_a_waived_gap_does_NOT_permit_understood():
    """`verified` is the only status that permits it (§18.16 final state model).

    Waiving is a decision to stop working on something, not evidence about it.
    What it buys the learner is that the system stops asking — M8's business,
    not this function's.
    """
    node = _node("understood")
    node.gap_state.gaps.append(_blocking("waived"))
    assert understanding_of(node) == "partial"


def test_every_blocking_gap_must_be_verified_not_merely_one():
    node = _node("understood")
    node.gap_state.gaps.extend([_blocking("verified"), _blocking("open")])
    assert understanding_of(node) == "partial"


def test_a_non_blocking_gap_never_affects_the_outcome():
    """A `right_idea_wrong_altitude` gap is real and worth showing, but it is not
    a claim that the objective was missed."""
    node = _node("understood")
    node.gap_state.gaps.append(Gap.create("right_idea_wrong_altitude", "too low"))
    assert understanding_of(node) == "understood"


def test_failed_stays_failed_with_an_open_gap():
    """Not demoted to `partial`: the latest answer showed a real
    misunderstanding, which is a sharper fact than "some gap is open"."""
    node = _node("failed")
    node.gap_state.gaps.append(_blocking("open"))
    assert understanding_of(node) == "failed"


def test_not_started_stays_not_started_with_an_open_gap():
    """Gaps without an attempt should not happen; inventing progress if they do
    would be worse than reporting none."""
    node = _node("not_started")
    node.gap_state.gaps.append(_blocking("open"))
    assert understanding_of(node) == "not_started"


def test_partial_stays_partial():
    node = _node("partial")
    node.gap_state.gaps.append(_blocking("open"))
    assert understanding_of(node) == "partial"


def test_the_derivation_never_mutates_the_node():
    node = _node("understood")
    gap = _blocking("open")
    node.gap_state.gaps.append(gap)
    understanding_of(node)
    assert node.understanding_state == "understood"  # the stored input is intact
    assert gap.status == "open"


def test_mark_understanding_records_an_assessment_rather_than_a_conclusion():
    """Writing `understood` no longer makes a node understood."""
    graph = LearningGraph(repo_url=REPO, goal=GOAL)
    node = graph.add_node(_node())
    node.gap_state.gaps.append(_blocking("open"))
    graph.mark_understanding(node.id, "understood")
    assert node.understanding_state == "understood"      # recorded
    assert understanding_of(node) == "partial"           # not concluded


def test_mark_understood_override_cannot_confer_mastery_over_a_gap():
    """§18.16.2: a learner choosing to move on is not claiming mastery.

    M7 stopped this action from lying by demoting the result; M8 stopped it being
    taken at all on a gap-bearing node, routing it to `waive_remaining` instead.
    Both layers are asserted here because the guarantee is the conjunction: the
    stored assessment is never written, AND the derived value is not `understood`.
    """
    graph = LearningGraph(repo_url=REPO, goal=GOAL)
    node = graph.add_node(_node("partial"))
    node.gap_state.gaps.append(_blocking("open"))
    graph.override(node.id, "mark_understood")
    assert node.understanding_state == "partial"      # never overwritten
    assert understanding_of(node) != "understood"
    assert node.user_override == "waive_remaining"    # M8 migration


def test_mark_understood_cannot_confer_mastery_on_a_gap_free_node_either():
    """M0. The same guarantee as the test above, on the node shape that escaped it.

    §18.16.2 blocked the gap-bearing door and left this one open. The gap model
    was not what made the write wrong — a learner decision is not evidence of
    understanding, whether or not a misconception happens to be recorded.
    """
    graph = LearningGraph(repo_url=REPO, goal=GOAL)
    node = graph.add_node(_node())
    graph.override(node.id, "mark_understood")
    assert node.understanding_state == "not_started"   # never overwritten
    assert understanding_of(node) != "understood"
    assert node.user_override == "mark_understood"     # the intent IS recorded


# ── the consumers ────────────────────────────────────────────────────────────


def _two_node_area() -> LearningGraph:
    graph = LearningGraph(repo_url=REPO, goal=GOAL)
    a = graph.add_node(_node("understood", area_id="a1", priority="required"))
    b = graph.add_node(_node("understood", area_id="a1", priority="required"))
    ahead = graph.add_node(_node("not_started", area_id="a1", priority="recommended"))
    graph.add_edge(a.id, b.id, kind="sequence")
    graph.add_edge(b.id, ahead.id, kind="sequence")
    graph.set_current(a.id)
    for node in (a, b):
        node.visited = True
    return graph


def test_prune_ahead_becomes_stricter_for_free():
    """§18.8's knock-on: an area cannot be pruned on the strength of nodes that
    still carry unverified gaps. No change to `prune_ahead` was required."""
    clean = _two_node_area()
    assert adaptation.prune_ahead(clean), "two understood units should prune"

    gapped = _two_node_area()
    first = gapped.nodes[gapped.path_order()[0]]
    first.gap_state.gaps.append(_blocking("open"))
    assert adaptation.prune_ahead(gapped) == []


def test_to_dict_reports_the_derived_state():
    """This is what the UI renders; it must not report mastery over a gap."""
    graph = LearningGraph(repo_url=REPO, goal=GOAL)
    node = graph.add_node(_node("understood"))
    graph.set_current(node.id)
    node.gap_state.gaps.append(_blocking("open"))
    payload = graph.to_dict()
    shown = [n for n in payload["nodes"] if n["id"] == node.id][0]
    assert shown["understanding_state"] == "partial"


def test_goal_readiness_does_not_credit_an_unverified_node():
    """An open blocking gap removes the unit's demonstrated credit entirely.

    UPDATED for learning-graph M3a.3 (Model A'): `readiness()` is now
    demonstrated coverage rather than a weighted fold, so an unverified node
    drops from 1.0 to 0.0 rather than to 0.5. The property under test is
    unchanged and strictly stronger — M7's blocking still costs the credit.

    The node carries a real answer because demonstrated coverage is defined over
    assessed evidence; a bare `understanding_state` is "not yet assessed".
    """
    graph = LearningGraph(repo_url=REPO, goal=GOAL)
    node = graph.add_node(_node("understood", area_id="a1", priority="required"))
    graph.set_current(node.id)
    graph.record_attempt(node.id, "an answer", "understood", "because")
    clean = progress.goal_readiness(graph)
    assert clean == 1.0

    node.gap_state.gaps.append(_blocking("open"))
    gapped = progress.goal_readiness(graph)
    assert gapped < clean
    assert gapped == 0.0


def test_resume_point_will_not_pass_an_unverified_prerequisite():
    """`resume_point` advances past a warm-up only once it is understood, so an
    open gap on the warm-up now holds the learner there.

    The warm-up is `visited` so the walk steps over it and actually evaluates
    `main`'s prerequisite, and `current_node_id` points at the warm-up so the
    fallback is distinguishable from the qualifying answer.
    """
    graph = LearningGraph(repo_url=REPO, goal=GOAL)
    warm_up = graph.add_node(_node("understood"))
    main = graph.add_node(_node("not_started"))
    graph.add_edge(warm_up.id, main.id, kind="prerequisite")
    warm_up.visited = True
    graph.set_current(warm_up.id)
    assert graph.resume_point() == main.id

    warm_up.gap_state.gaps.append(_blocking("open"))
    assert graph.resume_point() == warm_up.id


# ── the compatibility gate, over real stored sessions ────────────────────────


@pytest.mark.skipif(not LIVE_DB.exists(), reason="no local sessions.db")
def test_every_stored_gap_free_node_derives_its_stored_state():
    """gap-model.md M7's compatibility gate, exactly as specified.

    Skipped where the database is absent (it is gitignored), because a gate that
    silently passes on an empty set is worse than one that says it did not run.
    """
    session_ids = [
        row[0] for row in sqlite3.connect(LIVE_DB).execute("select session_id from sessions")
    ]
    assert session_ids, "sessions.db exists but holds no sessions"

    checked = 0
    mismatches = []
    for session_id in session_ids:
        graph = learning_store.load_graph(session_id, LIVE_DB)
        if graph is None:
            continue
        for node in graph.nodes.values():
            if any(g.is_blocking and g.status != "verified" for g in node.gaps):
                continue  # legitimately expected to differ
            checked += 1
            derived = understanding_of(node)
            if derived != node.understanding_state:
                mismatches.append((session_id, node.id, node.understanding_state, derived))

    assert checked > 0, "no gap-free nodes to check"
    assert not mismatches, f"{len(mismatches)} stored nodes derive a different state: {mismatches[:5]}"


# ── the structural rule ──────────────────────────────────────────────────────


def _raw_attribute_reads(path: Path) -> list[int]:
    """Lines where `<something>.understanding_state` is READ or WRITTEN.

    AST-based rather than textual so a mention in a comment or docstring — of
    which there are many, since this is the field the whole phase is about —
    cannot fail the test.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "understanding_state"
    ]


def test_production_code_reads_the_derivation_not_the_raw_attribute():
    """The failure M7 introduces, and the only one no behavioural test catches.

    A reader left on `node.understanding_state` keeps compiling, keeps passing,
    and silently reports mastery over an unverified gap. So the rule is asserted
    structurally: outside the derivation's own module and the store, nothing in
    `backend/` may touch the attribute.
    """
    offenders = {}
    for path in sorted(Path("backend").rglob("*.py")):
        rel = path.as_posix()
        if rel in _RAW_ACCESS_ALLOWED:
            continue
        lines = _raw_attribute_reads(path)
        if lines:
            offenders[rel] = lines

    assert not offenders, (
        "these modules use the raw stored attribute instead of "
        f"understanding_of(node): {offenders}"
    )


def test_the_allowlist_itself_is_still_accurate():
    """Guards the guard: if an allowed module stops needing raw access, the
    allowlist should shrink rather than quietly permit a future regression."""
    for rel in _RAW_ACCESS_ALLOWED:
        assert _raw_attribute_reads(Path(rel)), (
            f"{rel} no longer touches understanding_state — remove it from "
            "_RAW_ACCESS_ALLOWED"
        )
