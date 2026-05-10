# Mentor Agent — turns goal + module_map + RAG retrieval into an ordered
# learning path. Only Phase 1 agent that uses claude-sonnet-4-6 (one call).
#
# Entry point:
#   run(state, client) → embeds goal text, queries ChromaDB for top-K chunks,
#                        picks a goal-type-specific prompt builder, calls Sonnet
#                        once, validates the output through Pydantic, writes
#                        learning_path + confidence to state, and returns it.
#
# Mirrors the Code Structure Agent pattern: client injected, errors appended
# to state.errors, never raises.

import json
import os
from typing import Callable, Literal

import anthropic
from pydantic import BaseModel

from backend.pipeline.state import OnboardState
from backend.rag import embedder, store
from backend.rag.cloner import get_commit_sha, parse_repo_url


MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096
TOP_K = 20


class LearningPathStep(BaseModel):
    step: int
    title: str
    file: str
    line_range: tuple[int, int]
    why: str
    understand: str
    concepts: list[str]


class MentorOutput(BaseModel):
    steps: list[LearningPathStep]
    confidence: Literal["high", "medium", "low"]


_SYSTEM_PROMPT = """\
You are a mentor guiding a developer through an unfamiliar Python codebase.

Given the user's goal, the repository's module map, and a set of code chunks
retrieved via semantic search, produce a JSON object with exactly these keys:
  steps:      list of 5–8 ordered learning steps
  confidence: one of "high", "medium", "low"

Each step is an object with exactly these keys:
  step:        1-indexed integer
  title:       short imperative title
  file:        path to the file (must come from the retrieved chunks — no invented paths)
  line_range:  [start_line, end_line] from the retrieved chunk metadata
  why:         one sentence — why this step matters for the user's goal
  understand:  one sentence — what the user should take away
  concepts:    list of short concept tags (≤ 4 entries)

Rules:
- Use only files that appear in the retrieved chunks. Never invent file paths.
- 5–8 steps total. Order matters: each step builds on the previous one.
- Self-rate confidence:
    high   — retrieved chunks clearly cover the user's goal and the path is concrete
    medium — chunks partially cover the goal, some steps required interpolation
    low    — chunks barely related to the goal; you are mostly guessing
- Return ONLY the JSON object — no markdown fences, no explanation.
"""


def _format_module_map(module_map: dict) -> str:
    lines = []
    for name, entry in module_map.items():
        lines.append(
            f"- {name}: {entry['purpose']} "
            f"(exports: {', '.join(entry['exports'])})"
        )
    return "\n".join(lines)


def _format_chunks(chunks: list[dict]) -> str:
    lines = []
    for c in chunks:
        lines.append(
            f"[{c['type'].upper()}] {c['name']} — "
            f"{c['file']} (lines {c['start_line']}–{c['end_line']})\n"
            f"{c['content']}"
        )
    return "\n\n".join(lines)


def _common_context(goal: dict, module_map: dict, chunks: list[dict]) -> str:
    return (
        f"User goal: {goal['primary_goal']}\n"
        f"Experience level: {goal['experience_level']}\n"
        f"Depth requested: {goal['depth']}\n\n"
        f"Module map:\n{_format_module_map(module_map)}\n\n"
        f"Retrieved code chunks:\n{_format_chunks(chunks)}"
    )


def _build_understand_system_prompt(
    goal: dict, module_map: dict, chunks: list[dict]
) -> str:
    return (
        f"{_common_context(goal, module_map, chunks)}\n\n"
        f"Goal type: understand_system. The user wants a high-level tour. "
        f"Pick steps that span the major modules and show how they connect. "
        f"Favour breadth over depth — touch entry points, not internals."
    )


