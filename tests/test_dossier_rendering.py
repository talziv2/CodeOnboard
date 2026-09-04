"""
Pytest tests for dossier rendering (backend/agents/mentor/dossier.py).
Run with: uv run pytest tests/test_dossier_rendering.py -v

What must hold: the prompt text carries the dossier's pedagogical semantics
(why_it_matters, prerequisites, flow order, open questions, entry-point
perspective); each verified anchor's source is attached exactly once however
many sections cite it; and one enormous symbol is render-capped rather than
dropped, so a 900-line class cannot crowd the rest of the dossier out of the
prompt.

This file used to be `test_mentor_dossier.py` and used to test a planner. That
planner was the pre-B3 one, reached only with `CODEONBOARD_CURRICULUM=0`, and
both the flag and the planner are gone — `curriculum.py` is the only planner and
`tests/test_curriculum_planner.py` tests it. What survived the deletion is the
half both planners always shared: turning a dossier into prompt text. These
tests came with it, retargeted at `render_dossier` directly instead of reaching
it through a planner's first model call.

The fixtures below are shared: `test_curriculum_planner.py` imports `DOSSIER`,
`FILES` and `GOAL` from here.

No network — nothing in this file calls a model.
"""
import copy
import json
from pathlib import Path

import pytest

from backend.agents.mentor import dossier as dossier_path
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


# ── the prompt carries the dossier's semantics ────────────────────────────────


def test_the_prompt_preserves_pedagogical_structure(repo):
    text = dossier_path.render_dossier(build_skeleton(repo), DOSSIER, GOAL)
    assert "it is the mechanism the whole goal turns on" in text   # why_it_matters
    assert "role in this goal" in text
    assert "EXECUTION order" in text                               # flow framing
    assert "credential storage" in text                            # unanchored prereq
    assert "(no code anchor)" in text
    assert "OPEN QUESTIONS" in text
    assert "how are credentials rotated" in text
    assert "def fetch" in text                                     # real code attached


def test_the_prompt_renders_each_anchor_once(repo):
    text = dossier_path.render_dossier(build_skeleton(repo), DOSSIER, GOAL)
    # fetch is a component AND an entry point AND a flow step and a prerequisite
    # anchor; its body must be rendered exactly once.
    assert text.count("def fetch(url, credentials=None):") == 1


# ── render caps bound one entry, never the evidence ──────────────────────────


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


# ── entry-point perspective survives rendering (LQ5) ─────────────────────────


def test_entry_point_perspective_survives_dossier_rendering(repo):
    """Phase A collected `perspective`; the renderer dropped it.

    Without this the planner could not tell a caller-facing entry point from a
    runtime one for ANY goal type — the distinction existed in the schema, was
    verified by the investigation, and then vanished on the way to the prompt.
    """
    dossier = copy.deepcopy(DOSSIER)
    dossier["entry_points"] = [
        {"file": "src/app/client.py", "symbol": "fetch",
         "perspective": "public_api", "how_it_enters": "what callers import"},
        {"file": "src/app/transport.py", "symbol": "send",
         "perspective": "runtime", "how_it_enters": "invoked internally"},
    ]
    rendered = dossier_path.render_dossier(build_skeleton(repo), dossier, dict(GOAL))

    assert "[public_api]" in rendered
    assert "[runtime]" in rendered
    # …and the prompt explains what the two mean, so the label is usable.
    assert "USING this code imports and calls" in rendered


def test_rendering_survives_an_entry_point_with_no_perspective(repo):
    # Dossiers written before the field was required.
    dossier = copy.deepcopy(DOSSIER)
    dossier["entry_points"] = [
        {"file": "src/app/client.py", "symbol": "fetch", "how_it_enters": "public API"},
    ]
    rendered = dossier_path.render_dossier(build_skeleton(repo), dossier, dict(GOAL))
    assert "src/app/client.py:fetch" in rendered
    assert "[]" not in rendered
