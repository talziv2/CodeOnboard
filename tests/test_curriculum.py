"""
Pytest tests for the objective-first planner's deterministic half.
Run with: uv run pytest tests/test_curriculum.py -v

There is no client here and no API key: selection, closure, area coverage, the
guard band and ordering are all pure functions over the model's proposal. That
is the point of B3 — the end of L1 is that curriculum size becomes something a
test can assert without an LLM (learning-engine.md "Done when" #9).
"""
import pytest

from backend.agents.mentor.curriculum import (
    AnchorWire,
    AreaWire,
    ObjectiveWire,
    band_report,
    core_set,
    dependency_closure,
    journey_size,
    order,
    select,
)


def obj(
    id: str,
    priority: str = "recommended",
    area: str = "a1",
    depends_on: list[str] | None = None,
    kind: str = "component",
) -> ObjectiveWire:
    return ObjectiveWire(
        id=id,
        title=f"Learn {id}",
        objective=f"Explain what {id} owns",
        kind=kind,
        priority=priority,
        area_id=area,
        depends_on=depends_on or [],
        anchors=[AnchorWire(file="src/app.py", symbol=id)],
        why="matters",
        understand="takeaway",
    )


def area(id: str, order_: int = 1) -> AreaWire:
    return AreaWire(id=id, title=f"Area {id}", why="relevant", order=order_)


def priorities(selected: list[ObjectiveWire]) -> dict[str, str]:
    return {o.id: o.priority for o in selected}


# ── the required set is the floor ─────────────────────────────────────────────

def test_every_required_objective_survives_selection():
    objectives = [obj(f"n{i}", priority="required") for i in range(11)]
    selected = select(objectives, [area("a1")], "map")
    assert journey_size(selected) == 11
    assert all(p == "required" for p in priorities(selected).values())


def test_the_required_set_outranks_the_band():
    # A goal that genuinely needs sixteen concepts gets sixteen, even though the
    # `map` band tops out at eighteen with only two units of room left over.
    objectives = [obj(f"r{i}", priority="required") for i in range(16)]
    objectives += [obj(f"x{i}") for i in range(6)]
    selected = select(objectives, [area("a1")], "map")
    got = priorities(selected)
    assert all(got[f"r{i}"] == "required" for i in range(16))
    # Two units of room remain under the band of 18; the rest are demoted.
    assert sum(1 for k, v in got.items() if k.startswith("x") and v != "optional") == 2


def test_a_dependency_of_a_required_objective_is_also_required():
    # A required objective whose foundation is optional is a required objective
    # that cannot be taught.
    objectives = [
        obj("top", priority="required", depends_on=["mid"]),
        obj("mid", priority="optional", depends_on=["base"]),
        obj("base", priority="optional"),
    ]
    selected = select(objectives, [area("a1")], "map")
    assert priorities(selected) == {
        "top": "required", "mid": "required", "base": "required"
    }


def test_closure_ignores_an_unknown_dependency_id():
    objectives = [obj("top", priority="required", depends_on=["ghost"])]
    by_id = {o.id: o for o in objectives}
    assert dependency_closure({"top"}, by_id) == {"top"}


def test_closure_survives_a_dependency_cycle():
    objectives = [
        obj("a", priority="required", depends_on=["b"]),
        obj("b", depends_on=["a"]),
    ]
    by_id = {o.id: o for o in objectives}
    assert dependency_closure({"a"}, by_id) == {"a", "b"}


# ── area coverage is a breadth obligation ─────────────────────────────────────

def test_every_declared_area_contributes_at_least_one_unit():
    objectives = [
        obj("core1", priority="required", area="routing"),
        obj("core2", priority="required", area="routing"),
        obj("di1", priority="recommended", area="di"),
        obj("di2", priority="optional", area="di"),
    ]
    areas = [area("routing", 1), area("di", 2)]
    selected = select(objectives, areas, "map")
    covered = {o.area_id for o in selected if o.priority != "optional"}
    assert covered == {"routing", "di"}
    # The better candidate is the one promoted, not just any of them.
    assert priorities(selected)["di1"] == "required"


def test_covering_an_area_pulls_in_that_units_dependencies_too():
    objectives = [
        obj("core", priority="required", area="routing"),
        obj("di1", priority="recommended", area="di", depends_on=["dibase"]),
        obj("dibase", priority="optional", area="di"),
    ]
    selected = select(objectives, [area("routing"), area("di")], "map")
    assert priorities(selected)["dibase"] == "required"