def _build_understand_component_prompt(
    goal: dict, module_map: dict, chunks: list[dict]
) -> str:
    return (
        f"{_common_context(goal, module_map, chunks)}\n\n"
        f"Goal type: understand_component. Focus area: {goal['focus_area']}. "
        f"Go deep into this area. Prefer fewer files at greater depth over "
        f"a broad tour. Each step should explain a specific abstraction or flow."
    )


def _build_contribute_code_prompt(
    goal: dict, module_map: dict, chunks: list[dict]
) -> str:
    contribution = goal.get("contribution_context", "(none provided)")
    return (
        f"{_common_context(goal, module_map, chunks)}\n\n"
        f"Goal type: contribute_code. Contribution context: {contribution}\n"
        f"Order steps so the user understands extension points first, then "
        f"the file(s) most likely to need editing. The final step should "
        f"land at the most likely insertion site."
    )


def _build_debug_issue_prompt(
    goal: dict, module_map: dict, chunks: list[dict]
) -> str:
    error = goal.get("error_description", "(none provided)")
    tried = goal.get("tried_so_far", "(none provided)")
    return (
        f"{_common_context(goal, module_map, chunks)}\n\n"
        f"Goal type: debug_issue.\n"
        f"Error: {error}\n"
        f"Tried so far: {tried}\n"
        f"Trace the execution path that produces this error. Each step should "
        f"narrow the search — start at the entry point, end at the most likely "
        f"source of the bug."
    )


_PROMPT_BUILDERS: dict[str, Callable[[dict, dict, list[dict]], str]] = {
    "understand_system": _build_understand_system_prompt,
    "understand_component": _build_understand_component_prompt,
    "contribute_code": _build_contribute_code_prompt,
    "debug_issue": _build_debug_issue_prompt,
}


def _retrieve_chunks(state: OnboardState) -> list[dict]:
    owner, repo = parse_repo_url(state.repo_url)
    commit_sha = get_commit_sha(state.repo_path)
    name = store.collection_name(owner, repo, commit_sha)

    embedding = embedder.embed_query(state.goal["primary_goal"])
    result = store.query(name, embedding, top_k=TOP_K)

    documents = result["documents"][0]
    metadatas = result["metadatas"][0]

    return [
        {
            "file": meta["file"],
            "start_line": meta["start_line"],
            "end_line": meta["end_line"],
            "type": meta["type"],
            "name": meta["name"],
            "content": doc,
        }
        for doc, meta in zip(documents, metadatas)
    ]


def _parse_output(raw: str) -> MentorOutput:
    raw = raw.strip()
    if "```json" in raw:
        raw = raw.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in raw:
        parts = raw.split("```")
        if len(parts) >= 2:
            raw = parts[1]
    start = raw.find("{")
    if start < 0:
        raise ValueError("no JSON object found in response")
    decoded, _ = json.JSONDecoder().raw_decode(raw[start:])
    return MentorOutput(**decoded)


def run(
    state: OnboardState,
    client: anthropic.Anthropic | None = None,
) -> OnboardState:
    if client is None:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    if state.goal is None:
        state.errors.append("mentor_agent: goal missing")
        return state

    if state.module_map is None:
        state.errors.append("mentor_agent: module_map missing")
        return state

    if not state.chunks_embedded:
        state.errors.append("mentor_agent: chunks not embedded")
        return state

    goal_type = state.goal.get("goal_type")
    if goal_type not in _PROMPT_BUILDERS:
        state.errors.append(f"mentor_agent: unknown goal_type {goal_type!r}")
        return state

    try:
        chunks = _retrieve_chunks(state)
    except Exception as e:
        state.errors.append(f"mentor_agent retrieval failed: {e}")
        return state

    builder = _PROMPT_BUILDERS[goal_type]
    user_content = builder(state.goal, state.module_map, chunks)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        raw = response.content[0].text
        output = _parse_output(raw)
        state.learning_path = [step.model_dump() for step in output.steps]
        state.confidence = output.confidence
    except Exception as e:
        state.errors.append(f"mentor_agent LLM call failed: {e}")

    return state
