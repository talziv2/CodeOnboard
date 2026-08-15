"""
Pytest tests for Layer C — Goal Investigation (Stage 3, backend/repo/investigation.py).
Run with: uv run pytest tests/test_investigation.py -v

What must hold: anchors in a dossier resolve or the dossier is rejected; exit
criteria vary by goal type and catch the premature stop; the survey seeds the
exploration but never becomes evidence; the chunk-shape shim hands the existing
Mentor only verified source; nothing here is wired into production.

No network: scripted fake client throughout.
"""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.repo import explore, investigation
from backend.repo.explore import Budget
from backend.repo.skeleton import build_skeleton

# ── a checkout with enough shape for a real investigation ─────────────────────

FILES = {
    "src/app/__init__.py": "from .client import fetch\n",
    "src/app/client.py": (
        "from .auth import sign\n"
        "from .transport import send\n"
        "\n\n"
        "def fetch(url, credentials=None):\n"
        "    request = {'url': url}\n"
        "    if credentials:\n"
        "        request = sign(request, credentials)\n"
        "    return send(request)\n"
    ),
    "src/app/auth.py": (
        "class Signer:\n"
        "    def apply(self, request):\n"
        "        request['signed'] = True\n"
        "        return request\n"
        "\n\n"
        "def sign(request, credentials):\n"
        "    return Signer().apply(request)\n"
    ),
    "src/app/transport.py": (
        "def send(request):\n"
        "    return {'status': 200, 'request': request}\n"
    ),
    "tests/test_client.py": (
        "from src.app.client import fetch\n"
        "\n\n"
        "def test_fetch():\n"
        "    assert fetch('http://x')['status'] == 200\n"
    ),
}

GOAL = {
    "primary_goal": "understand how requests are signed",
    "goal_type": "understand_component",
    "focus_area": "authentication",
    "code_depth": "working",
}


@pytest.fixture
def repo(tmp_path: Path) -> str:
    for relative, body in FILES.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    build_skeleton.cache_clear()
    return str(tmp_path)


@pytest.fixture
def skeleton(repo):
    return build_skeleton(repo)


def full_dossier() -> dict:
    """A dossier that satisfies understand_component criteria on the fixture."""
    return {
        "understanding": "Signing wraps each outgoing request via Signer before transport.",
        "components": [
            {"file": "src/app/auth.py", "symbol": "Signer",
             "role_in_goal": "applies the signature", "why_it_matters": "it is the mechanism"},
            {"file": "src/app/auth.py", "symbol": "sign",
             "role_in_goal": "public signing entry", "why_it_matters": "callers use this"},
            {"file": "src/app/client.py", "symbol": "fetch",
             "role_in_goal": "decides when signing happens", "why_it_matters": "the trigger"},
            {"file": "src/app/transport.py", "symbol": "send",
             "role_in_goal": "consumes the signed request", "why_it_matters": "downstream contract"},
        ],
        "entry_points": [
            {"file": "src/app/client.py", "symbol": "fetch",
             "how_it_enters": "the public API call"},
        ],
        "flows": [
            {"name": "signed fetch", "steps": [
                {"file": "src/app/client.py", "symbol": "fetch", "what_happens": "receives credentials"},
                {"file": "src/app/auth.py", "symbol": "sign", "what_happens": "wraps request"},
                {"file": "src/app/auth.py", "symbol": "Signer.apply", "what_happens": "marks signed"},
                {"file": "src/app/transport.py", "symbol": "send", "what_happens": "transmits"},
            ]},
        ],
        "relationships": [
            {"from_file": "src/app/client.py", "from_symbol": "fetch",
             "to_file": "src/app/auth.py", "to_symbol": "sign",
             "kind": "calls", "note": "only when credentials given"},
            {"from_file": "src/app/auth.py", "from_symbol": "sign",
             "to_file": "src/app/auth.py", "to_symbol": "Signer",
             "kind": "constructs", "note": "one per call"},
        ],
        "contracts": [
            {"file": "src/app/auth.py", "symbol": "Signer.apply",
             "contract": "takes and returns a request dict; sets 'signed'"},
        ],
        "prerequisites": [
            {"concept": "request lifecycle", "why_needed": "signing happens mid-flight",
             "file": "src/app/client.py", "symbol": "fetch"},
            {"concept": "credential handling", "why_needed": "explains the optional path"},
        ],
        "evidence_refs": [
            {"path": "tests/test_client.py", "clarifies": "the unsigned default path"},
        ],
        "context": ["transport is a stub in this fixture"],
        "open_questions": [
            {"question": "how are credentials stored", "why_it_matters": "not in this repo"},
        ],
    }


