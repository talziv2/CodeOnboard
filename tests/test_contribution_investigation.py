# The contribution task reaches the investigation — and what it demands there.
#
# THE FIRST TEST IN THIS FILE IS THE WHOLE POINT OF THE FEATURE.
#
# `contribution_context` was collected by the interview, carried through goal
# synthesis, and then dropped by `_task()` — so two learners with different
# contribution tasks got the SAME investigation of the same repository, and the
# task first mattered at planning time, by which point the repository
# understanding was already fixed and could only be filtered.
#
# Everything else here guards the section that redirection produces: a change
# boundary that is grounded like every other citation, and exit criteria that ask
# for it without lowering any floor that already existed.

import pytest

from backend.repo import investigation as inv


CONTRIBUTION_GOAL = {
    "goal_type": "contribute_code",
    "primary_goal": "add a getter",
    "contribution_context": (
        "Add RequestsCookieJar.get_all(name) returning every value stored "
        "under that name, and cover its boundary cases with tests."
    ),
    "contribution_scope": "a small addition; existing behaviour is untouched",
    "code_depth": "working",
}


class TestTaskReachesInvestigation:
    def test_contribution_task_appears_in_the_investigators_brief(self):
        task = inv._task(CONTRIBUTION_GOAL)
        assert "RequestsCookieJar.get_all" in task

    def test_two_different_tasks_produce_different_briefs(self):
        """The claim the whole journey rests on: the task shapes the investigation.

        Before this, both of these produced a byte-identical brief, because the
        only fields `_task` read were the goal type, the primary goal, the focus
        area and the code depth — none of which differ between them.
        """
        other = {**CONTRIBUTION_GOAL, "contribution_context": "Fix the cookie expiry parser"}
        assert inv._task(CONTRIBUTION_GOAL) != inv._task(other)

    def test_the_expected_size_reaches_the_brief_too(self):
        assert "existing behaviour is untouched" in inv._task(CONTRIBUTION_GOAL)

    def test_brief_asks_for_the_boundary_the_criteria_demand(self):
        """The prompt and the contract have to be about the same things.

        A brief that never mentions the tests or the edge cases while the exit
        criteria require them produces rejection loops, not better dossiers.
        """
        task = inv._task(CONTRIBUTION_GOAL)
        for demand in ("change_boundary", "TESTS THAT ALREADY GUARD",
                       "EDGE CASES", "MUST NOT TOUCH", "CONTRACT"):
            assert demand in task

    def test_brief_forbids_anchoring_on_the_symbol_being_added(self):
        """A failure mode the contribution framing INTRODUCED, found in rehearsal.

        Asked to investigate a change, the model anchored seven citations on
        `RequestsCookieJar.get_all` — the method the developer is about to write.
        It does not exist, so none of them resolved, and the run spent turns
        re-trying them until it hit its budget and was salvaged.

        Describing the change is prose; anchoring is about code that is there.
        """
        task = inv._task(CONTRIBUTION_GOAL)
        assert "THE CHANGE DOES NOT EXIST YET" in task
        assert "can never" in task and "be verified" in task

    def test_brief_does_not_ask_for_a_smaller_investigation(self):
        """It REDIRECTS, it does not shrink.

        Shortness has to be earned in the curriculum's required set. A brief that
        told the investigator to establish less would produce a thinner dossier
        and a journey that is short because it is uninformed — which is exactly
        the artificial cap this design refuses.
        """
        # Matched on fragments that do not span the brief's line wrapping — a
        # test that pins the wrapping fails on a reflow rather than on a meaning.
        task = inv._task(CONTRIBUTION_GOAL)
        assert "NOT a licence" in task
        assert "exit criteria still apply" in task


class TestOtherGoalTypesAreUntouched:
    @pytest.mark.parametrize("goal_type", [
        "understand_architecture", "understand_system", "understand_component",
        "use_library", "improve_existing_system", "debug_issue",
    ])
    def test_non_contribution_goals_get_the_original_brief(self, goal_type):
        goal = {**CONTRIBUTION_GOAL, "goal_type": goal_type}
        task = inv._task(goal)
        assert "THIS IS A CONTRIBUTION" not in task
        assert task.rstrip().endswith("then submit the dossier.")

    def test_a_contribution_with_no_task_falls_back(self):
        """A learner who skipped the question, and every session planned before
        the question existed, behave exactly as they did."""
        goal = {**CONTRIBUTION_GOAL, "contribution_context": ""}
        assert "THIS IS A CONTRIBUTION" not in inv._task(goal)


