"""
Pytest tests for the exploration harness (Stage 1, backend/repo/explore.py).
Run with: uv run pytest tests/test_explore.py -v

The harness exists to make three guarantees that a prompt cannot make, so those
are what these tests pin down:

  1. budgets are enforced here, in code, not requested of the model
  2. exhaustion, tool failure and API failure are all *results* — nothing raises
  3. every tool call and every token is recorded

No network: the client is a scripted fake, so a turn's tool calls are exactly
what the test says they are.
"""
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.repo import explore
from backend.repo.explore import Budget, Exploration, ReportSpec
from backend.repo.skeleton import build_skeleton


# ── the checkout under exploration ────────────────────────────────────────────

MODULE = '''\
"""Widgets."""
from .support import helper


class Widget:
    def spin(self):
        return helper()
'''

SUPPORT = '''\
def helper():
    return 42
'''


@pytest.fixture
def repo(tmp_path: Path) -> str:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "widget.py").write_text(MODULE, encoding="utf-8")
    (pkg / "support.py").write_text(SUPPORT, encoding="utf-8")
    build_skeleton.cache_clear()
    return str(tmp_path)


# ── the scripted client ───────────────────────────────────────────────────────


def text_block(text):
    return SimpleNamespace(type="text", text=text)


def tool_block(name, arguments, id="tu_1"):
    return SimpleNamespace(type="tool_use", id=id, name=name, input=arguments)


def turn(*blocks, usage=None):
    """One scripted assistant response."""
    stop = "tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn"
    return SimpleNamespace(
        content=list(blocks),
        stop_reason=stop,
        usage=usage or SimpleNamespace(
            input_tokens=100, output_tokens=20,
            cache_creation_input_tokens=0, cache_read_input_tokens=0,
        ),
    )


class FakeClient:
    """Replays a script of responses and records the requests it was sent."""

    def __init__(self, script, on_request=None):
        self.script = list(script)
        self.requests: list[dict] = []
        self.on_request = on_request
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        # Deep-copy: the harness mutates one `messages` list in place across
        # turns, so recording the reference would make every recorded request
        # look like the last one — and quietly turn the cached-prefix assertions
        # below into tautologies. The real SDK serialises per call.
        self.requests.append(copy.deepcopy(kwargs))
        if self.on_request is not None:
            self.on_request(kwargs)
        if not self.script:
            # Falling off the end of the script means the loop ran longer than
            # the test expected — say so rather than looping forever.
            return turn(text_block("script exhausted"))
        nxt = self.script.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


def run(repo, script, **kwargs):
    client = FakeClient(script)
    result = explore.explore(
        client=client, repo_path=repo,
        instructions="Explore this repository.", task="Describe the widget.",
        **kwargs,
    )
    return result, client


REPORT = ReportSpec(
    name="submit_survey",
    description="Submit the finished survey.",
    input_schema={
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
    },
)


# ── the happy paths ───────────────────────────────────────────────────────────


def test_a_loop_with_no_tool_calls_returns_the_prose(repo):
    result, client = run(repo, [turn(text_block("Nothing to look at."))])
    assert result.stop_reason == explore.ANSWERED
    assert result.ok
    assert result.text == "Nothing to look at."
    assert result.turns == 1
    assert result.trace == []
    assert len(client.requests) == 1


def test_tool_results_are_fed_back_and_the_loop_continues(repo):
    result, client = run(repo, [
        turn(tool_block("symbols", {"path": "pkg/widget.py"})),
        turn(text_block("Widget.spin calls helper.")),
    ])
    assert result.stop_reason == explore.ANSWERED
    assert result.turns == 2
    assert [c.name for c in result.trace] == ["symbols"]
    assert result.trace[0].ok

    # Second request carries: task, assistant tool_use, user tool_result.
    replayed = client.requests[1]["messages"]
    assert [m["role"] for m in replayed] == ["user", "assistant", "user"]
    assert replayed[1]["content"][0]["type"] == "tool_use"
    tool_result = replayed[2]["content"][0]
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == "tu_1"
    assert "Widget.spin" in tool_result["content"]


