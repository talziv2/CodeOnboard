"""
Inspect a ChromaDB collection — counts chunks by role and by top-level path
segment so we can confirm what is actually indexed for a given repo.

Useful for sanity-checking the chunker + role tagging after a re-embed.
Reports nothing about embeddings; only metadata.

Run with:
    .venv\\Scripts\\python.exe scripts\\inspect_collection.py <repo_url> [<repo_path>]

If <repo_path> is omitted it defaults to data/repos/<repo_name>, matching the
cloner's layout.
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.rag import store
from backend.rag.cloner import get_commit_sha, parse_repo_url


def _top_segment(file_path: str) -> str:
    # Metadata stores paths with the chunker's native separator (backslash on
    # Windows); normalize before splitting so the report is OS-agnostic.
    norm = file_path.replace("\\", "/")
    return norm.split("/", 1)[0] if "/" in norm else norm


def main(repo_url: str, repo_path: str) -> None:
    owner, repo = parse_repo_url(repo_url)
    commit_sha = get_commit_sha(repo_path)
    name = store.collection_name(owner, repo, commit_sha)

    if not store.collection_exists(name):
        print(f"collection {name!r} does not exist — nothing to inspect")
        return

    client = store._get_client()
    collection = client.get_collection(name=name)
    result = collection.get(include=["metadatas"])
    metas = result.get("metadatas") or []

    print(f"collection: {name}")
    print(f"total chunks: {len(metas)}")

    roles = Counter(m.get("role", "source") for m in metas)
    print("\nby role:")
    for role, count in roles.most_common():
        print(f"  {role:8s} {count}")

    top_segments = Counter(_top_segment(m["file"]) for m in metas)
    print("\nby top-level path segment:")
    for seg, count in top_segments.most_common():
        print(f"  {seg:30s} {count}")

    # Cross-tab role × top segment — handy for catching e.g. tests/ files
    # tagged as source by mistake.
    print("\nrole × top segment:")
    cross: Counter = Counter()
    for m in metas:
        cross[(m.get("role", "source"), _top_segment(m["file"]))] += 1
    for (role, seg), count in sorted(cross.items()):
        print(f"  {role:8s} {seg:30s} {count}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    url = sys.argv[1]
    if len(sys.argv) >= 3:
        path = sys.argv[2]
    else:
        repo_name = url.rstrip("/").split("/")[-1]
        path = f"data/repos/{repo_name}"
    main(url, path)
