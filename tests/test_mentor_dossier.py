"""
Pytest tests for the native-Dossier Mentor path (backend/agents/mentor/dossier.py).
Run with: uv run pytest tests/test_mentor_dossier.py -v

What must hold: the prompt carries the dossier's pedagogical semantics
(why_it_matters, prerequisites, flow order, open questions with the not-facts
instruction); a node grounded by symbol gets its range resolved by our code
(G1); the evidence gate is the dossier, so an anchor outside it is rejected;
ungrounded nodes are dropped rather than persisted; a salvaged dossier caps
confidence (§5.4); and agent.run() delegates here exactly when
state.investigation is present.

No network: scripted fake client.
"""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.agents.mentor import agent as mentor_agent
from backend.agents.mentor import dossier as dossier_path
from backend.pipeline.state import OnboardState
from backend.repo.skeleton import build_skeleton

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
}

GOAL = {
    "primary_goal": "understand how requests are signed",
    "goal_type": "understand_component",
    "focus_area": "authentication",
    "code_depth": "working",
    "depth": "moderate",
    "language": "en",
}

DOSSIER = {
    "understanding": "Signing wraps each outgoing request via Signer before transport.",
    "components": [
        {"file": "src/app/auth.py", "symbol": "Signer",
         "role_in_goal": "applies the signature",
         "why_it_matters": "it is the mechanism the whole goal turns on"},
        {"file": "src/app/auth.py", "symbol": "sign",
         "role_in_goal": "public signing entry", "why_it_matters": "callers use this"},
        {"file": "src/app/client.py", "symbol": "fetch",
         "role_in_goal": "decides when signing happens", "why_it_matters": "the trigger"},
    ],
    "entry_points": [
        {"file": "src/app/client.py", "symbol": "fetch", "how_it_enters": "public API"},
    ],
    "flows": [
        {"name": "signed fetch", "steps": [
            {"file": "src/app/client.py", "symbol": "fetch", "what_happens": "receives credentials"},
            {"file": "src/app/auth.py", "symbol": "sign", "what_happens": "wraps request"},
            {"file": "src/app/transport.py", "symbol": "send", "what_happens": "transmits"},
        ]},
    ],
    "relationships": [
        {"from_file": "src/app/client.py", "from_symbol": "fetch",
         "to_file": "src/app/auth.py", "to_symbol": "sign",
         "kind": "calls", "note": "only when credentials given"},
    ],
    "contracts": [
        {"file": "src/app/auth.py", "symbol": "Signer.apply",
         "contract": "takes and returns a request dict"},
    ],
    "prerequisites": [
        {"concept": "request lifecycle", "why_needed": "signing happens mid-flight",
         "file": "src/app/client.py", "symbol": "fetch"},
        {"concept": "credential storage", "why_needed": "explains the optional path"},
    ],
    "evidence_refs": [{"path": "tests/test_client.py", "clarifies": "default path"}],
    "context": ["transport is a stub here"],
    "open_questions": [
        {"question": "how are credentials rotated", "why_it_matters": "not in this repo"},
    ],
}


@pytest.fixture
def repo(tmp_path: Path) -> str:
    for relative, body in FILES.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    build_skeleton.cache_clear()
    return str(tmp_path)


def wire_response(nodes, confidence="high"):
    edges = [
        {"from_id": nodes[i]["id"], "to_id": nodes[i + 1]["id"], "kind": "sequence"}
        for i in range(len(nodes) - 1)
    ]
    return json.dumps({"nodes": nodes, "edges": edges, "confidence": confidence})


def node(id, file, symbol=None, line_start=None, line_end=None, title=None):
    return {
        "id": id, "title": title or f"Learn {symbol or file}", "file": file,
        "symbol": symbol, "line_start": line_start, "line_end": line_end,
        "why": "matters", "understand": "takeaway", "concept_tags": ["component"],
    }