# ── validation: anchors ───────────────────────────────────────────────────────


def test_a_complete_dossier_passes(skeleton):
    check = investigation.validate_dossier(skeleton, GOAL, full_dossier())
    assert check.ok, check.gap_message()
    assert check.grounding_accuracy == 1.0
    assert check.total_anchors >= 13


def test_an_unresolvable_component_is_rejected(skeleton):
    payload = full_dossier()
    payload["components"][0]["symbol"] = "Teleporter"
    check = investigation.validate_dossier(skeleton, GOAL, payload)
    assert not check.ok
    assert any("Teleporter" in m for m in check.unresolved_anchors)


def test_a_bad_flow_step_is_rejected(skeleton):
    payload = full_dossier()
    payload["flows"][0]["steps"][1]["file"] = "src/app/ghost.py"
    check = investigation.validate_dossier(skeleton, GOAL, payload)
    assert not check.ok
    assert any("flow:signed fetch" in m for m in check.unresolved_anchors)


def test_relationship_endpoints_are_both_checked(skeleton):
    payload = full_dossier()
    payload["relationships"][0]["to_symbol"] = "sign_everything"
    check = investigation.validate_dossier(skeleton, GOAL, payload)
    assert not check.ok
    assert any("relationship_to" in m for m in check.unresolved_anchors)


def test_a_prerequisite_without_an_anchor_is_legal(skeleton):
    payload = full_dossier()
    # "credential handling" has no file/symbol — concepts may be unanchored.
    check = investigation.validate_dossier(skeleton, GOAL, payload)
    assert check.ok


def test_a_prerequisite_with_a_bad_anchor_is_not(skeleton):
    payload = full_dossier()
    payload["prerequisites"][0]["symbol"] = "nope"
    check = investigation.validate_dossier(skeleton, GOAL, payload)
    assert not check.ok


def test_a_vacuous_component_is_rejected(skeleton):
    payload = full_dossier()
    payload["components"][0]["why_it_matters"] = "  "
    check = investigation.validate_dossier(skeleton, GOAL, payload)
    assert not check.ok
    assert check.vacuous


# ── validation: goal-typed exit criteria ──────────────────────────────────────


def test_the_premature_stop_is_caught(skeleton):
    """One plausible flow and nothing else is exactly the failure mode §5.5 names."""
    thin = {
        "understanding": "It signs requests.",
        "components": [full_dossier()["components"][0]],
        "entry_points": [],
        "flows": [{"name": "f", "steps": full_dossier()["flows"][0]["steps"][:2]}],
        "relationships": [],
        "contracts": [],
        "prerequisites": [],
        "evidence_refs": [],
        "context": [],
        "open_questions": [],
    }
    check = investigation.validate_dossier(skeleton, GOAL, thin)
    assert not check.ok
    joined = " ".join(check.unmet_criteria)
    assert "component" in joined
    assert "entry point" in joined
    assert "relationship" in joined


def test_criteria_vary_by_goal_type(skeleton):
    payload = full_dossier()
    # understand_component demands a contract; debug_issue does not.
    payload["contracts"] = []
    as_component = investigation.validate_dossier(
        skeleton, {**GOAL, "goal_type": "understand_component"}, payload
    )
    as_debug = investigation.validate_dossier(
        skeleton, {**GOAL, "goal_type": "debug_issue"}, payload
    )
    assert any("contract" in m for m in as_component.unmet_criteria)
    assert not any("contract" in m for m in as_debug.unmet_criteria)


def test_an_unknown_goal_type_falls_back_to_base_criteria(skeleton):
    check = investigation.validate_dossier(
        skeleton, {"goal_type": "something_new"}, full_dossier()
    )
    assert check.ok