def test_parallel_tool_calls_in_one_turn_all_run(repo):
    result, client = run(repo, [
        turn(
            tool_block("symbols", {"path": "pkg/widget.py"}, id="a"),
            tool_block("read_file", {"path": "pkg/support.py"}, id="b"),
            tool_block("search_code", {"pattern": "helper"}, id="c"),
        ),
        turn(text_block("done")),
    ])
    assert [c.name for c in result.trace] == ["symbols", "read_file", "search_code"]
    assert all(c.turn == 1 for c in result.trace)
    # All three results come back in a single user message, as the API requires.
    blocks = client.requests[1]["messages"][2]["content"]
    assert [b["tool_use_id"] for b in blocks] == ["a", "b", "c"]


def test_the_report_tool_ends_the_loop_with_a_payload(repo):
    result, _ = run(repo, [
        turn(tool_block("symbols", {"path": "pkg/widget.py"}, id="a")),
        turn(tool_block("submit_survey", {"summary": "one widget"}, id="r")),
        turn(text_block("should never be reached")),
    ], report=REPORT)
    assert result.stop_reason == explore.REPORTED
    assert result.output == {"summary": "one widget"}
    assert result.turns == 2


def test_a_missing_report_is_reported_as_such(repo):
    result, _ = run(repo, [turn(text_block("I would rather not."))], report=REPORT)
    assert result.stop_reason == explore.NO_REPORT
    assert not result.ok
    assert result.output is None


def test_no_report_spec_means_prose_is_success(repo):
    result, _ = run(repo, [turn(text_block("prose"))])
    assert result.stop_reason == explore.ANSWERED and result.ok


# ── budgets are enforced in code ──────────────────────────────────────────────


def test_the_turn_budget_stops_the_loop(repo):
    script = [turn(tool_block("symbols", {"path": "pkg/widget.py"})) for _ in range(10)]
    result, client = run(repo, script, budget=Budget(max_turns=3))
    assert result.stop_reason == explore.TURN_BUDGET
    assert result.budget_exhausted
    assert result.turns == 4          # 3 exploring turns + the salvage turn
    assert len(client.requests) == 4


def test_the_tool_call_budget_stops_the_loop(repo):
    # One turn, four calls, a cap of two: the cap is checked after the turn, so
    # a parallel burst can overshoot within a turn but never continues past it.
    script = [
        turn(*[tool_block("symbols", {"path": "pkg/widget.py"}, id=f"t{i}") for i in range(4)]),
        turn(text_block("unreached")),
    ]
    result, _ = run(repo, script, budget=Budget(max_tool_calls=2, max_turns=9))
    assert result.stop_reason == explore.TOOL_CALL_BUDGET
    assert len(result.trace) == 4


def test_the_read_budget_stops_the_loop(repo):
    script = [
        turn(tool_block("read_file", {"path": "pkg/widget.py"}, id=f"t{i}"))
        for i in range(6)
    ]
    result, _ = run(repo, script, budget=Budget(max_result_chars=50, max_turns=9))
    assert result.stop_reason == explore.READ_BUDGET
    assert result.result_chars >= 50
    # Stopped early rather than spending the whole turn budget.
    assert result.turns < 9


def test_the_time_budget_stops_the_loop(repo, monkeypatch):
    clock = iter([0.0, 0.0, 5.0, 5.0, 99.0, 99.0, 99.0, 99.0])
    monkeypatch.setattr(explore.time, "monotonic", lambda: next(clock))
    script = [turn(tool_block("symbols", {"path": "pkg/widget.py"})) for _ in range(6)]
    result, _ = run(repo, script, budget=Budget(max_seconds=10.0, max_turns=6))
    assert result.stop_reason == explore.TIME_BUDGET


