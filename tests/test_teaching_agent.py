"""
Pytest tests for the Teaching Agent using mocks.
Run with: uv run pytest tests/test_teaching_agent.py -v

No real Haiku and no real file reads — source reading is patched. There is no
retrieval to patch: Stage 5 removed it, and lesson context now comes from the
Dossier, then the Skeleton, then nothing (see test_dossier_session.py).
"""
import json
from unittest.mock import MagicMock, patch

from backend.agents.teaching import run
from backend.agents.teaching.agent import (
    LessonOutput,
    _SYSTEM_PROMPT,
    _build_prior_context,
    _build_user_content,
    _format_doc_context,
    _parse_output,
    _read_node_source,
    _source_header,
    _pick_extra_doc,
)
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode
from backend.pipeline.state import OnboardState


FAKE_REPO_URL = "https://github.com/psf/requests"
FAKE_REPO_PATH = "data/repos/requests"
FAKE_GOAL = {
    "primary_goal": "understand how authentication works",
    "goal_type": "understand_component",
    "focus_area": "authentication",
    "code_depth": "working",
    "depth": "deep",
}

FAKE_SOURCE = "class HTTPBasicAuth:\n    def __call__(self, r):\n        ..."

FAKE_LESSON_OUTPUT = {
    "walkthrough": "`HTTPBasicAuth.__call__` attaches the Authorization header…",
    "prompt": "Before reading on: what do you think __call__ returns?",
    "expected_answer": "The mutated PreparedRequest with the auth header set.",
    "prompt_kind": "predict-then-reveal",
}


def _make_node(title: str = "Understand HTTPBasicAuth", understood: bool = False) -> LearningNode:
    node = LearningNode(
        title=title,
        code_anchor=CodeAnchor(file="requests/auth.py", line_start=72, line_end=100),
        concept_tags=["callable classes", "request signing"],
        lesson_brief={"why": "central auth abstraction", "understand": "how __call__ signs"},
    )
    if understood:
        node.understanding_state = "understood"
    return node


def _make_state_with_current_node() -> tuple[OnboardState, LearningNode]:
    state = OnboardState(repo_url=FAKE_REPO_URL)
    state.repo_path = FAKE_REPO_PATH
    state.goal = FAKE_GOAL
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    node = graph.add_node(_make_node())
    graph.set_current(node.id)
    state.graph = graph
    return state, node


def _make_mock_client(content: str) -> MagicMock:
    message = MagicMock()
    message.content = [MagicMock(text=content)]
    client = MagicMock()
    client.messages.create.return_value = message
    return client


# ── happy path ────────────────────────────────────────────────────────────────

@patch("backend.agents.teaching.agent._read_source_lines", return_value=FAKE_SOURCE)
def test_run_sets_current_lesson(mock_read):
    state, node = _make_state_with_current_node()
    client = _make_mock_client(json.dumps(FAKE_LESSON_OUTPUT))
    result = run(state, client=client)
    assert result.current_lesson is not None
    assert result.current_lesson["prompt_kind"] == "predict-then-reveal"
    assert result.current_lesson["walkthrough"].startswith("`HTTPBasicAuth")


@patch("backend.agents.teaching.agent._read_source_lines", return_value=FAKE_SOURCE)
def test_run_caches_lesson_on_node(mock_read):
    state, node = _make_state_with_current_node()
    client = _make_mock_client(json.dumps(FAKE_LESSON_OUTPUT))
    run(state, client=client)
    assert node.cached_lesson is not None
    assert node.cached_lesson == state.current_lesson


@patch("backend.agents.teaching.agent._read_source_lines", return_value=FAKE_SOURCE)
def test_run_uses_haiku_model(mock_read):
    state, node = _make_state_with_current_node()
    client = _make_mock_client(json.dumps(FAKE_LESSON_OUTPUT))
    run(state, client=client)
    assert client.messages.create.call_args.kwargs["model"] == "claude-haiku-4-5"


@patch("backend.agents.teaching.agent._read_source_lines", return_value=FAKE_SOURCE)
def test_run_handles_fenced_json(mock_read):
    state, node = _make_state_with_current_node()
    fenced = f"```json\n{json.dumps(FAKE_LESSON_OUTPUT)}\n```"
    client = _make_mock_client(fenced)
    result = run(state, client=client)
    assert result.current_lesson is not None


