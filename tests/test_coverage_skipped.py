# What the journey deliberately left out — computed, never generated.
#
# The scope card claims "not required for this contribution", and that claim is
# only worth making if it is TRUE OF THIS PLAN. A model asked "what did you skip?"
# produces a plausible list; this subtracts what the curriculum anchored on from
# what the survey said the repository contains.
#
# The two tests that matter most are the negative ones: no survey means no list,
# and a subsystem the curriculum touches never appears. Both are about the card
# refusing to say something it cannot support.

from backend.learning import coverage
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode


SURVEY = {
    "subsystems": [
        {"name": "Cookies", "responsibility": "cookie storage and lookup",
         "key_files": ["src/requests/cookies.py"]},
        {"name": "Transport adapters", "responsibility": "connection pooling",
         "key_files": ["src/requests/adapters.py"]},
        {"name": "Authentication", "responsibility": "request signing",
         "key_files": ["src/requests/auth.py"]},
        {"name": "Sessions", "responsibility": "the request lifecycle",
         "key_files": ["src/requests/sessions.py"]},
    ],
}


def _graph(*anchors: tuple[str, list[str]]) -> LearningGraph:
    """anchors: (display file, extra anchor files) per node."""
    graph = LearningGraph(repo_url="r", goal={})
    for i, (display, extra) in enumerate(anchors):
        graph.add_node(LearningNode(
            title=f"n{i}",
            code_anchor=CodeAnchor(file=display, line_start=1, line_end=2),
            lesson_brief={"anchors": [{"file": f} for f in extra]},
        ))
    return graph


class TestSkippedAreas:
    def test_subsystems_the_curriculum_never_touches_are_listed(self):
        graph = _graph(("src/requests/cookies.py", []))
        skipped = coverage.skipped_areas(SURVEY, graph)
        assert [a["name"] for a in skipped] == [
            "Transport adapters", "Authentication", "Sessions",
        ]

    def test_a_touched_subsystem_never_appears(self):
        graph = _graph(("src/requests/cookies.py", []),
                       ("src/requests/auth.py", []))
        names = [a["name"] for a in coverage.skipped_areas(SURVEY, graph)]
        assert "Cookies" not in names
        assert "Authentication" not in names

    def test_a_multi_anchor_units_later_files_count_as_covered(self):
        """A flow's second and third files are as covered as its first. Counting
        only the display anchor reported them as skipped while the learner was
        being taught out of them."""
        graph = _graph((
            "src/requests/cookies.py",
            ["src/requests/cookies.py", "src/requests/sessions.py"],
        ))
        names = [a["name"] for a in coverage.skipped_areas(SURVEY, graph)]
        assert "Sessions" not in names

    def test_the_reason_is_the_surveys_own_words(self):
        """This list is a claim about COVERAGE. Writing new prose about the
        subsystem would make it a claim about the subsystem as well."""
        graph = _graph(("src/requests/cookies.py", []))
        adapters = coverage.skipped_areas(SURVEY, graph)[0]
        assert adapters["reason"] == "connection pooling"

    def test_it_is_capped(self):
        graph = _graph(("src/requests/cookies.py", []))
        assert len(coverage.skipped_areas(SURVEY, graph, limit=2)) == 2

    def test_no_survey_means_no_list_rather_than_a_guess(self):
        """The survey is cached per (repo, commit) and can legitimately be
        missing. "We skipped nothing" and "we cannot say what we skipped" are
        different claims, and the card renders nothing for the second."""
        graph = _graph(("src/requests/cookies.py", []))
        assert coverage.skipped_areas(None, graph) == []
        assert coverage.skipped_areas({}, graph) == []
        assert coverage.skipped_areas({"subsystems": "broken"}, graph) == []

    def test_a_subsystem_with_no_files_is_not_reported(self):
        """With nothing to compare, "the curriculum does not touch it" is not a
        fact we have."""
        survey = {"subsystems": [{"name": "Vague", "responsibility": "things"}]}
        graph = _graph(("a.py", []))
        assert coverage.skipped_areas(survey, graph) == []

    def test_a_directory_shaped_subsystem_matches_a_file_anchor(self):
        """Surveys name directories, curricula anchor files. Exact-match-only
        reported directory-shaped subsystems as skipped while the learner was
        being taught out of them."""
        survey = {"subsystems": [
            {"name": "Cookies", "responsibility": "r", "key_files": ["src/requests/cookies"]},
        ]}
        graph = _graph(("src/requests/cookies.py", []))
        assert coverage.skipped_areas(survey, graph) == []

    def test_a_package_shaped_subsystem_matches_a_file_inside_it(self):
        survey = {"subsystems": [
            {"name": "Auth", "responsibility": "r", "key_files": ["src/requests/auth/"]},
        ]}
        graph = _graph(("src/requests/auth/basic.py", []))
        assert coverage.skipped_areas(survey, graph) == []

    def test_separators_and_case_do_not_matter(self):
        graph = _graph(("src\\Requests\\Cookies.py", []))
        names = [a["name"] for a in coverage.skipped_areas(SURVEY, graph)]
        assert "Cookies" not in names


class TestTheRealSurveyShape:
    """`key_file`, SINGULAR, is what a real survey writes.

    Reading only the plural forms made this list silently empty on every real
    session: every subsystem looked file-less, so none could be reported as
    untouched and the card had nothing to show. Found in rehearsal rather than
    in the suite, because the suite's fixture used the shape the code expected —
    which is the reason this class exists beside it.
    """

    REAL = {
        "subsystems": [
            {"name": "src/requests/cookies.py", "responsibility": "cookie jar",
             "key_file": "src/requests/cookies.py"},
            {"name": "src/requests/adapters.py", "responsibility": "transport",
             "key_file": "src/requests/adapters.py", "key_symbol": "HTTPAdapter"},
            {"name": "setup.py", "responsibility": "packaging",
             "key_file": "setup.py"},
            {"name": "src/requests/models.py", "responsibility": "the models",
             "key_file": "src/requests/models.py", "key_symbol": "Response"},
        ],
        "core_abstractions": [
            {"file": "src/requests/models.py", "symbol": "Response", "role": "r"},
        ],
    }

    def test_a_singular_key_file_is_read(self):
        graph = _graph(("src/requests/cookies.py", []))
        names = [a["name"] for a in coverage.skipped_areas(self.REAL, graph)]
        assert names, "a real survey's subsystems must be readable"
        assert "src/requests/cookies.py" not in names

    def test_the_surveys_own_central_files_come_first(self):
        """Order only — this cannot add or remove an entry, only decide which
        three of seventeen get the space. Both signals (`core_abstractions` and
        `key_symbol`) are the survey's own judgement, not ours.

        Without it the learner is told they skipped `setup.py` while `models.py`
        goes unmentioned, which is the opposite of useful.
        """
        graph = _graph(("src/requests/cookies.py", []))
        names = [a["name"] for a in coverage.skipped_areas(self.REAL, graph)]
        assert names.index("src/requests/models.py") < names.index("setup.py")
        assert names.index("src/requests/adapters.py") < names.index("setup.py")

    def test_ranking_never_changes_the_membership(self):
        graph = _graph(("src/requests/cookies.py", []))
        names = {a["name"] for a in coverage.skipped_areas(self.REAL, graph, limit=99)}
        assert names == {
            "src/requests/adapters.py", "setup.py", "src/requests/models.py",
        }