class TestChangeBoundaryIsGrounded:
    """Every boundary citation is checked against the repository, like the rest.

    A target file that does not resolve is the one error that would send a
    learner to write code in a place that is not there, so it must fail the
    dossier rather than reach the product as prose.
    """

    def _payload(self) -> dict:
        return {
            "change_boundary": {
                "target": [{"file": "a.py", "symbol": "Jar.get_all", "why_here": "x"}],
                "must_not_change": [{"file": "b.py", "symbol": "send", "why_not": "y"}],
                "existing_tests": [{"file": "t.py", "symbol": "TestJar", "what_it_guards": "z"}],
                "edge_cases": [
                    {"case": "two domains", "why_it_bites": "w",
                     "file": "a.py", "symbol": "Jar._find"},
                    {"case": "reasoned only", "why_it_bites": "w"},
                ],
            }
        }

    def test_boundary_anchors_are_cited(self):
        cited = inv.cited_anchors(self._payload())
        wheres = {w for w, _, _ in cited}
        assert "boundary:target" in wheres
        assert "boundary:must_not_change" in wheres
        assert "boundary:existing_tests" in wheres
        assert "boundary:edge_case" in wheres

    def test_an_unanchored_edge_case_is_not_cited(self):
        """It is permitted, and it is not a citation to verify — there is nothing
        to verify. It simply does not count toward the criterion either."""
        cited = inv.cited_anchors(self._payload())
        edge_anchors = [(f, s) for w, f, s in cited if w == "boundary:edge_case"]
        assert edge_anchors == [("a.py", "Jar._find")]

    def test_anchored_edge_cases_excludes_the_reasoned_one(self):
        anchored = inv.anchored_edge_cases(self._payload())
        assert [e["case"] for e in anchored] == ["two domains"]

    def test_a_malformed_boundary_degrades_instead_of_raising(self):
        """A model that serialises `target` as a string must produce feedback,
        not a TypeError halfway through validation."""
        assert inv.boundary_entries({"change_boundary": "<target>…"}, "target") == []
        assert inv.boundary_entries({"change_boundary": {"target": "x"}}, "target") == []
        assert inv.boundary({}) == {}


class TestExitCriteria:
    def test_contribution_demands_a_boundary(self):
        criteria = inv.CRITERIA_BY_GOAL_TYPE["contribute_code"]
        assert criteria.min_boundary_targets >= 1
        assert criteria.min_boundary_tests >= 1
        assert criteria.min_boundary_edge_cases >= 2

    def test_no_other_goal_type_demands_one(self):
        """Zero by default, so the section's existence changes nothing for the
        six goal types that are not making a change."""
        for goal_type, criteria in inv.CRITERIA_BY_GOAL_TYPE.items():
            if goal_type == "contribute_code":
                continue
            assert criteria.min_boundary_targets == 0
            assert criteria.min_boundary_tests == 0
            assert criteria.min_boundary_edge_cases == 0

    def test_base_floors_were_not_lowered_for_contribution(self):
        """A contribution journey is short because the REQUIRED SET is smaller,
        never because the investigation was allowed to establish less."""
        base = inv.BASE_CRITERIA
        contribution = inv.CRITERIA_BY_GOAL_TYPE["contribute_code"]
        assert contribution.min_components >= base.min_components
        assert contribution.min_flows >= base.min_flows
        assert contribution.min_flow_steps >= base.min_flow_steps
        assert contribution.min_prerequisites >= base.min_prerequisites
        assert contribution.min_contracts >= base.min_contracts

    def test_change_boundary_is_not_a_required_dossier_key(self):
        """Demanded by criteria, never by the schema — otherwise every other
        goal type's dossier fails on a contract that is not about it."""
        assert "change_boundary" in inv.INVESTIGATION_SPEC.input_schema["properties"]
        assert "change_boundary" not in inv.INVESTIGATION_SPEC.input_schema["required"]