def test_budget_exhaustion_still_yields_a_report(repo):
    """§5.4: exhaustion is a partial result, not a discarded run."""
    script = [turn(tool_block("symbols", {"path": "pkg/widget.py"})) for _ in range(3)]
    script.append(turn(tool_block("submit_survey", {"summary": "partial"}, id="r")))
    result, client = run(repo, script, budget=Budget(max_turns=3), report=REPORT)
    assert result.stop_reason == explore.TURN_BUDGET   # honest about why it stopped
    assert result.output == {"summary": "partial"}     # ...and still produced one
    assert result.budget_exhausted

    salvage = client.requests[-1]
    assert salvage["tool_choice"] == {"type": "tool", "name": "submit_survey"}
    assert "budget is now exhausted" in salvage["messages"][-1]["content"]


class _WireValidator:
    """Accepts anything with a `summary`; treats a stringified `items` as broken.

    Stands in for `DossierValidator`: it distinguishes a payload that could not
    be *read* (repairable by re-emitting) from one that is merely thin (not).
    """

    def __init__(self):
        self.seen: list[dict] = []

    def _broken(self, payload):
        return not isinstance(payload.get("items", []), list)

    def __call__(self, payload):
        self.seen.append(payload)
        if self._broken(payload):
            return "items arrived as a string"
        return None if payload.get("summary") else "no summary"

    def repair_prompt(self, payload):
        return "Resubmit the SAME findings as JSON." if self._broken(payload) else None


def test_an_unreadable_salvage_is_re_emitted_once(repo):
    """A transmission fault must not cost the run everything it gathered.

    The salvaged payload arrived unreadable, so the findings are intact but
    unusable; one forced re-send recovers them. This is not extra exploration —
    the tool_choice pins the model straight back to the report.
    """
    validator = _WireValidator()
    script = [turn(tool_block("symbols", {"path": "pkg/widget.py"}))]
    script.append(turn(tool_block("submit_survey", {"items": "<item>a</item>"}, id="r1")))
    script.append(turn(tool_block("submit_survey",
                                  {"summary": "recovered", "items": ["a"]}, id="r2")))
    result, client = run(repo, script, budget=Budget(max_turns=1), report=REPORT,
                         validate=validator)

    assert result.output == {"summary": "recovered", "items": ["a"]}
    assert result.contract_met is True
    assert result.stop_reason == explore.TURN_BUDGET   # still honest about the stop
    repair = client.requests[-1]
    assert repair["tool_choice"] == {"type": "tool", "name": "submit_survey"}
    assert "Resubmit the SAME findings" in repair["messages"][-1]["content"][0]["content"]
    assert any(c.facts.get("repair") for c in result.trace)


def test_the_repair_turn_answers_every_tool_use_in_the_salvage_turn(repo):
    """Forcing the report tool does not stop the model calling others beside it.

    Observed in a real run: the salvage turn emitted nine exploration calls
    alongside the report, the repair request answered only the report, and the
    API rejected the whole message — so the repair never happened and the
    unreadable dossier reached the Mentor anyway. Every `tool_use` needs a
    `tool_result`.
    """
    validator = _WireValidator()
    salvage = turn(
        tool_block("submit_survey", {"items": "<item>a</item>"}, id="r1"),
        tool_block("symbols", {"path": "pkg/widget.py"}, id="extra1"),
        tool_block("read_file", {"path": "pkg/support.py"}, id="extra2"),
    )
    script = [turn(tool_block("symbols", {"path": "pkg/widget.py"})), salvage]
    script.append(turn(tool_block("submit_survey",
                                  {"summary": "recovered", "items": ["a"]}, id="r2")))
    result, client = run(repo, script, budget=Budget(max_turns=1), report=REPORT,
                         validate=validator)

    repair = client.requests[-1]
    answered = {
        block["tool_use_id"] for block in repair["messages"][-1]["content"]
        if block.get("type") == "tool_result"
    }
    assert answered == {"r1", "extra1", "extra2"}
    assert result.output == {"summary": "recovered", "items": ["a"]}


def test_a_thin_salvage_gets_no_repair_turn(repo):
    """Re-emitting a thin report would not make it less thin — so we do not ask."""
    validator = _WireValidator()
    script = [turn(tool_block("symbols", {"path": "pkg/widget.py"}))]
    script.append(turn(tool_block("submit_survey", {"items": []}, id="r1")))
    result, client = run(repo, script, budget=Budget(max_turns=1), report=REPORT,
                         validate=validator)

    assert result.output == {"items": []}
    assert result.contract_met is False
    assert not any(c.facts.get("repair") for c in result.trace)
    assert len(validator.seen) == 1


