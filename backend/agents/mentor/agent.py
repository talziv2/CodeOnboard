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
from collections import Counter
from typing import Callable, Literal

import anthropic
from pydantic import BaseModel

from backend.pipeline.state import OnboardState
from backend.pipeline.profiles import RetrievalProfile, get_profile
from backend.rag import embedder, store
from backend.rag.cloner import get_commit_sha, parse_repo_url


MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096

# Reciprocal Rank Fusion constant. 60 is the value used in the original RRF
# paper (Cormack et al., 2009); the choice is conventional, not tuned per repo.
# Larger k flattens the rank-position weighting (everyone's vote counts more
# equally); smaller k makes top ranks dominate. 60 is the well-tested middle.
RRF_K = 60


class LearningPathStep(BaseModel):
    step: int
    title: str
    file: str
    line_range: tuple[int, int]
    why: str
    understand: str
    concepts: list[str]


class DuplicateAnchorsError(ValueError):
    """Raised when the LLM emits multiple steps anchored on the same chunk."""

    def __init__(self, duplicates: list[tuple[str, tuple[int, int]]]) -> None:
        self.duplicates = duplicates
        formatted = ", ".join(f"{f}:{r[0]}-{r[1]}" for f, r in duplicates)
        super().__init__(f"duplicate step anchors: {formatted}")


class MentorOutput(BaseModel):
    steps: list[LearningPathStep]
    confidence: Literal["high", "medium", "low"]


def _find_duplicate_anchors(
    output: MentorOutput,
) -> list[tuple[str, tuple[int, int]]]:
    seen: set[tuple[str, tuple[int, int]]] = set()
    duplicates: list[tuple[str, tuple[int, int]]] = []
    for step in output.steps:
        key = (step.file, tuple(step.line_range))
        if key in seen and key not in duplicates:
            duplicates.append(key)
        seen.add(key)
    return duplicates


def _normalize_path(p: str) -> str:
    """Fold Windows backslashes to forward slashes for cross-run comparison."""
    return p.replace("\\", "/")


def _ground_anchors(
    output: MentorOutput, chunks: list[dict]
) -> list[tuple[str, tuple[int, int]]]:
    """Match every step anchor against a retrieved chunk; auto-correct prefix
    stripping; return any anchors that still cannot be grounded.

    Two kinds of grounding pass:
      1. Exact:  (normalized step.file, start, end) is a known chunk anchor.
      2. Suffix: line range matches a chunk's range and the step's file is a
                 path-suffix of the chunk's file (e.g. step said ``params.py``,
                 chunk says ``fastapi/params.py``). Treated as the LLM dropping
                 the package prefix; auto-corrected by rewriting step.file.

    Anything that doesn't ground under either rule is returned to the caller
    so it can drive a corrective retry.
    """
    # Map normalized chunk paths to their canonical form, and build an index
    # from line range → list of chunk files sharing it.
    chunk_files_by_range: dict[tuple[int, int], list[str]] = {}
    valid_keys: set[tuple[str, int, int]] = set()
    for c in chunks:
        cf = _normalize_path(c["file"])
        valid_keys.add((cf, c["start_line"], c["end_line"]))
        chunk_files_by_range.setdefault(
            (c["start_line"], c["end_line"]), []
        ).append(cf)

    invalid: list[tuple[str, tuple[int, int]]] = []
    for step in output.steps:
        sf = _normalize_path(step.file)
        start, end = step.line_range

        if (sf, start, end) in valid_keys:
            step.file = sf  # canonicalize separators
            continue

        # Suffix match: tolerate dropped package prefix when the line range
        # matches a real chunk uniquely. ``sf`` may equal the chunk file
        # exactly, or be a trailing component of it ("/params.py").
        candidates = [
            cf
            for cf in chunk_files_by_range.get((start, end), [])
            if cf == sf or cf.endswith("/" + sf) or sf.endswith("/" + cf)
        ]
        if len(candidates) == 1:
            step.file = candidates[0]
            continue

        invalid.append((step.file, (start, end)))

    return invalid


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
- Copy file paths VERBATIM from the retrieved chunk metadata, including any
  package prefix (e.g. "fastapi/params.py", not just "params.py").
- Copy line_range VERBATIM from the retrieved chunk's start_line/end_line —
  do NOT pick round numbers or guess ranges.
- Source code is the implementation truth. Tests and examples are supporting
  behavioral evidence — anchor steps on source whenever both source and a
  test/example chunk can answer a step. Cite a test or example only when it
  reproduces the exact failure mode, shows a concrete usage idiom, or
  illustrates the extension surface the user must touch.
