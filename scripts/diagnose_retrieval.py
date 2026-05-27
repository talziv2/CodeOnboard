"""
Diagnose what the Mentor Agent's retrieval actually surfaces for a goal.

For each sub-query × pool, prints the ranked candidate list, then shows the
RRF-fused order, then what survives the diversity cap and the redundant-class
filter. Finally checks a set of "expected" anchors (the ones a human reviewer
believes ought to be teaching anchors for the goal) and reports whether each
appears in the candidate pool, in the final selection, or not at all.

Use this when a smoke run shows the Mentor producing duplicate or weak
anchors — it answers "did retrieval surface the right chunks?" before we
debate prompt changes.

Run with:
    .venv\\Scripts\\python.exe scripts\\diagnose_retrieval.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from backend.agents.mentor.agent import (
    _build_retrieval_queries,
    _drop_redundant_class_chunks,
    _flatten_chunk,
    _rrf_fuse,
    _select_with_file_cap,
    _single_role_where,
)
from backend.pipeline.profiles import get_profile
from backend.rag import embedder, store
from backend.rag.cloner import get_commit_sha, parse_repo_url


load_dotenv(override=True)

REPO_URL = "https://github.com/fastapi/fastapi"
REPO_PATH = "data/repos/fastapi"

# The goal we want to diagnose. Mirrors scripts/smoke_onboard_fastapi.py.
GOAL = {
    "primary_goal": "add a new parameter source for request trailers",
    "goal_type": "contribute_code",
    "focus_area": "request parameter extraction",
    "experience_level": "intermediate",
    "depth": "deep",
    "target_repo": REPO_URL,
    "familiarity": "new to FastAPI internals",
    "background": "5 years of Python",
    "contribution_context": (
        "want to add a Trailer() param source alongside Header/Query/Path"
    ),
}

# Anchors a human reviewer believes the agent should be able to choose from.
# Each is (file_path, expected_start_line, expected_end_line, description).
# The check matches by file + start_line; end_line is informational.
EXPECTED_ANCHORS = [
    ("fastapi/params.py", 19, 25, "ParamTypes enum (extension point)"),
    ("fastapi/params.py", 26, 136, "Param base class (subclass target)"),
    ("fastapi/params.py", 303, 386, "Header class (closest analogue)"),
    ("fastapi/params.py", 387, 468, "Cookie class (lean analogue)"),
    ("fastapi/param_functions.py", 701, 2282, "Header() factory function"),
    ("fastapi/dependencies/utils.py", 393, 561, "analyze_param (param classification)"),
    ("fastapi/dependencies/utils.py", 562, 575, "add_param_to_fields (dispatch site)"),
    ("fastapi/dependencies/utils.py", 784, 868, "request_params_to_args (extraction)"),
    ("fastapi/dependencies/utils.py", 598, 735, "solve_dependencies (insertion site)"),
]


def _norm(p: str) -> str:
    return p.replace("\\", "/")


def _print_chunks(chunks, indent="    "):
    for i, c in enumerate(chunks, 1):
        file = _norm(c["file"])
        role = c.get("role", "?")
        print(
            f"{indent}{i:>3}.  [{role:6s}] {file}:{c['start_line']}-{c['end_line']}"
            f"  [{c['type']} {c['name']}]"
        )


def _print_fused(scored_chunks):
    for i, (score, c) in enumerate(scored_chunks, 1):
        file = _norm(c["file"])
        role = c.get("role", "?")
        print(
            f"    {i:>3}.  rrf={score:.5f}  [{role:6s}] {file}:{c['start_line']}-{c['end_line']}"
            f"  [{c['type']} {c['name']}]"
        )


def _rrf_fuse_with_scores(ranked_lists, k=60):
    """Same as _rrf_fuse but also returns each chunk's accumulated score."""
    scores = {}
    chunks_by_key = {}
    for ranked in ranked_lists:
        for rank, chunk in enumerate(ranked, start=1):
            key = (_norm(chunk["file"]), chunk["start_line"], chunk["end_line"])
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            chunks_by_key.setdefault(key, chunk)
    sorted_keys = sorted(scores, key=lambda k: scores[k], reverse=True)
    return [(scores[k], chunks_by_key[k]) for k in sorted_keys]


def main():
    profile = get_profile(GOAL["goal_type"])
    owner, repo = parse_repo_url(REPO_URL)
    sha = get_commit_sha(REPO_PATH)
    collection = store.collection_name(owner, repo, sha)

    print(f"goal_type       : {GOAL['goal_type']}")
    print(f"profile         : roles={sorted(profile.retrieval_roles)} "
          f"top_k={profile.top_k} per_pool_k={profile.per_pool_k} "
          f"max_per_file={profile.max_per_file} decompose={profile.decompose_query}")
    print(f"collection      : {collection}")

    queries = _build_retrieval_queries(GOAL, profile)
    print(f"\nsub-queries ({len(queries)}):")
    for q in queries:
        print(f"  - {q!r}")

    # Per-pool retrieval — same loop the Mentor Agent runs.
    ranked_lists = []
    for q in queries:
        print(f"\n=== sub-query: {q!r} ===")
        embedding = embedder.embed_query(q)
        for role in sorted(profile.retrieval_roles):
            print(f"\n  -- role: {role} (top {profile.per_pool_k}) --")
            result = store.query(
                collection, embedding, top_k=profile.per_pool_k,
                where=_single_role_where(role),
            )
            docs = result["documents"][0]
            metas = result["metadatas"][0]
            chunks = [_flatten_chunk(d, m) for d, m in zip(docs, metas)]
            if not chunks:
                print("    (empty)")
            else:
                _print_chunks(chunks)
            ranked_lists.append(chunks)

    # RRF fusion with scores.
    print("\n=== after RRF fusion ===")
    fused_with_scores = _rrf_fuse_with_scores(ranked_lists)
    print(f"  unique candidates: {len(fused_with_scores)}")
    _print_fused(fused_with_scores[:40])  # cap printed list

    # Diversity cap.
    fused_chunks = [c for _, c in fused_with_scores]
    capped = _select_with_file_cap(fused_chunks, profile.top_k, profile.max_per_file)
    print(f"\n=== after diversity cap (top {profile.top_k}, max {profile.max_per_file}/file) ===")
    _print_chunks(capped)

    # Redundant-class filter.
    final = _drop_redundant_class_chunks(capped) if profile.drop_redundant_classes else capped
    print(f"\n=== final (after drop_redundant_classes) ===")
    print(f"  count: {len(final)}")
    _print_chunks(final)

    # Expected-anchor check.
    print("\n=== expected-anchor check ===")
    all_keys = {(_norm(c["file"]), c["start_line"]) for c in fused_chunks}
    final_keys = {(_norm(c["file"]), c["start_line"]) for c in final}
    for file, start, end, desc in EXPECTED_ANCHORS:
        key = (file, start)
        in_pool = key in all_keys
        in_final = key in final_keys
        status = (
            "in final  " if in_final
            else "in pool   " if in_pool
            else "NOT FOUND "
        )
        print(f"  {status}  {file}:{start}-{end}  {desc}")


if __name__ == "__main__":
    main()
