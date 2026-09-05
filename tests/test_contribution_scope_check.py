# The deterministic checks on a learner-authored patch.
#
# No model, no execution, no repository write — so every one of these runs
# without an API key, which is the point of putting the checks in Python at all.
#
# THE CLAIM `passed` SUPPORTS, AND THE TWO IT DOES NOT.
#
#   SCOPE        no files outside the planned boundary   ← this is `passed`
#   CORRECTNESS  does it do what was asked               ← a model's opinion
#   TESTS        does the repository still pass          ← NOBODY. Not run.
#
# `test_a_syntax_error_is_not_a_scope_failure` is the one that keeps those apart
# mechanically: folding any other finding into `passed` would make one word mean
# two things, which is how "scope check passed" starts being read as "the change
# is fine".

import pytest

from backend.learning import contribution as c


BOUNDARY = {
    "target": [
        {"file": "src/requests/cookies.py", "symbol": "RequestsCookieJar.get_all",
         "why_here": "the jar owns name lookup"},
    ],
    "must_not_change": [
        {"file": "src/requests/sessions.py", "symbol": "Session.send",
         "why_not": "unrelated to cookie lookup"},
    ],
    "existing_tests": [
        {"file": "tests/test_requests.py", "symbol": "TestRequests",
         "what_it_guards": "cookie conflict behaviour"},
    ],
}

GOOD_SOURCE = (
    "class RequestsCookieJar:\n"
    "    def get_all(self, name, domain=None, path=None):\n"
    "        return []\n"
)
GOOD_TEST = (
    "class TestRequests:\n"
    "    def test_get_all_across_domains(self):\n"
    "        assert True\n"
)


def _patch(*files):
    return [c.PatchFile(path=p, contents=s) for p, s in files]