- 5–8 steps total. Order matters: each step builds on the previous one.
- Prefer the narrowest chunk that answers the step. When both an enclosing
  class and one of its methods are retrieved, anchor on the method's
  line_range — a whole class is rarely the right teaching unit.
- Each step must anchor on a distinct chunk. Do not reuse the same
  (file, line_range) pair across multiple steps; if the most relevant
  chunk has already been used, move to a sibling chunk instead.
- Only describe inheritance, imports, or call relationships that are
  visible in the retrieved chunks. Do not infer relationships from class
  names alone.
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


def _effective_module_map(state: OnboardState) -> dict:
    """Module map narrowed to the Prioritization Agent's relevant set, if any.

    When the Prioritization Agent ran, ``state.relevant_modules`` holds the
    module names worth reading for the goal; restricting retrieval and the
    prompt to those keeps the Sonnet call focused and cheaper. When it did
    not run (or filtering produced nothing usable), fall back to the full map.
    """
    if not state.relevant_modules:
        return state.module_map
    filtered = {
        name: entry
        for name, entry in state.module_map.items()
        if name in state.relevant_modules
    }
    return filtered or state.module_map


def _collection_name(state: OnboardState) -> str:
    owner, repo = parse_repo_url(state.repo_url)
    commit_sha = get_commit_sha(state.repo_path)
    return store.collection_name(owner, repo, commit_sha)


def _flatten_chunk(doc: str, meta: dict) -> dict:
    return {
        "file": meta["file"],
        "start_line": meta["start_line"],
        "end_line": meta["end_line"],
        "type": meta["type"],
        "name": meta["name"],
        "role": meta.get("role", "source"),
        "content": doc,
    }


def _drop_redundant_class_chunks(chunks: list[dict]) -> list[dict]:
    """Drop a class chunk when any of its methods are in the same result set.

    The chunker emits both whole-class chunks and per-method chunks. When
    both land in retrieval, the class chunk is redundant — its content
    already covers the method, but at a coarser line_range. Keeping only
    the method chunk nudges the LLM toward narrower, more teachable anchors.

    A chunk ``fn`` is considered a method of class chunk ``cls`` when:
      - ``cls["type"] == "class"`` and ``fn["type"] == "function"``
      - same file
      - ``cls.start_line <= fn.start_line`` and ``fn.end_line <= cls.end_line``
    """
    classes = [c for c in chunks if c["type"] == "class"]
    funcs = [c for c in chunks if c["type"] == "function"]

    redundant: set[tuple[str, int, int]] = set()
    for cls in classes:
        for fn in funcs:
            if (
                fn["file"] == cls["file"]
                and cls["start_line"] <= fn["start_line"]
                and fn["end_line"] <= cls["end_line"]
            ):
                redundant.add((cls["file"], cls["start_line"], cls["end_line"]))
                break

    return [
        c for c in chunks
        if (c["file"], c["start_line"], c["end_line"]) not in redundant
    ]


def _build_retrieval_query(goal: dict) -> str:
    primary = goal["primary_goal"]
    goal_type = goal["goal_type"]
    if goal_type == "understand_component":
        focus = goal.get("focus_area", "")
        return f"{primary}. Focus area: {focus}" if focus else primary
    if goal_type == "contribute_code":
        contribution = goal.get("contribution_context", "")
        return f"{primary}. Contribution: {contribution}" if contribution else primary
    if goal_type == "debug_issue":
        error = goal.get("error_description", "")
        tried = goal.get("tried_so_far", "")
        parts = [primary]
        if error:
            parts.append(f"Error: {error}")
        if tried:
            parts.append(f"Tried: {tried}")
        return ". ".join(parts)
    return primary


def _build_retrieval_queries(goal: dict, profile: RetrievalProfile) -> list[str]:
    """Sub-queries to embed for focused retrieval.

    Without decomposition this is a single combined query. With it, each
    goal-specific field becomes its own query so the error message and what
    the developer already tried are matched on their own terms, not diluted
    inside one long string.
    """
    if not profile.decompose_query:
        return [_build_retrieval_query(goal)]

    queries = [goal["primary_goal"]]
    if goal["goal_type"] == "debug_issue":
        extra_fields = ("error_description", "tried_so_far")
    elif goal["goal_type"] == "contribute_code":
        extra_fields = ("contribution_context",)
    else:
        extra_fields = ()
    for field in extra_fields:
        value = goal.get(field)
        if value:
            queries.append(value)
    return queries


def _role_where(profile: RetrievalProfile) -> dict:
    """ChromaDB metadata filter for all of the profile's roles in one query.

    Used by the per_module strategy, which is single-pool for every current
    goal. The focused strategy queries each role independently — see
    _retrieve_chunks_focused.
    """
    return {"role": {"$in": sorted(profile.retrieval_roles)}}