# ── the change boundary as an EXIT REQUIREMENT ────────────────────────────────
#
# Run 3 of the rehearsal exposed the inconsistency these tests close: the
# boundary was OPTIONAL during investigation, while Locate, the plan, the scope
# check and the review all read it. An investigation that established no usable
# boundary produced a session whose contribution stage had nothing to stand on.
#
# The requirement goes through the criteria machinery — `requires_change_boundary`
# on `ExitCriteria` — rather than a post-hoc check somewhere else, so it reaches
# the investigator in the same feedback as every other shortfall and can be
# repaired inside the same budget.

from backend.repo.skeleton import build_skeleton

_FILES = {
    "src/app/__init__.py": "from .jar import Jar\n",
    "src/app/jar.py": (
        "class Jar:\n"
        "    def get(self, name):\n"
        "        return self._find(name)\n"
        "\n"
        "    def _find(self, name):\n"
        "        return None\n"
    ),
    "tests/test_jar.py": (
        "from src.app.jar import Jar\n"
        "\n\n"
        "def test_get():\n"
        "    assert Jar().get('x') is None\n"
    ),
}


@pytest.fixture
def repo(tmp_path):
    for relative, body in _FILES.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    build_skeleton.cache_clear()
    return str(tmp_path)


@pytest.fixture
def skeleton(repo):
    return build_skeleton(repo)


def _usable_boundary() -> dict:
    return {
        "target": [{"file": "src/app/jar.py", "symbol": "Jar",
                    "why_here": "the accessor belongs on the jar"}],
        "must_not_change": [{"file": "src/app/jar.py", "symbol": "Jar.get",
                             "why_not": "its contract is public"}],
        "existing_tests": [{"file": "tests/test_jar.py", "symbol": "test_get",
                            "what_it_guards": "the single-value path"}],
        "edge_cases": [
            {"case": "no match", "why_it_bites": "must not raise",
             "file": "src/app/jar.py", "symbol": "Jar._find"},
            {"case": "duplicate names", "why_it_bites": "the point of the change",
             "file": "src/app/jar.py", "symbol": "Jar.get"},
        ],
        "conventions": [{"convention": "nested ifs", "evidence_file": "src/app/jar.py"}],
    }


def _dossier(boundary: dict | None) -> dict:
    payload = {
        "understanding": "The jar looks a value up by name.",
        "components": [
            {"file": "src/app/jar.py", "symbol": "Jar",
             "role_in_goal": "owns lookup", "why_it_matters": "the change lands here"},
            {"file": "src/app/jar.py", "symbol": "Jar.get",
             "role_in_goal": "the strict accessor", "why_it_matters": "the contract to match"},
            {"file": "src/app/jar.py", "symbol": "Jar._find",
             "role_in_goal": "the filter", "why_it_matters": "the pattern to reuse"},
        ],
        "entry_points": [
            {"file": "src/app/jar.py", "symbol": "Jar.get",
             "how_it_enters": "callers ask by name"},
        ],
        "flows": [
            {"name": "lookup", "steps": [
                {"file": "src/app/jar.py", "symbol": "Jar.get", "what_happens": "asks"},
                {"file": "src/app/jar.py", "symbol": "Jar._find", "what_happens": "filters"},
                {"file": "tests/test_jar.py", "symbol": "test_get", "what_happens": "asserts"},
            ]},
        ],
        "relationships": [
            {"from_file": "src/app/jar.py", "from_symbol": "Jar.get",
             "to_file": "src/app/jar.py", "to_symbol": "Jar._find",
             "kind": "calls", "note": "always"},
            {"from_file": "tests/test_jar.py", "from_symbol": "test_get",
             "to_file": "src/app/jar.py", "to_symbol": "Jar.get",
             "kind": "calls", "note": "the guard"},
            {"from_file": "src/app/__init__.py", "from_symbol": "Jar",
             "to_file": "src/app/jar.py", "to_symbol": "Jar",
             "kind": "exports", "note": "public name"},
        ],
        "contracts": [
            {"file": "src/app/jar.py", "symbol": "Jar.get",
             "contract": "returns one value or None"},
            {"file": "src/app/jar.py", "symbol": "Jar._find",
             "contract": "internal filter; never raises"},
        ],
        "prerequisites": [
            {"concept": "iteration", "why_needed": "the filter walks the jar"},
        ],
        "evidence_refs": [{"path": "tests/test_jar.py", "clarifies": "the idiom"}],
        "context": [],
        "open_questions": [],
    }
    if boundary is not None:
        payload["change_boundary"] = boundary
    return payload