@patch("backend.agents.teaching.agent._read_source_lines", return_value=FAKE_SOURCE)
def test_run_passes_source_into_prompt(mock_read):
    state, node = _make_state_with_current_node()
    client = _make_mock_client(json.dumps(FAKE_LESSON_OUTPUT))
    run(state, client=client)
    user_msg = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "HTTPBasicAuth" in user_msg
    assert "requests/auth.py" in user_msg


# ── caching ───────────────────────────────────────────────────────────────────

@patch("backend.agents.teaching.agent._read_source_lines", return_value=FAKE_SOURCE)
def test_run_cache_hit_skips_llm(mock_read):
    state, node = _make_state_with_current_node()
    node.cached_lesson = FAKE_LESSON_OUTPUT  # pre-seed a prior visit
    client = MagicMock()
    result = run(state, client=client)
    client.messages.create.assert_not_called()
    assert result.current_lesson == FAKE_LESSON_OUTPUT


# ── prior-context ─────────────────────────────────────────────────────────────

def test_prior_context_empty_when_no_understood_nodes():
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    cur = graph.add_node(_make_node())
    text = _build_prior_context(graph, cur.id)
    assert "first lesson" in text.lower()


def test_prior_context_lists_understood_nodes():
    graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)
    cur = graph.add_node(_make_node("Current node"))
    done = graph.add_node(_make_node("Session basics", understood=True))
    text = _build_prior_context(graph, cur.id)
    assert "Session basics" in text
    assert "Current node" not in text  # the current node is excluded


@patch("backend.agents.teaching.agent._read_source_lines", return_value=FAKE_SOURCE)
def test_run_includes_prior_understanding_in_prompt(mock_read):
    state, node = _make_state_with_current_node()
    done = state.graph.add_node(_make_node("Session basics", understood=True))
    client = _make_mock_client(json.dumps(FAKE_LESSON_OUTPUT))
    run(state, client=client)
    user_msg = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "Session basics" in user_msg


# ── error handling ────────────────────────────────────────────────────────────

def test_run_errors_when_graph_missing():
    state = OnboardState(repo_url=FAKE_REPO_URL)
    state.goal = FAKE_GOAL
    result = run(state, client=MagicMock())
    assert result.current_lesson is None
    assert any("graph missing" in e for e in result.errors)


def test_run_errors_when_no_current_node():
    state = OnboardState(repo_url=FAKE_REPO_URL)
    state.goal = FAKE_GOAL
    state.graph = LearningGraph(repo_url=FAKE_REPO_URL, goal=FAKE_GOAL)  # no current_node_id
    result = run(state, client=MagicMock())
    assert result.current_lesson is None
    assert any("no current node" in e for e in result.errors)


def test_run_errors_when_goal_missing():
    state, node = _make_state_with_current_node()
    state.goal = None
    result = run(state, client=MagicMock())
    assert result.current_lesson is None
    assert any("goal missing" in e for e in result.errors)


@patch("backend.agents.teaching.agent._read_source_lines",
       side_effect=FileNotFoundError("no such file"))
def test_run_errors_when_source_unreadable(mock_read):
    state, node = _make_state_with_current_node()
    client = MagicMock()
    result = run(state, client=client)
    assert result.current_lesson is None
    assert any("could not read source" in e for e in result.errors)
    client.messages.create.assert_not_called()


@patch("backend.agents.teaching.agent._read_source_lines", return_value=FAKE_SOURCE)
def test_a_truncated_lesson_is_asked_to_be_shorter_not_told_it_is_malformed(mock_read):
    """Truncation and malformed JSON both parse as "Unterminated string".

    They need opposite corrections: telling a model that ran out of output
    tokens that its JSON was invalid makes it emit the same too-long lesson and
    truncate in the same place. Observed on an 87-line doc-heavy anchor, where
    the call and its retry both failed and the session served a placeholder.
    """
    state, node = _make_state_with_current_node()
    cut_off = MagicMock()
    cut_off.content = [MagicMock(text='{"walkthrough": "a very long lesson that')]
    cut_off.stop_reason = "max_tokens"
    good = MagicMock()
    good.content = [MagicMock(text=json.dumps(FAKE_LESSON_OUTPUT))]
    good.stop_reason = "end_turn"
    client = MagicMock()
    client.messages.create.side_effect = [cut_off, good]

    result = run(state, client=client)

    assert result.current_lesson == FAKE_LESSON_OUTPUT
    correction = client.messages.create.call_args.kwargs["messages"][-1]["content"]
    assert "hit the output limit" in correction
    assert "SHORTER lesson" in correction
    assert "not a valid JSON object" not in correction


