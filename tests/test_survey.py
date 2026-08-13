"""
Pytest tests for Layer B — the repository survey and its coverage contract
(Stage 2, backend/repo/survey.py and backend/repo/metrics.py).
Run with: uv run pytest tests/test_survey.py -v

Layer B itself is on trial under H1. The coverage contract is not: whatever the
survey turns out to be, the account it produces is validated against the
deterministic skeleton inventory by our code (D13). So the bulk of these tests
pin down the validator — that silent omission fails, that a reasoned skip passes,
that an unresolvable citation fails, and that a rejection sends the model back to
gather more within the same budget.

No network: the survey is driven through a scripted fake client.
"""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.repo import explore, metrics, survey
from backend.repo.explore import Budget
from backend.repo.skeleton import build_skeleton

# ── a checkout with a shape worth surveying ───────────────────────────────────
#
# Two subdirectory subsystems plus root modules, so the inventory has more than
# one kind of entry and name matching is actually exercised.

FILES = {
    "src/demo/__init__.py": "from .app import App\n",
    "src/demo/app.py": (
        "from .core.engine import Engine\n"
        "\n\n"
        "class App:\n"
        "    def run(self):\n"
        "        return Engine().start()\n"
    ),
    "src/demo/core/__init__.py": "",
    "src/demo/core/engine.py": (
        "class Engine:\n"
        "    def start(self):\n"
        "        return 1\n"
    ),
    "src/demo/core/util.py": "def helper():\n    return 2\n",
    "src/demo/plugins/__init__.py": "",
    "src/demo/plugins/base.py": (
        "class Plugin:\n"
        "    def apply(self):\n"
        "        raise NotImplementedError\n"
    ),
    "tests/test_app.py": "def test_run():\n    assert True\n",
}


def _write(root: Path, files: dict[str, str]) -> str:
    for relative, body in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    build_skeleton.cache_clear()
    return str(root)


@pytest.fixture
def repo(tmp_path: Path) -> str:
    """The clean shape: source root resolves, so subsystems are short names."""
    return _write(tmp_path, FILES)


@pytest.fixture
def collapsed_repo(tmp_path: Path) -> str:
    """The OQ7 wart: a stray top-level module collapses the source root to "",
    so the inventory spells every subsystem as a full path."""
    return _write(
        tmp_path,
        {**FILES, "setup.py": "from setuptools import setup\n\nsetup(name='demo')\n"},
    )


@pytest.fixture
def skeleton(repo):
    return build_skeleton(repo)


def full_payload(skeleton) -> dict:
    """A survey that satisfies the contract, built from the real inventory."""
    inventory = skeleton.subsystems()
    return {
        "architecture": "A small demo application with a core engine and plugins.",
        "subsystems": [
            {
                "name": name,
                "responsibility": f"Handles the {name} concern.",
                "key_file": files[0],
            }
            for name, files in inventory.items()
        ],
        "skipped": [],
        "entry_points": [
            {"file": "src/demo/app.py", "symbol": "App.run",
             "what_it_starts": "the application"},
        ],
        "core_abstractions": [
            {"file": "src/demo/core/engine.py", "symbol": "Engine", "role": "does the work"},
        ],
        "flows": [
            {"name": "startup", "steps": [
                {"file": "src/demo/app.py", "symbol": "App.run", "what_happens": "entry"},
                {"file": "src/demo/core/engine.py", "symbol": "Engine.start",
                 "what_happens": "work"},
            ]},
        ],
        "boundaries": [
            {"file": "src/demo/plugins/base.py", "symbol": "Plugin", "kind": "extension_point",
             "note": "subclass to extend"},
        ],
        "testing_posture": "pytest under tests/",
        "docs": [],
    }


# ── the coverage contract ─────────────────────────────────────────────────────


def test_a_complete_survey_passes(skeleton):
    check = survey.validate_survey(skeleton, full_payload(skeleton))
    assert check.ok, check.gap_message()
    assert check.coverage.complete
    assert check.coverage.unaccounted == []
    assert check.grounding_accuracy == 1.0


def test_a_silently_omitted_subsystem_fails(skeleton):
    payload = full_payload(skeleton)
    dropped = payload["subsystems"].pop()
    check = survey.validate_survey(skeleton, payload)
    assert not check.ok
    assert dropped["name"] in check.coverage.unaccounted
    assert dropped["name"] in check.gap_message()


def test_a_reasoned_skip_is_accounted_for(skeleton):
    payload = full_payload(skeleton)
    moved = payload["subsystems"].pop()
    payload["skipped"].append(
        {"name": moved["name"], "reason": "packaging scaffolding, not library code"}
    )
    check = survey.validate_survey(skeleton, payload)
    assert check.ok
    assert moved["name"] in check.coverage.skipped_with_reason
    assert moved["name"] not in check.coverage.covered


