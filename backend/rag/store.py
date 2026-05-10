import re
from functools import lru_cache
from pathlib import Path

import chromadb


CHROMA_DIR = Path("data/chroma")
COMMIT_SHA_LEN = 12


@lru_cache(maxsize=1)
def _get_client() -> chromadb.api.ClientAPI:
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def collection_name(owner: str, repo: str, commit_sha: str) -> str:
    raw = f"{owner}_{repo}_{commit_sha[:COMMIT_SHA_LEN]}"
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", raw).lower()
    return sanitized[:63]


def collection_exists(name: str) -> bool:
    client = _get_client()
    return any(c.name == name for c in client.list_collections())


def add_chunks(
    name: str,
    chunks: list[dict],
    embeddings: list[list[float]],
) -> None:
    if not chunks:
        return

    client = _get_client()
    collection = client.get_or_create_collection(name=name)

    ids = [
        f"{c['file']}:{c['start_line']}-{c['end_line']}:{c['name']}"
        for c in chunks
    ]
    documents = [c["content"] for c in chunks]
    metadatas = [
        {
            "file": c["file"],
            "start_line": c["start_line"],
            "end_line": c["end_line"],
            "type": c["type"],
            "name": c["name"],
            "language": c["language"],
        }
        for c in chunks
    ]

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )


def query(name: str, query_embedding: list[float], top_k: int = 5) -> dict:
    client = _get_client()
    collection = client.get_collection(name=name)
    return collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
    )