def test_a_repair_that_fails_the_same_way_is_not_retried(repo):
    validator = _WireValidator()
    script = [turn(tool_block("symbols", {"path": "pkg/widget.py"}))]
    script += [
        turn(tool_block("submit_survey", {"items": "<item>a</item>"}, id=f"r{i}"))
        for i in range(4)
    ]
    result, _ = run(repo, script, budget=Budget(max_turns=1), report=REPORT,
                    validate=validator)

    assert result.contract_met is False
    assert result.output == {"items": "<item>a</item>"}   # the first one, kept
    assert sum(1 for c in result.trace if c.facts.get("repair")) == 1


def test_an_ambiguous_neighbors_call_renders_both_definitions(repo, tmp_path):
    """The fork in the road has to reach the model as a signpost, not an error."""
    (tmp_path / "one.py").write_text("def thing(): pass\n", encoding="utf-8")
    (tmp_path / "two.py").write_text("class thing: pass\n", encoding="utf-8")
    build_skeleton.cache_clear()

    result, _ = run(str(tmp_path), [
        turn(tool_block("neighbors", {"symbol": "thing"})),
        turn(text_block("Two definitions; the function wraps the class.")),
    ])
    call = result.trace[0]
    assert call.ok and call.facts["ambiguous"]
    assert call.facts["paths"] == ["one.py", "two.py"]


def test_a_salvage_turn_that_produces_nothing_keeps_the_budget_reason(repo):
    script = [turn(tool_block("symbols", {"path": "pkg/widget.py"})) for _ in range(2)]
    script.append(turn(text_block("I have nothing")))
    result, _ = run(repo, script, budget=Budget(max_turns=2), report=REPORT)
    assert result.stop_reason == explore.TURN_BUDGET
    assert result.output is None


def test_salvage_forbids_tools_when_there_is_no_report_spec(repo):
    script = [turn(tool_block("symbols", {"path": "pkg/widget.py"})) for _ in range(2)]
    script.append(turn(text_block("Here is what I found.")))
    result, client = run(repo, script, budget=Budget(max_turns=2))
    assert client.requests[-1]["tool_choice"] == {"type": "none"}
    assert result.text == "Here is what I found."


def test_default_budget_values_are_bounded(repo):
    budget = Budget()
    assert 1 <= budget.max_turns <= 30
    assert budget.max_tool_calls >= budget.max_turns
    assert budget.max_result_chars > 0
    assert budget.max_seconds > 0


# ── failures are results ──────────────────────────────────────────────────────


def test_a_failing_tool_comes_back_as_an_error_result_the_model_can_recover_from(repo):
    result, client = run(repo, [
        turn(tool_block("read_file", {"path": "pkg/nope.py"})),
        turn(tool_block("read_file", {"path": "pkg/widget.py"}, id="b")),
        turn(text_block("recovered")),
    ])
    assert result.stop_reason == explore.ANSWERED
    assert [c.ok for c in result.trace] == [False, True]
    assert result.trace[0].error == "not_found"

    failed = client.requests[1]["messages"][2]["content"][0]
    assert failed["is_error"] is True
    assert "not_found" in failed["content"]


def test_an_unknown_tool_name_does_not_break_the_loop(repo):
    result, _ = run(repo, [
        turn(tool_block("semantic_search", {"query": "widgets"})),
        turn(text_block("fine, I will use the real ones")),
    ])
    assert result.stop_reason == explore.ANSWERED
    assert result.trace[0].error == "unknown_tool"


def test_bad_tool_arguments_do_not_break_the_loop(repo):
    result, _ = run(repo, [
        turn(tool_block("read_file", {"pathh": "pkg/widget.py"})),
        turn(text_block("typo noted")),
    ])
    assert result.trace[0].error == "bad_arguments"
    assert result.stop_reason == explore.ANSWERED


