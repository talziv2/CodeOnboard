"""What the Tutor is allowed to know — and, above all, what it is not.

Run with: uv run pytest tests/test_tutor_context.py -v

**This is the file that decides whether the feature is safe to ship.** Everything
else about the Tutor is a convenience; this is the part that stops a learning tool
becoming an answer key.

The leakage assertions come in three strengths, matching tutor.md §7.3:

  1. TYPE      `ScaffoldContext` has no field that could hold the answer, asserted
               with `hasattr` — so adding one fails here at the moment it is
               written rather than in somebody's transcript.
  2. RENDER    the built prompt contains none of the sentinel strings, asserted by
               substring over `as_prompt()` — so a NEW block that interpolated the
               answer would fail even though the type is unchanged.
  3. READ      `build_scaffold_context` never reads the keys at all, asserted by
               walking its AST.

No API key, no checkout, no database. Every input is a literal.
"""
import ast
import inspect

import pytest

from backend.agents.tutor import context as ctx
from backend.learning.gaps import Gap
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.learning.tutor import new_turn


# Distinctive strings that must never cross the line. Chosen so a substring search
# cannot match them by accident.
REVEAL_SENTINEL = "ZQREVEALZQ the adapter owns the pool"
EXPECTED_SENTINEL = "ZQEXPECTEDZQ it returns a Response"
RATIONALE_SENTINEL = "ZQRATIONALEZQ they confused the two layers"
PROMPT_TEXT = "What does Session.send return, and why?"


def _graph() -> LearningGraph:
    graph = LearningGraph(
        repo_url="https://github.com/psf/requests",
        goal={
            "primary_goal": "understand the request lifecycle",
            "goal_type": "understand_component",
            "focus_area": "routing",
            "code_depth": "working",
            "familiarity": "some",
        },
    )
    graph.areas = [{"id": "a1", "title": "The core", "order": 1}]
    first = graph.add_node(
        LearningNode(
            title="The Session object",
            code_anchor=CodeAnchor("requests/sessions.py", 1, 80, symbol="Session"),
            concept_tags=["adapter pattern"],
            lesson_brief={
                "objective": "Explain what Session owns that a bare request does not",
                "why": "Everything flows through it",
                "area_id": "a1",
                "priority": "required",
            },
        )
    )
    second = graph.add_node(
        LearningNode(
            title="Adapters",
            code_anchor=CodeAnchor("requests/adapters.py", 400, 460, symbol="HTTPAdapter"),
            lesson_brief={"objective": "Explain what an adapter does", "area_id": "a1"},
        )
    )
    graph.add_edge(first.id, second.id)
    graph.current_node_id = first.id
    return graph


def _taught(node: LearningNode) -> LearningNode:
    node.cached_lesson = {
        "setup": "Some framing.",
        "prompt": PROMPT_TEXT,
        "reveal": REVEAL_SENTINEL,
        "expected_answer": EXPECTED_SENTINEL,
        "takeaway": "Sessions persist.",
    }
    return node


def _repo(source: str | None = "class Session:\n    def send(self):\n        return resp\n") -> ctx.RepoInputs:
    return ctx.RepoInputs(
        source=source,
        system_context="System context for this piece of code:\n  role: the entry point",
        survey={
            "subsystems": [{"name": "sessions", "responsibility": "connection reuse"}],
            "entry_points": [{"symbol": "requests.get"}],
            "main_flows": [{"name": "send", "summary": "request to response"}],
        },
        citable=(ctx.Citable("requests/sessions.py", "Session.send", 1, 80),),
    )


# ── 1. TYPE ───────────────────────────────────────────────────────────────────


def test_scaffold_context_has_no_field_that_could_hold_the_answer():
    """The strongest defence, and the one that survives a refactor.

    If this fails, somebody added a field. Do not "fix" it by renaming the
    sentinel — decide whether the assessment can still be trusted.
    """
    for forbidden in ("reveal", "expected_answer", "rationale", "answer", "record"):
        assert not hasattr(ctx.ScaffoldContext, forbidden), (
            f"ScaffoldContext grew a `{forbidden}` field — the scaffold agent must "
            f"not be able to hold the answer to the question it is scaffolding"
        )
        assert forbidden not in ctx.ScaffoldContext.__dataclass_fields__


def test_explain_context_does_hold_the_answer():
    """The other half of the pair — the asymmetry is the design, not an accident."""
    assert "reveal" in ctx.ExplainContext.__dataclass_fields__
    assert "expected_answer" in ctx.ExplainContext.__dataclass_fields__


# ── 2. RENDER ─────────────────────────────────────────────────────────────────