def test_a_walkthrough_containing_a_code_fence_still_parses():
    """The bug that cost a real session its lesson.

    Walkthroughs are markdown and routinely embed a ```python block. Stripping
    the wrapping fence by cutting at the NEXT ``` truncated the JSON mid-string,
    which surfaced as "Unterminated string" pointing at the walkthrough's opening
    quote — indistinguishable from an output-limit truncation, and it was not
    one: the response was complete at 674 tokens with `stop_reason=end_turn`.
    """
    lesson = {
        **FAKE_LESSON_OUTPUT,
        "walkthrough": "First read this:\n\n```python\nauth(r)\n```\n\nThen note the header.",
    }
    fenced = "```json\n" + json.dumps(lesson) + "\n```"

    assert _parse_output(fenced).walkthrough == lesson["walkthrough"]
    assert _parse_output(json.dumps(lesson)).walkthrough == lesson["walkthrough"]
    # Trailing prose after the object is ignored, as it always was.
    assert _parse_output(json.dumps(lesson) + "\nHope that helps!").prompt


@patch("backend.agents.teaching.agent._read_source_lines", return_value=FAKE_SOURCE)
def test_a_lesson_split_across_text_blocks_is_read_whole(mock_read):
    """`content[0].text` drops the rest and fails as "Unterminated string".

    That parse error is indistinguishable from an output-limit truncation, which
    sent the diagnosis in the wrong direction; joining the blocks removes the
    whole class of confusion.
    """
    state, node = _make_state_with_current_node()
    payload = json.dumps(FAKE_LESSON_OUTPUT)
    split = MagicMock()
    split.content = [
        MagicMock(type="text", text=payload[:20]),
        MagicMock(type="text", text=payload[20:]),
    ]
    split.stop_reason = "end_turn"
    client = MagicMock()
    client.messages.create.return_value = split

    result = run(state, client=client)

    assert result.current_lesson == FAKE_LESSON_OUTPUT
    assert client.messages.create.call_count == 1     # no retry was needed


@patch("backend.agents.teaching.agent._read_source_lines", return_value=FAKE_SOURCE)
def test_genuinely_malformed_json_still_gets_the_json_correction(mock_read):
    state, node = _make_state_with_current_node()
    garbage = MagicMock()
    garbage.content = [MagicMock(text="here is your lesson!")]
    garbage.stop_reason = "end_turn"
    good = MagicMock()
    good.content = [MagicMock(text=json.dumps(FAKE_LESSON_OUTPUT))]
    client = MagicMock()
    client.messages.create.side_effect = [garbage, good]

    run(state, client=client)

    correction = client.messages.create.call_args.kwargs["messages"][-1]["content"]
    assert "not a valid JSON object" in correction


@patch("backend.agents.teaching.agent._read_source_lines", return_value=FAKE_SOURCE)
def test_run_handles_invalid_llm_json(mock_read):
    state, node = _make_state_with_current_node()
    # Both the first call and the retry return garbage → give up gracefully.
    client = MagicMock()
    bad = MagicMock()
    bad.content = [MagicMock(text="not valid json")]
    client.messages.create.side_effect = [bad, bad]
    result = run(state, client=client)
    assert result.current_lesson is None
    assert node.cached_lesson is None
    assert any("LLM call failed" in e for e in result.errors)


@patch("backend.agents.teaching.agent._read_source_lines", return_value=FAKE_SOURCE)
def test_run_retries_once_on_bad_json(mock_read):
    # First response is unparseable; the retry returns valid JSON → lesson set.
    state, node = _make_state_with_current_node()
    bad = MagicMock()
    bad.content = [MagicMock(text="here you go: {oops not json")]
    good = MagicMock()
    good.content = [MagicMock(text=json.dumps(FAKE_LESSON_OUTPUT))]
    client = MagicMock()
    client.messages.create.side_effect = [bad, good]

    result = run(state, client=client)

    assert client.messages.create.call_count == 2
    assert result.current_lesson is not None
    assert result.current_lesson["prompt_kind"] == "predict-then-reveal"