def test_an_api_failure_returns_a_partial_result_instead_of_raising(repo):
    result, _ = run(repo, [
        turn(tool_block("symbols", {"path": "pkg/widget.py"})),
        RuntimeError("connection reset"),
    ])
    assert result.stop_reason == explore.API_ERROR
    assert not result.ok
    assert len(result.trace) == 1          # the work before the failure survives
    assert result.errors and "connection reset" in result.errors[0]


def test_an_api_failure_on_the_first_call_is_still_not_an_exception(repo):
    result, _ = run(repo, [RuntimeError("no api key")])
    assert result.stop_reason == explore.API_ERROR
    assert result.turns == 0
    assert result.errors


def test_an_api_failure_during_salvage_is_swallowed(repo):
    script = [turn(tool_block("symbols", {"path": "pkg/widget.py"})) for _ in range(2)]
    script.append(RuntimeError("overloaded"))
    result, _ = run(repo, script, budget=Budget(max_turns=2), report=REPORT)
    assert result.stop_reason == explore.TURN_BUDGET
    assert result.output is None
    assert result.errors


# ── recording: trace and usage ────────────────────────────────────────────────


def test_the_trace_records_arguments_and_a_summary_for_every_call(repo):
    result, _ = run(repo, [
        turn(tool_block("read_file", {"path": "pkg/support.py"})),
        turn(text_block("done")),
    ])
    call = result.trace[0]
    assert call.arguments == {"path": "pkg/support.py"}
    assert call.result_chars > 0
    assert "pkg/support.py" in call.summary
    assert call.turn == 1


def test_on_call_reports_progress_while_the_loop_runs(repo):
    seen = []
    run(repo, [
        turn(tool_block("symbols", {"path": "pkg/widget.py"}, id="a"),
             tool_block("list_files", {}, id="b")),
        turn(text_block("done")),
    ], on_call=seen.append)
    assert [c.name for c in seen] == ["symbols", "list_files"]


def test_the_report_call_is_traced_but_costs_no_read_budget(repo):
    result, _ = run(repo, [
        turn(tool_block("submit_survey", {"summary": "s"}, id="r")),
    ], report=REPORT)
    assert [c.name for c in result.trace] == ["submit_survey"]
    assert result.result_chars == 0


def test_usage_accumulates_across_every_call(repo):
    script = [
        turn(tool_block("symbols", {"path": "pkg/widget.py"}),
             usage=SimpleNamespace(input_tokens=1000, output_tokens=50,
                                   cache_creation_input_tokens=800,
                                   cache_read_input_tokens=0)),
        turn(text_block("done"),
             usage=SimpleNamespace(input_tokens=200, output_tokens=30,
                                   cache_creation_input_tokens=0,
                                   cache_read_input_tokens=800)),
    ]
    result, _ = run(repo, script)
    usage = result.usage
    assert usage.api_calls == 2
    assert usage.input_tokens == 1200
    assert usage.output_tokens == 80
    assert usage.cache_creation_input_tokens == 800
    assert usage.cache_read_input_tokens == 800
    assert usage.cache_hit_ratio == pytest.approx(800 / 2800)


def test_usage_tolerates_a_response_without_cache_fields():
    usage = explore.Usage()
    usage.add(SimpleNamespace(input_tokens=10, output_tokens=5))
    assert usage.cache_creation_input_tokens == 0
    assert usage.cost_usd() > 0


def test_cost_prices_cache_reads_far_below_fresh_input():
    fresh = explore.Usage(input_tokens=100_000, api_calls=1)
    cached = explore.Usage(cache_read_input_tokens=100_000, api_calls=1)
    assert cached.cost_usd() == pytest.approx(fresh.cost_usd() * 0.10)


def test_cost_uses_the_named_models_rates():
    usage = explore.Usage(input_tokens=1_000_000, output_tokens=0)
    assert usage.cost_usd("claude-haiku-4-5") == pytest.approx(1.00)
    assert usage.cost_usd("claude-sonnet-4-6") == pytest.approx(3.00)
    assert usage.cost_usd("some-unknown-model") == 0.0