def _single_role_where(role: str) -> dict:
    """ChromaDB metadata filter for one role pool."""
    return {"role": role}


def _rrf_fuse(ranked_lists: list[list[dict]], k: int = RRF_K) -> list[dict]:
    """Reciprocal Rank Fusion.

    Each ranked list votes for its chunks with weight ``1 / (k + rank)``,
    where ``rank`` is the chunk's 1-indexed position in that list. Scores
    accumulate across lists; the final ordering is by total score, highest
    first. Because votes are based on rank position rather than raw
    similarity scores, a large pool cannot drown out a small one — a chunk
    that ranks #1 in its pool weighs the same as #1 in any other pool,
    regardless of how many candidates each pool contributed.

    Chunks are keyed by (file, start_line, end_line) so the same chunk
    appearing in multiple lists is fused, not duplicated.
    """
    scores: dict[tuple[str, int, int], float] = {}
    chunks_by_key: dict[tuple[str, int, int], dict] = {}
    for ranked in ranked_lists:
        for rank, chunk in enumerate(ranked, start=1):
            key = (chunk["file"], chunk["start_line"], chunk["end_line"])
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            chunks_by_key.setdefault(key, chunk)
    sorted_keys = sorted(scores, key=lambda k: scores[k], reverse=True)
    return [chunks_by_key[key] for key in sorted_keys]


def _select_with_file_cap(
    chunks: list[dict], top_k: int, max_per_file: int
) -> list[dict]:
    """Greedy select up to ``top_k`` chunks, capping any single file at
    ``max_per_file`` contributions.

    Prevents one large file (a 5,000-line ``routing.py``) from monopolising
    the final selection just because many of its methods score well.
    """
    counts: Counter = Counter()
    selected: list[dict] = []
    for chunk in chunks:
        f = chunk["file"]
        if counts[f] >= max_per_file:
            continue
        selected.append(chunk)
        counts[f] += 1
        if len(selected) >= top_k:
            break
    return selected


def _retrieve_chunks_focused(
    state: OnboardState, profile: RetrievalProfile
) -> list[dict]:
    """Three-layer retrieval: per-pool candidates → RRF fusion → diversity cap.

    Layer 1: goal-aware pool selection. profile.retrieval_roles is the
             pedagogical whitelist of evidence sources the goal cares about.
    Layer 2: each (sub_query, role) pair runs its own ChromaDB query and
             returns up to per_pool_k candidates; the resulting ranked lists
             are fused by RRF so pool-size imbalance cannot dominate.
    Layer 3: a per-file diversity cap stops any single file from flooding
             the final budget, then drop_redundant_classes removes class
             chunks whose methods are already in the selection.
    """
    name = _collection_name(state)
    queries = _build_retrieval_queries(state.goal, profile)
    roles = sorted(profile.retrieval_roles)

    ranked_lists: list[list[dict]] = []
    for query_text in queries:
        embedding = embedder.embed_query(query_text)
        for role in roles:
            where = _single_role_where(role)
            result = store.query(
                name, embedding, top_k=profile.per_pool_k, where=where
            )
            docs = result["documents"][0]
            metas = result["metadatas"][0]
            ranked_lists.append(
                [_flatten_chunk(d, m) for d, m in zip(docs, metas)]
            )

    fused = _rrf_fuse(ranked_lists)
    selected = _select_with_file_cap(fused, profile.top_k, profile.max_per_file)

    if profile.drop_redundant_classes:
        selected = _drop_redundant_class_chunks(selected)
    return selected


def _retrieve_chunks_per_module(
    state: OnboardState, profile: RetrievalProfile
) -> list[dict]:
    name = _collection_name(state)
    where = _role_where(profile)
    seen: set[tuple[str, int, int]] = set()
    results: list[dict] = []
    for entry in _effective_module_map(state).values():
        exports = ", ".join(entry.get("exports", []))
        query_text = f"{entry['purpose']}. Exports: {exports}" if exports else entry["purpose"]
        embedding = embedder.embed_query(query_text)
        result = store.query(name, embedding, top_k=profile.per_module_top_k, where=where)
        for doc, meta in zip(result["documents"][0], result["metadatas"][0]):
            key = (meta["file"], meta["start_line"], meta["end_line"])
            if key in seen:
                continue
            seen.add(key)
            results.append(_flatten_chunk(doc, meta))

    chunks = results[:profile.top_k]
    if profile.drop_redundant_classes:
        chunks = _drop_redundant_class_chunks(chunks)
    return chunks