def test_a_skip_without_a_reason_is_not_a_skip(skeleton):
    payload = full_payload(skeleton)
    moved = payload["subsystems"].pop()
    payload["skipped"].append({"name": moved["name"], "reason": "   "})
    check = survey.validate_survey(skeleton, payload)
    assert not check.ok
    assert moved["name"] in check.coverage.unaccounted


def test_an_empty_survey_accounts_for_nothing(skeleton):
    check = survey.validate_survey(skeleton, {})
    assert not check.ok
    assert len(check.coverage.unaccounted) == len(skeleton.subsystems())
    assert check.coverage.covered_ratio == 0.0


def test_covering_everything_by_skipping_everything_is_visible_not_hidden(skeleton):
    """RK10: vacuous coverage passes the contract — and must be measurable.

    D13 stops a subsystem *disappearing*; it deliberately does not judge whether
    a skip was reasonable (H7 decides whether a floor is needed, from data). What
    the contract must not do is make the difference invisible.
    """
    inventory = skeleton.subsystems()
    payload = full_payload(skeleton)
    payload["subsystems"] = []
    payload["skipped"] = [
        {"name": name, "reason": "not interesting"} for name in inventory
    ]
    check = survey.validate_survey(skeleton, payload)
    assert check.ok                                  # the contract is satisfied...
    assert check.coverage.covered_ratio == 0.0       # ...and the vacuity is legible
    assert len(check.coverage.skipped_with_reason) == len(inventory)


def test_a_vacuous_entry_is_rejected(skeleton):
    payload = full_payload(skeleton)
    payload["subsystems"][0]["responsibility"] = "  "
    check = survey.validate_survey(skeleton, payload)
    assert not check.ok
    assert check.vacuous


def test_a_representative_file_from_the_wrong_subsystem_is_rejected(skeleton):
    payload = full_payload(skeleton)
    assert "core" in skeleton.subsystems(), skeleton.subsystems()
    target = next(
        entry for entry in payload["subsystems"] if entry["name"] == "core"
    )
    target["key_file"] = "src/demo/plugins/base.py"
    check = survey.validate_survey(skeleton, payload)
    assert not check.ok
    assert any("core" in m for m in check.misfiled)
    assert "does not belong" in check.gap_message()


def test_an_invented_file_is_rejected(skeleton):
    payload = full_payload(skeleton)
    payload["subsystems"][0]["key_file"] = "src/demo/teleporter.py"
    check = survey.validate_survey(skeleton, payload)
    assert not check.ok
    assert check.misfiled


# ── name matching ─────────────────────────────────────────────────────────────


def test_subsystem_names_match_despite_reasonable_spelling(skeleton):
    payload = full_payload(skeleton)
    for entry in payload["subsystems"]:
        if entry["name"] == "core":
            entry["name"] = "src/demo/core/"        # prefixed and trailing slash
        elif entry["name"] == "plugins":
            entry["name"] = "Plugins"               # different case
    check = survey.validate_survey(skeleton, payload)
    assert check.ok, check.gap_message()
    assert {"core", "plugins"} <= set(check.coverage.covered)


def test_a_root_module_matches_by_basename(collapsed_repo):
    # Under the OQ7 wart the inventory spells subsystems as full paths
    # ("src/demo/core", "src/demo/app.py"); a model writing the short name it can
    # see in the file listing must still match.
    collapsed = build_skeleton(collapsed_repo)
    inventory = collapsed.subsystems()
    assert any("/" in name for name in inventory), inventory   # the wart is present
    payload = full_payload(collapsed)
    renamed = {}
    for entry in payload["subsystems"]:
        short = entry["name"].rsplit("/", 1)[-1]
        renamed[short] = entry["name"]
        entry["name"] = short
    check = survey.validate_survey(collapsed, payload)
    assert check.ok, check.gap_message()
    assert set(check.coverage.covered) == set(inventory)


def test_an_unknown_name_is_reported_and_covers_nothing(skeleton):
    payload = full_payload(skeleton)
    payload["subsystems"][0]["name"] = "authentication"
    check = survey.validate_survey(skeleton, payload)
    assert not check.ok
    assert "authentication" in check.coverage.unknown
    assert len(check.coverage.unaccounted) == 1


def test_ambiguous_names_are_refused_rather_than_guessed():
    """Two subsystems folding to one key must not let a wrong match score.

    Coverage credited to the wrong subsystem is worse than a reported gap: the
    contract would pass while a subsystem really had disappeared.
    """
    from backend.repo.skeleton import Skeleton

    synthetic = Skeleton.from_chunks([
        {"file": "a/thing/x.py", "start_line": 1, "end_line": 2,
         "type": "function", "name": "f", "role": "source"},
        {"file": "b/thing/y.py", "start_line": 1, "end_line": 2,
         "type": "function", "name": "g", "role": "source"},
    ])
    index = survey._name_index(synthetic.subsystems())
    assert "thing" not in index


