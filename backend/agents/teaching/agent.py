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
# Walkthroughs are the longest prose in the system. 2048 was too tight — a long
# lesson would get truncated mid-JSON-string ("Unterminated string" on parse).
# Match the Mentor's budget so the JSON always closes.
MAX_TOKENS = 8192

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
  - the developer's profile (experience level, familiarity with THIS codebase,
    background — known languages/frameworks)
  - their overall goal and the depth they requested
  - what they already understand (so you don't re-explain it)
  - a "lesson brief": why this piece matters and what they should take away
  - the actual source code for this piece
  - a few supporting code chunks for cross-reference context
  - the node's concept tags (frame your walkthrough around the dominant tag)

CRITICAL: Your ENTIRE response must be under 600 words. Be very concise.

Produce a JSON object with exactly these keys:
  walkthrough:     markdown. MAX 250 words. Explain this code so the developer
                   understands it in service of their goal. Be brief and direct.
                   Reference key identifiers only — no exhaustive walkthroughs.
  prompt:          ONE active-learning question of the "predict-then-reveal"
                   form — ask the developer to predict something about this code
                   BEFORE they read your explanation in full (e.g. "Before
                   reading on: what do you think `Session.send` does with the
                   adapter it looks up?"). It must be answerable from the code
                   shown.
  expected_answer: a concise model answer to your prompt — what a developer who
                   understood the code would say. Used to grade their response.
  prompt_kind:     always the string "predict-then-reveal".

Framing by dominant concept tag:
  - `risk`            — lead with WHAT CAN GO WRONG. Name the invariant or
                        hidden coupling, then show the code that depends on
                        it. The prompt should ask the developer to predict a
                        consequence of violating it.
  - `extension_point` — lead with HOW THIS IS MEANT TO BE EXTENDED. Identify
                        the contract (ABC, protocol, callback shape), and
                        show one concrete extension if visible. The prompt
                        should ask the developer to predict the minimum
                        surface a new extension would need.
  - `architecture`    — lead with WHAT THIS LAYER OWNS and what it does NOT
                        own. Frame the explanation around the responsibility,
                        not line-by-line behavior. The prompt should ask the
                        developer to predict what would change if this layer
                        were removed.
  - `flow`            — lead with WHAT TRIGGERS THIS PATH and where it ends
                        up. Treat the anchored code as the entry point of a
                        path that continues through the supporting chunks.
  - `test_coverage`   — lead with WHAT THIS TEST GUARDS (or what is left
                        unguarded). The prompt should ask the developer to
                        predict which kinds of regression this coverage would
                        and would not catch.
  - other tags        — default behavior: explain the piece in service of
                        the goal.

Calibration by goal fields (read these from the user content):

  By `Depth requested`:
    overview  → ~100 words. Focus on the WHY only.
    moderate  → ~150 words (current default). Balanced explanation.
    deep      → ~250 words. Walk through the code. Stay under 250 words regardless.

  By `familiarity with THIS codebase`:
    "Starting fresh"      → define repo-specific terms on first use; do not
                            assume any working model of THIS codebase.
    "Skimmed the README"  → define internal terms; assume the developer
                            knows what the library does and roughly why.
    "Looked at some code" → assume working vocabulary; define only the
                            non-obvious internal terms.
    "Diving into source"  → terse expert framing; no re-explanation of
                            anything they could find by reading.

  By `background`:
    If the developer's background suggests fluency with a concept this
    lesson would otherwise re-explain (e.g. Python decorators for a 5-year
    Python developer, REST middleware for a web-backend engineer), OMIT
    that re-explanation and spend the saved words on what's specific to
    THIS codebase. This is information elision — DO NOT force analogies.
    Analogies are decoration; only use one if it makes the concept land
    materially faster, and never more than one per lesson.

Rules:
- Teach only what the shown code supports. Do not invent behavior, file paths,
  or relationships not visible in the code or supporting chunks.
- Keep the walkthrough focused on THIS piece — the supporting chunks are
  context, not separate lessons. The target word count is set by
  `Depth requested` (see Calibration above).
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


def _format_doc_context(node: LearningNode, doc_context: dict | None) -> str:
    """Build the documentation-context section for the Teaching Agent prompt.

    Pulls four sources of real repo documentation (none LLM-generated):
      1. Module docstring for the node's file
      2. Class / function docstrings in that file
      3. README excerpt (first 400 chars)
      4. Relevant docs/ file excerpt if one matches the node's file path
    Returns "" when doc_context is absent or all sources are empty.
    """
    if not doc_context:
        return ""
    parts: list[str] = []

    file = node.code_anchor.file

    # 1. Module-level docstring
    file_doc = (doc_context.get("file_docs") or {}).get(file, "").strip()
    if file_doc:
        parts.append(f"Module docstring for {file}:\n{file_doc}")

    # 2. Class / function docstrings in this file
    symbols: dict[str, str] = (doc_context.get("symbol_docs") or {}).get(file, {})
    if symbols:
        lines = [f"  `{name}`: {doc.splitlines()[0]}" for name, doc in symbols.items()]
        parts.append(f"Docstrings in {file}:\n" + "\n".join(lines))

    # 3. README excerpt
    readme = (doc_context.get("readme") or "").strip()
    if readme:
        parts.append(f"README excerpt:\n{readme[:400]}")

    # 4. Relevant docs/ file — pick the first extra_doc whose key mentions
    #    the stem of the node's file (e.g. "sessions" matches docs/api.rst
    #    only if "sessions" appears in the key; otherwise skip).
    file_stem = Path(file).stem  # e.g. "sessions" from "requests/sessions.py"
    extra: dict[str, str] = doc_context.get("extra_docs") or {}
    for doc_path, content in extra.items():
        if file_stem in doc_path:
            parts.append(f"Docs file ({doc_path}):\n{content[:500]}")
            break

    if not parts:
        return ""
    return "\n\n".join(parts) + "\n\n"


def _build_user_content(
    goal: dict,
    node: LearningNode,
    source: str,
    prior_context: str,
    supporting: list[dict],
    doc_context: dict | None = None,
) -> str:
    brief = node.lesson_brief or {}
    doc_section = _format_doc_context(node, doc_context)
    return (
        f"Developer profile:\n"
        f"  experience level: {goal.get('experience_level', 'unknown')}\n"
        f"  familiarity with THIS codebase: {goal.get('familiarity', 'unknown')}\n"
        f"  background: {goal.get('background', 'unknown')}\n"
        f"Overall goal: {goal.get('primary_goal', '')}\n"
        f"Depth requested: {goal.get('depth', 'normal')}\n\n"
        f"{prior_context}\n\n"
        f"{doc_section}"
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
    doc_context = state.doc_context if state.doc_context is not None else state.graph.doc_context
    user_content = _build_user_content(state.goal, node, source, prior_context, supporting, doc_context=doc_context)

    try:
        output = _generate_lesson(client, user_content)
        lesson = output.model_dump()
        node.cached_lesson = lesson
        state.current_lesson = lesson
    except Exception as e:
        state.errors.append(f"teaching_agent LLM call failed: {e}")

    return state


def _generate_lesson(client: anthropic.Anthropic, user_content: str) -> LessonOutput:
    """One Haiku call, with a single corrective retry on a parse failure.

    Haiku occasionally wraps the JSON in prose or emits malformed JSON. Like
    the Mentor's retries and the Grader's fallback, we don't let one bad
    response fail the lesson — we show the model its miss and ask once more.
    """
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    raw = response.content[0].text
    try:
        return _parse_output(raw)
    except Exception:
        retry = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": user_content},
                {"role": "assistant", "content": raw},
                {"role": "user", "content": (
                    "That was not a valid JSON object. Return ONLY the JSON object "
                    "with keys walkthrough, prompt, expected_answer, prompt_kind — "
                    "no markdown fences, no prose."
                )},
            ],
        )
        return _parse_output(retry.content[0].text)  # may raise → caller logs it