def test_an_area_with_no_candidates_is_not_forced():
    objectives = [obj("core", priority="required", area="routing")]
    selected = select(objectives, [area("routing"), area("empty")], "map")
    assert journey_size(selected) == 1


# ── the band is a guard, and demotes rather than discards ─────────────────────

def test_overflow_is_demoted_never_discarded():
    objectives = [obj(f"n{i}") for i in range(30)]
    selected = select(objectives, [area("a1")], "map")
    # Nothing is lost — depth stays one click away.
    assert len(selected) == 30
    assert journey_size(selected) == 18  # the `map` ceiling


@pytest.mark.parametrize(
    "code_depth,ceiling", [("map", 18), ("working", 22), ("implementation", 28)]
)
def test_the_band_moves_with_code_depth(code_depth, ceiling):
    objectives = [obj(f"n{i}") for i in range(40)]
    selected = select(objectives, [area("a1")], code_depth)
    assert journey_size(selected) == ceiling


def test_an_unknown_code_depth_falls_back_to_the_middle_band():
    objectives = [obj(f"n{i}") for i in range(40)]
    selected = select(objectives, [area("a1")], "nonsense")
    assert journey_size(selected) == 22


def test_a_small_curriculum_is_reported_but_never_padded():
    objectives = [obj("n1", priority="required"), obj("n2", priority="required")]
    selected = select(objectives, [area("a1")], "map")
    assert journey_size(selected) == 2
    report = band_report(selected, "map")
    assert report is not None and "advisory" in report


def test_a_journey_inside_its_band_reports_nothing():
    objectives = [obj(f"n{i}", priority="required") for i in range(8)]
    assert band_report(select(objectives, [area("a1")], "map"), "map") is None


def test_a_required_set_over_the_ceiling_is_reported():
    objectives = [obj(f"n{i}", priority="required") for i in range(20)]
    selected = select(objectives, [area("a1")], "map")
    assert "exceeds" in band_report(selected, "map")


# ── ordering ──────────────────────────────────────────────────────────────────

def test_dependencies_are_taught_before_what_needs_them():
    objectives = [
        obj("c", depends_on=["b"]),
        obj("a"),
        obj("b", depends_on=["a"]),
    ]
    assert [o.id for o in order(objectives)] == ["a", "b", "c"]


def test_model_order_breaks_ties_within_a_dependency_tier():
    # Nothing depends on anything, so the model's own sequencing stands.
    objectives = [obj("z"), obj("m"), obj("a")]
    assert [o.id for o in order(objectives)] == ["z", "m", "a"]


def test_a_dependency_cycle_costs_the_ordering_not_the_journey():
    objectives = [obj("a", depends_on=["b"]), obj("b", depends_on=["a"]), obj("c")]
    ordered = order(objectives)
    assert len(ordered) == 3
    assert ordered[0].id == "c"  # the orderable one goes first


def test_a_self_dependency_does_not_deadlock():
    objectives = [obj("a", depends_on=["a"]), obj("b")]
    assert {o.id for o in order(objectives)} == {"a", "b"}


def test_ordering_keeps_every_objective_exactly_once():
    objectives = [obj(f"n{i}", depends_on=[f"n{i-1}"] if i else []) for i in range(10)]
    ordered = order(objectives)
    assert [o.id for o in ordered] == [f"n{i}" for i in range(10)]


# ── the plan report: what the band is guarding ────────────────────────────────

def test_the_core_is_measured_before_the_band_touches_it():
    # The band is a guard around this number. Measuring it only AFTER the guard
    # has run would make a mis-set band invisible — the journey would always
    # look like it fitted.
    objectives = [obj(f"r{i}", priority="required") for i in range(20)]
    core = core_set(objectives, [area("a1")])
    assert len(core) == 20
    assert journey_size(select(objectives, [area("a1")], "map")) == 20


def test_the_core_counts_dependency_closure_and_area_promotions():
    objectives = [
        obj("req", priority="required", area="a1", depends_on=["dep"]),
        obj("dep", priority="optional", area="a1"),
        obj("other", priority="recommended", area="a2"),
    ]
    core = core_set(objectives, [area("a1"), area("a2")])
    assert core == {"req", "dep", "other"}


def test_core_and_select_agree_on_what_is_required():
    objectives = [
        obj("req", priority="required", depends_on=["dep"]),
        obj("dep", priority="optional"),
        obj("spare", priority="recommended"),
    ]
    areas = [area("a1")]
    core = core_set(objectives, areas)
    selected = select(objectives, areas, "map")
    assert {o.id for o in selected if o.priority == "required"} == core