def test_a_flow_must_cross_files_not_just_steps(skeleton):
    payload = full_dossier()
    payload["flows"] = [{"name": "one-file", "steps": [
        {"file": "src/app/auth.py", "symbol": "sign", "what_happens": "a"},
        {"file": "src/app/auth.py", "symbol": "Signer", "what_happens": "b"},
        {"file": "src/app/auth.py", "symbol": "Signer.apply", "what_happens": "c"},
    ]}]
    check = investigation.validate_dossier(
        skeleton, {**GOAL, "goal_type": "understand_system"}, payload
    )
    assert any("file" in m for m in check.unmet_criteria)


@pytest.mark.parametrize(
    "field", ["components", "entry_points", "flows", "relationships",
              "contracts", "prerequisites", "evidence_refs", "open_questions"],
)
def test_a_malformed_entry_in_any_field_is_a_rejection_not_a_crash(skeleton, field):
    """The model sometimes emits a bare string where the schema wants an object.

    That must come back as precise feedback the model can act on — never as an
    exception out of the validator, which in production crashed the whole
    goal_investigation node with `'str' object has no attribute 'get'`.
    """
    payload = full_dossier()
    payload[field] = list(payload.get(field) or []) + ["a bare string"]
    check = investigation.validate_dossier(skeleton, GOAL, payload)
    assert not check.ok
    assert any(field in v for v in check.structural), check.structural
    assert field in check.gap_message()


def test_a_malformed_flow_step_is_a_rejection_not_a_crash(skeleton):
    payload = full_dossier()
    payload["flows"][0]["steps"].append("not a step object")
    check = investigation.validate_dossier(skeleton, GOAL, payload)
    assert not check.ok      # surfaces as an incomplete citation
    assert check.gap_message()


def test_a_whole_field_arriving_as_a_string_names_the_real_fault(skeleton):
    """The production failure: the model serialised its array as markup inside
    one string value. Iterating that per-character reported "0 components",
    which describes the wrong problem — the model then resubmitted the same
    broken shape until its budget ran out."""
    payload = full_dossier()
    payload["components"] = "the components are auth.py and client.py"
    check = investigation.validate_dossier(skeleton, GOAL, payload)
    assert not check.ok
    message = check.gap_message()
    assert "`components` arrived as str" in message
    assert "list of objects" in message
    # ...and it must not degenerate into one complaint per character.
    assert len(check.structural) <= 3, check.structural


def test_citing_the_internal_twin_of_an_exported_name_is_rejected(skeleton, repo):
    """The `fastapi-di` defect, as a general rule.

    A package re-exports one definition of a name while another definition of
    the SAME name sits beside it — a factory next to the class it builds. Citing
    the unexported one and calling it the entry point is a claim the import
    graph contradicts, and three consecutive runs shipped a learning graph whose
    first node named the internal type "the user-facing declaration" because of
    it. Nothing here knows about any particular repository: the check fires only
    where such a twin exists.
    """
    (Path(repo) / "src/app/public.py").write_text(
        "from .auth import Signer as _Signer\n"
        "\n\n"
        "def sign(request, credentials):\n"
        "    return _Signer().apply(request)\n",
        encoding="utf-8",
    )
    (Path(repo) / "src/app/__init__.py").write_text(
        "from .public import sign as sign\n", encoding="utf-8"
    )
    build_skeleton.cache_clear()
    sk = build_skeleton(repo)

    payload = full_dossier()          # cites src/app/auth.py:sign, the internal twin
    check = investigation.validate_dossier(sk, GOAL, payload)
    assert check.surface, check
    message = check.gap_message()
    assert "app.sign" in message              # the path a caller actually types
    assert "src/app/public.py" in message
    assert "exported_by" in message           # and how to establish the relationship

    # Establishing BOTH definitions is the right answer, not a second offence.
    payload["components"].append({
        "file": "src/app/public.py", "symbol": "sign",
        "role_in_goal": "the name users import",
        "why_it_matters": "it is what a caller actually reaches",
    })
    assert not investigation.validate_dossier(sk, GOAL, payload).surface


def test_a_repository_with_no_exported_twin_never_sees_the_check(skeleton):
    """Narrow by construction: no twin, no complaint."""
    assert investigation.validate_dossier(skeleton, GOAL, full_dossier()).surface == []
    assert investigation.public_surface_gaps(skeleton, full_dossier()) == []