class TestScope:
    def test_a_patch_inside_the_boundary_passes(self):
        check = c.check_scope(
            _patch(("src/requests/cookies.py", GOOD_SOURCE),
                   ("tests/test_requests.py", GOOD_TEST)),
            BOUNDARY,
        )
        assert check.passed
        assert check.outside_boundary == []
        assert sorted(check.in_boundary) == [
            "src/requests/cookies.py", "tests/test_requests.py",
        ]

    def test_a_file_outside_the_boundary_fails_and_is_named(self):
        """Named, not merely counted. A check that reports only a boolean cannot
        tell the learner what to fix."""
        check = c.check_scope(
            _patch(("src/requests/cookies.py", GOOD_SOURCE),
                   ("src/requests/adapters.py", "x = 1\n")),
            BOUNDARY,
        )
        assert not check.passed
        assert check.outside_boundary == ["src/requests/adapters.py"]

    def test_touching_a_forbidden_file_is_its_own_finding(self):
        """Its own list because the response differs: not "you went wide" but
        "you went somewhere the change was explicitly not supposed to go".

        The entry names NO symbol, which is what makes it a whole-file exclusion
        a path check can evaluate — see `whole_files_forbidden`.
        """
        boundary = {
            **BOUNDARY,
            "must_not_change": [{"file": "src/requests/sessions.py",
                                 "why_not": "stay out of the session layer"}],
        }
        check = c.check_scope(
            _patch(("src/requests/sessions.py", "x = 1\n")), boundary,
        )
        assert not check.passed
        assert check.forbidden == ["src/requests/sessions.py"]
        assert check.outside_boundary == []

    def test_a_forbidden_symbol_in_the_target_file_is_not_a_violation(self):
        """THE BUG A REAL RUN FOUND, and the reason this test exists.

        A real boundary named `cookies.py:RequestsCookieJar` as the target and
        `cookies.py:RequestsCookieJar.get` (plus four siblings) as
        `must_not_change` — the same file, different symbols. Comparing paths
        alone marked BOTH files of a correct patch forbidden, because for a small
        contribution the code being added and the code that must not move almost
        always live together.

        The path-level question is "did they touch a file they were told to stay
        out of entirely". The symbol-level question is left unclaimed rather than
        guessed at.
        """
        boundary = {
            "target": [{"file": "src/requests/cookies.py",
                        "symbol": "RequestsCookieJar", "why_here": "x"}],
            "must_not_change": [
                {"file": "src/requests/cookies.py",
                 "symbol": "RequestsCookieJar.get", "why_not": "contract"},
                {"file": "src/requests/sessions.py",
                 "symbol": "Session.send", "why_not": "unrelated"},
            ],
            "existing_tests": [{"file": "tests/test_requests.py",
                                "symbol": "TestRequests", "what_it_guards": "y"}],
        }
        check = c.check_scope(
            _patch(("src/requests/cookies.py", GOOD_SOURCE),
                   ("tests/test_requests.py", GOOD_TEST)),
            boundary,
        )
        assert check.forbidden == []
        assert check.passed
        assert sorted(check.in_boundary) == [
            "src/requests/cookies.py", "tests/test_requests.py",
        ]

    def test_a_test_file_the_learner_must_extend_is_not_forbidden(self):
        """The SECOND real case, one level out from the first.

        The boundary put `tests/test_requests.py:TestRequests.test_cookie_
        duplicate_names_different_domains` in `must_not_change` — protecting one
        test function in the very file the learner has to add tests to. A path
        comparison cannot tell "do not break this test" from "stay out of this
        file", so it must not claim to.
        """
        boundary = {
            "target": [{"file": "src/requests/cookies.py", "symbol": "Jar"}],
            "must_not_change": [
                {"file": "tests/test_requests.py",
                 "symbol": "TestRequests.test_existing", "why_not": "guards get()"},
            ],
        }
        check = c.check_scope(_patch(("tests/test_requests.py", GOOD_TEST)), boundary)
        assert check.forbidden == []
        # And not "outside" either: a file the boundary NAMES is a file the
        # investigation considered part of this change's neighbourhood.
        assert check.outside_boundary == []
        assert check.passed

    def test_a_symbol_level_exclusion_never_fails_a_path_check(self):
        """Reporting one would be claiming to have checked something we did not —
        the overclaiming this whole stage's wording is built to avoid. What is
        lost is left to the Review step, which is labelled an opinion."""
        boundary = {
            "target": [{"file": "a.py", "symbol": "f"}],
            "must_not_change": [{"file": "b.py", "symbol": "g", "why_not": "z"}],
        }
        check = c.check_scope(_patch(("b.py", "x = 1\n")), boundary)
        assert check.forbidden == []
        # Nor "outside": the boundary NAMES `b.py`, so it is inside the
        # neighbourhood the investigation drew. The scope check therefore passes
        # and says nothing about whether `g` was edited — which is the honest
        # answer, because it did not look.
        assert check.outside_boundary == []
        assert check.passed

    def test_a_file_the_boundary_never_mentions_is_outside(self):
        """The claim that survives, and the only one `passed` ever supported."""
        boundary = {"target": [{"file": "a.py", "symbol": "f"}]}
        check = c.check_scope(_patch(("elsewhere.py", "x = 1\n")), boundary)
        assert check.outside_boundary == ["elsewhere.py"]
        assert not check.passed

    def test_windows_separators_and_leading_dots_compare_equal(self):
        check = c.check_scope(
            _patch(("./src\\requests\\cookies.py", GOOD_SOURCE)), BOUNDARY,
        )
        assert check.passed

    def test_an_undrawn_boundary_accuses_nobody(self):
        """A boundary with no targets cannot decide scope, so nothing is reported
        outside it — an empty plan must not accuse the learner of leaving one."""
        check = c.check_scope(_patch(("anything.py", "x = 1\n")), {})
        assert check.passed
        assert check.outside_boundary == []


