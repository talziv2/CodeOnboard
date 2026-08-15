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
from backend.repo import dossier_context, dossier_store, structure
from backend.repo.skeleton import build_skeleton


MODEL = "claude-haiku-4-5"
# Walkthroughs are the longest prose in the system. 2048 was too tight — a long
# lesson would get truncated mid-JSON-string ("Unterminated string" on parse).
# Match the Mentor's budget so the JSON always closes.
MAX_TOKENS = 8192



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
  - the LEARNING OBJECTIVE for this lesson (see below)
  - a "lesson brief": why this piece matters and what they should take away
  - the actual source code for this piece
  - system context: how this piece connects to the rest of the codebase
  - the node's concept tags (frame your walkthrough around the dominant tag)

THE OBJECTIVE IS YOUR BRIEF. It is the claim the developer should be able to
make, in their own words, when the lesson ends — written by the planner who
designed their whole path, and the same claim their answer will be marked
against. Build exactly that claim. If the code shown would support a more
interesting lesson than the objective asks for, you still build the objective:
the path depends on this node delivering what the next ones assume. Teach
whatever the objective requires and no more.

CRITICAL: Your ENTIRE response must be under 600 words. Be very concise.

Produce a JSON object with exactly these keys:
  walkthrough:     markdown. MAX 250 words. Explain this code so the developer
                   can make the objective's claim. Be brief and direct.
                   Reference key identifiers only — no exhaustive walkthroughs.
  prompt:          ONE active-learning question of the "predict-then-reveal"
                   form — ask the developer to predict something about this code
                   BEFORE they read your explanation in full (e.g. "Before
                   reading on: what do you think `Session.send` does with the
                   adapter it looks up?"). It must be answerable from the code
                   shown, and answering it well must require the objective's
                   claim — not a detail beside it.
  expected_answer: a concise model answer to your prompt — one way a developer
                   who reached the objective might phrase it. This is a
                   calibration reference for the grader, not the marking
                   standard: the objective is what gets marked.
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
                        path that continues through the connected code.
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
  or relationships not visible in the code or the system context.
- Keep the walkthrough focused on THIS piece — the system context is
  context, not a second lesson. The target word count is set by
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


# Module names too generic to identify a docs page — matching on them produces
# a confidently wrong pairing rather than no pairing, which is worse.
_GENERIC_STEMS = frozenset({
    "__init__", "__main__", "main", "app", "base", "core", "utils", "util",
    "helpers", "common", "types", "compat", "constants", "config", "settings",
})
# How many times a module must be named in a docs page before we accept that
# page as being about it. One passing mention is not a topic.
_MIN_DOC_MENTIONS = 2


def _pick_extra_doc(file: str, extra: dict[str, str]) -> tuple[str, str] | None:
    """Pick the docs/ page most likely to be *about* `file`, or None.

    Two passes, strongest signal first:
      1. the module's name appears in the docs filename ("sessions" → sessions.rst)
      2. otherwise, the page that names the module most often in its body

    The second pass is what makes this fire at all. Projects name docs pages
    after topics ("advanced.rst", "quickstart.rst"), not after modules, so
    requiring the module name in the *path* — as this once did — meant the
    section was almost never emitted.
    """
    stem = Path(file).stem.lower()
    if len(stem) < 4 or stem in _GENERIC_STEMS:
        return None
    # Modules are named in the plural, prose is written in the singular:
    # `sessions.py` is documented as "the Session object". Searching for the
    # singular finds both, since it is a prefix of the plural.
    needle = stem[:-1] if stem.endswith("s") and len(stem) > 4 else stem

    for doc_path, content in extra.items():
        if needle in Path(doc_path).stem.lower():
            return doc_path, content

    best: tuple[str, str] | None = None
    best_mentions = _MIN_DOC_MENTIONS - 1
    for doc_path, content in extra.items():
        mentions = content.lower().count(needle)
        if mentions > best_mentions:
            best, best_mentions = (doc_path, content), mentions
    return best


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

    # 4. Relevant docs/ file
    picked = _pick_extra_doc(file, doc_context.get("extra_docs") or {})
    if picked is not None:
        doc_path, content = picked
        parts.append(f"Docs file ({doc_path}):\n{content[:500]}")

    if not parts:
        return ""
    return "\n\n".join(parts) + "\n\n"


def _build_user_content(
    goal: dict,
    node: LearningNode,
    source: str,
    prior_context: str,
    doc_context: dict | None = None,
    system_context: str = "",
) -> str:
    brief = node.lesson_brief or {}
    doc_section = _format_doc_context(node, doc_context)
    # One slot, filled by whichever provider had something to say — the dossier
    # slice, the structural neighbourhood, or neither. A source-only lesson is a
    # supported mode, so an empty section stays empty rather than being padded
    # with a placeholder the model would try to interpret.
    context_section = f"{system_context}\n\n" if system_context else ""
    return (
        f"Developer profile:\n"
        f"  familiarity with THIS codebase: {goal.get('familiarity', 'unknown')}\n"
        f"  background: {goal.get('background', 'unknown')}\n"
        f"Overall goal: {goal.get('primary_goal', '')}\n"
        f"Depth requested: {goal.get('depth', 'normal')}\n\n"
        f"{prior_context}\n\n"
        f"{doc_section}"
        f"LEARNING OBJECTIVE — build exactly this claim:\n"
        f"  {node.objective() or '(none stated — build the takeaway below)'}\n\n"
        f"Lesson brief for this node:\n"
        f"  title: {node.title}\n"
        f"  why: {brief.get('why', '')}\n"
        f"  understand: {brief.get('understand', '')}\n"
        f"  concepts: {', '.join(node.concept_tags) if node.concept_tags else '—'}\n\n"
        f"Source code for this node "
        f"({node.code_anchor.file} lines "
        f"{node.code_anchor.line_start}–{node.code_anchor.line_end}):\n"
        f"{source}\n\n"
        f"{context_section}"
    )


def _parse_output(raw: str) -> LessonOutput:
    """Decode the lesson JSON, tolerating a markdown fence around it.

    NEVER cut at the closing fence. A walkthrough is markdown and routinely
    contains its own ```python block, so splitting on the next ``` truncates the
    JSON mid-string — which surfaces as "Unterminated string" pointing at the
    walkthrough's opening quote and looks exactly like an output-limit
    truncation. Measured on a real lesson: `stop_reason=end_turn`, 674 output
    tokens, a complete response, and both the call and its retry "failed".
    `raw_decode` already stops at the end of the object, so trailing text —
    including the closing fence — needs no handling at all.
    """
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else ""
    start = raw.find("{")
    if start < 0:
        raise ValueError("no JSON object found in response")
    decoded, _ = json.JSONDecoder().raw_decode(raw[start:])
    return LessonOutput(**decoded)


def _session_dossier(state: OnboardState) -> dict | None:
    """The investigation for this session, from state or from the store.

    At onboarding time it rides on `state.investigation`; at session time the
    request is rebuilt from the persisted graph, so it is loaded by session id.
    Unavailable for any reason (absent, schema bump, moved commit, corrupt) is a
    supported state — the caller falls back (D12).
    """
    if state.investigation:
        return state.investigation.get("dossier")
    if state.graph is None:
        return None
    try:
        from backend.repo.cloner import get_commit_sha

        commit_sha = get_commit_sha(state.repo_path) if state.repo_path else None
    except Exception:
        commit_sha = None
    stored = dossier_store.load_investigation(state.graph.session_id, commit_sha)
    if stored is None:
        return None
    state.investigation = stored
    return stored.get("dossier")


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

    # System context for this lesson, in strict preference order:
    #
    #   1. DOSSIER    the investigation's structured understanding, sliced to
    #                 THIS node deterministically (component role, flow
    #                 neighbourhood, relationships, contracts, prerequisites,
    #                 evidence). Preferred because it knows the user's GOAL.
    #   2. SKELETON   the repository's own structure around the node — what it
    #                 extends, what it uses, what uses it. Knows nothing about
    #                 the goal, but is grounded by construction and available
    #                 whenever the checkout is.
    #   3. NOTHING    a source-only lesson, which is a valid degraded mode.
    #
    # D12 is the reason rung 2 exists: an absent, stale or version-mismatched
    # dossier is a SUPPORTED state, not an error, and it must not fall through
    # to nothing when the repository can still say something true. The anchored
    # source is the lesson's evidence either way — everything here is
    # enrichment, and no failure in it may block a lesson.
    system_context = ""
    skeleton = None
    try:
        skeleton = build_skeleton(state.repo_path)
    except Exception as e:
        state.errors.append(f"teaching_agent: skeleton unavailable (non-fatal): {e}")

    dossier = _session_dossier(state)
    if dossier is not None and skeleton is not None:
        try:
            system_context = dossier_context.context_for_node(
                skeleton,
                dossier,
                node.code_anchor.file,
                symbol=node.code_anchor.symbol,
                line_start=node.code_anchor.line_start,
                line_end=node.code_anchor.line_end,
            ).as_prompt_section()
        except Exception as e:
            state.errors.append(
                f"teaching_agent: dossier context failed (non-fatal): {e}"
            )
    if not system_context and skeleton is not None:
        try:
            system_context = structure.neighbour_context(
                skeleton,
                node.code_anchor.file,
                symbol=node.code_anchor.symbol,
                line_start=node.code_anchor.line_start,
                line_end=node.code_anchor.line_end,
            )
        except Exception as e:
            state.errors.append(
                f"teaching_agent: structural context failed (non-fatal): {e}"
            )

    prior_context = _build_prior_context(state.graph, current_id)
    doc_context = state.doc_context if state.doc_context is not None else state.graph.doc_context
    user_content = _build_user_content(
        state.goal, node, source, prior_context,
        doc_context=doc_context, system_context=system_context,
    )

    try:
        output = _generate_lesson(client, user_content, _SYSTEM_PROMPT)
        lesson = output.model_dump()
        node.cached_lesson = lesson
        state.current_lesson = lesson
    except Exception as e:
        state.errors.append(f"teaching_agent LLM call failed: {e}")

    return state


def _generate_lesson(
    client: anthropic.Anthropic, user_content: str, system: str = _SYSTEM_PROMPT
) -> LessonOutput:
    """One Haiku call, with a single corrective retry on a parse failure.

    Haiku occasionally wraps the JSON in prose or emits malformed JSON. Like
    the Mentor's retries and the Grader's fallback, we don't let one bad
    response fail the lesson — we show the model its miss and ask once more.
    """
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )
    raw = _text_of(response)
    try:
        return _parse_output(raw)
    except Exception:
        retry = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[
                {"role": "user", "content": user_content},
                {"role": "assistant", "content": raw},
                {"role": "user", "content": _correction(response)},
            ],
        )
        return _parse_output(_text_of(retry))  # may raise → caller logs it


