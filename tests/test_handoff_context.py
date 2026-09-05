"""The grounded handoff — what leaves CodeOnboard for a coding agent.

Pure: no database, no repository on disk, no model. The caller loads the dossier,
the survey and the commit and passes them in, which is what lets every claim here
be asserted without an API key.

The two properties worth breaking a build over:

  1. REPOSITORY KNOWLEDGE AND LEARNER STATE STAY APART. A consumer that reads
     "demonstrated 11 concepts" as a fact about the code — or the reverse — makes
     exactly the claim D8 exists to prevent.
  2. NO LINE NUMBERS EVER LEAVE. `anchors.resolve` is the oracle because a model
     never names a range (D2), and a range read against a working tree we cannot
     see is the fastest thing here to go stale.
"""
from __future__ import annotations

import pytest

from backend.learning import handoff
from backend.learning.contribution import ContributionState
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode

COMMIT = "e8d2c015aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

BOUNDARY = {
    "target": [
        {"file": "src/requests/cookies.py", "symbol": "RequestsCookieJar.get_all",
         "why_here": "the jar owns name lookup"},
    ],
    "must_not_change": [
        {"file": "src/requests/cookies.py", "symbol": "RequestsCookieJar.get",
         "why_not": "existing callers rely on the single-value contract"},
    ],
    "existing_tests": [
        {"file": "tests/test_requests.py", "symbol": "TestRequests",
         "what_it_guards": "cookie conflict behaviour"},
    ],
    "edge_cases": [
        {"case": "a cookie whose value is None", "why_it_bites":
         "_find_no_duplicates treats it as absent",
         "file": "src/requests/cookies.py", "symbol": "_find_no_duplicates"},
        {"case": "same name, two domains", "why_it_bites": "get() raises"},
    ],
    "conventions": [
        {"convention": "docstrings use reST field lists",
         "evidence_file": "src/requests/api.py"},
    ],
}

DOSSIER = {
    "change_boundary": BOUNDARY,
    "contracts": [
        {"file": "src/requests/cookies.py", "symbol": "RequestsCookieJar.get",
         "contract": "returns exactly one value or raises"},
    ],
    # Deliberately present and deliberately NOT exported: the handoff is context
    # for one change, not a session dump.
    "flows": [{"name": "a flow", "steps": []}],
    "open_questions": [{"question": "q", "why_it_matters": "w"}],
}

SURVEY = {
    "subsystems": [
        {"name": "cookies", "responsibility": "cookie storage",
         "key_file": "src/requests/cookies.py"},
        {"name": "adapters", "responsibility": "transport",
         "key_file": "src/requests/adapters.py"},
    ],
}


def _graph(demonstrated: int = 2, required: int = 2) -> LearningGraph:
    graph = LearningGraph(
        repo_url="https://github.com/psf/requests",
        goal={
            "goal_type": "contribute_code",
            "primary_goal": "add a getter",
            "contribution_context": "Add get_all(name) to RequestsCookieJar.",
        },
    )
    for i in range(required):
        node = graph.add_node(LearningNode(
            title=f"Stop {i}",
            code_anchor=CodeAnchor(file="src/requests/cookies.py",
                                   line_start=1, line_end=9, symbol="Jar"),
            lesson_brief={"priority": "required", "area_id": "a1",
                          "objective": f"Explain thing {i}"},
        ))
        if i < demonstrated:
            node.understanding_state = "understood"
            node.attempts.append({
                "kind": "assessment", "answer": "a", "classification": "understood",
                "rationale": "r", "at": "2026-09-05T10:00:00Z",
            })
    return graph