class FakeClient:
    def __init__(self, texts):
        self.texts = list(texts)
        self.requests = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        text = self.texts.pop(0) if self.texts else self.texts_last
        self.texts_last = text
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def make_state(repo, accepted=True, investigation=None):
    return OnboardState(
        repo_url="https://github.com/example/demo",
        goal=dict(GOAL),
        repo_path=repo,
        investigation=investigation if investigation is not None else {
            "dossier": DOSSIER, "accepted": accepted, "stop_reason": "reported",
            "turns": 8, "tool_calls": 20, "rejections": [], "cost_usd": 0.1,
            "seconds": 30.0, "used_survey": True,
        },
    )


GOOD_WIRE = [
    node("n1", "src/app/client.py", symbol="fetch", title="Start at the entry point"),
    node("n2", "src/app/auth.py", symbol="sign"),
    node("n3", "src/app/auth.py", symbol="Signer.apply"),
]


# ── happy path: symbol-first grounding ────────────────────────────────────────


def test_a_symbol_grounded_graph_is_built_with_resolved_ranges(repo):
    client = FakeClient([wire_response(GOOD_WIRE)])
    state = mentor_agent.run(make_state(repo), client)
    assert not [e for e in state.errors if "mentor" in e], state.errors
    assert state.graph is not None
    assert len(state.graph.nodes) == 3
    by_symbol = {n.code_anchor.symbol: n for n in state.graph.nodes.values()}
    fetch = by_symbol["fetch"]
    # The model gave no line numbers; our code resolved them (G1).
    assert fetch.code_anchor.line_start == 5
    assert fetch.code_anchor.line_end == 9
    assert state.learning_path[0]["title"] == "Start at the entry point"
    assert state.confidence == "high"


def test_line_numbers_from_the_model_are_overridden_by_the_symbol(repo):
    lying = [dict(GOOD_WIRE[0], line_start=999, line_end=1500)] + GOOD_WIRE[1:]
    client = FakeClient([wire_response(lying)])
    state = mentor_agent.run(make_state(repo), client)
    fetch = next(n for n in state.graph.nodes.values()
                 if n.code_anchor.symbol == "fetch")
    assert fetch.code_anchor.line_start == 5      # the symbol's real range wins


def test_a_raw_range_anchor_is_still_legal(repo):
    wire = GOOD_WIRE[:2] + [
        node("n3", "src/app/auth.py", line_start=1, line_end=4, title="The Signer class body"),
    ]
    client = FakeClient([wire_response(wire)])
    state = mentor_agent.run(make_state(repo), client)
    assert len(state.graph.nodes) == 3


# ── the evidence gate is the dossier ──────────────────────────────────────────


def test_an_anchor_outside_the_dossier_is_rejected_then_dropped(repo):
    # `send` exists in the repository but is only a flow step in the dossier —
    # that IS evidence. `helper`-style symbols outside the dossier entirely
    # must be refused. transport.py:send appears in the dossier flow, so use a
    # file the dossier never cites: __init__.py has no symbols... craft one:
    outside = GOOD_WIRE[:2] + [
        node("n3", "src/app/transport.py", line_start=1, line_end=2,
             title="A range the dossier never verified... except send is cited"),
    ]
    # send IS in the dossier (flow step) — so that one grounds. Use a truly
    # outside anchor instead: a range in client.py lines 1-2 (imports, outside
    # fetch's span).
    outside[2] = node("n3", "src/app/client.py", line_start=1, line_end=2,
                      title="Imports — never part of the dossier evidence")
    client = FakeClient([
        wire_response(outside),
        wire_response(outside),      # retry repeats the mistake
    ])
    state = mentor_agent.run(make_state(repo), client)
    assert len(client.requests) == 2                     # corrective retry fired
    assert any("dropped 1 ungrounded node" in e for e in state.errors)
    assert len(state.graph.nodes) == 2                   # the bad node is gone
    titles = [n.title for n in state.graph.nodes.values()]
    assert "Imports — never part of the dossier evidence" not in titles