def _unmet(skeleton, goal_type: str, boundary: dict | None) -> list[str]:
    goal = {**CONTRIBUTION_GOAL, "goal_type": goal_type}
    return inv.validate_dossier(skeleton, goal, _dossier(boundary)).unmet_criteria


class TestBoundaryUsability:
    def test_a_usable_boundary_satisfies_the_requirement(self, skeleton):
        assert inv.boundary_usable(skeleton, {"change_boundary": _usable_boundary()})

    def test_a_missing_boundary_is_not_usable(self, skeleton):
        assert not inv.boundary_usable(skeleton, {})
        assert not inv.boundary_usable(skeleton, {"change_boundary": {}})

    def test_a_structurally_present_but_empty_boundary_is_not_usable(self, skeleton):
        """Run 3's actual shape: the key arrived, with nothing in it."""
        payload = {"change_boundary": {"target": [], "edge_cases": [],
                                       "existing_tests": [], "conventions": []}}
        assert not inv.boundary_usable(skeleton, payload)

    def test_a_target_without_a_symbol_is_not_usable(self, skeleton):
        """Locate opens the target AT ITS ANCHOR. A file alone cannot do that."""
        payload = {"change_boundary": {"target": [{"file": "src/app/jar.py"}]}}
        assert not inv.boundary_usable(skeleton, payload)

    def test_a_target_that_does_not_resolve_is_not_usable(self, skeleton):
        """The failure the anchoring rule exists to prevent, caught by code.

        A target naming a symbol that is not there sends the learner to write
        code in a place that does not exist — which is exactly what the model did
        in rehearsal when it anchored on the method being added.
        """
        payload = {"change_boundary": {"target": [
            {"file": "src/app/jar.py", "symbol": "Jar.get_all", "why_here": "x"},
        ]}}
        assert not inv.boundary_usable(skeleton, payload)

    def test_one_resolvable_target_is_enough(self, skeleton):
        """Deliberately small. Requiring every section to prove the boundary is
        not empty would be demanding a full schema, which is the opposite of a
        usability test — the other sections have their own counted criteria."""
        payload = {"change_boundary": {"target": [
            {"file": "src/app/jar.py", "symbol": "Jar.get_all", "why_here": "x"},
            {"file": "src/app/jar.py", "symbol": "Jar", "why_here": "y"},
        ]}}
        assert inv.boundary_usable(skeleton, payload)


class TestBoundaryIsRequiredForContributionOnly:
    def test_contribution_with_a_usable_boundary_is_accepted(self, skeleton):
        assert _unmet(skeleton, "contribute_code", _usable_boundary()) == []

    def test_contribution_without_a_boundary_is_refused(self, skeleton):
        assert any("not usable" in m
                   for m in _unmet(skeleton, "contribute_code", None))

    def test_contribution_with_an_empty_boundary_is_refused(self, skeleton):
        """Present but useless — run 3's shape. The message names the LEVER
        rather than only the count, because "0 entries" three times over does not
        say which section the rest of the product reads."""
        unmet = _unmet(skeleton, "contribute_code", {"target": []})
        message = next(m for m in unmet if "not usable" in m)
        assert "no `target` entry names both a file and a symbol" in message

    def test_an_unresolvable_target_is_refused_and_says_so_differently(self, skeleton):
        unmet = _unmet(skeleton, "contribute_code", {
            "target": [{"file": "src/app/jar.py", "symbol": "Jar.get_all",
                        "why_here": "the method being added"}],
        })
        message = next(m for m in unmet if "not usable" in m)
        assert "resolve against the repository" in message

    @pytest.mark.parametrize("goal_type", [
        "understand_architecture", "understand_system", "understand_component",
        "use_library", "improve_existing_system", "debug_issue",
    ])
    def test_no_other_goal_type_requires_a_boundary(self, skeleton, goal_type):
        """The whole reason the requirement is per-goal rather than in the
        schema's `required` list: six goal types have no change to bound."""
        assert not any("change_boundary" in m
                       for m in _unmet(skeleton, goal_type, None))