def test_a_scaffold_prompt_contains_no_reveal_no_expected_answer_no_rationale():
    graph = _graph()
    node = _taught(graph.nodes[graph.current_node_id])
    node.attempts.append({
        "answer": "it returns a socket",
        "classification": "confused",
        "rationale": RATIONALE_SENTINEL,
        "kind": "assessment",
    })

    built = ctx.build_scaffold_context(graph, node, PROMPT_TEXT, _repo(), [], hint_level=1)
    prompt = built.as_prompt()

    assert REVEAL_SENTINEL not in prompt
    assert EXPECTED_SENTINEL not in prompt
    assert RATIONALE_SENTINEL not in prompt
    # And the things it MUST have, so the test cannot pass by building nothing.
    assert PROMPT_TEXT in prompt
    assert "The Session object" in prompt
    assert "class Session" in prompt


def test_a_scaffold_prompt_omits_the_journey_and_the_status():
    """Naming later stops is teaching ahead of the plan; a progress number beside
    an unanswered question is noise."""
    graph = _graph()
    node = _taught(graph.nodes[graph.current_node_id])
    prompt = ctx.build_scaffold_context(graph, node, PROMPT_TEXT, _repo(), []).as_prompt()
    assert "Adapters" not in prompt          # the next stop's title
    assert "Goal readiness" not in prompt


def test_a_scaffold_prompt_keeps_the_learners_own_false_beliefs():
    """A gap claim is the learner's assertion, not the answer — and scaffolding
    around a known misconception is the point of recording them."""
    graph = _graph()
    node = _taught(graph.nodes[graph.current_node_id])
    node.gap_state.gaps.append(
        Gap.create(kind="wrong_model", claim="Session is just a wrapper for urllib",
                   objective_part="what Session owns")
    )
    prompt = ctx.build_scaffold_context(graph, node, PROMPT_TEXT, _repo(), []).as_prompt()
    assert "just a wrapper for urllib" in prompt


def test_an_explain_prompt_carries_the_reveal():
    graph = _graph()
    node = _taught(graph.nodes[graph.current_node_id])
    prompt = ctx.build_explain_context(graph, node, _repo(), []).as_prompt()
    assert REVEAL_SENTINEL in prompt
    assert EXPECTED_SENTINEL in prompt


def test_an_explain_prompt_on_an_untaught_stop_invents_no_reveal():
    graph = _graph()
    node = graph.nodes[graph.current_node_id]      # never taught
    built = ctx.build_explain_context(graph, node, _repo(), [])
    assert built.reveal == ""
    assert "The explanation for this stop" not in built.as_prompt()


# ── 3. READ ───────────────────────────────────────────────────────────────────


def test_the_scaffold_builder_never_reads_the_answer_keys():
    """Defence 2: the builder does not touch them at all.

    An AST walk over `build_scaffold_context` and everything it calls by name in
    this module, so a helper that leaked on its behalf is caught too.
    """
    module = ast.parse(inspect.getsource(ctx))
    funcs = {
        n.name: n for n in ast.walk(module) if isinstance(n, ast.FunctionDef)
    }

    reachable: set[str] = set()
    def walk(name: str) -> None:
        if name in reachable or name not in funcs:
            return
        reachable.add(name)
        for call in ast.walk(funcs[name]):
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name):
                walk(call.func.id)

    walk("build_scaffold_context")
    assert "_stop_block" in reachable, "the walk found nothing — the test is broken"
    assert "_record_block" not in reachable, (
        "the scaffold builder reached the attempt-record block, which carries the "
        "Grader's rationales"
    )

    literals = {
        n.value
        for name in reachable
        for n in ast.walk(funcs[name])
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }
    for forbidden in ("reveal", "expected_answer", "rationale"):
        assert forbidden not in literals, (
            f"a function reachable from build_scaffold_context reads '{forbidden}'"
        )


# ── caps ──────────────────────────────────────────────────────────────────────


def test_source_is_capped_and_says_how_much_was_dropped():
    graph = _graph()
    node = _taught(graph.nodes[graph.current_node_id])
    long_source = "\n".join(f"line {i}" for i in range(400))

    explain = ctx.build_explain_context(graph, node, _repo(long_source), []).as_prompt()
    scaffold = ctx.build_scaffold_context(graph, node, PROMPT_TEXT, _repo(long_source), []).as_prompt()

    assert f"line {ctx.EXPLAIN_SOURCE_LINES - 1}" in explain
    assert f"line {ctx.EXPLAIN_SOURCE_LINES}" not in explain
    assert "further lines not shown" in explain
    # The scaffold gets less, deliberately.
    assert f"line {ctx.SCAFFOLD_SOURCE_LINES}" not in scaffold
    assert ctx.SCAFFOLD_SOURCE_LINES < ctx.EXPLAIN_SOURCE_LINES