def _text_of(response) -> str:
    """Every text block, joined — not just the first.

    `content[0].text` silently truncates a response the model split across
    blocks, and the resulting fragment fails to parse as "Unterminated string"
    at the very start of the JSON, which reads exactly like an output-limit
    truncation and is not one. Cheap to be right about; the harness has always
    joined blocks this way.
    """
    return "".join(
        block.text for block in response.content
        if isinstance(getattr(block, "text", None), str)
    )


# Two different faults present as the same "Unterminated string" parse error, and
# they need opposite corrections. Telling a model that ran out of output tokens
# that its JSON was malformed makes it emit the same too-long lesson again and
# truncate in the same place — observed on a 87-line doc-heavy anchor, where both
# the call and its retry failed and the session fell back to a placeholder.
_CORRECTION_MALFORMED = (
    "That was not a valid JSON object. Return ONLY the JSON object with keys "
    "walkthrough, prompt, expected_answer, prompt_kind — no markdown fences, no "
    "prose."
)
_CORRECTION_TRUNCATED = (
    "Your response hit the output limit and was cut off mid-JSON, so it could not "
    "be read. Write a SHORTER lesson this time — the same teaching, fewer words: "
    "trim the walkthrough hardest, quote less source, and close the JSON. Return "
    "ONLY the JSON object with keys walkthrough, prompt, expected_answer, "
    "prompt_kind."
)


def _correction(response) -> str:
    truncated = getattr(response, "stop_reason", None) == "max_tokens"
    return _CORRECTION_TRUNCATED if truncated else _CORRECTION_MALFORMED