# ── system-prompt calibration regression guards ──────────────────────────────


def test_system_prompt_has_depth_calibration_with_word_counts():
    # Depth must drive lesson length — the most demo-visible Teaching lever.
    # The targets came down (200/350/500 -> 100/150/250) when the walkthrough
    # was capped; what matters is that all three tiers still differ.
    assert "By `Depth requested`" in _SYSTEM_PROMPT
    assert "~100 words" in _SYSTEM_PROMPT
    assert "~150 words" in _SYSTEM_PROMPT
    assert "~250 words" in _SYSTEM_PROMPT


def test_system_prompt_has_familiarity_terminology_calibration():
    assert "By `familiarity" in _SYSTEM_PROMPT
    assert "Starting fresh" in _SYSTEM_PROMPT
    assert "Diving into source" in _SYSTEM_PROMPT


def test_system_prompt_has_background_elision_not_analogies():
    # Background should drive elision, not forced analogies.
    assert "By `background`" in _SYSTEM_PROMPT
    assert "information elision" in _SYSTEM_PROMPT.lower() or "elision" in _SYSTEM_PROMPT.lower()
    assert "DO NOT force analogies" in _SYSTEM_PROMPT


def test_user_content_includes_familiarity_and_background():
    # Plumbing check: the new fields must reach the model.
    node = LearningNode(
        title="Identify the auth extension point",
        code_anchor=CodeAnchor(file="requests/auth.py", line_start=1, line_end=5),
        concept_tags=["extension_point"],
        lesson_brief={"why": "x", "understand": "y"},
    )
    goal = {
        "primary_goal": "extend safely",
        "code_depth": "working",
        "depth": "moderate",
        "familiarity": "Skimmed the README or docs",
        "background": "Python, Flask",
    }
    content = _build_user_content(
        goal, node, "source code", "no prior context", []
    )
    assert "Skimmed the README or docs" in content
    assert "Python, Flask" in content
    # familiarity must be labeled "with THIS codebase" so the LLM doesn't
    # confuse it with general experience_level.
    assert "familiarity with THIS codebase" in content


# ── parsing ───────────────────────────────────────────────────────────────────

def test_parse_output_plain_json():
    output = _parse_output(json.dumps(FAKE_LESSON_OUTPUT))
    assert isinstance(output, LessonOutput)
    assert output.prompt_kind == "predict-then-reveal"


def test_parse_output_defaults_prompt_kind():
    payload = {k: v for k, v in FAKE_LESSON_OUTPUT.items() if k != "prompt_kind"}
    output = _parse_output(json.dumps(payload))
    assert output.prompt_kind == "predict-then-reveal"


# ── docs/ pairing (F4) ────────────────────────────────────────────────────────

_DOCS = {
    "docs/index.rst": "Requests: HTTP for Humans.",
    "docs/user/advanced.rst": (
        "Session Objects\n"
        "The Session object lets you persist parameters across requests. "
        "A Session also persists cookies. Create a Session to reuse a connection."
    ),
    "docs/user/authentication.rst": "Many web services require authentication.",
}


def test_a_docs_page_named_after_the_module_wins():
    picked = _pick_extra_doc(
        "requests/authentication.py",
        {"docs/user/advanced.rst": "x", "docs/user/authentication.rst": "auth docs"},
    )
    assert picked == ("docs/user/authentication.rst", "auth docs")


def test_a_docs_page_that_discusses_the_module_is_found_by_body():
    # The real case the old path-only match missed: docs are named by topic,
    # so "sessions" appears in advanced.rst's prose, never in its filename.
    picked = _pick_extra_doc("requests/sessions.py", _DOCS)
    assert picked is not None
    assert picked[0] == "docs/user/advanced.rst"


def test_a_single_passing_mention_is_not_enough():
    picked = _pick_extra_doc(
        "requests/adapters.py", {"docs/index.rst": "…uses adapters internally."}
    )
    assert picked is None


def test_a_generic_module_name_pairs_with_nothing():
    # "utils" would match half the documentation of any project.
    assert _pick_extra_doc("requests/utils.py", _DOCS) is None
    assert _pick_extra_doc("requests/__init__.py", _DOCS) is None