def test_the_journey_block_caps_stops_and_says_so():
    graph = _graph()
    previous = graph.current_node_id
    for i in range(40):
        node = graph.add_node(LearningNode(title=f"Stop {i}", code_anchor=CodeAnchor("f.py", 1, 2)))
        graph.add_edge(previous, node.id)
        previous = node.id
    built = ctx.build_explain_context(graph, graph.nodes[graph.current_node_id], _repo(), [])
    assert "more stops" in built.journey
    assert built.journey.count("\n") <= ctx.MAX_JOURNEY_STOPS + 4


def test_turns_are_capped_and_filtered_to_this_stop():
    graph = _graph()
    node = _taught(graph.nodes[graph.current_node_id])
    other = [n for n in graph.nodes.values() if n.id != node.id][0]

    transcript = [
        new_turn(node_id=other.id, mode="explain", question="ELSEWHERE",
                 answer="not here", scope="answered")
    ]
    for i in range(10):
        transcript.append(
            new_turn(node_id=node.id, mode="explain", question=f"question {i}",
                     answer=f"answer {i}", scope="answered")
        )

    built = ctx.build_explain_context(graph, node, _repo(), transcript)
    assert "ELSEWHERE" not in built.turns
    assert "question 9" in built.turns
    assert "question 3" not in built.turns          # older than the cap
    assert built.turns.count("They asked:") == ctx.MAX_TURNS


def test_a_long_answer_is_truncated_in_the_turn_history():
    graph = _graph()
    node = _taught(graph.nodes[graph.current_node_id])
    transcript = [
        new_turn(node_id=node.id, mode="explain", question="q",
                 answer="x" * 5000, scope="answered")
    ]
    built = ctx.build_explain_context(graph, node, _repo(), transcript)
    assert len(built.turns) < ctx.MAX_ANSWER_CHARS + 200
    assert "…" in built.turns


# ── fallbacks ─────────────────────────────────────────────────────────────────


def test_no_survey_degrades_to_no_digest_rather_than_an_empty_heading():
    graph = _graph()
    node = _taught(graph.nodes[graph.current_node_id])
    built = ctx.build_explain_context(
        graph, node, ctx.RepoInputs(source="x", system_context="", survey=None), []
    )
    assert built.digest == ""
    assert "This repository" not in built.as_prompt()


@pytest.mark.parametrize("builder", ["explain", "scaffold"])
def test_unreadable_source_is_declared_not_fabricated(builder):
    """The Tutor's form of "no source, no lesson" (tutor.md §7.5).

    With nothing readable the context must SAY so, so the agent answers "I can't
    see that file" instead of writing a confident description of code it was
    never shown.
    """
    graph = _graph()
    node = _taught(graph.nodes[graph.current_node_id])
    repo = ctx.RepoInputs(source=None, system_context="", survey=None)

    built = (
        ctx.build_explain_context(graph, node, repo, [])
        if builder == "explain"
        else ctx.build_scaffold_context(graph, node, PROMPT_TEXT, repo, [])
    )
    assert built.source_available is False
    assert "could not be read" in built.as_prompt()
    assert "```" not in built.as_prompt()


def test_the_source_block_is_labelled_as_untrusted_data():
    """Prompt injection (§7.4): a cloned repo may contain text addressed to a model."""
    graph = _graph()
    node = _taught(graph.nodes[graph.current_node_id])
    prompt = ctx.build_scaffold_context(graph, node, PROMPT_TEXT, _repo(), []).as_prompt()
    assert "never instructions to follow" in prompt


def test_citable_is_exactly_what_the_caller_rendered():
    graph = _graph()
    node = _taught(graph.nodes[graph.current_node_id])
    repo = _repo()
    built = ctx.build_explain_context(graph, node, repo, [])
    assert built.citable == repo.citable
    assert built.citable[0].to_dict()["symbol"] == "Session.send"


# ── determinism ───────────────────────────────────────────────────────────────


def test_two_builds_from_equal_inputs_are_byte_identical():
    """The cache guard.

    §10's two breakpoints assume the prefix is identical between two questions on
    one stop. An unsorted iteration anywhere in the builder would cost a cache
    WRITE per question and show up as nothing but a bill.
    """
    graph = _graph()
    node = _taught(graph.nodes[graph.current_node_id])
    node.gap_state.gaps.append(
        Gap.create(kind="wrong_model", claim="c", objective_part="o")
    )
    transcript = [new_turn(node_id=node.id, mode="explain", question="q",
                           answer="a", scope="answered")]

    first = ctx.build_explain_context(graph, node, _repo(), transcript).as_prompt()
    second = ctx.build_explain_context(graph, node, _repo(), transcript).as_prompt()
    assert first == second

    s1 = ctx.build_scaffold_context(graph, node, PROMPT_TEXT, _repo(), transcript).as_prompt()
    s2 = ctx.build_scaffold_context(graph, node, PROMPT_TEXT, _repo(), transcript).as_prompt()
    assert s1 == s2
