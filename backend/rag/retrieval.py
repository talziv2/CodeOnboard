# Retrieval — turns goal + module_map + ChromaDB into a curated set of code
# chunks for the LLM to anchor on.
#
# Lifted out of the Mentor Agent in Phase 3 so the Teaching Agent can also use
# it (the Mentor builds the overall plan; the Teaching Agent will later pull
# extra context per-node from the same retrieval helpers).
#
# Public entry point:
#   retrieve_chunks(state) -> list[chunk_dict]
#
# Two strategies are chosen by the goal's RetrievalProfile:
#   - per_module : sweep every module shallowly (broad system tour).
#   - focused    : three-layer retrieval — per-pool candidates, RRF fusion to
#                  balance pool sizes, file-diversity cap. Goals that need
#                  multi-aspect matching (debug_issue, contribute_code) get
#                  query decomposition: the goal splits into sub-queries that
#                  are embedded and matched independently.
#
# After either strategy, redundant whole-class chunks are dropped when one of
# their methods is also in the result — the method is the more teachable unit.

from collections import Counter

from backend.pipeline.state import OnboardState
from backend.pipeline.profiles import RetrievalProfile, get_profile
from backend.rag import embedder, store
from backend.rag.cloner import get_commit_sha, parse_repo_url


# Reciprocal Rank Fusion constant. 60 is the value used in the original RRF
# paper (Cormack et al., 2009); the choice is conventional, not tuned per repo.
# Larger k flattens the rank-position weighting (everyone's vote counts more
# equally); smaller k makes top ranks dominate. 60 is the well-tested middle.
RRF_K = 60


def collection_name(state: OnboardState) -> str:
    owner, repo = parse_repo_url(state.repo_url)
    commit_sha = get_commit_sha(state.repo_path)
    return store.collection_name(owner, repo, commit_sha)


def effective_module_map(state: OnboardState) -> dict:
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


def flatten_chunk(doc: str, meta: dict) -> dict:
    return {
        "file": meta["file"],
        "start_line": meta["start_line"],
        "end_line": meta["end_line"],
        "type": meta["type"],
        "name": meta["name"],
        "role": meta.get("role", "source"),
        "content": doc,
    }


def drop_redundant_class_chunks(chunks: list[dict]) -> list[dict]:
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


def build_retrieval_query(goal: dict) -> str:
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


def build_retrieval_queries(goal: dict, profile: RetrievalProfile) -> list[str]:
    """Sub-queries to embed for focused retrieval.

    Without decomposition this is a single combined query. With it, each
    goal-specific field becomes its own query so the error message and what
    the developer already tried are matched on their own terms, not diluted
    inside one long string.
    """
    if not profile.decompose_query:
        return [build_retrieval_query(goal)]

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
    retrieve_chunks_focused.
    """
    return {"role": {"$in": sorted(profile.retrieval_roles)}}


def _single_role_where(role: str) -> dict:
    return {"role": role}


def rrf_fuse(ranked_lists: list[list[dict]], k: int = RRF_K) -> list[dict]:
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


def select_with_file_cap(
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


def retrieve_chunks_focused(
    state: OnboardState, profile: RetrievalProfile
) -> list[dict]:
    """Three-layer retrieval: per-pool candidates → RRF fusion → diversity cap."""
    name = collection_name(state)
    queries = build_retrieval_queries(state.goal, profile)
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
                [flatten_chunk(d, m) for d, m in zip(docs, metas)]
            )

    fused = rrf_fuse(ranked_lists)
    selected = select_with_file_cap(fused, profile.top_k, profile.max_per_file)

    if profile.drop_redundant_classes:
        selected = drop_redundant_class_chunks(selected)
    return selected


def retrieve_chunks_per_module(
    state: OnboardState, profile: RetrievalProfile
) -> list[dict]:
    name = collection_name(state)
    where = _role_where(profile)
    seen: set[tuple[str, int, int]] = set()
    results: list[dict] = []
    for entry in effective_module_map(state).values():
        exports = ", ".join(entry.get("exports", []))
        query_text = f"{entry['purpose']}. Exports: {exports}" if exports else entry["purpose"]
        embedding = embedder.embed_query(query_text)
        result = store.query(name, embedding, top_k=profile.per_module_top_k, where=where)
        for doc, meta in zip(result["documents"][0], result["metadatas"][0]):
            key = (meta["file"], meta["start_line"], meta["end_line"])
            if key in seen:
                continue
            seen.add(key)
            results.append(flatten_chunk(doc, meta))

    chunks = results[:profile.top_k]
    if profile.drop_redundant_classes:
        chunks = drop_redundant_class_chunks(chunks)
    return chunks


def retrieve_chunks(state: OnboardState) -> list[dict]:
    """Public entry point — picks the strategy from the goal's RetrievalProfile."""
    profile = get_profile(state.goal["goal_type"])
    if profile.retrieval_strategy == "per_module":
        return retrieve_chunks_per_module(state, profile)
    return retrieve_chunks_focused(state, profile)
