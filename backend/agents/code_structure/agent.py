# Code Structure Agent — clones repo, chunks it, embeds chunks into ChromaDB,
# and builds a module map.
#
# Entry point:
#   run(state, client)  → clones repo, chunks Python files, embeds chunks into
#                         ChromaDB (cached per commit), calls Haiku once to
#                         produce a validated ModuleEntry map, writes everything
#                         to state, and returns it.
#
# Mirrors the Goal Agent pattern: client is injected rather than module-level,
# making unit tests simple (no patching of globals required).

import json
import os

import anthropic
from pydantic import BaseModel

from backend.pipeline.state import OnboardState
from backend.rag.cloner import clone_repo, get_commit_sha, parse_repo_url
from backend.rag.chunker import chunk_repo
from backend.rag import embedder, store

MODEL = "claude-haiku-4-5"
MAX_CHUNKS = 80


class ModuleEntry(BaseModel):
    purpose: str
    key_files: list[str]
    exports: list[str]
    dependencies: list[str]


def _build_prompt(chunks: list[dict]) -> str:
    lines = []
    for chunk in chunks:
        if chunk["type"] == "import":
            continue
        lines.append(
            f"[{chunk['type'].upper()}] {chunk['name']} — "
            f"{chunk['file']} (lines {chunk['start_line']}–{chunk['end_line']})"
        )

    chunk_summary = "\n".join(lines)

    return f"""You are analyzing a Python codebase.
Below is a list of its modules, classes, and functions with their file locations.

{chunk_summary}

Your tasks:
1. In ~200 words, describe the overall architecture and identify the key entry points.
2. Return a JSON object where each key is a module name (without .py extension) with these fields:
   - purpose: one sentence describing what this module does
   - key_files: list of the most important files in this module
   - exports: list of the key classes or functions it exposes
   - dependencies: list of other modules it depends on

Return ONLY valid JSON. No explanation before or after it."""


def _parse_module_map(raw: str) -> dict[str, ModuleEntry]:
    raw = _extract_json_object(raw)
    data = json.loads(raw)
    return {name: ModuleEntry(**entry) for name, entry in data.items()}


def _extract_json_object(raw: str) -> str:
    raw = raw.strip()
    # Prefer content inside a ```json fence, then any ``` fence, otherwise
    # fall back to the substring from the first { onward.
    if "```json" in raw:
        raw = raw.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in raw:
        parts = raw.split("```")
        if len(parts) >= 2:
            raw = parts[1]
    start = raw.find("{")
    if start < 0:
        raise ValueError("no JSON object found in response")
    # raw_decode parses one JSON value and ignores any trailing text.
    decoded, _ = json.JSONDecoder().raw_decode(raw[start:])
    return json.dumps(decoded)


def _embed_chunks(state: OnboardState, chunks: list[dict]) -> None:
    embeddable = [c for c in chunks if c["type"] != "import"]
    if not embeddable:
        return

    owner, repo = parse_repo_url(state.repo_url)
    commit_sha = get_commit_sha(state.repo_path)
    name = store.collection_name(owner, repo, commit_sha)

    if store.collection_exists(name):
        state.chunks_embedded = True
        return

    texts = [c["content"] for c in embeddable]
    vectors = embedder.embed_documents(texts)
    store.add_chunks(name, embeddable, vectors)
    state.chunks_embedded = True


def run(
    state: OnboardState,
    client: anthropic.Anthropic | None = None,
) -> OnboardState:
    if client is None:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    try:
        repo_path = clone_repo(state.repo_url)
        state.repo_path = repo_path
    except Exception as e:
        state.errors.append(f"cloner failed: {e}")
        return state

    try:
        chunks = chunk_repo(repo_path)
    except Exception as e:
        state.errors.append(f"chunker failed: {e}")
        return state

    try:
        _embed_chunks(state, chunks)
    except Exception as e:
        state.errors.append(f"embedding failed: {e}")

    sampled = [c for c in chunks if c["type"] != "import"][:MAX_CHUNKS]

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": _build_prompt(sampled)}],
        )
        raw = response.content[0].text.strip()
        module_map = _parse_module_map(raw)
        state.module_map = {name: entry.model_dump() for name, entry in module_map.items()}
    except Exception as e:
        state.errors.append(f"code_structure_agent LLM call failed: {e}")

    return state
