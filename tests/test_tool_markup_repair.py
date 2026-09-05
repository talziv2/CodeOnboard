"""The tool-input transport artifact, and the feedback it used to destroy.

Run with: uv run pytest tests/test_tool_markup_repair.py -v

## The defect

The model sometimes emits tool-call markup INSIDE a JSON tool input: a field that
should be an array arrives as a string beginning `<parameter name="…">`. Measured
across seven instrumented runs spanning three goal types, this was the FIRST
submission's fate in six of them — and the single run that escaped it is the one
whose dossier was accepted. On `understand_architecture` it fired sixteen times
consecutively.

## Why it cost so much more than a formatting slip

A report that cannot be read yields NO information about the contract. The
validator could only answer "re-emit", so a submission — roughly a third of a
run's feedback budget — was spent learning nothing about what the investigation
still lacked. The stricter the contract, the worse the loss; `contribute_code`,
which asks for a change boundary on top of the base floors, could not absorb it.

## The two halves of the fix, and which test covers which

  RECOVER   `explore.repair_tool_input` undoes the shape that is provably
            recoverable — a `<parameter>` wrapper around otherwise-valid JSON —
            at the one point every tool input passes through. Self-verifying: if
            the unwrapped text does not parse, nothing changes.
            -> TestUnwrapping, TestTheRepairIsAppliedAtTheBoundary

  DO NOT LOSE THE REST   For the shapes that cannot be recovered, the diagnostics
            that are still valid survive. Only the complaints that are ARTIFACTS
            of the corrupted field are suppressed.
            -> TestDiagnosticsSurviveACorruptedField
"""
import json

import pytest

from backend.repo import explore, investigation as inv
from backend.repo.skeleton import build_skeleton


# The three shapes observed in production, verbatim from the recorded rejections.
WRAPPED_JSON = (
    '<parameter name="components">\n'
    '[\n  {"file": "src/app/jar.py", "symbol": "Jar", '
    '"role_in_goal": "owns lookup", "why_it_matters": "the change lands here"}\n]\n'
    '</parameter>'
)
WHOLE_TOOL_CALL = (
    '<invoke name="propose_anchor">\n'
    '<parameter name="file">src/requests/cookies.py</parameter>'
)
XML_ITEMS = (
    '<item>\n<parameter name="file">src/requests/cookies.py</parameter>\n'
    '<parameter name="symbol">RequestsCookieJar</parameter>\n</item>'
)


class TestUnwrapping:
    def test_a_parameter_wrapper_around_json_is_recovered(self):
        recovered = explore.unwrap_tool_markup(WRAPPED_JSON)
        assert isinstance(recovered, list)
        assert recovered[0]["symbol"] == "Jar"

    def test_an_unclosed_wrapper_is_recovered_too(self):
        """Observed unclosed as often as closed — `raw_decode` stops at the end
        of the first complete value, which handles both."""
        assert explore.unwrap_tool_markup('<parameter name="x">[1, 2, 3]') == [1, 2, 3]

    def test_a_whole_tool_call_is_left_alone(self):
        """There is no components data in a `propose_anchor` call. Recovering
        something from it would be inventing evidence."""
        assert explore.unwrap_tool_markup(WHOLE_TOOL_CALL) == WHOLE_TOOL_CALL

    def test_xml_serialised_items_are_left_alone(self):
        """Hand-rolling an XML reader for an undefined format is how a mis-parse
        becomes 'evidence'. It stays corrupt, and stays reported as corrupt."""
        assert explore.unwrap_tool_markup(XML_ITEMS) == XML_ITEMS

    def test_an_ordinary_string_is_untouched(self):
        assert explore.unwrap_tool_markup("src/app/jar.py") == "src/app/jar.py"

    def test_a_non_string_is_untouched(self):
        value = [{"file": "a.py"}]
        assert explore.unwrap_tool_markup(value) is value

    def test_a_wrapped_scalar_is_not_recovered(self):
        """Only a container is worth recovering; unwrapping a scalar would
        change a legitimate field's meaning for no gain."""
        wrapped = '<parameter name="x">42</parameter>'
        assert explore.unwrap_tool_markup(wrapped) == wrapped

    def test_the_repair_reports_which_fields_it_touched(self):
        arguments, recovered = explore.repair_tool_input({
            "understanding": "a paragraph",
            "components": WRAPPED_JSON,
            "flows": WHOLE_TOOL_CALL,
        })
        assert recovered == ["components"]
        assert isinstance(arguments["components"], list)
        assert arguments["flows"] == WHOLE_TOOL_CALL
        assert arguments["understanding"] == "a paragraph"

    def test_a_clean_input_is_reported_as_untouched(self):
        clean = {"file": "a.py", "symbol": "Jar"}
        arguments, recovered = explore.repair_tool_input(clean)
        assert recovered == []
        assert arguments == clean