def test_normalisation_folds_separators_case_and_suffix():
    assert survey._normalize("Src\\Demo\\Core") == "src/demo/core"
    assert survey._normalize("routing.py") == "routing"
    assert survey._normalize("  security/  ") == "security"


# ── anchors ───────────────────────────────────────────────────────────────────


def test_an_unresolvable_citation_is_rejected(skeleton):
    payload = full_payload(skeleton)
    payload["core_abstractions"].append(
        {"file": "src/demo/core/engine.py", "symbol": "Engine.teleport", "role": "invented"}
    )
    check = survey.validate_survey(skeleton, payload)
    assert not check.ok
    assert any("Engine.teleport" in m for m in check.unresolved_anchors)
    assert check.grounding_accuracy < 1.0


def test_an_incomplete_citation_is_rejected(skeleton):
    payload = full_payload(skeleton)
    payload["entry_points"].append({"file": "src/demo/app.py", "symbol": "",
                                    "what_it_starts": "nothing"})
    check = survey.validate_survey(skeleton, payload)
    assert not check.ok
    assert any("incomplete" in m for m in check.unresolved_anchors)


def test_every_anchor_bearing_field_is_checked(skeleton):
    payload = full_payload(skeleton)
    payload["subsystems"][0]["key_symbol"] = "NotAThing"
    cited = survey.cited_anchors(payload)
    places = {where.split(":")[0] for where, _, _ in cited}
    assert {"entry_point", "core_abstraction", "boundary", "flow", "subsystem"} <= places
    assert not survey.validate_survey(skeleton, payload).ok


def test_a_flow_step_anchor_is_checked(skeleton):
    payload = full_payload(skeleton)
    payload["flows"][0]["steps"][1]["symbol"] = "Engine.nope"
    check = survey.validate_survey(skeleton, payload)
    assert not check.ok
    assert any("flow:startup" in m for m in check.unresolved_anchors)


# ── the gap message ───────────────────────────────────────────────────────────


def test_the_gap_message_names_what_is_missing_and_not_the_answer(skeleton):
    payload = full_payload(skeleton)
    dropped = next(e for e in payload["subsystems"] if e["name"] == "core")
    payload["subsystems"] = [e for e in payload["subsystems"] if e["name"] != "core"]
    message = survey.validate_survey(skeleton, payload).gap_message()

    assert "core" in message                       # says what is unaccounted for...
    assert dropped["responsibility"] not in message  # ...but never what to write
    assert dropped["key_file"] not in message
    assert "Engine" not in message


def test_the_gap_message_bounds_a_long_list(skeleton):
    message = survey.validate_survey(skeleton, {}).gap_message()
    assert len(message) < 1200
    required = len(skeleton.subsystems())
    if required > survey.MAX_NAMED_GAPS:
        assert "more" in message


def test_the_gap_message_is_never_empty(skeleton):
    assert survey.validate_survey(skeleton, {"subsystems": []}).gap_message().strip()


# ── the validator as an explore() hook ────────────────────────────────────────


def test_the_validator_accepts_by_returning_none(skeleton):
    validator = survey.SurveyValidator(skeleton)
    assert validator(full_payload(skeleton)) is None
    assert validator.first is not None and validator.first.ok


def test_the_validator_returns_the_gap_and_remembers_every_attempt(skeleton):
    validator = survey.SurveyValidator(skeleton)
    broken = full_payload(skeleton)
    broken["subsystems"].pop()
    assert validator(broken) is not None
    assert validator(full_payload(skeleton)) is None
    assert len(validator.attempts) == 2
    assert not validator.first.ok and validator.last.ok


def test_enforcement_can_be_disabled_for_a_control_arm(skeleton):
    validator = survey.SurveyValidator(skeleton, enforce=False)
    assert validator({}) is None            # accepted...
    assert not validator.first.ok           # ...but still measured


# ── the contract drives the loop ──────────────────────────────────────────────


def text_block(text):
    return SimpleNamespace(type="text", text=text)


def tool_block(name, arguments, id="tu_1"):
    return SimpleNamespace(type="tool_use", id=id, name=name, input=arguments)


def turn(*blocks):
    stop = "tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn"
    return SimpleNamespace(
        content=list(blocks), stop_reason=stop,
        usage=SimpleNamespace(input_tokens=100, output_tokens=50,
                              cache_creation_input_tokens=0, cache_read_input_tokens=0),
    )