class TestItOnlyClaimsWhatItChecked:
    """**`ScopeCheck` may only claim enforcement of what it can evaluate.**

    It sees `{path, contents}`. It never reads the original file and never
    compares at symbol granularity, so a constraint like `cookies.py:get` is
    something it was ASKED about and cannot answer — and silence would read as a
    pass. `unchecked_symbols` is that list, and the Validate surface renders it
    as "Not performed" rather than as a result.
    """

    BOUNDARY = {
        "target": [{"file": "src/requests/cookies.py", "symbol": "RequestsCookieJar"}],
        "must_not_change": [
            {"file": "src/requests/cookies.py",
             "symbol": "RequestsCookieJar.get", "why_not": "public contract"},
            {"file": "src/requests/cookies.py",
             "symbol": "RequestsCookieJar._find", "why_not": "internal"},
            {"file": "src/requests/adapters.py", "why_not": "stay out entirely"},
        ],
    }

    def test_symbol_constraints_in_a_touched_file_are_reported_as_unchecked(self):
        check = c.check_scope(
            _patch(("src/requests/cookies.py", GOOD_SOURCE)), self.BOUNDARY,
        )
        assert check.unchecked_symbols == [
            "src/requests/cookies.py:RequestsCookieJar.get",
            "src/requests/cookies.py:RequestsCookieJar._find",
        ]

    def test_being_unchecked_is_not_a_failure(self):
        """They answer different questions. Failing a learner for something
        nobody looked at is the mirror image of passing them for it."""
        check = c.check_scope(
            _patch(("src/requests/cookies.py", GOOD_SOURCE)), self.BOUNDARY,
        )
        assert check.passed
        assert check.forbidden == []

    def test_a_symbol_in_an_untouched_file_is_not_reported(self):
        """A constraint on a file the learner never opened is not something they
        need telling about."""
        boundary = {
            "target": [{"file": "a.py", "symbol": "f"}],
            "must_not_change": [{"file": "b.py", "symbol": "g", "why_not": "x"}],
        }
        check = c.check_scope(_patch(("a.py", "def f():\n    pass\n")), boundary)
        assert check.unchecked_symbols == []

    def test_a_whole_file_exclusion_is_enforced_not_merely_reported(self):
        """The one thing `must_not_change` can say that a path check CAN act on,
        and it still acts on it."""
        check = c.check_scope(
            _patch(("src/requests/adapters.py", "x = 1\n")), self.BOUNDARY,
        )
        assert check.forbidden == ["src/requests/adapters.py"]
        assert not check.passed

    def test_the_two_kinds_survive_a_round_trip(self):
        check = c.check_scope(
            _patch(("src/requests/cookies.py", GOOD_SOURCE)), self.BOUNDARY,
        )
        restored = c.ScopeCheck.from_dict(check.to_dict())
        assert restored.unchecked_symbols == check.unchecked_symbols


class TestSyntax:
    def test_a_syntax_error_is_reported(self):
        check = c.check_scope(
            _patch(("src/requests/cookies.py", "def broken(:\n")), BOUNDARY,
        )
        assert check.unparseable == ["src/requests/cookies.py"]

    def test_a_syntax_error_is_not_a_scope_failure(self):
        """The two are different claims and `passed` is only ever the first."""
        check = c.check_scope(
            _patch(("src/requests/cookies.py", "def broken(:\n")), BOUNDARY,
        )
        assert check.passed

    def test_a_non_python_file_is_not_parsed(self):
        check = c.check_scope(
            _patch(("src/requests/cookies.py", GOOD_SOURCE),
                   ("README.md", "# not python (:\n")),
            BOUNDARY,
        )
        assert check.unparseable == []

    def test_parsing_does_not_execute_the_patch(self, tmp_path):
        """`ast.parse` builds a tree; it does not import, execute or evaluate.

        That distinction is the whole reason these checks can exist. If it ever
        stopped being true, this patch would write a file and the assertion would
        catch it.
        """
        marker = tmp_path / "executed.txt"
        source = f"open({str(marker)!r}, 'w').write('x')\n"
        c.check_scope(_patch(("src/requests/cookies.py", source)), BOUNDARY)
        assert not marker.exists()