def test_a_mangled_payload_is_not_also_told_about_its_public_surface(skeleton):
    """One fault at a time: an unreadable dossier has no claims to contradict."""
    payload = full_dossier()
    payload["components"] = "<component>whatever</component>"
    check = investigation.validate_dossier(skeleton, GOAL, payload)
    assert check.structural and not check.surface


def test_a_serialisation_fault_asks_for_a_re_emission_not_more_exploration(skeleton):
    """The production shape that cost a whole run (fastapi-di, Stage-4 repeats).

    `components` arrived as XML-ish markup and the item's own keys were stranded
    at the top level. The old feedback led with "0 goal-relevant components
    established … Investigate further", so the model went exploring, ran out of
    turns, and salvaged the same unreadable payload — which reached the Mentor
    as a dossier with no resolvable evidence. The counts were artifacts of a
    payload we could not parse; the feedback has to say so.
    """
    payload = {
        "understanding": "FastAPI resolves dependencies from function signatures.",
        "components": '\n<component>\n<parameter name="file">fastapi/dependencies/models.py',
        "symbol": "Dependant",
        "role_in_goal": "holds the resolved dependency tree",
        "why_it_matters": "everything the resolver walks lives here",
    }
    check = investigation.validate_dossier(skeleton, GOAL, payload)
    assert not check.ok
    assert check.structural

    message = check.gap_message()
    assert "`components` arrived as XML-style tool markup" in message
    # The stranded item keys are the other half of the same fault, and naming
    # them is how the model learns its nested objects collapsed.
    for stranded in ("`symbol`", "`role_in_goal`", "`why_it_matters`"):
        assert stranded in message, message
    assert "Do NOT gather more evidence" in message
    # ...and none of the coverage arithmetic that sent it back out exploring.
    assert "Investigate further" not in message
    assert "goal-relevant component(s) established" not in message


def test_the_xml_markup_signature_is_named_rather_than_generically_described(skeleton):
    """Four consecutive gate attempts failed this exact way, so say what it is."""
    payload = full_dossier()
    payload["components"] = '\n<component>\n<parameter name="file">src/app/auth.py'
    message = investigation.validate_dossier(skeleton, GOAL, payload).gap_message()
    assert "XML-style tool markup" in message
    assert "<component>" in message      # quoted back, so it is unmistakable


def test_a_repeated_shape_failure_escalates_instead_of_repeating_itself(skeleton):
    """One run resubmitted the identical broken payload twelve times.

    The instruction was right and still did not work, so saying it again is not
    feedback; the second time, ask for a payload small enough to emit.
    """
    validator = investigation.DossierValidator(skeleton, GOAL)
    broken = full_dossier()
    broken["components"] = '<component><parameter name="file">src/app/auth.py'

    first = validator(dict(broken))
    assert "attempt 2 at the same shape" not in first
    second = validator(dict(broken))
    assert "attempt 2 at the same shape" in second
    assert "SMALLER payload" in second
    # ...and what it asks to drop is what no exit criterion counts.
    assert "`context` and `open_questions` empty" in second

    # A shape failure that is not consecutive does not escalate.
    thin = full_dossier()
    thin["components"] = []
    validator(thin)
    assert "same shape" not in (validator(dict(broken)) or "")


def test_a_readable_but_thin_dossier_still_gets_coverage_feedback(skeleton):
    """The suppression above is scoped to unreadable payloads, not to thin ones."""
    payload = full_dossier()
    payload["components"] = payload["components"][:1]
    check = investigation.validate_dossier(skeleton, GOAL, payload)
    assert not check.ok
    assert not check.structural
    message = check.gap_message()
    assert "Investigate further" in message
    assert check.repair_message() is None


def test_only_a_serialisation_fault_earns_a_repair_prompt(skeleton):
    """`explore` re-emits on a broken wire; it must not re-emit a thin dossier."""
    validator = investigation.DossierValidator(skeleton, GOAL)
    thin = full_dossier()
    thin["components"] = []
    assert validator.repair_prompt(thin) is None
    assert validator.repair_prompt(full_dossier()) is None

    broken = full_dossier()
    broken["flows"] = "<flow>step one</flow>"
    assert "Resubmit the SAME findings" in (validator.repair_prompt(broken) or "")


def test_a_wholly_malformed_payload_still_validates(skeleton):
    check = investigation.validate_dossier(
        skeleton, GOAL,
        {"understanding": "x", "components": "not a list", "flows": ["s"]},
    )
    assert not check.ok
    assert check.gap_message()