class FakeClient:
    def __init__(self, script):
        self.script = list(script)
        self.requests = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.requests.append(copy.deepcopy(kwargs))
        if not self.script:
            return turn(text_block("script exhausted"))
        return self.script.pop(0)


def test_a_rejected_survey_sends_the_model_back_within_the_same_budget(repo, skeleton):
    incomplete = full_payload(skeleton)
    incomplete["subsystems"].pop()
    client = FakeClient([
        turn(tool_block("submit_survey", incomplete, id="r1")),
        turn(tool_block("symbols", {"path": "src/demo/core/engine.py"}, id="s1")),
        turn(tool_block("submit_survey", full_payload(skeleton), id="r2")),
    ])
    run = survey.run_survey(client=client, repo_path=repo, skeleton=skeleton,
                            budget=Budget(max_turns=6))
    assert run.accepted
    assert run.exploration.stop_reason == explore.REPORTED
    assert len(run.exploration.rejections) == 1
    assert len(run.validator.attempts) == 2
    # The gap came back as an error result, so the model had to act on it.
    rejection = client.requests[1]["messages"][2]["content"][0]
    assert rejection["is_error"] is True
    assert "neither described nor skipped" in rejection["content"]


def test_a_survey_salvaged_at_the_budget_is_returned_but_not_counted_as_passing(
    repo, skeleton
):
    """§5.4: exhaustion accepts a partial report with an explicit gap.

    Returning it is right; scoring it as a pass would report exactly the silent
    incompleteness D13 exists to prevent.
    """
    incomplete = full_payload(skeleton)
    dropped = incomplete["subsystems"].pop()
    client = FakeClient([
        turn(tool_block("submit_survey", incomplete, id=f"r{i}")) for i in range(6)
    ])
    run = survey.run_survey(client=client, repo_path=repo, skeleton=skeleton,
                            budget=Budget(max_turns=3))
    assert run.produced                                  # a report came back...
    assert not run.accepted                              # ...and did not pass
    assert run.exploration.contract_met is False
    assert run.exploration.budget_exhausted

    # The verdict describes the payload actually returned, not a stale attempt.
    assert run.survey == run.exploration.output
    assert run.check is not None and not run.check.ok
    assert dropped["name"] in run.check.coverage.unaccounted
    assert metrics.quality(run).unaccounted == 1


def test_repeated_rejection_cannot_outlast_the_budget(repo, skeleton):
    client = FakeClient([turn(tool_block("submit_survey", {}, id=f"r{i}")) for i in range(50)])
    run = survey.run_survey(client=client, repo_path=repo, skeleton=skeleton,
                            budget=Budget(max_turns=4))
    assert run.exploration.turns <= 5          # 4 turns + one salvage turn
    assert len(run.exploration.rejections) <= 5


def test_the_survey_brief_is_cached_and_the_inventory_rides_with_it(repo, skeleton):
    client = FakeClient([turn(tool_block("submit_survey", full_payload(skeleton), id="r"))])
    survey.run_survey(client=client, repo_path=repo, skeleton=skeleton)
    seed = "\n".join(b["text"] for b in client.requests[0]["system"])
    assert "BREADTH is not optional" in seed
    assert "REPOSITORY INVENTORY" in seed
    assert "core" in seed
    assert "cache_control" in json.dumps(client.requests[0]["system"])


def test_the_survey_asks_for_more_output_room_than_the_default(repo, skeleton):
    client = FakeClient([turn(tool_block("submit_survey", full_payload(skeleton), id="r"))])
    survey.run_survey(client=client, repo_path=repo, skeleton=skeleton)
    assert client.requests[0]["max_tokens"] == survey.SURVEY_MAX_TOKENS
    assert survey.SURVEY_MAX_TOKENS > explore.MAX_TOKENS


# ── experiment variables reach the request ────────────────────────────────────


def test_the_exploration_policy_is_selectable(repo, skeleton):
    for name, guide in explore.TOOL_GUIDES.items():
        client = FakeClient([turn(tool_block("submit_survey", full_payload(skeleton), id="r"))])
        survey.run_survey(client=client, repo_path=repo, skeleton=skeleton, tool_guide=guide)
        seed = "\n".join(b["text"] for b in client.requests[0]["system"])
        assert guide.splitlines()[3] in seed, name


def test_the_structural_policy_asks_for_structure_before_reading():
    guide = explore.TOOL_GUIDE_STRUCTURAL
    assert "Prefer structural navigation" in guide
    # ...but it must stay a policy, not a fixed sequence.
    assert "policy, not a fixed sequence" in guide
    assert "Adapt it" in guide