def test_a_flow_step_symbol_counts_as_dossier_evidence(repo):
    wire = GOOD_WIRE[:2] + [node("n3", "src/app/transport.py", symbol="send")]
    client = FakeClient([wire_response(wire)])
    state = mentor_agent.run(make_state(repo), client)
    assert not [e for e in state.errors if "dropped" in e]
    assert len(state.graph.nodes) == 3


def test_a_nonexistent_symbol_is_rejected(repo):
    wire = GOOD_WIRE[:2] + [node("n3", "src/app/auth.py", symbol="Signer.teleport")]
    client = FakeClient([wire_response(wire), wire_response(GOOD_WIRE)])
    state = mentor_agent.run(make_state(repo), client)
    # The retry fixed it, so all three nodes survive.
    assert len(state.graph.nodes) == 3
    assert not [e for e in state.errors if "dropped" in e]


# ── the prompt carries the dossier's semantics ────────────────────────────────


def test_the_prompt_preserves_pedagogical_structure(repo):
    client = FakeClient([wire_response(GOOD_WIRE)])
    mentor_agent.run(make_state(repo), client)
    prompt = client.requests[0]["messages"][0]["content"]
    assert "it is the mechanism the whole goal turns on" in prompt   # why_it_matters
    assert "role in this goal" in prompt
    assert "EXECUTION order" in prompt                               # flow framing
    assert "credential storage" in prompt                            # unanchored prereq
    assert "(no code anchor)" in prompt
    assert "OPEN QUESTIONS" in prompt
    assert "how are credentials rotated" in prompt
    assert "def fetch" in prompt                                     # real code attached
    system = client.requests[0]["system"]
    assert "not a curriculum" in system
    assert "unresolved claim as fact" in system    # (line-wrapped in the prompt)
    assert "Prerequisites in the dossier are candidates, not obligations" in system


def test_the_prompt_renders_each_anchor_once(repo):
    client = FakeClient([wire_response(GOOD_WIRE)])
    mentor_agent.run(make_state(repo), client)
    prompt = client.requests[0]["messages"][0]["content"]
    # fetch is a component AND an entry point AND a flow step and a prerequisite
    # anchor; its body must be rendered exactly once.
    assert prompt.count("def fetch(url, credentials=None):") == 1


def test_long_anchors_are_render_capped_not_dropped(repo, tmp_path):
    big = tmp_path / "src" / "app" / "big.py"
    big.write_text(
        "def huge():\n" + "\n".join(f"    x{i} = {i}" for i in range(400)) + "\n",
        encoding="utf-8",
    )
    build_skeleton.cache_clear()
    dossier = json.loads(json.dumps(DOSSIER))
    dossier["components"].append({
        "file": "src/app/big.py", "symbol": "huge",
        "role_in_goal": "x", "why_it_matters": "y",
    })
    skeleton = build_skeleton(repo)
    text = dossier_path.render_dossier(skeleton, dossier, GOAL)
    assert "more lines not shown" in text
    assert "huge" in text


# ── uncertainty and confidence (§5.4) ─────────────────────────────────────────


def test_a_salvaged_dossier_caps_confidence_at_medium(repo):
    client = FakeClient([wire_response(GOOD_WIRE, confidence="high")])
    state = mentor_agent.run(make_state(repo, accepted=False), client)
    assert state.confidence == "medium"


def test_an_accepted_dossier_keeps_the_models_confidence(repo):
    client = FakeClient([wire_response(GOOD_WIRE, confidence="high")])
    state = mentor_agent.run(make_state(repo, accepted=True), client)
    assert state.confidence == "high"


def test_low_confidence_is_never_raised_by_the_cap(repo):
    client = FakeClient([wire_response(GOOD_WIRE, confidence="low")])
    state = mentor_agent.run(make_state(repo, accepted=False), client)
    assert state.confidence == "low"


# ── delegation and preconditions ──────────────────────────────────────────────


def test_agent_run_delegates_exactly_when_an_investigation_is_present(repo):
    client = FakeClient([wire_response(GOOD_WIRE)])
    state = mentor_agent.run(make_state(repo), client)
    assert state.graph is not None
    # No module_map was ever consulted: after Stage 5 the dossier is the only
    # evidence the Mentor has, and this state carries nothing else.
    assert state.module_map is None