class TestFlowFilesIsExemptNotLowered:
    SINGLE_FILE_FLOW = [{"name": "lookup", "steps": [
        {"file": "src/app/jar.py", "symbol": "Jar.get", "what_happens": "asks"},
        {"file": "src/app/jar.py", "symbol": "Jar._find", "what_happens": "filters"},
        {"file": "src/app/jar.py", "symbol": "Jar", "what_happens": "holds"},
    ]}]

    def test_contribution_exempts_the_criterion_entirely(self):
        """`None`, not 1. A floor of 1 would say "one file is barely enough";
        `None` says the number is not evidence about this goal at all."""
        assert inv.CRITERIA_BY_GOAL_TYPE["contribute_code"].min_flow_files is None

    def test_every_other_goal_type_keeps_its_floor(self):
        for goal_type, criteria in inv.CRITERIA_BY_GOAL_TYPE.items():
            if goal_type == "contribute_code":
                continue
            assert criteria.min_flow_files is not None
            assert criteria.min_flow_files >= inv.BASE_CRITERIA.min_flow_files
        assert inv.BASE_CRITERIA.min_flow_files == 2

    def test_a_single_file_contribution_is_not_penalised(self, skeleton):
        """The rehearsal's actual blocker: a contribution correctly scoped to one
        production file was told its behaviour "spans at least 2 files"."""
        payload = _dossier(_usable_boundary())
        payload["flows"] = self.SINGLE_FILE_FLOW
        goal = {**CONTRIBUTION_GOAL, "goal_type": "contribute_code"}
        unmet = inv.validate_dossier(skeleton, goal, payload).unmet_criteria
        assert not any("file(s)" in m for m in unmet), unmet

    def test_a_single_file_flow_still_fails_for_other_goal_types(self, skeleton):
        """`understand_component`, not `understand_architecture`: the latter
        demands two flows, so a one-flow dossier fails on the count and never
        reaches the file check at all — which would make this pass for the wrong
        reason."""
        payload = _dossier(None)
        payload["flows"] = self.SINGLE_FILE_FLOW
        goal = {**CONTRIBUTION_GOAL, "goal_type": "understand_component"}
        unmet = inv.validate_dossier(skeleton, goal, payload).unmet_criteria
        assert any("file(s)" in m for m in unmet), unmet


# ── the three grounding fixes, measured against the runs that forced them ─────
#
# Three clean runs of Candidate A failed 2-in-3 for one mechanism: the model
# built a `flow` for the method it was being asked to help create, every step
# anchored on a symbol that does not exist, and the generic "verify with
# `symbols`, then correct or drop them" sent it looking for something unfindable
# until the turn budget was gone.


