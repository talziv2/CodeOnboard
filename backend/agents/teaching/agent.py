# Teaching Agent — expands one learning-graph node into the actual lesson.
#
# Where the Mentor produces a *brief* (one-sentence why / understand), the
# Teaching Agent produces the *lesson* the user reads: a walkthrough plus one
# active-learning prompt. Runs once per node visit; one Haiku call per lesson.
#
# Entry point:
#   run(state, client) → renders the lesson for state.graph.current_node_id,
#                        writes it to node.cached_lesson AND state.current_lesson.
#
# Caching: if the node already has a cached_lesson (a prior visit), reuse it —
# no LLM call. Regeneration on demand is a Part 4 concern (a refresh flag).
#
# Mirrors the other agents: client injected, errors appended to state.errors,
# never raises.

import json
import os
from pathlib import Path
from typing import Literal

import anthropic
from pydantic import BaseModel

from backend.learning.graph import LearningGraph, LearningNode
from backend.pipeline.state import OnboardState
from backend.rag.retrieval import retrieve_supporting_chunks


MODEL = "claude-haiku-4-5"
MAX_TOKENS = 2048

# How many extra cross-reference chunks to pull for context. Small on purpose —
# the lesson is about one node, the supporting chunks just give it reach.
SUPPORTING_CHUNK_COUNT = 2


class LessonOutput(BaseModel):
    walkthrough: str   # markdown lesson body
    prompt: str        # the active-learning question
    expected_answer: str  # what a correct answer looks like — used by the Grader (Part 5)
    # v1 locks to a single prompt form (phase3.md Open decision #1). The field
    # stays so the wire format is stable when other forms arrive.
    prompt_kind: Literal["predict-then-reveal"] = "predict-then-reveal"


_SYSTEM_PROMPT = """\
You are a patient programming mentor guiding a developer through one specific
piece of an unfamiliar Python codebase. You are given:
  - the developer's experience level and overall goal
  - what they already understand (so you don't re-explain it)
  - a "lesson brief": why this piece matters and what they should take away
  - the actual source code for this piece
  - a few supporting code chunks for cross-reference context

Produce a JSON object with exactly these keys:
  walkthrough:     markdown. Explain this code so the developer understands it
                   in service of their goal. Reference the real identifiers and
                   line structure. Calibrate depth to their experience level.
                   Connect to what they already understand where relevant.
  prompt:          ONE active-learning question of the "predict-then-reveal"
                   form — ask the developer to predict something about this code
                   BEFORE they read your explanation in full (e.g. "Before
                   reading on: what do you think `Session.send` does with the
                   adapter it looks up?"). It must be answerable from the code
                   shown.
  expected_answer: a concise model answer to your prompt — what a developer who
                   understood the code would say. Used to grade their response.
  prompt_kind:     always the string "predict-then-reveal".

Rules:
- Teach only what the shown code supports. Do not invent behavior, file paths,
  or relationships not visible in the code or supporting chunks.
- Keep the walkthrough focused on THIS piece — the supporting chunks are
  context, not separate lessons.
- Return ONLY the JSON object — no markdown fences, no preamble.
"""


def _read_source_lines(repo_path: str, file: str, start: int, end: int) -> str:
    """Read lines [start, end] (1-indexed, inclusive) from {repo_path}/{file}."""
    path = Path(repo_path) / file
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    # start/end are 1-indexed and inclusive; slice is 0-indexed half-open.
    return "\n".join(lines[start - 1:end])


def _build_prior_context(graph: LearningGraph, current_id: str) -> str:
    understood = [
        n
        for nid, n in graph.nodes.items()
        if nid != current_id and n.understanding_state == "understood"
    ]
    if not understood:
        return "This is the developer's first lesson in this session — assume no prior nodes covered."
    lines = []
    for n in understood:
        tags = ", ".join(n.concept_tags) if n.concept_tags else "—"
        lines.append(f"- {n.title} (concepts: {tags})")
    return "The developer already understands these earlier nodes:\n" + "\n".join(lines)


def _format_supporting_chunks(chunks: list[dict]) -> str:
    if not chunks:
        return "(none)"
    lines = []
    for c in chunks:
        lines.append(
            f"[{c['type'].upper()}] {c['name']} — "
            f"{c['file']} (lines {c['start_line']}–{c['end_line']})\n{c['content']}"
        )
    return "\n\n".join(lines)


def _build_user_content(
    goal: dict,
    node: LearningNode,
    source: str,
    prior_context: str,
    supporting: list[dict],
) -> str:
    brief = node.lesson_brief or {}
    return (
        f"Developer experience level: {goal.get('experience_level', 'unknown')}\n"
        f"Overall goal: {goal.get('primary_goal', '')}\n"
        f"Depth requested: {goal.get('depth', 'normal')}\n\n"
        f"{prior_context}\n\n"
        f"Lesson brief for this node:\n"
        f"  title: {node.title}\n"
        f"  why: {brief.get('why', '')}\n"
        f"  understand: {brief.get('understand', '')}\n"
        f"  concepts: {', '.join(node.concept_tags) if node.concept_tags else '—'}\n\n"
        f"Source code for this node "
        f"({node.code_anchor.file} lines "
        f"{node.code_anchor.line_start}–{node.code_anchor.line_end}):\n"
        f"{source}\n\n"
        f"Supporting chunks for cross-reference:\n"
        f"{_format_supporting_chunks(supporting)}"
    )


def _parse_output(raw: str) -> LessonOutput:
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
    return LessonOutput(**decoded)


def run(
    state: OnboardState,
    client: anthropic.Anthropic | None = None,
) -> OnboardState:
    if client is None:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    if state.graph is None:
        state.errors.append("teaching_agent: graph missing")
        return state

    current_id = state.graph.current_node_id
    if current_id is None or current_id not in state.graph.nodes:
        state.errors.append("teaching_agent: no current node to teach")
        return state

    if state.goal is None:
        state.errors.append("teaching_agent: goal missing")
        return state

    node = state.graph.nodes[current_id]

    # Cache hit — a prior visit already rendered this lesson.
    if node.cached_lesson is not None:
        state.current_lesson = node.cached_lesson
        return state

    try:
        source = _read_source_lines(
            state.repo_path,
            node.code_anchor.file,
            node.code_anchor.line_start,
            node.code_anchor.line_end,
        )
    except Exception as e:
        state.errors.append(f"teaching_agent: could not read source: {e}")
        return state

    # Supporting chunks are best-effort — a retrieval failure must not block
    # the lesson, since the primary source is already in hand.
    supporting: list[dict] = []
    try:
        query_text = node.title
        if node.concept_tags:
            query_text = f"{node.title}. {', '.join(node.concept_tags)}"
        supporting = retrieve_supporting_chunks(
            state,
            query_text,
            exclude={(
                node.code_anchor.file,
                node.code_anchor.line_start,
                node.code_anchor.line_end,
            )},
            top_k=SUPPORTING_CHUNK_COUNT,
        )
    except Exception as e:
        state.errors.append(f"teaching_agent: supporting retrieval failed (non-fatal): {e}")

    prior_context = _build_prior_context(state.graph, current_id)
    user_content = _build_user_content(state.goal, node, source, prior_context, supporting)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        raw = response.content[0].text
        output = _parse_output(raw)
        lesson = output.model_dump()
        node.cached_lesson = lesson
        state.current_lesson = lesson
    except Exception as e:
        state.errors.append(f"teaching_agent LLM call failed: {e}")

    return state