class TestTheRepairIsAppliedAtTheBoundary:
    """Structurally: at the ONE place every tool input passes through.

    A per-caller repair would leave the next `ReportSpec` — and every ordinary
    tool — to rediscover the artifact on its own.
    """

    def test_the_dispatch_loop_repairs_before_validating(self):
        import ast
        import pathlib

        source = pathlib.Path(explore.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "repair_tool_input" in called, (
            "the transport repair must be applied inside the exploration loop, "
            "not left to each caller"
        )

    def test_a_wrapped_report_now_validates_as_the_model_meant_it(self, skeleton):
        """End to end through the validator: the same payload that was
        unreadable is read normally once the wrapper is gone."""
        broken = {"components": WRAPPED_JSON}
        assert inv.structural_faults(broken)          # unreadable as sent

        repaired, recovered = explore.repair_tool_input(broken)
        assert recovered == ["components"]
        assert inv.structural_faults(repaired) == []  # readable once unwrapped
        assert len(inv._entries(repaired, "components")[0]) == 1

    def test_recovery_does_not_bypass_grounding(self, skeleton):
        """The recovered claims go through the same anchor resolution as any
        other. This fixes an encoding, never a fact."""
        wrapped = (
            '<parameter name="components">\n'
            '[{"file": "src/app/jar.py", "symbol": "NoSuchSymbol", '
            '"role_in_goal": "r", "why_it_matters": "w"}]\n</parameter>'
        )
        repaired, _ = explore.repair_tool_input({"components": wrapped})
        cited = inv.cited_anchors(repaired)
        assert cited == [("component", "src/app/jar.py", "NoSuchSymbol")]
        check = inv.validate_dossier(skeleton, {"goal_type": "understand_system"}, repaired)
        assert any("NoSuchSymbol" in a for a in check.unresolved_anchors)


class TestDiagnosticsSurviveACorruptedField:
    """THE HALF THAT MATTERED MOST. A report mangled in one field must cost that
    field — not the whole submission's worth of feedback."""

    def _payload(self, corrupt_components: bool) -> dict:
        payload = {
            "understanding": "The jar looks a value up by name.",
            "components": XML_ITEMS if corrupt_components else [
                {"file": "src/app/jar.py", "symbol": "Jar",
                 "role_in_goal": "r", "why_it_matters": "w"},
                {"file": "src/app/jar.py", "symbol": "Jar.get",
                 "role_in_goal": "r", "why_it_matters": "w"},
                {"file": "src/app/jar.py", "symbol": "Jar._find",
                 "role_in_goal": "r", "why_it_matters": "w"},
            ],
            "entry_points": [], "flows": [], "relationships": [],
            "contracts": [], "prerequisites": [],
            "evidence_refs": [], "context": [], "open_questions": [],
        }
        return payload

    def test_the_corrupted_field_is_named(self, skeleton):
        assert inv.corrupted_fields(self._payload(True)) == {"components"}

    def test_a_clean_payload_names_nothing(self, skeleton):
        assert inv.corrupted_fields(self._payload(False)) == set()

    def test_the_artifact_complaint_is_suppressed(self, skeleton):
        """"0 components established" is a restatement of the transmission
        fault, not a finding — reporting it sends the investigator exploring for
        evidence it already has."""
        check = inv.validate_dossier(
            skeleton, {"goal_type": "understand_system"}, self._payload(True)
        )
        assert not any("component(s) established" in m for m in check.unmet_criteria)

    def test_every_other_shortfall_is_still_reported(self, skeleton):
        """The regression this whole file exists for: these used to be thrown
        away wholesale."""
        check = inv.validate_dossier(
            skeleton, {"goal_type": "understand_system"}, self._payload(True)
        )
        assert any("flow" in m for m in check.unmet_criteria)
        assert any("relationship" in m for m in check.unmet_criteria)
        assert any("prerequisite" in m for m in check.unmet_criteria)

    def test_the_message_leads_with_the_repair_and_keeps_the_rest(self, skeleton):
        check = inv.validate_dossier(
            skeleton, {"goal_type": "understand_system"}, self._payload(True)
        )
        message = check.gap_message()
        # The repair still comes first and still says not to go exploring.
        assert message.startswith("Your submission did not arrive in the shape")
        assert "Do NOT gather more evidence" in message
        # …and the contract information is no longer lost.
        assert "the contract still needs" in message
        assert "SAME resubmission" in message

    def test_a_contribution_keeps_its_boundary_feedback_through_a_mangled_field(
        self, skeleton
    ):
        """The case that motivated the fix. A contribution whose `components`
        arrived corrupt still learns that its change boundary is missing —
        previously it learned only "re-emit", and ran out of turns."""
        goal = {
            "goal_type": "contribute_code",
            "contribution_context": "Add a get_all method to Jar",
        }
        message = inv.validate_dossier(
            skeleton, goal, self._payload(True)
        ).gap_message()
        assert "change_boundary" in message

    def test_a_clean_payload_is_unaffected_by_any_of_this(self, skeleton):
        """No structural fault, no change in behaviour: the ordinary path still
        reports its criteria exactly as before."""
        check = inv.validate_dossier(
            skeleton, {"goal_type": "understand_system"}, self._payload(False)
        )
        assert check.structural == []
        message = check.gap_message()
        assert "did not arrive in the shape" not in message
        assert "the contract still needs" not in message


# The fixture repository. Small and real: `validate_dossier` resolves anchors
# against a Skeleton, so these tests need one even though the subject is
# transport rather than grounding.
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
}