class TestRefusal:
    """DI-8: refuse rather than fabricate. A confident schema wrapped around an
    empty boundary is worse than an error, because the schema is what makes a
    reader trust it."""

    def test_a_session_with_no_contribution_task_is_refused(self):
        graph = _graph()
        graph.goal["contribution_context"] = ""
        assert handoff.unusable_reason(graph, DOSSIER) == "not_a_contribution_session"

    def test_a_learner_who_is_not_ready_is_refused(self):
        assert handoff.unusable_reason(_graph(demonstrated=0), DOSSIER) \
            == "not_ready_to_implement"

    def test_a_session_with_no_change_boundary_is_refused(self):
        assert handoff.unusable_reason(_graph(), {"contracts": []}) \
            == "no_change_boundary"
        assert handoff.unusable_reason(_graph(), None) == "no_change_boundary"

    def test_a_ready_session_with_a_boundary_is_usable(self):
        assert handoff.unusable_reason(_graph(), DOSSIER) is None

    def test_the_override_opens_the_handoff_without_claiming_readiness(self):
        """`proceeded_unready` unlocks the stage; it never becomes a claim about
        understanding. Both halves are asserted here."""
        graph = _graph(demonstrated=0)
        graph.contribution = ContributionState(proceeded_unready=True)
        assert handoff.unusable_reason(graph, DOSSIER) is None
        ctx = handoff.build_context(graph, DOSSIER, SURVEY, COMMIT)
        assert ctx["learner"]["ready"] is False
        assert ctx["learner"]["demonstrated"] == 0
        assert ctx["learner"]["started_unready"] is True


class TestRepositoryKnowledge:
    def test_the_pinned_revision_travels_with_a_verify_instruction(self):
        """Every file:symbol below is true at ONE commit. Against a different
        checkout the payload is confidently wrong, which is worse than empty."""
        ctx = handoff.build_context(_graph(), DOSSIER, SURVEY, COMMIT)
        assert ctx["repository"]["commit"] == COMMIT
        assert ctx["repository"]["url"] == "https://github.com/psf/requests"
        assert "git rev-parse HEAD" in ctx["repository"]["verify"]

    def test_every_boundary_section_survives_with_its_reason(self):
        b = handoff.build_context(_graph(), DOSSIER, SURVEY, COMMIT)["change_boundary"]
        assert b["target"][0]["symbol"] == "RequestsCookieJar.get_all"
        assert b["target"][0]["why_here"]
        assert b["must_not_change"][0]["why_not"]
        assert b["existing_tests"][0]["what_it_guards"]
        assert b["conventions"][0]["convention"]
        # The reason is the point: a list of paths tells an agent where to go,
        # not what the investigation understood about going there.

    def test_an_unanchored_edge_case_keeps_its_case_and_drops_the_blanks(self):
        b = handoff.build_context(_graph(), DOSSIER, SURVEY, COMMIT)["change_boundary"]
        anchored, bare = b["edge_cases"]
        assert anchored["file"] == "src/requests/cookies.py"
        assert bare["case"] == "same name, two domains"
        # Absent, not empty: an empty string reads as a missing anchor we failed
        # to resolve rather than one the investigation never claimed.
        assert "file" not in bare

    def test_contracts_come_from_the_dossier_not_the_boundary(self):
        """`must_not_change` says WHERE not to go; a contract says WHAT stays
        true. Different claims, both useful to someone editing."""
        ctx = handoff.build_context(_graph(), DOSSIER, SURVEY, COMMIT)
        assert ctx["contracts"][0]["contract"] == "returns exactly one value or raises"

    def test_the_validation_command_is_recommended_never_run(self):
        ctx = handoff.build_context(_graph(), DOSSIER, SURVEY, COMMIT)
        assert ctx["recommended_validation"] == "pytest tests/test_requests.py -q"

    def test_no_line_number_ever_leaves(self):
        """D2 in export form. A range read against a working tree we cannot see
        goes stale the moment anything above it is edited; a symbol does not."""
        import json
        blob = json.dumps(handoff.build_context(_graph(), DOSSIER, SURVEY, COMMIT))
        assert "line_start" not in blob
        assert "line_end" not in blob

    def test_it_is_a_handoff_not_a_session_dump(self):
        ctx = handoff.build_context(_graph(), DOSSIER, SURVEY, COMMIT)
        assert set(ctx) == {
            "repository", "task", "change_boundary", "contracts",
            "recommended_validation", "learner",
        }
        # Present in the dossier, deliberately not exported.
        assert "flows" not in ctx
        assert "open_questions" not in ctx
        # And no lesson text, no attempts, no transcripts — the agent needs the
        # shape of what is known, not the learner's answers.
        import json
        blob = json.dumps(ctx)
        assert "attempts" not in blob and "cached_lesson" not in blob

    def test_a_section_that_grew_a_field_does_not_export_it_unreviewed(self):
        """The dossier is model-authored. Fields are whitelisted, not copied."""
        dossier = {"change_boundary": {"target": [
            {"file": "a.py", "symbol": "S", "why_here": "w",
             "secret_note": "should not travel"},
        ]}}
        ctx = handoff.build_context(_graph(), dossier, SURVEY, COMMIT)
        assert ctx["change_boundary"]["target"][0] == {
            "file": "a.py", "symbol": "S", "why_here": "w",
        }