class TestSymbol:
    def test_the_boundarys_target_symbol_is_bare(self):
        """`ast` sees `get_all`, the boundary carries `RequestsCookieJar.get_all`
        — comparing the two forms directly reports every method as missing."""
        assert c.target_symbol(BOUNDARY) == "get_all"

    def test_a_defined_symbol_is_found(self):
        check = c.check_scope(_patch(("src/requests/cookies.py", GOOD_SOURCE)), BOUNDARY)
        assert check.symbol_found

    def test_a_missing_symbol_is_reported(self):
        check = c.check_scope(
            _patch(("src/requests/cookies.py", "def something_else():\n    pass\n")),
            BOUNDARY,
        )
        assert not check.symbol_found

    def test_no_target_symbol_means_the_row_is_not_rendered(self):
        """Empty rather than false, so the Validate surface can omit the row
        instead of showing an empty one for a task that named no symbol."""
        check = c.check_scope(_patch(("a.py", "x = 1\n")), {"target": [{"file": "a.py"}]})
        assert check.symbol_expected == ""
        assert not check.symbol_found


class TestTests:
    def test_a_boundary_test_file_is_recognised(self):
        check = c.check_scope(_patch(("tests/test_requests.py", GOOD_TEST)), BOUNDARY)
        assert check.test_files == ["tests/test_requests.py"]

    def test_a_new_test_file_the_investigation_never_named_still_counts(self):
        """Adding a test file the boundary did not list is a good thing to do and
        must not read as "no test written"."""
        check = c.check_scope(
            _patch(("tests/test_cookie_get_all.py", GOOD_TEST)), BOUNDARY,
        )
        assert check.test_files == ["tests/test_cookie_get_all.py"]

    def test_a_test_pytest_will_not_collect_is_flagged(self):
        check = c.check_scope(
            _patch(("tests/test_requests.py",
                    "class TestRequests:\n    def checks_get_all(self):\n        pass\n")),
            BOUNDARY,
        )
        assert check.misnamed_tests == ["checks_get_all"]

    def test_module_level_and_method_tests_are_both_seen(self):
        source = (
            "def test_top_level():\n    pass\n"
            "class TestRequests:\n    def test_method(self):\n        pass\n"
        )
        check = c.check_scope(_patch(("tests/test_requests.py", source)), BOUNDARY)
        assert check.misnamed_tests == []


class TestBounds:
    def test_too_many_files_is_refused(self):
        patch = _patch(*[(f"f{i}.py", "x = 1\n") for i in range(c.MAX_PATCH_FILES + 1)])
        assert c.patch_faults(patch)

    def test_an_oversized_file_is_refused(self):
        patch = _patch(("a.py", "x" * (c.MAX_PATCH_BYTES + 1)))
        assert c.patch_faults(patch)

    def test_a_pathless_file_is_refused(self):
        assert c.patch_faults(_patch(("", "x = 1\n")))

    def test_an_ordinary_patch_has_no_faults(self):
        assert c.patch_faults(_patch(("a.py", "x = 1\n"))) == []


class TestValidationCommand:
    def test_it_names_the_tests_the_investigation_found(self):
        assert c.validation_command(BOUNDARY) == "pytest tests/test_requests.py -q"

    def test_no_tests_means_no_command_rather_than_a_guess(self):
        assert c.validation_command({}) == ""


class TestStagePersistence:
    def test_a_state_survives_a_round_trip(self):
        state = c.ContributionState(
            stage="validate",
            plan={"steps": [{"title": "t", "detail": "d"}]},
            patch=_patch(("a.py", "x = 1\n")),
            proceeded_unready=True,
            validation_command="pytest -q",
        )
        state.scope_check = c.check_scope(state.patch, BOUNDARY)
        restored = c.ContributionState.from_dict(state.to_dict())
        assert restored.stage == "validate"
        assert restored.patch[0].path == "a.py"
        assert restored.proceeded_unready is True
        assert restored.scope_check is not None
        assert restored.scope_check.outside_boundary == ["a.py"]

    def test_passed_is_derived_on_read_not_trusted_from_the_row(self):
        """A stored boolean that disagreed with the lists beside it would be a
        second authority on the same question."""
        raw = c.check_scope(_patch(("nope.py", "x = 1\n")), BOUNDARY).to_dict()
        raw["passed"] = True
        assert c.ScopeCheck.from_dict(raw).passed is False

    def test_an_unknown_stage_falls_back_rather_than_raising(self):
        assert c.ContributionState.from_dict({"stage": "nonsense"}).stage == "plan"

    def test_no_contribution_is_none_not_an_empty_state(self):
        assert c.ContributionState.from_dict(None) is None