@pytest.fixture
def skeleton(tmp_path):
    for relative, body in _FILES.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    build_skeleton.cache_clear()
    return build_skeleton(str(tmp_path))


class TestBoundarySectionsStrandedAtTheTopLevel:
    """The same flattening fault, one level up — and it went undetected.

    `structural_faults` predates `change_boundary`, so it knew about stranded
    ITEM keys and nothing about stranded SECTION names. Observed in a real run: a
    dossier arrived with `existing_tests`, `edge_cases`, `must_not_change` and
    `conventions` as top-level keys and `change_boundary` empty. Four tests and
    six edge cases had been found — and the investigator was told "0 entries" for
    every one of them, which reads as "you did not find any" and sends it back to
    look for what it had already written down.
    """

    FLATTENED = {
        "understanding": "The jar looks a value up by name.",
        "components": [{"file": "src/app/jar.py", "symbol": "Jar",
                        "role_in_goal": "r", "why_it_matters": "w"}],
        "entry_points": [], "flows": [], "relationships": [],
        "contracts": [], "prerequisites": [],
        "evidence_refs": [], "context": [], "open_questions": [],
        # Where they should not be.
        "target": [{"file": "src/app/jar.py", "symbol": "Jar", "why_here": "x"}],
        "existing_tests": [{"file": "tests/test_jar.py", "symbol": "test_get",
                            "what_it_guards": "y"}],
        "edge_cases": [{"case": "no match", "why_it_bites": "z"}],
    }

    def test_the_flattening_is_detected(self):
        faults = inv.structural_faults(self.FLATTENED)
        assert any("change-boundary sections arrived at the top level" in f
                   for f in faults)

    def test_the_message_names_them_and_says_where_they_go(self):
        fault = next(f for f in inv.structural_faults(self.FLATTENED)
                     if "change-boundary sections" in f)
        assert "`existing_tests`" in fault and "`edge_cases`" in fault
        assert "`change_boundary.target`" in fault
        assert "the findings themselves are fine" in fault

    def test_a_correctly_nested_boundary_is_not_flagged(self):
        nested = {
            "understanding": "u",
            "change_boundary": {
                "target": [{"file": "src/app/jar.py", "symbol": "Jar"}],
                "existing_tests": [{"file": "tests/test_jar.py", "symbol": "t"}],
            },
        }
        assert inv.structural_faults(nested) == []

    def test_the_investigator_is_told_to_re_emit_rather_than_explore(self, skeleton):
        """The whole point of detecting it: the repair is one resubmission, not
        another search for evidence already in hand."""
        message = inv.validate_dossier(
            skeleton, {"goal_type": "contribute_code",
                       "contribution_context": "Add get_all to Jar"},
            self.FLATTENED,
        ).gap_message()
        assert "Do NOT gather more evidence" in message
        assert "change-boundary sections arrived at the top level" in message