def test_the_loop_uses_haiku_by_default(repo):
    # CLAUDE.md: never Sonnet in a loop.
    _, client = run(repo, [turn(text_block("done"))])
    assert client.requests[0]["model"] == "claude-haiku-4-5"
    assert explore.MODEL == "claude-haiku-4-5"


def test_seconds_are_recorded(repo):
    result, _ = run(repo, [turn(text_block("done"))])
    assert result.seconds >= 0.0


# ── the request the harness builds ────────────────────────────────────────────


def test_six_tools_are_offered_and_repo_path_is_not_among_their_arguments(repo):
    _, client = run(repo, [turn(text_block("done"))])
    offered = client.requests[0]["tools"]
    assert [t["name"] for t in offered] == list(explore.TOOL_NAMES)
    assert len(offered) == 6
    for schema in offered:
        # The checkout is injected, never model-supplied: a tool cannot be aimed
        # at another repository.
        assert "repo_path" not in schema["input_schema"]["properties"]


def test_the_report_tool_is_appended_after_the_six(repo):
    _, client = run(repo, [turn(text_block("x"))], report=REPORT)
    names = [t["name"] for t in client.requests[0]["tools"]]
    assert names == [*explore.TOOL_NAMES, "submit_survey"]


def test_tool_order_is_stable_across_calls(repo):
    # Tools render first in the cached prefix, so reordering them would
    # invalidate the cache on every request.
    _, client = run(repo, [
        turn(tool_block("symbols", {"path": "pkg/widget.py"})),
        turn(text_block("done")),
    ])
    assert client.requests[0]["tools"] == client.requests[1]["tools"]


def test_every_tool_schema_is_well_formed():
    for schema in explore.TOOL_SCHEMAS:
        assert schema["name"] in explore.TOOL_NAMES
        assert len(schema["description"]) > 40, schema["name"]
        assert schema["input_schema"]["type"] == "object"
        for name, prop in schema["input_schema"]["properties"].items():
            assert "type" in prop, (schema["name"], name)


def test_declared_tools_match_the_dispatch_table():
    assert set(explore.TOOL_NAMES) == set(explore.tools.TOOLS)


def test_neighbor_relation_enum_tracks_the_implementation():
    schema = next(s for s in explore.TOOL_SCHEMAS if s["name"] == "neighbors")
    assert schema["input_schema"]["properties"]["relations"]["items"]["enum"] == list(
        explore.tools.RELATIONS
    )


# ── the cached seed ───────────────────────────────────────────────────────────


def test_the_seed_carries_exactly_one_breakpoint_on_its_last_block(repo):
    blocks = explore.seed_blocks("Do the thing.", build_skeleton(repo))
    marked = [b for b in blocks if "cache_control" in b]
    assert len(marked) == 1
    assert marked[0] is blocks[-1]


def test_the_seed_holds_the_deterministic_inventory(repo):
    blocks = explore.seed_blocks("Do the thing.", build_skeleton(repo))
    text = "\n".join(b["text"] for b in blocks)
    assert "Do the thing." in text
    assert "REPOSITORY INVENTORY" in text
    assert "widget.py" in text            # the subsystem inventory is present
    assert "symbols" in text              # the tool guide is present


def test_the_seed_works_without_a_skeleton():
    blocks = explore.seed_blocks("Do the thing.")
    assert len(blocks) == 2
    assert "cache_control" in blocks[-1]


def test_the_skeleton_brief_lists_every_subsystem(repo):
    skeleton = build_skeleton(repo)
    brief = explore.skeleton_brief(skeleton)
    for name in skeleton.subsystems():
        assert name in brief


def test_the_skeleton_brief_truncates_honestly(repo):
    brief = explore.skeleton_brief(build_skeleton(repo), max_subsystems=1)
    assert "further subsystems" in brief


def test_the_cached_prefix_is_byte_identical_across_turns(repo):
    """H6 depends on this: one changed byte in the prefix costs the whole cache."""
    _, client = run(repo, [
        turn(tool_block("symbols", {"path": "pkg/widget.py"})),
        turn(tool_block("list_files", {}, id="b")),
        turn(text_block("done")),
    ], skeleton=build_skeleton(repo))
    prefixes = [request["system"] for request in client.requests]
    assert prefixes[0] == prefixes[1] == prefixes[2]