class TestFutureSymbolIsRecognised:
    """A citation of the symbol being CREATED is its own failure family.

    Still unresolved — it genuinely does not resolve, and grounding accuracy must
    not be flattered by pretending otherwise. What changes is the ADVICE.
    """

    GOAL = {
        "goal_type": "contribute_code",
        "contribution_context": (
            "Add a get_all(name, domain=None, path=None) method to Jar that "
            "returns every value stored under that name."
        ),
    }

    def test_a_symbol_the_task_names_that_exists_nowhere(self, skeleton):
        assert inv.is_future_symbol(skeleton, self.GOAL, "Jar.get_all")
        assert inv.is_future_symbol(skeleton, self.GOAL, "get_all")

    def test_a_symbol_the_task_never_mentions_is_not_one(self, skeleton):
        assert not inv.is_future_symbol(skeleton, self.GOAL, "Jar.something_else")

    def test_the_container_the_task_also_names_is_not_one(self, skeleton):
        """THE FALSE POSITIVE THE THIRD CONDITION EXISTS FOR.

        "add a get_all method to Jar" names `Jar` too, and a citation of
        `__init__.py:Jar` fails to resolve for a completely different reason —
        imported there, not defined there. That wants "you cited the wrong file",
        not advice about prose.
        """
        assert not inv.is_future_symbol(skeleton, self.GOAL, "Jar")

    def test_it_only_applies_to_contributions(self, skeleton):
        """Every other goal type has no change being made, so an unresolvable
        citation there is an ordinary mistake about the repository."""
        goal = {**self.GOAL, "goal_type": "understand_architecture"}
        assert not inv.is_future_symbol(skeleton, goal, "Jar.get_all")

    def test_a_contribution_with_no_task_recognises_nothing(self, skeleton):
        goal = {**self.GOAL, "contribution_context": ""}
        assert not inv.is_future_symbol(skeleton, goal, "Jar.get_all")

    def test_the_check_separates_it_from_ordinary_unresolved_anchors(self, skeleton):
        payload = _dossier(_usable_boundary())
        payload["flows"] = [{"name": "get_all execution", "steps": [
            {"file": "src/app/jar.py", "symbol": "Jar.get_all", "what_happens": "iterates"},
            {"file": "src/app/jar.py", "symbol": "Jar.nonexistent", "what_happens": "?"},
            {"file": "src/app/jar.py", "symbol": "Jar._find", "what_happens": "filters"},
        ]}]
        check = inv.validate_dossier(skeleton, self.GOAL, payload)
        assert check.future_symbols == ["src/app/jar.py:Jar.get_all"]
        # STILL UNRESOLVED, and still counted: the fix is the advice, not the
        # arithmetic. Grounding accuracy must not be flattered by a citation
        # that does not resolve, whatever the reason.
        assert any("Jar.get_all" in a for a in check.unresolved_anchors)
        assert any("Jar.nonexistent" in a for a in check.unresolved_anchors)
        assert check.grounding_accuracy < 1.0

    def test_the_feedback_names_where_the_intent_belongs(self, skeleton):
        """The whole point. The generic message says "verify it"; this one says
        it can never resolve and names the two fields that take the meaning."""
        payload = _dossier(_usable_boundary())
        payload["flows"] = [{"name": "f", "steps": [
            {"file": "src/app/jar.py", "symbol": "Jar.get_all", "what_happens": "x"},
            {"file": "src/app/jar.py", "symbol": "Jar._find", "what_happens": "y"},
            {"file": "src/app/jar.py", "symbol": "Jar", "what_happens": "z"},
        ]}]
        message = inv.validate_dossier(skeleton, self.GOAL, payload).gap_message()
        assert "going to CREATE" in message
        assert "no anchor on it can ever resolve" in message
        assert "`understanding`" in message
        assert "`change_boundary.target`" in message

    def test_the_generic_advice_is_suppressed_for_it(self, skeleton):
        """Two messages about one citation, one of them wrong, is worse than one.

        A payload whose ONLY unresolved citation is the future symbol — the
        shared fixture carries an ordinary one as well, and with both present
        both messages are correct.
        """
        payload = {
            "understanding": "u",
            "components": [{"file": "src/app/jar.py", "symbol": "Jar",
                            "role_in_goal": "r", "why_it_matters": "w"}],
            "entry_points": [], "flows": [{"name": "f", "steps": [
                {"file": "src/app/jar.py", "symbol": "Jar.get_all",
                 "what_happens": "x"},
            ]}],
            "relationships": [], "contracts": [], "prerequisites": [],
            "evidence_refs": [], "context": [], "open_questions": [],
        }
        check = inv.validate_dossier(skeleton, self.GOAL, payload)
        assert check.future_symbols == ["src/app/jar.py:Jar.get_all"]
        message = check.gap_message()
        assert "going to CREATE" in message
        assert "correct or drop them" not in message

    def test_an_ordinary_unresolved_anchor_still_gets_the_generic_advice(self, skeleton):
        payload = _dossier(_usable_boundary())
        payload["flows"] = [{"name": "f", "steps": [
            {"file": "src/app/jar.py", "symbol": "Jar.typo_here", "what_happens": "x"},
            {"file": "src/app/jar.py", "symbol": "Jar._find", "what_happens": "y"},
            {"file": "src/app/jar.py", "symbol": "Jar", "what_happens": "z"},
        ]}]
        message = inv.validate_dossier(skeleton, self.GOAL, payload).gap_message()
        assert "correct or drop them" in message
        assert "going to CREATE" not in message