class TestScopingNeverLetsAnUnreadableDossierThrough:
    """The risk the diagnostic-scoping change introduced, pinned.

    `validate_dossier` now SKIPS the criteria that would be artifacts of a
    corrupted field — "0 components established" when `components` never
    arrived readable. The obvious way for that to go wrong is for a dossier to
    pass its contract on the strength of checks that were skipped, be accepted,
    and then reach the planner with nothing it can anchor on:

        curriculum: dossier contains no resolvable evidence

    It cannot, because `DossierCheck.ok` requires `not self.structural`. A
    payload we could not read is never accepted, whatever the criteria say. This
    test exists so that stays true if `ok` is ever rewritten.
    """

    def _partially_corrupt(self) -> dict:
        return {
            "understanding": "u",
            "components": XML_ITEMS,           # unreadable
            "entry_points": [{"file": "src/app/jar.py", "symbol": "Jar.get",
                              "how_it_enters": "callers ask by name"}],
            "flows": [{"name": "lookup", "steps": [
                {"file": "src/app/jar.py", "symbol": "Jar", "what_happens": "a"},
                {"file": "src/app/jar.py", "symbol": "Jar.get", "what_happens": "b"},
                {"file": "src/app/jar.py", "symbol": "Jar._find", "what_happens": "c"},
            ]}],
            "relationships": [], "contracts": [],
            "prerequisites": [{"concept": "iteration", "why_needed": "w"}],
            "evidence_refs": [], "context": [], "open_questions": [],
        }

    def test_the_artifact_criterion_is_skipped(self, skeleton):
        check = inv.validate_dossier(
            skeleton, {"goal_type": "understand_system"}, self._partially_corrupt()
        )
        assert not any("component(s) established" in m for m in check.unmet_criteria)

    def test_but_the_dossier_is_still_refused(self, skeleton):
        """The load-bearing half. Skipping a complaint must not become accepting
        the payload it was about."""
        check = inv.validate_dossier(
            skeleton, {"goal_type": "understand_system"}, self._partially_corrupt()
        )
        assert check.structural, "the corrupted field must still be a structural fault"
        assert check.ok is False

    def test_a_readable_field_is_judged_rather_than_skipped(self, skeleton):
        """The control, and the other half of the rule.

        Skipping is scoped to fields that did not ARRIVE. A readable
        `components` is judged normally — here it is one short of the floor and
        says so, where the corrupted version said nothing about components at
        all.
        """
        payload = self._partially_corrupt()
        payload["components"] = [
            {"file": "src/app/jar.py", "symbol": "Jar",
             "role_in_goal": "r", "why_it_matters": "w"},
        ]
        check = inv.validate_dossier(
            skeleton, {"goal_type": "understand_system"}, payload
        )
        assert check.structural == []
        assert any("component(s) established" in m for m in check.unmet_criteria)