def test_the_cache_strategy_is_selectable(repo, skeleton):
    for breakpoints in (1, 2):
        client = FakeClient([
            turn(tool_block("symbols", {"path": "src/demo/app.py"}, id="s")),
            turn(tool_block("symbols", {"path": "src/demo/core/engine.py"}, id="s2")),
            turn(tool_block("submit_survey", full_payload(skeleton), id="r")),
        ])
        survey.run_survey(client=client, repo_path=repo, skeleton=skeleton,
                          conversation_breakpoints=breakpoints)
        final = client.requests[-1]
        marked = sum(
            isinstance(b, dict) and "cache_control" in b
            for m in final["messages"] if isinstance(m.get("content"), list)
            for b in m["content"]
        )
        assert marked == breakpoints, breakpoints


def test_the_seed_breakpoint_is_unaffected_by_the_cache_strategy(repo, skeleton):
    for breakpoints in (1, 2):
        client = FakeClient([turn(tool_block("submit_survey", full_payload(skeleton), id="r"))])
        survey.run_survey(client=client, repo_path=repo, skeleton=skeleton,
                          conversation_breakpoints=breakpoints)
        assert sum("cache_control" in b for b in client.requests[0]["system"]) == 1


# ── no repository-specific tuning ─────────────────────────────────────────────


def test_the_brief_names_no_repository_framework_or_expected_subsystem():
    """A gain that comes from naming the answer is not a gain in exploration."""
    corpus = " ".join([
        survey.SURVEY_INSTRUCTIONS, survey.SURVEY_TASK,
        json.dumps(survey.SURVEY_SPEC.input_schema), survey.SURVEY_SPEC.description,
        explore.TOOL_GUIDE_DEFAULT, explore.TOOL_GUIDE_STRUCTURAL,
    ]).lower()
    for banned in (
        "fastapi", "requests", "psf", "starlette", "pydantic", "urllib3", "flask",
        "django", "security/", "routing.py", "sessions.py", "httpadapter",
    ):
        assert banned not in corpus, banned


def test_the_survey_module_contains_no_repository_specific_logic():
    source = Path("backend/repo/survey.py").read_text(encoding="utf-8").lower()
    for banned in ("fastapi", "psf/requests", "starlette", "pydantic"):
        assert banned not in source, banned


def test_the_coverage_contract_is_repository_agnostic(skeleton):
    """It derives entirely from the skeleton, so an unseen repo shape still binds."""
    from backend.repo.skeleton import Skeleton

    odd = Skeleton.from_chunks([
        {"file": "weird/place/one.py", "start_line": 1, "end_line": 3,
         "type": "class", "name": "One", "role": "source"},
        {"file": "weird/place/two.py", "start_line": 1, "end_line": 3,
         "type": "class", "name": "Two", "role": "source"},
    ])
    check = survey.validate_survey(odd, {"subsystems": [], "skipped": []})
    assert check.coverage.unaccounted == list(odd.subsystems())


# ── metrics ───────────────────────────────────────────────────────────────────


def build_run(repo, skeleton, script):
    client = FakeClient(script)
    return survey.run_survey(client=client, repo_path=repo, skeleton=skeleton,
                             budget=Budget(max_turns=8))


def test_behavior_counts_calls_by_tool_and_ignores_the_report(repo, skeleton):
    run = build_run(repo, skeleton, [
        turn(tool_block("symbols", {"path": "src/demo/app.py"}, id="a"),
             tool_block("search_code", {"pattern": "Engine"}, id="b")),
        turn(tool_block("read_file", {"path": "src/demo/core/engine.py"}, id="c")),
        turn(tool_block("submit_survey", full_payload(skeleton), id="r")),
    ])
    stats = metrics.behavior(run.exploration)
    assert stats.tool_calls == 3
    assert stats.calls_by_tool == {"symbols": 1, "search_code": 1, "read_file": 1}
    assert "submit_survey" not in stats.calls_by_tool
    assert stats.structural_calls == 2
    assert stats.read_calls == 1


def test_behavior_measures_the_resolved_extent_of_each_read(repo, skeleton):
    run = build_run(repo, skeleton, [
        turn(tool_block("read_file", {"path": "src/demo/app.py", "start": 4, "end": 6}, id="a")),
        turn(tool_block("submit_survey", full_payload(skeleton), id="r")),
    ])
    stats = metrics.behavior(run.exploration)
    assert stats.source_lines_read == 3
    assert stats.average_read_lines == 3.0
    assert stats.source_chars_read > 0
    assert stats.whole_file_reads == 0


def test_behavior_flags_a_whole_file_read(repo, skeleton):
    run = build_run(repo, skeleton, [
        turn(tool_block("read_file", {"path": "src/demo/core/engine.py"}, id="a")),
        turn(tool_block("submit_survey", full_payload(skeleton), id="r")),
    ])
    stats = metrics.behavior(run.exploration)
    assert stats.whole_file_reads == 1
    assert stats.outline_reads == 0