class TestTheBriefGivesTheIntentAPlace:
    """A prohibition with nowhere to redirect into is a prohibition being fought.

    The first version said only "never cite the symbol you are going to add". One
    run in three obeyed it, because `flows` was still the only field that could
    express the change's behaviour.
    """

    def test_it_names_the_fields_that_take_the_meaning(self):
        task = inv._task(CONTRIBUTION_GOAL)
        assert "`understanding`" in task
        assert "`change_boundary.target`" in task
        assert "`change_boundary.edge_cases`" in task

    def test_it_names_the_fields_the_future_symbol_may_not_enter(self):
        # Fragments, not sentences: the brief is hard-wrapped, so a phrase that
        # spans a line break would fail on a reflow rather than on a meaning.
        task = inv._task(CONTRIBUTION_GOAL)
        assert "CODE THAT RUNS TODAY" in task
        assert "flow for the method being added" in task

    def test_it_says_to_anchor_on_the_container(self):
        """The container exists, so that anchor resolves — which is what makes
        the redirection actionable rather than merely a refusal."""
        assert "CLASS OR MODULE IT IS ADDED" in inv._task(CONTRIBUTION_GOAL)

    def test_it_still_demands_the_ordinary_sections(self):
        """THE OVER-CORRECTION THIS SENTENCE EXISTS TO PREVENT.

        Told firmly enough what must NOT go in `components` / `flows` /
        `relationships` / `contracts`, the model submitted a dossier containing
        `change_boundary` AND NOTHING ELSE — every required field absent, seven
        criteria unmet at once. Saying where the change goes is only half the
        instruction; the other half is that the existing code around it is still
        most of the dossier.
        """
        task = inv._task(CONTRIBUTION_GOAL)
        assert "STILL REQUIRED" in task
        assert "does not replace them" in task
        assert "EXISTING CODE THE CHANGE JOINS" in task


class TestSurfaceCheckIgnoresQualifiedNames:
    """A method is not a twin of a module-level function of the same leaf name.

    Measured: `RequestsCookieJar.get` was flagged against `requests.get` in
    `api.py` on every contribution run against `psf/requests`, costing turns each
    time. `A.b` and `b` are different names.
    """

    def test_a_method_is_not_compared_against_a_module_level_function(self, tmp_path):
        files = {
            "src/pkg/__init__.py": "from .api import fetch\n",
            "src/pkg/api.py": "def fetch(url):\n    return url\n",
            "src/pkg/jar.py": (
                "class Jar:\n"
                "    def fetch(self):\n"
                "        return None\n"
            ),
        }
        for relative, body in files.items():
            path = tmp_path / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        build_skeleton.cache_clear()
        sk = build_skeleton(str(tmp_path))
        payload = {"components": [
            {"file": "src/pkg/jar.py", "symbol": "Jar.fetch",
             "role_in_goal": "the jar's own fetch", "why_it_matters": "x"},
        ]}
        assert inv.public_surface_gaps(sk, payload) == []

    def test_an_unqualified_twin_is_still_caught(self, tmp_path):
        """The case the check was written for survives: two module-level
        definitions of one bare name, one exported and one not."""
        files = {
            "src/pkg/__init__.py": "from .public import Widget\n",
            "src/pkg/public.py": "class Widget:\n    pass\n",
            "src/pkg/internal.py": "class Widget:\n    pass\n",
        }
        for relative, body in files.items():
            path = tmp_path / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        build_skeleton.cache_clear()
        sk = build_skeleton(str(tmp_path))
        payload = {"components": [
            {"file": "src/pkg/internal.py", "symbol": "Widget",
             "role_in_goal": "the internal one", "why_it_matters": "x"},
        ]}
        gaps = inv.public_surface_gaps(sk, payload)
        assert len(gaps) == 1
        assert "src/pkg/internal.py:Widget" in gaps[0]