def test_open_questions_are_never_required(skeleton):
    payload = full_dossier()
    payload["open_questions"] = []
    assert investigation.validate_dossier(skeleton, GOAL, payload).ok


def test_every_goal_type_has_criteria_or_a_fallback():
    for goal_type in investigation.GOAL_TYPES:
        criteria = investigation.CRITERIA_BY_GOAL_TYPE.get(
            goal_type, investigation.BASE_CRITERIA
        )
        assert criteria.min_flows >= 1
        assert criteria.min_components >= 2


# ── the survey is a map, not evidence ─────────────────────────────────────────

SURVEY = {
    "architecture": "A small HTTP client with signing.",
    "subsystems": [
        {"name": "auth.py", "responsibility": "signs requests", "key_file": "src/app/auth.py"},
        {"name": "client.py", "responsibility": "public API", "key_file": "src/app/client.py"},
    ],
    "skipped": [{"name": "tests", "reason": "test code"}],
    "entry_points": [
        {"file": "src/app/client.py", "symbol": "fetch", "what_it_starts": "a fetch"},
    ],
    "needs_investigation": [
        {"area": "auth", "open_question": "how Signer is configured"},
    ],
    "testing_posture": "pytest under tests/",
}


def test_survey_context_renders_breadth_and_labels_itself_a_map():
    text = investigation.survey_context(SURVEY)
    assert "NOT evidence" in text
    assert "auth.py: signs requests" in text
    assert "fetch" in text
    assert "how Signer is configured" in text


def test_survey_context_excludes_unstable_depth_fields():
    survey = dict(SURVEY)
    survey["flows"] = [{"name": "secret flow", "steps": []}]
    survey["core_abstractions"] = [{"file": "x", "symbol": "Hidden", "role": "r"}]
    text = investigation.survey_context(survey)
    # Stage 2 measured these at 0–63% cross-run stability — they must not steer.
    assert "secret flow" not in text
    assert "Hidden" not in text


def test_survey_context_is_bounded():
    survey = dict(SURVEY)
    survey["subsystems"] = [
        {"name": f"mod_{i}.py", "responsibility": "x" * 200} for i in range(200)
    ]
    assert len(investigation.survey_context(survey)) <= 6000


def test_empty_survey_renders_nothing():
    assert investigation.survey_context({}) == ""


# ── the loop ──────────────────────────────────────────────────────────────────


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


def test_with_survey_the_seed_carries_the_map(repo, skeleton):
    client = FakeClient([turn(tool_block("submit_dossier", full_dossier(), id="r"))])
    run = investigation.run_investigation(
        client=client, repo_path=repo, goal=GOAL, skeleton=skeleton,
        survey_payload=SURVEY,
    )
    assert run.used_survey and run.accepted
    seed = "\n".join(b["text"] for b in client.requests[0]["system"])
    assert "REPOSITORY SURVEY" in seed
    assert "signs requests" in seed


def test_without_survey_the_seed_carries_only_the_skeleton(repo, skeleton):
    client = FakeClient([turn(tool_block("submit_dossier", full_dossier(), id="r"))])
    run = investigation.run_investigation(
        client=client, repo_path=repo, goal=GOAL, skeleton=skeleton,
    )
    assert not run.used_survey and run.accepted
    seed = "\n".join(b["text"] for b in client.requests[0]["system"])
    assert "REPOSITORY SURVEY" not in seed
    assert "REPOSITORY INVENTORY" in seed


def test_the_goal_rides_in_the_task_not_the_cached_seed(repo, skeleton):
    client = FakeClient([turn(tool_block("submit_dossier", full_dossier(), id="r"))])
    investigation.run_investigation(
        client=client, repo_path=repo, goal=GOAL, skeleton=skeleton,
        survey_payload=SURVEY,
    )
    request = client.requests[0]
    seed = "\n".join(b["text"] for b in request["system"])
    assert GOAL["primary_goal"] not in seed          # cache-stable seed
    assert GOAL["primary_goal"] in request["messages"][0]["content"]
    assert "understand_component" in request["messages"][0]["content"]