def test_structural_share_separates_the_two_policies(repo, skeleton):
    reading = build_run(repo, skeleton, [
        turn(*[tool_block("read_file", {"path": "src/demo/app.py"}, id=f"r{i}")
               for i in range(4)]),
        turn(tool_block("submit_survey", full_payload(skeleton), id="r")),
    ])
    structural = build_run(repo, skeleton, [
        turn(tool_block("symbols", {"path": "src/demo/app.py"}, id="s0"),
             tool_block("symbols", {"path": "src/demo/core/engine.py"}, id="s1"),
             tool_block("search_code", {"pattern": "helper"}, id="s2"),
             tool_block("read_file", {"path": "src/demo/app.py", "start": 1, "end": 2}, id="r0")),
        turn(tool_block("submit_survey", full_payload(skeleton), id="r")),
    ])
    assert metrics.behavior(reading.exploration).structural_share == 0.0
    assert metrics.behavior(structural.exploration).structural_share == pytest.approx(0.75)


# ── waste elimination (§0: remove waste, never capability) ────────────────────


def test_an_identical_repeated_call_is_not_re_run(repo, skeleton):
    run = build_run(repo, skeleton, [
        turn(tool_block("read_file", {"path": "src/demo/app.py"}, id="a")),
        turn(tool_block("read_file", {"path": "src/demo/app.py"}, id="b")),
        turn(tool_block("submit_survey", full_payload(skeleton), id="r")),
    ])
    stats = metrics.behavior(run.exploration)
    assert stats.duplicate_calls == 1
    assert stats.read_calls == 1                    # the repeat gathered nothing
    assert run.exploration.trace[1].facts["duplicate_of"] == 1
    assert "duplicate of turn 1" in run.exploration.trace[1].summary


def test_the_duplicate_pointer_costs_a_fixed_trivial_amount(repo, skeleton):
    """The saving scales with the file; the pointer must not.

    On a six-line file a pointer saves almost nothing. The property that matters
    is that its size is constant, so re-reading a 400-line file costs the same
    handful of characters as re-reading a stub.
    """
    run = build_run(repo, skeleton, [
        turn(tool_block("read_file", {"path": "src/demo/app.py"}, id="a")),
        turn(tool_block("read_file", {"path": "src/demo/app.py"}, id="b")),
        turn(tool_block("submit_survey", full_payload(skeleton), id="r")),
    ])
    assert run.exploration.trace[1].result_chars < 100


def test_dedupe_can_be_disabled_so_the_experiment_can_measure_it(repo, skeleton):
    client = FakeClient([
        turn(tool_block("read_file", {"path": "src/demo/app.py"}, id="a")),
        turn(tool_block("read_file", {"path": "src/demo/app.py"}, id="b")),
        turn(tool_block("submit_survey", full_payload(skeleton), id="r")),
    ])
    run = survey.run_survey(client=client, repo_path=repo, skeleton=skeleton,
                            budget=Budget(max_turns=6), dedupe_identical_calls=False)
    stats = metrics.behavior(run.exploration)
    assert stats.duplicate_calls == 0
    assert stats.read_calls == 2                    # both really ran


def test_a_differently_argued_call_is_not_a_duplicate(repo, skeleton):
    run = build_run(repo, skeleton, [
        turn(tool_block("read_file", {"path": "src/demo/app.py", "start": 1, "end": 2}, id="a"),
             tool_block("read_file", {"path": "src/demo/app.py", "start": 4, "end": 6}, id="b")),
        turn(tool_block("submit_survey", full_payload(skeleton), id="r")),
    ])
    assert metrics.behavior(run.exploration).duplicate_calls == 0


def test_overlapping_reads_are_counted_as_repeated_work(repo, skeleton):
    run = build_run(repo, skeleton, [
        turn(tool_block("read_file", {"path": "src/demo/app.py", "start": 1, "end": 6}, id="a")),
        turn(tool_block("read_file", {"path": "src/demo/app.py", "start": 4, "end": 6}, id="b")),
        turn(tool_block("submit_survey", full_payload(skeleton), id="r")),
    ])
    stats = metrics.behavior(run.exploration)
    assert stats.duplicate_calls == 0        # not identical arguments...
    assert stats.overlapping_reads == 1      # ...but the lines were already held
    assert stats.reread_lines == 3
    assert stats.waste_share > 0


def test_non_overlapping_reads_of_one_file_are_not_waste(repo, skeleton):
    run = build_run(repo, skeleton, [
        turn(tool_block("read_file", {"path": "src/demo/app.py", "start": 1, "end": 2}, id="a"),
             tool_block("read_file", {"path": "src/demo/app.py", "start": 4, "end": 6}, id="b")),
        turn(tool_block("submit_survey", full_payload(skeleton), id="r")),
    ])
    assert metrics.behavior(run.exploration).overlapping_reads == 0


