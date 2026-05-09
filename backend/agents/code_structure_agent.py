import json

import anthropic

from backend.pipeline.state import OnboardState
from backend.rag.cloner import clone_repo
from backend.rag.chunker import chunk_repo

CLIENT = anthropic.Anthropic()
MODEL = "claude-haiku-4-5"
MAX_CHUNKS = 80


def _build_prompt(chunks: list[dict]) -> str:
    lines = []
    for chunk in chunks:
        if chunk["type"] == "import":
            continue
        lines.append(f"[{chunk['type'].upper()}] {chunk['name']} — {chunk['file']} (lines {chunk['start_line']}–{chunk['end_line']})")

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


def run(state: OnboardState) -> OnboardState:
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

    non_import_chunks = [c for c in chunks if c["type"] != "import"]
    sampled = non_import_chunks[:MAX_CHUNKS]

    try:
        prompt = _build_prompt(sampled)
        response = CLIENT.messages.create(
            model=MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        state.module_map = json.loads(raw)
    except Exception as e:
        state.errors.append(f"code_structure_agent LLM call failed: {e}")

    return state