def test_the_task_stays_out_of_the_cached_prefix(repo):
    _, client = run(repo, [turn(text_block("done"))], skeleton=build_skeleton(repo))
    request = client.requests[0]
    seed = "\n".join(b["text"] for b in request["system"])
    assert "Describe the widget." not in seed
    assert request["messages"][0]["content"] == "Describe the widget."


def test_breakpoints_never_exceed_the_api_limit(repo):
    """At most 4 cache_control blocks per request — the seed already uses one."""
    counts = []

    def count(request):
        n = sum("cache_control" in b for b in request["system"])
        for message in request["messages"]:
            content = message.get("content")
            if isinstance(content, list):
                n += sum(
                    isinstance(b, dict) and "cache_control" in b for b in content
                )
        counts.append(n)

    client = FakeClient(
        [turn(tool_block("symbols", {"path": "pkg/widget.py"}, id=f"t{i}"))
         for i in range(8)] + [turn(text_block("done"))],
        on_request=count,
    )
    explore.explore(
        client=client, repo_path=repo, instructions="Explore.", task="Go.",
        skeleton=build_skeleton(repo), budget=Budget(max_turns=8),
    )
    assert len(counts) >= 8
    assert max(counts) <= 4, counts


def test_the_conversation_breakpoints_track_the_newest_turns(repo):
    """The breakpoints must follow the conversation, not be stranded at its start.

    A breakpoint more than 20 content blocks behind the end of the prompt is
    outside the lookback window and stops being read, so a fixed early
    breakpoint would silently stop paying off as the loop runs.
    """
    seen = []

    def record(request):
        messages = request["messages"]
        marked = [
            i for i, m in enumerate(messages)
            if isinstance(m.get("content"), list)
            and any(isinstance(b, dict) and "cache_control" in b for b in m["content"])
        ]
        eligible = [
            i for i, m in enumerate(messages)
            if m.get("role") == "user" and isinstance(m.get("content"), list)
        ]
        seen.append((marked, eligible))

    client = FakeClient(
        [turn(tool_block("symbols", {"path": "pkg/widget.py"}, id=f"t{i}"))
         for i in range(5)] + [turn(text_block("done"))],
        on_request=record,
    )
    explore.explore(
        client=client, repo_path=repo, instructions="Explore.", task="Go.",
        budget=Budget(max_turns=5),
    )
    # Once several tool-result turns exist, the breakpoints are exactly the two
    # newest of them — never an older one, never more than two.
    marked, eligible = seen[-1]
    assert len(eligible) >= 3, eligible
    assert marked == sorted(eligible)[-2:], (marked, eligible)


# ── tool-result rendering ─────────────────────────────────────────────────────
#
# Tool output is prompt text, so its shape is a cost decision: source code stays
# readable instead of being JSON-escaped, and nothing is silently dropped.


def test_source_is_rendered_as_numbered_text_not_escaped_json(repo):
    text, summary = explore._render(
        "read_file", explore.tools.read_file(repo, "pkg/support.py")
    )
    assert "\\n" not in text
    assert "def helper" in text
    assert "pkg/support.py" in summary


def test_an_outline_render_keeps_the_hint(repo, tmp_path):
    big = tmp_path / "pkg" / "big.py"
    big.write_text(
        "\n".join(f"def fn_{i}():\n    return {i}\n" for i in range(300)),
        encoding="utf-8",
    )
    build_skeleton.cache_clear()
    text, _ = explore._render("read_file", explore.tools.read_file(repo, "pkg/big.py"))
    assert "outline only" in text
    assert "Re-read with start/end" in text


def test_an_error_render_names_the_code(repo):
    text, summary = explore._render(
        "read_file", explore.tools.read_file(repo, "pkg/ghost.py")
    )
    assert text.startswith("error: not_found")
    assert "not_found" in summary