# ── did the structural tools narrow anything? ────────────────────────────────


def test_a_structural_call_counts_as_narrowing_when_a_read_follows_it(repo, skeleton):
    run = build_run(repo, skeleton, [
        turn(tool_block("symbols", {"path": "src/demo/core/engine.py"}, id="s")),
        turn(tool_block("read_file", {"path": "src/demo/core/engine.py", "start": 1, "end": 3}, id="r0")),
        turn(tool_block("submit_survey", full_payload(skeleton), id="r")),
    ])
    stats = metrics.behavior(run.exploration)
    assert stats.narrowing_structural_calls == 1
    assert stats.narrowing_share == 1.0


def test_a_structural_call_nobody_acts_on_did_not_narrow(repo, skeleton):
    run = build_run(repo, skeleton, [
        turn(tool_block("symbols", {"path": "src/demo/plugins/base.py"}, id="s")),
        turn(tool_block("read_file", {"path": "src/demo/app.py", "start": 1, "end": 2}, id="r0")),
        turn(tool_block("submit_survey", full_payload(skeleton), id="r")),
    ])
    assert metrics.behavior(run.exploration).narrowing_structural_calls == 0


# ── evidence depth: accounting is not deep reading ────────────────────────────


def test_evidence_depth_distinguishes_reading_from_merely_naming(repo, skeleton):
    run = build_run(repo, skeleton, [
        turn(tool_block("read_file", {"path": "src/demo/core/engine.py", "start": 1, "end": 3}, id="a"),
             tool_block("symbols", {"path": "src/demo/plugins/base.py"}, id="b"),
             tool_block("list_files", {}, id="c")),
        turn(tool_block("submit_survey", full_payload(skeleton), id="r")),
    ])
    depth = metrics.subsystem_evidence(run.exploration, skeleton)
    assert depth["core"] == metrics.READ
    assert depth["plugins"] == metrics.OUTLINED
    # list_files named everything else without opening any of it.
    assert depth["app.py"] == metrics.NAMED


def test_evidence_depth_marks_what_was_never_touched(repo, skeleton):
    run = build_run(repo, skeleton, [
        turn(tool_block("read_file", {"path": "src/demo/core/engine.py", "start": 1, "end": 3}, id="a")),
        turn(tool_block("submit_survey", full_payload(skeleton), id="r")),
    ])
    depth = metrics.subsystem_evidence(run.exploration, skeleton)
    assert depth["core"] == metrics.READ
    assert depth["plugins"] == metrics.UNTOUCHED
    # A survey can claim coverage of something it never opened — and that claim is
    # now visibly weaker than one backed by a read, rather than indistinguishable.
    assert run.check.coverage.covered.get("plugins")


def test_coverage_progression_shows_when_breadth_arrived(repo, skeleton):
    run = build_run(repo, skeleton, [
        turn(tool_block("symbols", {"path": "src/demo/app.py"}, id="a")),
        turn(tool_block("symbols", {"path": "src/demo/core/engine.py"}, id="b")),
        turn(tool_block("submit_survey", full_payload(skeleton), id="r")),
    ])
    progression = metrics.coverage_progression(run.exploration, skeleton)
    assert progression == sorted(progression)     # cumulative, never decreasing
    assert progression[-1] >= 2


# ── reusable knowledge (the Layer B -> Layer C handoff) ───────────────────────


def test_reuse_scores_each_category_by_count_and_stability(repo, skeleton):
    payload = full_payload(skeleton)
    runs = [build_run(repo, skeleton, [turn(tool_block("submit_survey", payload, id="r"))])
            for _ in range(3)]
    scores = metrics.reuse(runs)
    assert scores["entry points"].facts == 1
    assert scores["entry points"].stability == 1.0       # identical every run
    assert scores["entry points"].reusable_facts == 1.0


def test_reuse_discounts_a_category_that_varies_between_runs(repo, skeleton):
    a = full_payload(skeleton)
    b = full_payload(skeleton)
    b["core_abstractions"] = [
        {"file": "src/demo/plugins/base.py", "symbol": "Plugin", "role": "different"}
    ]
    runs = [build_run(repo, skeleton, [turn(tool_block("submit_survey", p, id="r"))])
            for p in (a, b)]
    scores = metrics.reuse(runs)
    assert scores["core abstractions"].stability == 0.0
    assert scores["core abstractions"].reusable_facts == 0.0
    # ...while a category that did agree keeps its full weight.
    assert scores["entry points"].stability == 1.0