def test_no_docs_at_all_is_not_an_error():
    assert _pick_extra_doc("requests/sessions.py", {}) is None


def test_the_docs_section_reaches_the_prompt():
    node = _make_node()
    node.code_anchor = CodeAnchor(file="requests/sessions.py", line_start=1, line_end=40)
    section = _format_doc_context(node, {"extra_docs": _DOCS})
    assert "docs/user/advanced.rst" in section
    assert "Session object lets you persist" in section


# ── the objective contract (B1) ───────────────────────────────────────────────

_OBJECTIVE = (
    "Explain why auth is a callable attached to the request rather than a "
    "branch inside Session.send"
)


def _content_for(brief: dict) -> str:
    node = LearningNode(
        title="Identify the auth extension point",
        code_anchor=CodeAnchor(file="requests/auth.py", line_start=1, line_end=5),
        concept_tags=["extension_point"],
        lesson_brief=brief,
    )
    return _build_user_content(FAKE_GOAL, node, "source code", "no prior context", [])


def test_the_objective_reaches_the_teaching_prompt():
    content = _content_for(
        {"objective": _OBJECTIVE, "why": "x", "understand": "y"}
    )
    assert _OBJECTIVE in content
    # Named as the brief, not buried as one line among the others — Teaching is
    # told to build exactly this.
    assert "LEARNING OBJECTIVE" in content


def test_teaching_falls_back_to_understand_on_a_pre_objective_graph():
    # The same fallback the Grader uses. If these two diverged, the teacher and
    # the marker would aim at different claims on every old session.
    content = _content_for({"why": "x", "understand": "the takeaway"})
    assert "the takeaway" in content
    assert "LEARNING OBJECTIVE" in content


def test_the_system_prompt_subordinates_the_lesson_to_the_objective():
    assert "THE OBJECTIVE IS YOUR BRIEF" in _SYSTEM_PROMPT
    # expected_answer is demoted to a calibration reference, not the standard.
    assert "calibration reference" in _SYSTEM_PROMPT


# ── multi-anchor units (B3) ───────────────────────────────────────────────────

_FLOW_ANCHORS = [
    {"file": "a.py", "symbol": "entry", "line_start": 1, "line_end": 2},
    {"file": "b.py", "symbol": "middle", "line_start": 1, "line_end": 2},
    {"file": "c.py", "symbol": "exit", "line_start": 1, "line_end": 2},
]


def _flow_node() -> LearningNode:
    return LearningNode(
        title="Trace the signed request",
        code_anchor=CodeAnchor(file="a.py", line_start=1, line_end=2),
        concept_tags=["flow"],
        lesson_brief={
            "objective": "Trace where a request is signed",
            "why": "x", "understand": "y", "anchors": _FLOW_ANCHORS,
        },
    )


def test_every_anchors_source_reaches_the_lesson(tmp_path):
    for name in ("a", "b", "c"):
        (tmp_path / f"{name}.py").write_text(
            f"def {name}():\n    return '{name}-body'\n", encoding="utf-8"
        )
    source = _read_node_source(str(tmp_path), _flow_node())
    for name in ("a", "b", "c"):
        assert f"{name}-body" in source
    # Labelled and numbered, so the model can trace them in order.
    assert "anchor 1 of 3" in source and "anchor 3 of 3" in source


def test_a_single_anchor_node_reads_exactly_as_before(tmp_path):
    (tmp_path / "requests").mkdir()
    (tmp_path / "requests/auth.py").write_text(
        "line one\nline two\nline three\n", encoding="utf-8"
    )
    node = _make_node()  # no `anchors` key at all — a pre-B3 graph
    source = _read_node_source(str(tmp_path), node)
    assert "anchor 1 of" not in source


def test_one_stale_anchor_does_not_cost_the_whole_lesson(tmp_path):
    (tmp_path / "a.py").write_text("def a():\n    return 'a-body'\n", encoding="utf-8")
    (tmp_path / "c.py").write_text("def c():\n    return 'c-body'\n", encoding="utf-8")
    source = _read_node_source(str(tmp_path), _flow_node())  # b.py never written
    assert "a-body" in source and "c-body" in source


def test_the_prompt_says_the_anchor_order_is_the_lesson_order():
    header = _source_header(_flow_node())
    assert "3 anchors, in order" in header
    assert "Teach across all of them" in header