class TestStageOrder:
    @pytest.mark.parametrize("stage,expected", [
        ("plan", "locate"), ("locate", "implement"), ("implement", "validate"),
        ("validate", "review"), ("review", "done"), ("done", "done"),
    ])
    def test_advance(self, stage, expected):
        assert c.advance(stage) == expected


class TestCheckPaths:
    """Scope from file paths alone — the MCP bridge's only view of the change.

    The working tree belongs to the learner and their coding agent; only
    `git diff --name-only` crosses back. So the question is whether a path-only
    check can make the scope claim WITHOUT quietly making the three it cannot.
    """

    def test_paths_inside_the_boundary_pass(self):
        out = c.check_paths(
            ["src/requests/cookies.py", "tests/test_requests.py"], BOUNDARY,
        )
        assert out["passed"] is True
        assert out["outside_boundary"] == []
        assert set(out["in_boundary"]) == {
            "src/requests/cookies.py", "tests/test_requests.py",
        }

    def test_a_path_the_boundary_never_mentions_is_outside(self):
        out = c.check_paths(["src/requests/cookies.py", "setup.py"], BOUNDARY)
        assert out["passed"] is False
        assert out["outside_boundary"] == ["setup.py"]

    def test_a_whole_file_exclusion_is_forbidden(self):
        boundary = {**BOUNDARY, "must_not_change": [
            {"file": "src/requests/adapters.py", "why_not": "transport layer"},
        ]}
        out = c.check_paths(["src/requests/adapters.py"], boundary)
        assert out["forbidden"] == ["src/requests/adapters.py"]
        assert out["passed"] is False

    def test_it_agrees_with_check_scope_on_the_same_paths(self):
        """Two definitions of "inside the boundary" would be two answers to the
        question the whole stage exists to answer. `_scope_sets` is shared so
        they cannot drift; this asserts it."""
        paths = ["src/requests/cookies.py", "setup.py", "tests/test_requests.py"]
        full = c.check_scope(
            [c.PatchFile(path=p, contents="x = 1\n") for p in paths], BOUNDARY,
        )
        thin = c.check_paths(paths, BOUNDARY)
        assert thin["passed"] == full.passed
        assert sorted(thin["in_boundary"]) == sorted(full.in_boundary)
        assert sorted(thin["outside_boundary"]) == sorted(full.outside_boundary)

    def test_it_names_what_it_did_not_look_at(self):
        """THE POINT OF THE SEPARATE FUNCTION. `check_scope` with empty contents
        would report a present symbol as missing and render "every file parses" —
        two claims nobody made. Silence reads as a pass, so the result says so."""
        out = c.check_paths(["src/requests/cookies.py"], BOUNDARY)
        assert "syntax" in out["not_checked"]
        assert "symbol definitions" in out["not_checked"]
        assert "repository tests" in out["not_checked"]
        # And it makes none of those claims by omission.
        assert "unparseable" not in out
        assert "symbol_found" not in out
        assert "symbols_defined" not in out

    def test_protected_symbols_are_reported_but_never_evaluated(self):
        out = c.check_paths(["src/requests/sessions.py"], BOUNDARY)
        assert out["unchecked_symbols"] == ["src/requests/sessions.py:Session.send"]
        # Symbol-level `must_not_change` is a constraint we were asked about and
        # cannot answer from a path. It must not fail the check...
        assert out["passed"] is True
        # ...and it must not be silent either.
        assert "protected symbols" in out["not_checked"]

    def test_an_empty_boundary_accuses_nobody(self):
        out = c.check_paths(["anything.py"], {})
        assert out["passed"] is True
        assert out["in_boundary"] == ["anything.py"]

    def test_windows_separators_and_blank_entries_are_tolerated(self):
        out = c.check_paths(
            [r"src\requests\cookies.py", "", "  "], BOUNDARY,
        )
        assert out["in_boundary"] == ["src/requests/cookies.py"]