def test_an_empty_investigation_fails_explicitly(repo):
    state = make_state(repo, investigation={"dossier": None, "accepted": False})
    state = mentor_agent.run(state, MagicMock())
    assert any("no investigation dossier" in e for e in state.errors)
    assert state.graph is None


def test_a_dossier_with_no_resolvable_evidence_fails_explicitly(repo):
    ghost = {
        "understanding": "x",
        "components": [{"file": "src/app/ghost.py", "symbol": "Ghost",
                        "role_in_goal": "x", "why_it_matters": "y"}],
        "entry_points": [], "flows": [], "relationships": [], "contracts": [],
        "prerequisites": [], "evidence_refs": [], "context": [], "open_questions": [],
    }
    state = make_state(repo, investigation={"dossier": ghost, "accepted": False})
    state = mentor_agent.run(state, MagicMock())
    assert any("no resolvable evidence" in e for e in state.errors)


def test_doc_context_still_reaches_the_graph_for_teaching(repo):
    client = FakeClient([wire_response(GOOD_WIRE)])
    state = make_state(repo)
    state.doc_context = {"readme_excerpt": "hello"}
    state = mentor_agent.run(state, client)
    assert state.graph.doc_context == {"readme_excerpt": "hello"}


def test_the_graph_wire_shape_is_unchanged(repo):
    """The wire format outlived the migration (§13).

    Graphs persisted before Stage 5 must still load, and the frontend still
    consumes exactly these fields — removing the old path must not have moved
    them.
    """
    client = FakeClient([wire_response(GOOD_WIRE)])
    state = mentor_agent.run(make_state(repo), client)
    payload = state.graph.to_dict()
    node_payload = payload["nodes"][0]
    # The frontend consumes file + [line_start, line_end]; both paths must emit
    # exactly this shape (CodeViewer highlights the range via /session/{id}/file).
    assert {"id", "title", "file", "line_start", "line_end"} <= set(node_payload)
    assert isinstance(node_payload["line_start"], int)
    assert node_payload["line_start"] > 0


# ── the objective contract (B1) ───────────────────────────────────────────────

_OBJECTIVE = "Explain what the signer owns that the client deliberately does not"


def test_the_planners_objective_reaches_the_nodes_lesson_brief(repo):
    wire = [dict(GOOD_WIRE[0], objective=_OBJECTIVE)] + GOOD_WIRE[1:]
    state = mentor_agent.run(make_state(repo), FakeClient([wire_response(wire)]))
    node_ = next(
        n for n in state.graph.nodes.values() if n.code_anchor.symbol == "fetch"
    )
    assert node_.lesson_brief["objective"] == _OBJECTIVE
    assert node_.objective() == _OBJECTIVE
    # …and out through the flat path the /onboard response still returns.
    assert state.learning_path[0]["objective"] == _OBJECTIVE


def test_a_node_missing_an_objective_costs_one_node_not_the_graph(repo):
    # GOOD_WIRE carries no `objective` at all — the pre-B1 shape. A required
    # field would fail the parse and leave the user with no learning path.
    state = mentor_agent.run(make_state(repo), FakeClient([wire_response(GOOD_WIRE)]))
    assert state.graph is not None
    assert len(state.graph.nodes) == 3
    node_ = next(iter(state.graph.nodes.values()))
    assert node_.lesson_brief["objective"] == ""
    # Falls back to the takeaway, which is what Teaching and the Grader use.
    assert node_.objective() == "takeaway"


def test_the_prompt_demands_a_claim_rather_than_a_topic():
    # LR3: the one quality property no test can assert is that objectives are
    # sharp. The least we can pin is that the prompt asks for a claim and shows
    # what a bad one looks like.
    assert "objective" in dossier_path._SYSTEM_PROMPT
    assert "BAD" in dossier_path._SYSTEM_PROMPT
    assert "GOOD" in dossier_path._SYSTEM_PROMPT
    assert "marked against" in dossier_path._SYSTEM_PROMPT