def test_quality_reports_coverage_and_both_grounding_numbers(repo, skeleton):
    broken = full_payload(skeleton)
    broken["core_abstractions"].append(
        {"file": "src/demo/core/engine.py", "symbol": "Engine.ghost", "role": "invented"}
    )
    run = build_run(repo, skeleton, [
        turn(tool_block("submit_survey", broken, id="r1")),
        turn(tool_block("submit_survey", full_payload(skeleton), id="r2")),
    ])
    stats = metrics.quality(run)
    assert stats.accepted
    assert stats.rejections == 1
    assert stats.unaccounted == 0
    assert stats.covered == len(skeleton.subsystems())
    assert stats.first_grounding < 1.0        # the informative number
    assert stats.final_grounding == 1.0       # true by construction once accepted
    assert stats.widest_flow_files == 2


def test_quality_records_skip_reasons_without_judging_them(repo, skeleton):
    payload = full_payload(skeleton)
    moved = payload["subsystems"].pop()
    payload["skipped"].append({"name": moved["name"], "reason": "generated file"})
    run = build_run(repo, skeleton, [turn(tool_block("submit_survey", payload, id="r"))])
    stats = metrics.quality(run)
    assert stats.skipped == 1
    assert stats.skip_reasons == ["generated file"]      # recorded (M1c), not scored
    assert stats.covered_ratio < 1.0


def test_cost_reports_the_uncached_counterfactual(repo, skeleton):
    run = build_run(repo, skeleton, [turn(tool_block("submit_survey", full_payload(skeleton), id="r"))])
    run.exploration.usage = explore.Usage(
        input_tokens=1000, output_tokens=500,
        cache_creation_input_tokens=10_000, cache_read_input_tokens=40_000, api_calls=3,
    )
    stats = metrics.cost(run.exploration, explore.MODEL)
    assert stats.prompt_tokens == 51_000
    assert stats.cache_hit_rate == pytest.approx(40_000 / 51_000)
    assert stats.uncached_cost_usd > stats.cost_usd
    assert stats.caching_saved_usd > 0


def test_cost_can_show_caching_losing(repo, skeleton):
    """Writes bill at 1.25x, so write-heavy caching can cost more than not caching."""
    run = build_run(repo, skeleton, [turn(tool_block("submit_survey", full_payload(skeleton), id="r"))])
    run.exploration.usage = explore.Usage(
        cache_creation_input_tokens=50_000, cache_read_input_tokens=0, api_calls=1,
    )
    stats = metrics.cost(run.exploration, explore.MODEL)
    assert stats.caching_saved_usd < 0


def test_consistency_scores_agreement_across_repeats(repo, skeleton):
    runs = [
        build_run(repo, skeleton, [turn(tool_block("submit_survey", full_payload(skeleton), id="r"))])
        for _ in range(3)
    ]
    stats = metrics.consistency(runs, explore.MODEL)
    assert stats.runs == 3
    assert stats.covered_overlap == 1.0
    assert stats.anchor_overlap == 1.0


def test_consistency_notices_disagreement(repo, skeleton):
    same = full_payload(skeleton)
    different = full_payload(skeleton)
    different["core_abstractions"] = [
        {"file": "src/demo/plugins/base.py", "symbol": "Plugin", "role": "other"}
    ]
    runs = [
        build_run(repo, skeleton, [turn(tool_block("submit_survey", p, id="r"))])
        for p in (same, different)
    ]
    assert metrics.consistency(runs, explore.MODEL).anchor_overlap < 1.0


def test_a_row_serialises_for_the_results_file(repo, skeleton):
    run = build_run(repo, skeleton, [turn(tool_block("submit_survey", full_payload(skeleton), id="r"))])
    row = metrics.row("demo", "default", "two", run, explore.MODEL)
    payload = row.as_dict()
    assert json.loads(json.dumps(payload))       # must round-trip
    assert payload["quality"]["unaccounted"] == 0
    assert "structural_share" in payload["behavior"]
    assert "cache_hit_rate" in payload["cost"]


# ── Layer B stays out of production ───────────────────────────────────────────


def test_not_yet_migrated_agents_stay_off_layer_b():
    """The integration boundary is the Mentor (user-approved, 2026-08-13).

    The explorer pipeline consumes the Survey by design; the agents that have
    not migrated must not.
    """
    import subprocess

    hits = subprocess.run(
        ["git", "grep", "-l", "-E", r"repo\.(survey|explore|metrics)",
         "--",
         "backend/agents/teaching", "backend/agents/grader",
         "backend/agents/mentor/mutator.py"],
        capture_output=True, text=True,
    )
    assert hits.stdout.strip() == "", hits.stdout


def test_the_mentor_has_no_retrieval_branch_left():
    """Stage 5 inverted this guard: the baseline is gone, so it must be gone."""
    source = Path("backend/agents/mentor/agent.py").read_text(encoding="utf-8")
    assert "retrieve_chunks" not in source
    assert "backend.rag" not in source