def test_an_insufficient_dossier_sends_the_model_back(repo, skeleton):
    thin = full_dossier()
    thin["relationships"] = []
    client = FakeClient([
        turn(tool_block("submit_dossier", thin, id="r1")),
        turn(tool_block("submit_dossier", full_dossier(), id="r2")),
    ])
    run = investigation.run_investigation(
        client=client, repo_path=repo, goal=GOAL, skeleton=skeleton,
        budget=Budget(max_turns=6),
    )
    assert run.accepted
    assert len(run.exploration.rejections) == 1
    assert "relationship" in run.exploration.rejections[0]


def test_budget_exhaustion_still_returns_the_best_dossier(repo, skeleton):
    thin = full_dossier()
    thin["entry_points"] = []
    client = FakeClient([
        turn(tool_block("submit_dossier", thin, id=f"r{i}")) for i in range(5)
    ])
    run = investigation.run_investigation(
        client=client, repo_path=repo, goal=GOAL, skeleton=skeleton,
        budget=Budget(max_turns=2),
    )
    assert run.produced and not run.accepted
    assert run.exploration.contract_met is False
    assert run.dossier is not None
    assert run.check is not None and not run.check.ok


# ── the chunk-shape shim ──────────────────────────────────────────────────────


def test_dossier_chunks_carry_real_source_at_resolved_ranges(skeleton):
    chunks = investigation.dossier_as_chunks(skeleton, full_dossier())
    assert chunks
    by_name = {c["name"]: c for c in chunks}
    signer = by_name["Signer"]
    assert signer["file"] == "src/app/auth.py"
    assert "class Signer" in signer["content"]
    assert signer["start_line"] < signer["end_line"]
    for c in chunks:
        assert set(c) == {"file", "start_line", "end_line", "type", "name", "role", "content"}
        assert c["content"].strip()


def test_dossier_chunks_drop_what_does_not_resolve(skeleton):
    payload = full_dossier()
    payload["components"].append({
        "file": "src/app/auth.py", "symbol": "Ghost",
        "role_in_goal": "x", "why_it_matters": "y",
    })
    chunks = investigation.dossier_as_chunks(skeleton, payload)
    assert not any(c["name"] == "Ghost" for c in chunks)


def test_dossier_chunks_deduplicate_by_resolved_range(skeleton):
    # `fetch` appears as component, entry point and flow step: one chunk.
    chunks = investigation.dossier_as_chunks(skeleton, full_dossier())
    fetches = [c for c in chunks if c["name"] == "fetch"]
    assert len(fetches) == 1


def test_dossier_chunks_are_capped(skeleton):
    payload = full_dossier()
    chunks = investigation.dossier_as_chunks(skeleton, payload, max_chunks=2)
    assert len(chunks) == 2


def test_the_module_map_view_groups_components_by_file(skeleton):
    modules = investigation.module_map_from_dossier(full_dossier())
    assert "auth" in modules and "client" in modules
    assert "src/app/auth.py" in modules["auth"]["key_files"]
    assert "Signer" in modules["auth"]["exports"]
    assert "auth" in modules["client"]["dependencies"]


# ── isolation ─────────────────────────────────────────────────────────────────


def test_not_yet_migrated_agents_stay_off_the_explorer_stack():
    """The integration boundary is the Mentor (user-approved, 2026-08-13).

    Teaching, Grader and the Mutator still run on the RAG path and must not
    quietly start depending on the explorer stack before their own migration
    stage. (Mentor, Reviewer and the pipeline now import it by design.)
    """
    import subprocess

    hits = subprocess.run(
        ["git", "grep", "-l", "-E", r"repo\.(investigation|survey|explore|metrics)",
         "--",
         "backend/agents/teaching", "backend/agents/grader",
         "backend/agents/mentor/mutator.py",
         "backend/agents/code_structure", "backend/agents/prioritization"],
        capture_output=True, text=True,
    )
    assert hits.stdout.strip() == "", hits.stdout


def test_the_brief_names_no_repository_or_framework():
    corpus = (
        investigation.INVESTIGATION_INSTRUCTIONS
        + json.dumps(investigation.INVESTIGATION_SPEC.input_schema)
    ).lower()
    for banned in ("fastapi", "requests", "psf", "starlette", "pydantic",
                   "urllib3", "security/", "sessions.py", "dependency injection"):
        assert banned not in corpus, banned