class TestLearnerState:
    def test_the_counts_and_the_named_concepts_cannot_disagree(self):
        """Both read `core_nodes` + `is_demonstrated` — the same predicates
        `ready_to_implement` counts with."""
        ctx = handoff.build_context(_graph(demonstrated=1, required=3),
                                    DOSSIER, SURVEY, COMMIT)
        learner = ctx["learner"]
        assert learner["required"] == 3
        assert learner["demonstrated"] == 1
        assert len(learner["demonstrated_concepts"]) == 1
        assert learner["ready"] is False

    def test_what_demonstrated_means_travels_with_the_number(self):
        """Without this sentence, `demonstrated: 11` reads as a certification.
        It is a record of eleven exchanges."""
        learner = handoff.build_context(_graph(), DOSSIER, SURVEY, COMMIT)["learner"]
        assert "not a certification" in learner["means"]
        assert "Grader" in learner["means"]

    def test_what_was_never_taught_is_part_of_the_handoff(self):
        """As much a part of the trust map as what was covered: it says where
        this learner has no grounding at all."""
        learner = handoff.build_context(_graph(), DOSSIER, SURVEY, COMMIT)["learner"]
        assert {a["name"] for a in learner["not_taught"]} == {"adapters"}

    def test_learner_state_makes_no_claim_about_the_code(self):
        learner = handoff.build_context(_graph(), DOSSIER, SURVEY, COMMIT)["learner"]
        assert set(learner) == {
            "ready", "required", "demonstrated", "demonstrated_concepts",
            "not_taught", "started_unready", "means",
        }

    def test_repository_knowledge_makes_no_claim_about_the_learner(self):
        ctx = handoff.build_context(_graph(), DOSSIER, SURVEY, COMMIT)
        import json
        code_half = json.dumps({k: v for k, v in ctx.items() if k != "learner"})
        assert "demonstrated" not in code_half
        assert "ready" not in code_half


class TestDegradedInputs:
    """Every one of these is a state a real session reaches."""

    def test_no_survey_means_no_skipped_areas_not_a_crash(self):
        learner = handoff.build_context(_graph(), DOSSIER, None, COMMIT)["learner"]
        assert learner["not_taught"] == []

    def test_a_corrupted_boundary_section_yields_an_empty_list(self):
        dossier = {"change_boundary": {"target": "not a list",
                                       "must_not_change": [BOUNDARY["must_not_change"][0]]}}
        ctx = handoff.build_context(_graph(), dossier, SURVEY, COMMIT)
        assert ctx["change_boundary"]["target"] == []
        assert len(ctx["change_boundary"]["must_not_change"]) == 1

    def test_contracts_that_are_not_a_list_are_dropped(self):
        ctx = handoff.build_context(_graph(), {"change_boundary": BOUNDARY,
                                               "contracts": "nope"}, SURVEY, COMMIT)
        assert ctx["contracts"] == []

    def test_contracts_are_capped(self):
        dossier = {"change_boundary": BOUNDARY, "contracts": [
            {"file": f"f{i}.py", "symbol": "S", "contract": f"c{i}"}
            for i in range(40)
        ]}
        ctx = handoff.build_context(_graph(), dossier, SURVEY, COMMIT)
        assert len(ctx["contracts"]) == handoff.MAX_CONTRACTS