def _retrieve_chunks(state: OnboardState) -> list[dict]:
    profile = get_profile(state.goal["goal_type"])
    if profile.retrieval_strategy == "per_module":
        return _retrieve_chunks_per_module(state, profile)
    return _retrieve_chunks_focused(state, profile)


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
    user_content = builder(state.goal, _effective_module_map(state), chunks)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        raw = response.content[0].text
        output = _parse_output(raw)

        # One retry if the LLM reused the same (file, line_range) for multiple
        # steps. The prompt rule already forbids this, but Sonnet sometimes
        # ignores it — showing it its own bad output is a much stronger signal.
        duplicates = _find_duplicate_anchors(output)
        if duplicates:
            retry_raw, retry_output = _retry_distinct_anchors(
                client, user_content, raw, duplicates
            )
            if retry_output is not None and not _find_duplicate_anchors(retry_output):
                output = retry_output
                raw = retry_raw
            else:
                state.errors.append(
                    f"mentor_agent: duplicate anchors persisted after retry: "
                    f"{[f'{f}:{r[0]}-{r[1]}' for f, r in duplicates]}"
                )

        # Ground every step anchor against the retrieved chunks. _ground_anchors
        # silently fixes prefix-stripped paths; anything still unmatched goes
        # through a corrective retry so the model can pick real chunks.
        invalid = _ground_anchors(output, chunks)
        if invalid:
            retry_raw, retry_output = _retry_grounded_anchors(
                client, user_content, raw, invalid, chunks
            )
            if retry_output is not None and not _ground_anchors(retry_output, chunks):
                output = retry_output
            else:
                state.errors.append(
                    f"mentor_agent: ungrounded anchors persisted after retry: "
                    f"{[f'{f}:{r[0]}-{r[1]}' for f, r in invalid]}"
                )

        state.learning_path = [step.model_dump() for step in output.steps]
        state.confidence = output.confidence
    except Exception as e:
        state.errors.append(f"mentor_agent LLM call failed: {e}")

    return state


def _retry_distinct_anchors(
    client: anthropic.Anthropic,
    user_content: str,
    previous_raw: str,
    duplicates: list[tuple[str, tuple[int, int]]],
) -> tuple[str, MentorOutput | None]:
    """Ask the LLM to regenerate with distinct anchors.

    Returns ``(raw_text, parsed_output)``. ``parsed_output`` is ``None`` if
    the retry response failed to parse — callers should keep the original
    output in that case.
    """
    dupe_str = ", ".join(f"{f} lines {r[0]}-{r[1]}" for f, r in duplicates)
    correction = (
        f"Your previous response reused these (file, line_range) anchors "
        f"across multiple steps: {dupe_str}. The rules require each step "
        f"to anchor on a DISTINCT chunk. Regenerate the JSON object with "
        f"distinct (file, line_range) pairs for every step. Return ONLY "
        f"the JSON object."
    )
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": previous_raw},
            {"role": "user", "content": correction},
        ],
    )
    raw = response.content[0].text
    try:
        return raw, _parse_output(raw)
    except Exception:
        return raw, None


def _format_anchor_inventory(chunks: list[dict]) -> str:
    """Compact list of (file, line_range) anchors the LLM is allowed to use."""
    lines = []
    for c in chunks:
        lines.append(
            f"  - {_normalize_path(c['file'])} lines {c['start_line']}-{c['end_line']}"
        )
    return "\n".join(lines)


def _retry_grounded_anchors(
    client: anthropic.Anthropic,
    user_content: str,
    previous_raw: str,
    invalid: list[tuple[str, tuple[int, int]]],
    chunks: list[dict],
) -> tuple[str, MentorOutput | None]:
    """Ask the LLM to regenerate using anchors that come from real chunks.

    Returns ``(raw_text, parsed_output)``. ``parsed_output`` is ``None`` if
    the retry response failed to parse — callers should keep the original
    output in that case.
    """
    bad = ", ".join(f"{f} lines {r[0]}-{r[1]}" for f, r in invalid)
    inventory = _format_anchor_inventory(chunks)
    correction = (
        f"Your previous response used these (file, line_range) anchors that "
        f"are NOT in the retrieved chunks: {bad}. Every step must anchor on "
        f"a real retrieved chunk — both the file path (copied verbatim, "
        f"including the package prefix) and the line range (copied verbatim "
        f"from the chunk metadata, not rounded or invented).\n\n"
        f"The complete set of allowed anchors is:\n{inventory}\n\n"
        f"Regenerate the JSON object using only anchors from that list. "
        f"Return ONLY the JSON object."
    )
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": previous_raw},
            {"role": "user", "content": correction},
        ],
    )
    raw = response.content[0].text
    try:
        return raw, _parse_output(raw)
    except Exception:
        return raw, None
