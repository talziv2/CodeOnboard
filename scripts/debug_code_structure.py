"""
Debug script: call Haiku with the Code Structure Agent's prompt and dump
the raw response so we can see what's actually breaking the JSON parse.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anthropic
from dotenv import load_dotenv

from backend.agents.code_structure.agent import MAX_CHUNKS, MODEL, _build_prompt
from backend.rag.chunker import chunk_repo
from backend.rag.cloner import clone_repo


load_dotenv()


def main() -> None:
    repo_path = clone_repo("https://github.com/psf/requests")
    chunks = chunk_repo(repo_path)
    sampled = [c for c in chunks if c["type"] != "import"][:MAX_CHUNKS]

    print(f"Sampled {len(sampled)} chunks")
    prompt = _build_prompt(sampled)
    print(f"Prompt size: {len(prompt)} chars\n")

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    print(f"Stop reason: {response.stop_reason}")
    print(f"Input tokens:  {response.usage.input_tokens}")
    print(f"Output tokens: {response.usage.output_tokens}")
    print("\n── raw response ──")
    print(response.content[0].text)
    print("\n── end ──")


if __name__ == "__main__":
    main()