def test_search_render_states_the_total_beyond_what_is_shown(repo):
    result = explore.tools.search_code(repo, "e", max_results=1)
    text, _ = explore._render("search_code", result)
    assert str(result["total"]) in text
    assert "showing 1" in text


def test_neighbor_render_flags_the_approximate_relation(repo):
    # `helper` is defined in support.py and referenced from widget.py, so this
    # exercises the one relation the tool layer cannot promise is exact.
    result = explore.tools.neighbors(repo, "helper", relations=["references"])
    assert result["total"] > 0, result
    text, _ = explore._render("neighbors", result)
    assert "name-based, verify by reading" in text


def test_neighbor_render_does_not_flag_exact_relations(repo):
    text, _ = explore._render(
        "neighbors", explore.tools.neighbors(repo, "Widget", relations=["defines"])
    )
    assert "name-based" not in text


def test_every_tool_renders_without_crashing(repo):
    calls = [
        ("list_files", {}),
        ("read_file", {"path": "pkg/widget.py"}),
        ("search_code", {"pattern": "helper"}),
        ("symbols", {"path": "pkg/widget.py"}),
        ("neighbors", {"symbol": "Widget"}),
        ("propose_anchor", {"file": "pkg/widget.py", "symbol": "Widget.spin"}),
    ]
    for name, kwargs in calls:
        text, summary = explore._render(name, explore.tools.run_tool(name, repo, **kwargs))
        assert text and summary, name


# ── conventions ───────────────────────────────────────────────────────────────


def test_a_budget_notice_is_issued_once_near_the_end(repo):
    script = [turn(tool_block("symbols", {"path": f"pkg/widget.py"}, id=f"t{i}"),
                   tool_block("read_file", {"path": "pkg/support.py", "start": 1, "end": i + 1},
                              id=f"u{i}"))
              for i in range(8)]
    client = FakeClient(script + [turn(text_block("done"))])
    explore.explore(
        client=client, repo_path=repo, instructions="i", task="t",
        report=REPORT, budget=Budget(max_turns=8),
    )
    notices = [
        b["text"]
        for request in client.requests
        for m in request["messages"] if isinstance(m.get("content"), list)
        for b in m["content"]
        if isinstance(b, dict) and b.get("type") == "text" and "[budget]" in b.get("text", "")
    ]
    # Deduplicate: the same conversation is resent every turn.
    assert len(set(notices)) == 1
    assert "2 of 8 turns remain" in notices[0]


def test_no_budget_notice_without_a_report_spec(repo):
    script = [turn(tool_block("symbols", {"path": "pkg/widget.py"}, id=f"t{i}"))
              for i in range(6)]
    client = FakeClient(script + [turn(text_block("done"))])
    explore.explore(client=client, repo_path=repo, instructions="i", task="t",
                    budget=Budget(max_turns=6))
    all_text = str(client.requests[-1]["messages"])
    assert "[budget]" not in all_text


def test_explore_never_raises_whatever_the_client_does(repo):
    class Hostile:
        messages = SimpleNamespace(create=lambda **kw: (_ for _ in ()).throw(KeyError("x")))

    result = explore.explore(
        client=Hostile(), repo_path=repo, instructions="i", task="t",
    )
    assert isinstance(result, Exploration)
    assert result.stop_reason == explore.API_ERROR


def test_a_missing_repository_is_an_error_result_not_a_crash(tmp_path):
    result, _ = run(str(tmp_path / "not-cloned"), [
        turn(tool_block("list_files", {})),
        turn(text_block("nothing here")),
    ])
    assert result.stop_reason == explore.ANSWERED
    assert result.trace[0].result_chars > 0


def test_only_the_explorer_stack_drives_the_harness():
    """The harness is driven through investigation/survey; agents that have not
    migrated (Teaching, Grader, Mutator) must not reach it directly."""
    import subprocess
    hits = subprocess.run(
        ["git", "grep", "-l", "repo.explore", "--",
         "backend/agents/teaching", "backend/agents/grader",
         "backend/agents/mentor/mutator.py"],
        capture_output=True, text=True,
    )
    assert hits.stdout.strip() == "", hits.stdout
